#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JUSTICIA-DT Nicaragua — Empaqueta el proyecto como ZIP para Windows 11.

Genera justicia_dt.zip con TODO lo necesario (código + informe_demo.json de
referencia), excluyendo __pycache__, .venv y archivos temporales.

Uso:   python exportar_html.py
Luego: copie el ZIP al destino, clic derecho -> "Extraer todo..."
"""
import os
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del repo
RAIZ = os.path.basename(BASE)
ZIP = os.path.join(BASE, "justicia_dt.zip")
EXCLUIR_DIRS = {"__pycache__", ".venv", "venv", ".git"}


def en_ruta(nombre):
    return nombre in ("justicia_dt.zip",) or nombre.endswith((".pyc", "~"))


with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for raiz, dirs, archivos in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in EXCLUIR_DIRS]
        for a in archivos:
            if en_ruta(a):
                continue
            completo = os.path.join(raiz, a)
            rel = os.path.relpath(completo, BASE)
            z.write(completo, os.path.join(RAIZ, rel))
    print("Contenido del ZIP:")
    for i in z.infolist():
        print(f"  {i.filename}  ({i.file_size} B)")

print("\nZIP generado en:", ZIP)
print("Windows 11: clic derecho sobre el ZIP -> 'Extraer todo...'")
