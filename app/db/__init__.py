"""Paquete de persistencia del Gemelo Digital del Proceso Civil."""

from app.db.base import (
    AccionAuditoria,
    Base,
    EstadoProcesal,
    EtapaProcesal,
    RolActor,
    SentidoFallo,
    TipoPretension,
    TipoResolucion,
)
from app.db.models import (
    ActorJuridico,
    Caso,
    CasoActor,
    LogAuditoria,
    Pretension,
    ReglaTransicion,
    ResolucionJudicial,
    TransicionEstado,
)

__all__ = [
    "AccionAuditoria",
    "ActorJuridico",
    "Base",
    "Caso",
    "CasoActor",
    "EstadoProcesal",
    "EtapaProcesal",
    "LogAuditoria",
    "Pretension",
    "ReglaTransicion",
    "ResolucionJudicial",
    "RolActor",
    "SentidoFallo",
    "TipoPretension",
    "TipoResolucion",
    "TransicionEstado",
]
