"""``PredictiveService`` — estimación de probabilidad de éxito y duración.

Dado un ``Caso`` (o sus atributos equivalentes) y su pretensión principal,
consulta el dataset anonimizado ``hechos_judiciales_historicos`` y devuelve:

* probabilidad de éxito (estimador bayesiano con suavizado Laplace →
  estable incluso con muestras pequeñas),
* intervalo de confianza ~95 % (regla del empírico sobre la proporción),
* tiempo real estimado Admisión → Sentencia (mediana histórica + banda
  p10–p90),
* **fundamento XAI obligatorio**: n de la muestra, distrito, ventana
  temporal y fuente de datos, más la cita normativa pertinente del CPCN.

⚖️ La salida es INSUMISO procesal: no habilita ni bloquea transiciones
(eso lo decide exclusivamente el CaseFlowEngine sobre el YAML). Sirve para
calibrar expectativas y priorizar carga judicial, nunca para sustituir el
criterio jurídico del juzgador. Ver ``docs/IA_GOBERNANZA.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.analytics.modelos import HechoJudicialHistorico

#: Mínimo de casos históricos para emitir una predicción "confiable".
#: Por debajo, la salida se marca ``datos_insuficientes`` (gobernanza IA).
UMBRAL_MUESTRA_MINIMA = 20


@dataclass(frozen=True, slots=True)
class FundamentoPredictivo:
    """Explicación XAI adjunta a toda predicción (requisito sin excepciones)."""

    muestra_casos: int
    distrito_judicial: str
    ventana_inicio: date | None
    ventana_fin: date | None
    fuente_datos: str
    citas_normativas: tuple[str, ...]
    metodo: str
    advertencia: str = (
        "Estadística descriptiva de apoyo; no constituye asesoría legal ni "
        "sustituye el criterio del juzgador (ver docs/IA_GOBERNANZA.md)."
    )


@dataclass(frozen=True, slots=True)
class PrediccionCaso:
    """Resultado completo e inmutable de una predicción."""

    codigo_tipo_pretension: str
    probabilidad_exito: float | None  # [0..1], None si muestra insuficiente
    margen_confianza_pp: float | None  # ± puntos porcentuales (~95 %)
    dias_admision_sentencia_estimados: int | None  # mediana histórica
    banda_p10_p90_dias: tuple[int, int] | None
    datos_insuficientes: bool
    fundamento: FundamentoPredictivo

    def como_dict(self) -> dict[str, Any]:
        """Serialización para el endpoint / JSONB de respuestas."""
        return {
            "codigo_tipo_pretension": self.codigo_tipo_pretension,
            "probabilidad_exito": self.probabilidad_exito,
            "margen_confianza_pp": self.margen_confianza_pp,
            "dias_admision_sentencia_estimados": self.dias_admision_sentencia_estimados,
            "banda_p10_p90_dias": list(self.banda_p10_p90_dias)
            if self.banda_p10_p90_dias
            else None,
            "datos_insuficientes": self.datos_insuficientes,
            "fundamento": {
                "muestra_casos": self.fundamento.muestra_casos,
                "distrito_judicial": self.fundamento.distrito_judicial,
                "ventana": [
                    str(self.fundamento.ventana_inicio),
                    str(self.fundamento.ventana_fin),
                ],
                "fuente_datos": self.fundamento.fuente_datos,
                "citas_normativas": list(self.fundamento.citas_normativas),
                "metodo": self.fundamento.metodo,
                "advertencia": self.fundamento.advertencia,
            },
        }


class PredictiveService:
    """Servicio puro de lectura analítica (sin efectos sobre el dominio).

    Args:
        session: sesión SQLAlchemy **de solo lectura** (el rol de BD de la
            aplicación carece de INSERT/UPDATE sobre ``analytics``).
    """

    #: Cita por defecto: Arts. 148 (admisión) y 192-201 (sentencia) CPCN.
    CITAS_BASE = ("Art. 148 CPCN (auto iniciado)", "Arts. 192-201 CPCN (sentencia)")

    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------- API pública
    def predecir(
        self,
        *,
        codigo_tipo_pretension: str,
        distrito_judicial: str | None = None,
        cuantia_rango: str | None = None,
    ) -> PrediccionCaso:
        """Predice éxito + duración para (pretensión [, distrito [, cuantía]]).

        La probabilidad usa *add-one smoothing* (Laplace): p̂ = (éxitos+1)/(n+2),
        robusto ante colas de distribución y muestras pequeñas. El margen de
        confianza ~95 % se obtiene por aproximación normal (Wald) acotada.
        """
        # Agregados directos sobre la tabla con WHERE (portable PG/SQLite,
        # sin subconsulta ni producto cartesiano).
        H = HechoJudicialHistorico
        exitos_expr = func.sum(
            H.sentido_fallo.in_(("con_lugar", "con_lugar_parcialmente")).cast(Integer)
        )
        stmt_agg = select(
            func.count().label("n"),
            exitos_expr.label("exitos"),
            func.min(H.ventana_inicio),
            func.max(H.ventana_fin),
            func.max(H.fuente_datos),
        ).where(
            *self._filtros(codigo_tipo_pretension, distrito_judicial, cuantia_rango)
        )
        fila_agregados = self._session.execute(stmt_agg).one()

        n = int(fila_agregados[0] or 0)
        exitos = int(fila_agregados[1] or 0)
        fundamento = FundamentoPredictivo(
            muestra_casos=n,
            distrito_judicial=distrito_judicial or "todas",
            ventana_inicio=fila_agregados[2],
            ventana_fin=fila_agregados[3],
            fuente_datos=fila_agregados[4] or "dataset anonimizado",
            citas_normativas=self.CITAS_BASE,
            metodo="Laplace-smoothed proportion + median duration (XAI)",
        )

        if n == 0:
            return PrediccionCaso(
                codigo_tipo_pretension=codigo_tipo_pretension,
                probabilidad_exito=None,
                margen_confianza_pp=None,
                dias_admision_sentencia_estimados=None,
                banda_p10_p90_dias=None,
                datos_insuficientes=True,
                fundamento=fundamento,
            )

        p_hat = (exitos + 1) / (n + 2)
        se = math.sqrt(max(p_hat * (1 - p_hat) / (n + 2), 1e-12))
        margen_pp = round(min(1.96 * se * 100, 50.0), 1)

        duraciones = self._duraciones(
            codigo_tipo_pretension, distrito_judicial, cuantia_rango
        )
        mediana, banda = self._resumen_duraciones(duraciones)

        return PrediccionCaso(
            codigo_tipo_pretension=codigo_tipo_pretension,
            probabilidad_exito=round(p_hat, 3),
            margen_confianza_pp=margen_pp,
            dias_admision_sentencia_estimados=mediana,
            banda_p10_p90_dias=banda,
            datos_insuficientes=n < UMBRAL_MUESTRA_MINIMA,
            fundamento=fundamento,
        )

    def estadisticas_publicas(self, anio: int | None = None) -> list[dict[str, Any]]:
        """Dashboard anónimo: métricas agregadas por pretensión (sin PII).

        Fuente: tabla pre-agregada ``metrica_distrito_anual`` vía SQL GROUP BY
        sobre el detalle histórico — siempre desidentificado.
        """
        stmt = (
            select(
                HechoJudicialHistorico.codigo_tipo_pretension,
                func.count().label("total"),
                func.sum(
                    (HechoJudicialHistorico.sentido_fallo == "con_lugar").cast(Integer)
                ).label("con_lugar"),
                func.avg(HechoJudicialHistorico.dias_admision_sentencia).label(
                    "media_dias"
                ),
            )
            .group_by(HechoJudicialHistorico.codigo_tipo_pretension)
            .order_by(func.count().desc())
        )
        if anio is not None:
            stmt = stmt.where(HechoJudicialHistorico.anio_resolucion == anio)
        filas = self._session.execute(stmt).all()
        return [
            {
                "tipo_pretension": f.codigo_tipo_pretension,
                "total_casos": int(f.total),
                "tasa_con_lugar": round(int(f.con_lugar or 0) / int(f.total), 3),
                "tiempo_promedio_dias_habiles": round(float(f.media_dias), 1)
                if f.media_dias is not None
                else None,
            }
            for f in filas
        ]

    # ---------------------------------------------------------------- helpers
    def _duraciones(
        self, tipo: str, distrito: str | None, cuantia: str | None
    ) -> list[int]:
        columnas = select(HechoJudicialHistorico.dias_admision_sentencia).where(
            *self._filtros(tipo, distrito, cuantia)
        )
        valores = self._session.execute(columnas).scalars().all()
        return sorted(v for v in valores if v is not None)

    @staticmethod
    def _filtros(tipo: str, distrito: str | None, cuantia: str | None) -> list[Any]:
        fijos: list[Any] = [HechoJudicialHistorico.codigo_tipo_pretension == tipo]
        if distrito:
            fijos.append(HechoJudicialHistorico.distrito_judicial == distrito)
        if cuantia:
            fijos.append(HechoJudicialHistorico.cuantia_rango == cuantia)
        return fijos

    @staticmethod
    def _resumen_duraciones(d: list[int]) -> tuple[int | None, tuple[int, int] | None]:
        """Mediana y banda p10–p90 (percentil por interpolación lineal simple)."""
        if not d:
            return None, None
        mediana = (
            d[len(d) // 2] if len(d) % 2 else (d[len(d) // 2 - 1] + d[len(d) // 2]) // 2
        )
        p10 = d[max(0, int(0.10 * (len(d) - 1)))]
        p90 = d[min(len(d) - 1, int(0.90 * (len(d) - 1)))]
        return int(mediana), (p10, p90)
