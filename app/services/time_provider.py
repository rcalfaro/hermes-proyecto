"""Proveedores de tiempo inyectables para el Gemelo Digital.

Principio rector: **ningún servicio de dominio llama a ``datetime.now()``
directamente**. El reloj se inyecta como dependencia (``TimeProvider``), lo
que garantiza:

* *Determinismo*: los tests controlan el tiempo de forma explícita.
* *Testeabilidad*: ``FakeClock`` permite avanzar el reloj sin dormir.
* *Trazabilidad*: cada cálculo de plazo queda anclado a la marca temporal
  observada por el sistema en ese instante exacto.

Convención horaria: las marcas internas son *timezone-aware* en UTC; la capa
de presentación las proyecta a la hora local de Managua (UTC-6, sin horario
de verano) conforme a la práctica forense nicaragüense.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class TimeProvider(Protocol):
    """Contrato mínimo de cualquier fuente de tiempo del sistema."""

    def now(self) -> datetime:
        """Retorna la marca temporal actual, consciente del time-zone.

        Returns:
            datetime: ``tzinfo`` no nulo (UTC por convención interna).
        """
        ...


class SystemClock:
    """Reloj de producción: delega en el reloj del sistema operativo.

    Uso::

        clock: TimeProvider = SystemClock()
        plazo_service = PlazoService(calendario, clock)
    """

    __slots__ = ()

    def now(self) -> datetime:
        """Marca temporal UTC del sistema operativo."""
        return datetime.now(UTC)


class FakeClock:
    """Reloj virtual para pruebas y simulaciones del gemelo digital.

    Permite congelar el tiempo en una fecha inicial y avanzarlo de forma
    determinista. No es thread-safe por diseño: su uso está acotado a tests
    unitarios single-thread.

    Ejemplo::

        clock = FakeClock(datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
        clock.advance_to(datetime(2026, 3, 13, 9, 0, tzinfo=UTC))
        assert clock.now().day == 13
    """

    __slots__ = ("_history", "_now")

    def __init__(self, initial: datetime) -> None:
        if initial.tzinfo is None:
            raise ValueError("FakeClock exige marcas temporales timezone-aware (UTC).")
        self._now: datetime = initial
        # Bitácora de saltos del reloj: útil para depurar tests deterministas.
        self._history: list[datetime] = [initial]

    @property
    def history(self) -> tuple[datetime, ...]:
        """Marcas por las que ha pasado el reloj (auditoría del propio test)."""
        return tuple(self._history)

    def now(self) -> datetime:
        """Marca temporal virtual actual (cumple el protocolo ``TimeProvider``)."""
        return self._now

    def advance_to(self, instant: datetime) -> None:
        """Salta el reloj a ``instant``.

        Args:
            instant: Nueva marca; debe ser posterior o igual a la actual.

        Raises:
            ValueError: Si ``instant`` es anterior al tiempo actual o carece
                de ``tzinfo`` — la línea de tiempo procesal es monotónica.
        """
        if instant.tzinfo is None:
            raise ValueError("advance_to exige marcas timezone-aware (UTC).")
        if instant < self._now:
            raise ValueError(
                f"El reloj no puede retroceder: {instant} < {self._now} "
                "(la línea de tiempo procesal es monotónica)."
            )
        self._now = instant
        self._history.append(instant)

    def advance_by(self, delta: timedelta) -> None:
        """Avanza el reloj una duración relativa (p. ej. ``timedelta(days=9)``)."""
        self.advance_to(self._now + delta)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FakeClock now={self._now.isoformat()}>"
