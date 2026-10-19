"""Resolución de legitimación procesal: Usuario (JWT) → Actor + rol en el caso.

Zero Trust aplicado al derecho procesal: el ``actor_id`` y el ``rol_actor``
que consumen los comandos **nunca** vienen del cliente. El endpoint recibe
solo el JWT; aquí se deriva la identidad procesal real contra la BD:

1. Inscripción vigente del usuario en ``caso_actor`` (``hasta IS NULL``):
   ese es su actor y rol efectivos. Soporta abogados que patrocinan a
   varias partes (un usuario ↔ N actores vía vínculo directo ``actor_id``,
   o vía coincidencia de cédula/RUC — migración progresiva).
2. Juez titular: si ``usuario.actor_id == caso.juez_id``, actúa con rol
   ``JUEZ`` sobre ese expediente.
3. Cualquier otro vínculo se descarta: sin inscripción vigente no hay
   legitimación (Art. 39 CPCN) → HTTP 403.

El par ``(actor, rol)`` resultante se inyecta en el comando y el
``CaseFlowEngine`` lo confronta además con ``roles_autorizados`` del YAML
(segunda capa RBAC: guard de transición + plazo, Arts. 132-134 CPCN).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import RolActor
from app.db.models import ActorJuridico, Caso, CasoActor, Usuario


class ResolverLegitimacionError(Exception):
    """El usuario no tiene vinculación procesal vigente en el expediente."""


@dataclass(frozen=True, slots=True)
class LegitimacionProcesal:
    """Identidad procesal efectiva de un usuario dentro de UN caso."""

    actor_id: uuid.UUID
    rol_actor: RolActor
    actor_nombre: str
    usuario_id: uuid.UUID | None = None

    def como_detalle_auditoria(self) -> dict[str, str]:
        """Evidencia serializable para el LogAuditoria (trazabilidad JWT→acto)."""
        datos = {
            "actor_id": str(self.actor_id),
            "rol_actor": self.rol_actor.value,
            "actor_nombre": self.actor_nombre,
        }
        if self.usuario_id is not None:
            datos["usuario_jwt"] = str(self.usuario_id)
        return datos


def resolver_actor_y_rol(
    session: Session, usuario: Usuario, caso_id: uuid.UUID
) -> LegitimacionProcesal:
    """Deriva el ``(actor_id, rol_actor)`` con el que ``usuario`` impulsa el acto.

    Args:
        session: Sesión ORM de la petición (solo lectura).
        usuario: Cuenta autenticada por ``get_current_active_user``.
        caso_id: Expediente objeto del acto procesal.

    Returns:
        La legitimación efectiva, lista para poblar el comando.

    Raises:
        ResolverLegitimacionError: si ninguna regla de vinculación aplica.
    """
    caso = session.get(Caso, caso_id)
    if caso is None:
        raise ResolverLegitimacionError("Expediente inexistente.")

    # 1) Intervenciones vigentes del expediente cuyo actor pertenezca al
    #    usuario (vínculo directo o por documento — ver _pertenece_a_usuario).
    intervenciones = session.scalars(
        select(CasoActor)
        .where(CasoActor.caso_id == caso_id, CasoActor.hasta.is_(None))
    ).all()
    candidatos: list[tuple[CasoActor, ActorJuridico]] = []
    for intervencion in intervenciones:
        actor = session.get(ActorJuridico, intervencion.actor_id)
        if actor is not None and actor.activo and _pertenece_a_usuario(
            session, usuario, actor
        ):
            candidatos.append((intervencion, actor))
    if candidatos:
        # Determinismo ante empates (dos roles vigentes para el mismo actor):
        # se elige la inscripción más antigua; el motor RBAC aún debe
        # autorizar ese rol concreto contra roles_autorizados del YAML.
        elegida, actor_elegido = min(
            candidatos, key=lambda par: (par[0].desde, str(par[0].actor_id))
        )
        return LegitimacionProcesal(
            actor_elegido.id, elegida.rol_en_caso, actor_elegido.nombre_razon_social,
            usuario.id,
        )

    # 2) Juez titular: su actor principal debe ser exactamente caso.juez_id.
    if usuario.actor_id is not None and usuario.actor_id == caso.juez_id:
        actor = session.get(ActorJuridico, usuario.actor_id)
        if actor is not None and actor.activo:
            return LegitimacionProcesal(
                actor.id, RolActor.JUEZ, actor.nombre_razon_social, usuario.id
            )

    raise ResolverLegitimacionError(
        f"El usuario '{usuario.username}' no está legitimado en el expediente "
        f"{caso.numero_expediente} (Art. 39 CPCN)."
    )


def _pertenece_a_usuario(
    session: Session, usuario: Usuario, actor: ActorJuridico
) -> bool:
    """Vínculo cuenta↔actor.

    Regla primaria: ``usuario.actor_id == actor.id`` (cuenta mono-actor).
    Regla de migración: coincidencia de documento (cedularuc del usuario vs.
    ``cedula_ruc`` del actor) para cuentas creadas antes de la normalización;
    se retira cuando la tabla de patrocinios N:M entre en producción.
    """
    if usuario.actor_id == actor.id:
        return True
    documento_usuario = getattr(usuario, "documento_identidad", None)
    return bool(documento_usuario) and actor.cedula_ruc == documento_usuario


__all__ = ["LegitimacionProcesal", "ResolverLegitimacionError", "resolver_actor_y_rol"]
