"""Unit of Work: transacción atómica por comando (patrón clásico DDD).

Cada handler envuelve carga de agregados, mutaciones de estado, registros de
transición y entradas de auditoría en **una sola transacción**: si algo falla
(comando rechazado), se revierte todo — el LogAuditoria nunca registra un acto
que no produjo efecto jurídico, y viceversa: ningún acto sin su trazabilidad.
"""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Any, Self

from sqlalchemy.orm import Session

from app.db.models import ActorJuridico, Caso, LogAuditoria


class SqlAlchemyUnitOfWork:
    """Unidad de trabajo sobre una ``Session`` de SQLAlchemy.

    Args:
        session_factory: Callable que produce una sesión nueva por comando.
    """

    def __init__(self, session_factory: Any) -> None:
        #: Acepta un callable que devuelve ``Session`` **o** una ``sessionmaker``.
        self._session_factory = session_factory
        self.session: Session = None  # type: ignore[assignment]

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()

    # ------------------------------------------------- paso al frente (Session)
    # El UoW expone la API de escritura que usan handlers y tests sin forzar a
    # todos a acceder a `uow.session` (Law of Demeter): el agregado se persiste
    # dentro de la transacción del comando, no a través de la sesión cruda.
    def add(self, objeto: Any) -> None:
        """Registra una entidad nueva en la transacción actual."""
        self.session.add(objeto)

    def add_all(self, objetos: Any) -> None:
        """Registra un iterable de entidades en la transacción actual."""
        self.session.add_all(list(objetos))

    def flush(self) -> None:
        """Envía los pendings a la BD (para obtener PKs) sin cerrar tx."""
        self.session.flush()

    # ------------------------------------------------------------ repositorios
    def cargar_caso(self, caso_id: uuid.UUID) -> Caso:
        """Carga el expediente completo o lanza ``CasoNoEncontrado``."""
        from app.application.errors import CasoNoEncontrado

        caso = self.session.get(Caso, caso_id)
        if caso is None:
            raise CasoNoEncontrado(f"Expediente {caso_id} inexistente.")
        return caso

    def cargar_actor(self, actor_id: uuid.UUID) -> ActorJuridico:
        """Carga a un actor del foro o lanza ``ErrorValidacion``."""
        from app.application.errors import ErrorValidacion

        actor = self.session.get(ActorJuridico, actor_id)
        if actor is None:
            raise ErrorValidacion(f"Actor {actor_id} inexistente.")
        return actor

    def registrar_auditoria(
        self,
        *,
        caso_id: uuid.UUID | None,
        accion: str,
        entidad_afectada: str,
        registro_id: str | None,
        actor_id: uuid.UUID | None,
        estado_antes: str | None,
        estado_despues: str | None,
        detalle: dict[str, Any],
    ) -> LogAuditoria:
        """Escribe una entrada inmutable en ``log_auditoria`` (solo INSERT)."""
        entrada = LogAuditoria(
            caso_id=caso_id,
            accion=accion,
            entidad_afectada=entidad_afectada,
            registro_id=registro_id,
            actor_id=actor_id,
            estado_antes=estado_antes,
            estado_despues=estado_despues,
            detalle=detalle,
        )
        self.session.add(entrada)
        return entrada
