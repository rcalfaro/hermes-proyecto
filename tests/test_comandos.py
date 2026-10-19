"""Pruebas de integración del CQRS de actos procesales (CPCN, Ley 908).

Demuestran el flujo completo comando → handler → motor de estados → BD →
LogAuditoria, con FakeClock para dominar el tiempo procesal:

1. Demanda válida ⇒ caso pasa a calificación/admisión y queda auditado.
2. Contestación fuera de plazo ⇒ rechazo 409 (preclusión, Art. 134 CPCN).
3. Sentencia ⇒ evento en LogAuditoria con fundamento legal (Art. 197).
4. Vencimientos con FakeClock ⇒ rebeldía y su efecto preclusivo.
5. RBAC ⇒ roles no legitimados producen 403; sentencia incongruente 400.
6. Queries de solo lectura y anonimización de simulaciones públicas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.commands import (
    ApelarSentenciaCommand,
    ContestarDemandaCommand,
    DictarSentenciaCommand,
    EjecutarSentenciaCommand,
)
from app.application.container import ContenedorDependencias
from app.application.unit_of_work import SqlAlchemyUnitOfWork
from app.db.base import (
    Base,
    EstadoProcesal,
    EtapaProcesal,
    RolActor,
    SentidoFallo,
    TipoPretension,
)
from app.db.models import ActorJuridico, Caso, CasoActor, Pretension
from app.engine.flow_engine import Disparador
from app.main import crear_app
from app.services.calendario_judicial import CalendarioJudicial
from app.services.plazo_service import EventoVencimiento, TipoPlazo, nuevo_plazo
from app.services.time_provider import FakeClock

# ------------------------------------------------------------------ utilidades


@pytest.fixture(name="clock")
def fixture_clock() -> FakeClock:
    return FakeClock(datetime(2026, 3, 2, 9, 0, 0, tzinfo=UTC))


@pytest.fixture(name="uow_factory")
def fixture_uow_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture(name="contenedor")
def fixture_contenedor(uow_factory, clock) -> ContenedorDependencias:
    calendario = CalendarioJudicial(
        feriados=frozenset({date(2026, 5, 1), date(2026, 4, 9)}), nombre="prueba-2026"
    )
    return ContenedorDependencias.construir(uow_factory, clock, calendario)


@pytest.fixture(name="client")
def fixture_client(contenedor) -> TestClient:
    return TestClient(crear_app(contenedor))


def _semilla(uow_factory, *, estado=EstadoProcesal.PRESENTADO) -> dict[str, uuid.UUID]:
    """Crea juez, demandante, demandado y expediente precargado."""
    ids = {k: uuid.uuid4() for k in ("caso", "juez", "demandante", "demandado")}
    with SqlAlchemyUnitOfWork(uow_factory) as uow:
        juez = ActorJuridico(
            id=ids["juez"],
            tipo_persona="natural",
            nombre_razon_social="Dra. Sinergia",
            rol_principal=RolActor.JUEZ,
            cedula_ruc="J-001",
        )
        dte = ActorJuridico(
            id=ids["demandante"],
            tipo_persona="juridica",
            nombre_razon_social="Inmobiliaria X LTDA",
            rol_principal=RolActor.DEMANDANTE,
            cedula_ruc="RUC-DTE",
        )
        ddo = ActorJuridico(
            id=ids["demandado"],
            tipo_persona="natural",
            nombre_razon_social="B. Pérez",
            rol_principal=RolActor.DEMANDADO,
            cedula_ruc="CED-DDO",
        )
        caso = Caso(
            id=ids["caso"],
            numero_expediente="001-2026-CIV-ORD",
            tipo_proceso="juicio_ordinario_civil",
            materia="desalojo",
            juzgado_asignado="Juzgado Civil Managua",
            etapa_actual=EtapaProcesal.CALIFICACION_DEMANDA,
            estado_actual=estado,
            fecha_presentacion_demanda=date(2026, 3, 2),
            juez_id=ids["juez"],
        )
        uow.session.add_all([juez, dte, ddo, caso])
        if estado is not EstadoProcesal.PRESENTADO:
            caso.pretensiones.append(
                Pretension(
                    id=ids.get("pretension", uuid.uuid4()),
                    caso_id=caso.id,
                    codigo_tipo=TipoPretension.DESALOJO,
                    orden=1,
                    descripcion="Se declare terminado el contrato de alquiler y desocupen el inmueble.",
                    es_principal=True,
                )
            )
        uow.session.add_all(
            [
                CasoActor(
                    caso_id=caso.id,
                    actor_id=ids["demandante"],
                    rol_en_caso=RolActor.DEMANDANTE,
                ),
                CasoActor(
                    caso_id=caso.id,
                    actor_id=ids["demandado"],
                    rol_en_caso=RolActor.DEMANDADO,
                ),
            ]
        )
        uow.session.flush()
        ids["pretension"] = (
            caso.pretensiones[0].id
            if caso.pretensiones
            else ids.get("pretension", uuid.uuid4())
        )
    return ids


# ====================================================== 1. DEMANDA → ADMISIÓN


def test_presentar_demanda_valida_deja_el_caso_para_admision(client, contenedor):
    """Demanda bien formada ⇒ PRESENTADO (calificación, Arts. 146-148 CPCN)."""
    with contenedor.uow_factory() as uow:
        juez = ActorJuridico(
            id=uuid.uuid4(),
            tipo_persona="natural",
            nombre_razon_social="Juez Sorteador",
            rol_principal=RolActor.JUEZ,
        )
        dte = ActorJuridico(
            id=uuid.uuid4(),
            tipo_persona="natural",
            nombre_razon_social="Ana Demandante",
            rol_principal=RolActor.DEMANDANTE,
        )
        caso = Caso(
            id=uuid.uuid4(),
            numero_expediente="002-2026-CIV-ORD",
            tipo_proceso="juicio_ordinario_civil",
            materia="cobro",
            juzgado_asignado="Juzgado 1 Civil",
            etapa_actual=EtapaProcesal.CALIFICACION_DEMANDA,
            estado_actual=EstadoProcesal.BORRADOR,
            fecha_presentacion_demanda=date(2026, 3, 2),
            juez_id=juez.id,
        )
        uow.session.add_all([juez, dte, caso])
        uow.session.flush()
        caso.intervenciones.append(
            CasoActor(caso_id=caso.id, actor_id=dte.id, rol_en_caso=RolActor.DEMANDANTE)
        )
        caso_id, actor_id = caso.id, dte.id

    # Alta desde borrador (Art. 37 CPCN) + verificación de la admisión
    # por auto iniciado del juez (Art. 148 CPCN):
    comando = {
        "caso_id": str(caso_id),
        "actor_id": str(actor_id),
        "rol_actor": "demandante",
        "materia": "cobro",
        "juzgado_asignado": "Juzgado 1 Civil",
        "fecha_presentacion": "2026-03-02",
        "hechos": "El demandado adeuda tres mensualidades del contrato de préstamo.",
        "pretensiones": [
            {
                "codigo_tipo": "cobro_de_dinero",
                "descripcion": "Condena al pago de C$ 50,000 con intereses legales.",
                "monto_pretendido": "50000.00",
                "es_principal": True,
            }
        ],
    }
    resp = client.post("/api/comandos/presentar-demanda", json=comando)
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert cuerpo["estado_resultante"] == "presentado"
    assert cuerpo["fundamento_legal"].startswith("Arts. 37")

    # Y la ADMISIÓN por auto iniciado del juez (Art. 148 CPCN):
    decision = contenedor.flow_engine.can_transition(
        caso_id=caso_id,
        estado_actual=EstadoProcesal.PRESENTADO,
        disparador=Disparador.DEMANDA_ADMITIDA,
        rol_actor=RolActor.JUEZ,
        plazos=[],
        ahora=contenedor.clock.now(),
    )
    assert decision.permitido and decision.estado_hacia is EstadoProcesal.ADMITIDA


# ============================================ 2. CONTESTACIÓN FUERA DE PLAZO


def test_contestar_fuera_de_plazo_es_rechazado_409(
    client, contenedor, clock, uow_factory
):
    """Preclusión Art. 134 CPCN: contestar después del traslado ⇒ 409."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.ADMITIDA)
    computo = contenedor.servicio_plazos().calcular_vencimiento(
        date(2026, 3, 2), 10, TipoPlazo.PRECLUSIVO
    )
    contenedor.registro_plazos.abrir(ids["caso"], "contestacion_demanda", computo)

    cmd = ContestarDemandaCommand(
        caso_id=ids["caso"],
        actor_id=ids["demandado"],
        rol_actor=RolActor.DEMANDADO,
        oferta_probatoria="Documental: contrato autenticado.",
    )
    # Dentro del plazo: OK (sube a contestada).
    clock.advance_to(datetime(2026, 3, 5, 9, 0, tzinfo=UTC))
    resultado = contenedor.handler_contestar.manejar(cmd)
    assert resultado.estado_resultante == "contestada"

    # Rebobinar para probar el vencimiento: caso de nuevo en admitida.
    ids2 = _semilla(uow_factory, estado=EstadoProcesal.ADMITIDA)
    contenedor.registro_plazos.abrir(ids2["caso"], "contestacion_demanda", computo)
    clock.advance_to(computo.vencimiento_datetime.replace(microsecond=0))
    clock.advance_by(timedelta(seconds=1))
    cmd2 = ContestarDemandaCommand(
        caso_id=ids2["caso"],
        actor_id=ids2["demandado"],
        rol_actor=RolActor.DEMANDADO,
        oferta_probatoria="Documental: contrato autenticado.",
    )
    resp = client.post(
        "/api/comandos/contestar-demanda", json=cmd2.model_dump(mode="json")
    )
    assert resp.status_code == 409
    assert "precluid" in resp.json()["detalle"] or "venció" in resp.json()["detalle"]


