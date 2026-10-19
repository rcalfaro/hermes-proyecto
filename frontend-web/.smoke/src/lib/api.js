/**
 * lib/api.ts — Cliente HTTP tipado del Gemelo Digital.
 *
 * Cada función es un adaptador 1:1 de un endpoint FastAPI:
 *   getCaseState        → GET  /api/casos/{id}
 *   getCaseHistory      → GET  /api/casos/{id}/historial
 *   getActiveDeadlines  → GET  /api/casos/{id}/plazos
 *   getPublicSimulations→ GET  /api/publico/simulaciones
 *   executeCommand      → POST /api/comandos/<commandName>
 *   getAvailableActions → derivación CLIENTE del catálogo de transiciones
 *                         (espejo de config/flow_reglas.yaml) + RBAC local;
 *                         el backend SIEMPRE revalida (defensa en profundidad).
 */
import { ApiError } from './types';
const BASE_URL = import.meta.env.VITE_API_URL ?? '';
async function request(ruta, init = {}) {
    let response;
    try {
        const opciones = {
            headers: { 'Content-Type': 'application/json', ...init.headers },
            ...(init.method !== undefined ? { method: init.method } : {}),
            ...(init.body !== undefined && init.body !== null ? { body: init.body } : {}),
        };
        if (init.signal !== undefined)
            opciones.signal = init.signal;
        response = await fetch(`${BASE_URL}${ruta}`, opciones);
    }
    catch (cause) {
        throw new ApiError(0, `Sin conexión con el servidor judicial (${ruta})`, cause);
    }
    if (!response.ok) {
        let detail = null;
        try {
            const cuerpo = (await response.json());
            detail = cuerpo.detail ?? cuerpo;
        }
        catch {
            /* respuesta sin JSON */
        }
        // Mensajes canónicos según código HTTP exigido por el backend:
        // 400 validación · 403 permiso · 409 conflicto de estado · 422 esquema.
        const mensajes = {
            400: 'Datos del acto procesal inválidos.',
            403: 'Su rol no está autorizado para este acto.',
            404: 'Expediente no encontrado.',
            409: 'El caso no se encuentra en la etapa requerida para esta acción.',
            422: 'El request no cumple el esquema del comando.',
        };
        throw new ApiError(response.status, typeof detail === 'string' ? detail : (mensajes[response.status] ?? `Error HTTP ${response.status}`), detail);
    }
    return (await response.json());
}
/* ------------------------------------------------------------------ */
/* Query side (lectura)                                               */
/* ------------------------------------------------------------------ */
/** Fotografía del expediente: estado actual + pretensiones (ADN del proceso). */
export function getCaseState(casoId, signal) {
    return request(`/api/casos/${casoId}`, { method: 'GET', ...(signal !== undefined ? { signal } : {}) });
}
/** Log de auditoría inmutable — trazabilidad completa del expediente. */
export function getCaseHistory(casoId, signal) {
    return request(`/api/casos/${casoId}/historial`, {
        method: 'GET',
        ...(signal !== undefined ? { signal } : {}),
    });
}
/** Plazos activos con vencimientos calculados por el motor determinista. */
export function getActiveDeadlines(casoId, signal) {
    return request(`/api/casos/${casoId}/plazos`, { method: 'GET', ...(signal !== undefined ? { signal } : {}) });
}
/** Simulaciones públicas anonimizadas (sin nombres ni cédulas — Ley 787). */
export function getPublicSimulations(signal) {
    return request('/api/publico/simulaciones', {
        method: 'GET',
        ...(signal !== undefined ? { signal } : {}),
    });
}
/**
 * Ejecuta un acto procesal contra el handler correspondiente.
 * El endpoint solo parsea e instancia el comando; guardas/RBAC/plazos
 * los aplica el CaseFlowEngine dentro del Unit of Work (transacción atómica).
 */
