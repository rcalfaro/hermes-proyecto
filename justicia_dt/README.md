# JUSTICIA-DT Nicaragua — Aplicación (Módulo por Pretensión)

Implementación funcional de la aplicación **JUSTICIA-DT Nicaragua** descrita en
la sección 3 del documento *Metodología, Aplicación y Modelo de Gemelo Digital
para Análisis de Escenarios en Juicios Civiles según la Pretensión* (Ley 902 y
Código Civil de Nicaragua). Datos sintéticos — Fase 1 de la hoja de ruta
(desarrollo ético y legal).

## Ejecución

```bash
python justicia_dt/app.py        # demo: incumplimiento de contrato (Empresa A vs B, USD 50,000)
```

Salida: dashboard (M8) + recomendación estratégica e informe JSON (M9) en
`justicia_dt/informe_demo.json`.

## Arquitectura

```
UI/Dashboard (M8) ── API REST/JSON (FastAPI) ── Núcleo DT híbrido (5 componentes)
M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9
Sincronización: MQTT/Kafka · Firma electrónica: Ley 729 · Trazabilidad: SHA-256
```

**Núcleo DT (clase `NucleoDT`) — modelo híbrido:**
- C1 Clasificador de pretensión (NLP por palabras clave;→ Random Forest/BERT en producción)
- C2 Process Mining (conformance checking del flujo por pretensión)
- C3 Simulación de eventos (Monte Carlo beta/gauss sembrado; → SimPy/Salabim)
- C4 IA predictiva (duración por etapa + anomalías >2σ; → LSTM/XGBoost)
- C5 Grafo de conocimiento (nodos partes/pretensión/normas; → Neo4j)

## Los 9 módulos

| Módulo | Clase | Funcionalidad |
|---|---|---|
| M1 Selección de pretensión | `Modulo1_SeleccionPretension` | Clasifica tipo/subtipo (manual o desde texto de demanda) |
| M2 Registro de caso | `Modulo2_RegistroCaso` | Valida y crea el expediente digital (`Caso`, con hash de integridad) |
| M3 Análisis de viabilidad | `Modulo3_AnalisisViabilidad` | Score de viabilidad, veredicto, duración esperada y obstáculos |
| M4 Simulación de escenarios | `Modulo4_SimulacionEscenarios` | What-if: base, allanamiento, reconvención, excepciones previas, prórroga, acuerdo conciliatorio, apelación, incidente probatorio, recusación, nulidad |
| M5 Predicción de duración | `Modulo5_PrediccionDuracion` | Duración estimada por etapa procesal según pretensión |
| M6 Predicción de resultados | `Modulo6_PrediccionResultados` | Probabilidad de éxito del escenario base y ranking de escenarios |
| M7 Detección de anomalías | `Modulo7_DeteccionAnomalias` | Alertas de desviación de flujo y retrasos (>2σ), nivel verde/amarillo/rojo |
| M8 Dashboard de seguimiento | `Modulo8_DashboardSeguimiento` | Vista consolidada del estado del expediente |
| M9 Informe de resultados | `Modulo9_InformeResultados` | Reporte final JSON con recomendación estratégica |

## Flujo de uso (Pasos 1–5)

Orquestado por `JusticiaDT.flujo_completo()`:

1. **Paso 1** — El abogado selecciona la pretensión (M1): tipo (declarativa,
   constitutiva, de condena, ejecutiva, cautelar, probatoria) y subtipo
   (incumplimiento, nulidad, daños y perjuicios, cobro de pesos, usucapión…).
2. **Paso 2** — Ingresa los datos del caso (M2): partes, hechos, fundamentos
   jurídicos, cuantía, juzgado, pruebas.
3. **Paso 3** — El DT analiza viabilidad según pretensión (M3): comparación con
   estándares históricos, requisitos, obstáculos.
4. **Paso 4** — Simulación de escenarios what-if (M4) + predicción de duración
   (M5), de resultados (M6) y detección de anomalías (M7).
5. **Paso 5** — Dashboard (M8) e informe con recomendación estratégica (M9).

## Uso programático

```python
from justicia_dt.app import JusticiaDT

app = JusticiaDT(seed=902)
salida = app.flujo_completo(
    seleccion={"pretension": "de_condena", "subtipo": "incumplimiento"},
    datos_caso={
        "demandante": "Empresa A", "demandado": "Empresa B",
        "hechos": "Contrato de prestación de servicios incumplido por falta de pago.",
        "fundamentos_juridicos": "Arts. 2440 y siguientes CC.",
        "cuantia_usd": 50000, "juzgado": "Civil de Managua",
        "pruebas": ["contrato", "facturas", "correos"],
    },
)
print(salida["dashboard"])          # M8
print(salida["informe"]["recomendacion"])  # M9
```

> **Nota legal:** análisis orientativo generado con datos sintéticos; no
> sustituye el criterio profesional del abogado o notario.
