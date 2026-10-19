"""Adaptadores HTTP del lado IA (Fase 8 — Calibración e Inteligencia Operativa).

Endpoints:
    * ``GET  /api/casos/{id}/prediccion``   → análisis predictivo del caso.
    * ``GET  /api/publico/estadisticas``    → dashboard anónimo de métricas.
    * ``POST /api/ia/analizar-escrito``     → RAG de prellenado de demanda.

Reglas de seguridad aplicadas (Zero Trust, coherente con auth/JWT previo):
    * Predicción de caso interno: requiere rol JUEZ o DEMANDANTE/DEMANDADO
      legitimado (se reutiliza ``get_current_active_user``); la predicción
      NO es pública porque revela análisis sobre un expediente concreto.
    * Estadísticas y análisis de escrito: roles autenticados; el texto del
      escrito se anonimiza ANTES de cualquier embedding (nunca PII al RAG).

⚖️ Ningún endpoint de este router muta el expediente: son capas de insight
sobre la fuente de verdad legal (YAML + CaseFlowEngine), nunca sustitutos
del criterio jurídico humano.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.analytics.predictive_service import PredictiveService
from app.api.endpoints import obtener_contenedor
from app.auth.permissions import require_role
from app.auth.security import get_current_active_user
from app.db.models import Usuario
from app.nlp.rag import RagPipeline

router = APIRouter(tags=["ia-insight"])

#: Roles de plataforma que pueden consultar la predicción de UN caso
#: concreto (la legitimación por expediente la resuelve el dominio).
_ROLES_PREDICCION = ["juez", "abogado"]


class AnalisisEscritoRequest(BaseModel):
    """Borrador de demanda enviado para prellenado asistido."""

    texto: str = Field(
        min_length=40,
        max_length=20_000,
        description="Borrador del escrito. Se anonimiza antes de embeber.",
        examples=[
            "SEÑOR JUEZ... Que el día 3 de marzo de 2026 celebré contrato de arrendamiento..."
        ],
    )


def _uow(request: Request) -> Any:
    contenedor = obtener_contenedor(request)
    return contenedor.uow_factory()


@router.get(
    "/api/casos/{caso_id}/prediccion",
    summary="Análisis predictivo del caso (XAI)",
)
async def prediccion_caso(
    caso_id: uuid.UUID,
    request: Request,
    usuario: Annotated[Usuario, Depends(require_role(_ROLES_PREDICCION))],
) -> dict[str, Any]:
    """Estimación de éxito y duración basada en históricos anonimizados.

    Combina: tipo de pretensión principal + distrito del juzgado asignado.
    Devuelve siempre el bloque ``fundamento`` (muestra, ventana, fuente y
    citas CPCN) — sin fundamento no hay respuesta (política XAI).
    """
    with _uow(request) as uow:
        caso = uow.cargar_caso(caso_id)
        if not caso.pretensiones:
            raise HTTPException(409, "El expediente aún no registra pretensiones.")
        principal = next(
            (p for p in caso.pretensiones if p.es_principal), caso.pretensiones[0]
        )
        distrito = (caso.juzgado_asignado or "").split("—")[0].strip() or None
        servicio = PredictiveService(uow.session)
        prediccion = servicio.predecir(
            codigo_tipo_pretension=str(
                principal.codigo_tipo.value
                if hasattr(principal.codigo_tipo, "value")
                else principal.codigo_tipo
            ),
            distrito_judicial=distrito,
        )
    # Auditoría pasiva del consumo de IA (trazabilidad del gemelo):
    # se registra como 'anotacion' — no cambia estado alguno.
    payload = prediccion.como_dict()
    payload["solicitado_por"] = str(usuario.id)
    return payload


@router.get("/api/publico/estadisticas", summary="Dashboard público anónimo")
async def estadisticas_publicas(
    request: Request,
    usuario: Annotated[Usuario, Depends(get_current_active_user)],
    anio: int | None = None,
) -> dict[str, Any]:
    """Métricas agregadas sin PII: tiempos y tasas por tipo de pretensión.

    Fuente: ``hechos_judiciales_historicos`` (ETL nightly desidentificado).
    Política de supresión: grupos con n < 5 casos se omiten (anti-re-
    identificación por rareza — k-anonymity mínima, ver gobernanza IA).
    """
    with _uow(request) as uow:
        filas = PredictiveService(uow.session).estadisticas_publicas(anio=anio)
    visibles = [f for f in filas if f["total_casos"] >= 5]
    return {
        "periodo": anio or "histórico completo",
        "total_grupos": len(visibles),
        "metricas": visibles,
        "nota_privacidad": (
            "Agregados anoniminizados; grupos con menos de 5 casos se "
            "suprimen para prevenir reidentificación (k-anonimato)."
        ),
    }


@router.post(
    "/api/ia/analizar-escrito",
    summary="RAG: extraer pretensión/hechos/fundamentos de un borrador",
)
async def analizar_escrito(
    cuerpo: AnalisisEscritoRequest,
    request: Request,
    usuario: Annotated[Usuario, Depends(get_current_active_user)],
) -> dict[str, Any]:
    """Devuelve estructura lista para prellenar PresentarDemandaCommand.

    El resultado es SUGERENCIA revisable: incluye ``advertencia_humano`` y
    ``explicacion_xai`` con la base empírica citada. No ejecuta comandos.
    """
    contenedor = obtener_contenedor(request)
    pipeline: RagPipeline = (
        getattr(contenedor, "rag_pipeline", None) or _pipeline_default()
    )
    resultado = pipeline.analizar_escrito(cuerpo.texto)
    return {
        "pretension_detectada": resultado.pretension_detectada,
        "pretensiones_alternativas": resultado.pretensiones_alternativas,
        "hechos_clave": resultado.hechos_clave,
        "fundamentos_legales_sugeridos": resultado.fundamentos_legales_sugeridos,
        "monto_sugerido": resultado.monto_sugerido,
        "confianza_global": resultado.confianza_global,
        "fragmentos_citados": resultado.fragmentos_citados,
        "explicacion_xai": resultado.explicacion_xai,
        "advertencia_humano": resultado.advertencia_humano,
    }


def _pipeline_default() -> RagPipeline:
    """Fallback determinista si el contenedor no trajo pipeline configurado.

    Uso en tests locales/desarrollo: embedder simulado + corpus vacío. En
    producción el contenedor SIEMPRE inyecta RagPipeline con PgVectorStore.
    """
    from app.nlp.rag import InMemoryVectorStore, SimuladoEmbedder

    return RagPipeline(SimuladoEmbedder(), InMemoryVectorStore([]))
