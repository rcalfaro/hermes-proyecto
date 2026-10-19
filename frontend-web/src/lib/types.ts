/**
 * Tipos compartidos del Gemelo Digital — espejo exacto de los DTOs Pydantic
 * del backend FastAPI (app/api/queries.py y app/api/endpoints.py).
 *
 * Convención: los estados/etapas llegan como strings crudos del enum Python
 * (EstadoProcesal / EtapaProcesal), por eso se modelan como uniones literales
 * para que el compilador obligue a cubrir cada valor en el semáforo visual.
 */

/** EstadoProcesal (Ley 908, CPCN) — app/db/base.py */
export type EstadoProcesal =
  | 'borrador'
  | 'presentado'
  | 'admitida'
  | 'inadmisible_reformable'
  | 'contestada'
  | 'en_tramite'
  | 'sentenciado'
  | 'en_recurso'
  | 'firme'
  | 'en_ejecucion'
  | 'terminado'
  | 'archivado';

/** EtapaProcesal — app/db/base.py */
export type EtapaProcesal =
  | 'calificacion_demanda'
  | 'traslado_demanda'
  | 'audiencia_conciliacion'
  | 'periodos_pruebas'
  | 'audiencia_juicio'
  | 'sentencia'
  | 'recursos'
  | 'ejecucion'
  | 'archivo_definitivo';

/** RolActor — terminología civil estricta (nunca "acusador"/"fiscal"). */
export type RolUsuario =
  | 'juez'
  | 'demandante'
  | 'demandado'
  | 'apoderado_judicial_demandante'
  | 'apoderado_judicial_demandado'
  | 'tercero_interviniente';

/** Nombre canónico del comando CQRS ( coincide con la ruta del endpoint ). */
export type CommandName =
  | 'presentar-demanda'
  | 'admitir-demanda'
  | 'contestar-demanda'
  | 'dictar-sentencia'
  | 'apelar-sentencia'
  | 'ejecutar-sentencia';

/** GET /api/casos/{id} → dict con `caso` + `pretensiones`. */
export interface EstadoCasoDTO {
  id: string;
  numero_expediente: string;
  tipo_proceso: string;
  materia: string;
  juzgado_asignado: string;
  etapa_actual: EtapaProcesal;
  estado_actual: EstadoProcesal;
  estado_anterior: EstadoProcesal | null;
  cuantia: number | null;
  fecha_presentacion_demanda: string | null;
  fecha_admision: string | null;
  cerrado: boolean;
}

export interface PretensionDTO {
  codigo_tipo: string;
  orden: number;
  descripcion: string;
  es_principal: boolean;
  resuelta: boolean;
  sentido_fallo: string | null;
}

export interface DetalleCasoDTO {
  caso: EstadoCasoDTO;
  pretensiones: PretensionDTO[];
}

/** GET /api/casos/{id}/historial — LogAuditoria inmutable. */
export interface EntradaAuditoriaDTO {
  id: number;
  timestamp_evento: string;
  accion: string;
  entidad_afectada: string;
  actor_id: string | null;
  estado_antes: string | null;
  estado_despues: string | null;
  fundamento_legal: string | null;
  detalle: Record<string, unknown>;
}

/** GET /api/casos/{id}/plazos — salida del motor de plazos determinista. */
export interface PlazoDTO {
  id: string;
  tipo_plazo: 'preclusivo' | 'no_preclusivo';
  nombre: string;
  fecha_inicio: string;
  vencimiento: string; // ISO datetime (23:59:59 del último día hábil)
  dias_habiles: number;
  suspendido: boolean;
  vencido: boolean;
  fundamento: string;
}

/** Acción autorizada devuelta por getAvailableActions (derivada local del YAML). */
export interface AccionDisponible {
  command: CommandName;
  etiqueta: string;
  disparador: string;
  roles_autorizados: RolUsuario[];
  requisito_normativo: string;
  /** false ⇒ se muestra deshabilitada CON motivo (nunca oculta: UX jurídica). */
  permitida: boolean;
  motivo_bloqueo: string | null;
}

/** Resultado de POST /api/comandos/<cmd> (resumen de acreditación). */
export interface ResultadoComandoDTO {
  caso_id: string;
  command: CommandName;
  estado_resultante: EstadoProcesal;
  etapa_resultante: EtapaProcesal;
  auditoria_id: number | null;
  fundamento_legal: string;
}

/** GET /api/publico/simulaciones — vista anonimizada. */
export interface SimulacionPublicaDTO {
  clave_simulacion: string;
  materia: string;
  tipo_proceso: string;
  secuencia_estados: EstadoProcesal[];
  duracion_dias: number | null;
  resultado: string | null;
}

/** Error HTTP normalizado del backend (FastAPI { detail } o validación 422). */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
