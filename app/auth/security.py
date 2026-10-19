"""Autenticación JWT bajo principio Zero Trust (Gemelo Digital — CPCN, Ley 908).

Flujo de seguridad
------------------
1. ``POST /api/auth/login`` valida credenciales contra ``usuario.password_hash``
   (bcrypt) y emite un **access token** de vida corta (default 30 min).
2. El frontend guarda el token y lo envía EXCLUSIVAMENTE en la cabecera
   ``Authorization: Bearer <jwt>``. NUNCA envía ``actor_id`` ni rol procesal
   en el cuerpo de la petición: son datos que un cliente malicioso podría
   forjar para suplantar al juez o a la contraparte.
3. Cada endpoint protegido depende de ``get_current_active_user``, que:
   a) decodifica y verifica firma/expiración/emisor del JWT (PyJWT, HS256);
   b) consulta la BD por ``sub`` (user_id) — la BD es la ÚNICA fuente de
      verdad sobre si la cuenta sigue activa y qué actor representa;
   c) inyecta el objeto ``Usuario`` en el handler/endpoint.
4. La legitimación procesal fina (qué Actor puede actuar en QUÉ expediente
   y con QUÉ rol) NO vive en el token: se resuelve por caso en
   ``app.auth.usuarios.resolver_actor_y_rol`` contra ``caso_actor``, y el
   ``CaseFlowEngine`` la compara con los ``roles_autorizados`` del YAML.

Reclamos del token (claims):
    * ``sub``  : identificador de usuario (UUID canónico).
    * ``rol``  : rol de plataforma — ``juez | abogado | publico`` (RBAC de
                 superficie; ver ``require_role``).
    * ``exp``/``iat``/``nbf``: expiración (vida corta obligatoria), emitido
                 en y no-válido-antes.
    * ``iss``  : emisor — defensa ante tokens de otro entorno.
    * ``jti``  : identificador único de token (base de futura revocación).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.models import Usuario

#: Algoritmo de firma. HS256 simétrico basta para el monolito; migrar a
#: RS256/ES256 (clave asimétrica) cuando servicios externos validen tokens.
ALGORITMO = "HS256"

#: Vida del access token: corta, porque autoriza actos jurídicos. Renovación
#: silenciosa vía refresh token queda fuera de alcance (documentado).
TTL_TOKEN_MINUTOS = 30

_BEARER = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class ConfiguracionJWT:
    """Parámetros criptográficos del emisor de tokens (inyectable en tests).

    Args:
        secreto: Clave HS256. En producción proviene de variable de entorno
            (``GEMELO_JWT_SECRET``); jamás hardcodeada ni versionada.
        emisor: Identificador del emisor (claim ``iss``).
        ttl: Duración del access token.
    """

    secreto: str
    emisor: str = "gemelo-digital-cpcn"
    ttl: timedelta = timedelta(minutes=TTL_TOKEN_MINUTOS)


@dataclass(frozen=True, slots=True)
class ClaimsJWT:
    """Payload verificado de un access token."""

    sub: uuid.UUID
    rol: str
    exp: datetime
    jti: str
    iat: datetime | None = None


# --------------------------------------------------------------- contraseñas
def hash_password(contrasena: str) -> str:
    """Genera el hash bcrypt de una contraseña (coste 12, ~250 ms).

    bcrypt incorpora la sal aleatoria dentro del digest: el resultado es
    autocontenido y verificable sin columna adicional de sales.
    """
    if len(contrasena.encode("utf-8")) > 72:
        # Truncamiento silencioso de bcrypt sobre >72 bytes: rechazar.
        raise ValueError("La contraseña debe tener como máximo 72 bytes.")
    return bcrypt.hashpw(
        contrasena.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode()


def verificar_password(contrasena: str, password_hash: str) -> bool:
    """Comparación en tiempo constante entre contraseña y hash bcrypt."""
    try:
        return bcrypt.checkpw(
            contrasena.encode("utf-8"), password_hash.encode("utf-8")
        )
    except ValueError:
        # Hash malformado (dato corrupto) → nunca autenticar.
        return False


# --------------------------------------------------------------------- tokens
def crear_token_acceso(
    usuario: Usuario, config: ConfiguracionJWT, ahora: datetime | None = None
) -> str:
    """Emite un JWT firmado con claims mínimos necesarios.

    El token deliberadamente NO contiene ``actor_id`` ni roles procesales por
    expediente: son datos derivados y cambiantes (un apoderado puede ser
    revocado hoy); resolverlos desde la BD evita 'privilegios fantasma'
    atrapados en tokens viejos.
    """
    instante = ahora or datetime.now(UTC)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=UTC)
    exp = instante + config.ttl
    payload: dict[str, Any] = {
        "sub": str(usuario.id),
        "rol": usuario.rol_sistema,
        "iat": int(instante.timestamp()),
        "nbf": int(instante.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": config.emisor,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, config.secreto, algorithm=ALGORITMO)


def decodificar_token(
    token: str, config: ConfiguracionJWT, ahora: datetime | None = None
) -> ClaimsJWT:
    """Verifica firma, expiración y emisor; retorna los claims tipados.

    Args:
        ahora: Reloj inyectable (FakeClock) para pruebas de expiración. Como
            PyJWT evalúa ``exp`` contra el reloj real, se traduce la
            diferencia a ``leeway`` — determinismo sin parchar la librería.

    Raises:
        HTTPException(401): token caducado, firma inválida o emisor ajeno.
    """
    opciones: dict[str, Any] = {"require": ["sub", "exp", "jti"], "issuer": config.emisor}
    if ahora is not None:
        momento = ahora if ahora.tzinfo else ahora.replace(tzinfo=UTC)
        opciones["leeway"] = abs((datetime.now(UTC) - momento).total_seconds())
    try:
        claims = jwt.decode(
            token, config.secreto, algorithms=[ALGORITMO], options=opciones
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Su sesión ha expirado; vuelva a autenticarse.",
            headers={"X-Causa-Error": "token_expirado"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial de acceso inválida.",
            headers={"X-Causa-Error": type(exc).__name__},
        ) from exc
    try:
        sub = uuid.UUID(claims["sub"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sujeto de token inválido.",
        ) from exc
    return ClaimsJWT(
        sub=sub,
        rol=str(claims.get("rol", "")),
        exp=datetime.fromtimestamp(claims["exp"], tz=UTC),
        jti=str(claims.get("jti", "")),
        iat=(
            datetime.fromtimestamp(claims["iat"], tz=UTC)
            if claims.get("iat")
            else None
        ),
    )


# ------------------------------------------------------ proveedores de deps
def obtener_config_jwt(request: Request) -> ConfiguracionJWT:
    """Resuelve la configuración JWT registrada en ``app.state.config_jwt``."""
    config = getattr(request.app.state, "config_jwt", None)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El servidor no tiene configurada la emisión de tokens.",
        )
    return config  # type: ignore[no-any-return]


def obtener_session_auth(request: Request) -> Iterator[Session]:
    """Sesión ORM ligada al ciclo de vida de la petición (yield → cierre).

    Es una sesión de LECTURA para autenticación; las mutaciones transaccionales
    siguen viviendo en la Unit of Work de los handlers CQRS.
    """
    contenedor = request.app.state.contenedor
    session = contenedor.uow_factory()
    try:
        yield session
    finally:
        session.close()


# ------------------------------------------------------------- dependencia DI
def get_current_active_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)],
    session: Annotated[Session, Depends(obtener_session_auth)],
    config: Annotated[ConfiguracionJWT, Depends(obtener_config_jwt)],
) -> Usuario:
    """Dependencia FastAPI: JWT → objeto ``Usuario`` activo cargado de la BD.

    Cascada Zero Trust:
      1. Sin cabecera Bearer ⇒ 401 (no autenticado).
      2. Token inválido/expirado ⇒ 401 (``decodificar_token``).
      3. ``sub`` inexistente en BD ⇒ 401 — el token puede ser legítimo pero
         la cuenta fue eliminada; la BD manda sobre el token.
      4. Cuenta inactiva ⇒ 403 — identidad válida sin permiso de uso (baja
         del funcionario, colegiatura suspendida).
      5. Rol del token ≠ rol persistido ⇒ 403 — hubo degradación de
         privilegios y el token aún no expiró; se exige re-login.

    Returns:
        Instancia ORM ``Usuario`` fresca para inyectarse en endpoints/handlers.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado: falta el token Bearer.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decodificar_token(credentials.credentials, config)
    usuario = session.get(Usuario, claims.sub)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La cuenta asociada al token ya no existe en el sistema.",
        )
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada; contacte al administrador del juzgado.",
        )
    if usuario.rol_sistema != claims.rol:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los privilegios de su cuenta cambiaron; vuelva a autenticarse.",
        )
    return usuario


# Alias tipado para firmas de endpoint: `usuario: CurrentUser`.
CurrentUser = Annotated[Usuario, Depends(get_current_active_user)]


__all__ = [
    "ALGORITMO",
    "ClaimsJWT",
    "ConfiguracionJWT",
    "CurrentUser",
    "crear_token_acceso",
    "decodificar_token",
    "get_current_active_user",
    "hash_password",
    "obtener_config_jwt",
    "obtener_session_auth",
    "verificar_password",
]
