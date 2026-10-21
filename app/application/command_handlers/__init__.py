"""Handlers de comandos — lógica de negocio del Gemelo Digital.

Flujo canónico de todo handler (plantilla ``_manejar_transicion``):

1. **UoW atómica**: carga caso y actor dentro de una sola transacción.
2. **Validación de dominio** específica del acto (congruencia, plazos).
3. **Guard del motor de estados**: ``CaseFlowEngine.can_transition()`` evalúa
   arista + RBAC + plazo (Art. 134 CPCN si precluyó).
4. **Ejecución**: ``CaseFlowEngine.execute()`` muta el agregado Caso y produce
   la fila ``TransicionEstado``.
5. **Trazabilidad obligatoria**: entrada inmutable en ``LogAuditoria`` con tipo
   de acto, actor, fecha, fundamento legal y estado resultante.

Todo comando exitoso queda así reproducible: el gemelo puede reconstruir el
estado actual recorriendo el log (replay determinista).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.application.commands import (
    AdmitirDemandaCommand,
    ApelarSentenciaCommand,
    ComandoBase,
    ContestarDemandaCommand,
    DictarSentenciaCommand,
    EjecutarSentenciaCommand,
    PresentarDemandaCommand,
)
from app.application.errors import (
    ConflictoDeEstado,
    ErrorGuardAdmision,
    ErrorPermisoProcesal,
    ErrorValidacion,
    PlazoPrecluido,
)
from app.application.unit_of_work import SqlAlchemyUnitOfWork
from app.db.base import (
    AccionAuditoria,
    EstadoProcesal,
    EtapaProcesal,
    RolActor,
    TipoResolucion,
)
from app.db.models import (
    Caso,
    CasoActor,
    Pretension,
    ResolucionJudicial,
    TransicionEstado,
)
from app.engine.flow_engine import CaseFlowEngine, Disparador
from app.services.plazo_service import EstadoPlazo, PlazoProcesal


@dataclass(frozen=True, slots=True)
class ResultadoComando:
    """Acreditación de un acto procesal consumado."""

    caso_id: uuid.UUID
    estado_anterior: str | None
    estado_resultante: str
    etapa_resultante: str
    accion_auditoria: str
    fundamento_legal: str
    timestamp: str
    id_registros: dict[str, str]


class BaseHandler:
    """Plantilla común: UoW + reloj + motor de flujo + registro de plazos."""

    disparador: Disparador
    accion: AccionAuditoria
    _comando_en_curso: Any

    def __init__(
        self,
        uow_factory: Any,
        flow_engine: CaseFlowEngine,
        clock: Any,
        registro_plazos: RegistroPlazos | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._flow = flow_engine
        self._clock = clock
        self._plazos = registro_plazos or RegistroPlazos.en_memoria()

    # ------------------------------------------------------------ plantilla
    def _manejar_transicion(
        self,
        comando: ComandoBase,
        *,
        accion_specificas: Any = None,
        resoluciones: Any = None,
    ) -> ResultadoComando:
        """Ejecuta el ciclo guard→execute→auditoría bajo una sola transacción.

        Args:
            comando: Orden procesal ya validada por Pydantic.
            accion_specificas: Callback ``(uow, caso) -> dict`` con efectos
                adicionales del acto (crear pretensiones, resolver fallos...).
            resoluciones: Callback ``(uow, caso) -> list[ResolucionJudicial]``
                para actos que emiten resolución judicial.
        """
        with self._uow_factory() as uow:
            if self.alta_desde_comando:
                # Alta del expediente: el propio comando crea el Caso y lo
                # deja en su estado inicial PRESENTADO (Arts. 37/146 CPCN).
                # No hay transición previa que validar; la auditoría registra
                # la creación con su fundamento normativo explícito.
                return self._manejar_alta(uow, comando, accion_specificas)
            caso = uow.cargar_caso(comando.caso_id)
            actor = uow.cargar_actor(comando.actor_id)
            self._verificar_legitimacion(comando, actor, caso)

            decision = self._flow.can_transition(
                caso_id=caso.id,
                estado_actual=caso.estado_actual,
                disparador=self.disparador,
                rol_actor=comando.rol_actor,
                plazos=self._plazos.plazos_de(caso.id),
                ahora=self._clock.now(),
            )
            if not decision.permitido:
                raise self._traducir_denegacion(decision)

            estado_antes = caso.estado_actual.value
            ids: dict[str, str] = {"caso": str(caso.id)}
            extras: dict[str, Any] = {}
            if accion_specificas is not None:
                extras = accion_specificas(uow, caso) or {}
            ids.update(extras.pop("ids", {}))

            registro = self._flow.execute(
                decision,
                caso=caso,
                clock=self._clock,
                transicion_cls=TransicionEstado,
                ejecutada_por_id=comando.actor_id,
            )
            uow.session.add(registro)
            uow.session.flush()
            ids["transicion"] = str(registro.id)

            if resoluciones is not None:
                emitidas: list[str] = []
                for resolucion in resoluciones(uow, caso) or []:
                    uow.session.add(resolucion)
                    uow.session.flush()
                    emitidas.append(str(resolucion.id))
                if emitidas:
                    ids["resoluciones"] = ",".join(emitidas)

            detalle: dict[str, Any] = {
                "acto": self.disparador.value,
                "actor": actor.nombre_razon_social,
                "rol": comando.rol_actor.value,
                "fecha_acto": self._clock.now().isoformat(),
                "fundamento_legal": decision.fundamento_legal,
                "estado_resultante": caso.estado_actual.value,
                "etapa_resultante": (
                    caso.etapa_actual.value if caso.etapa_actual else None
                ),
            }
            detalle.update(extras)
            uow.registrar_auditoria(
                caso_id=caso.id,
                accion=self.accion.value,
                entidad_afectada="caso",
                registro_id=str(caso.id),
                actor_id=comando.actor_id,
                estado_antes=estado_antes,
                estado_despues=caso.estado_actual.value,
                detalle=detalle,
            )
            return ResultadoComando(
                caso_id=caso.id,
                estado_anterior=estado_antes,
                estado_resultante=caso.estado_actual.value,
                etapa_resultante=(caso.etapa_actual.value if caso.etapa_actual else ""),
                accion_auditoria=self.accion.value,
                fundamento_legal=decision.fundamento_legal,
                timestamp=self._clock.now().isoformat(),
                id_registros=ids,
            )

    # ------------------------------------------------------------ auxiliares
    #: Actos de ALTA (crear expediente): True en PresentarDemandaHandler.
    #: El resto de actos procesales operan sobre un caso ya existente.
    alta_desde_comando: bool = False

    def _fundamento_alta(self, comando: Any) -> str:
        """Fundamento legal del acto de alta (sobrescríbalo por handler)."""
        raise NotImplementedError

    def _crear_caso_desde_comando(
        self, uow: SqlAlchemyUnitOfWork, comando: Any
    ) -> tuple[Caso, Any]:
        """Crea el expediente en PRESENTADO a partir del comando de alta."""
        raise NotImplementedError

    def _manejar_alta(
        self,
        uow: SqlAlchemyUnitOfWork,
        comando: ComandoBase,
        accion_specificas: Any,
    ) -> ResultadoComando:
        """Ejecuta el ciclo de ALTA bajo una sola transacción atómica.

        Efectos: creación del Caso (estado inicial PRESENTADO, calificación
        pendiente — Art. 148 CPCN), efectos específicos del acto (registro de
        pretensiones, vinculación de partes) y evento inmutable al
        LogAuditoria con fundamento legal. Devuelve ``estado_anterior=None``
        porque no existe estado previo: el expediente nace aquí.
        """
        actor_objeto: Any = None
        if getattr(comando, "actor_id", None) is not None:
            actor_objeto = uow.cargar_actor(comando.actor_id)
        caso, actor_objeto = self._crear_caso_desde_comando(uow, comando)

        extras: dict[str, Any] = {}
        ids: dict[str, str] = {"caso": str(caso.id)}
        if accion_specificas is not None:
            extras = accion_specificas(uow, caso) or {}
        ids.update(extras.pop("ids", {}))

        fundamento = self._fundamento_alta(comando)
        detalle: dict[str, Any] = {
            "acto": self.disparador.value,
            "actor": getattr(actor_objeto, "nombre_razon_social", None),
            "rol": comando.rol_actor.value,
            "fecha_acto": self._clock.now().isoformat(),
            "fundamento_legal": fundamento,
            "estado_resultante": caso.estado_actual.value,
            "etapa_resultante": (
                caso.etapa_actual.value if caso.etapa_actual else None
            ),
        }
        detalle.update(extras)
        uow.registrar_auditoria(
            caso_id=caso.id,
            accion=self.accion.value,
            entidad_afectada="caso",
            registro_id=str(caso.id),
            actor_id=getattr(comando, "actor_id", None),
            estado_antes=None,
            estado_despues=caso.estado_actual.value,
            detalle=detalle,
        )
        return ResultadoComando(
            caso_id=caso.id,
            estado_anterior=None,
            estado_resultante=caso.estado_actual.value,
            etapa_resultante=(caso.etapa_actual.value if caso.etapa_actual else ""),
            accion_auditoria=self.accion.value,
            fundamento_legal=fundamento,
            timestamp=self._clock.now().isoformat(),
            id_registros=ids,
        )

    @staticmethod
    def _verificar_legitimacion(comando: ComandoBase, actor: Any, caso: Caso) -> None:
        """RBAC de superficie: el rol declarado debe coincidir con el registrado.

        Complementa al RBAC por regla del motor: aquí se evita que alguien se
        atribuya un rol que no tiene inscrito en el expediente (falsedad).
        """
        if comando.rol_actor is RolActor.JUEZ:
            if caso.juez_id != comando.actor_id:
                raise ErrorPermisoProcesal(
                    "El actor no es el juez titular asignado al expediente."
                )
        else:
            vigente = next(
                (
                    i
                    for i in caso.intervenciones
                    if i.actor_id == comando.actor_id and i.hasta is None
                ),
                None,
            )
            if vigente is None or vigente.rol_en_caso is not comando.rol_actor:
                raise ErrorPermisoProcesal(
                    f"El actor no está inscrito en el expediente con el rol "
                    f"'{comando.rol_actor.value}' (Art. 39 y ss. CPCN)."
                )
        es_apoderado = comando.rol_actor.value.startswith("apoderado")
        if es_apoderado and not actor.numero_colegiado_abogado:
            raise ErrorValidacion(
                "El apoderado judicial debe tener número de colegiatura activo."
            )

    @staticmethod
    def _traducir_denegacion(decision: Any) -> Exception:
        """Convierte la denegación del motor en error HTTP apropiado."""
        if "legitimado" in decision.motivo:
            return ErrorPermisoProcesal(decision.motivo)
        if "precluid" in decision.motivo or "venció" in decision.motivo:
            return PlazoPrecluido(decision.motivo)
        return ConflictoDeEstado(decision.motivo)


class RegistroPlazos:
    """Registro de plazos activos por caso (en memoria; producción: tabla).

    Mantiene el acoplamiento mínimo: los handlers consultan vencimientos sin
    depender de la persistencia de plazos.
    """

    def __init__(self, almacen: dict[uuid.UUID, list[PlazoProcesal]]) -> None:
        self._almacen = almacen

    @classmethod
    def en_memoria(cls) -> RegistroPlazos:
        return cls({})

    def plazos_de(self, caso_id: uuid.UUID) -> list[PlazoProcesal]:
        return self._almacen.get(caso_id, [])

    def abrir(self, caso_id: uuid.UUID, nombre: str, computo: Any) -> PlazoProcesal:
        """Registra el cómputo de un plazo para el expediente (idempotente).

        Si ya existe un plazo CORRIENTE con el mismo nombre (p. ej. al
        rehacer un cómputo tras una interrupción, Art. 137 CPCN), se
        reemplaza en lugar de acumular duplicados — un acto procesal tiene
        UN solo plazo vigente por nombre.
        """
        from app.services.plazo_service import nuevo_plazo

        plazo = nuevo_plazo(caso_id, nombre, computo)
        lista = self._almacen.setdefault(caso_id, [])
        for i, existente in enumerate(lista):
            if existente.nombre == nombre and existente.estado is EstadoPlazo.CORRIENTE:
                lista[i] = plazo
                return plazo
        lista.append(plazo)
        return plazo

    def cerrar_vigente(self, caso_id: uuid.UUID, nombre: str) -> None:
        """Marca CUMPLIDO el plazo corriente de ese nombre (acto realizado)."""
        for plazo in self._almacen.get(caso_id, []):
            if plazo.nombre == nombre and plazo.estado is EstadoPlazo.CORRIENTE:
                plazo.estado = EstadoPlazo.CUMPLIDO


# ================================================================== DEMANDA
class PresentarDemandaHandler(BaseHandler):
    """Promoción del juicio ordinario civil (Arts. 37, 146-147 CPCN).

    Acto de ALTA: crea el expediente directamente en estado PRESENTADO
    (calificación pendiente, Art. 148 CPCN), registra las pretensiones
    deducidas —el ADN del proceso— y vincula al promovente como parte.
    No hay transición previa que validar porque el caso nace con el acto;
    la subsanación de una demanda INADMISIBLE_REFORMABLE se modela
    presentando de nuevo sobre el mismo expediente ya creado.

    GUARDS DE ADMISIÓN (``_verificar_guards_admision``): antes de tocar la
    BD se verifica el cumplimiento de los requisitos formales del libelo
    (Art. 146 CPCN). Un incumplimiento lanza ``ErrorGuardAdmision`` → HTTP
    400 con la cita normativa exacta, imitando la inadmisión reformable del
    Art. 147 CPCN sin persistir nada (transacción abortada por el UoW).
    """

    disparador = Disparador.PRESENTAR_DEMANDA
    accion = AccionAuditoria.PRESENTACION_ESCRITO
    alta_desde_comando = True

    #: Vías procesales civiles reconocidas por el CPCN (Ley 908).
    VIAS_PROCESALES_VALIDAS = frozenset(
        {
            "juicio_ordinario_civil",   # Arts. 146 y ss. CPCN
            "juicio_sumario",           # Arts. 390 y ss. CPCN (desalojo, alimentos)
            "proceso_monitorio",        # Arts. 448 y ss. CPCN (deuda documentada)
        }
    )

    def manejar(self, comando: PresentarDemandaCommand) -> ResultadoComando:
        # Guard de admisión ANTES de cualquier efecto sobre la BD:
        # el motor de flujo no admite un escrito formalmente defectuoso.
        self._verificar_guards_admision(comando)
        self._comando_en_curso = comando
        try:
            return self._manejar_transicion(comando, accion_specificas=self._efectos)
        finally:
            del self._comando_en_curso

    # ------------------------------------------------------- guards CPCN
    @classmethod
    def _verificar_guards_admision(cls, comando: PresentarDemandaCommand) -> None:
        """Valida los requisitos formales de la demanda (Art. 146 CPCN).

        Recorre todos los defectos (no falla al primero) para que el abogado
        pueda subsanar de una sola vez — espíritu del Art. 147 CPCN
        (inadmisible reformable, tercero día). Cada hallazgo cita su artículo.

        Raises:
            ErrorGuardAdmision: si falta algún requisito legal (HTTP 400).
        """
        defectos: list[str] = []

        # a) Determinación clara de la pretensión (Art. 146 num. 4 + Art. 37).
        for i, p in enumerate(comando.pretensiones, start=1):
            descripcion = p.descripcion.strip()
            if len(descripcion) < 15 or not descripcion.endswith((".", ";", ":")):
                defectos.append(
                    f"La pretensión N.º {i} no está determinada con claridad: "
                    "debe precisar qué se pide al juez (petitum), conforme al "
                    "Art. 146 numeral 4 y Art. 37 CPCN."
                )
        via = comando.tipo_proceso.strip().lower()
        if via not in cls.VIAS_PROCESALES_VALIDAS:
            defectos.append(
                f"Vía procesal '{comando.tipo_proceso}' desconocida: use "
                "'juicio_ordinario_civil', 'juicio_sumario' o 'proceso_"
                "monitorio' (Arts. 146, 390 y 448 CPCN)."
            )

        # b) Identificación y domicilio del demandado (Art. 146 num. 2).
        ddo = comando.demandado
        if len(ddo.nombre.strip()) < 3:
            defectos.append(
                "Falta la identificación del demandado: nombre o razón social "
                "insuficiente según el Art. 146 numeral 2 CPCN."
            )
        if len(ddo.domicilio.strip()) < 5:
            defectos.append(
                "Falta indicar el domicilio del demandado según el Art. 146 "
                "numeral 2 CPCN: sin dirección cierta es imposible el "
                "emplazamiento personal (Arts. 168 y ss. CPCN)."
            )

        # c) Acompañamiento de documentos esenciales (Art. 146 num. 5).
        anexos = [x for x in comando.documentos_esenciales if x and x.strip()]
        if not anexos:
            defectos.append(
                "La demanda no acompaña documentos esenciales: el título en "
                "que se funda la acción debe acompañarse al escrito inicial "
                "(Art. 146 numeral 5 CPCN; en monitorio, prueba literal de la "
                "deuda — Art. 449 CPCN)."
            )

        if defectos:
            raise ErrorGuardAdmision(defectos)

    # ------------------------------------------------------------- alta
    def _fundamento_alta(self, comando: Any) -> str:
        extra = (
            f" | Invocado: {comando.fundamento_legal}."
            if getattr(comando, "fundamento_legal", None)
            else ""
        )
        return (
            "Arts. 37 y 146 CPCN: promoción de la demanda; "
            "Art. 148 CPCN: calificación de admisión pendiente." + extra
        )

    def _crear_caso_desde_comando(
        self, uow: SqlAlchemyUnitOfWork, comando: Any
    ) -> tuple[Caso, Any]:
        """Alta atómica del expediente en PRESENTADO (Art. 148: calificación)."""
        actor = uow.cargar_actor(comando.actor_id)
        rol = comando.rol_actor
        if rol not in (RolActor.DEMANDANTE, RolActor.APODERADO_JUDICIAL_DEMANDANTE):
            raise ErrorPermisoProcesal(
                f"El rol '{rol.value}' no está legitimado para promover la "
                "demanda (legitimación, Arts. 37 y 39 CPCN)."
            )
        numero = self._generar_numero_expediente(uow, comando)
        caso = Caso(
            id=comando.caso_id,
            numero_expediente=numero,
            tipo_proceso=comando.tipo_proceso,
            materia=comando.materia,
            juzgado_asignado=comando.juzgado_asignado,
            etapa_actual=EtapaProcesal.CALIFICACION_DEMANDA,
            estado_actual=EstadoProcesal.PRESENTADO,
            cuantia=comando.cuantia,
            fecha_presentacion_demanda=comando.fecha_presentacion,
        )
        uow.session.add(caso)
        uow.session.flush()
        uow.session.add(
            CasoActor(
                caso_id=caso.id, actor_id=actor.id, rol_en_caso=rol
            )
        )
        uow.session.flush()
        return caso, actor

    @staticmethod
    def _generar_numero_expediente(
        uow: SqlAlchemyUnitOfWork, comando: Any
    ) -> str:
        """Número único provisional de expediente (reemplazable por el real
        asignado por el sistema de gestión judicial)."""
        from sqlalchemy import func, select

        existente = uow.session.scalar(
            select(Caso.numero_expediente).where(Caso.id == comando.caso_id)
        )
        if existente:
            return str(existente)
        secuencia = (uow.session.scalar(select(func.count(Caso.id))) or 0) + 1
        anio = comando.fecha_presentacion.year
        return f"{secuencia:05d}-{anio}-CIV-ORD"

    def _efectos(self, uow: SqlAlchemyUnitOfWork, caso: Caso) -> dict[str, Any]:
        comando: PresentarDemandaCommand = self._comando_en_curso
        ids: dict[str, str] = {}
        for orden, p in enumerate(comando.pretensiones, start=1):
            pretension = Pretension(
                caso_id=caso.id,
                codigo_tipo=p.codigo_tipo,
                orden=orden,
                descripcion=p.descripcion,
                fundamento_normativo=p.fundamento_normativo,
                monto_pretendido=p.monto_pretendido,
                es_principal=p.es_principal,
            )
            uow.session.add(pretension)
            uow.session.flush()
            ids[f"pretension_{orden}"] = str(pretension.id)
        return {"ids": ids, "num_pretensiones": len(comando.pretensiones)}


# ================================================================ ADMISIÓN
class AdmitirDemandaHandler(BaseHandler):
    """Auto iniciado que admite la demanda (Art. 148 CPCN).

    Efectos: traslada al demandado con emplazamiento de diez días (Art. 151),
    fija la fecha de admisión y abre formalmente la relación procesal.
    """

    disparador = Disparador.DEMANDA_ADMITIDA
    accion = AccionAuditoria.EMISION_RESOLUCION

    def manejar(self, comando: AdmitirDemandaCommand) -> ResultadoComando:
        self._comando_en_curso = comando
        try:
            resultado = self._manejar_transicion(
                comando,
                accion_specificas=self._efectos,
                resoluciones=self._emision_auto,
            )
        finally:
            del self._comando_en_curso
        if resultado.estado_resultante == EstadoProcesal.ADMITIDA.value:
            computo = comando.computo_reconstruido()  # calculado vía PlazoService
            if computo is not None:
                self._plazos.abrir(comando.caso_id, "contestacion_demanda", computo)
        return resultado

    def _efectos(self, uow: SqlAlchemyUnitOfWork, caso: Caso) -> dict[str, Any]:
        comando: AdmitirDemandaCommand = self._comando_en_curso
        if comando.admite:
            caso.fecha_admision = self._clock.now().date()
            caso.dias_plazo_vigente = comando.dias_emplazamiento
        return {
            "admite": comando.admite,
            "dias_emplazamiento": comando.dias_emplazamiento,
            "observaciones": comando.observaciones,
        }

    def _emision_auto(
        self, uow: SqlAlchemyUnitOfWork, caso: Caso
    ) -> list[ResolucionJudicial]:
        comando: AdmitirDemandaCommand = self._comando_en_curso
        resolucion = ResolucionJudicial(
            caso_id=caso.id,
            tipo=(
                TipoResolucion.AUTO_INICIADO
                if comando.admite
                else TipoResolucion.PROVIDENCIA
            ),
            numero_resolucion=comando.numero_resolucion,
            resumen=comando.resumen,
            parte_resolutiva=comando.parte_resolutiva,
            es_impugnable=False,
            emisor_id=comando.actor_id,
            fecha_resolucion=self._clock.now(),
        )
        return [resolucion]


# ============================================================== CONTESTACIÓN
class ContestarDemandaHandler(BaseHandler):
    """Contestación dentro del traslado de diez días (Art. 151 CPCN).

    Si el plazo ``contestacion_demanda`` venció, el motor rechaza (409) y la
    rebeldía queda firme (Art. 153 CPCN); si procede, cierra el plazo y
    registra excepciones y reconvención.
    """

    disparador = Disparador.CONTESTAR_DEMANDA
    accion = AccionAuditoria.PRESENTACION_ESCRITO

    def manejar(self, comando: ContestarDemandaCommand) -> ResultadoComando:
        self._comando_en_curso = comando
        try:
            resultado = self._manejar_transicion(
                comando, accion_specificas=self._efectos
            )
        finally:
            del self._comando_en_curso
        self._plazos.cerrar_vigente(comando.caso_id, "contestacion_demanda")
        return resultado

    def _efectos(self, uow: SqlAlchemyUnitOfWork, caso: Caso) -> dict[str, Any]:
        cmd: ContestarDemandaCommand = self._comando_en_curso
        ids: dict[str, str] = {}
        for orden, p in enumerate(cmd.contra_pretensiones, start=1):
            reconvencion = Pretension(
                caso_id=caso.id,
                codigo_tipo=p.codigo_tipo,
                orden=len(caso.pretensiones) + orden,
                descripcion=p.descripcion,
                fundamento_normativo=p.fundamento_normativo,
                monto_pretendido=p.monto_pretendido,
                es_principal=False,
            )
            uow.session.add(reconvencion)
            uow.session.flush()
            ids[f"reconvenccion_{orden}"] = str(reconvencion.id)
        return {
            "ids": ids,
            "excepciones_opuestas": cmd.excepciones_opuestas,
            "oferta_probatoria": cmd.oferta_probatoria,
        }


# ================================================================ SENTENCIA
class DictarSentenciaHandler(BaseHandler):
    """Sentencia definitiva motivada sobre cada pretensión (Arts. 192-201 CPCN).

    Valida **congruencia** (Art. 197 CPCN): el mapa ``fallos`` debe cubrir la
    totalidad de pretensiones del expediente; cada pretensión queda resuelta
    con su sentido de fallo y se emite la ``ResolucionJudicial`` correspondiente.
    """

    disparador = Disparador.DICTAR_SENTENCIA
    accion = AccionAuditoria.EMISION_RESOLUCION

    def manejar(self, comando: DictarSentenciaCommand) -> ResultadoComando:
        self._comando_en_curso = comando
        try:
            return self._manejar_transicion(
                comando,
                accion_specificas=self._resolver_pretensiones,
                resoluciones=self._emision,
            )
        finally:
            del self._comando_en_curso

    def _resolver_pretensiones(
        self, uow: SqlAlchemyUnitOfWork, caso: Caso
    ) -> dict[str, Any]:
        """Aplica los fallos a las pretensiones (Art. 197 CPCN: congruencia)."""
        comando: DictarSentenciaCommand = self._comando_en_curso
        pendientes = {p.id for p in caso.pretensiones}
        if not set(comando.fallos) >= pendientes:
            faltantes = [
                str(x) for x in sorted(pendientes - set(comando.fallos), key=str)
            ]
            raise ErrorValidacion(
                "Sentencia incongruente (Art. 197 CPCN): faltan pretensiones "
                f"por resolver: {faltantes}"
            )
        for pretension in caso.pretensiones:
            pretension.resuelta = True
            pretension.sentido_fallo = comando.fallos[pretension.id]
        return {"fallos": {str(k): v.value for k, v in comando.fallos.items()}}

    def _emision(
        self, uow: SqlAlchemyUnitOfWork, caso: Caso
    ) -> list[ResolucionJudicial]:
        comando: DictarSentenciaCommand = self._comando_en_curso
        resolucion = ResolucionJudicial(
            caso_id=caso.id,
            tipo=TipoResolucion.SENTENCIA_DEFINITIVA,
            numero_resolucion=comando.numero_resolucion,
            resumen=comando.resumen,
            parte_resolutiva=comando.parte_resolutiva,
            sentido_fallo=self._sintesis(comando.fallos.values()),
            es_impugnable=True,
            emisor_id=comando.actor_id,
            fecha_resolucion=self._clock.now(),
        )
        return [resolucion]

    @staticmethod
    def _sintesis(sentidos: Any) -> Any:
        sentidos = list(sentidos)
        if all(s is sentidos[0] for s in sentidos):
            return sentidos[0]
        from app.db.base import SentidoFallo

        return SentidoFallo.CON_LUGAR_PARCIALMENTE


# ================================================================= APELACIÓN
class ApelarSentenciaHandler(BaseHandler):
    """Recurso de apelación en quinto día (Arts. 246-248 CPCN).

    El motor exige el plazo vigente ``termino_apelacion``; fuera de él el
    fallo quedó firme y el recurso es improcedente (409 → preclusión).
    """

    disparador = Disparador.APELAR_SENTENCIA
    accion = AccionAuditoria.PRESENTACION_ESCRITO

    def manejar(self, comando: ApelarSentenciaCommand) -> ResultadoComando:
        resultado = self._manejar_transicion(
            comando,
            accion_specificas=lambda uow, caso: {
                "agravios": comando.agravios,
                "petitorio": comando.petitorio,
            },
        )
        self._plazos.cerrar_vigente(comando.caso_id, "termino_apelacion")
        return resultado


# ================================================================= EJECUCIÓN
class EjecutarSentenciaHandler(BaseHandler):
    """Ejecución forzosa de sentencia ejecutoriada (Arts. 258, 263 y ss. CPCN).

    Solo procede si la pretensión ejecutada fue estimatoria (CON_LUGAR /
    PARCIAL) y el expediente está FIRME; la condena se hace efectiva mediante
    el apremio solicitado por la parte acreedora.
    """

    disparador = Disparador.INICIAR_EJECUCION
    accion = AccionAuditoria.TRANSICION_ESTADO

    def manejar(self, comando: EjecutarSentenciaCommand) -> ResultadoComando:
        self._comando_en_curso = comando
        try:
            return self._manejar_transicion(
                comando, accion_specificas=self._verificar_titulo
            )
        finally:
            del self._comando_en_curso

    def _verificar_titulo(
        self, uow: SqlAlchemyUnitOfWork, caso: Caso
    ) -> dict[str, Any]:
        from app.db.base import SentidoFallo

        comando: EjecutarSentenciaCommand = self._comando_en_curso
        if caso.estado_actual is not EstadoProcesal.FIRME:
            raise ConflictoDeEstado(
                "La ejecución solo admite sentencias ejecutoriadas (Art. 258 CPCN)."
            )
        objetivo = next(
            (p for p in caso.pretensiones if p.id == comando.pretension_ejecutada_id),
            None,
        )
        if objetivo is None:
            raise ErrorValidacion("La pretensión indicada no pertenece al expediente.")
        if objetivo.sentido_fallo not in (
            SentidoFallo.CON_LUGAR,
            SentidoFallo.CON_LUGAR_PARCIALMENTE,
        ):
            raise ConflictoDeEstado(
                "No hay condena estimatoria que ejecutar en esa pretensión "
                "(sin contenido ejecutable, Art. 263 CPCN)."
            )
        return {
            "pretension_ejecutada": str(objetivo.id),
            "forma_de_apereo": comando.forma_de_apereo,
            "monto_liquido": (
                str(comando.monto_liquido) if comando.monto_liquido else None
            ),
            "titulo_ejecutivo": "sentencia_definitiva_ejecutoriada",
        }


MANEJADORES: dict[type[ComandoBase], str] = {
    PresentarDemandaCommand: "presentar_demanda",
    AdmitirDemandaCommand: "admitir_demanda",
    ContestarDemandaCommand: "contestar_demanda",
    DictarSentenciaCommand: "dictar_sentencia",
    ApelarSentenciaCommand: "apelar_sentencia",
    EjecutarSentenciaCommand: "ejecutar_sentencia",
}


def despacho(comando: ComandoBase) -> str:
    """Devuelve el nombre canónico del handler para un comando (registro)."""
    return MANEJADORES[type(comando)]


__all__ = [
    "ApelarSentenciaHandler",
    "BaseHandler",
    "ContestarDemandaHandler",
    "DictarSentenciaHandler",
    "EjecutarSentenciaHandler",
    "PresentarDemandaHandler",
    "RegistroPlazos",
    "ResultadoComando",
    "despacho",
]
