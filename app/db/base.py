"""Configuración base de SQLAlchemy 2.0 para el Gemelo Digital del Proceso Civil.

Incluye:
    * ``Base`` declarativa con naming convention adaptada a PostgreSQL.
    * Mixins de auditoría (``created_at`` / ``updated_at``).
    * Enumeraciones nativas de PostgreSQL (``native_enum=True``) para los
      dominios jurídicos del Código Procesal Civil de Nicaragua.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Convención de nombres consistente para índices/restricciones en PostgreSQL,
# indispensable para las migraciones con Alembic.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Clase base declarativa (estilo SQLAlchemy 2.0)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Permite usar uuid.UUID como tipo Python en todo el esquema.
    type_annotation_map: ClassVar[dict] = {
        UUID: UUID(as_uuid=True),
    }


def utcnow() -> datetime:
    """Marca temporal UTC consciente del time-zone (server-side default)."""
    return datetime.now(UTC)


class TimestampMixin:
    """Columnas de control temporal para todas las entidades persistentes."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=text("now()"),
        nullable=False,
        comment="Momento de creación del registro.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
        nullable=False,
        comment="Momento de la última modificación del registro.",
    )


# ---------------------------------------------------------------------------
# Enumeraciones del dominio juridico del proceso civil nicaraguense (PostgreSQL)
# ---------------------------------------------------------------------------


class TipoPretension(str, enum.Enum):
    """Naturaleza de la pretensión: el 'ADN' del proceso (art. 37 CPC)."""

    COBRO_DE_DINERO = "cobro_de_dinero"
    DESALOJO = "desalojo"
    CUMPLIMIENTO_Y_O_RESCISION_DE_CONTRATO = "cumplimiento_o_rescision_de_contrato"
    PRESCRIPCION_ADQUISITIVA = "prescripcion_adquisitiva"
    PRESCRIPCION_EXTINTIVA = "prescripcion_extintiva"
    NULIDAD_ABSOLUTA_DE_ACTO_JURIDICO = "nulidad_absoluta"
    NULIDAD_RELATIVA_DE_ACTO_JURIDICO = "nulidad_relativa"
    DIVORCIO = "divorcio"
    FILIACION = "filiacion"
    REIVINDICACION = "reivindicacion"
    ABINTESTATO = "sucesion_abintestato"
    TESTAMENTO = "sucesion_testamentaria"
    OTRO = "otro"


class EtapaProcesal(str, enum.Enum):
    """Etapas del juicio ordinario civil (Libro II, Código Procesal Civil)."""

    CALIFICACION_DEMANDA = "calificacion_demanda"  # Arts. 146-148 CPC
    TRASLADO_DEMANDA = "traslado_demanda"  # Contestación, Art. 151 CPC
    AUDIENCIA_CONCILIACION = "audiencia_conciliacion"  # Art. 159 CPC
    PERIODOS_PRUEBAS = "periodos_pruebas"  # Arts. 165 y ss. CPC
    AUDIENCIA_JUICIO = "audiencia_juicio"  # Arts. 182-191 CPC
    SENTENCIA = "sentencia"  # Arts. 192-201 CPC
    EJECUCION = "ejecucion"  # Fase de cumplimiento
    RECURSOS = "recursos"  # Apelación / Casación
    ARCHIVO_DEFINITIVO = "archivo_definitivo"  # Conclusión del expediente


class EstadoProcesal(str, enum.Enum):
    """Micro-estado del caso dentro de su etapa (para validar transiciones)."""

    BORRADOR = "borrador"
    PRESENTADO = "presentado"
    ADMITIDA = "admitida"
    INADMISIBLE_REFORMABLE = "inadmisible_reformable"
    CONTESTADA = "contestada"
    EN_TRAMITE = "en_tramite"
    SENTENCIADO = "sentenciado"
    EN_RECURSO = "en_recurso"
    FIRME = "firme"
    EN_EJECUCION = "en_ejecucion"
    TERMINADO = "terminado"
    ARCHIVADO = "archivado"


class RolActor(str, enum.Enum):
    """Rol procesal que un actor jurídico desempeña en un caso concreto."""

    JUEZ = "juez"
    DEMANDANTE = "demandante"
    DEMANDADO = "demandado"
    APODERADO_JUDICIAL_DEMANDANTE = "apoderado_judicial_demandante"
    APODERADO_JUDICIAL_DEMANDADO = "apoderado_judicial_demandado"
    TERCERO_INTERVINIENTE = "tercero_interviniente"


class TipoResolucion(str, enum.Enum):
    """Tipo de resolución o acto procesal dictado dentro del expediente."""

    AUTO_INICIADO = "auto_iniciado"  # Calificación de la demanda
    DECRETO = "decreto"
    PROVIDENCIA = "providencia"
    SENTENCIA_INTERLOCUTORIA = "sentencia_interlocutoria"
    SENTENCIA_DEFINITIVA = "sentencia_definitiva"
    RESOLUCION = "resolucion"


class SentidoFallo(str, enum.Enum):
    """Sentido del fallo respecto de las pretensiones (arts. 192-201 CPC)."""

    CON_LUGAR = "con_lugar"  # Estimatorio total
    CON_LUGAR_PARCIALMENTE = "con_lugar_parcialmente"  # Estimatorio parcial
    SIN_LUGAR = "sin_lugar"  # Desestimatorio
    IMPROCEDENTE = "improcedente"
    SOBRESEIMIENTO = "sobreseimiento"


class AccionAuditoria(str, enum.Enum):
    """Acciones trazadas en el log de auditoría inmutable."""

    CREACION = "creacion"
    TRANSICION_ESTADO = "transicion_estado"
    ASIGNACION_ACTOR = "asignacion_actor"
    PRESENTACION_ESCRITO = "presentacion_escrito"
    EMISION_RESOLUCION = "emision_resolucion"
    REGISTRO_PRETENSION = "registro_pretension"
    ANOTACION = "anotacion"
    INICIO_SESION = "inicio_sesion"
    INTENTO_LOGIN_FALLIDO = "intento_login_fallido"
