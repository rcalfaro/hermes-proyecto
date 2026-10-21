/**
 * Simulaciones públicas (GET /api/publico/simulaciones) — vista anonimizada
 * para transparencia judicial: secuencias de estados sin datos personales.
 */

import { useEffect, useState } from 'react';

import { getPublicSimulations } from '../lib/api';
import type { SimulacionPublicaDTO } from '../lib/types';
import { ApiError } from '../lib/types';

export default function SimulacionesPage() {
  const [items, setItems] = useState<SimulacionPublicaDTO[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getPublicSimulations(ctrl.signal)
      .then(setItems)
      .catch((err: unknown) => {
        if (err instanceof ApiError) setError(err.message);
        else setError('Error inesperado.');
      });
    return () => ctrl.abort();
  }, []);

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-1 font-serif text-2xl font-bold text-ink">
        Simulaciones Públicas del Proceso Civil
      </h1>
      <p className="mb-6 text-sm text-slate-500">
        Traza anonimizada de expedientes simulados — publicidad sin datos personales (Art. 6 CPCN,
        Ley 787).
      </p>

      {error !== null && <p className="rounded bg-red-50 p-3 text-red-800">{error}</p>}
      {items === null && error === null && <p className="animate-pulse text-slate-400">Cargando…</p>}

      <ul className="space-y-3">
        {(items ?? []).map((s) => (
          <li key={s.clave_simulacion} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="font-mono text-xs text-slate-400">{s.clave_simulacion}</p>
            <p className="font-serif font-semibold text-ink">
              {s.materia} · {s.tipo_proceso}
            </p>
            <p className="mt-1 text-xs text-slate-600">
              Secuencia: {s.secuencia_estados.join(' → ')}
            </p>
            <p className="text-xs text-slate-500">
              Duración: {s.duracion_dias ?? '—'} días hábiles · Resultado:{' '}
              {s.resultado ?? 'en curso'}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