# =========================================== 3. SENTENCIA + AUDITORÍA JURÍDICA


def test_dictar_sentencia_emite_evento_con_fundamento_legal(
    client, contenedor, clock, uow_factory
):
    """Arts. 192-201 CPCN: sentencia estimatoria ⇒ log con fundamento (Art. 197)."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.EN_TRAMITE)
    cmd = DictarSentenciaCommand(
        caso_id=ids["caso"],
        actor_id=ids["juez"],
        rol_actor=RolActor.JUEZ,
        numero_resolucion="SL-001-2026",
        resumen="Valoradas las pruebas, la relación contractual quedó acreditada.",
        parte_resolutiva="POR TANTO: Se declara con lugar la demanda de desalojo.",
        fallos={ids["pretension"]: SentidoFallo.CON_LUGAR},
    )
    resp = client.post(
        "/api/comandos/dictar-sentencia", json=cmd.model_dump(mode="json")
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado_resultante"] == "sentenciado"

    historial = client.get(f"/api/casos/{ids['caso']}/historial").json()
    entrada = next(e for e in historial if e["accion"] == "emision_resolucion")
    assert "192" in entrada["fundamento_legal"]
    assert entrada["estado_antes"] == "en_tramite"
    assert entrada["estado_despues"] == "sentenciado"
    assert entrada["detalle"]["acto"] == "dictar_sentencia"


def test_sentencia_incongruente_es_rechazada_400(contenedor, uow_factory):
    """Art. 197 CPCN: omitir una pretensión ⇒ 400 (incongruencia negativa)."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.EN_TRAMITE)
    cmd = DictarSentenciaCommand(
        caso_id=ids["caso"],
        actor_id=ids["juez"],
        rol_actor=RolActor.JUEZ,
        numero_resolucion="SL-002-2026",
        resumen="Considerandos varios de la sentencia impugnada.",
        parte_resolutiva="POR TANTO: se resuelve lo pertinente.",
        fallos={uuid.uuid4(): SentidoFallo.SIN_LUGAR},  # pretensión ajena
    )
    with pytest.raises(Exception) as exc_info:
        contenedor.handler_sentenciar.manejar(cmd)
    assert exc_info.value.status_code == 400


