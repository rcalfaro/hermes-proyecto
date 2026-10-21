"""Adaptadores HTTP del lado de escritura (CQRS: command side).

Los endpoints son **solo traducción HTTP → comando**: parsean el request,
instancian el comando Pydantic y lo entregan al handler. Ninguna regla de
negocio vive aquí. Mapeo de errores: 400 validación / 403 legitimación /
404 expediente / 409 conflicto de estado o preclusión (Art. 134 CPCN).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.application.commands import (
    AdmitirDemandaCommand,
    ApelarSentenciaCommand,
    ContestarDemandaCommand,
    DictarSentenciaCommand,
    EjecutarSentenciaCommand,
    PresentarDemandaCommand,
)
from app.application.commands import ComandoBase
from app.application.container import ContenedorDependencias
from app.auth.security import get_current_active_user
from app.db.models import Usuario


def obtener_contenedor(request: Request) -> ContenedorDependencias:
    """Resuelve el contenedor de DI desde el estado de la app."""
    return request.app.state.contenedor  # type: ignore[no-any-return]


Contenedor = Annotated[ContenedorDependencias, Depends(obtener_contenedor)]
UsuarioActual = Annotated[Usuario, Depends(get_current_active_user)]

router = APIRouter(prefix="/api/comandos", tags=["comandos-procesales"])


def _acreditacion(resultado: Any) -> dict[str, Any]:
    """Serializa uniformemente el ResultadoComando del handler."""
    return asdict(resultado)


def _sellar_identidad(comando: ComandoBase, usuario: Usuario) -> ComandoBase:
    """Zero Trust: el ``actor_id`` del comando SIEMPRE proviene de la sesión.

    El frontend nunca envía identidad (o envía un placeholder ignorado): aquí
    se sustituye por el ActorJuridico vinculado a la cuenta autenticada
    (``usuario.actor_id``, resuelto server-side contra la BD — única fuente
    de verdad). Si la cuenta no está encadenada a un actor del foro, ningún
    acto procesal es posible ⇒ 403 con causa clara (Art. 39 CPCN).
    """
    if usuario.actor_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Su cuenta no está vinculada a ningún actor jurídico del foro; "
                "contacte a la administración judicial para su habilitación."
            ),
        )
    return comando.model_copy(update={"actor_id": usuario.actor_id})


@router.post(
    "/presentar-demanda",
    status_code=201,
    summary="Presentar demanda (Arts. 37, 146-147 CPCN)",
)
async def presentar_demanda(
    comando: PresentarDemandaCommand,
    contenedor: Contenedor,
    usuario: UsuarioActual,
) -> dict[str, Any]:
    """Promueve el juicio ordinario civil o subsana una demanda reformable.

    Zero Trust: la identidad del promovente se toma del JWT (nunca del body).
    """
    resultado = contenedor.handler_presentar.manejar(_sellar_identidad(comando, usuario))
    return _acreditacion(resultado)


@router.post(
    "/admitir-demanda", status_code=201, summary="Auto iniciado (Art. 148 CPCN)"
)
async def admitir_demanda(
    comando: AdmitirDemandaCommand,
    contenedor: Contenedor,
    usuario: UsuarioActual,
) -> dict[str, Any]:
    """El juez titular admite la demanda y abre el traslado de diez días."""
    return _acreditacion(
        contenedor.handler_admitir.manejar(_sellar_identidad(comando, usuario))
    )


@router.post(
    "/contestar-demanda",
    summary="Contestar dentro del traslado (Art. 151 CPCN)",
)
async def contestar_demanda(
    comando: ContestarDemandaCommand,
    contenedor: Contenedor,
    usuario: UsuarioActual,
) -> dict[str, Any]:
    """Escrito de contestación; rechazado (409) si el plazo precluyó."""
    return _acreditacion(
        contenedor.handler_contestar.manejar(_sellar_identidad(comando, usuario))
    )


@router.post("/dictar-sentencia", summary="Sentencia definitiva (Arts. 192-201 CPCN)")
async def dictar_sentencia(
    comando: DictarSentenciaCommand,
    contenedor: Contenedor,
    usuario: UsuarioActual,
) -> dict[str, Any]:
    """Solo el juez titular; exige congruencia con todas las pretensiones."""
    return _acreditacion(
        contenedor.handler_sentenciar.manejar(_sellar_identidad(comando, usuario))
    )


@router.post(
    "/apelar-sentencia", summary="Apelación en quinto día (Arts. 246-248 CPCN)"
)
async def apelar_sentencia(
    comando: ApelarSentenciaCommand,
    contenedor: Contenedor,
    usuario: UsuarioActual,
) -> dict[str, Any]:
    """Recurso de la parte agraviada dentro del término de apelación."""
    return _acreditacion(
        contenedor.handler_apelar.manejar(_sellar_identidad(comando, usuario))
    )


@router.post(
    "/ejecutar-sentencia",
    summary="Ejecución forzosa de sentencia firme (Arts. 258, 263 CPCN)",
)
async def ejecutar_sentencia(
    comando: EjecutarSentenciaCommand,
    contenedor: Contenedor,
    usuario: UsuarioActual,
) -> dict[str, Any]:
    """Apremio sobre condena estimatoria ejecutoriada, a pedido de acreedor."""
    return _acreditacion(
        contenedor.handler_ejecutar.manejar(_sellar_identidad(comando, usuario))
    )
