# Gobernanza de la IA — Gemelo Digital del Proceso Civil (Nicaragua)

**Versión:** 1.0 · **Fecha:** 2026-10-19 · **Alcance:** módulos `app/analytics/`, `app/nlp/`, `app/api/insights_endpoints.py`

> ⚖️ Principio matriz: **la IA apoya, el humano decide.** El `CaseFlowEngine` + `config/flow_reglas.yaml` siguen siendo la única fuente de verdad legal. Ninguna salida de IA habilita, bloquea ni ejecuta un acto procesal.

---

## 1. Límites de uso (lo que la IA NUNCA hace)

| # | Prohibición | Mecanismo técnico que la garantiza |
|---|-------------|-----------------------------------|
| L1 | Modificar reglas YAML o transiciones de estado | Los servicios IA son **solo lectura**; el rol de BD `gemelo_app` no tiene `INSERT/UPDATE` sobre el esquema `analytics` y los endpoints IA no invocan handlers de comando |
| L2 | Emitir comandos (`PresentarDemandaCommand`, etc.) automáticamente | El prellenado RAG devuelve un *payload sugerido* que el frontend muestra en modo revisión; el envío exige clic humano autenticado con JWT |
| L3 | Fundamentar resoluciones judiciales | Sentencias las redacta/emite el juez (handler `DictarSentenciaHandler`); la predicción es insumso estadístico, no ratio decidendi |
| L4 | Contactar partes ni notificar plazos | No existe ese canal; notificaciones solo por el flujo transaccional auditado |
| L5 | Operar sin trazabilidad | Cada consumo de `/prediccion` se anota en `LogAuditoria` (acción `anotacion`) con quién y cuándo |

## 2. Explainable AI (XAI) — requisito de salida

Toda respuesta de IA es **rechazable por contrato** si carece de:

1. **Fundamento empírico**: tamaño de muestra (`muestra_casos`), distrito, ventana temporal y `fuente_datos` (etiqueta del ETL).
2. **Cita normativa**: artículos CPCN/Ley 908 pertinentes (p. ej. Arts. 37, 146–148 para pretensión/demanda; Arts. 132–137 para plazos).
3. **Método declarado**: algoritmo usado (proporción suavizada Laplace, mediana p10–p90, similitud coseno pgvector).
4. **Advertencia de rango**: texto embebido en el payload: *"no constituye asesoría legal ni sustituye el criterio del juzgador"*.

Umbral de confiabilidad: con `n < 20` casos históricos la predicción se marca `datos_insuficientes=true` y el frontend debe mostrarla como indicativa, nunca como estimación sólida.

## 3. Human-in-the-loop

* **Prellenado de escritos**: obligatorio que un abogado (rol `abogado` en JWT) revise y confirme cada campo sugerido antes de ejecutar cualquier comando. La UI marca visualmente los campos asistidos por IA.
* **Predicciones en tablero**: se muestran en panel lateral "Insight", separadas del semáforo de etapas, para evitar confusión entre *estado jurídico* (autoritativo) y *estimación estadística* (informativo).
* **Revisión periódica**: el Consejo Judicial designado revisa trimestralmente calibración (Brier score / error de duración) contra resultados reales; documentado en acta.

## 4. Política de anonimización y privacidad

1. **PII prohibida en datos de entrenamiento/análisis**: nombres, cédulas (formato `NNN-NNNNNN-NNNNL`), RUC (13 dígitos), correos y teléfonos.
2. **Doble barrera**:
   * *ETL*: poblar `hechos_judiciales_historicos` y `documento_anonimizado` solo con llaves sintéticas `hash_anonimizado = SHA-256(expediente + sal)`; la sal vive en bóveda de secretos, jamás en BD ni repositorio.
   * *Runtime*: `anonimizar_texto()` se aplica **antes** de generar embeddings o llamar a cualquier API externa de modelos; verificación defensiva con `contiene_pii_sospechosa()`.
3. **k-anonimato en dashboards públicos**: grupos agregados con menos de 5 casos se suprimen (`estadisticas_publicas`).
4. **Cuarentena de reidentificación**: si un auditor demuestra un ataque de reidentificación viable, el dataset se recalibra con nueva sal y se re-embedda el corpus (procedimiento en runbook de operaciones).
5. Base legal: Ley 787 (acceso a información pública, con reservas), Constitución Art. 26 (intimidad), y principio de publicidad de resoluciones del Art. 6 CPCN — armonizados: público = estadística anónima; reservado = expediente identificado.

## 5. Modelo de datos y entorno

* Entorno analítico separado del transaccional (mismo PostgreSQL, esquema lógico distinto, credenciales de solo lectura distintas).
* Cambios de versión de modelo/embebder ⇒ migración versionada + re-evaluación obligatoria + nota en esta gobernanza (registro de cambios abajo).

## 6. Responsabilidades

| Rol | Responsabilidad |
|-----|-----------------|
| Arquitecto de Datos | calidad y anonimización del ETL, métricas de deriva |
| Juez/RJ | validación humana de insights usados en gestión judicial |
| Abogado usuario | revisión obligatoria del prellenado antes de presentar |
| Seguridad | gestión de sal de seudonimización, rotación, accesos al esquema analytics |

## 7. Registro de cambios

| Fecha | Versión | Cambio |
|-------|---------|--------|
| 2026-10-19 | 1.0 | Emisión inicial (Fase 8) |
