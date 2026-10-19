---
name: "Análisis Jurídico RAG Avanzado con Evaluación"
description: "Skill para analizar documentos legales (constituciones, códigos, leyes, contratos) mediante recuperación aumentada de información (RAG) con capacidades avanzadas de razonamiento y un sistema de evaluación objetivo."
---

## Objetivo
Permitir que el agente jurídico procese documentos legales en múltiples formatos, extraiga artículos relevantes, interprete su alcance normativo y genere respuestas con razonamiento jurídico contextualizado, evaluadas mediante criterios objetivos.

## Capacidades
- **Carga multiformato**: Leer documentos legales en PDF, DOCX, TXT y HTML.  
- **Indexación avanzada**: Identificar artículos, secciones, cláusulas y jurisprudencia para consultas rápidas.  
- **Razonamiento normativo**:  
  - Interpretar el sentido jurídico de un artículo.  
  - Detectar principios generales y excepciones.  
  - Evaluar compatibilidad entre normas distintas.  
- **Comparación normativa**: Contrastar disposiciones entre códigos, leyes o contratos.  
- **Análisis de conflictos**: Señalar contradicciones o vacíos legales.  
- **Resúmenes ejecutivos**: Generar síntesis claras para audiencias ejecutivas, académicas o ciudadanas.  
- **Contextualización multicultural**: Adaptar explicaciones para Nicaragua y Latinoamérica, con referencias comparativas.  
- **Capacidad predictiva segura**: Anticipar posibles interpretaciones judiciales basadas en precedentes (sin emitir juicios propios).  
- **Evaluación objetiva**: Aplicar métricas de calidad a cada respuesta.  

## Sistema de Evaluación Objetivo
Cada respuesta generada será evaluada con los siguientes criterios:

1. **Precisión normativa (0–5)**  
   - ¿La cita corresponde exactamente al texto legal?  
   - ¿Se evita la interpretación errónea?  

2. **Relevancia contextual (0–5)**  
   - ¿La respuesta aborda directamente la consulta del usuario?  
   - ¿Incluye referencias normativas pertinentes?  

3. **Claridad comunicativa (0–5)**  
   - ¿El lenguaje es comprensible para el público objetivo?  
   - ¿Se evita el exceso de tecnicismos sin explicación?  

4. **Profundidad analítica (0–5)**  
   - ¿Se identifican principios, excepciones o conflictos normativos?  
   - ¿Se ofrece un razonamiento más allá de la cita literal?  

5. **Trazabilidad (0–5)**  
   - ¿Se indican claramente las fuentes (documento, artículo, sección)?  
   - ¿La respuesta permite verificar la información?  

**Escala de evaluación:**  
- 20–25: Excelente (respuesta completa y confiable).  
- 15–19: Buena (respuesta útil con pequeños ajustes).  
- 10–14: Regular (respuesta parcial, necesita mejoras).  
- <10: Deficiente (respuesta insuficiente o incorrecta).  

## Instrucciones
1. Detectar y cargar documentos desde el directorio `./leyes/`.  
2. Procesar cada documento con embeddings seguros.  
3. Al recibir una consulta:  
   - Buscar pasajes relevantes.  
   - Interpretar el alcance normativo.  
   - Comparar con otras fuentes si procede.  
   - Evaluar la respuesta con el sistema objetivo.  
4. Responder con:  
   - Explicación clara y razonada.  
   - Cita del artículo o sección.  
   - Nombre del documento fuente.  
   - Observaciones sobre compatibilidad o conflicto normativo.  
   - Puntuación de evaluación objetiva.  

## Entradas
- Documentos legales en formato `.pdf`, `.docx`, `.txt`, `.html`.  
- Consultas del usuario en lenguaje natural.  

## Salidas
- Respuestas jurídicas con razonamiento normativo.  
- Tablas comparativas de artículos.  
- Resúmenes ejecutivos de leyes o contratos.  
- Señalamiento de posibles conflictos normativos.  
- Puntuación objetiva de calidad de la respuesta.  

## Ejemplo de uso
**Consulta:**  
> ¿Qué establece el artículo 27 de la Constitución de Nicaragua y cómo se relaciona con el Código Civil?

**Respuesta esperada:**  
> El artículo 27 de la Constitución de Nicaragua establece la igualdad de todas las personas ante la ley y la prohibición de discriminación.  
> En el Código Civil, los artículos sobre capacidad jurídica refuerzan este principio al reconocer la igualdad en el ejercicio de derechos civiles.  
> **Fuente:** Constitución Política de Nicaragua, Art. 27; Código Civil de Nicaragua, Arts. 30–32.  
> **Evaluación objetiva:** Precisión 5, Relevancia 5, Claridad 4, Profundidad 4, Trazabilidad 5 → **23/25 (Excelente)**  

## Notas
- Compatible con agentes académicos, ejecutivos y creativos.  
- No requiere acceso a GPU ni comandos externos.  
- Puede integrarse con la skill `pdf` para extracción de texto.  
- Diseñado para entornos legales en Nicaragua y Latinoamérica.  
- Optimizado para razonamiento normativo, comparativo y evaluación objetiva.  
