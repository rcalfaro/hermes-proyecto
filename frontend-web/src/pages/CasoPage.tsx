/**
 * Página principal del tablero: app/caso/[id] (App Router) portada a Vite con
 * ruta dinámica equivalente (/caso/:id). Orquesta diagrama + panel + datos.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Edge } from '@xyflow/react';

import { FlowDiagram } from '../components/FlowDiagram';
import { ActionPanel } from '../components/ActionPanel';
import type { StageFlowNode } from '../components/nodes/StageNode';
import {
  executeCommand as apiExecuteCommand,
  getActiveDeadlines,
  getAvailableActions,
  getCaseState,
  REGLAS_FLUJO,
} from '../lib/api';
import {
  clasificarNodo,
  evaluarRiesgo,
  LINEA_PROCESAL,
  type EstadoVisualNodo,
} from '../lib/semaphore';
import type {
  CommandName,
  DetalleCasoDTO,
  EstadoProcesal,
  PlazoDTO,
  RolUsuario,
} from '../lib/types';
import { ApiError } from '../lib/types';

/* ETIQUETAS legibles por estado (terminología civil nicaragüense). */
const ETIQUETA_ESTADO: Record<string, string> = {
  borrador: 'Borrador de Demanda',
  presentado: 'Demanda Presentada',
  admitida: 'Admisión — Auto Iniciado',
  inadmisible_reformable: 'Inadmisible Reformable',
  contestada: 'Contestación y Excepciones',
  en_tramite: 'Período Probatorio',
  sentenciado: 'Sentencia Definitiva',
  en_recurso: 'En Recurso (Apelación)',
  firme: 'Ejecutoria / Sentencia Firme',
  en_ejecucion: 'Ejecución Forzosa',
  terminado: 'Terminado — Archivo',
};

function etiquetaDe(estado: string): string {
  return ETIQUETA_ESTADO[estado] ?? estado.replaceAll('_', ' ');
}

/**
 * Mapeo disparador → estado destino (espejo de `estado_hacia` en el YAML).
 * Permite etiquetar cada arista con el acto procesal exacto que la cruza.
 */
const DISPARADOR_A_ESTADO: Record<string, EstadoProcesal> = {
  presentar_demanda: 'presentado',
  demanda_admitida: 'admitida',
  declarar_inadmisible: 'inadmisible_reformable',
  contestar_demanda: 'contestada',
  apertura_a_pruebas: 'en_tramite',
  dictar_sentencia: 'sentenciado',
  apelar_sentencia: 'en_recurso',
  declaratoria_firme: 'firme',
  iniciar_ejecucion: 'en_ejecucion',
  terminar_ejecucion: 'terminado',
};

function disparadorLlevaA(disparador: string, destino: string): boolean {
  return DISPARADOR_A_ESTADO[disparador] === destino;
}

export interface CasoPageProps {
  casoId: string;
  /** En producción esto viene del JWT (Depends de FastAPI); aquí se selecciona. */
  rolInicial?: RolUsuario;
}

