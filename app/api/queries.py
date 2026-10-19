"""Adaptadores HTTP del lado de lectura (CQRS: query side).

Consultas puras sobre el expediente: sin mutaciones, sin handlers. Incluye
la vista **anonimizada** para simulaciones públicas del gemelo digital
(se suprimen nombres, cédulas/RUC y datos de las partes — protección de
datos personales, Ley 787 de acceso a la información pública, principio de
publicidad de las resoluciones, Art. 6 CPCN).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.endpoints import obtener_contenedor
from app.application.unit_of_work import SqlAlchemyUnitOfWork
from app.db.models import Caso, LogAuditoria


class EstadoCasoDTO(BaseModel):
    """Fotografía del estado vital del expediente."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    numero_expediente: str
    tipo_proceso: str
    materia: str
    juzgado_asignado: str
    etapa_actual: str
    estado_actual: str
    estado_anterior: str | None
    cuantia: float | None
    fecha_presentacion_demanda: Any
    fecha_admision: Any
    cerrado: bool


class PretensionDTO(BaseModel):
    codigo_tipo: str
    orden: int
    descripcion: str
    es_principal: bool
    resuelta: bool
    sentido_fallo: str | None


class EntradaAuditoriaDTO(BaseModel):
    """Registro inmutable del log — base del replay determinista."""

    id: int
    timestamp_evento: datetime
    accion: str
    entidad_afectada: str
    actor_id: uuid.UUID | None
    estado_antes: str | None
    estado_despues: str | None
    fundamento_legal: str | None = Field(
        description="Extraído del detalle JSONB cuando existe."
    )
    detalle: dict[str, Any]


class PlazoDTO(BaseModel):
    id: uuid.UUID
    nombre: str
    estado: str
    fecha_inicio: Any
    vencimiento: datetime
    dias_habiles: int
    feriados_saltados: list[Any]


class SimulacionPublicaDTO(BaseModel):
    """Expediente anonimizado apto para publicación."""

    numero_expediente_anonimizado: str
    tipo_proceso: str
    materia: str
    etapa_actual: str
    estado_actual: str
    pretensiones_tipificadas: list[str]
    senas_resolucion: str | None


def _uow(request: Request) -> SqlAlchemyUnitOfWork:
    """La convención del contenedor es que ``uow_factory`` YA devuelve un UoW
    envuelto; aquí solo se obtiene la instancia (no re-envolver)."""
    contenedor = obtener_contenedor(request)
    uow = contenedor.uow_factory()
    assert isinstance(uow, SqlAlchemyUnitOfWork), (
        "uow_factory debe producir SqlAlchemyUnitOfWork (ver container)."
    )
    return uow


router = APIRouter(prefix="/api", tags=["consultas"])


@router.get("/casos/{caso_id}", response_model=dict)
def leer_caso(caso_id: uuid.UUID, request: Request) -> dict[str, Any]:
    """Estado actual del expediente con sus pretensiones (ADN del proceso)."""
    with _uow(request) as uow:
        caso = uow.session.get(Caso, caso_id)
        if caso is None:
            raise HTTPException(status_code=404, detail="Expediente inexistente.")
        return {
            "caso": EstadoCasoDTO.model_validate(caso).model_dump(mode="json"),
            "pretensiones": [
                PretensionDTO.model_validate(p).model_dump(mode="json")
                for p in caso.pretensiones
            ],
        }


@router.get("/casos/{caso_id}/historial", response_model=list[EntradaAuditoriaDTO])
def leer_historial(caso_id: uuid.UUID, request: Request) -> list[EntradaAuditoriaDTO]:
    """Log de auditoría completo, ordenado cronológicamente (trazabilidad)."""
    with _uow(request) as uow:
        filas = uow.session.scalars(
            select(LogAuditoria)
            .where(LogAuditoria.caso_id == caso_id)
            .order_by(LogAuditoria.id)
        ).all()
        salida: list[EntradaAuditoriaDTO] = []
        for f in filas:
            dto = EntradaAuditoriaDTO(
                id=f.id,
                timestamp_evento=f.timestamp_evento,
                accion=f.accion.value if hasattr(f.accion, "value") else str(f.accion),
                entidad_afectada=f.entidad_afectada,
                actor_id=f.actor_id,
                estado_antes=f.estado_antes,
                estado_despues=f.estado_despues,
                fundamento_legal=(f.detalle or {}).get("fundamento_legal"),
                detalle=f.detalle or {},
            )
            salida.append(dto)
        return salida


@router.get("/casos/{caso_id}/plazos", response_model=list[PlazoDTO])
def leer_plazos(caso_id: uuid.UUID, request: Request) -> list[PlazoDTO]:
    """Plazos activos y vencimientos computados del expediente."""
    contenedor = obtener_contenedor(request)
    plazos = contenedor.registro_plazos.plazos_de(caso_id)
    return [
        PlazoDTO(
            id=p.id,
            nombre=p.nombre,
            estado=p.estado.value,
            fecha_inicio=p.computo.fecha_inicio,
            vencimiento=p.computo.vencimiento_datetime,
            dias_habiles=p.computo.dias_habiles_solicitados,
            feriados_saltados=list(p.computo.feriados_saltados),
        )
        for p in plazos
    ]


@router.get(
    "/publico/simulaciones",
    response_model=list[SimulacionPublicaDTO],
    summary="Simulaciones públicas anonimizadas (Art. 6 CPCN: publicidad)",
)
def leer_simulaciones(
    request: Request, limit: Annotated[int, Field(le=50)] = 20
) -> list[SimulacionPublicaDTO]:
    """Expedientes en modo simulación, sin datos personales de las partes."""
    with _uow(request) as uow:
        casos = uow.session.scalars(
            select(Caso).where(Caso.tipo_proceso.like("%simulaci%")).limit(limit)
        ).all()
        resultado: list[SimulacionPublicaDTO] = []
        for caso in casos:
            ultima = next(
                (
                    r.sentido_fallo.value
                    for r in reversed(caso.resoluciones)
                    if r.sentido_fallo is not None
                ),
                None,
            )
            anon = "SIM-" + str(caso.id)[:8].upper()
            resultado.append(
                SimulacionPublicaDTO(
                    numero_expediente_anonimizado=anon,
                    tipo_proceso=caso.tipo_proceso,
                    materia=caso.materia,
                    etapa_actual=caso.etapa_actual.value,
                    estado_actual=caso.estado_actual.value,
                    pretensiones_tipificadas=[
                        p.codigo_tipo.value for p in caso.pretensiones
                    ],
                    senas_resolucion=ultima,
                )
            )
        return resultado
