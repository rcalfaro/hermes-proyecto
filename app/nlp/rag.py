"""Pipeline RAG (Retrieval-Augmented Generation) ligero sobre pgvector.

Flujo de ``POST /api/ia/analizar-escrito``:

    1. anonimizar_texto()      — PII nunca toca el embedder ni sale del
                                 perímetro (política IA_GOBERNANZA.md).
    2. extracto_preliminar()   — capa determinista (grounding verificable).
    3. Embedder.embed()        — Protocol inyectable: implementación local
                                 simulada (hash estable → vector unitario)
                                 o adaptador a API externa en producción.
    4. VectorStore.buscar_similares() — pgvector:
            SELECT ... ORDER BY embedding <=> :v LIMIT :k
       sobre ``documento_anonimizado`` (corpus ya anonimizado por el ETL).
    5. Ensamblado XAI          — cada sugerencia cita su base empírica:
         "Basado en K fragmentos de sentencias similares" + artículos CPCN.

Sin sesión/DB (tests): se puede construir RagPipeline con un VectorStore en
memoria; en producción se inyecta PgVectorStore(session).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.analytics.modelos import DIMENSION_EMBEDDING
from app.nlp.anonimizador import anonimizar_texto
from app.nlp.extractor import Extrahecho, extracto_preliminar


class Embedder(Protocol):
    """Contrato de generación de embeddings (inyectable, testeable)."""

    def embed(self, texto: str) -> list[float]: ...


class SimuladoEmbedder:
    """Embedder determinista de desarrollo/tests: hashing bag-of-tokens.

    No es un modelo semántico real — produce vectores estables y dispersos
    que preservan solapamiento léxico suficiente para probar el pipeline
    end-to-end sin dependencias externas. En producción se sustituye por
    un adaptador (p. ej. sentence-transformers o API), manteniendo el
    mismo Protocol.
    """

    def __init__(self, dimension: int = DIMENSION_EMBEDDING) -> None:
        self.dimension = dimension

    def embed(self, texto: str) -> list[float]:
        vec = [0.0] * self.dimension
        for token in self._tokens(texto):
            idx = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimension
            vec[idx] += 1.0
        norma = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norma for v in vec]

    @staticmethod
    def _tokens(texto: str) -> list[str]:
        limpiado = "".join(
            c if c.isalnum() or c.isspace() else " " for c in texto.lower()
        )
        return [t for t in limpiado.split() if len(t) >= 4]


@dataclass(frozen=True, slots=True)
class FragmentoRecuperado:
    """Trozo de resolución anonimizada recuperado por similitud."""

    hash_fuente: str
    tipo_documento: str
    trozo: str
    similitud: float
    fundamentos_legales: tuple[str, ...]


class VectorStore(Protocol):
    """Almacén vectorial (pgvector en producción; memoria en tests)."""

    def buscar_similares(
        self,
        vector: Sequence[float],
        *,
        k: int,
        filtro_tipo_pretension: str | None = None,
    ) -> list[FragmentoRecuperado]: ...


class PgVectorStore:
    """Búsqueda por similitud coseno (operador ``<=>``) en PostgreSQL+pgvector.

    Requiere la extensión creada en migración:
    ``CREATE EXTENSION IF NOT EXISTS vector;`` e índice HNSW
    (``USING hnsw (embedding vector_cosine_ops)``).
    """

    SQL = """
        SELECT hash_fuente, tipo_documento,
               LEFT(texto, 400) AS trozo,
               1 - (embedding <=> CAST(:vec AS vector)) AS similitud,
               fundamentos_legales
          FROM documento_anonimizado
         WHERE (:filtro IS NULL OR codigo_tipo_pretension = :filtro)
         ORDER BY embedding <=> CAST(:vec AS vector)
         LIMIT :k
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def buscar_similares(
        self,
        vector: Sequence[float],
        *,
        k: int,
        filtro_tipo_pretension: str | None = None,
    ) -> list[FragmentoRecuperado]:
        filas = self._session.execute(
            sa_text(self.SQL),
            {
                "vec": "[" + ",".join(f"{x:.6f}" for x in vector) + "]",
                "k": k,
                "filtro": filtro_tipo_pretension,
            },
        ).all()
        return [
            FragmentoRecuperado(
                hash_fuente=f.hash_fuente,
                tipo_documento=f.tipo_documento,
                trozo=f.trozo,
                similitud=float(f.similitud),
                fundamentos_legales=tuple(f.fundamentos_legales or []),
            )
            for f in filas
        ]


