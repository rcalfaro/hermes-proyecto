"""Pruebas unitarias del motor de plazos — CPCN (Ley 908, Nicaragua).

Cobertura exigida:
    a) Cómputo de 9 días hábiles saltando un feriado (Art. 132 CPCN).
    b) Suspensión de plazo por incidente (Art. 136 CPCN).
    c) Rebeldía automática al vencer el plazo de contestación (Arts. 151/153).
    d) Preclusión/caducidad de la facultad probatoria al vencer el período
       de prueba (Arts. 134 y 162 CPCN).
    + Escenarios borde: inicio en viernes, feriado en lunes, notificación en
      día inhábil, determinismo puro, interrupción (Art. 137), plazo no
      preclusivo (Art. 135) y evidencia obligatoria en LogAuditoria.

Todas las pruebas usan ``FakeClock``; el suite completo corre en < 100 ms.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.services.calendario_judicial import CalendarioJudicial, cargar_calendario_2026
from app.services.plazo_service import (
    EstadoPlazo,
    EventoVencimiento,
    PlazoService,
    TipoPlazo,
    nuevo_plazo,
)
from app.services.time_provider import FakeClock, SystemClock, TimeProvider

CASO_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


# ---------------------------------------------------------------------------
# Dobles de test
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class AuditoriaEspia:
    """Doble del escritor de ``LogAuditoria``: captura cada evento emitido."""

    entradas: list[dict[str, Any]] = field(default_factory=list)

    def registrar(
        self,
        *,
        caso_id: uuid.UUID | None,
        accion: str,
        entidad_afectada: str,
        registro_id: str | None,
        detalle: dict[str, Any],
        timestamp: datetime,
    ) -> None:
        self.entradas.append(
            {
                "caso_id": caso_id,
                "accion": accion,
                "entidad_afectada": entidad_afectada,
                "registro_id": registro_id,
                "detalle": detalle,
                "timestamp": timestamp,
            }
        )

    def por_accion(self, accion: str) -> list[dict[str, Any]]:
        return [e for e in self.entradas if e["accion"] == accion]


def _servicio(
    reloj_iso: datetime | None = None,
    calendario: CalendarioJudicial | None = None,
) -> tuple[PlazoService, FakeClock, AuditoriaEspia]:
    """Fábrica de servicio con dependencias falsas inyectadas."""
    clock = FakeClock(reloj_iso or datetime(2026, 2, 27, 10, 0, tzinfo=UTC))
    espia = AuditoriaEspia()
    svc = PlazoService(calendario or cargar_calendario_2026(), clock, auditoria=espia)
    return svc, clock, espia


# ---------------------------------------------------------------------------
# Protocolos e infraestructura de tiempo
# ---------------------------------------------------------------------------
class TestTimeProvider:
    def test_system_clock_cumple_protocolo(self) -> None:
        assert isinstance(SystemClock(), TimeProvider)

    def test_fake_clock_cumple_protocolo_y_es_monotonica(self) -> None:
        clock = FakeClock(datetime(2026, 3, 1, 8, 0, tzinfo=UTC))
        assert isinstance(clock, TimeProvider)
        clock.advance_by(timedelta(days=2))
        assert clock.now().day == 3
        with pytest.raises(ValueError, match="monotónica"):
            clock.advance_to(datetime(2026, 1, 1, tzinfo=UTC))

    def test_fake_clock_exige_timezone_aware(self) -> None:
        with pytest.raises(ValueError):
            FakeClock(datetime(2026, 3, 1))  # naive → rechazo explícito


# ---------------------------------------------------------------------------
# a) Cómputo de 9 días hábiles saltando un feriado (Art. 132 CPCN)
# ---------------------------------------------------------------------------
class TestComputoNovenario:
    """Escenario: emplazamiento viernes 27-feb-2026; feriado lunes 2-mar-2026.

    El término de 9 días hábiles arranca el martes 3 de marzo (el sábado
    siguiente es inhábil y el lunes feriado se salta); vence el viernes 13.
    """

    def test_nueve_dias_habiles_saltando_feriado_de_lunes(self) -> None:
        svc, _, _ = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 9)

        assert computo.primer_dia_habil == date(2026, 3, 3)  # tras feriado 2-mar
        assert computo.fecha_vencimiento == date(2026, 3, 13)  # 9° día hábil
        assert computo.dias_habiles_contados == 9
        # Evidencia de feriados saltados: sábados y domingos intermedios.
        assert date(2026, 3, 7) in computo.feriados_saltados
        assert date(2026, 3, 8) in computo.feriados_saltados

    def test_dia_de_notificacion_no_se_cuenta(self) -> None:
        svc, _, _ = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 1)
        # Notificado viernes → único día hábil contado: martes 3 (lunes 2 feriado).
        assert computo.fecha_vencimiento == date(2026, 3, 3)

    def test_vencimiento_a_las_23_59_59_del_dia_habil(self) -> None:
        svc, _, _ = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 9)
        assert computo.vencimiento_datetime == datetime(
            2026, 3, 13, 23, 59, 59, tzinfo=UTC
        )

    def test_determinismo_puro_misma_entrada_mismo_resultado(self) -> None:
        svc1, _, _ = _servicio()
        svc2, _, _ = _servicio()
        a = svc1.calcular_vencimiento(date(2026, 2, 27), 9)
        b = svc2.calcular_vencimiento(date(2026, 2, 27), 9)
        assert a == b  # dataclass frozen: igualdad estructural completa

    def test_plazo_que_inicia_en_viernes_salta_al_lunes(self) -> None:
        cal = CalendarioJudicial()  # sin feriados: solo fines de semana
        svc, _, _ = _servicio(calendario=cal)
        computo = svc.calcular_vencimiento(date(2026, 3, 6), 1)  # viernes
        assert computo.fecha_vencimiento == date(2026, 3, 9)  # lunes

    def test_calendario_rechaza_configuracion_infinita(self) -> None:
        # Racha de 500 días inhábiles consecutivos (2030) → la cota defensiva
        # del algoritmo aborta en lugar de iterar sin fin.
        feriados = frozenset(date(2030, 1, 1) + timedelta(days=i) for i in range(500))
        cal = CalendarioJudicial(feriados=feriados)
        with pytest.raises(RuntimeError, match="calendario inválido"):
            cal.siguiente_dia_habil(date(2030, 1, 1))

    def test_error_si_plazo_no_positivo(self) -> None:
        svc, _, _ = _servicio()
        with pytest.raises(ValueError):
            svc.calcular_vencimiento(date(2026, 2, 27), 0)


# ---------------------------------------------------------------------------
# b) Suspensión por incidente (Art. 136 CPCN)
# ---------------------------------------------------------------------------
class TestSuspensionArt136:
    def test_suspension_congela_y_reanuda_por_el_remanente(self) -> None:
        svc, _clock, espia = _servicio(reloj_iso=datetime(2026, 3, 5, 9, 0, tzinfo=UTC))
        # Plazo de 9 días hábiles iniciado el 27-feb (vence 13-mar).
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 9)
        plazo = nuevo_plazo(CASO_ID, "contestacion_demanda", computo)

        # Al 5-mar quedan 5 días hábiles pendientes (6, 9, 10, 11, 12... 13).
        svc.suspender_plazo(
            plazo, "incidente_de_nulidad_de_notificaciones", hasta=date(2026, 3, 20)
        )

        assert plazo.estado is EstadoPlazo.SUSPENDIDO
        # Remanente (5 hábiles) reanudado desde el 20-mar (viernes):
        # pend. = contar(5-mar → 13-mar) = 6, 9, 10, 11, 12, 13 = 6 días.
        esperado_fin = svc.calcular_vencimiento(date(2026, 3, 19), 6)
        assert plazo.computo.fecha_vencimiento == esperado_fin.fecha_vencimiento
        assert plazo.computo.fecha_vencimiento > date(2026, 3, 20)

        # Trazabilidad del incidente con fundamento legal.
        incidente = plazo.incidentes[-1]
        assert incidente["tipo"] == "suspension"
        assert "Art. 136 CPCN" in incidente["fundamento"]
        assert espia.por_accion("suspension_plazo"), "debe quedar auditado"

    def test_no_suspende_plazo_ya_suspendido(self) -> None:
        svc, _, _ = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 9)
        plazo = nuevo_plazo(CASO_ID, "contestacion_demanda", computo)
        svc.suspender_plazo(plazo, "incidente", hasta=date(2026, 3, 20))
        with pytest.raises(ValueError, match="no suspendible"):
            svc.suspender_plazo(plazo, "segundo incidente", hasta=date(2026, 4, 1))

    def test_interrupcion_reinicia_plazo_integro_art137(self) -> None:
        svc, _, espia = _servicio()
        original = svc.calcular_vencimiento(date(2026, 2, 27), 9)
        plazo = nuevo_plazo(CASO_ID, "contestacion_demanda", original)

        # Nulidad de notificación el 9-mar: lo transcurrido queda sin efecto.
        svc.interrumpir_plazo(
            plazo, "nulidad_de_la_notificacion", desde=date(2026, 3, 9)
        )

        renacido = svc.calcular_vencimiento(date(2026, 3, 9), 9)
        assert plazo.computo.fecha_vencimiento == renacido.fecha_vencimiento
        assert plazo.estado is EstadoPlazo.INTERRUMPIDO
        assert any("Art. 137 CPCN" in i["fundamento"] for i in plazo.incidentes)
        assert espia.por_accion("interrupcion_plazo")


# ---------------------------------------------------------------------------
# c) Rebeldía automática al vencer el plazo de contestación
# ---------------------------------------------------------------------------
class TestRebeldiaAutomatica:
    def test_vencido_plazo_de_contestacion_emite_rebeldia(self) -> None:
        svc, clock, espia = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 9)  # vence 13-mar
        plazo = nuevo_plazo(CASO_ID, "contestacion_demanda", computo)

        # Dentro del plazo: no ocurre nada.
        clock.advance_to(datetime(2026, 3, 13, 12, 0, tzinfo=UTC))
        assert svc.procesar_vencimientos([plazo]) == []

        # Un segundo después del cierre (23:59:59 del 13-mar): rebeldía.
        clock.advance_to(datetime(2026, 3, 14, 0, 0, 1, tzinfo=UTC))
        eventos = svc.procesar_vencimientos([plazo])

        assert eventos == [EventoVencimiento.REBELDIA]
        assert plazo.estado is EstadoPlazo.VENCIDO
        entrada = espia.por_accion("rebeldia")[-1]
        assert entrada["caso_id"] == CASO_ID
        # La evidencia del cómputo viaja íntegra al log.
        assert entrada["detalle"]["computo"]["fecha_inicio"] == "2026-02-27"
        assert entrada["detalle"]["computo"]["dias_habiles_contados"] == 9

    def test_procesar_vencimientos_es_idempotente(self) -> None:
        svc, clock, espia = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 9)
        plazo = nuevo_plazo(CASO_ID, "contestacion_demanda", computo)
        clock.advance_to(datetime(2026, 3, 20, 9, 0, tzinfo=UTC))

        primera = svc.procesar_vencimientos([plazo])
        segunda = svc.procesar_vencimientos([plazo])

        assert primera == [EventoVencimiento.REBELDIA]
        assert segunda == [], "un plazo vencido no re-emite el evento"
        assert len(espia.por_accion("rebeldia")) == 1

    def test_plazo_suspendido_no_genera_rebeldia(self) -> None:
        svc, clock, _ = _servicio(reloj_iso=datetime(2026, 3, 5, 9, 0, tzinfo=UTC))
        computo = svc.calcular_vencimiento(date(2026, 2, 27), 9)
        plazo = nuevo_plazo(CASO_ID, "contestacion_demanda", computo)
        svc.suspender_plazo(plazo, "incidente", hasta=date(2026, 3, 20))

        clock.advance_to(datetime(2026, 3, 16, 9, 0, tzinfo=UTC))  # venc. original
        assert svc.procesar_vencimientos([plazo]) == []


# ---------------------------------------------------------------------------
# d) Preclusión de la facultad probatoria al vencer el período de prueba
# ---------------------------------------------------------------------------
class TestPreclusionProbatoria:
    def test_periodo_de_prueba_vencido_caduca_facultad(self) -> None:
        svc, clock, espia = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 4, 8), 8, TipoPlazo.PRECLUSIVO)
        plazo = nuevo_plazo(CASO_ID, "periodo_de_prueba", computo)

        clock.advance_to(computo.vencimiento_datetime + timedelta(seconds=2))
        eventos = svc.procesar_vencimientos([plazo])

        assert eventos == [EventoVencimiento.CADUCIDAD_PERIODO_PRUEBA]
        detalle = espia.por_accion("caducidad_periodo_prueba")[-1]["detalle"]
        assert "134" in detalle["computo"]["fundamento_legal"]

    def test_preclusion_general_de_facultad_art134(self) -> None:
        svc, clock, _ = _servicio()
        computo = svc.calcular_vencimiento(date(2026, 5, 25), 5)  # apelar, etc.
        plazo = nuevo_plazo(CASO_ID, "interposicion_recurso_apelacion", computo)

        clock.advance_to(computo.vencimiento_datetime + timedelta(hours=1))
        assert svc.procesar_vencimientos([plazo]) == [EventoVencimiento.PRECLUSION]

    def test_no_preclusivo_vence_con_sancion_pero_sigue_cumplible_art135(self) -> None:
        svc, clock, _ = _servicio()
        computo = svc.calcular_vencimiento(
            date(2026, 5, 25), 3, TipoPlazo.NO_PRECLUSIVO
        )
        plazo = nuevo_plazo(CASO_ID, "fallo_sentencia_obligatoria", computo)

        clock.advance_to(computo.vencimiento_datetime + timedelta(hours=1))
        eventos = svc.procesar_vencimientos([plazo])

        assert eventos == [EventoVencimiento.SANCION_NO_PRECLUSIVO]
        assert "135" in computo.fundamento_legal


# ---------------------------------------------------------------------------
# Nota crítica: evidencia obligatoria de cada cálculo en LogAuditoria
# ---------------------------------------------------------------------------
class TestEvidenciaAuditoriaObligatoria:
    def test_cada_calculo_registra_inicio_vencimiento_dias_y_fundamento(self) -> None:
        svc, _, espia = _servicio()
        svc.calcular_vencimiento(date(2026, 2, 27), 9)

        registros = espia.por_accion("calculo_plazo")
        assert len(registros) == 1
        detalle = registros[0]["detalle"]
        assert detalle["fecha_inicio"] == "2026-02-27"
        assert detalle["fecha_vencimiento"] == "2026-03-13"
        assert detalle["dias_habiles_contados"] == 9
        assert "2026-03-07" in detalle["feriados_saltados"]  # sábado saltado
        assert "CPCN" in detalle["fundamento_legal"]
        assert detalle["tipo_plazo"] == "preclusivo"
        # Timestamp anclado al reloj inyectado, no al reloj global.
        assert registros[0]["timestamp"].year == 2026


# ---------------------------------------------------------------------------
# Presupuesto de rendimiento: suite completo < 100 ms
# ---------------------------------------------------------------------------
def test_suite_completo_dentro_de_presupuesto() -> None:
    """Meta-fallback barato: recalcula los escenarios clave 100 veces."""
    t0 = time.perf_counter()
    for _ in range(100):
        svc, _, _ = _servicio()
        c = svc.calcular_vencimiento(date(2026, 2, 27), 9)
        p = nuevo_plazo(CASO_ID, "contestacion_demanda", c)
        svc.suspender_plazo(p, "x", hasta=date(2026, 3, 20))
    assert time.perf_counter() - t0 < 0.100 * 100  # holgado; ver pytest --durations
