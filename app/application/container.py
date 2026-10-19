"""Contenedor de inyección de dependencias (composition root).

Construye una vez por proceso: UoW factory, reloj, calendario, motor de
plazos, motor de flujo y los cinco handlers. FastAPI los expone vía
``Depends``; los tests construyen un contenedor con ``FakeClock`` y SQLite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.application.command_handlers import (
    AdmitirDemandaHandler,
    ApelarSentenciaHandler,
    ContestarDemandaHandler,
    DictarSentenciaHandler,
    EjecutarSentenciaHandler,
    PresentarDemandaHandler,
    RegistroPlazos,
)
from app.engine.flow_engine import CaseFlowEngine
from app.services.calendario_judicial import CalendarioJudicial
from app.services.plazo_service import PlazoService
from app.services.time_provider import TimeProvider

#: Secreto de SOLO desarrollo (tests y `uvicorn` local). En produccion se
#: sobrescribe con GEMELO_JWT_SECRET; su uso fuera de local debe alertar.
_SECRETO_DESARROLLO = "dev-only-insecure-secret-cambiar-en-produccion"

#: Reglas del juicio ordinario civil (Ley 908) — catálogo declarativo.
RUTA_REGLAS = Path(__file__).resolve().parents[2] / "config" / "flow_reglas.yaml"


@dataclass(slots=True)
class ContenedorDependencias:
    """Grafo de objetos de la aplicación (singleton por proceso/test)."""

    uow_factory: Callable[[], Any]
    clock: TimeProvider
    calendario: CalendarioJudicial
    flow_engine: CaseFlowEngine
    registro_plazos: RegistroPlazos
    handler_presentar: PresentarDemandaHandler
    handler_admitir: AdmitirDemandaHandler
    handler_contestar: ContestarDemandaHandler
    handler_sentenciar: DictarSentenciaHandler
    handler_apelar: ApelarSentenciaHandler
    handler_ejecutar: EjecutarSentenciaHandler
    #: Configuracion JWT del emisor de tokens. Default: secreto de desarrollo
    #: (SOLO local/tests); en produccion se inyecta desde GEMELO_JWT_SECRET —
    #: ver main.crear_app. Nunca se expone al cliente: solo firma/verifica.
    config_jwt: Any | None = field(default=None)

    @classmethod
    def construir(
        cls,
        uow_factory: Callable[[], Any],
        clock: TimeProvider,
        calendario: CalendarioJudicial,
        ruta_reglas: Path | str = RUTA_REGLAS,
        config_jwt: Any | None = None,
    ) -> ContenedorDependencias:
        """Alambra el contenedor completo con dependencias explícitas.

        Args:
            config_jwt: Configuración del emisor JWT; ``None`` usa el secreto
                de desarrollo (solo local/tests). En producción main.crear_app
                la construye desde variable de entorno.
        """
        from app.auth.security import ConfiguracionJWT

        flow = CaseFlowEngine.desde_yaml(ruta_reglas)
        plazos = RegistroPlazos.en_memoria()
        common: dict[str, Any] = {
            "uow_factory": uow_factory,
            "flow_engine": flow,
            "clock": clock,
            "registro_plazos": plazos,
        }
        return cls(
            uow_factory=uow_factory,
            clock=clock,
            calendario=calendario,
            flow_engine=flow,
            registro_plazos=plazos,
            handler_presentar=PresentarDemandaHandler(**common),
            handler_admitir=AdmitirDemandaHandler(**common),
            handler_contestar=ContestarDemandaHandler(**common),
            handler_sentenciar=DictarSentenciaHandler(**common),
            handler_apelar=ApelarSentenciaHandler(**common),
            handler_ejecutar=EjecutarSentenciaHandler(**common),
            config_jwt=config_jwt
            or ConfiguracionJWT(secreto=_SECRETO_DESARROLLO),
        )

    def servicio_plazos(self, auditoria: Any = None) -> PlazoService:
        """Motor de plazos compartiendo el reloj inyectado del contenedor."""
        return PlazoService(self.calendario, self.clock, auditoria)


#: Instancia global de producción (se rellena en main.lifespan).
contenedor: ContenedorDependencias | None = None