export default function CasoPage({ casoId, rolInicial = 'juez' }: CasoPageProps) {
  const [detalle, setDetalle] = useState<DetalleCasoDTO | null>(null);
  const [plazos, setPlazos] = useState<PlazoDTO[]>([]);
  const [rol, setRol] = useState<RolUsuario>(rolInicial);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nodoSeleccionado, setNodoSeleccionado] = useState<string | null>(null);
  // Reloj de la UI: análogo frontend del TimeProvider inyectable del dominio.
  const [ahora, setAhora] = useState(() => new Date());

  /* Carga inicial + refresco tras cada comando (read-your-writes). */
  const cargar = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const [d, p] = await Promise.all([getCaseState(casoId), getActiveDeadlines(casoId)]);
      setDetalle(d);
      setPlazos(p);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Error inesperado al cargar el expediente.');
    } finally {
      setCargando(false);
    }
  }, [casoId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Tick de cuenta regresiva (1 min basta para plazos en días).
  useEffect(() => {
    const t = setInterval(() => setAhora(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  /* ---- Grafo: nodos = línea procesal + ramas; aristas = reglas YAML ---- */
  const { nodos, aristas } = useMemo(() => {
    if (detalle === null) return { nodos: [] as StageFlowNode[], aristas: [] as Edge[] };
    const estadoActual = detalle.caso.estado_actual;

    const estadosGrafo: string[] = [...LINEA_PROCESAL];
    if (!estadosGrafo.includes(estadoActual)) estadosGrafo.push(estadoActual);

    const X0 = 40;
    const DX = 280;
    const Y_MAIN = 160;
    const Y_RAMAS = 320;

    const riesgo = evaluarRiesgo(plazos, ahora);
    // Plazo lógico asociado a cada etapa (nombre usado por el motor de plazos).
    const PLAZO_DE_ESTADO: Partial<Record<EstadoProcesal, string>> = {
      admitida: 'contestacion_demanda',
      sentenciado: 'termino_apelacion',
      firme: 'ejecucion_forzosa',
    };
    const nodes: StageFlowNode[] = estadosGrafo.map((estado, i) => {
      const visualBase: EstadoVisualNodo = clasificarNodo(estado as EstadoProcesal, estadoActual);
      // La etapa activa pasa a 🔴 si su plazo está en riesgo o vencido.
      const esActiva = visualBase === 'activa';
      const nombrePlazoEtapa = PLAZO_DE_ESTADO[estado as EstadoProcesal];
      const plazoDeEtapa =
        nombrePlazoEtapa !== undefined
          ? plazos.find((p) => p.nombre === nombrePlazoEtapa)
          : undefined;
      const visual: EstadoVisualNodo =
        esActiva &&
        ((plazoDeEtapa !== undefined && new Date(plazoDeEtapa.vencimiento) <= ahora) ||
          (riesgo !== null && riesgo.nivel !== 'vigente' && nombrePlazoEtapa !== undefined))
          ? 'riesgo'
          : visualBase;

      const esRama = estado === 'inadmisible_reformable' || estado === 'en_recurso';
      const regla = REGLAS_FLUJO.find((r) => r.estado_desde === estado);

      return {
        id: estado,
        type: 'stage',
        position: esRama ? { x: X0 + DX * 1.5, y: Y_RAMAS } : { x: X0 + DX * i, y: Y_MAIN },
        data: {
          etiquetaEtapa: etiquetaDe(estado),
          estadoVisual: visual,
          fundamento: regla?.requisito_normativo ?? 'Etapa del juicio ordinario civil (Ley 908).',
          ...(esActiva && plazoDeEtapa !== undefined
            ? { vencimientoIso: plazoDeEtapa.vencimiento }
            : {}),
          ahora,
          ...(regla !== undefined && regla.command !== null
            ? { commandVinculado: regla.command }
            : {}),
        },
      };
    });

    // Aristas encadenadas sobre la línea principal + flechas hacia las ramas.
    const edges: Edge[] = [];
    const principales = LINEA_PROCESAL.filter((e) => estadosGrafo.includes(e));
    for (let i = 0; i < principales.length - 1; i++) {
      const src = principales[i];
      const dst = principales[i + 1];
      if (src === undefined || dst === undefined) continue;
      // Regla YAML cuyo estado destino coincide ⇒ etiqueta = disparador real.
      const regla = REGLAS_FLUJO.find(
        (r) => r.estado_desde === src && disparadorLlevaA(r.disparador, dst),
      );
      edges.push({
        id: `${src}->${dst}`,
        source: src,
        target: dst,
        ...(regla !== undefined ? { label: regla.disparador.replaceAll('_', ' ') } : {}),
        animated: clasificarNodo(src as EstadoProcesal, estadoActual) === 'activa',
      });
    }
    edges.push({
      id: 'presentado->inadmisible',
      source: 'presentado',
      target: 'inadmisible_reformable',
      label: 'declarar inadmissible',
      style: { strokeDasharray: '5 4' },
    });
    edges.push({
      id: 'sentenciado->recurso',
      source: 'sentenciado',
      target: 'en_recurso',
      label: 'apelar sentencia',
      style: { strokeDasharray: '5 4' },
    });

    return { nodos: nodes, aristas: edges };
  }, [detalle, plazos, ahora]);

  /* ---- Acciones del panel (RBAC local espejo del YAML; revalida el server) ---- */
  // El nodo clickeado define la etapa origen: solo se listan actos cuyo
  // estado_desde coincide con él ⇒ "solo los comandos que el usuario puede
  // ejecutar EN ESA etapa" (requisito del tablero contextual).
  const acciones = useMemo(() => {
    if (detalle === null || nodoSeleccionado === null) return [];
    return getAvailableActions(
      nodoSeleccionado as EstadoProcesal,
      rol,
      plazos,
    ).filter((a) => a.disparador !== '');
  }, [detalle, rol, plazos, nodoSeleccionado]);

  const manejarComando = useCallback(
    async (command: CommandName, payloadExtra: Record<string, unknown>) => {
      await apiExecuteCommand(command, {
        caso_id: casoId,
        actor_id: '00000000-0000-0000-0000-000000000000', // lo resuelve el backend por sesión
        ...payloadExtra,
      });
      setNodoSeleccionado(null);
      await cargar(); // read-your-writes: repinta semáforo desde el server
    },
    [casoId, cargar],
  );

  /* ---------------------------- render ---------------------------- */
  if (cargando) {
    return (
      <div className="flex h-full items-center justify-center bg-parchment">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-sky-200 border-t-sky-600" />
          <p className="mt-3 font-serif text-sm text-slate-600">Cargando expediente…</p>
        </div>
      </div>
    );
  }

  if (error !== null || detalle === null) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-parchment p-6">
        <p className="rounded-lg bg-red-50 px-4 py-2 font-medium text-red-800">⚠️ {error}</p>
        <button
          onClick={() => {
            setCargando(true);
            void cargar();
          }}
          className="rounded-md bg-sky-700 px-4 py-2 text-white hover:bg-sky-800"
        >
          Reintentar
        </button>
      </div>
    );
  }

  const nodoActivo = nodos.find((n) => n.id === nodoSeleccionado);

  return (
    <div className="flex h-full flex-col bg-parchment">
      {/* Barra superior: identidad del expediente + selector de rol (demo) */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div>
          <h1 className="font-serif text-lg font-bold text-ink">
            Expediente {detalle.caso.numero_expediente}
          </h1>
          <p className="text-xs text-slate-500">
            {detalle.caso.materia} · {detalle.caso.juzgado_asignado} · Pretensiones:{' '}
            {detalle.pretensiones.length}
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
          Sesión como:
          <select
            value={rol}
            onChange={(e) => setRol(e.target.value as RolUsuario)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs"
            title="Cambia el rol para auditar cómo ve cada actor el mismo expediente"
          >
            <option value="juez">Juez</option>
            <option value="demandante">Demandante</option>
            <option value="demandado">Demandado</option>
            <option value="apoderado_judicial_demandante">Apoderado Demandante</option>
            <option value="apoderado_judicial_demandado">Apoderado Demandado</option>
          </select>
        </label>
      </header>

      {/* Leyenda del semáforo (autoexplicativa para usuarios de juzgado) */}
      <div className="flex flex-wrap gap-4 border-b border-slate-100 bg-white/60 px-4 py-2 text-[11px] text-slate-600">
        <span>🟢 Completada</span>
        <span>🔵 Etapa activa</span>
        <span>⚪ Bloqueada (depende de la actual)</span>
        <span>🔴 En riesgo / preclusión</span>
        <span className="ml-auto italic">
          Clic en la etapa activa para ver los actos que su rol puede ejecutar
        </span>
      </div>

      {/* Tablero: React Flow ocupa el alto restante (usable en tablet táctil) */}
      <main className="relative min-h-0 flex-1">
        <FlowDiagram
          nodos={nodos}
          aristas={aristas}
          onNodoActivoClick={(id) => setNodoSeleccionado(id)}
        />
      </main>

      <ActionPanel
        abierto={nodoActivo !== undefined}
        tituloEtapa={nodoActivo?.data.etiquetaEtapa ?? ''}
        estadoActual={detalle.caso.estado_actual}
        acciones={acciones}
        executeCommand={manejarComando}
        onCerrar={() => setNodoSeleccionado(null)}
      />
    </div>
  );
}
