"""Adaptadores HTTP del lado de escritura (CQRS: command side).

Los endpoints son **solo traducción HTTP → comando**: parsean el request,
instancian el comando Pydantic y lo entregan al handler. Ninguna regla de
negocio vive aquí. Mapeo de errores: 400 validación / 403 legitimación /
404 expediente / 409 conflicto de estado o preclusión (Art. 134 CPCN).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.application.commands import (
    AdmitirDemandaCommand,
    ApelarSentenciaCommand,
    ContestarDemandaCommand,
    DictarSentenciaCommand,
    EjecutarSentenciaCommand,
    PresentarDemandaCommand,
)
from app.application.container import ContenedorDependencias


def obtener_contenedor(request: Request) -> ContenedorDependencias:
    """Resuelve el contenedor de DI desde el estado de la app."""
    return request.app.state.contenedor  # type: ignore[no-any-return]


Contenedor = Annotated[ContenedorDependencias, Depends(obtener_contenedor)]

router = APIRouter(prefix="/api/comandos", tags=["comandos-procesales"])


def _acreditacion(resultado: Any) -> dict[str, Any]:
    """Serializa uniformemente el ResultadoComando del handler."""
    return asdict(resultado)


@router.post(
    "/presentar-demanda",
    status_code=201,
    summary="Presentar demanda (Arts. 37, 146-147 CPCN)",
)
async def presentar_demanda(
    comando: PresentarDemandaCommand, contenedor: Contenedor
) -> dict[str, Any]:
    """Promueve el juicio ordinario civil o subsana una demanda reformable."""
    return _acreditacion(contenedor.handler_presentar.manejar(comando))


@router.post(
    "/admitir-demanda", status_code=201, summary="Auto iniciado (Art. 148 CPCN)"
)
async def admitir_demanda(
    comando: AdmitirDemandaCommand, contenedor: Contenedor
) -> dict[str, Any]:
    """El juez titular admite la demanda y abre el traslado de diez días."""
    return _acreditacion(contenedor.handler_admitir.manejar(comando))


@router.post(
    "/contestar-demanda",
    summary="Contestar dentro del traslado (Art. 151 CPCN)",
)
async def contestar_demanda(
    comando: ContestarDemandaCommand, contenedor: Contenedor
) -> dict[str, Any]:
    """Escrito de contestación; rechazado (409) si el plazo precluyó."""
    return _acreditacion(contenedor.handler_contestar.manejar(comando))


@router.post("/dictar-sentencia", summary="Sentencia definitiva (Arts. 192-201 CPCN)")
async def dictar_sentencia(
    comando: DictarSentenciaCommand, contenedor: Contenedor
) -> dict[str, Any]:
    """Solo el juez titular; exige congruencia con todas las pretensiones."""
    return _acreditacion(contenedor.handler_sentenciar.manejar(comando))


@router.post(
    "/apelar-sentencia", summary="Apelación en quinto día (Arts. 246-248 CPCN)"
)
async def apelar_sentencia(
    comando: ApelarSentenciaCommand, contenedor: Contenedor
) -> dict[str, Any]:
    """Recurso de la parte agraviada dentro del término de apelación."""
    return _acreditacion(contenedor.handler_apelar.manejar(comando))


@router.post(
    "/ejecutar-sentencia",
    summary="Ejecución forzosa de sentencia firme (Arts. 258, 263 CPCN)",
)
async def ejecutar_sentencia(
    comando: EjecutarSentenciaCommand, contenedor: Contenedor
) -> dict[str, Any]:
    """Apremio sobre condena estimatoria ejecutoriada, a pedido de acreedor."""
    return _acreditacion(contenedor.handler_ejecutar.manejar(comando))
