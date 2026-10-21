/**
 * FlowDiagram — tablero visual del expediente sobre @xyflow/react.
 *
 * Construye el grafo a partir de:
 *   - `nodos` (etapas con semáforo) y `aristas` (transiciones del YAML),
 *     preparados por la página; aquí solo se renderizan de forma declarativa.
 *   - El layout es determinista izquierda→derecha (línea procesal), con
 *     ramas verticales para estados alternativos (inadmisible/en_recurso).
 */

import { useCallback } from 'react';
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type NodeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { StageNode, type StageFlowNode, type StageNodeData } from './nodes/StageNode';

const nodeTypes = { stage: StageNode };

export interface FlowDiagramProps {
  nodos: StageFlowNode[];
  aristas: Edge[];
  /** Callback al hacer clic en un nodo ACTIVO/EN RIESGO (abre el ActionPanel). */
  onNodoActivoClick?: (nodoId: string) => void;
}

export function FlowDiagram({ nodos, aristas, onNodoActivoClick }: FlowDiagramProps) {
  // Nodos no arrastrables ni conectables: el orden del proceso lo fija la ley,
  // no el usuario. Los cambios de selección los gestiona React Flow internamente.
  const onNodesChange = useCallback((_cambios: NodeChange<StageFlowNode>[]) => {
    /* solo-lectura: sin mutación local del grafo */
  }, []);

  const edgesDecoradas: Edge[] = aristas.map((e) => ({
    ...e,
    style: { stroke: '#94a3b8', strokeWidth: 1.5, ...e.style },
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
  }));

  return (
    <div className="h-full w-full" aria-label="Diagrama de etapas procesales">
      <ReactFlow<StageFlowNode, Edge>
        nodes={nodos}
        edges={edgesDecoradas}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        fitView
        minZoom={0.4}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, nodo) => {
          const data = nodo.data as StageNodeData;
          if (data.estadoVisual === 'activa' || data.estadoVisual === 'riesgo') {
            onNodoActivoClick?.(nodo.id);
          }
        }}
      >
        <Background gap={20} size={1} color="#e2e8f0" />
        <Controls showInteractive={false} className="!shadow-md" />
      </ReactFlow>
    </div>
  );
}
