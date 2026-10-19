#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JUSTICIA-DT Nicaragua — Motor de Gemelo Digital para análisis de escenarios
en juicios civiles según la pretensión (Ley 902, Código Civil de Nicaragua).

Implementa los 9 módulos del documento metodológico:
  M1 Selección de pretensión | M2 Registro de caso | M3 Viabilidad
  M4 Simulación de escenarios | M5 Predicción de duración | M6 Resultados
  M7 Detección de anomalías | M8 Dashboard | M9 Informe de resultados

Solo usa la biblioteca estándar de Python (portable Windows/Linux/macOS).
Ejecutar:  python app.py
"""

import hashlib
import json
import math
import os
import random
from datetime import datetime

# ----------------------------------------------------------------------------
# Catálogo de pretensiones (§1.1, §1.2 y §7.2 del documento)
# ----------------------------------------------------------------------------
PRETENSIONES = {
    "declarativa": {
        "nombre": "Declarativa",
        "descripcion": "Busca que se declare la existencia o inexistencia de un derecho.",
        "fundamento": "Arts. 2895 y ss. CC; Arts. 900 y ss. CC (usucapión)",
        "duracion_base_meses": 8,
        "rango_meses": (6, 12),
        "complejidad": "Alta",
        "subtipos": ["nulidad", "usucapion", "prescripcion", "reivindicacion", "servidumbres"],
        "requisitos": ["interes_legitimo", "falta_de_prescripcion", "validez_del_acto"],
        "pruebas": ["documental", "testimonial", "pericial"],
        "escenarios": ["allanamiento", "excepciones_previas", "apelacion"],
        "etapas": ["Demanda", "Contestación", "Audiencia Inicial",
                   "Audiencia Probatoria", "Sentencia", "(Apelación)"],
        "modelo_ia": "Clasificación binaria (procede/no procede)",
        "palabras_clave": ["nulidad", "usucapión", "usucapion", "declaración", "declare",
                           "inexistencia", "prescripción adquisitiva", "reivindicación"],
    },
    "constitutiva": {
        "nombre": "Constitutiva",
        "descripcion": "Crea, modifica o extingue una relación jurídica.",
        "fundamento": "Art. 2455 CC (resolución); Family Code (divorcio)",
        "duracion_base_meses": 12,
        "rango_meses": (8, 18),
        "complejidad": "Media-Alta",
        "subtipos": ["divorcio", "resolucion_contrato", "division_bienes", "nulidad_matrimonio"],
        "requisitos": ["causales", "gravedad", "imputabilidad"],
        "pruebas": ["documental", "testimonial", "pericial"],
        "escenarios": ["allanamiento", "reconvencion", "acuerdo"],
        "etapas": ["Demanda", "Contestación", "Audiencia Inicial",
                   "Audiencia Probatoria", "Sentencia Constitutiva"],
        "modelo_ia": "Clasificación multiclase",
        "palabras_clave": ["divorcio", "resolución de contrato", "resolucion", "disolución",
                           "extingir", "modificar la relación"],
    },
    "de_condena": {
        "nombre": "De condena",
        "descripcion": "Busca condenar al demandado a dar, hacer o no hacer.",
        "fundamento": "Arts. 2440, 2498 y ss., 2500 y ss. CC",
        "duracion_base_meses": 10,
        "rango_meses": (6, 15),
        "complejidad": "Media-Alta",
        "subtipos": ["incumplimiento", "cobro_pesos", "danos_perjuicios",
                     "responsabilidad_civil", "arrendamiento", "compraventa"],
        "requisitos": ["obligacion", "incumplimiento", "nexo_causal"],
        "pruebas": ["documental", "pericial", "testimonial"],
        "escenarios": ["allanamiento", "excepciones_previas", "reconvencion",
                       "apelacion", "ejecucion"],
        "etapas": ["Demanda", "Contestación", "Audiencia Inicial",
                   "Audiencia Probatoria", "Sentencia", "Ejecución"],
        "modelo_ia": "Regresión + clasificación (éxito + cuantía)",
        "palabras_clave": ["condena", "pague", "daños y perjuicios", "incumplimiento",
                           "cobro", "indemnización", "cumplimiento del contrato"],
    },
    "ejecutiva": {
        "nombre": "Ejecutiva",
        "descripcion": "Busca ejecutar un título ejecutivo.",
        "fundamento": "Títulos ejecutivos: pagaré, letra de cambio, hipoteca (Ley 902 Libro IV)",
        "duracion_base_meses": 5,
        "rango_meses": (3, 8),
        "complejidad": "Baja",
        "subtipos": ["pagare", "letra_cambio", "hipoteca", "sentencia_firme"],
        "requisitos": ["titulo_ejecutivo", "liquidez", "exigibilidad"],
        "pruebas": ["documental"],
        "escenarios": ["oposicion", "embargo", "remate", "pago"],
        "etapas": ["Demanda", "Mandamiento de Ejecución", "Embargo", "Remate", "Pago"],
        "modelo_ia": "Clasificación binaria",
        "palabras_clave": ["pagaré", "pagare", "letra de cambio", "ejecución", "título ejecutivo",
                           "hipoteca", "remate"],
    },
    "cautelar": {
        "nombre": "Cautelar",
        "descripcion": "Busca asegurar bienes o derechos durante el proceso.",
        "fundamento": "Medidas cautelares Ley 902 (embargo, secuestro, anotación preventiva)",
        "duracion_base_meses": 2,
        "rango_meses": (1, 3),
        "complejidad": "Baja-Media",
        "subtipos": ["embargo", "secuestro", "anotacion_preventiva"],
        "requisitos": ["peligro_demora", "apariencia_buen_derecho", "contracautela"],
        "pruebas": ["documental", "testimonial"],
        "escenarios": ["admision", "rechazo", "sustitucion", "caucion"],
        "etapas": ["Solicitud", "Admisión", "Ejecución de la Medida", "(Proceso principal)"],
        "modelo_ia": "Clasificación binaria",
        "palabras_clave": ["embargo", "secuestro", "anotación preventiva", "medida cautelar",
                           "asegurar bienes"],
    },
    "probatoria": {
        "nombre": "Probatoria",
        "descripcion": "Busca anticipar o asegurar prueba.",
        "fundamento": "Diligencias preliminares / prueba anticipada Ley 902",
        "duracion_base_meses": 1,
        "rango_meses": (1, 2),
        "complejidad": "Baja",
        "subtipos": ["inspeccion_judicial", "testimonio_anticipado", "pericial_anticipada"],
        "requisitos": ["urgencia", "relevancia", "imposibilidad_posterior"],
        "pruebas": ["documental", "testimonial", "pericial"],
        "escenarios": ["admision", "rechazo", "produccion"],
        "etapas": ["Solicitud", "Admisión", "Producción de Prueba"],
        "modelo_ia": "Clasificación binaria",
        "palabras_clave": ["prueba anticipada", "inspección judicial", "testigo anticipado",
                           "asegurar prueba"],
    },
}

# Subtipos comunes con su pretensión madre (§1.2)
SUBTIPO_A_PRETENSION = {
    "incumplimiento": "de_condena", "cobro_pesos": "de_condena",
    "danos_perjuicios": "de_condena", "responsabilidad_civil": "de_condena",
    "arrendamiento": "de_condena", "compraventa": "de_condena",
    "nulidad": "declarativa", "usucapion": "declarativa", "prescripcion": "declarativa",
    "reivindicacion": "declarativa", "servidumbres": "declarativa",
    "divorcio": "constitutiva", "resolucion_contrato": "constitutiva",
    "division_bienes": "constitutiva", "nulidad_matrimonio": "constitutiva",
    "pagare": "ejecutiva", "letra_cambio": "ejecutiva", "hipoteca": "ejecutiva",
    "sentencia_firme": "ejecutiva",
    "embargo": "cautelar", "secuestro": "cautelar", "anotacion_preventiva": "cautelar",
    "inspeccion_judicial": "probatoria", "testimonio_anticipado": "probatoria",
    "pericial_anticipada": "probatoria",
}

# Multiplicadores de escenario sobre el caso base (§5.2)
ESCENARIOS = {
    "base":                 {"factor_exito": 1.00, "factor_duracion": 1.00, "factor_costo": 1.00},
    "allanamiento":         {"factor_exito": 1.30, "factor_duracion": 0.38, "factor_costo": 0.42},
    "acuerdo_conciliatorio":{"factor_exito": 1.18, "factor_duracion": 0.45, "factor_costo": 0.55},
    "reconvencion":         {"factor_exito": 0.86, "factor_duracion": 1.50, "factor_costo": 1.60},
    "excepciones_previas":  {"factor_exito": 0.92, "factor_duracion": 1.25, "factor_costo": 1.30},
    "prorroga":             {"factor_exito": 0.96, "factor_duracion": 1.20, "factor_costo": 1.10},
    "apelacion":            {"factor_exito": 0.78, "factor_duracion": 2.25, "factor_costo": 2.40},
    "incidente_probatorio": {"factor_exito": 0.90, "factor_duracion": 1.35, "factor_costo": 1.45},
    "recusacion":           {"factor_exito": 0.88, "factor_duracion": 1.30, "factor_costo": 1.25},
    "nulidad_actuaciones":  {"factor_exito": 0.72, "factor_duracion": 1.80, "factor_costo": 1.90},
}

LISTA_ESCENARIOS = list(ESCENARIOS.keys())


def _rng_int(texto, mod):
    """Entero determinista derivado de SHA-256 (independiente de PYTHONHASHSEED)."""
    return int(hashlib.sha256(texto.encode("utf-8")).hexdigest(), 16) % mod


class NucleoDT:
    """Núcleo del gemelo digital: componentes C1..C5 (§6.1)."""

    # ---------------- C1: Clasificador de pretensión (NLP heurístico) --------
    @staticmethod
    def clasificar(texto_demanda):
        texto = (texto_demanda or "").lower()
        puntajes = {}
        for clave, p in PRETENSIONES.items():
            s = 0.0
            for kw in p["palabras_clave"]:
                if kw.lower() in texto:
                    s += 1.0
            for st in p["subtipos"]:
                if st.replace("_", " ") in texto or st in texto:
                    s += 0.5
            puntajes[clave] = s
        mejor = max(puntajes, key=puntajes.get) if puntajes else None
        total = sum(puntajes.values()) or 1.0
        conf = round(min(0.99, 0.5 + 0.5 * (puntajes.get(mejor, 0) / total)), 2) \
            if puntajes.get(mejor, 0) > 0 else 0.3
        subtipo = None
        for st, pref in SUBTIPO_A_PRETENSION.items():
            if pref == mejor and (st.replace("_", " ") in texto or st in texto):
                subtipo = st
                break
        return {"pretension": mejor, "subtipo": subtipo, "confianza": conf}

    # ---------------- C4: IA predictiva — distribución Beta truncada ---------
    @staticmethod
    def simular_exito(p_base, n=400, semilla=""):
        """Monte Carlo determinista: éxito ~ Beta(a,b) centrado en p_base."""
        rng = random.Random("exito:" + semilla)
        a, b = max(0.5, p_base * 8), max(0.5, (1 - p_base) * 8)
        muestras = [min(0.99, max(0.01, rng.betavariate(a, b))) for _ in range(n)]
        return sum(muestras) / len(muestras)

    @staticmethod
    def simular_duracion(meses_base, n=400, semilla=""):
        """Duración ~ Gamma(mu=meses_base, k=6): cola derecha moderada."""
        rng = random.Random("dur:" + semilla)
        k = 6.0
        muestras = [rng.gammavariate(k, meses_base / k) for _ in range(n)]
        return sum(muestras) / len(muestras)


class Justiciable:
    pass


class JusticiaDT:
    """Orquesta los 9 módulos y el flujo de uso de 5 pasos (§3.3)."""

    def __init__(self):
        self.nucleo = NucleoDT()
        self.informes = {}

    # ------------------ M1 Selección de pretensión --------------------------
    def m1_seleccion(self, pretension=None, subtipo=None, texto_demanda=""):
        if not pretension and texto_demanda:
            auto = self.nucleo.clasificar(texto_demanda)
            pretension, subtipo = auto["pretension"], auto.get("subtipo") or subtipo
        if pretension not in PRETENSIONES:
            raise ValueError(f"Pretensión inválida: {pretension}. "
                             f"Válidas: {', '.join(PRETENSIONES)}")
        p = PRETENSIONES[pretension]
        if subtipo and subtipo not in p["subtipos"]:
            subtipo = p["subtipos"][0]
        return {"tipo": pretension, "nombre": p["nombre"],
                "subtipo": subtipo or p["subtipos"][0],
                "requisitos": p["requisitos"], "escenarios_aplicables": LISTA_ESCENARIOS}

    # ------------------ M2 Registro de caso ----------------------------------
    def m2_registro(self, sel, datos):
        requeridos = ["demandante", "demandado", "cuantia_usd", "juzgado"]
        faltan = [c for c in requeridos if not datos.get(c)]
        if faltan:
            raise ValueError("Faltan campos: " + ", ".join(faltan))
        cuantia = float(datos["cuantia_usd"])
        if cuantia <= 0:
            raise ValueError("La cuantía debe ser mayor que cero.")
        expediente = "NIC-2026-%05d" % _rng_int(
            f"{sel['tipo']}|{datos['demandante']}|{datos['demandado']}|{cuantia}", 99999)
        canon = json.dumps({"exp": expediente, **{k: str(v) for k, v in datos.items()}},
                           sort_keys=True, ensure_ascii=False)
        hash_int = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
        caso = {"expediente": expediente, "hash_integridad": hash_int,
                "pretension": sel["tipo"], "subtipo": sel["subtipo"],
                "demandante": datos["demandante"], "demandado": datos["demandado"],
                "cuantia_usd": cuantia, "juzgado": datos["juzgado"],
                "pruebas": datos.get("pruebas", ["documental"]),
                "hechos": datos.get("hechos", ""),
                "fecha_registro": datetime.now().isoformat(timespec="seconds")}
        return caso

    # ------------------ M3 Análisis de viabilidad ----------------------------
    def m3_viabilidad(self, caso):
        p = PRETENSIONES[caso["pretension"]]
        pruebas_ok = len(set(p["pruebas"]) & set(caso["pruebas"])) / max(1, len(p["pruebas"]))
        tiene_hechos = 1.0 if len(caso.get("hechos", "")) >= 20 else 0.5
        complejidad_pen = {"Baja": 0.05, "Media": 0.0, "Media-Alta": -0.03,
                           "Alta": -0.05, "Baja-Media": 0.02}.get(p["complejidad"], 0.0)
        viab = round(min(1.0, max(0.05, 0.35 + 0.30 * pruebas_ok + 0.20 * tiene_hechos
                                  + 0.10 + complejidad_pen)), 2)
        veredicto = "Viable" if viab >= 0.6 else ("Viable con observaciones" if viab >= 0.4
                                                  else "Riesgo alto")
        obstaculos = []
        if pruebas_ok < 1:
            obstaculos.append("Faltan medios de prueba sugeridos: "
                              + ", ".join(set(p["pruebas"]) - set(caso["pruebas"])))
        if p["complejidad"] in ("Alta", "Media-Alta"):
            obstaculos.append(f"Complejidad {p['complejidad']}: mayor riesgo de incidencias.")
        return {"score": viab, "veredicto": veredicto, "obstaculos": obstaculos,
                "requisitos_a_acreditar": p["requisitos"]}

    # ------------------ M4 Simulación de escenarios (what-if) ----------------
    def m4_escenarios(self, caso, viab):
        p = PRETENSIONES[caso["pretension"]]
        meses_base = p["duracion_base_meses"]
        costo_base = round(500 + 0.10 * min(caso["cuantia_usd"], 100000)
                           + 400 * meses_base, -1)
        sem = caso["expediente"] + "|" + caso["subtipo"]
        out = []
        for esc, f in ESCENARIOS.items():
            p_base = min(0.95, max(0.05, viab["score"] * f["factor_exito"]))
            exito = self.nucleo.simular_exito(p_base, semilla=sem + esc)
            meses = self.nucleo.simular_duracion(meses_base * f["factor_duracion"],
                                                 semilla=sem + esc)
            costo = costo_base * f["factor_costo"] * (0.9 + 0.2 * (meses / meses_base) / 2)
            out.append({"escenario": esc,
                        "exito_pct": round(exito * 100),
                        "meses": round(meses, 1),
                        "costo_usd": round(costo),
                        "nota": ("Estrategia recomendada" if esc == "allanamiento" else
                                 "Alternativa transaccional" if esc == "acuerdo_conciliatorio" else
                                 "Evitar si es posible" if f["factor_duracion"] >= 1.5 else
                                 "Escenario estándar" if esc == "base" else "Incidencia probable")})
        out.sort(key=lambda x: (-x["exito_pct"], x["meses"]))
        return out, {"meses_base": meses_base, "costo_base_usd": costo_base}

    # ------------------ M5 Predicción de duración por etapa ------------------
    def m5_duracion(self, caso):
        p = PRETENSIONES[caso["pretension"]]
        etapas = [e for e in p["etapas"] if not e.startswith("(")]
        pesos = [0.10, 0.15, 0.15, 0.35, 0.15, 0.10][:len(etapas)]
        s = sum(pesos)
        pesos = [w / s for w in pesos]
        sem = random.Random("etapas:" + caso["expediente"])
        filas, total = [], 0.0
        for nombre, w in zip(etapas, pesos):
            m = round(p["duracion_base_meses"] * w * sem.uniform(0.92, 1.08) * 2) / 2
            filas.append({"etapa": nombre, "meses": m})
            total += m
        return {"etapas": filas, "total_meses": round(total, 1),
                "rango_esperado_meses": p["rango_meses"]}

    # ------------------ M6 Predicción de resultados --------------------------
    def m6_resultados(self, caso, escenarios):
        mejor = escenarios[0]
        base = next((e for e in escenarios if e["escenario"] == "base"), mejor)
        return {"mejor_escenario": mejor, "escenario_base": base,
                "probabilidad_condenada": base["exito_pct"] / 100.0,
                "modelo_ia": PRETENSIONES[caso["pretension"]]["modelo_ia"]}

    # ------------------ M7 Detección de anomalías ----------------------------
    def m7_anomalias(self, caso, dur, traza_real=None):
        alertas = []
        esperado = dur["total_meses"]
        if traza_real:
            for i, (etapa, real) in enumerate(traza_real):
                ref = dur["etapas"][i]["meses"] if i < len(dur["etapas"]) else esperado / len(dur["etapas"])
                if real > ref * 2:
                    alertas.append({"nivel": "rojo", "tipo": "retraso",
                                    "detalle": f"'{etapa}' tardó {real} m (>2σ vs {ref} m esperados)"})
                elif real > ref * 1.5:
                    alertas.append({"nivel": "amarillo", "tipo": "desviacion",
                                    "detalle": f"'{etapa}' tardó {real} m (>1.5σ vs {ref} m)"})
        p = PRETENSIONES[caso["pretension"]]
        if p["complejidad"] in ("Alta", "Media-Alta"):
            alertas.append({"nivel": "amarillo", "tipo": "riesgo_estructural",
                            "detalle": f"Complejidad {p['complejidad']}: vigilar plazos procesales."})
        nivel = "rojo" if any(a["nivel"] == "rojo" for a in alertas) else \
                ("amarillo" if alertas else "verde")
        return {"nivel": nivel, "alertas": alertas}

    # ------------------ M9 Informe de resultados ------------------------------
    def m9_informe(self, caso, viab, escenarios, dur, res, anom):
        mejor = res["mejor_escenario"]
        rec = (f"Para la pretensión de {caso['subtipo'].replace('_',' ')}, se recomienda explorar "
               f"el escenario '{mejor['escenario']}' (éxito {mejor['exito_pct']}%, "
               f"{mejor['meses']} meses, USD {mejor['costo_usd']:,}). Evite generar incidencias "
               f"que prolonguen el juicio; la pretensión es sólida siempre que se acrediten los "
               f"requisitos: {', '.join(viab['requisitos_a_acreditar'])}.")
        informe = {
            "expediente": caso["expediente"], "hash_integridad": caso["hash_integridad"],
            "caso": caso, "viabilidad": viab, "escenarios": escenarios,
            "duracion_por_etapa": dur, "prediccion_resultado": res,
            "anomalias": anom, "recomendacion": rec,
            "nota_legal": ("Herramienta de apoyo basada en datos sintéticos (Fase 1 hoja de ruta). "
                           "No sustituye el criterio profesional del abogado/notario."),
            "generado": datetime.now().isoformat(timespec="seconds"),
        }
        self.informes[caso["expediente"]] = informe
        return informe

    # ------------------ Orquestación: flujo completo (§3.3) -------------------
    def flujo_completo(self, pretension, subtipo, datos, traza_real=None):
        sel = self.m1_seleccion(pretension, subtipo)          # Paso 1
        caso = self.m2_registro(sel, datos)                    # Paso 2
        viab = self.m3_viabilidad(caso)                        # Paso 3
        esc, params = self.m4_escenarios(caso, viab)           # Paso 4
        dur = self.m5_duracion(caso)                           # Paso 4/5
        res = self.m6_resultados(caso, esc)                    # Paso 5
        anom = self.m7_anomalias(caso, dur, traza_real)        # Paso 5
        inf = self.m9_informe(caso, viab, esc, dur, res, anom) # Paso 5
        inf["params_escenario"] = params
        return inf


# ----------------------------------------------------------------------------
# M8: Dashboard de consola
# ----------------------------------------------------------------------------
def dashboard(inf):
    c = inf["caso"]
    L = "=" * 72
    print(L)
    print(f"JUSTICIA-DT NICARAGUA — Dashboard | Expediente {c['expediente']} | "
          f"Hash {c['hash_integridad']}")
    print(f"Pretensión: {PRETENSIONES[c['pretension']]['nombre']} ({c['subtipo']}) | "
          f"Juzgado: {c['juzgado']} | Cuantía: USD {c['cuantia_usd']:,.0f}")
    print("-" * 72)
    print("Duración estimada por etapa:")
    for e in inf["duracion_por_etapa"]["etapas"]:
        print(f"  • {e['etapa']:<28} {e['meses']:>4.1f} meses")
    print(f"  TOTAL: {inf['duracion_por_etapa']['total_meses']} meses")
    print("Escenarios (éxito / meses / costo USD):")
    for s in inf["escenarios"]:
        print(f"  • {s['escenario']:<24} {s['exito_pct']:>3}%  "
              f"{s['meses']:>5.1f} m  USD {s['costo_usd']:>8,}")
    print(f"Nivel de alertas: {inf['anomalias']['nivel']} "
          f"({len(inf['anomalias']['alertas'])} alertas)")
    print(L)
    print("\n--- RECOMENDACIÓN DEL DT ---")
    print(inf["recomendacion"] + "\n")


def demo_incumplimiento_contrato():
    """Ejemplo concreto §5: Empresa A vs B, incumplimiento, USD 50,000."""
    dt = JusticiaDT()
    inf = dt.flujo_completo(
        "de_condena", "incumplimiento",
        {"demandante": "Empresa A", "demandado": "Empresa B",
         "cuantia_usd": 50000, "juzgado": "Civil de Managua",
         "pruebas": ["documental", "testimonial", "pericial"],
         "hechos": "Falta de pago por prestación de servicios conforme al contrato suscrito."})
    dashboard(inf)
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "informe_demo.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(inf, f, ensure_ascii=False, indent=2)
    print("Informe completo guardado en", ruta)
    return inf


if __name__ == "__main__":
    demo_incumplimiento_contrato()
