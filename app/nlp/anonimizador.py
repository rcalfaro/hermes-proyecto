"""Anonimización obligatoria de textos antes de cualquier procesamiento IA.

Política (docs/IA_GOBERNANZA.md, art. de privacidad): ningún texto con PII
puede salir del perímetro hacia un modelo externo ni entrar al corpus RAG.
Este módulo aplica pseudonimia determinista reversible-solo-con-sal (la sal
vive en bóveda, nunca en BD) sobre los patrones de identidad nicaragüenses:

* nombres propios → ``[PERSONA-<hash8>]`` (estable dentro del mismo texto),
* cédulas (001-120390-1000A) y RUC (0101xxxxxxxxxx1) → ``[DOC]``,
* teléfonos, correos y direcciones simples → tokens sintéticos.

Determinismo: misma entrada + misma sal = misma salida (requisito XAI para
reproducir análisis años después).
"""

from __future__ import annotations

import hashlib
import re

#: Cédula nicaragüense: 3 dígitos - 6 dígitos - 4 caracteres.
_RE_CEDULA = re.compile(r"\b\d{3}-\d{6}-\d{4}[A-Za-z]\b")
#: RUC: 13 dígitos (Ley 794 de simplificación tributaria).
_RE_RUC = re.compile(r"\b\d{13}\b")
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_TEL = re.compile(r"\+(?:505|\\d{1,3})[\s-]?\d{4}[\s-]?\d{4}")
#: Nombres propios secuenciales (mayúscula inicial consecutiva, ≥2 palabras,
#: excluyendo inicio de oración tras punto — heurística conservadora legal).
_RE_NOMBRE = re.compile(
    r"(?<!\. )\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+(?:de\s+|del\s+|y\s+)?"
    r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})+)\b"
)


def _token_etiquetado(valor: str, sal: str, etiqueta: str) -> str:
    """Token sintético estable: hash truncado → deduplicable, no reversible."""
    h = hashlib.sha256(f"{sal}:{valor}".encode()).hexdigest()[:8].upper()
    return f"[{etiqueta}-{h}]"


def anonimizar_texto(texto: str, *, sal: str = "gemelo-sal-demo") -> str:
    """Devuelve ``texto`` sin PII identificable, listo para embedder/RAG.

    Args:
        texto: borrador o fragmento original (puede contener nombres).
        sal: secreto de seudonimización; cambiarla invalida equivalencias
            históricas de tokens (gestión de claves en gobernanza).

    Returns:
        Texto con documentos, contactos y nombres sustituidos por tokens.
    """
    resultado = _RE_CEDULA.sub("[DOC-CEDULA]", texto)
    resultado = _RE_RUC.sub("[DOC-RUC]", resultado)
    resultado = _RE_EMAIL.sub("[CONTACTO-EMAIL]", resultado)
    resultado = _RE_TEL.sub("[CONTACTO-TEL]", resultado)
    resultado = _RE_NOMBRE.sub(
        lambda m: _token_etiquetado(m.group(0), sal, "PERSONA"), resultado
    )
    return resultado


def contiene_pii_sospechosa(texto: str) -> bool:
    """Detector defensivo previo a enviar texto a APIs externas (Zero Trust)."""
    return bool(
        _RE_CEDULA.search(texto) or _RE_RUC.search(texto) or _RE_EMAIL.search(texto)
    )
