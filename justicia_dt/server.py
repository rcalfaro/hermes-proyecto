#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JUSTICIA-DT Nicaragua — API REST con FastAPI.

Reutiliza el motor del gemelo digital (app.py) sin duplicar lógica y expone
los 9 módulos (§3.2) como endpoints, además de servir el dashboard index.html.

Instalar dependencias :  python -m pip install -r requirements.txt
Ejecutar              :  python server.py
Dashboard             :  http://127.0.0.1:8000/
Swagger / OpenAPI     :  http://127.0.0.1:8000/docs
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple

from app import (ESCENARIOS, LISTA_ESCENARIOS, PRETENSIONES, JusticiaDT, NucleoDT)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(
    title="JUSTICIA-DT Nicaragua",
    description=("Gemelo Digital para análisis de escenarios en juicios civiles "
                 "según la pretensión (Ley 902 — Nicaragua). Datos sintéticos, Fase 1."),
    version="1.0.0",
)

DT = JusticiaDT()          # Núcleo compartido; DT.informes = almacén de informes M9


# ----------------------------------------------------------------------------
# Esquemas Pydantic (validación automática -> errores 422 claros)
# ----------------------------------------------------------------------------
class ClasificarReq(BaseModel):
    texto_demanda: str = Field(..., min_length=10,
                               description="Fragmento de hechos/petitorio de la demanda")


class CasoReq(BaseModel):
    pretension: str = Field(..., description="declarativa|constitutiva|de_condena|"
                                             "ejecutiva|cautelar|probatoria")
    subtipo: Optional[str] = None
    demandante: str
    demandado: str
    cuantia_usd: float = Field(..., gt=0)
    juzgado: str
    pruebas: List[str] = ["documental"]
    hechos: str = ""


class TrazaPaso(BaseModel):
    etapa: str
    meses_reales: float = Field(..., gt=0)


class FlujoReq(CasoReq):
    traza_real: Optional[List[TrazaPaso]] = None


# ----------------------------------------------------------------------------
# Raíz y salud
# ----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    """M8: sirve el dashboard gráfico autocontenido."""
    ruta = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(ruta):
        return JSONResponse({"mensaje": "index.html no encontrado; use /docs"}, status_code=404)
    return FileResponse(ruta, media_type="text/html")


@app.get("/api/salud")
def salud():
    return {"estado": "operativo", "sistema": "JUSTICIA-DT Nicaragua",
            "modo": "datos sintéticos (Fase 1 hoja de ruta)",
            "pretensiones": len(PRETENSIONES), "escenarios": len(LISTA_ESCENARIOS),
            "informes_en_memoria": len(DT.informes)}


# ----------------------------------------------------------------------------
# M1 — Selección / clasificación de pretensión
# ----------------------------------------------------------------------------
@app.get("/api/catalogo")
def catalogo():
    """Catálogo Ley 902: tipos, subtipos, requisitos, etapas y escenarios."""
    def serial(p):
        q = dict(p)
        q["rango_meses"] = list(p["rango_meses"])
        return q
    return {"pretensiones": {k: serial(v) for k, v in PRETENSIONES.items()},
            "escenarios": LISTA_ESCENARIOS}


@app.post("/api/clasificar")
def clasificar(req: ClasificarReq):
    """C1: NLP heurístico que identifica pretensión y subtipo desde la demanda."""
    r = NucleoDT.clasificar(req.texto_demanda)
    if r["confianza"] < 0.4:
        raise HTTPException(422, "Texto insuficiente/no clasificable. Use /api/catalogo "
                                 "y seleccione la pretensión manualmente.")
    return r


# ----------------------------------------------------------------------------
# Módulos individuales M2..M7
# ----------------------------------------------------------------------------
@app.post("/api/caso")
def registrar_caso(req: CasoReq):
    """M2: registro + expediente digital con hash SHA-256 de integridad."""
    try:
        sel = DT.m1_seleccion(req.pretension, req.subtipo)
        caso = DT.m2_registro(sel, req.model_dump())
    except ValueError as e:
        raise HTTPException(404 if "Pretensión inválida" in str(e) else 422, str(e))
    return caso


@app.post("/api/viabilidad")
def viabilidad(req: CasoReq):
    """M3: evaluación preliminar comparada con casos históricos sintéticos."""
    try:
        sel = DT.m1_seleccion(req.pretension, req.subtipo)
        caso = DT.m2_registro(sel, req.model_dump())
        return DT.m3_viabilidad(caso)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/escenarios")
def escenarios(req: CasoReq):
    """M4: simulación Monte Carlo what-if de los 10 escenarios (§3.1)."""
    try:
        sel = DT.m1_seleccion(req.pretension, req.subtipo)
        caso = DT.m2_registro(sel, req.model_dump())
        viab = DT.m3_viabilidad(caso)
        esc, params = DT.m4_escenarios(caso, viab)
        return {"expediente": caso["expediente"], "viabilidad": viab["score"],
                "params": params, "escenarios": esc}
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/duracion")
def duracion(req: CasoReq):
    """M5: predicción de duración por etapa procesal según la pretensión."""
    try:
        sel = DT.m1_seleccion(req.pretension, req.subtipo)
        caso = DT.m2_registro(sel, req.model_dump())
        return DT.m5_duracion(caso)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/resultados")
def resultados(req: CasoReq):
    """M6: probabilidad de éxito y ranking de escenarios."""
    try:
        sel = DT.m1_seleccion(req.pretension, req.subtipo)
        caso = DT.m2_registro(sel, req.model_dump())
        viab = DT.m3_viabilidad(caso)
        esc, _ = DT.m4_escenarios(caso, viab)
        return DT.m6_resultados(caso, esc)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/anomalias")
def anomalias(req: CasoReq):
    """M7: detección de retrasos/desviaciones sobre la traza real del expediente."""
    try:
        sel = DT.m1_seleccion(req.pretension, req.subtipo)
        caso = DT.m2_registro(sel, req.model_dump())
        dur = DT.m5_duracion(caso)
        traza = [(t.etapa, t.meses_reales) for t in (req.traza_real or [])] \
            if isinstance(req, FlujoReq) else []
        return DT.m7_anomalias(caso, dur, traza or None)
    except ValueError as e:
        raise HTTPException(422, str(e))


# ----------------------------------------------------------------------------
# Orquestación completa (flujo de uso §3.3, Pasos 1-5) y M9
# ----------------------------------------------------------------------------
@app.post("/api/flujo_completo")
def flujo_completo(req: FlujoReq):
    """Ejecuta M1→M9 en un solo llamado (Pasos 1-5 del flujo de uso)."""
    try:
        traza = [(t.etapa, t.meses_reales) for t in (req.traza_real or [])] or None
        inf = DT.flujo_completo(req.pretension, req.subtipo,
                                req.model_dump(exclude={"traza_real"}), traza)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return inf


@app.get("/api/informe/{expediente}")
def informe(expediente: str):
    """M9: recupera el informe final almacenado por número de expediente."""
    if expediente not in DT.informes:
        raise HTTPException(404, f"Informe {expediente} no encontrado. "
                                 "Genere uno primero con /api/flujo_completo.")
    return DT.informes[expediente]


if __name__ == "__main__":
    import uvicorn
    print("JUSTICIA-DT Nicaragua — servidor FastAPI")
    print("  Dashboard : http://127.0.0.1:8000/")
    print("  Swagger   : http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)
