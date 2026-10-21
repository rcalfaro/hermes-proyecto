/**
 * Router mínimo sin dependencias extra: mapea la convención de App Router
 *   app/caso/[id]/page.tsx  →  #/caso/:id
 *   app/publico/simulaciones→  #/publico/simulaciones
 * (HashRouter propio y diminuto; en migración a Next.js basta mover los
 * componentes a sus rutas de archivo.)
 */

import { useEffect, useState } from 'react';

import CasoPage from './pages/CasoPage';
import SimulacionesPage from './pages/SimulacionesPage';

type Ruta =
  | { nombre: 'caso'; id: string }
  | { nombre: 'simulaciones' }
  | { nombre: 'inicio' };

function parsear(hash: string): Ruta {
  const limpio = hash.replace(/^#\/?/, '');
  const partes = limpio.split('/');
  if (partes[0] === 'caso' && partes[1] !== undefined && partes[1] !== '') {
    return { nombre: 'caso', id: partes[1] };
  }
  if (partes[0] === 'publico' && partes[1] === 'simulaciones') {
    return { nombre: 'simulaciones' };
  }
  return { nombre: 'inicio' };
}

export default function App() {
  const [ruta, setRuta] = useState<Ruta>(() => parsear(window.location.hash));

  useEffect(() => {
    const onHash = (): void => setRuta(parsear(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  if (ruta.nombre === 'caso') {
    return (
      <div className="h-screen">
        <CasoPage casoId={ruta.id} />
      </div>
    );
  }

  if (ruta.nombre === 'simulaciones') {
    return <SimulacionesPage />;
  }

  // Pantalla de acceso al tablero: solicita el ID del expediente.
  return (
    <div className="flex h-screen items-center justify-center bg-parchment p-6">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const input = new FormData(e.currentTarget).get('caso');
          if (typeof input === 'string' && input.trim() !== '') {
            window.location.hash = `#/caso/${input.trim()}`;
          }
        }}
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-lg"
      >
        <h1 className="font-serif text-xl font-bold text-ink">Gemelo Digital — Proceso Civil</h1>
        <p className="mb-4 text-sm text-slate-500">Ley 908 · Código Procesal Civil de Nicaragua</p>
        <label className="block text-sm font-medium text-slate-700">
          ID del expediente (UUID)
          <input
            name="caso"
            required
            placeholder="ej. 3f0c1a6e-…"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm focus:border-sky-500 focus:outline-none"
          />
        </label>
        <button
          type="submit"
          className="mt-4 w-full rounded-md bg-sky-700 py-2 font-medium text-white hover:bg-sky-800"
        >
          Abrir tablero de control
        </button>
        <a href="#/publico/simulaciones" className="mt-3 block text-center text-xs text-sky-700">
          Ver simulaciones públicas anonimizadas →
        </a>
      </form>
    </div>
  );
}
