"""Modelos ORM (SQLAlchemy 2.0) del Gemelo Digital del Proceso Civil Nicaragüense.

Entidades principales:
    * ``ActorJuridico``   -- Personas jurídicas/físicas: Jueces, Abogados, Partes.
    * ``Caso``            -- Expediente judicial (entidad central).
    * ``Pretension``      -- ADN del proceso: lo que el demandante pide al juez.
    * ``TransicionEstado``-- Catálogo de transiciones válidas (máquina de estados).
    * ``ResolucionJudicial`` -- Autos, decretos, providencias y sentencias.
    * ``LogAuditoria``    -- Trazabilidad inmutable de cada acción procesal.

Estilo: SQLAlchemy 2.0 con ``DeclarativeBase``, ``Mapped`` y ``mapped_column``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    AccionAuditoria,
    Base,
    EstadoProcesal,
    EtapaProcesal,
    RolActor,
    SentidoFallo,
    TimestampMixin,
    TipoPretension,
    TipoResolucion,
)

# ---------------------------------------------------------------------------
# ACTORES JURÍDICOS
# ---------------------------------------------------------------------------


class ActorJuridico(TimestampMixin, Base):
    """Persona natural o jurídica que participa en el sistema judicial.

    Cubre tres perfiles mediante ``rol_principal``: juez, abogado (con número
    de colegiación exigible por la Ley de Ejercicio de la Abogacía) y parte
    procesal (demandante/demandado). Un mismo actor puede intervenir en
    varios casos a través de la tabla puente ``CasoActor``.
    """

    __tablename__ = "actor_juridico"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Identificador único del actor.",
    )
    tipo_persona: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment="'natural' o 'juridica'.",
    )
    nombre_razon_social: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Nombre completo o razón social."
    )
    cedula_ruc: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Cédula de identidad (natural) o RUC (jurídica), Nicaragua.",
    )
    rol_principal: Mapped[RolActor] = mapped_column(
        Enum(RolActor, name="rol_actor", native_enum=True, validate_strings=True),
        nullable=False,
        comment="Rol predominante del actor dentro del sistema.",
    )
    numero_colegiado_abogado: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="N.º de colegiación en el TSJ (exigible solo a abogados).",
    )
    bufete_nombre: Mapped[str | None] = mapped_column(
        String(150), nullable=True, comment="Bufete jurídico al que pertenece."
    )
    correo_electronico: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )

    # Relaciones -------------------------------------------------------------
    intervenciones: Mapped[list[CasoActor]] = relationship(
        back_populates="actor", cascade="all, delete-orphan"
    )
    casos_como_juez: Mapped[list[Caso]] = relationship(
        "Caso",
        back_populates="juez",
        foreign_keys="Caso.juez_id",
        doc="Casos sorteados a este juzgador.",
    )

    __table_args__ = (
        CheckConstraint(
            "tipo_persona IN ('natural', 'juridica')",
            name="tipo_persona_valido",
        ),
        CheckConstraint(
            "rol_principal <> 'apoderado_judicial_demandante' "
            "OR numero_colegiado_abogado IS NOT NULL",
            name="colegiatura_exigible_al_apoderado",
        ),
        UniqueConstraint("cedula_ruc", name="cedula_ruc_unico"),
        Index("ix_actor_juridico_rol_principal", "rol_principal"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ActorJuridico id={self.id!r} rol={self.rol_principal.value!r} "
            f"nombre={self.nombre_razon_social!r}>"
        )


# ---------------------------------------------------------------------------
# CASO (EXPEDIENTE) -- ENTIDAD CENTRAL
# ---------------------------------------------------------------------------


class Caso(TimestampMixin, Base):
    """Expediente judicial: entidad central del Gemelo Digital.

    Ligado intrínsecamente a:
      * Su estado actual (``estado_actual`` + ``etapa_actual``) para validar
        transiciones contra el catálogo ``transicion_estado``.
      * Sus pretensiones (``pretensiones``, 1:N) -- el ADN del proceso.
      * Los actores vinculados (``intervenciones`` N:M vía ``CasoActor`` y
        ``juez_id`` como FK directa para integridad referencial fuerte).
      * Su bitácora inmutable (``bitacora_auditoria``).
    """

    __tablename__ = "caso"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    numero_expediente: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="N.º único de expediente, ej. '00123-2026-CIV-ORD'.",
    )
    tipo_proceso: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="juicio_ordinario_civil",
        comment="juicio_ordinario_civil | proceso_sumario | ejecucion | etc.",
    )
    materia: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="Materia civil: obligaciones, familia, sucesiones, reales...",
    )
    juzgado_asignado: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="Órgano jurisdiccional competente."
    )
    distrito_judicial: Mapped[str] = mapped_column(
        String(60), nullable=False, default="Managua"
    )

    # --- Estado actual (validación de transiciones) -------------------------
    etapa_actual: Mapped[EtapaProcesal] = mapped_column(
        Enum(
            EtapaProcesal,
            name="etapa_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=EtapaProcesal.CALIFICACION_DEMANDA,
        comment="Etapa procesal vigente del expediente.",
    )
    estado_actual: Mapped[EstadoProcesal] = mapped_column(
        Enum(
            EstadoProcesal,
            name="estado_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=EstadoProcesal.PRESENTADO,
        comment="Estado procesal vigente; debe ser alcanzable vía catálogo.",
    )
    estado_anterior: Mapped[EstadoProcesal | None] = mapped_column(
        Enum(
            EstadoProcesal,
            name="estado_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=True,
        comment="Último estado conocido (desnormalizado para consultas rápidas).",
    )
    cuantia: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Cuantía estimada en córdobas (C$); relevante para recursos.",
    )

    # --- Fechas procesales ---------------------------------------------------
    fecha_presentacion_demanda: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Fecha de presentación de la demanda."
    )
    fecha_admision: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Fecha del auto iniciado (art. 148 CPC)."
    )
    fecha_ultima_notificacion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dias_plazo_vigente: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Días hábiles restantes del plazo procesal en curso.",
    )
    cerrado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )

    # --- FK principal ----------------------------------------------------------
    juez_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("actor_juridico.id", ondelete="SET NULL"),
        nullable=True,
        comment="Juez titular sorteado para conocer del caso.",
    )

    # --- Relaciones -------------------------------------------------------------
    juez: Mapped[ActorJuridico | None] = relationship(
        back_populates="casos_como_juez", foreign_keys=[juez_id]
    )
    pretensiones: Mapped[list[Pretension]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="Pretension.orden"
    )
    intervenciones: Mapped[list[CasoActor]] = relationship(
        back_populates="caso", cascade="all, delete-orphan"
    )
    transiciones: Mapped[list[TransicionEstado]] = relationship(
        back_populates="caso",
        cascade="all, delete-orphan",
        order_by="TransicionEstado.fecha_transicion",
    )
    resoluciones: Mapped[list[ResolucionJudicial]] = relationship(
        back_populates="caso",
        cascade="all, delete-orphan",
        order_by="ResolucionJudicial.fecha_resolucion",
    )
    bitacora_auditoria: Mapped[list[LogAuditoria]] = relationship(
        back_populates="caso",
        cascade="all, delete-orphan",
        order_by="LogAuditoria.timestamp_evento",
    )

    __table_args__ = (
        CheckConstraint("cuantia IS NULL OR cuantia >= 0", name="cuantia_no_negativa"),
        CheckConstraint(
            "dias_plazo_vigente IS NULL OR dias_plazo_vigente >= 0",
            name="plazo_no_negativo",
        ),
        Index("ix_caso_etapa_estado", "etapa_actual", "estado_actual"),
        Index("ix_caso_fecha_presentacion", "fecha_presentacion_demanda"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Caso expediente={self.numero_expediente!r} "
            f"etapa={self.etapa_actual.value!r} estado={self.estado_actual.value!r}>"
        )


# ---------------------------------------------------------------------------
# PRETENSIÓN (ADN DEL PROCESO)
# ---------------------------------------------------------------------------


class Pretension(TimestampMixin, Base):
    """Pretensión deducida en la demanda (petitum).

    Una demanda puede acumular varias pretensiones (principal y subsidiarias,
    art. 147 CPC). Cada una se resuelve individualmente en la sentencia, por
    lo que el ``sentido_fallo`` queda ligado a la pretensión, no al caso.
    """

    __tablename__ = "pretension"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caso.id", ondelete="CASCADE"), nullable=False, index=True
    )
    codigo_tipo: Mapped[TipoPretension] = mapped_column(
        Enum(
            TipoPretension,
            name="tipo_pretension",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        comment="Tipo de pretensión: desalojo, cobro, nulidad... (el ADN).",
    )
    orden: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="1 = pretensión principal; >1 = acumuladas/subsidiarias.",
    )
    descripcion: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Petitum: qué se pide exactamente."
    )
    fundamento_normativo: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Normas sustantivas y adjetivas invocadas (C.C. / C.P.C.).",
    )
    monto_pretendido: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Monto reclamado (si es de contenido económico).",
    )
    es_principal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    resuelta: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    sentido_fallo: Mapped[SentidoFallo | None] = mapped_column(
        Enum(
            SentidoFallo, name="sentido_fallo", native_enum=True, validate_strings=True
        ),
        nullable=True,
        comment="Fallo respecto de ESTA pretensión tras la sentencia.",
    )

    caso: Mapped[Caso] = relationship(back_populates="pretensiones")
    resoluciones: Mapped[list[ResolucionJudicial]] = relationship(
        back_populates="pretension_resuelta"
    )

    __table_args__ = (
        UniqueConstraint(
            "caso_id", "codigo_tipo", "orden", name="uq_pretension_por_caso_tipo_orden"
        ),
        CheckConstraint("orden >= 1", name="orden_positivo"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Pretension id={self.id!r} tipo={self.codigo_tipo.value!r} "
            f"resuelta={self.resuelta}>"
        )


# ---------------------------------------------------------------------------
# VÍNCULO CASO <-> ACTORES (N:M con atributos)
# ---------------------------------------------------------------------------


class CasoActor(Base):
    """Tabla puente que vincula actores al caso con su rol procesal concreto.

    Permite historial: un mismo abogado puede representar primero al
    demandante y luego revocar poder; la vigencia se controla con fechas.
    """

    __tablename__ = "caso_actor"

    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caso.id", ondelete="CASCADE"), primary_key=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actor_juridico.id", ondelete="CASCADE"), primary_key=True
    )
    rol_en_caso: Mapped[RolActor] = mapped_column(
        Enum(RolActor, name="rol_actor", native_enum=True, validate_strings=True),
        nullable=False,
        comment="Rol efectivo desempeñado dentro de ESTE expediente.",
    )
    desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="NULL mientras la representación esté vigente.",
    )

    caso: Mapped[Caso] = relationship(back_populates="intervenciones")
    actor: Mapped[ActorJuridico] = relationship(back_populates="intervenciones")

    __table_args__ = (
        UniqueConstraint(
            "caso_id", "actor_id", "rol_en_caso", "desde", name="uq_intervencion_unica"
        ),
        Index("ix_caso_actor_rol", "rol_en_caso"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CasoActor caso={self.caso_id!r} actor={self.actor_id!r} "
            f"rol={self.rol_en_caso.value!r}>"
        )


# ---------------------------------------------------------------------------
# TRANSICIÓN DE ESTADO (BITÁCORA + CATÁLOGO VALIDADOR)
# ---------------------------------------------------------------------------


class TransicionEstado(TimestampMixin, Base):
    """Registro de una transición de estado efectivamente ejecutada en un caso.

    La validez de la transición se valida en la capa de servicio contra el
    catálogo ``ReglaTransicion`` (máquina de estados del proceso civil).
    """

    __tablename__ = "transicion_estado"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caso.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estado_desde: Mapped[EstadoProcesal] = mapped_column(
        Enum(
            EstadoProcesal,
            name="estado_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    estado_hacia: Mapped[EstadoProcesal] = mapped_column(
        Enum(
            EstadoProcesal,
            name="estado_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    etapa_desde: Mapped[EtapaProcesal] = mapped_column(
        Enum(
            EtapaProcesal,
            name="etapa_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    etapa_hacia: Mapped[EtapaProcesal] = mapped_column(
        Enum(
            EtapaProcesal,
            name="etapa_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    disparador: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="Evento que provoca la transición: 'auto_iniciado', 'vencimiento_plazo'...",
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    ejecutada_por_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("actor_juridico.id", ondelete="SET NULL"),
        nullable=True,
        comment="Actor que impulsa la transición (simulación o usuario real).",
    )
    fecha_transicion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    caso: Mapped[Caso] = relationship(back_populates="transiciones")
    ejecutada_por: Mapped[ActorJuridico | None] = relationship(
        "ActorJuridico", foreign_keys=[ejecutada_por_id]
    )

    __table_args__ = (
        CheckConstraint(
            "estado_desde <> estado_hacia OR etapa_desde <> etapa_hacia",
            name="transicion_debe_implicar_cambio",
        ),
        Index("ix_transicion_caso_fecha", "caso_id", "fecha_transicion"),
    )


class ReglaTransicion(Base):
    """Catálogo estático de transiciones permitidas (máquina de estados).

    El servicio de simulación consulta esta tabla antes de aplicar cualquier
    cambio de estado sobre un ``Caso``; si no existe regla, la transición se
    rechaza (principio de legalidad procesal: nada fuera del CPC).
    """

    __tablename__ = "regla_transicion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estado_desde: Mapped[EstadoProcesal] = mapped_column(
        Enum(
            EstadoProcesal,
            name="estado_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    estado_hacia: Mapped[EstadoProcesal] = mapped_column(
        Enum(
            EstadoProcesal,
            name="estado_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    etapa_hacia: Mapped[EtapaProcesal] = mapped_column(
        Enum(
            EtapaProcesal,
            name="etapa_procesal",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    disparador: Mapped[str] = mapped_column(String(80), nullable=False)
    requisito_normativo: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="Artículo del CPC que habilita la transición, ej. 'Art. 148 CPC'.",
    )
    orden_secuencia: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Orden canónico del flujo procesal para simulación lineal.",
    )

    __table_args__ = (
        UniqueConstraint(
            "estado_desde",
            "estado_hacia",
            "disparador",
            name="uq_regla_transicion_unica",
        ),
        CheckConstraint("estado_desde <> estado_hacia", name="no_autotransicion"),
    )


# ---------------------------------------------------------------------------
# RESOLUCIONES JUDICIALES
# ---------------------------------------------------------------------------


class ResolucionJudicial(TimestampMixin, Base):
    """Autos, decretos, providencias y sentencias emitidos en el expediente.

    La sentencia definitiva referencia las pretensiones que resuelve
    (``pretension_resuelta_id``), cerrando el ciclo pretensión -> solución.
    """

    __tablename__ = "resolucion_judicial"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caso.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[TipoResolucion] = mapped_column(
        Enum(
            TipoResolucion,
            name="tipo_resolucion",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    numero_resolucion: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment="N.º interno de resolución, ej. 'SENT-004-2026'.",
    )
    resumen: Mapped[str] = mapped_column(Text, nullable=False)
    parte_resolutiva: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="'POR TANTO...' de la resolución."
    )
    sentido_fallo: Mapped[SentidoFallo | None] = mapped_column(
        Enum(
            SentidoFallo, name="sentido_fallo", native_enum=True, validate_strings=True
        ),
        nullable=True,
    )
    es_impugnable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    recurso_interpuesto: Mapped[str | None] = mapped_column(
        String(40), nullable=True, comment="'apelacion' | 'casacion' | NULL."
    )
    emisor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("actor_juridico.id", ondelete="SET NULL"),
        nullable=True,
        comment="Juez o funcionario que suscribe la resolución.",
    )
    pretension_resuelta_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pretension.id", ondelete="SET NULL"),
        nullable=True,
        comment="Pretensión concretamente resuelta (solo en sentencias).",
    )
    fecha_resolucion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    caso: Mapped[Caso] = relationship(back_populates="resoluciones")
    emisor: Mapped[ActorJuridico | None] = relationship(
        "ActorJuridico", foreign_keys=[emisor_id]
    )
    pretension_resuelta: Mapped[Pretension | None] = relationship(
        back_populates="resoluciones", foreign_keys=[pretension_resuelta_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "caso_id", "numero_resolucion", name="uq_resolucion_numero_por_caso"
        ),
        CheckConstraint(
            "tipo <> 'sentencia_definitiva' OR sentido_fallo IS NOT NULL",
            name="sentencia_requiere_sentido_fallo",
        ),
    )


# ---------------------------------------------------------------------------
# LOG DE AUDITORÍA INMUTABLE
# ---------------------------------------------------------------------------


class LogAuditoria(Base):
    """Trazabilidad inmutable de cada acción y cambio de estado.

    Inmutabilidad garantizada por capas:
      1. Sin UPDATE/DELETE en el ORM (no hay forma de borrar por API interna).
      2. Trigger PostgreSQL ``prevent_audit_mutation`` (ver schema.sql).
      3. Permisos de BD: la aplicación solo tiene INSERT + SELECT.
    """

    __tablename__ = "log_auditoria"

    id: Mapped[int] = mapped_column(
        BIGINT(),
        primary_key=True,
        autoincrement=True,
        comment="BIGSERIAL en PostgreSQL: orden cronológico y paginación eficiente.",
    )
    timestamp_evento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    caso_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("caso.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="NULL en eventos globales (login, catálogos).",
    )
    accion: Mapped[AccionAuditoria] = mapped_column(
        Enum(
            AccionAuditoria,
            name="accion_auditoria",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    entidad_afectada: Mapped[str] = mapped_column(
        String(60), nullable=False, comment="Tabla afectada: 'caso', 'pretension'..."
    )
    registro_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="PK (como texto) del registro afectado."
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("actor_juridico.id", ondelete="SET NULL"),
        nullable=True,
        comment="Usuario/sistema que ejecutó la acción.",
    )
    estado_antes: Mapped[str | None] = mapped_column(
        String(40), nullable=True, comment="Valor de estado procesal previo."
    )
    estado_despues: Mapped[str | None] = mapped_column(
        String(40), nullable=True, comment="Valor de estado procesal posterior."
    )
    detalle: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=dict),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
        comment="Payload libre del evento (diff de campos, documentos adjuntos...).",
    )
    ip_origen: Mapped[str | None] = mapped_column(String(45), nullable=True)

    caso: Mapped[Caso | None] = relationship(back_populates="bitacora_auditoria")
    actor: Mapped[ActorJuridico | None] = relationship(
        "ActorJuridico", foreign_keys=[actor_id]
    )

    __table_args__ = (
        Index("ix_log_auditoria_caso_timestamp", "caso_id", "timestamp_evento"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<LogAuditoria id={self.id} accion={self.accion.value!r} "
            f"caso={self.caso_id!r} ts={self.timestamp_evento!r}>"
        )


# ---------------------------------------------------------------------------
# Compatibilidad con bases de datos de prueba embebidas (SQLite).
# En PostgreSQL, una PK entera autoincremental se traduce a BIGSERIAL de
# forma nativa; en SQLite es necesario compilar BIGINT como INTEGER para
# que exista ROWID autoincremental. No afecta al esquema de producción.
# ---------------------------------------------------------------------------


@compiles(BIGINT, "sqlite")
def _bigint_sqlite(type_: BIGINT, compiler: Any, **kw: Any) -> str:
    """Renderiza ``BIGINT`` como ``INTEGER`` únicamente en el dialecto SQLite."""
    return "INTEGER"
