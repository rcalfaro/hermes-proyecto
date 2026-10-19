"""Comandos de la capa de aplicación — un acto procesal, un comando.

Patrón CQRS ligero: cada clase es una orden inmutable e autovalidada que
describe **qué** acto procesal se pretende y **quién** lo impulsa. No contienen
lógica de negocio: esa vive en los handlers (``app.application.command_handlers``).

Convención de nombres imperativos del foro civil nicaragüense:
``PresentarDemandaCommand``, ``ContestarDemandaCommand``, ``DictarSentenciaCommand``,
``ApelarSentenciaCommand``, ``EjecutarSentenciaCommand``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.base import RolActor, SentidoFallo, TipoPretension


class ComandoBase(BaseModel):
    """Campos comunes a todo acto procesal dirigido a un expediente."""

    model_config = ConfigDict(frozen=True)

    caso_id: uuid.UUID = Field(description="Expediente judicial objeto del acto.")
    actor_id: uuid.UUID = Field(
        description="Actor jurídico que impulsa el acto (legitimación, Art. 39 CPCN)."
    )
    rol_actor: RolActor = Field(
        description="Rol procesal con el que actúa; base del RBAC del motor de flujo."
    )
    fundamento_legal: str | None = Field(
        default=None,
        max_length=200,
        description="Cita normativa invocada por el promovente (opcional).",
    )


class PretensionInput(BaseModel):
    """Una pretensión deducida en la demanda (petitum, Arts. 37 y 146 CPCN)."""

    model_config = ConfigDict(frozen=True)

    codigo_tipo: TipoPretension
    descripcion: str = Field(min_length=10, description="Petitum: qué se pide al juez.")
    fundamento_normativo: str | None = Field(
        default=None, description="Normas sustantivas en que se apoya (ej. CCyC art.)."
    )
    monto_pretendido: Decimal | None = Field(default=None, ge=0)
    es_principal: bool = True


class PresentarDemandaCommand(ComandoBase):
    """Promoción del juicio ordinario civil (Arts. 37, 146-147 CPCN).

    Efecto en el gemelo: crea/reescribe el escrito de demanda y deja el
    expediente en estado ``PRESENTADO`` para calificación judicial.
    Si el caso ya está ``INADMISIBLE_REFORMABLE``, representa la subsanación
    dentro de tercero día (Art. 147 CPCN).
    """

    tipo_proceso: str = Field(default="juicio_ordinario_civil", max_length=40)
    materia: str = Field(min_length=3, max_length=60)
    juzgado_asignado: str = Field(min_length=5, max_length=120)
    fecha_presentacion: date
    cuantia: Decimal | None = Field(default=None, ge=0)
    hechos: str = Field(
        min_length=20, description="Relación de hechos (Art. 146 num. 3)."
    )
    pretensiones: list[PretensionInput] = Field(min_length=1)

    @field_validator("fecha_presentacion")
    @classmethod
    def _no_futuro(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("La fecha de presentación no puede ser futura.")
        return v


class AdmitirDemandaCommand(ComandoBase):
    """Proveído del juez que admite o rechaza liminarmente la demanda.

    Art. 148 CPCN: auto iniciado dentro de tercero día de recibida la
    demanda; Art. 147: inadmisible reformable subsanable en tercero día.
    El cómputo del plazo de contestación se realiza externamente con
    ``PlazoService`` (servicio puro) y se adjunta como evidencia.
    """

    admite: bool = True
    numero_resolucion: str = Field(min_length=1, max_length=40)
    resumen: str = Field(min_length=20)
    parte_resolutiva: str = Field(min_length=10)
    dias_emplazamiento: int = Field(default=10, ge=1, le=30)
    observaciones: str | None = None
    #: Cómputo del traslado calculado externamente con PlazoService (DI);
    #: se transmite como evidencia serializable y reconstruible.
    computo_traslado: dict[str, Any] | None = None

    def computo_reconstruido(self) -> Any:
        """Reconstruye el ``ComputoPlazo`` desde la evidencia serializada.

        La evidencia es exactamente el payload de ``como_detalle_auditoria``
        (Art. 132 CPCN), lo que garantiza paridad cómputo ↔ auditoría.
        """
        from datetime import date as _date

        from app.services.plazo_service import ComputoPlazo, TipoPlazo

        if self.computo_traslado is None:
            return None
        d = self.computo_traslado
        return ComputoPlazo(
            fecha_inicio=_date.fromisoformat(d["fecha_inicio"]),
            primer_dia_habil=_date.fromisoformat(d["primer_dia_habil"]),
            fecha_vencimiento=_date.fromisoformat(d["fecha_vencimiento"]),
            vencimiento_datetime=datetime.fromisoformat(d["vencimiento_datetime"]),
            dias_habiles_solicitados=d["dias_habiles_solicitados"],
            dias_habiles_contados=d["dias_habiles_contados"],
            feriados_saltados=tuple(
                _date.fromisoformat(x) for x in d["feriados_saltados"]
            ),
            tipo_plazo=TipoPlazo(d["tipo_plazo"]),
            fundamento_legal=d["fundamento_legal"],
        )


class ContestarDemandaCommand(ComandoBase):
    """Escrito de contestación dentro del traslado (Art. 151 CPCN).

    El handler verifica contra el plazo ``contestacion_demanda``: si venció,
    la facultad precluyó (Art. 134 CPCN) y el comando se rechaza con 409;
    el sistema habrá declarado la rebeldía previamente (Arts. 151/153 CPCN).
    """

    excepciones_opuestas: list[str] = Field(
        default_factory=list,
        description="Excepciones perentorias/dilatorias opuestas (Art. 152 CPCN).",
    )
    contra_pretensiones: list[PretensionInput] = Field(
        default_factory=list,
        description="Reconvención, si se formula (Art. 151 in fine CPCN).",
    )
    oferta_probatoria: str = Field(
        min_length=10, description="Medios de prueba que ofrece el demandado."
    )


class DictarSentenciaCommand(ComandoBase):
    """Sentencia definitiva del juez (Arts. 192-201 CPCN).

    Debe resolver **cada pretensión** deducida (congruencia, Art. 197 CPCN);
    el handler valida que ``fallos`` cubra todas las pretensiones del caso.
    Solo el rol JUEZ está legitimado (RBAC de la regla de flujo).
    """

    numero_resolucion: str = Field(min_length=1, max_length=40)
    resumen: str = Field(min_length=20, description="Considerandos de la sentencia.")
    parte_resolutiva: str = Field(
        min_length=10, description="'POR TANTO...': dispositivo formal."
    )
    fallos: dict[uuid.UUID, SentidoFallo] = Field(
        description="Mapa pretension_id -> sentido del fallo (congruencia Art. 197)."
    )

    @field_validator("fallos")
    @classmethod
    def _no_vacio(
        cls, v: dict[uuid.UUID, SentidoFallo]
    ) -> dict[uuid.UUID, SentidoFallo]:
        if not v:
            raise ValueError("La sentencia debe resolver al menos una pretensión.")
        return v


class ApelarSentenciaCommand(ComandoBase):
    """Recurso de apelación en quinto día (Arts. 246-248 CPCN).

    Lo interpone la parte agraviada (demandante o demandado/apoderados) dentro
    del plazo ``termino_apelacion``; el handler rechaza fuera de él (409).
    """

    agravios: str = Field(
        min_length=20,
        description="Agravios concretos que fundan el recurso (Art. 248).",
    )
    petitorio: str = Field(
        min_length=10, description="Qué se pide al tribunal de alzada."
    )


class EjecutarSentenciaCommand(ComandoBase):
    """Inicio de la ejecución forzosa de sentencia firme (Arts. 263 y ss. CPCN).

    Solo procede sobre sentencias ejecutoriadas (estado FIRME, Art. 258 CPCN);
    la parte acreedora (demandante) solicita el apremio conforme a lo resuelto.
    """

    pretension_ejecutada_id: uuid.UUID = Field(
        description="Pretensión estimatoria cuya condena se busca hacer efectiva."
    )
    forma_de_apereo: str = Field(
        min_length=10,
        max_length=120,
        description="Medio de apremio solicitado (embargo, entrega, desalojo...).",
    )
    monto_liquido: Decimal | None = Field(default=None, ge=0)


__all__ = [
    "AdmitirDemandaCommand",
    "ApelarSentenciaCommand",
    "ComandoBase",
    "ContestarDemandaCommand",
    "DictarSentenciaCommand",
    "EjecutarSentenciaCommand",
    "PresentarDemandaCommand",
    "PretensionInput",
]
