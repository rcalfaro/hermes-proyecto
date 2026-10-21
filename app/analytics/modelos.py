"""Esquema analítico de SOLO LECTURA: hechos judiciales históricos calibrados.

Estas tablas viven en el mismo PostgreSQL pero en un esquema lógico separado
(``analytics``). Reglas de oro implementadas aquí:

1. **Separación de entornos** -- el ETL las puebla desde el sistema
   transaccional ya terminado (casos ``terminado``/``archivado``); nunca son
   fuente de verdad legal: el YAML del flujo sigue siéndolo.
2. **Privacidad / anonimización** -- no existen columnas con PII: ni nombres,
   ni cédulas/RUC, ni números de expediente reales. Solo se guardan
   *agregados* y hechos desidentificados con llave sintética
   (``hash_anonimizado`` = SHA-256(expediente + sal) truncado), que permite
   deduplicar sin reidentificar. Política completa: ``docs/IA_GOBERNANZA.md``.
3. **XAI** -- cada fila declara su ``fuente_datos`` y ventana temporal, para
   que toda predicción pueda citar "Basado en N sentencias de <distrito>,
   <periodo>".

SQLAlchemy 2.0 (``Mapped``/``mapped_column``); pgvector para embeddings.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Dimensión de los embeddings usados por el RAG del módulo nlp (modelo
#: embebible de 768 dimensiones; cambiar solo re-embeddando el corpus).
DIMENSION_EMBEDDING = 768


class HechoJudicialHistorico(Base):
    """Un caso real terminado y anonimizado (grano: 1 expediente).

    Es la 'célula de memoria' del gemelo: a partir de estos hechos se
    calibran duraciones entre etapas y tasas de éxito por pretensión.
    Prohibido almacenar PII -- ver docstring del módulo.
    """

    __tablename__ = "hechos_judiciales_historicos"
    __table_args__ = (
        UniqueConstraint("hash_anonimizado", name="uq_hecho_hash_unico"),
        CheckConstraint(
            "dias_admision_sentencia IS NULL OR dias_admision_sentencia >= 0",
            name="ck_duracion_no_negativa",
        ),
        CheckConstraint(
            "sentido_fallo IN ('con_lugar', 'con_lugar_parcialmente',"
            " 'sin_lugar', 'improcedente', 'sobreseimiento')",
            name="ck_sentido_fallo_valido",
        ),
        Index(
            "ix_hecho_tipo_pretension_fallo", "codigo_tipo_pretension", "sentido_fallo"
        ),
        Index("ix_hecho_distrito_periodo", "distrito_judicial", "anio_resolucion"),
        {"schema": None, "comment": "Tabla analítica de SOLO LECTURA (ETL nightly)."},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hash_anonimizado: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256(numero_expediente + sal) — clave sintética NO reidentificable.",
    )
    distrito_judicial: Mapped[str] = mapped_column(
        String(60), nullable=False, comment="Ej. 'Managua', 'León'."
    )
    tipo_proceso: Mapped[str] = mapped_column(String(40), nullable=False)
    codigo_tipo_pretension: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="Espejo de TipoPretension (str puro, sin FK).",
    )
    cuantia_rango: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Bucket 'baja|media|alta' — se omite el monto exacto (privacidad).",
    )
    sentido_fallo: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Sentido del fallo sobre la pretensión principal.",
    )
    anio_resolucion: Mapped[int] = mapped_column(Integer, nullable=False)
    # --- Duraciones reales observadas (calendario judicial, días hábiles) ---
    dias_presentacion_admision: Mapped[int | None] = mapped_column(Integer)
    dias_admision_sentencia: Mapped[int | None] = mapped_column(
        Integer, comment="Métrica estrella: tiempo real Admisión → Sentencia."
    )
    dias_sentencia_ejecutoria: Mapped[int | None] = mapped_column(Integer)
    tuvo_apelacion: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="0/1 (evita bool para agregados SQL).",
    )
    # --- Traza de origen (auditoría del propio dataset) ---
    fuente_datos: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="Ej. 'ETL transaccional 2026-Q1'."
    )
    ventana_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    ventana_fin: Mapped[date] = mapped_column(Date, nullable=False)
    cargado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MetricaDistritoAnual(Base):
    """Vista materializada de agregados por (distrito, pretensión, año).

    Precalculada por el ETL para que el dashboard público
    (``GET /api/publico/estadisticas``) sea O(1) y no escanee el detalle.
    """

    __tablename__ = "metrica_distrito_anual"
    __table_args__ = (
        UniqueConstraint(
            "distrito_judicial", "codigo_tipo_pretension", "anio", name="uq_metrica_agg"
        ),
        CheckConstraint("total_casos >= 0", name="ck_total_no_negativo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    distrito_judicial: Mapped[str] = mapped_column(String(60), nullable=False)
    codigo_tipo_pretension: Mapped[str] = mapped_column(String(60), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    total_casos: Mapped[int] = mapped_column(Integer, nullable=False)
    casos_con_lugar: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    casos_con_lugar_parcial: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    casos_sin_lugar: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    p50_dias_admision_sentencia: Mapped[int | None] = mapped_column(Integer)
    p90_dias_admision_sentencia: Mapped[int | None] = mapped_column(Integer)
    media_dias_admision_sentencia: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2)
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DocumentoAnonimizado(Base):
    """Corpus vectorial del RAG: fragmentos de resoluciones anonimizadas.

    La columna ``embedding`` usa **pgvector** (extensión nativa de
    PostgreSQL) para no añadir infraestructura extra al stack. El acceso
    por similitud usa índice HNSW creado en la migración
    (``db/migrations`` -> ``CREATE INDEX ... USING hnsw``).
    """

    __tablename__ = "documento_anonimizado"
    __table_args__ = (CheckConstraint("LENGTH(texto) > 0", name="ck_texto_no_vacio"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hash_fuente: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="hash_anonimizado del hecho origen (sin PII).",
    )
    codigo_tipo_pretension: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo_documento: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="'sentencia_definitiva' | 'auto_iniciado' | ...",
    )
    texto: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Fragmento YA anonimizado por el ETL (pseudonimia).",
    )
    fundamentos_legales: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment='["Art. 148 CPCN", "Art. 1302 CCN"]',
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(DIMENSION_EMBEDDING),
        nullable=False,
        comment="pgvector <=> similitud coseno.",
    )
    anio_resolucion: Mapped[int] = mapped_column(Integer, nullable=False)
