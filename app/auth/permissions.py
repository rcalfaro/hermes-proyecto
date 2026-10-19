"""Autorización RBAC de superficie sobre claims del JWT (Zero Trust).

Dos niveles complementarios, deliberadamente separados:

* **RBAC de plataforma** (este módulo): ``require_role(...)`` mira el claim
  ``rol`` del token ya verificado por ``get_current_active_user`` — decide
  qué *tipo de usuario* puede llegar al endpoint (juez, abogado, público).
* **RBAC procesal por expediente**: vive en el dominio — los handlers
  resuelven el Actor real del usuario contra ``caso_actor`` y el
  ``CaseFlowEngine`` lo contrasta con ``roles_autorizados`` del YAML. Un
  abogado autorizado por plataforma puede aun así recibir 403 si no es la
  parte legitimada en ESE juicio (Art. 39 CPCN).

Orden de evaluación garantizado por la cadena de dependencias FastAPI:
primero identidad (401), luego rol de plataforma (403), luego legitimación
procesal (403 con detalle jurídico).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.security import CurrentUser
from app.db.models import Usuario

#: Roles de plataforma admitidos (espejo del CHECK ``usuario.rol_sistema``).
ROL_JUEZ = "juez"
ROL_ABOGADO = "abogado"
ROL_PUBLICO = "publico"


def require_role(allowed_roles: list[str]) -> Callable[..., Usuario]:
    """Fábrica de dependencias que exige un rol de plataforma en el JWT.

    Args:
        allowed_roles: Subconjunto de ``{juez, abogado, publico}`` con acceso.

    Returns:
        Dependencia FastAPI que retorna el ``Usuario`` autenticado o lanza
        ``HTTPException(403)``. No muta nada: es un guard puro sobre claims
        ya verificados criptográficamente.

    Ejemplo::

        @router.post("/dictar-sentencia",
                     dependencies=[Depends(require_role(["juez"]))])
        ...
    """
    permitidos = frozenset(allowed_roles)
    if not permitidos <= {ROL_JUEZ, ROL_ABOGADO, ROL_PUBLICO}:
        raise ValueError(f"Roles de plataforma desconocidos: {sorted(permitidos)}")

    def _guard(usuario: CurrentUser) -> Usuario:
        if usuario.rol_sistema not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Su rol de plataforma '{usuario.rol_sistema}' no está "
                    f"autorizado para este endpoint; se requiere uno de "
                    f"{sorted(permitidos)}."
                ),
            )
        return usuario

    _guard.__name__ = f"requiere_{'_'.join(sorted(permitidos))}"
    return _guard


#: Atajos declarativos para las firmas más comunes del tribunal digital.
SoloJueces = Annotated[Usuario, Depends(require_role([ROL_JUEZ]))]
AbogadosOAutorizados = Annotated[
    Usuario, Depends(require_role([ROL_JUEZ, ROL_ABOGADO]))
]

__all__ = [
    "AbogadosOAutorizados",
    "ROL_ABOGADO",
    "ROL_JUEZ",
    "ROL_PUBLICO",
    "SoloJueces",
    "require_role",
]
