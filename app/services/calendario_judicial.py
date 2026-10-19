"""Calendario judicial de Nicaragua para el cómputo de plazos procesales.

Fundamento legal (Código Procesal Civil, Ley 908 — CPCN):

* **Art. 132 CPCN** — Los términos y plazos se computan en días hábiles;
  no laboran los sábados, domingos ni días feriados o de vacación judicial.
* **Art. 133 CPCN** — Vacaciones judiciales (colectivas) y suspensión de
  labores: los días de vacación no son hábiles para la computación.

Diseño:
    * Objeto **puro e inmutable** (``@dataclass(frozen=True)``).
    * Mismo calendario + misma fecha ⇒ mismo resultado (determinismo).
    * Feriados configurables por año: se cargan como ``frozenset`` y se
      indexan por año para consultas O(1).

Los feriados incluidos son un *set de ejemplo* representativo (festivos
nacionales + Semana Santa 2026 + vacaciones colectivas de fin de año del
Poder Judicial). En producción provienen de un catálogo versionado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


def _feriados_nicaragua_2026() -> frozenset[date]:
    """Feriados nacionales y vacación judicial — año 2026 (datos de ejemplo)."""
    dias = {
        date(2026, 1, 1),  # Año Nuevo
        date(2026, 1, 6),  # Epifanía / Compañía de María
        date(2026, 2, 2),  # Virgen de Candelaria
        date(2026, 3, 2),  # Fundación de la Policía Nacional
        date(2026, 4, 1),  # Jueves Santo (Semana Santa 2026)
        date(2026, 4, 2),  # Viernes Santo
        date(2026, 4, 3),  # Sábado de Gloria (no laborable judicial)
        date(2026, 5, 1),  # Día del Trabajo (Ley 716)
        date(2026, 5, 24),  # Batalla de San Jacinto
        date(2026, 7, 19),  # Día de la Liberación
        date(2026, 8, 10),  # Natalicio de Sandino
        date(2026, 9, 14),  # Cristo de la Victoria (El Viejo)
        date(2026, 9, 15),  # Independencia Centroamericana
        date(2026, 10, 12),  # Día de la Resistencia Indígena
        date(2026, 12, 8),  # Inmaculada Concepción
        date(2026, 12, 25),  # Navidad
        # Vacaciones colectivas del Poder Judicial (fin de año, Art. 133 CPCN).
        date(2026, 12, 28),
        date(2026, 12, 29),
        date(2026, 12, 30),
        date(2026, 12, 31),
    }
    return frozenset(dias)


@dataclass(frozen=True)
class CalendarioJudicial:
    """Calendario de días hábiles del Poder Judicial de Nicaragua.

    Attributes:
        feriados: Días inhábiles adicionales a sábado/domingo (feriados
            nacionales y de vacación judicial).
        nombre: Identificador del catálogo (auditoría: "cual calendario").
    """

    feriados: frozenset[date] = frozenset()
    nombre: str = "custom"
    #: Índice interno derivado (por año) — no forma parte de la API pública.
    _by_year: dict[int, frozenset[date]] = field(
        init=False, repr=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        by_year: dict[int, set[date]] = {}
        for d in self.feriados:
            by_year.setdefault(d.year, set()).add(d)
        object.__setattr__(
            self, "_by_year", {y: frozenset(v) for y, v in by_year.items()}
        )

    # ------------------------------------------------------------------ API
    def es_dia_habil(self, dia: date) -> bool:
        """Indica si ``dia`` es hábil para la computación procesal.

        Son inhábiles: sábado, domingo y todo día presente en el catálogo de
        feriados/vacaciones (Arts. 132 y 133 CPCN).

        Args:
            dia: Fecha natural a evaluar.

        Returns:
            bool: ``True`` si el día es procesalmente hábil.
        """
        if dia.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return dia not in self._by_year.get(dia.year, frozenset())

    def siguiente_dia_habil(self, dia: date) -> date:
        """Primer día hábil igual o posterior a ``dia``.

        Escenarios borde cubiertos: viernes → lunes; lunes feriado → martes;
        racha de feriados → avanza hasta el primer día libre.

        Args:
            dia: Fecha de referencia (inclusiva).

        Returns:
            date: El día hábil más cercano ≥ ``dia``.

        Raises:
            RuntimeError: Si tras 400 días no existe día hábil (calendario
                malformado); defensa contra configuración errónea.
        """
        candidato = dia
        for _ in range(400):  # cota defensiva anti-bucle infinito
            if self.es_dia_habil(candidato):
                return candidato
            candidato += timedelta(days=1)
        raise RuntimeError(
            f"No se halló día hábil desde {dia.isoformat()}: calendario inválido."
        )

    def contar_dias_habiles(self, inicio: date, fin: date) -> int:
        """Días hábiles transcurridos en el intervalo ``(inicio, fin]``.

        Criterio procesal (Art. 132 CPCN): el día de la notificación
        (``inicio``) **no** se cuenta; el día ``fin`` sí cuenta si es hábil.

        Args:
            inicio: Fecha del acto de notificación (exclusiva).
            fin: Fecha límite a evaluar (inclusiva).

        Returns:
            int: Cantidad de días hábiles; 0 si ``fin <= inicio``.
        """
        if fin <= inicio:
            return 0
        total = 0
        cursor = inicio + timedelta(days=1)
        while cursor <= fin:
            if self.es_dia_habil(cursor):
                total += 1
            cursor += timedelta(days=1)
        return total


def cargar_calendario_2026() -> CalendarioJudicial:
    """Fábrica con los feriados de ejemplo de Nicaragua, año 2026."""
    return CalendarioJudicial(
        feriados=_feriados_nicaragua_2026(), nombre="nicaragua-2026"
    )