class InMemoryVectorStore:
    """Corpus en memoria (mismo contrato) para pruebas deterministas rápidas."""

    def __init__(self, documentos: list[tuple[str, str, str, list[float], list[str]]]):
        #: (hash_fuente, tipo_doc, trozo, embedding, fundamentos)
        self._docs = documentos

    def buscar_similares(
        self,
        vector: Sequence[float],
        *,
        k: int,
        filtro_tipo_pretension: str | None = None,
    ) -> list[FragmentoRecuperado]:
        puntuadas = sorted(
            (
                (self._coseno(vector, emb), h, td, tr, fu)
                for h, td, tr, emb, fu in self._docs
            ),
            key=lambda t: -t[0],
        )[:k]
        return [
            FragmentoRecuperado(h, td, tr, round(sim, 4), tuple(fu))
            for sim, h, td, tr, fu in puntuadas
        ]

    @staticmethod
    def _coseno(a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)


@dataclass(slots=True)
class ResultadoAnalisisEscrito:
    """Salida estructurada del endpoint — espejo del prellenado del comando.

    Cada campo sugiere; ninguno ordena. La advertencia de revisión humana
    viaja DENTRO del payload (no solo en docs) para que ningún cliente la
    pierda al renderizar.
    """

    pretension_detectada: str | None
    pretensiones_alternativas: list[dict[str, Any]]
    hechos_clave: list[str]
    fundamentos_legales_sugeridos: list[str]
    monto_sugerido: float | None
    confianza_global: float
    fragmentos_citados: list[dict[str, Any]]
    explicacion_xai: str = field(
        default="Sugerencia generada por RAG sobre corpus anonimizado."
    )
    advertencia_humano: str = (
        "⚖️ Prellenado asistido por IA. Un abogado o juez DEBE revisar y "
        "confirmar antes de presentar el PresentarDemandaCommand "
        "(human-in-the-loop obligatorio — docs/IA_GOBERNANZA.md)."
    )


class RagPipeline:
    """Orquestador puro del análisis (DI: embedder + store + calendario-léxico)."""

    def __init__(
        self, embedder: Embedder, store: VectorStore, *, top_k: int = 4
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._top_k = top_k

    def analizar_escrito(self, texto_borrador: str) -> ResultadoAnalisisEscrito:
        """Extrae señales + recupera jurisprudencia similar, con XAI completo."""
        # 1) Determinista (no sale del perímetro; puede ver PII porque es
        #    código propio auditado) — grounding principal.
        extra: Extrahecho = extracto_preliminar(texto_borrador)
        # 2) Anonimización OBLIGATORIA antes de cualquier embedding/envío.
        seguro = anonimizar_texto(texto_borrador)
        vector = self._embedder.embed(seguro)
        filtro = (
            extra.pretension_principal.codigo_tipo
            if extra.pretension_principal
            else None
        )
        fragmentos = self._store.buscar_similares(
            vector,
            k=self._top_k,
            filtro_tipo_pretension=None,  # no sobre-filtrar: recall
        )
        # 3) Fusión de fundamentos: citas propias ∪ citas de lo recuperado.
        citas_rag = {c for f in fragmentos for c in f.fundamentos_legales}
        fundamentos = sorted(set(extra.fundamentos_legales) | citas_rag)

        n_frag = len(fragmentos)
        explicacion = (
            f"Basado en {n_frag} fragmento(s) de resoluciones similares "
            f"(similitud media "
            f"{sum(f.similitud for f in fragmentos) / max(n_frag, 1):.2f}) "
            f"del corpus anonimizado y en el léxico procesal del escrito. "
            f"Fundamento normativo primario: Art. 37 y 146-148 CPCN "
            f"(determinación de la pretensión y contenido de la demanda)."
        )

        return ResultadoAnalisisEscrito(
            pretension_detectada=filtro,
            pretensiones_alternativas=[
                {
                    "codigo_tipo": p.codigo_tipo,
                    "puntaje": p.puntaje,
                    "terminos": list(p.terminos_detectados),
                }
                for p in extra.pretensiones[1:]
            ],
            hechos_clave=extra.hechos_clave,
            fundamentos_legales_sugeridos=fundamentos,
            monto_sugerido=extra.monto_sugerido,
            confianza_global=extra.confianza_global,
            fragmentos_citados=[
                {
                    "hash_fuente": f.hash_fuente,
                    "tipo": f.tipo_documento,
                    "similitud": f.similitud,
                    "trozo": f.trozo[:200],
                }
                for f in fragmentos
            ],
            explicacion_xai=explicacion,
        )
