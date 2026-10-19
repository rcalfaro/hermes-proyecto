"""Módulo de Analítica Predictiva (Fase 8 — Calibración e IA Operativa).

⚖️  PRINCIPIO RECTOR: la IA es una herramienta de APOYO a la decisión
jurídica, NUNCA un sustituto del criterio del juzgador. Este módulo es de
SOLO LECTURA sobre el sistema transaccional: no modifica reglas YAML, no
emite comandos y no cambia estados de expediente. Toda salida lleva
fundamento explicable (XAI) y fuente de datos trazable.

Submódulos:
    * ``modelos``           -- esquema de tablas analíticas (solo lectura).
    * ``predictive_service``-- estimaciones con margen de confianza.
"""

from app.analytics.modelos import HechoJudicialHistorico, MetricaDistritoAnual
from app.analytics.predictive_service import (
    FundamentoPredictivo,
    PrediccionCaso,
    PredictiveService,
)

__all__ = [
    "FundamentoPredictivo",
    "HechoJudicialHistorico",
    "MetricaDistritoAnual",
    "PrediccionCaso",
    "PredictiveService",
]
