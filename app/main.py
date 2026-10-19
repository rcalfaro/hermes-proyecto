"""Punto de entrada FastAPI del Gemelo Digital del Proceso Civil (Ley 908).

Alambre la aplicación: contenedor de dependencias en ``app.state``, routers
de comandos, queries, autenticación JWT (Zero Trust) y analítica/IA, junto con
el manejador global que traduce los errores de la capa de aplicación a códigos
HTTP (400/401/403/404/409).

Arranque gestionado (``lifespan``):
  1. Construye el motor PostgreSQL desde ``DATABASE_URL``.
  2. Crea el esquema si falta (idempotente; en producción gobernaría Alembic).
  3. Alambra el ``ContenedorDependencias`` de producción (UoW + reloj sistema
     + calendario judicial + secretos JWT desde variables de entorno).
  4. Si la tabla ``usuario`` está vacía, siembra cuentas DEMO locales para que
     el tablero sea utilizable sin pasos manuales (nunca en producción).

Tests y despliegues alternativos pueden seguir llamando a
``crear_app(contenedor)`` con un contenedor propio (SQLite + FakeClock).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import date
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api import auth_endpoints, endpoints, insights_endpoints, queries
from app.application.container import ContenedorDependencias
from app.application.errors import ErrorAplicacion
from app.application.unit_of_work import SqlAlchemyUnitOfWork
from app.auth.security import ConfiguracionJWT, hash_password
from app.db.base import Base, TipoPretension
from app.db.models import Usuario
from app.services.calendario_judicial import cargar_calendario_2026
from app.services.time_provider import SystemClock

log = logging.getLogger("gemelo.main")


# ---------------------------------------------------------------------------
# Alambre de producción
# ---------------------------------------------------------------------------


def _construir_contenedor_produccion(engine: Any) -> ContenedorDependencias:
    """Grafo DI real: PostgreSQL + reloj del sistema + secretos del entorno.

    Zero Trust: el secreto JWT SOLO proviene de ``GEMELO_JWT_SECRET``. Si el
    entorno es producción y la variable falta o usa el default de plantilla,
    la API se niega a arrancar (fail-fast: nunca tokens firmados con clave
    conocida públicamente).
    """
    # Convención del grafo DI: uow_factory produce un SqlAlchemyUnitOfWork ya
    # envuelto (los handlers hacen `with self._uow_factory() as uow`). Se pasa
    # la Session cruda al UoW para que él gestione commit/rollback/close.
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    uow_factory = lambda: SqlAlchemyUnitOfWork(factory)  # noqa: E731
    entorno = os.getenv("GEMELO_ENV", "development")
    secreto = os.getenv("GEMELO_JWT_SECRET", "")
    if entorno == "production" and (
        not secreto or secreto.startswith("REEMPLAZAR")
    ):
        raise RuntimeError(
            "GEMELO_ENV=production exige GEMELO_JWT_SECRET fuerte (ver .env.example)."
        )
    minutos = int(os.getenv("GEMELO_JWT_EXPIRE_MINUTES", "30"))
    config_jwt = ConfiguracionJWT(
        secreto=secreto or "dev-only-insecure-secret-cambiar-en-produccion",
        ttl=timedelta(minutes=minutos),
    )
    return ContenedorDependencias.construir(
        uow_factory=uow_factory,
        clock=SystemClock(),
        calendario=cargar_calendario_2026(),
        config_jwt=config_jwt,
    )


def _preparar_esquema_y_seed(session: Session) -> None:
    """Crea tablas si no existen y siembra usuarios DEMO (solo desarrollo)."""
    from app import db as _db_pkg  # noqa: F401  (registra TODOS los mappers)
    from app.analytics import modelos as _analitica  # noqa: F401

    Base.metadata.create_all(session.get_bind())

    ya_existe = session.execute(select(Usuario)).first()
    if ya_existe is not None:
        return  # ya hay usuarios: no re-sembrar (idempotencia).
    from app.db.base import RolActor
    from app.db.models import ActorJuridico, Caso, CasoActor, Pretension

    # --- Actores del foro DEMO (ids deterministas: el seed SQL de scripts/
    #     usa los mismos UUIDs; sin PII real) -------------------------------
    juez = ActorJuridico(
        id=uuid.UUID("00000000-0000-0000-0000-00000000d001"),
        tipo_persona="natural", nombre_razon_social="Dra. Jueza Demo",
        cedula_ruc="J-DEMO-001", rol_principal=RolActor.JUEZ,
    )
    dte = ActorJuridico(
        id=uuid.UUID("00000000-0000-0000-0000-00000000d002"),
        tipo_persona="juridica", nombre_razon_social="Inmobiliaria Demo S.A.",
        cedula_ruc="RUC-DTE-001", rol_principal=RolActor.DEMANDANTE,
    )
    ddo = ActorJuridico(
        id=uuid.UUID("00000000-0000-0000-0000-00000000d003"),
        tipo_persona="natural", nombre_razon_social="Arrendatario Demo",
        cedula_ruc="001-250380-1000A", rol_principal=RolActor.DEMANDADO,
    )
    session.add_all([juez, dte, ddo])

    # --- Expediente DEMO navegable en el tablero (estado PRESENTADO) --------
    caso = Caso(
        numero_expediente="00001-2026-CIV-ORD",
        tipo_proceso="juicio_ordinario_civil", materia="arrendaticio",
        juzgado_asignado="Juzgado Civil de Managua",
        fecha_presentacion_demanda=date.today(), juez_id=juez.id,
    )
    session.add(caso)
    session.flush()  # obtiene caso.id (UUID aleatorio -> se imprime abajo)
    session.add(Pretension(
        caso_id=caso.id, codigo_tipo=TipoPretension.DESALOJO, orden=1,
        descripcion=("Se declare rescindido el contrato de arrendamiento y "
                     "se ordene la entrega material del inmueble."),
        es_principal=True,
    ))
    session.add_all([
        CasoActor(caso_id=caso.id, actor_id=dte.id, rol_en_caso=RolActor.DEMANDANTE),
        CasoActor(caso_id=caso.id, actor_id=ddo.id, rol_en_caso=RolActor.DEMANDADO),
    ])

    demo = [
        # username, password, rol_sistema, actor vinculado — credenciales
        # EXPLÍCITAMENTE demo. El actor_id es lo que Zero Trust sella en cada
        # comando: el frontend jamás envía identidad.
        ("juez", "demo-juez-2026", "juez", juez),
        ("abogado_demandante", "demo-abog-2026", "abogado", dte),
        ("abogado_demandado", "demo-abog-2026", "abogado", ddo),
        ("publico", "demo-publico-2026", "publico", None),
    ]
    for username, password, rol_sistema, actor in demo:
        session.add(
            Usuario(
                username=username,
                email=f"{username}@demo.local",
                password_hash=hash_password(password),
                rol_sistema=rol_sistema,
                actor_id=actor.id if actor else None,
            )
        )
    session.commit()
    log.warning("Expediente DEMO listo para el tablero — UUID: %s", caso.id)
    log.warning(
        "Se sembraron %d cuentas DEMO (login: 'juez' / 'demo-juez-2026'). "
        "Cambiar o desactivar antes de cualquier despliegue real.",
        len(demo),
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Ciclo de vida: motor BD + contenedor de producción (si no fue inyectado)."""
    if getattr(app.state, "contenedor", None) is None:
        from sqlalchemy import create_engine

        dsn = os.environ["DATABASE_URL"]
        engine = create_engine(dsn, pool_pre_ping=True)
        with Session(engine) as session:
            _preparar_esquema_y_seed(session)
        app.state.contenedor = _construir_contenedor_produccion(engine)
        app.state.engine = engine  # lectura pura (auth/queries) usa el motor
        # Zero Trust: la config JWT vive SOLO server-side (nunca se expone).
        app.state.config_jwt = app.state.contenedor.config_jwt
        log.info("Gemelo Digital alambrado contra PostgreSQL.")
    yield


