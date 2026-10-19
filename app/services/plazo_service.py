"""Motor de cómputo de plazos procesales — Código Procesal Civil (Ley 908).

Responsabilidad única: **calcular** vencimientos y evaluar vencidos. La
ejecución de actos procesales (contestar, ofrecer pruebas, apelar) pertenece
a otros servicios; aquí solo se produce el dato temporal determinista y su
trazabilidad ante ``LogAuditoria``.

Fundamento legal (CPCN):
    * Art. 132 CPCN — Cómputo en días hábiles (sábados, domingos y feriados
      excluidos). El término empieza a correr desde el día hábil siguiente
      a la notificación; el día del vencimiento es hábil hasta las 24:00.
    * Art. 134 CPCN — Plazos **preclusivos**: vencidos, la parte pierde la
      facultad de realizar el acto (preclusión/caducidad de la facultad).
    * Art. 135 CPCN — Plazos **no preclusivos** (obligatorios para el juez y
      auxiliares): pueden cumplirse después, sin perjuicio de la sanción que
      proceda; no extinguen la facultad del órgano jurisdiccional.
    * Art. 136 CPCN — **Suspensión**: el plazo se congela durante el
      incidente/impedimento y se reanuda contando solo lo pendiente.
    * Art. 137 CPCN — **Interrupción**: el transcurso queda sin efecto y el
      plazo vuelve a computarse íntegro desde el cese de la causa.

Garantías de calidad:
    * Determinismo puro: ``(fecha_inicio, dias, tipo_plazo, calendario)`` ⇒
      mismo ``vencimiento``, siempre. Sin acceso a reloj global.
    * Toda operación retorna un ``ComputoPlazo`` con la evidencia exigida
      para auditoría jurídica: inicio, vencimiento, días hábiles contados,
      feriados saltados y fundamento legal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any, Protocol

from app.services.calendario_judicial import CalendarioJudicial
from app.services.time_provider import TimeProvider

#: Hora de cierre de día hábil judicial (notificaciones electrónicas hasta
#: las 24:00 del día del vencimiento — práctica del Art. 132 CPCN).
HORA_VENCIMIENTO = time(23, 59, 59)


class TipoPlazo(StrEnum):
    """Naturaleza jurídica del plazo conforme al CPCN."""

    PRECLUSIVO = "preclusivo"  # Art. 134: se pierde la facultad.
    NO_PRECLUSIVO = "no_preclusivo"  # Art. 135: cabe cumplimiento tardío.


class EstadoPlazo(StrEnum):
    """Estado vital del plazo dentro del proceso."""

    CORRIENTE = "corriente"
    SUSPENDIDO = "suspendido"  # Art. 136 CPCN
    INTERRUMPIDO = "interrumpido"  # Art. 137 CPCN
    VENCIDO = "vencido"
    CUMPLIDO = "cumplido"


class EventoVencimiento(StrEnum):
    """Eventos emitidos por el motor al detectar plazos vencidos."""

    REBELDIA = "rebeldia"  # No contestó demanda (Art. 151/153).
    PRECLUSION = "preclusion"  # Art. 134: pérdida de la facultad.
    CADUCIDAD_PERIODO_PRUEBA = "caducidad_periodo_prueba"
    SANCION_NO_PRECLUSIVO = "sancion_no_preclusivo"  # Art. 135.


_FUNDAMENTOS: dict[TipoPlazo, str] = {
    TipoPlazo.PRECLUSIVO: (
        "Arts. 132 y 134 CPCN: cómputo en días hábiles; vencido el plazo, "
        "la parte pierde la facultad de realizar el acto (preclusión)."
    ),
    TipoPlazo.NO_PRECLUSIVO: (
        "Arts. 132 y 135 CPCN: plazo obligatorio no preclusivo; puede "
        "cumplirse posteriormente sin perjuicio de la sanción aplicable."
    ),
}


@dataclass(frozen=True, slots=True)
class ComputoPlazo:
    """Evidencia inmutable de un cálculo de plazo (obligación de auditoría).

    Attributes:
        fecha_inicio: Día de la notificación/emplazamiento (no se cuenta).
        primer_dia_habil: Día en que comenzó a correr el término.
        fecha_vencimiento: Fecha límite calculada (día hábil).
        vencimiento_datetime: Instante exacto de cierre (23:59:59 UTC).
        dias_habiles_solicitados: Días del plazo concedido por el juzgado.
        dias_habiles_contados: Habitables efectivamente consumidos (= solicitados).
        feriados_saltados: Fechas inhábiles salvadas durante el cómputo.
        tipo_plazo: Preclusividad (Arts. 134/135 CPCN).
        fundamento_legal: Cita normativa del resultado.
    """

    fecha_inicio: date
    primer_dia_habil: date
    fecha_vencimiento: date
    vencimiento_datetime: datetime
    dias_habiles_solicitados: int
    dias_habiles_contados: int
    feriados_saltados: tuple[date, ...]
    tipo_plazo: TipoPlazo
    fundamento_legal: str

    def como_detalle_auditoria(self) -> dict[str, Any]:
        """Serializa el cómputo para el payload JSONB de ``LogAuditoria``."""
        return {
            "fecha_inicio": self.fecha_inicio.isoformat(),
            "primer_dia_habil": self.primer_dia_habil.isoformat(),
            "fecha_vencimiento": self.fecha_vencimiento.isoformat(),
            "vencimiento_datetime": self.vencimiento_datetime.isoformat(),
            "dias_habiles_solicitados": self.dias_habiles_solicitados,
            "dias_habiles_contados": self.dias_habiles_contados,
            "feriados_saltados": [d.isoformat() for d in self.feriados_saltados],
            "tipo_plazo": self.tipo_plazo.value,
            "fundamento_legal": self.fundamento_legal,
        }


@dataclass(slots=True)
class PlazoProcesal:
    """Plazo activo dentro de un caso (entidad de memoria/simulación).

    Persistido en producción vía ``caso.dias_plazo_vigente`` + catálogo propio;
    aquí opera como registro de trabajo del motor.
    """

    id: uuid.UUID
    caso_id: uuid.UUID
    nombre: str  # p.ej. "contestacion_demanda"
    computo: ComputoPlazo
    estado: EstadoPlazo = EstadoPlazo.CORRIENTE
    #: Días hábiles ya consumidos antes de una suspensión (Art. 136 CPCN).
    dias_consumidos_previos: int = 0
    #: Instantes de suspensión/interrupción para trazabilidad.
    incidentes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def vencimiento(self) -> datetime:
        return self.computo.vencimiento_datetime


class AuditoriaWriter(Protocol):
    """Contrato mínimo para registrar eventos (implementa LogAuditoria)."""

    def registrar(
        self,
        *,
        caso_id: uuid.UUID | None,
        accion: str,
        entidad_afectada: str,
        registro_id: str | None,
        detalle: dict[str, Any],
        timestamp: datetime,
    ) -> None: ...


class PlazoService:
    """Servicio puro de cómputo y vigilancia de plazos procesales.

    Args:
        calendario: Calendario judicial inyectable (determinismo por año).
        clock: Fuente de tiempo inyectada — nunca ``datetime.now()`` interno.
        auditoria: Receptor opcional de eventos (``LogAuditoria`` en BD).
    """

    def __init__(
        self,
        calendario: CalendarioJudicial,
        clock: TimeProvider,
        auditoria: AuditoriaWriter | None = None,
    ) -> None:
        self._calendario = calendario
        self._clock = clock
        self._auditoria = auditoria

    # ------------------------------------------------------------ cómputo
    def calcular_vencimiento(
        self,
        fecha_inicio: date,
        dias_habiles: int,
        tipo_plazo: TipoPlazo = TipoPlazo.PRECLUSIVO,
    ) -> ComputoPlazo:
        """Calcula la fecha de vencimiento de un plazo en días hábiles.

        Algoritmo (Art. 132 CPCN):
            1. El día de la notificación no se cuenta; el término arranca en
               el primer día hábil *siguiente* a ``fecha_inicio``.
            2. Se avanzan ``dias_habiles`` días hábiles, registrando cada
               fecha inhábil saltada (feriado o fin de semana) como evidencia.
            3. El vencimiento fija a las 23:59:59 del último día hábil.

        Args:
            fecha_inicio: Fecha del acto de notificación/emplazamiento
                (exclusiva: nunca forma parte del cómputo).
            dias_habiles: Duración del plazo concedido (≥ 1).
            tipo_plazo: Preclusivo (Art. 134) o no preclusivo (Art. 135).

        Returns:
            ComputoPlazo: Resultado determinista con evidencia de auditoría.

        Raises:
            ValueError: Si ``dias_habiles`` < 1.
        """
        if dias_habiles < 1:
            raise ValueError("El plazo debe ser de al menos 1 día hábil.")

        primer_dia = self._calendario.siguiente_dia_habil(
            fecha_inicio + timedelta(days=1)
        )
        feriados_saltados: list[date] = []
        cursor = primer_dia
        contados = 0
        while True:
            if self._calendario.es_dia_habil(cursor):
                contados += 1
                if contados == dias_habiles:
                    break
            else:
                feriados_saltados.append(cursor)
            cursor += timedelta(days=1)

        vencimiento_dt = datetime.combine(cursor, HORA_VENCIMIENTO, tzinfo=UTC)
        computo = ComputoPlazo(
            fecha_inicio=fecha_inicio,
            primer_dia_habil=primer_dia,
            fecha_vencimiento=cursor,
            vencimiento_datetime=vencimiento_dt,
            dias_habiles_solicitados=dias_habiles,
            dias_habiles_contados=contados,
            feriados_saltados=tuple(feriados_saltados),
            tipo_plazo=tipo_plazo,
            fundamento_legal=_FUNDAMENTOS[tipo_plazo],
        )
        self._log(
            accion="calculo_plazo",
            caso_id=None,
            registro_id=None,
            entidad_afectada="plazo_procesal",
            detalle=computo.como_detalle_auditoria(),
        )
        return computo

    # -------------------------------------------------- suspensión / interrupción
    def suspender_plazo(
        self, plazo: PlazoProcesal, causa: str, hasta: date
    ) -> PlazoProcesal:
        """Congela el curso del plazo por incidente (Art. 136 CPCN).

        Lo ya transcurrido se conserva; al reanudarse solo se computa el
        remanente. Recalcula el vencimiento desplazando los días hábiles del
        paréntesis de suspensión.

        Args:
            plazo: Plazo activo en estado CORRIENTE.
            causa: Descripción del incidente (p. ej. "incidente_de_nulidad").
            hasta: Fecha en que se levanta la suspensión y reanuda el cómputo.
        """
        if plazo.estado is not EstadoPlazo.CORRIENTE:
            raise ValueError(f"Plazo en estado {plazo.estado} no suspendible.")
        ahora = self._clock.now().date()
        pendientes = self._calendario.contar_dias_habiles(
            ahora, plazo.computo.fecha_vencimiento
        )
        nuevo_fin = self._avanzar_dias(hasta, pendientes)
        plazo.estado = EstadoPlazo.SUSPENDIDO
        plazo.incidentes.append(
            {
                "tipo": "suspension",
                "causa": causa,
                "desde": ahora.isoformat(),
                "reanudacion": hasta.isoformat(),
                "dias_pendientes_al_congelar": pendientes,
                "fundamento": "Art. 136 CPCN: suspendido el plazo, se reanuda "
                "por el tiempo que falte para su vencimiento.",
            }
        )
        plazo.computo = self._con_nuevo_vencimiento(plazo.computo, nuevo_fin)
        self._log(
            accion="suspension_plazo",
            caso_id=plazo.caso_id,
            registro_id=str(plazo.id),
            entidad_afectada="plazo_procesal",
            detalle={
                "causa": causa,
                "hasta": hasta.isoformat(),
                "nuevo_vencimiento": nuevo_fin.isoformat(),
            },
        )
        return plazo

    def interrumpir_plazo(
        self, plazo: PlazoProcesal, causa: str, desde: date
    ) -> PlazoProcesal:
        """Deja sin efecto lo transcurrido y reinicia el cómputo (Art. 137 CPCN).

        Args:
            plazo: Plazo activo.
            causa: Motivo de interrupción (p. ej. "falta_de_notificacion_valida").
            desde: Fecha del acto que interrumpe; el nuevo término corre a
                partir del primer día hábil posterior.
        """
        dias = plazo.computo.dias_habiles_solicitados
        tipo = plazo.computo.tipo_plazo
        plazo.estado = EstadoPlazo.INTERRUMPIDO
        plazo.incidentes.append(
            {
                "tipo": "interrupcion",
                "causa": causa,
                "desde": desde.isoformat(),
                "fundamento": "Art. 137 CPCN: interrumpido el plazo, se computa "
                "íntegramente desde el día hábil siguiente al cese.",
            }
        )
        plazo.computo = self.calcular_vencimiento(desde, dias, tipo)
        self._log(
            accion="interrupcion_plazo",
            caso_id=plazo.caso_id,
            registro_id=str(plazo.id),
            entidad_afectada="plazo_procesal",
            detalle={
                "causa": causa,
                "reinicio_desde": desde.isoformat(),
                "nuevo_vencimiento": plazo.computo.fecha_vencimiento.isoformat(),
            },
        )
        return plazo

    # ------------------------------------------------------------- vigilancia
    def procesar_vencimientos(
        self, plazos: list[PlazoProcesal]
    ) -> list[EventoVencimiento]:
        """Evalúa los plazos contra el reloj inyectado y emite eventos.

        Reglas de negocio:
            * ``contestacion_demanda`` vencido sin escrito → **REBELDIA**
              ( Arts. 151 y 153 CPCN).
            * ``periodo_de_prueba`` vencido → **CADUCIDAD_PERIODO_PRUEBA**,
              preclusión de la facultad probatoria (Art. 134 CPCN).
            * Cualquier otro preclusivo vencido → **PRECLUSION** (Art. 134).
            * No preclusivo vencido → **SANCION_NO_PRECLUSIVO** (Art. 135);
              el plazo sigue siendo cumplible tardíamente.

        Args:
            plazos: Plazos activos del caso (los SUSPENDIDOS se ignoran).

        Returns:
            list[EventoVencimiento]: Eventos emitidos (uno por plazo vencido),
            cada uno registrado además en ``LogAuditoria`` si hay receptor.
        """
        ahora = self._clock.now()
        eventos: list[EventoVencimiento] = []
        for plazo in plazos:
            if plazo.estado in (
                EstadoPlazo.SUSPENDIDO,
                EstadoPlazo.VENCIDO,
                EstadoPlazo.CUMPLIDO,
            ):
                continue
            if ahora <= plazo.vencimiento:
                continue
            evento = self._clasificar(plazo)
            plazo.estado = EstadoPlazo.VENCIDO
            eventos.append(evento)
            self._log(
                accion=evento.value,
                caso_id=plazo.caso_id,
                registro_id=str(plazo.id),
                entidad_afectada="plazo_procesal",
                detalle={
                    "nombre_plazo": plazo.nombre,
                    "evento": evento.value,
                    "vencimiento": plazo.vencimiento.isoformat(),
                    "evaluado_en": ahora.isoformat(),
                    "computo": plazo.computo.como_detalle_auditoria(),
                },
            )
        return eventos

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _clasificar(plazo: PlazoProcesal) -> EventoVencimiento:
        if plazo.nombre == "contestacion_demanda":
            return EventoVencimiento.REBELDIA
        if plazo.nombre == "periodo_de_prueba":
            return EventoVencimiento.CADUCIDAD_PERIODO_PRUEBA
        if plazo.computo.tipo_plazo is TipoPlazo.NO_PRECLUSIVO:
            return EventoVencimiento.SANCION_NO_PRECLUSIVO
        return EventoVencimiento.PRECLUSION

    def _avanzar_dias(self, desde: date, habiles: int) -> date:
        """Devuelve el día hábil que queda ``habiles`` jornadas después."""
        if habiles <= 0:
            return self._calendario.siguiente_dia_habil(desde)
        cursor = self._calendario.siguiente_dia_habil(desde)
        restantes = habiles - 1
        while restantes > 0:
            cursor = self._calendario.siguiente_dia_habil(cursor + timedelta(days=1))
            restantes -= 1
        return cursor

    @staticmethod
    def _con_nuevo_vencimiento(base: ComputoPlazo, nueva_fecha: date) -> ComputoPlazo:
        """Reemplaza el vencimiento conservando la evidencia original."""
        return ComputoPlazo(
            fecha_inicio=base.fecha_inicio,
            primer_dia_habil=base.primer_dia_habil,
            fecha_vencimiento=nueva_fecha,
            vencimiento_datetime=datetime.combine(
                nueva_fecha, HORA_VENCIMIENTO, tzinfo=UTC
            ),
            dias_habiles_solicitados=base.dias_habiles_solicitados,
            dias_habiles_contados=base.dias_habiles_contados,
            feriados_saltados=base.feriados_saltados,
            tipo_plazo=base.tipo_plazo,
            fundamento_legal=base.fundamento_legal,
        )

    def _log(
        self,
        *,
        accion: str,
        caso_id: uuid.UUID | None,
        registro_id: str | None,
        entidad_afectada: str,
        detalle: dict[str, Any],
    ) -> None:
        """Descarga el evento en el receptor de auditoría, si está configurado."""
        if self._auditoria is not None:
            self._auditoria.registrar(
                caso_id=caso_id,
                accion=accion,
                entidad_afectada=entidad_afectada,
                registro_id=registro_id,
                detalle=detalle,
                timestamp=self._clock.now(),
            )


def nuevo_plazo(
    caso_id: uuid.UUID,
    nombre: str,
    computo: ComputoPlazo,
) -> PlazoProcesal:
    """Fábrica de registros de plazo con identidad UUID v4."""
    return PlazoProcesal(
        id=uuid.uuid4(), caso_id=caso_id, nombre=nombre, computo=computo
    )
