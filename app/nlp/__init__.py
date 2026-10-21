"""Módulo NLP (Fase 8): RAG ligero sobre pgvector para análisis de escritos.

Arquitectura (sin infraestructura adicional — todo vive en PostgreSQL):

    texto del borrador
        │
        ▼
    [1] ExtractorDeterminista ── reglas léxicas + patrones normativos CPCN
        │   (pretensión, hechos clave, citas legales detectadas)
        ▼
    [2] Embedder (Protocolo) ── modelo local o API externa; NUNCA recibe PII
        │   sin pasar antes por el anonimizador (Ley 787 protección datos)
        ▼
    [3] VectorStore (pgvector) ── top-k resoluciones anonimizadas similares
        │   ``ORDER BY embedding <=> :query LIMIT k`` (similitud coseno)
        ▼
    [4] Ensamblador XAI ── fusiona [1]+[3] y produce sugerencias SIEMPRE
        citando fuente ("Basado en N fragmentos" + "Artículo Y CPCN").

⚖️ Ningún resultado de este módulo ejecuta comandos ni muta expedientes:
produce *prellenado sugerido* que un humano debe revisar (human-in-the-loop
obligatorio, docs/IA_GOBERNANZA.md).
"""

from app.nlp.anonimizador import anonimizar_texto
from app.nlp.extractor import Extrahecho, extracto_preliminar
from app.nlp.rag import RagPipeline, ResultadoAnalisisEscrito, SimuladoEmbedder

__all__ = [
    "Extrahecho",
    "RagPipeline",
    "ResultadoAnalisisEscrito",
    "SimuladoEmbedder",
    "anonimizar_texto",
    "extracto_preliminar",
]
