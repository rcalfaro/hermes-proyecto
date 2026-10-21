/**
 * StageNode — nodo personalizado de React Flow para una etapa procesal.
 *
 * Vinculación con el backend: cada nodo representa un ESTADO del catálogo
 * config/flow_reglas.yaml; al ser clickeable solo si está ACTIVA, el click
 * abre el ActionPanel que lista los comandos cuyo `estado_desde` coincide
 * (POST /api/comandos/<command>). El plazo se pinta con los vencimientos
 * deterministas devueltos por GET /api/casos/{id}/plazos.
 */

import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';

import {
  CLASES_ESTADO,
  cuentaRegresiva,
  ETIQUETA_ESTADO_VISUAL,
  type EstadoVisualNodo,
} from '../../lib/semaphore';

/** Data tipada que la página inyecta al construir los nodos del grafo. */
export interface StageNodeData extends Record<string, unknown> {
  etiquetaEtapa: string;
  estadoVisual: EstadoVisualNodo;
  /** Fundamento normativo de la regla YAML que define esta etapa. */
  fundamento: string;
  /** Vencimiento ISO del plazo activo de la etapa (si existe). */
  vencimientoIso?: string | null;
  /** Reloj inyectado desde la página (mismo TimeProvider conceptual del dom). */
  ahora: Date;
  /** CommandName asociado — visible para auditoría visual del vínculo UI↔API. */
  commandVinculado?: string | null;
}

/** Especialización React Flow v12: nodo con data = StageNodeData. */
export type StageFlowNode = Node<StageNodeData, 'stage'>;

const ICONOS: Record<EstadoVisualNodo, string> = {
  completada: '✓', // check
  activa: '▶', // en curso
  bloqueada: '🔒', // candado
  riesgo: '⏳', // reloj de arena (preclusión próxima o vencida)
};

function StageNodeComponent({ data, selected }: NodeProps<StageFlowNode>) {
  const clases = CLASES_ESTADO[data.estadoVisual];
  const esEditable = data.estadoVisual === 'activa' || data.estadoVisual === 'riesgo';
  const regresion =
    data.vencimientoIso !== undefined && data.vencimientoIso !== null
      ? cuentaRegresiva(data.vencimientoIso, data.ahora)
      : null;

  return (
    <div
      role="button"
      tabIndex={esEditable ? 0 : -1}
      aria-disabled={!esEditable}
      title={
        esEditable
          ? `${data.etiquetaEtapa} — ${ETIQUETA_ESTADO_VISUAL[data.estadoVisual]} · ${data.fundamento}`
          : `${data.etiquetaEtapa} — ${ETIQUETA_ESTADO_VISUAL[data.estadoVisual]} (sin actos disponibles aún)`
      }
      className={[
        'w-52 rounded-xl border-2 px-3 py-2 text-left transition-all',
        clases.card,
        selected ? 'scale-[1.03]' : '',
        esEditable ? 'cursor-pointer hover:shadow-lg' : 'cursor-default',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-400" />

      {/* Encabezado: ícono de semáforo + nombre de la etapa */}
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${clases.punto}`}
        >
          {ICONOS[data.estadoVisual]}
        </span>
        <span className={`font-serif text-sm font-semibold leading-tight ${clases.texto}`}>
          {data.etiquetaEtapa}
        </span>
      </div>

      {/* Plazo activo: fecha de vencimiento + cuenta regresiva (motor CPCN) */}
      {regresion !== null && data.vencimientoIso != null && (
        <div className="mt-2 rounded-md bg-white/70 px-2 py-1 text-[11px] font-medium text-slate-700">
          <div>Vence: {new Date(data.vencimientoIso).toLocaleDateString('es-NI')}</div>
          <div className={data.estadoVisual === 'riesgo' ? 'text-red-700 font-bold' : ''}>
            ⏱ {regresion}
          </div>
        </div>
      )}

      {/* Pie: comando CQRS vinculado (auditoría visual del mapeo UI→endpoint) */}
      {data.commandVinculado != null && (
        <div className="mt-1 truncate font-mono text-[9px] text-slate-400">
          POST /api/comandos/{data.commandVinculado}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!bg-slate-400" />
    </div>
  );
}

// memo(): el grafo re-renderiza en cada tick del reloj; los nodos inmutados
// no deben repintarse (rendimiento en tablets de juzgado).
export const StageNode = memo(StageNodeComponent);