# ======================================= 4. REBELDÍA AUTOMÁTICA (FakeClock)


def test_rebeldia_al_vencer_contestacion_y_bloquea_facultad(
    contenedor, clock, uow_factory
):
    """Arts. 151/153 CPCN: vencido el traslado sin escrito ⇒ rebeldía (log)."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.ADMITIDA)
    servicio = contenedor.servicio_plazos(auditoria=_AuditoriaUoW(contenedor))
    computo = servicio.calcular_vencimiento(date(2026, 3, 2), 10, TipoPlazo.PRECLUSIVO)
    plazo = contenedor.registro_plazos.abrir(
        ids["caso"], "contestacion_demanda", computo
    )

    clock.advance_to(computo.vencimiento_datetime.replace(microsecond=0))
    clock.advance_by(timedelta(seconds=1))
    eventos = servicio.procesar_vencimientos(
        contenedor.registro_plazos.plazos_de(ids["caso"])
    )
    assert eventos == [EventoVencimiento.REBELDIA]

    # Efecto preclusivo: la contestación tardía ya no es admisible (Art. 134).
    decision = contenedor.flow_engine.can_transition(
        caso_id=ids["caso"],
        estado_actual=EstadoProcesal.ADMITIDA,
        disparador=Disparador.CONTESTAR_DEMANDA,
        rol_actor=RolActor.DEMANDADO,
        plazos=[plazo],
        ahora=clock.now(),
    )
    assert not decision.permitido and "precluido" in decision.motivo


class _AuditoriaUoW:
    """Adaptador AuditoriaWriter → LogAuditoria sobre el contenedor."""

    def __init__(self, contenedor: ContenedorDependencias) -> None:
        self._contenedor = contenedor

    def registrar(
        self, *, caso_id, accion, entidad_afectada, registro_id, detalle, timestamp
    ):
        with self._contenedor.uow_factory() as uow:
            uow.registrar_auditoria(
                caso_id=caso_id,
                accion=accion,
                entidad_afectada=entidad_afectada,
                registro_id=registro_id,
                actor_id=None,
                estado_antes=None,
                estado_despues=None,
                detalle={**detalle, "timestamp": timestamp.isoformat()},
            )


# ================================================================ 5. RBAC


def test_demandado_no_puede_dictar_sentencia_403(client, uow_factory):
    """RBAC del motor: solo JUEZ dicta; partes ⇒ 403 (Art. 192 CPCN)."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.EN_TRAMITE)
    cmd = DictarSentenciaCommand(
        caso_id=ids["caso"],
        actor_id=ids["demandado"],
        rol_actor=RolActor.DEMANDADO,
        numero_resolucion="SL-999",
        resumen="Sentencia arbitraria dictada por el demandado.",
        parte_resolutiva="POR TANTO: nada.",
        fallos={ids["pretension"]: SentidoFallo.CON_LUGAR},
    )
    resp = client.post(
        "/api/comandos/dictar-sentencia", json=cmd.model_dump(mode="json")
    )
    assert resp.status_code == 403