# ---------------------------------------------------------------------------
# Fábrica de la aplicación
# ---------------------------------------------------------------------------


def crear_app(contenedor: ContenedorDependencias | None = None) -> FastAPI:
    """Fábrica de la aplicación (permite inyección de contenedor de prueba)."""
    app = FastAPI(
        title="Gemelo Digital — Proceso Civil Nicaragua (CPCN, Ley 908)",
        version="0.4.0",
        lifespan=_lifespan,
    )

    @app.exception_handler(ErrorAplicacion)
    async def _mapear_error_aplicacion(
        request: Request, exc: ErrorAplicacion
    ) -> JSONResponse:
        """Errores de dominio → HTTP semántico con fundamento en el body."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detalle": exc.detalle, "codigo_http": exc.status_code},
        )

    if contenedor is not None:
        app.state.contenedor = contenedor
        app.state.config_jwt = contenedor.config_jwt
    app.include_router(auth_endpoints.router)   # POST /api/auth/login, GET /me
    app.include_router(endpoints.router)        # comandos CQRS (protegidos JWT)
    app.include_router(queries.router)          # lado de lectura
    # Fase 8: capa de IA (solo lectura; no toca el flujo transaccional).
    app.include_router(insights_endpoints.router)

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {"estado": "ok", "dominio": "proceso_civil_nicaragua"}

    return app


#: ASGI por defecto (uvicorn app.main:app); el lifespan alambra producción.
app = crear_app()
