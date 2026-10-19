/**
 * Semáforo visual del tablero — mapea estado procesal + plazo → color/nodo.
 *
 * Estados visuales exigidos por el diseño:
 *   🟢 completada  🔵 activa  ⚪ bloqueada  🔴 en riesgo / preclusión
 */
/** Línea de tiempo canónica del juicio ordinario civil (orden del proceso). */
export const LINEA_PROCESAL = [
    'borrador',
    'presentado',
    'admitida',
    'contestada',
    'en_tramite',
    'sentenciado',
    'firme',
    'en_ejecucion',
    'terminado',
];
/** Etapas intermedias/alternativas que se pintan tras su predecessor lógico. */
const ORDEN_EXTENDIDO = {
    inadmisible_reformable: 1.5, // ramifica desde "presentado"
    en_recurso: 6.5, // ramifica desde "sentenciado"
    archivado: 9,
};
function posicion(estado) {
    const idx = LINEA_PROCESAL.indexOf(estado);
    return idx >= 0 ? idx : (ORDEN_EXTENDIDO[estado] ?? -1);
}
/**
 * Estado visual de un nodo de etapa dado el estado actual del caso.
 * Nodos ya superados → completada; el presente → activa; futuros → bloqueada.
 */
export function clasificarNodo(estadoNodo, estadoActual) {
    const pNodo = posicion(estadoNodo);
    const pActual = posicion(estadoActual);
    if (pNodo < pActual)
        return 'completada';
    if (pNodo === pActual)
        return 'activa';
    return 'bloqueada';
}
/** Umbral legal de "riesgo": menos de 2 días naturales para el vencimiento. */
const UMBRAL_RIESGO_MS = 2 * 24 * 60 * 60 * 1000;
/**
 * Evalúa el plazo más crítico de la etapa activa contra `ahora`
 * (el reloj lo inyecta quien llama ⇒ determinismo y testabilidad).
 */
export function evaluarRiesgo(plazos, ahora) {
    const relevantes = plazos.filter((p) => !p.suspendido);
    if (relevantes.length === 0)
        return null;
    let critico = null;
    for (const p of relevantes) {
        if (critico === null || new Date(p.vencimiento) < new Date(critico.vencimiento)) {
            critico = p;
        }
    }
    if (critico === null)
        return null;
    const restanteMs = new Date(critico.vencimiento).getTime() - ahora.getTime();
    const nivel = restanteMs <= 0 ? 'vencido' : restanteMs < UMBRAL_RIESGO_MS ? 'riesgo' : 'vigente';
    return { nivel, plazo: critico };
}
/** Clases Tailwind por estado visual (borde + fondo + punto del semáforo). */
export const CLASES_ESTADO = {
    completada: {
        card: 'border-emerald-300 bg-emerald-50',
        punto: 'bg-emerald-500',
        texto: 'text-emerald-800',
    },
    activa: {
        card: 'border-sky-400 bg-sky-50 shadow-md ring-2 ring-sky-200',
        punto: 'bg-sky-500 animate-pulse',
        texto: 'text-sky-900',
    },
    bloqueada: {
        card: 'border-slate-200 bg-slate-50 opacity-70',
        punto: 'bg-slate-300',
        texto: 'text-slate-500',
    },
    riesgo: {
        card: 'border-red-400 bg-red-50 shadow-md ring-2 ring-red-200',
        punto: 'bg-red-500 animate-pulse',
        texto: 'text-red-800',
    },
};
export const ETIQUETA_ESTADO_VISUAL = {
    completada: 'Completada',
    activa: 'Etapa activa',
    bloqueada: 'Bloqueada',
    riesgo: 'En riesgo — plazo crítico',
};
/** Cuenta regresiva humana: "3 d 12 h" / "VENCIDO". */
export function cuentaRegresiva(vencimientoIso, ahora) {
    const restanteMs = new Date(vencimientoIso).getTime() - ahora.getTime();
    if (restanteMs <= 0)
        return 'VENCIDO';
    const dias = Math.floor(restanteMs / 86_400_000);
    const horas = Math.floor((restanteMs % 86_400_000) / 3_600_000);
    return dias > 0 ? `${dias} d ${horas} h` : `${horas} h`;
}
