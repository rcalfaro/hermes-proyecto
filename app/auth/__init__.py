"""Capa de Autenticación y Autorización (Zero Trust) del Gemelo Digital."""

from app.auth.permissions import require_role
from app.auth.security import (
    ClaimsJWT,
    ConfiguracionJWT,
    CurrentUser,
    crear_token_acceso,
    decodificar_token,
    get_current_active_user,
    hash_password,
    verificar_password,
)
from app.auth.usuarios import (
    LegitimacionProcesal,
    ResolverLegitimacionError,
    resolver_actor_y_rol,
)

__all__ = [
    "ClaimsJWT",
    "ConfiguracionJWT",
    "CurrentUser",
    "LegitimacionProcesal",
    "ResolverLegitimacionError",
    "crear_token_acceso",
    "decodificar_token",
    "get_current_active_user",
    "hash_password",
    "require_role",
    "resolver_actor_y_rol",
    "verificar_password",
]