def test_apelar_dentro_del_quinto_dia_y_preclusion_posterior(
    contenedor, clock, uow_factory
):
    """Arts. 246-248 CPCN: apelación tempestiva OK; tardía ⇒ facultad precluida."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.SENTENCIADO)
    computo = contenedor.servicio_plazos().calcular_vencimiento(
        date(2026, 3, 2), 5, TipoPlazo.PRECLUSIVO
    )
    contenedor.registro_plazos.abrir(ids["caso"], "termino_apelacion", computo)
    clock.advance_to(datetime(2026, 3, 9, 10, 0, tzinfo=UTC))
    cmd = ApelarSentenciaCommand(
        caso_id=ids["caso"],
        actor_id=ids["demandado"],
        rol_actor=RolActor.DEMANDADO,
        agravios="La sentencia ignora prueba documental esencial del proceso.",
        petitorio="Se revoque y declare sin lugar la demanda.",
    )
    resultado = contenedor.handler_apelar.manejar(cmd)
    assert resultado.estado_resultante == "en_recurso"

    # Nuevo caso sentenciado sin plazo vigente (vencido/interrumpido):
    ids2 = _semilla(uow_factory, estado=EstadoProcesal.SENTENCIADO)
    plazo_vencido = nuevo_plazo(ids2["caso"], "termino_apelacion", computo)
    from app.services.plazo_service import EstadoPlazo

    plazo_vencido.estado = EstadoPlazo.VENCIDO
    decision = contenedor.flow_engine.can_transition(
        caso_id=ids2["caso"],
        estado_actual=EstadoProcesal.SENTENCIADO,
        disparador=Disparador.APELAR_SENTENCIA,
        rol_actor=RolActor.DEMANDADO,
        plazos=[plazo_vencido],
        ahora=clock.now(),
    )
    assert not decision.permitido


def test_ejecucion_sobre_sentencia_no_firme_es_409(contenedor, uow_factory):
    """Art. 258 CPCN: sin ejecutoria no hay título ejecutivo ⇒ conflicto 409."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.SENTENCIADO)
    cmd = EjecutarSentenciaCommand(
        caso_id=ids["caso"],
        actor_id=ids["demandante"],
        rol_actor=RolActor.DEMANDANTE,
        pretension_ejecutada_id=ids["pretension"],
        forma_de_apereo="Lanzamiento y entrega material.",
    )
    with pytest.raises(Exception) as exc_info:
        contenedor.handler_ejecutar.manejar(cmd)
    assert exc_info.value.status_code == 409


