/**
 * ActionPanel — sidebar contextual de actos procesales.
 *
 * Se abre al seleccionar un nodo ACTIVO y lista SOLO los comandos evaluados
 * por getAvailableActions(caso, rol): cada botón dispara executeCommand()
 * contra POST /api/comandos/<name>. Las acciones no autorizadas se muestran
 * DESHABILITADAS con tooltip explicativo (motivo legal/rol), nunca ocultas:
 * la UX debe enseñar por qué el sistema niega el acto (Art. 134 preclusión,
 * roles_autorizados del YAML, etc.). La autorización definitiva es del backend.
 */

import { useState } from 'react';

import type { AccionDisponible, CommandName, EstadoProcesal } from '../lib/types';
import { ApiError } from '../lib/types';

export interface ActionPanelProps {
  abierto: boolean;
  tituloEtapa: string;
  estadoActual: EstadoProcesal;
  acciones: AccionDisponible[];
  /** Callback hacia la página: envía el comando al handler correspondiente. */
  executeCommand: (command: CommandName, payload: Record<string, unknown>) => Promise<void>;
  onCerrar: () => void;
}

type EstadoEjecucion = 'idle' | 'enviando' | 'exito' | 'error';

export function ActionPanel({
  abierto,
  tituloEtapa,
  estadoActual,
  acciones,
  executeCommand,
  onCerrar,
}: ActionPanelProps) {
  const [ejecucion, setEjecucion] = useState<EstadoEjecucion>('idle');
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [comandoEnCurso, setComandoEnCurso] = useState<CommandName | null>(null);

  if (!abierto) return null;

  const handleEjecutar = async (accion: AccionDisponible): Promise<void> => {
    if (!accion.permitida || ejecucion === 'enviando') return;
    setEjecucion('enviando');
    setComandoEnCurso(accion.command);
    setMensaje(null);
    try {
      // El payload mínimo lo completa la página (caso_id/actor_id); aquí se
      // agrega el disparador para trazabilidad cross-side.
      await executeCommand(accion.command, { disparador: accion.disparador });
      setEjecucion('exito');
      setMensaje(`✓ ${accion.etiqueta} registrado en LogAuditoria.`);
    } catch (err) {
      setEjecucion('error');
      setMensaje(
        err instanceof ApiError
          ? `⚠️ (${err.status}) ${err.message}`
          : 'No fue posible contactar al servidor judicial.',
      );
    } finally {
      setComandoEnCurso(null);
    }
  };

  return (
    <aside
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl"
      aria-label={`Acciones disponibles — ${tituloEtapa}`}
    >
      {/* Encabezado */}
      <header className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-sky-700">
            Actos procesales habilitados
          </p>
          <h2 className="font-serif text-lg font-bold text-ink">{tituloEtapa}</h2>
          <p className="text-xs text-slate-500">
            Estado del expediente: <span className="font-mono">{estadoActual}</span>
          </p>
        </div>
        <button
          onClick={onCerrar}
          aria-label="Cerrar panel"
          className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          ✕
        </button>
      </header>

      {/* Lista de acciones */}
      <ul className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {acciones.map((accion) => {
          const cargando = ejecucion === 'enviando' && comandoEnCurso === accion.command;
          return (
            <li key={`${accion.command}-${accion.disparador}`}>
              {/* title ⇒ tooltip nativo accesible con el MOTIVO DEL BLOQUEO */}
              <div
                className={accion.permitida ? '' : 'accion-deshabilitada'}
                title={accion.motivo_bloqueo ?? undefined}
              >
                <button
                  disabled={!accion.permitida || ejecucion === 'enviando'}
                  onClick={() => void handleEjecutar(accion)}
                  className={[
                    'w-full rounded-lg border px-4 py-3 text-left transition-colors',
                    accion.permitida
                      ? 'border-sky-300 bg-sky-50 hover:bg-sky-100 active:bg-sky-200'
                      : 'border-slate-200 bg-slate-50 opacity-60',
                    cargando ? 'animate-pulse' : '',
                  ].join(' ')}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-serif text-sm font-semibold text-ink">
                      {accion.permitida ? '⚖' : '🔒'} {accion.etiqueta}
                      {cargando ? ' …' : ''}
                    </span>
                    <span className="font-mono text-[9px] text-slate-400">
                      /{accion.command}
                    </span>
                  </span>
                  <span className="mt-1 block text-[11px] leading-snug text-slate-500">
                    {accion.requisito_normativo}
                  </span>
                  {!accion.permitida && accion.motivo_bloqueo !== null && (
                    <span className="mt-1 block text-[11px] font-medium text-red-700">
                      {accion.motivo_bloqueo}
                    </span>
                  )}
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      {/* Feedback de ejecución + recordatorio de trazabilidad */}
      <footer className="border-t border-slate-200 px-5 py-3">
        {mensaje !== null && (
          <p
            role="status"
            className={[
              'mb-2 rounded-md px-3 py-2 text-xs font-medium',
              ejecucion === 'exito' ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-800',
            ].join(' ')}
          >
            {mensaje}
          </p>
        )}
        <p className="text-[10px] text-slate-400">
          Todo acto exitoso queda asentado en el <strong>LogAuditoria</strong> inmutable con su
          fundamento legal (Ley 908). El gemelo reproduce el expediente desde ese registro.
        </p>
      </footer>
    </aside>
  );
}
