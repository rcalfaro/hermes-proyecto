"""Excepciones de la capa de aplicación y su mapeo a códigos HTTP.

Convención del Gemelo Digital:
    * 400 — validación de entrada (falla Pydantic en el comando).
    * 403 — el rol no está legitimado para el acto (RBAC del motor de flujo).
    * 404 — expediente inexistente.
    * 409 — conflicto de estado: transición prohibida o facultad precluida.
"""

from __future__ import annotations


class ErrorAplicacion(Exception):
    """Error base de la capa de aplicación con código HTTP asociado."""

    status_code: int = 400

    def __init__(self, detalle: str) -> None:
        super().__init__(detalle)
        self.detalle = detalle


class ErrorValidacion(ErrorAplicacion):
    """Datos del comando inválidos → HTTP 400."""

    status_code = 400


class ErrorPermisoProcesal(ErrorAplicacion):
    """Rol no legitimado para el acto procesal → HTTP 403."""

    status_code = 403


class CasoNoEncontrado(ErrorAplicacion):
    """Expediente inexistente → HTTP 404."""

    status_code = 404


class ConflictoDeEstado(ErrorAplicacion):
    """Transición contraria al grafo del CPCN → HTTP 409."""

    status_code = 409


class SinLegitimacionProcesal(ErrorAplicacion):
    """Usuario/actor sin vinculación vigente en el expediente → HTTP 403.

    Zero Trust: la identidad procesal se deriva del JWT + BD; si el actor
    real no está inscrito (o su rol no es el autorizado por el YAML), el
    acto se rechaza con la fórmula legal nicaragüense.
    """

    status_code = 403


class PlazoPrecluido(ErrorAplicacion):
    """Facultad extinguida por vencimiento del plazo (Art. 134 CPCN) → 409."""

    status_code = 409


class ErrorGuardAdmision(ErrorAplicacion):
    """Demanda que incumple los requisitos formales del Art. 146 CPCN → 400.

    Guard de admisión de la capa de aplicación: la demanda NO se persiste.
    Imita la inadmisión reformable del Art. 147 CPCN, devolviendo TODOS los
    defectos detectados (con su cita normativa) para que el promovente los
    subsane de una sola vez dentro de tercero día.
    """

    status_code = 400

    def __init__(self, defectos: list[str]) -> None:
        detalle = " | ".join(defectos) if defectos else "Requisitos legales faltantes."
        super().__init__(detalle)
        self.defectos = defectos
