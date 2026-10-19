# ⚖️ JUSTICIA-DT Nicaragua

Gemelo Digital para análisis de escenarios en juicios civiles según la pretensión
(Ley 902 — Código Civil de Nicaragua). Dirigido a abogados y notarios públicos.

## Estructura del proyecto (`justicia_dt/`)

| Archivo | Descripción |
|---|---|
| `app.py` | Motor del DT (módulos M1–M9). Solo biblioteca estándar de Python. |
| `server.py` | API REST **FastAPI** + servidor del dashboard. |
| `index.html` | Dashboard gráfico autocontenido (4 pestañas; motor JS espejo offline). |
| `requirements.txt` | Dependencias: fastapi, uvicorn[standard], pydantic. |
| `exportar_html.py` | Regenera `demo_embebida.json` con resultados del motor Python. |
| `informe_demo.json` | Informe §5 generado por `app.py`. |
| `__init__.py` | Marca el paquete. |

## Uso rápido (Windows 11)

### Opción A — Sin dependencias (consola)
```powershell
cd C:\ruta\justicia_dt
py app.py            # o: python app.py
```
Imprime el dashboard M8 y guarda `informe_demo.json` junto al script.

### Opción B — Dashboard offline
Doble clic en `index.html`, o desde PowerShell: `start index.html`.
La pestaña **📝 Nuevo Caso** calcula viabilidad, escenarios, duración y
recomendación íntegramente en el navegador (sin servidor).

### Opción C — Servidor FastAPI (API REST completa)
```powershell
py -m pip install -r requirements.txt
py server.py
```
- Dashboard: http://127.0.0.1:8000/
- Swagger:  http://127.0.0.1:8000/docs
- Salud:    http://127.0.0.1:8000/api/salud

> Nota: si `py -3` da "no such option: -3", use `py` o `python` a secas.

## API REST (mapeo módulos §3.2)

| Endpoint | Módulo | Función |
|---|---|---|
| `GET /` | M8 | Dashboard HTML |
| `GET /api/salud` | — | Estado del gemelo digital |
| `GET /api/catalogo` | M1 | Pretensiones Ley 902, subtipos, escenarios |
| `POST /api/clasificar` | M1/C1 | NLP: texto de demanda → pretensión/subtipo |
| `POST /api/caso` | M2 | Registro + expediente con hash SHA-256 |
| `POST /api/viabilidad` | M3 | Evaluación preliminar |
| `POST /api/escenarios` | M4 | Monte Carlo what-if (10 escenarios) |
| `POST /api/duracion` | M5 | Duración por etapa procesal |
| `POST /api/resultados` | M6 | Probabilidad de éxito + ranking |
| `POST /api/anomalias` | M7 | Alertas sobre traza real (>1.5σ amarillo, >2σ rojo) |
| `POST /api/flujo_completo` | M1→M9 | Flujo de uso §3.3 (Pasos 1–5) en un llamado |
| `GET /api/informe/{expediente}` | M9 | Informe final almacenado |

Ejemplo con PowerShell:
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/flujo_completo -Method Post -ContentType "application/json" -Body '{"pretension":"de_condena","subtipo":"incumplimiento","demandante":"Empresa A","demandado":"Empresa B","cuantia_usd":50000,"juzgado":"Civil de Managua","pruebas":["documental","testimonial","pericial"],"hechos":"Falta de pago por prestación de servicios conforme al contrato suscrito."}'
```

## Modelo (§4) y datos sintéticos
Cada pretensión tiene su propio modelo (objetivo, variables clave, modelo IA,
duración base y escenarios). Los resultados usan simulación Monte Carlo
determinista (Beta/Gamma), calibrada a la tabla §5.2 del documento.

**Nota legal:** herramienta de apoyo en Fase 1 (datos sintéticos); no sustituye
el criterio profesional del abogado/notario. La transición a datos reales
requiere convenio con la CSJ y anonimización (hoja de ruta §9).
