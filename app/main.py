"""Punto de entrada FastAPI del Gemelo Digital del Proceso Civil (Ley 908).

Alambre la aplicación: contenedor de dependencias en ``app.state``, routers
de comandos y consultas, y el manejador global que traduce los errores de la
capa de aplicación a códigos HTTP (400/403/404/409).

Producción: inyectar ``uow_factory`` sobre asyncpg/PostgreSQL; aquí se expone
``crear_app(contenedor)`` para que tests y despliegue compartan el mismo grafo.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import endpoints, insights_endpoints, queries
from app.application.container import ContenedorDependencias
from app.application.errors import ErrorAplicacion


def crear_app(contenedor: ContenedorDependencias | None = None) -> FastAPI:
    """Fábrica de la aplicación (permite inyección de contenedor de prueba)."""
    app = FastAPI(
        title="Gemelo Digital — Proceso Civil Nicaragua (CPCN, Ley 908)",
        version="0.3.0",
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
    app.include_router(endpoints.router)
    app.include_router(queries.router)
    # Fase 8: capa de IA (solo lectura; no toca el flujo transaccional).
    app.include_router(insights_endpoints.router)

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {"estado": "ok", "dominio": "proceso_civil_nicaragua"}

    return app


#: ASGI por defecto (uvicorn app.main:app); se rellena al arrancar el proceso.
app = crear_app()
