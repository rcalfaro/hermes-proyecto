"""
JUSTICIA-DT Nicaragua — Aplicación de Gemelo Digital para Análisis de
Escenarios en Juicios Civiles según la Pretensión.

Dirigida a Abogados y Notarios Públicos de la República de Nicaragua.

Arquitectura: 9 módulos (M1..M9) + Núcleo DT (motor híbrido de 5 componentes).
Datos: sintéticos (Fase 1 de la hoja de ruta — desarrollo ético y legal).

Ejecutar demo:  python justicia_dt/app.py
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Catálogo jurídico: pretensiones según Ley 902 (CPC Nicaragua) y Código Civil
# ---------------------------------------------------------------------------

PRETENSIONES = {
    "declarativa": {
        "nombre": "Declarativa",
        "descripcion": "Busca que se declare la existencia o inexistencia de un derecho.",
        "duracion_tipica_meses": (6, 12),
        "subtipos": ["nulidad", "usucapion", "prescripcion"],
        "requisitos": ["interes_legitimo", "falta_de_prescripcion"],
        "pruebas": ["documental", "testimonial", "pericial"],
        "duracion_base": 8,
        "escenarios": ["allanamiento", "excepciones", "apelacion"],
    },
    "constitutiva": {
        "nombre": "Constitutiva",
        "descripcion": "Crea, modifica o extingue una relación jurídica.",
        "duracion_tipica_meses": (8, 18),
        "subtipos": ["divorcio", "resolucion_contrato", "nulidad_matrimonio"],
        "requisitos": ["causales", "gravedad", "imputabilidad"],
        "pruebas": ["documental", "testimonial", "pericial"],
        "duracion_base": 12,
        "escenarios": ["allanamiento", "reconvencion", "acuerdo"],
    },
    "de_condena": {
        "nombre": "De condena",
        "descripcion": "Busca que se condene al demandado a dar, hacer o no hacer.",
        "duracion_tipica_meses": (6, 15),
        "subtipos": ["cobro_pesos", "danos_perjuicios", "incumplimiento"],
        "requisitos": ["obligacion", "incumplimiento", "nexo_causal"],
        "pruebas": ["documental", "pericial", "testimonial"],
        "duracion_base": 10,
        "escenarios": ["allanamiento", "excepciones", "apelacion", "ejecucion"],
    },
    "ejecutiva": {
        "nombre": "Ejecutiva",
        "descripcion": "Busca ejecutar un título ejecutivo.",
        "duracion_tipica_meses": (3, 8),
        "subtipos": ["pagare", "letra_cambio", "hipoteca"],
        "requisitos": ["titulo_ejecutivo", "liquidez", "exigibilidad"],
        "pruebas": ["documental"],
        "duracion_base": 5,
        "escenarios": ["oposicion", "embargo", "remate", "pago"],
    },
    "cautelar": {
        "nombre": "Cautelar",
        "descripcion": "Busca asegurar bienes o derechos durante el proceso.",
        "duracion_tipica_meses": (1, 3),
        "subtipos": ["embargo", "secuestro", "anotacion"],
        "requisitos": ["peligro_demora", "apariencia_buen_derecho"],
        "pruebas": ["documental", "testimonial"],
        "duracion_base": 2,
        "escenarios": ["admision", "rechazo", "sustitucion"],
    },
    "probatoria": {
        "nombre": "Probatoria",
        "descripcion": "Busca anticipar o asegurar prueba.",
        "duracion_tipica_meses": (1, 2),
        "subtipos": ["inspeccion", "testimonio_anticipado", "pericial"],
        "requisitos": ["urgencia", "relevancia", "imposibilidad"],
        "pruebas": ["documental", "testimonial", "pericial"],
        "duracion_base": 1,
        "escenarios": ["admision", "rechazo", "produccion"],
    },
}

# Subtipo -> pretensión principal (apoyo del clasificador, M1)
SUBTIPO_A_PRETENSION = {
    "incumplimiento": "de_condena",
    "resolucion_contrato": "constitutiva",
    "nulidad": "declarativa",
    "danos_perjuicios": "de_condena",
    "reivindicacion": "declarativa",
    "usucapion": "declarativa",
    "division_bienes": "declarativa",
    "cobro_pesos": "de_condena",
    "responsabilidad_civil": "de_condena",
    "arrendamiento": "de_condena",
    "compraventa": "de_condena",
    "hipoteca": "ejecutiva",
    "servidumbres": "declarativa",
    "divorcio": "constitutiva",
    "pagare": "ejecutiva",
    "letra_cambio": "ejecutiva",
    "embargo": "cautelar",
    "secuestro": "cautelar",
    "anotacion": "cautelar",
    "inspeccion": "probatoria",
    "testimonio_anticipado": "probatoria",
}

# Etapas procesales por pretensión (flujo del proceso — Fase de Diseño DT-PRET)
FLUJO_ETAPAS = {
    "declarativa": ["Demanda", "Contestación", "Audiencia Inicial",
                    "Audiencia Probatoria", "Sentencia", "(Apelación)"],
    "constitutiva": ["Demanda", "Contestación", "Audiencia Inicial",
                     "Audiencia Probatoria", "Sentencia", "(Apelación)"],
    "de_condena": ["Demanda", "Contestación", "Audiencia Inicial",
                   "Audiencia Probatoria", "Sentencia", "Ejecución"],
    "ejecutiva": ["Demanda", "Mandamiento de Ejecución", "Embargo",
                  "Remate", "Pago"],
    "cautelar": ["Solicitud", "Admisión", "Medida", "(Proceso principal)"],
    "probatoria": ["Solicitud", "Admisión", "Producción de prueba"],
}

# Escenarios what-if del módulo de simulación (M4)
ESCENARIOS = {
    # nombre: (factor_prob_exito, factor_duracion, factor_costo)
    "base": (1.00, 1.00, 1.00),
    "allanamiento": (1.35, 0.38, 0.42),
    "reconvencion": (0.86, 1.50, 1.60),
    "excepciones_previas": (0.93, 1.25, 1.30),
    "prorroga": (0.98, 1.20, 1.10),
    "acuerdo_conciliatorio": (1.22, 0.45, 0.55),
    "apelacion": (0.79, 2.25, 2.40),
    "incidente_probatorio": (0.90, 1.35, 1.45),
    "recusacion": (0.88, 1.30, 1.25),
    "nulidad_actuaciones": (0.70, 1.80, 1.90),
}


# ---------------------------------------------------------------------------
# Estructuras de datos compartidas (contrato entre módulos)
# ---------------------------------------------------------------------------

@dataclass
class Caso:
    """Expediente digital del caso (salida del Módulo 2)."""
    id: str
    pretension: str                 # clave de PRETENSIONES
    subtipo: str
    demandante: str
    demandado: str
    hechos: str
    fundamentos_juridicos: str
    cuantia_usd: float
    juzgado: str
    pruebas: list
    fecha_registro: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def hash(self) -> str:
        """Huella de integridad (trazabilidad tipo blockchain-lite)."""
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class ResultadoEscenario:
    escenario: str
    probabilidad_exito: float   # 0..1
    duracion_meses: float
    costo_usd: float
    descripcion: str


# ---------------------------------------------------------------------------
# Núcleo DT — Modelo híbrido por pretensión (5 componentes)
# ---------------------------------------------------------------------------

class NucleoDT:
    """Motor híbrido: C1 Clasificador, C2 Process Mining, C3 Simulación,
    C4 IA predictiva, C5 Grafos de conocimiento.

    Nota metodológica: en Fase 1 (datos sintéticos) los modelos se aproximan
    con heurísticas deterministas + Monte Carlo sembrado (reproducibilidad).
    En Fase 3 se sustituirán por LSTM/XGBoost entrenados con datos anonimizados.
    """

    def __init__(self, seed: int = 902):
        self.seed = seed

    # -- Componente 1: Clasificador de pretensión --------------------------
    def clasificar_pretension(self, texto: str) -> dict:
        """NLP simplificado: identifica tipo y subtipo desde el texto de la demanda."""
        t = (texto or "").lower()
        palabras_clave = {
            "declarativa": ["declare", "nulidad", "usucapión", "usucapion", "prescripción", "propiedad"],
            "constitutiva": ["divorcio", "resolución", "resolucion", "extinga", "disuelva"],
            "de_condena": ["condene", "pague", "cumplimiento", "incumplimiento", "daños", "danos", "indemnización"],
            "ejecutiva": ["pagaré", "pagare", "letra de cambio", "título ejecutivo", "titulo ejecutivo", "ejecute"],
            "cautelar": ["embargo", "secuestro", "anotación preventiva", "medida cautelar"],
            "probatoria": ["anticipo", "inspección judicial", "testimonio anticipado"],
        }
        puntajes = {tipo: sum(1 for kw in kws if kw in t) for tipo, kws in palabras_clave.items()}
        mejor = max(puntajes, key=puntajes.get)
        if puntajes[mejor] == 0:
            mejor = "de_condena"
        subtipo_detectado = next(
            (s for s in SUBTIPO_A_PRETENSION if s.replace("_", " ") in t or s in t),
            PRETENSIONES[mejor]["subtipos"][0],
        )
        return {
            "pretension": mejor,
            "subtipo": subtipo_detectado,
            "confianza": round(min(0.5 + 0.15 * puntajes[mejor], 0.95), 2),
            "requisitos_aplicables": PRETENSIONES[mejor]["requisitos"],
        }

    # -- Componente 2: Process Mining (descubrimiento de flujo) ------------
    def flujo_por_pretension(self, pretension: str) -> list:
        return FLUJO_ETAPAS.get(pretension, FLUJO_ETAPAS["declarativa"])

    def detectar_desviaciones(self, historial_etapas: list, pretension: str) -> list:
        """Conformance checking: traza real vs. modelo esperado por pretensión."""
        esperado = self.flujo_por_pretension(pretension)
        desviaciones = []
        for etapa in historial_etapas:
            if etapa not in esperado:
                desviaciones.append(f"Etapa fuera de flujo estándar: {etapa}")
        faltantes = [e for e in esperado if e not in historial_etapas and not e.startswith("(")]
        for e in faltantes:
            desviaciones.append(f"Etapa esperada no ejecutada: {e}")
        return desviaciones

    # -- Componente 3: Simulación de eventos (Monte Carlo) -----------------
    def _beta_sample(self, rng: random.Random, a: float, b: float) -> float:
        x = rng.gammavariate(a, 1.0)
        y = rng.gammavariate(b, 1.0)
        return x / (x + y) if (x + y) > 0 else 0.5

    def simular_escenario(self, caso: Caso, escenario: str, n: int = 2000) -> ResultadoEscenario:
        cat = PRETENSIONES[caso.pretension]
        f_p, f_d, f_c = ESCENARIOS[escenario]
        rng = random.Random(f"{self.seed}:{caso.id}:{escenario}")

        # Fortaleza base según cobertura de requisitos/pruebas
        score_pruebas = min(len(caso.pruebas) / max(len(cat["pruebas"]), 1), 1.0)
        exito_base = 0.45 + 0.25 * score_pruebas
        p_exito = min(max(exito_base * f_p, 0.02), 0.98)

        # Distribución beta centrada en p_exito -> probabilidad simulada
        muestras = [self._beta_sample(rng, 2 + 30 * p_exito, 2 + 30 * (1 - p_exito)) for _ in range(n)]
        prob_final = statistics.mean(muestras)

        dur_base = cat["duracion_base"] * f_d
        cost_base = max(800, min(caso.cuantia_usd * 0.10, 15000)) * f_c
        dur_media = statistics.mean([rng.gauss(dur_base, dur_base * 0.15) for _ in range(n)])
        cost_media = statistics.mean([rng.gauss(cost_base, cost_base * 0.12) for _ in range(n)])

        return ResultadoEscenario(
            escenario=escenario,
            probabilidad_exito=round(prob_final, 3),
            duracion_meses=round(max(0.5, dur_media), 1),
            costo_usd=round(max(500, cost_media)),
            descripcion=f"Simulación Monte Carlo ({n} iteraciones), escenario '{escenario}'.",
        )

    # -- Componente 4: IA predictiva (duración por etapa + anomalías) ------
    def predecir_duracion_etapas(self, caso: Caso) -> dict:
        cat = PRETENSIONES[caso.pretension]
        etapas = self.flujo_por_pretension(caso.pretension)
        pesos = [0.10, 0.15, 0.15, 0.35, 0.15, 0.10][: len(etapas)]
        total = sum(pesos)
        return {e: round(cat["duracion_base"] * w / total, 1) for e, w in zip(etapas, pesos)}

    def detectar_anomalias(self, dias_por_etapa: dict) -> list:
        """Alerta temprana: etapas que superan 2σ del promedio."""
        valores = list(dias_por_etapa.values())
        if len(valores) < 2:
            return []
        media = statistics.mean(valores)
        desv = statistics.pstdev(valores) or 1
        return [e for e, d in dias_por_etapa.items() if (d - media) / desv > 2]

    # -- Componente 5: Grafo de conocimiento -------------------------------
    def grafo_caso(self, caso: Caso) -> dict:
        cat = PRETENSIONES[caso.pretension]
        nodos = [
            {"id": caso.demandante, "tipo": "parte"},
            {"id": caso.demandado, "tipo": "parte"},
            {"id": cat["nombre"], "tipo": "pretension"},
            {"id": caso.subtipo, "tipo": "subtipo"},
            {"id": caso.juzgado, "tipo": "juzgado"},
        ]
        aristas = [
            {"origen": caso.demandante, "relacion": "demanda_a", "destino": caso.demandado},
            {"origen": caso.demandante, "relacion": "ejercita", "destino": cat["nombre"]},
            {"origen": cat["nombre"], "relacion": "subtipo", "destino": caso.subtipo},
            {"origen": caso.juzgado, "relacion": "conoce", "destino": caso.subtipo},
        ]
        for r in cat["requisitos"]:
            nodos.append({"id": r, "tipo": "requisito"})
            aristas.append({"origen": cat["nombre"], "relacion": "requiere", "destino": r})
        return {"nodos": nodos, "aristas": aristas}


# ===========================================================================
# MÓDULOS DE LA APLICACIÓN (M1 .. M9)
# ===========================================================================

class Modulo1_SeleccionPretension:
    """M1 — Selección de pretensión: clasificación tipo/subtipo."""

    def __init__(self, dt: NucleoDT):
        self.dt = dt

    def seleccionar(self, pretension: Optional[str] = None, subtipo: Optional[str] = None,
                    texto_demanda: Optional[str] = None) -> dict:
        if texto_demanda and not pretension:
            return self.dt.clasificar_pretension(texto_demanda)
        if pretension not in PRETENSIONES:
            raise ValueError(f"Pretensión inválida. Use: {list(PRETENSIONES)}")
        return {
            "pretension": pretension,
            "subtipo": subtipo or PRETENSIONES[pretension]["subtipos"][0],
            "confianza": 1.0,
            "requisitos_aplicables": PRETENSIONES[pretension]["requisitos"],
        }


class Modulo2_RegistroCaso:
    """M2 — Registro de caso: ingreso y validación de datos del expediente."""

    def registrar(self, pretension: str, subtipo: str, **datos) -> Caso:
        requeridos = ["demandante", "demandado", "cuantia_usd", "juzgado",
                      "hechos", "fundamentos_juridicos"]
        faltantes = [k for k in requeridos if k not in datos]
        if faltantes:
            raise ValueError(f"Campos faltantes: {faltantes}")
        if pretension not in PRETENSIONES:
            raise ValueError("Pretensión no catalogada (Ley 902).")
        if float(datos["cuantia_usd"]) <= 0:
            raise ValueError("La cuantía debe ser mayor que cero.")
        cid = f"NIC-{datetime.now().year}-{abs(hash(datos['hechos'])) % 100000:05d}"
        return Caso(
            id=cid, pretension=pretension, subtipo=subtipo,
            demandante=datos["demandante"], demandado=datos["demandado"],
            hechos=datos["hechos"], fundamentos_juridicos=datos["fundamentos_juridicos"],
            cuantia_usd=float(datos["cuantia_usd"]), juzgado=datos["juzgado"],
            pruebas=datos.get("pruebas", []),
        )


class Modulo3_AnalisisViabilidad:
    """M3 — Análisis de viabilidad: comparación con estándares de la pretensión."""

    def __init__(self, dt: NucleoDT):
        self.dt = dt

    def evaluar(self, caso: Caso) -> dict:
        cat = PRETENSIONES[caso.pretension]
        score_requisitos = 1.0  # con datos sintéticos se asume presentación formal correcta
        score_pruebas = min(len(caso.pruebas) / max(len(cat["pruebas"]), 1), 1.0)
        viabilidad = round(0.5 * score_requisitos + 0.5 * score_pruebas, 2)
        lo, hi = cat["duracion_tipica_meses"]
        obstaculos = []
        if score_pruebas < 0.5:
            obstaculos.append("Acervo probatorio insuficiente para el estándar de la pretensión.")
        if caso.cuantia_usd > 100000:
            obstaculos.append("Cuantía alta: mayor riesgo de reconvención y apelación.")
        return {
            "viabilidad": viabilidad,
            "veredicto": ("Viable" if viabilidad >= 0.6
                          else "Viable con reservas" if viabilidad >= 0.4
                          else "Riesgo alto"),
            "duracion_esperada_meses": f"{lo}-{hi}",
            "obstaculos": obstaculos,
            "requisitos_evaluados": cat["requisitos"],
        }


class Modulo4_SimulacionEscenarios:
    """M4 — Simulación de escenarios what-if por pretensión."""

    def __init__(self, dt: NucleoDT):
        self.dt = dt

    def simular(self, caso: Caso, escenarios: Optional[list] = None) -> list:
        esc = escenarios or list(ESCENARIOS)
        return [self.dt.simular_escenario(caso, e) for e in esc]


class Modulo5_PrediccionDuracion:
    """M5 — Predicción de duración por etapa."""

    def __init__(self, dt: NucleoDT):
        self.dt = dt

    def predecir(self, caso: Caso) -> dict:
        etapas = self.dt.predecir_duracion_etapas(caso)
        return {"etapas_meses": etapas,
                "total_meses": round(sum(etapas.values()), 1),
                "flujo_estandar": self.dt.flujo_por_pretension(caso.pretension)}


class Modulo6_PrediccionResultados:
    """M6 — Predicción de resultados: probabilidad de éxito global y ranking."""

    def predecir(self, caso: Caso, resultados: list) -> dict:
        base = next(r for r in resultados if r.escenario == "base")
        ranking = sorted(resultados, key=lambda r: (-r.probabilidad_exito, r.duracion_meses))
        return {
            "probabilidad_exito_base": base.probabilidad_exito,
            "mejor_escenario": ranking[0].escenario,
            "ranking": [(r.escenario, r.probabilidad_exito) for r in ranking],
        }


class Modulo7_DeteccionAnomalias:
    """M7 — Detección de anomalías: alertas tempranas de retraso/desviación."""

    def __init__(self, dt: NucleoDT):
        self.dt = dt

    def analizar(self, caso: Caso, traza_etapas: list, dias_por_etapa: dict) -> dict:
        desviaciones = self.dt.detectar_desviaciones(traza_etapas, caso.pretension)
        anomalias = self.dt.detectar_anomalias(dias_por_etapa)
        alertas = [{"tipo": "flujo", "mensaje": d} for d in desviaciones] + \
                  [{"tipo": "retraso", "mensaje": f"Retraso anómalo (>2σ) en: {a}"} for a in anomalias]
        nivel = "rojo" if len(alertas) > 2 else ("amarillo" if alertas else "verde")
        return {"alertas": alertas, "nivel": nivel}


class Modulo8_DashboardSeguimiento:
    """M8 — Dashboard de seguimiento: estado actual del expediente (vista texto)."""

    def render(self, caso: Caso, prediccion_duracion: dict, resultados: list,
               anomalias: dict) -> str:
        lineas = [
            "=" * 72,
            f"JUSTICIA-DT NICARAGUA — Dashboard | Expediente {caso.id} | Hash {caso.hash}",
            f"Pretensión: {PRETENSIONES[caso.pretension]['nombre']} ({caso.subtipo}) | "
            f"Juzgado: {caso.juzgado} | Cuantía: USD {caso.cuantia_usd:,.0f}",
            "-" * 72,
            "Duración estimada por etapa:",
        ]
        for e, m in prediccion_duracion["etapas_meses"].items():
            lineas.append(f"  • {e:<28} {m:>5} meses")
        lineas.append(f"  TOTAL: {prediccion_duracion['total_meses']} meses")
        lineas.append("Escenarios (éxito / meses / costo USD):")
        for r in sorted(resultados, key=lambda x: -x.probabilidad_exito):
            lineas.append(f"  • {r.escenario:<24} {r.probabilidad_exito:>6.0%} "
                          f"{r.duracion_meses:>6} m  USD {r.costo_usd:>9,.0f}")
        lineas.append(f"Nivel de alertas: {anomalias['nivel']} ({len(anomalias['alertas'])} alertas)")
        lineas.append("=" * 72)
        return "\n".join(lineas)


class Modulo9_InformeResultados:
    """M9 — Informe de resultados: reporte final con recomendación estratégica."""

    def generar(self, caso: Caso, viabilidad: dict, resultados: list,
                prediccion: dict, pred_resultados: dict, anomalias: dict) -> dict:
        # Mejor escenario: maximiza éxito ponderando rapidez y costo
        mejor = max(resultados, key=lambda r: r.probabilidad_exito / (r.duracion_meses * r.costo_usd) * 1e5)
        return {
            "expediente": caso.id,
            "hash_integridad": caso.hash,
            "generado": datetime.now().isoformat(timespec="seconds"),
            "caso": {"pretension": PRETENSIONES[caso.pretension]["nombre"],
                     "subtipo": caso.subtipo, "cuantia_usd": caso.cuantia_usd,
                     "juzgado": caso.juzgado},
            "viabilidad": viabilidad,
            "escenarios": [asdict(r) for r in resultados],
            "duracion_por_etapa": prediccion["etapas_meses"],
            "prediccion_resultado": pred_resultados,
            "anomalias": anomalias,
            "recomendacion": (
                f"Para la pretensión de {caso.subtipo}, se recomienda explorar el escenario "
                f"'{mejor.escenario}' (éxito {mejor.probabilidad_exito:.0%}, "
                f"{mejor.duracion_meses} meses, USD {mejor.costo_usd:,.0f}). "
                "Evite generar incidencias que prolonguen el juicio; la pretensión es sólida "
                "siempre que se acrediten los requisitos: "
                f"{', '.join(PRETENSIONES[caso.pretension]['requisitos'])}."
            ),
            "nota_legal": "Análisis orientativo con datos sintéticos (Fase 1). No sustituye el criterio profesional.",
        }


# ===========================================================================
# ORQUESTADOR — Arquitectura de la aplicación y flujo de uso (Pasos 1..5)
# ===========================================================================

class JusticiaDT:
    """Aplicación JUSTICIA-DT Nicaragua — Módulo por Pretensión.

    Arquitectura:
      UI/Dashboard (M8) ── API REST/JSON (FastAPI) ── Núcleo DT híbrido
      Cadena de módulos: M1→M2→M3→M4→M5→M6→M7→M8→M9
      Sincronización: MQTT/Kafka; firma electrónica Ley 729; trazabilidad SHA-256.
    """

    def __init__(self, seed: int = 902):
        self.dt = NucleoDT(seed=seed)
        self.m1 = Modulo1_SeleccionPretension(self.dt)
        self.m2 = Modulo2_RegistroCaso()
        self.m3 = Modulo3_AnalisisViabilidad(self.dt)
        self.m4 = Modulo4_SimulacionEscenarios(self.dt)
        self.m5 = Modulo5_PrediccionDuracion(self.dt)
        self.m6 = Modulo6_PrediccionResultados()
        self.m7 = Modulo7_DeteccionAnomalias(self.dt)
        self.m8 = Modulo8_DashboardSeguimiento()
        self.m9 = Modulo9_InformeResultados()

    def flujo_completo(self, seleccion: dict, datos_caso: dict,
                       traza_etapas: Optional[list] = None,
                       dias_por_etapa: Optional[dict] = None) -> dict:
        # PASO 1: selección de pretensión (M1)
        sel = self.m1.seleccionar(**seleccion)
        # PASO 2: registro de caso (M2)
        caso = self.m2.registrar(pretension=sel["pretension"], subtipo=sel["subtipo"], **datos_caso)
        # PASO 3: análisis de viabilidad según pretensión (M3)
        viab = self.m3.evaluar(caso)
        # PASO 4: simulación de escenarios (M4) + predicciones (M5, M6) + anomalías (M7)
        res = self.m4.simular(caso)
        pred = self.m5.predecir(caso)
        pr = self.m6.predecir(caso, res)
        ano = self.m7.analizar(
            caso,
            traza_etapas or pred["flujo_estandar"],
            dias_por_etapa or {e: int(m * 30) for e, m in pred["etapas_meses"].items()},
        )
        # PASO 5: dashboard (M8) e informe final (M9)
        dashboard = self.m8.render(caso, pred, res, ano)
        informe = self.m9.generar(caso, viab, res, pred, pr, ano)
        return {"caso": caso, "viabilidad": viab, "resultados": res,
                "prediccion_duracion": pred, "prediccion_resultado": pr,
                "anomalias": ano, "dashboard": dashboard, "informe": informe}


def demo_incumplimiento_contrato():
    """Ejemplo concreto §5 del documento: Empresa A vs Empresa B, USD 50,000."""
    app = JusticiaDT()
    salida = app.flujo_completo(
        seleccion={"pretension": "de_condena", "subtipo": "incumplimiento"},
        datos_caso={
            "demandante": "Empresa A", "demandado": "Empresa B",
            "hechos": "Contrato de prestación de servicios incumplido por falta de pago.",
            "fundamentos_juridicos": "Arts. 2440 y siguientes CC (incumplimiento contractual).",
            "cuantia_usd": 50000, "juzgado": "Civil de Managua",
            "pruebas": ["contrato", "facturas", "correos"],
        },
    )
    print(salida["dashboard"])
    print("\n--- RECOMENDACIÓN DEL DT ---")
    print(salida["informe"]["recomendacion"])
    with open("justicia_dt/informe_demo.json", "w", encoding="utf-8") as f:
        json.dump(salida["informe"], f, ensure_ascii=False, indent=2, default=str)
    print("\nInforme completo guardado en justicia_dt/informe_demo.json")
    return salida


if __name__ == "__main__":
    demo_incumplimiento_contrato()
