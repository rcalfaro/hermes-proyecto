"""Extractor determinista de señales jurídicas en borradores de escritos.

Primera capa del pipeline NLP — 100 % reproducible, sin modelo externo:
diccionarios de léxico procesal (terminología civil nicaragüense, CPCN Ley
908) + patrones de cita normativa. Sus salidas alimentan el prellenado del
``PresentarDemandaCommand`` y sirven de *grounding* para validar que las
sugerencias del RAG no contradigan lo que el propio texto dice.

Nota de diseño deliberada: la detección de pretensión es multicanal
(verbos rectores + sustantivos núcleo + referencias fácticas típicas) y
devuelve TODAS las coincidencias con puntaje, porque en el proceso civil
nicaragüense está permitida la acumulación de pretensiones (Art. 37 y 40
CPCN); el humano decide al revisar (human-in-the-loop).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Cita normativa: "Art. 148 CPC", "artículo 134 del Código Procesal Civil"...
_RE_CITA = re.compile(
    r"\b(?:arts?\.?|art[íi]culo)s?\s+(\d+(?:\s*(?:-\s*|\sy\s)\d+)?)?"
    r"[^\n]{0,40}?"
    r"(cpc(?:n)?|c[óo]digo\s+procesal\s+civil|ley\s+908|cc(?:n)?|c[óo]digo\s+civil)",
    re.IGNORECASE,
)

#: Léxico por tipo de pretensión → (peso, ejemplos de disparadores léxicos).
_LEXICO_PRETENSIONES: dict[str, tuple[int, tuple[str, ...]]] = {
    "desalojo": (
        5,
        (
            "desalojo",
            "desocupar",
            "precario",
            "terminaci[oó]n del contrato de arrendamiento",
            "no le he renovado",
            "restituci[oó]n del inmueble",
        ),
    ),
    "cobro_de_dinero": (
        5,
        (
            "cobro de dinero",
            "pague la suma",
            "adeuda",
            "deuda l[ií]quida",
            "exigible",
            "gastos m[eé]dicos",
            "cantidades adeudadas",
            "rinda cuentas",
        ),
    ),
    "cumplimiento_o_rescision_de_contrato": (
        4,
        (
            "cumplimiento del contrato",
            "rescisi[oó]n",
            "incumpli[oó]",
            "contrato de compraventa",
            "no ha entregado el bien",
        ),
    ),
    "nulidad_absoluta": (
        4,
        (
            "nulidad absoluta",
            "objeto il[ií]cito",
            "contrario a la ley",
            "nulidad de pleno derecho",
        ),
    ),
    "nulidad_relativa": (
        3,
        (
            "nulidad relativa",
            "vicio del consentimiento",
            "lesiones enormes",
            "capacidad de goce",
        ),
    ),
    "reivindicacion": (
        4,
        (
            "reivindicatoria",
            "reivindico",
            "soy [úu]nico due[ñn]o",
            "propiedad inscrita",
            "carezco de la posesi[oó]n",
        ),
    ),
    "divorcio": (
        4,
        ("divorcio", "disoluci[oó]n del v[ií]nculo matrimonial", "causales"),
    ),
    "filiacion": (
        4,
        ("filiaci[oó]n", "reclamaci[oó]n de paternidad", "prueba de paternidad"),
    ),
    "sucesion_abintestato": (
        4,
        ("sucesi[oó]n abintestato", "sin testamento", "declaraci[oó]n de herederos"),
    ),
}

#: Patrones de hechos clave (oraciones con estructura fáctica típica).
_RE_HECHOS = re.compile(
    r"(?:^|\.)\s*((?:El\s+d[ií]a|En\s+fecha|Con\s+fecha|"
    r"Que\s+(?:el|la|en|con|he|mi|se)|Mediante|"
    r"Por\s+medio\s+del|"
    r"En\s+virtud\s+del)[^.]{20,300})\.",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class CoincidenciaPretension:
    """Candidato a pretensión detectado con su evidencia lexical."""

    codigo_tipo: str
    puntaje: int
    terminos_detectados: tuple[str, ...]


@dataclass(slots=True)
class Extrahecho:
    """Resultado del análisis determinista de un escrito (borrador).

    Atributos pensados para mapear 1:1 los campos del PresentarDemandaCommand:
    ``pretension_detectada`` → ``codigo_tipo``, ``descripcion`` → resumen de
    hechos, ``fundamentos_sugeridos`` → ``fundamento_normativo``.
    """

    pretensiones: list[CoincidenciaPretension] = field(default_factory=list)
    hechos_clave: list[str] = field(default_factory=list)
    fundamentos_legales: list[str] = field(default_factory=list)
    monto_sugerido: float | None = None
    confianza_global: float = 0.0  # [0..1]: cobertura de señales encontradas

    @property
    def pretension_principal(self) -> CoincidenciaPretension | None:
        return max(self.pretensiones, key=lambda c: c.puntaje, default=None)


def _detectar_pretensiones(texto_lower: str) -> list[CoincidenciaPretension]:
    hallazgos: list[CoincidenciaPretension] = []
    for codigo, (peso, patrones) in _LEXICO_PRETENSIONES.items():
        termos = tuple(
            p for p in patrones if re.search(p.lower(), texto_lower, re.IGNORECASE)
        )
        if termos:
            hallazgos.append(
                CoincidenciaPretension(
                    codigo_tipo=codigo,
                    puntaje=peso * len(termos),
                    terminos_detectados=termos[:5],
                )
            )
    return sorted(hallazgos, key=lambda h: -h.puntaje)


def _extraer_montos(texto: str) -> float | None:
    """Primer monto en córdobas (C$) o formato numérico con separadores."""
    m = re.search(
        r"C[\$]\s*([\d.,]+)|(?:suma\s+de)\s+([\d.,]+)\s+(?:c[óo]rdobas)",
        texto,
        re.IGNORECASE,
    )
    if not m:
        return None
    crudo = (m.group(1) or m.group(2)).replace(",", "")
    try:
        return float(crudo)
    except ValueError:
        return None


def extracto_preliminar(texto: str) -> Extrahecho:
    """Analiza un borrador de demanda/escrito y extrae señales estructuradas.

    Args:
        texto: contenido íntegro del escrito (antes de anonimizar: este
            extractor NO sale del perímetro; el envío a modelos externos se
            hace solo sobre la versión anonimizada en RagPipeline).

    Returns:
        ``Extrahecho`` con pretensiones candidatas, hechos clave, citas
        normativas detectadas y monto sugerido.
    """
    bajo = texto.lower()
    pretensiones = _detectar_pretensiones(bajo)
    hechos = [h.strip() for h in _RE_HECHOS.findall(texto)][:8]
    citas: list[str] = []
    for m in _RE_CITA.finditer(texto):
        numero = (m.group(1) or "").strip()
        cuerpo = (
            "CPCN"
            if "908" in m.group(2).lower() or "procesal" in m.group(2).lower()
            else "CCN"
        )
        citas.append(f"Art. {numero} {cuerpo}" if numero else f"{cuerpo}")
    monto = _extraer_montos(texto)

    senales = sum([bool(pretensiones), bool(hechos), bool(citas), monto is not None])
    return Extrahecho(
        pretensiones=pretensiones,
        hechos_clave=hechos,
        fundamentos_legales=sorted(set(citas)),
        monto_sugerido=monto,
        confianza_global=senales / 4,
    )


def como_payload_comando(e: Extrahecho) -> dict[str, Any]:
    """Adaptador explícito hacia los campos de PresentarDemandaCommand.

    ⚠️ Solo PRELLENADO SUGERIDO: el abogado/juez debe revisar y confirmar;
    el sistema nunca envía el comando automáticamente (gobernanza IA).
    """
    principal = e.pretension_principal
    return {
        "codigo_tipo": principal.codigo_tipo if principal else None,
        "descripcion": "; ".join(e.hechos_clave[:3]) or None,
        "fundamento_normativo": ", ".join(e.fundamentos_legales) or None,
        "monto_pretendido": e.monto_sugerido,
        "_advertencia": "Prellenado por IA — requiere revisión humana obligatoria.",
    }