def test_ejecucion_sobre_sentencia_firme_procede(contenedor, uow_factory):
    """Arts. 258/263 CPCN: con ejecutoria y condena estimatoria, el apremio avanza."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.FIRME)
    with SqlAlchemyUnitOfWork(contenedor.uow_factory) as uow:
        pret = uow.session.get(Pretension, ids["pretension"])
        pret.resuelta = True
        pret.sentido_fallo = SentidoFallo.CON_LUGAR
    cmd = EjecutarSentenciaCommand(
        caso_id=ids["caso"],
        actor_id=ids["demandante"],
        rol_actor=RolActor.DEMANDANTE,
        pretension_ejecutada_id=ids["pretension"],
        forma_de_apereo="Embargo de bienes.",
    )
    resultado = contenedor.handler_ejecutar.manejar(cmd)
    assert resultado.estado_resultante == "en_ejecucion"


# ========================================================= 6. QUERY SIDE


def test_queries_de_lectura_y_anonimizacion(client, uow_factory, contenedor):
    """GET casos/historial/plazos y vista pública sin datos personales."""
    ids = _semilla(uow_factory, estado=EstadoProcesal.EN_TRAMITE)
    caso = client.get(f"/api/casos/{ids['caso']}").json()
    assert caso["caso"]["estado_actual"] == "en_tramite"
    assert caso["pretensiones"][0]["codigo_tipo"] == "desalojo"

    computo = contenedor.servicio_plazos().calcular_vencimiento(
        date(2026, 3, 2), 10, TipoPlazo.NO_PRECLUSIVO
    )
    contenedor.registro_plazos.abrir(ids["caso"], "periodo_de_prueba", computo)
    plazos = client.get(f"/api/casos/{ids['caso']}/plazos").json()
    assert plazos[0]["nombre"] == "periodo_de_prueba"
    assert plazos[0]["dias_habiles"] == 10

    vacio = client.get(f"/api/casos/{uuid.uuid4()}/historial").json()
    assert vacio == []
    assert client.get(f"/api/casos/{uuid.uuid4()}").status_code == 404

    sim = client.get("/api/publico/simulaciones").json()
    assert all("SIM-" in s["numero_expediente_anonimizado"] for s in sim)
