"""Endpoints de autenticación: login (emisión JWT) y perfil (/me).

Flujo de seguridad documentado en ``app.auth.security``:

    credenciales (usuario+contraseña, HTTPS-only)
      → verificación bcrypt contra BD (coste 12, tiempo constante)
      → JWT HS256 {sub, rol, exp, iat, nbf, iss, jti}, TTL corto
      → el cliente SOLO porta el token; identidad procesal se deriva en
        cada request desde la BD (Zero Trust).

Errores: 401 credenciales invalidas (mensaje uniforme — no revela si el
usuario existe, mitigando user-enumeration), 403 cuenta desactivada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import (
    ConfiguracionJWT,
    CurrentUser,
    crear_token_acceso,
    obtener_config_jwt,
    obtener_session_auth,
    verificar_password,
)
from app.db.base import AccionAuditoria
from app.db.models import Usuario

router = APIRouter(prefix="/api/auth", tags=["autenticacion"])


class CredencialesLogin(BaseModel):
    """Cuerpo de ``POST /api/auth/login`` — solo credenciales, nada más."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=72)


@dataclass(frozen=True, slots=True)
class PortadorDeToken:
    """Resultado interno del login: usuario autenticado + JWT emitido."""

    usuario: Usuario
    token: str
    expira_en: datetime | None = None


def autenticar_portador(
    session: Session, config: ConfiguracionJWT, username: str, password: str
) -> PortadorDeToken:
    """Valida credenciales y emite el access token (núcleo reutilizable).

    Separado del endpoint para que tests unitarios ataquen la lógica sin
    HTTP. La comparación de contraseña usa bcrypt (tiempo constante); el
    fallo es SIEMPRE el mismo mensaje 401 para no filtrar existencia de
    cuentas.
    """
    usuario = session.scalars(
        select(Usuario).where(Usuario.username == username.lower())
    ).first()
    if usuario is None or not verificar_password(password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada; contacte al administrador del juzgado.",
        )
    token = crear_token_acceso(usuario, config)
    return PortadorDeToken(usuario=usuario, token=token)


@router.post(
    "/login",
    summary="Autenticación por credenciales → JWT de vida corta",
    response_model=dict,
)
def login(
    credenciales: CredencialesLogin,
    request: Request,
    session: Annotated[Session, Depends(obtener_session_auth)],
    config: Annotated[ConfiguracionJWT, Depends(obtener_config_jwt)],
) -> dict[str, Any]:
    """Verifica credenciales (bcrypt) y devuelve el par {token, tipo, expira}."""
    portador = autenticar_portador(
        session, config, credenciales.username, credenciales.password
    )
    # Registro de intento exitoso SIN credenciales: trazabilidad de accesos
    # (quién entró al tribunal digital y cuándo), con hash de auditoría.
    contenedor = request.app.state.contenedor
    with contenedor.uow_factory() as uow:
        uow.registrar_auditoria(
            caso_id=None,
            accion=AccionAuditoria.INICIO_SESION.value,
            entidad_afectada="usuario",
            registro_id=str(portador.usuario.id),
            actor_id=portador.usuario.actor_id,
            estado_antes=None,
            estado_despues="autenticado",
            detalle={
                "username": portador.usuario.username,
                "rol": portador.usuario.rol_sistema,
                "fundamento_legal": "Control de acceso — Zero Trust (sin cita CPCN)",
            },
        )
    return {
        "access_token": portador.token,
        "token_type": "bearer",
        "rol": portador.usuario.rol_sistema,
    }


@router.get("/me", summary="Perfil del usuario autenticado (desde el JWT)")
def leer_perfil(usuario: CurrentUser) -> dict[str, Any]:
    """Devuelve la identidad REAL de la sesión: el cuerpo de la respuesta se
    construye desde el objeto cargado por ``get_current_active_user``, nunca
    desde claims crudos del token (la BD manda)."""
    return {
        "id": str(usuario.id),
        "username": usuario.username,
        "email": usuario.email,
        "rol_sistema": usuario.rol_sistema,
        "actor_principal_id": str(usuario.actor_id) if usuario.actor_id else None,
        "actor_principal_nombre": usuario.actor.nombre_razon_social if usuario.actor else None,
        "activo": usuario.activo,
    }


__all__ = ["CredencialesLogin", "PortadorDeToken", "autenticar_portador", "router"]