export function executeCommand(commandName, payload, signal) {
    return request(`/api/comandos/${commandName}`, {
        method: 'POST',
        body: JSON.stringify(payload),
        ...(signal !== undefined ? { signal } : {}),
    });
}
export const REGLAS_FLUJO = [
    {
        estado_desde: 'borrador',
        disparador: 'presentar_demanda',
        command: 'presentar-demanda',
        etiqueta: 'Presentar Demanda',
        roles_autorizados: ['demandante', 'apoderado_judicial_demandante'],
        requisito_normativo: 'Arts. 37 y 146 CPCN: promoción de la demanda.',
    },
    {
        estado_desde: 'presentado',
        disparador: 'demanda_admitida',
        command: 'admitir-demanda',
        etiqueta: 'Dictar Auto Iniciado (Admisión)',
        roles_autorizados: ['juez'],
        requisito_normativo: 'Art. 148 CPCN: auto iniciado que admite la demanda.',
    },
    {
        estado_desde: 'inadmisible_reformable',
        disparador: 'presentar_demanda',
        command: 'presentar-demanda',
        etiqueta: 'Subsanar y Replantear Demanda',
        roles_autorizados: ['demandante', 'apoderado_judicial_demandante'],
        requisito_normativo: 'Art. 147 CPCN: subsanación dentro de tercero día.',
    },
    {
        estado_desde: 'admitida',
        disparador: 'contestar_demanda',
        command: 'contestar-demanda',
        etiqueta: 'Presentar Contestación y Excepciones',
        roles_autorizados: ['demandado', 'apoderado_judicial_demandado'],
        requisito_normativo: 'Art. 151 CPCN: traslado de diez días para contestar.',
        plazo_requerido: 'contestacion_demanda',
    },
    {
        estado_desde: 'contestada',
        disparador: 'apertura_a_pruebas',
        command: null, // Handler pendiente: se muestra bloqueado con motivo (Art. 165).
        etiqueta: 'Apertura a Período Probatorio',
        roles_autorizados: ['juez'],
        requisito_normativo: 'Art. 165 CPCN: audiencia y apertura a período probatorio.',
    },
    {
        estado_desde: 'en_tramite',
        disparador: 'dictar_sentencia',
        command: 'dictar-sentencia',
        etiqueta: 'Dictar Sentencia Definitiva',
        roles_autorizados: ['juez'],
        requisito_normativo: 'Arts. 192-201 CPCN: sentencia definitiva, motiva el petitum.',
    },
    {
        estado_desde: 'sentenciado',
        disparador: 'apelar_sentencia',
        command: 'apelar-sentencia',
        etiqueta: 'Interponer Recurso de Apelación',
        roles_autorizados: [
            'demandante',
            'demandado',
            'apoderado_judicial_demandante',
            'apoderado_judicial_demandado',
        ],
        requisito_normativo: 'Arts. 246-248 CPCN: apelación en quinto día.',
        plazo_requerido: 'termino_apelacion',
    },
    {
        estado_desde: 'firme',
        disparador: 'iniciar_ejecucion',
        command: 'ejecutar-sentencia',
        etiqueta: 'Iniciar Ejecución Forzosa',
        roles_autorizados: ['demandante', 'apoderado_judicial_demandante'],
        requisito_normativo: 'Arts. 263 y ss. CPCN: ejecución forzosa de lo resuelto.',
        plazo_requerido: 'ejecucion_forzosa',
    },
];
// NOTA: la apertura a pruebas (Art. 165) no tiene comando propio en esta fase;
// el panel la lista como informativamente bloqueada hasta implementar el handler.
const ETIQUETAS_ROL = {
    juez: 'Juez',
    demandante: 'Demandante',
    demandado: 'Demandado',
    apoderado_judicial_demandante: 'Apoderado del Demandante',
    apoderado_judicial_demandado: 'Apoderado del Demandado',
    tercero_interviniente: 'Tercero Interviniente',
};
export function etiquetaRol(rol) {
    return ETIQUETAS_ROL[rol];
}
/**
 * Acciones visibles para `rol` sobre el caso en `estadoActual`.
 *
 * Regla de UX crítica: las acciones fuera de rol o de estado NO se ocultan,
 * se devuelven `permitida: false` con `motivo_bloqueo` legible para tooltip
 * ("Requiere rol de Juez", "Plazo vencido (preclusión, Art. 134 CPCN)").
 * La autorización real la decide siempre el backend al ejecutar.
 */
export function getAvailableActions(estadoActual, rolUsuario, plazos = []) {
    return REGLAS_FLUJO.map((regla) => {
        const enEstadoCorrecto = regla.estado_desde === estadoActual;
        const tieneRol = regla.roles_autorizados.includes(rolUsuario);
        const plazoVencido = regla.plazo_requerido !== undefined &&
            plazos.some((p) => p.nombre === regla.plazo_requerido && p.vencido && !p.suspendido);
        let motivo = null;
        if (regla.command === null) {
            // Acto procesal sin handler CQRS todavía: bloqueado con explicación.
            motivo = 'Acto en gestión del juzgado — comando no habilitado en esta versión.';
        }
        else if (!enEstadoCorrecto) {
            motivo = `Disponible solo en la etapa «${reemplazar(regla.estado_desde)}» (etapa actual: «${reemplazar(estadoActual)}»).`;
        }
        else if (!tieneRol) {
            const rolesTxt = regla.roles_autorizados.map(etiquetaRol).join(' o ');
            motivo = `Requiere rol de ${rolesTxt}.`;
        }
        else if (plazoVencido) {
            motivo = 'Plazo vencido — preclusión de la facultad (Art. 134 CPCN).';
        }
        return {
            command: regla.command ?? 'presentar-demanda', // nunca se ejecuta si permitida=false
            etiqueta: regla.etiqueta,
            disparador: regla.disparador,
            roles_autorizados: [...regla.roles_autorizados],
            requisito_normativo: regla.requisito_normativo,
            permitida: regla.command !== null && enEstadoCorrecto && tieneRol && !plazoVencido,
            ...(motivo !== null ? { motivo_bloqueo: motivo } : { motivo_bloqueo: null }),
        };
    });
}
function reemplazar(clave) {
    return clave.replaceAll('_', ' ');
}
