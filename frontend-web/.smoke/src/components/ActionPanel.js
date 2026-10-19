import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
import { ApiError } from '../lib/types';
export function ActionPanel({ abierto, tituloEtapa, estadoActual, acciones, executeCommand, onCerrar, }) {
    const [ejecucion, setEjecucion] = useState('idle');
    const [mensaje, setMensaje] = useState(null);
    const [comandoEnCurso, setComandoEnCurso] = useState(null);
    if (!abierto)
        return null;
    const handleEjecutar = async (accion) => {
        if (!accion.permitida || ejecucion === 'enviando')
            return;
        setEjecucion('enviando');
        setComandoEnCurso(accion.command);
        setMensaje(null);
        try {
            // El payload mínimo lo completa la página (caso_id/actor_id); aquí se
            // agrega el disparador para trazabilidad cross-side.
            await executeCommand(accion.command, { disparador: accion.disparador });
            setEjecucion('exito');
            setMensaje(`✓ ${accion.etiqueta} registrado en LogAuditoria.`);
        }
        catch (err) {
            setEjecucion('error');
            setMensaje(err instanceof ApiError
                ? `⚠️ (${err.status}) ${err.message}`
                : 'No fue posible contactar al servidor judicial.');
        }
        finally {
            setComandoEnCurso(null);
        }
    };
    return (_jsxs("aside", { className: "fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl", "aria-label": `Acciones disponibles — ${tituloEtapa}`, children: [_jsxs("header", { className: "flex items-start justify-between border-b border-slate-200 px-5 py-4", children: [_jsxs("div", { children: [_jsx("p", { className: "text-[11px] font-semibold uppercase tracking-widest text-sky-700", children: "Actos procesales habilitados" }), _jsx("h2", { className: "font-serif text-lg font-bold text-ink", children: tituloEtapa }), _jsxs("p", { className: "text-xs text-slate-500", children: ["Estado del expediente: ", _jsx("span", { className: "font-mono", children: estadoActual })] })] }), _jsx("button", { onClick: onCerrar, "aria-label": "Cerrar panel", className: "rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700", children: "\u2715" })] }), _jsx("ul", { className: "flex-1 space-y-3 overflow-y-auto px-5 py-4", children: acciones.map((accion) => {
                    const cargando = ejecucion === 'enviando' && comandoEnCurso === accion.command;
                    return (_jsx("li", { children: _jsx("div", { className: accion.permitida ? '' : 'accion-deshabilitada', title: accion.motivo_bloqueo ?? undefined, children: _jsxs("button", { disabled: !accion.permitida || ejecucion === 'enviando', onClick: () => void handleEjecutar(accion), className: [
                                    'w-full rounded-lg border px-4 py-3 text-left transition-colors',
                                    accion.permitida
                                        ? 'border-sky-300 bg-sky-50 hover:bg-sky-100 active:bg-sky-200'
                                        : 'border-slate-200 bg-slate-50 opacity-60',
                                    cargando ? 'animate-pulse' : '',
                                ].join(' '), children: [_jsxs("span", { className: "flex items-center justify-between gap-2", children: [_jsxs("span", { className: "font-serif text-sm font-semibold text-ink", children: [accion.permitida ? '⚖' : '🔒', " ", accion.etiqueta, cargando ? ' …' : ''] }), _jsxs("span", { className: "font-mono text-[9px] text-slate-400", children: ["/", accion.command] })] }), _jsx("span", { className: "mt-1 block text-[11px] leading-snug text-slate-500", children: accion.requisito_normativo }), !accion.permitida && accion.motivo_bloqueo !== null && (_jsx("span", { className: "mt-1 block text-[11px] font-medium text-red-700", children: accion.motivo_bloqueo }))] }) }) }, `${accion.command}-${accion.disparador}`));
                }) }), _jsxs("footer", { className: "border-t border-slate-200 px-5 py-3", children: [mensaje !== null && (_jsx("p", { role: "status", className: [
                            'mb-2 rounded-md px-3 py-2 text-xs font-medium',
                            ejecucion === 'exito' ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-800',
                        ].join(' '), children: mensaje })), _jsxs("p", { className: "text-[10px] text-slate-400", children: ["Todo acto exitoso queda asentado en el ", _jsx("strong", { children: "LogAuditoria" }), " inmutable con su fundamento legal (Ley 908). El gemelo reproduce el expediente desde ese registro."] })] })] }));
}
