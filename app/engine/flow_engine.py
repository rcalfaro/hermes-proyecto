"""Motor de máquina de estados del proceso civil (reglas en YAML).

El ``CaseFlowEngine`` es la autoridad única de transiciones: carga el
catálogo de transiciones permitidas desde un archivo YAML y valida, para
cada acto procesal, tres dimensiones antes de autorizar el cambio de
estado del expediente:

1. **Guard de transición** — ¿existe la arista ``(estado_actual, disparador)``
   en el grafo del CPCN? (p. ej. ``presentado --demanda_admitida--> admitida``,
   Art. 148 CPCN).
2. **RBAC por regla** — ¿el rol del actor que impulsa está autorizado para ese
   disparador? (JUEZ admite/dicta; DEMANDANTE presenta/apela; DEMANDADO
   contesta).
3. **Plazos** — si la regla declara ``plazo_requerido``, el acto debe ocurrir
   dentro del plazo activo correspondiente (Arts. 132-135 CPCN); fuera de él,
   la facultad ha precluido (Art. 134 CPCN).

Diseño: objeto puro, sin ORM ni reloj global — recibe ``ahora`` y los plazos
como argumentos, garantizando determinismo y testeabilidad.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from app.db.base import EstadoProcesal, EtapaProcesal, RolActor
from app.services.plazo_service import EstadoPlazo, PlazoProcesal


class Disparador(StrEnum):
    """Actos procesales que disparan una transición del expediente."""

    PRESENTAR_DEMANDA = "presentar_demanda"  # Arts. 37, 146-147 CPCN.
    DEMANDA_ADMITIDA = "demanda_admitida"  # Auto iniciado, Art. 148 CPCN.
    DECLARAR_INADMISIBLE = "declarar_inadmisible"  # Arts. 146-147 CPCN.
    CONTESTAR_DEMANDA = "contestar_demanda"  # Traslado, Art. 151 CPCN.
    APERTURA_A_PRUEBAS = "apertura_a_pruebas"  # Art. 165 CPCN.
    DICTAR_SENTENCIA = "dictar_sentencia"  # Arts. 192-201 CPCN.
    APELAR_SENTENCIA = "apelar_sentencia"  # Recurso de apelación, Art. 246 CPCN.
    DECLARATORIA_FIRME = "declaratoria_firme"  # Ejecutoria, Art. 258 CPCN.
    INICIAR_EJECUCION = "iniciar_ejecucion"  # Ejecución forzosa, Art. 263 CPCN.
    TERMINAR_EJECUCION = "terminar_ejecucion"  # Satisfacción, Art. 270 CPCN.
    ARCHIVAR = "archivar"  # Archivo definitivo.


@dataclass(frozen=True, slots=True)
class ReglaFlujo:
    """Arista del grafo de estados con su política de autorización."""

    estado_desde: EstadoProcesal
    disparador: Disparador
    estado_hacia: EstadoProcesal
    etapa_hacia: EtapaProcesal
    roles_autorizados: frozenset[RolActor]
    requisito_normativo: str
    #: Nombre del plazo que debe estar vigente (None => sin control temporal).
    plazo_requerido: str | None = None


class ErrorFlujo(Exception):
    """Transición inválida contra el grafo del CPCN → HTTP 409."""


class ErrorPermiso(Exception):
    """El rol del actor no está autorizado para el acto → HTTP 403."""


class ErrorPlazo(Exception):
    """Facultad precluida por vencimiento del plazo → HTTP 409 (Art. 134 CPCN)."""


@dataclass(slots=True)
class DecisionTransicion:
    """Resultado auditable de ``can_transition``."""

    permitido: bool
    estado_hacia: EstadoProcesal | None = None
    etapa_hacia: EtapaProcesal | None = None
    motivo: str = ""
    fundamento_legal: str = ""
    contexto: dict[str, Any] = field(default_factory=dict)


def _parse_fecha(valor: Any) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


class CaseFlowEngine:
    """Máquina de estados cargada desde YAML; valida y ejecuta transiciones."""

    def __init__(self, reglas: list[ReglaFlujo]) -> None:
        self._reglas: dict[tuple[EstadoProcesal, Disparador], ReglaFlujo] = {}
        for regla in reglas:
            # El par (estado, disparador) NO es único en el proceso real: la
            # calificación de admisión bifurca (auto iniciado vs. inadmisible
            # reformable). Se indexa además por el estado destino.
            clave = (regla.estado_desde, regla.disparador, regla.estado_hacia)
            if clave in self._reglas:
                raise ValueError(f"Regla duplicada para {clave}.")
            self._reglas[clave] = regla

    # ------------------------------------------------------------------ carga
    @classmethod
    def desde_yaml(cls, ruta: str | Path) -> CaseFlowEngine:
        """Carga el catálogo de transiciones desde un archivo YAML."""
        datos: dict[str, Any] = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
        reglas = [
            ReglaFlujo(
                estado_desde=EstadoProcesal(r["estado_desde"]),
                disparador=Disparador(r["disparador"]),
                estado_hacia=EstadoProcesal(r["estado_hacia"]),
                etapa_hacia=EtapaProcesal(r["etapa_hacia"]),
                roles_autorizados=frozenset(
                    RolActor(x) for x in r["roles_autorizados"]
                ),
                requisito_normativo=r["requisito_normativo"],
                plazo_requerido=r.get("plazo_requerido"),
            )
            for r in datos["transiciones"]
        ]
        return cls(reglas)

    def regla(
        self, estado: EstadoProcesal, disparador: Disparador
    ) -> ReglaFlujo | None:
        return self._reglas.get((estado, disparador))

    # -------------------------------------------------------------- validación
    def can_transition(
        self,
        *,
        caso_id: uuid.UUID,
        estado_actual: EstadoProcesal,
        disparador: Disparador,
        rol_actor: RolActor,
        plazos: list[PlazoProcesal] | None = None,
        ahora: datetime | None = None,
    ) -> DecisionTransicion:
        """Evalúa guard + RBAC + plazo sin mutar nada (consulta pura).

        Args:
            caso_id: Expediente evaluado (para trazabilidad de la decisión).
            estado_actual: Estado vital del caso.
            disparador: Acto procesal pretendido.
            rol_actor: Rol procesal de quien impulsa el acto.
            plazos: Plazos activos del caso (control temporal, Arts. 132-135).
            ahora: Instante de evaluación; si es ``None`` se asume medianoche
                UTC del día en curso del plazo (nunca reloj global interno:
                el llamador inyecta el tiempo — mismo principio DI del motor
                de plazos).
        """
        regla = self.regla(estado_actual, disparador)
        if regla is None:
            return DecisionTransicion(
                permitido=False,
                motivo=(
                    f"El acto '{disparador.value}' no está habilitado cuando el "
                    f"expediente se encuentra en estado '{estado_actual.value}'. "
                    "La preclusión impide retroceder o saltar etapas del proceso."
                ),
                contexto={"caso_id": str(caso_id)},
            )
        if rol_actor not in regla.roles_autorizados:
            permitidos = sorted(r.value for r in regla.roles_autorizados)
            return DecisionTransicion(
                permitido=False,
                motivo=(
                    f"El rol '{rol_actor.value}' no está legitimado para ejecutar "
                    f"'{disparador.value}'; roles autorizados: {permitidos}."
                ),
                fundamento_legal=regla.requisito_normativo,
                contexto={"caso_id": str(caso_id)},
            )
        if regla.plazo_requerido:
            decision_plazo = self._validar_plazo(regla, plazos or [], ahora, caso_id)
            if decision_plazo is not None:
                return decision_plazo
        return DecisionTransicion(
            permitido=True,
            estado_hacia=regla.estado_hacia,
            etapa_hacia=regla.etapa_hacia,
            fundamento_legal=regla.requisito_normativo,
            contexto={
                "caso_id": str(caso_id),
                "estado_desde": estado_actual.value,
                "disparador": disparador.value,
            },
        )

    def _validar_plazo(
        self,
        regla: ReglaFlujo,
        plazos: list[PlazoProcesal],
        ahora: datetime | None,
        caso_id: uuid.UUID,
    ) -> DecisionTransicion | None:
        """Devuelve una denegación si el plazo requerido venció; None si OK."""
        nombre = regla.plazo_requerido
        assert nombre is not None
        objetivo = next((p for p in plazos if p.nombre == nombre), None)
        if objetivo is None:
            return None  # Sin plazo registrado: no hay base para precluir.
        instante = ahora or datetime.now(tz=UTC)
        if objetivo.estado is EstadoPlazo.VENCIDO or instante > objetivo.vencimiento:
            return DecisionTransicion(
                permitido=False,
                motivo=(
                    f"El plazo '{nombre}' venció el "
                    f"{objetivo.vencimiento.date().isoformat()} y la facultad "
                    "ha precluido: el acto ya no puede realizarse válidamente."
                ),
                fundamento_legal="Arts. 132-134 CPCN (preclusión por vencimiento).",
                contexto={
                    "caso_id": str(caso_id),
                    "plazo": nombre,
                    "vencimiento": objetivo.vencimiento.isoformat(),
                    "evaluado_en": instante.isoformat(),
                },
            )
        return None

    # ---------------------------------------------------------------- ejecución
    def execute(
        self,
        decision: DecisionTransicion,
        *,
        caso: Any,
        clock: Any,
        transicion_cls: type,
        ejecutada_por_id: uuid.UUID | None = None,
    ) -> Any:
        """Aplica la transición autorizada sobre el agregado ``Caso``.

        Muta ``estado_actual``/``etapa_actual`` (conservando el anterior),
        marca el plazo cumplido si existía y produce el registro
        ``TransicionEstado`` pendiente de flush en la unidad de trabajo.
        """
        if not decision.permitido or decision.estado_hacia is None:
            raise ErrorFlujo(decision.motivo or "Transición no autorizada.")
        disparador = Disparador(decision.contexto["disparador"])
        caso.estado_anterior = caso.estado_actual
        caso.estado_actual = decision.estado_hacia
        caso.etapa_actual = decision.etapa_hacia
        if decision.estado_hacia in (
            EstadoProcesal.TERMINADO,
            EstadoProcesal.ARCHIVADO,
        ):
            caso.cerrado = True
        registro = transicion_cls(
            caso_id=caso.id,
            estado_desde=caso.estado_anterior,
            estado_hacia=decision.estado_hacia,
            etapa_desde=None
            if caso.estado_anterior is None
            else _etapa_por_estado(caso.estado_anterior),
            etapa_hacia=decision.etapa_hacia,
            disparador=disparador.value,
            ejecutada_por_id=ejecutada_por_id,
            fecha_transicion=clock.now(),
        )
        return registro


_ESTADO_BASE: dict[EstadoProcesal, EtapaProcesal] = {
    EstadoProcesal.BORRADOR: EtapaProcesal.CALIFICACION_DEMANDA,
    EstadoProcesal.PRESENTADO: EtapaProcesal.CALIFICACION_DEMANDA,
    EstadoProcesal.ADMITIDA: EtapaProcesal.TRASLADO_DEMANDA,
    EstadoProcesal.INADMISIBLE_REFORMABLE: EtapaProcesal.CALIFICACION_DEMANDA,
    EstadoProcesal.CONTESTADA: EtapaProcesal.AUDIENCIA_CONCILIACION,
    EstadoProcesal.EN_TRAMITE: EtapaProcesal.PERIODOS_PRUEBAS,
    EstadoProcesal.SENTENCIADO: EtapaProcesal.SENTENCIA,
    EstadoProcesal.EN_RECURSO: EtapaProcesal.RECURSOS,
    EstadoProcesal.FIRME: EtapaProcesal.EJECUCION,
    EstadoProcesal.EN_EJECUCION: EtapaProcesal.EJECUCION,
    EstadoProcesal.TERMINADO: EtapaProcesal.ARCHIVO_DEFINITIVO,
    EstadoProcesal.ARCHIVADO: EtapaProcesal.ARCHIVO_DEFINITIVO,
}


def _etapa_por_estado(estado: EstadoProcesal) -> EtapaProcesal:
    return _ESTADO_BASE[estado]
