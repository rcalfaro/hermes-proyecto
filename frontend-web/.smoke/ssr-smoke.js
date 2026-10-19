/* Verificación headless: ActionPanel + clasificación RBAC con datos CPCN. */
import { renderToString } from 'react-dom/server';
import React from 'react';
import { ActionPanel } from './src/components/ActionPanel';
import { getAvailableActions } from './src/lib/api';
import { clasificarNodo, evaluarRiesgo } from './src/lib/semaphore';
const plazos = [{
        id: 'p1', tipo_plazo: 'preclusivo', nombre: 'contestacion_demanda',
        fecha_inicio: '2026-03-02', vencimiento: '2026-03-13T23:59:59Z',
        dias_habiles: 10, suspendido: false, vencido: true, fundamento: 'Art. 151 CPCN',
    }];
// a) Demandado con plazo VENCIDO ⇒ contestación bloqueada por preclusión.
const accionesDemandado = getAvailableActions('admitida', 'demandado', plazos);
const contestar = accionesDemandado.find(a => a.etiqueta.includes('Contestación'));
console.assert(contestar.permitida === false, 'FALLO: debía estar bloqueada');
console.assert(contestar.motivo_bloqueo.includes('134'), 'FALLO: motivo preclusión');
// b) Juez en etapa admitida ⇒ no tiene actos propios (traslado es del demandado).
const accionesJuez = getAvailableActions('admitida', 'juez', plazos);
console.assert(accionesJuez.every(a => !a.permitida), 'FALLO: juez sin acto en admitida');
// c) Semáforo: en_tramite con caso en sentenciado ⇒ completada.
console.assert(clasificarNodo('en_tramite', 'sentenciado') === 'completada');
console.assert(clasificarNodo('firme', 'sentenciado') === 'bloqueada');
console.assert(clasificarNodo('sentenciado', 'sentenciado') === 'activa');
// d) Riesgo: plazo vencido detectado contra reloj fijo.
const riesgo = evaluarRiesgo(plazos, new Date('2026-03-14T10:00:00Z'));
console.assert(riesgo !== null && riesgo.nivel === 'vencido', 'FALLO: nivel vencido');
// e) Render del panel sin excepciones (tooltip de bloqueo presente).
const html = renderToString(React.createElement(ActionPanel, {
    abierto: true, tituloEtapa: 'Admisión — Auto Iniciado', estadoActual: 'admitida',
    acciones: accionesDemandado, onCerrar: () => { }, executeCommand: async () => { },
}));
console.assert(html.includes('Requiere rol') || html.includes('Plazo vencido'), 'FALLO: motivo visible');
console.log('SSR-SMOKE OK:', html.length, 'bytes de panel renderizado');
