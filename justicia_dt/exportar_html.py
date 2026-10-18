"""
JUSTICIA-DT Nicaragua — Exportador a HTML.

Genera un dashboard web autocontenido (un solo archivo .html, sin dependencias
externas ni CDN) a partir del motor app.py. Incluye:
  - Arquitectura de la aplicación (§3.1)
  - Los 9 módulos (§3.2) con sus resultados reales
  - Flujo de uso en 5 pasos (§3.3)
  - Formulario interactivo: el abogado selecciona pretensión/subtipo, ingresa
    datos del caso y el DT recalcula escenarios/duración/anomalías en el
    navegador (lógica JS portada fielmente del núcleo Python, mismo seed).

Uso:  python justicia_dt/exportar_html.py
Sale: justicia_dt/index.html
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (  # noqa: E402
    PRETENSIONES, SUBTIPO_A_PRETENSION, FLUJO_ETAPAS, ESCENARIOS,
    JusticiaDT, NucleoDT,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(HERE, "index.html")


# ---------------------------------------------------------------------------
# Datos de catálogo serializados para el cliente (JS)
# ---------------------------------------------------------------------------

def catalogo_js() -> dict:
    return {
        "pretensiones": {
            k: {
                "nombre": v["nombre"],
                "descripcion": v["descripcion"],
                "duracion_tipica_meses": list(v["duracion_tipica_meses"]),
                "subtipos": v["subtipos"],
                "requisitos": v["requisitos"],
                "pruebas": v["pruebas"],
                "duracion_base": v["duracion_base"],
                "escenarios": v["escenarios"],
            } for k, v in PRETENSIONES.items()
        },
        "subtipo_a_pretension": SUBTIPO_A_PRETENSION,
        "flujo_etapas": FLUJO_ETAPAS,
        "escenarios": ESCENARIOS,
    }


# ---------------------------------------------------------------------------
# Ejecución de la demo (§5) para precargar resultados reales del motor Python
# ---------------------------------------------------------------------------

def demo_data() -> dict:
    app = JusticiaDT(seed=902)
    salida = app.flujo_completo(
        seleccion={"pretension": "de_condena", "subtipo": "incumplimiento"},
        datos_caso={
            "demandante": "Empresa A", "demandado": "Empresa B",
            "hechos": "Contrato de prestación de servicios incumplido por falta de pago.",
            "fundamentos_juridicos": "Arts. 2440 y siguientes CC (incumplimiento contractual).",
            "cuantia_usd": 50000, "juzgado": "Civil de Managua",
            "pruebas": ["contrato", "facturas", "correos"],
        },
    )
    dt = NucleoDT(seed=902)
    return {
        "informe": salida["informe"],
        "dashboard_texto": salida["dashboard"],
        "grafo": dt.grafo_caso(salida["caso"]),
    }


# ---------------------------------------------------------------------------
# Plantilla HTML autocontenida
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JUSTICIA-DT Nicaragua — Gemelo Digital para Juicios Civiles</title>
<style>
:root{
  --azul:#0b3d6b; --azul2:#155a9c; --dorado:#c9a227; --fondo:#f4f7fb;
  --verde:#1e8a4e; --amarillo:#c98a1b; --rojo:#b3261e; --gris:#5a6b7d;
  --tarjeta:#ffffff; --borde:#dbe4ee;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,Arial,sans-serif;background:var(--fondo);color:#1c2b3a;line-height:1.55}
header{background:linear-gradient(135deg,var(--azul),var(--azul2));color:#fff;padding:28px 24px}
header h1{font-size:1.6rem;letter-spacing:.5px}
header p{opacity:.9;font-size:.95rem;margin-top:6px}
.badge{display:inline-block;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.35);
  border-radius:20px;padding:2px 12px;font-size:.78rem;margin-top:10px}
main{max-width:1200px;margin:0 auto;padding:24px}
nav{position:sticky;top:0;z-index:50;background:#fff;border-bottom:2px solid var(--borde);
  display:flex;flex-wrap:wrap;gap:4px;padding:8px 16px;box-shadow:0 2px 6px rgba(0,0,0,.06)}
nav button{border:none;background:transparent;padding:8px 14px;border-radius:8px;cursor:pointer;
  font-size:.88rem;color:var(--gris);font-weight:600}
nav button:hover{background:#eef3fa;color:var(--azul)}
nav button.activo{background:var(--azul);color:#fff}
section.tab{display:none}.section-visible{display:block}
h2{color:var(--azul);margin:18px 0 12px;font-size:1.25rem;border-left:5px solid var(--dorado);padding-left:10px}
h3{color:var(--azul2);margin:14px 0 8px;font-size:1.02rem}
.tarjeta{background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px;
  padding:18px;margin-bottom:16px;box-shadow:0 1px 4px rgba(11,61,107,.07)}
.grid{display:grid;gap:14px}
.g3{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.g2{grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th{background:var(--azul);color:#fff;text-align:left;padding:8px 10px}
td{padding:7px 10px;border-bottom:1px solid var(--borde)}
tr:hover td{background:#f0f5fb}
.pill{display:inline-block;border-radius:14px;padding:2px 10px;font-size:.78rem;font-weight:700}
.p-verde{background:#e2f4e9;color:var(--verde)}.p-amarillo{background:#fdf1dc;color:var(--amarillo)}
.p-rojo{background:#fbe5e3;color:var(--rojo)}.p-azul{background:#e3edf8;color:var(--azul2)}
.barra{background:#e9eff6;border-radius:6px;height:16px;overflow:hidden;min-width:120px}
.barra>div{height:100%;background:linear-gradient(90deg,var(--azul2),var(--dorado));border-radius:6px}
.cadena{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}
.cadena .m{background:var(--azul);color:#fff;border-radius:8px;padding:8px 12px;font-size:.82rem;font-weight:600}
.cadena .arrow{color:var(--dorado);font-weight:900}
.capas{display:flex;flex-direction:column;gap:6px}
.capa{border:1px solid var(--borde);border-radius:8px;padding:10px 14px;background:#fbfdff;display:flex;gap:12px;align-items:baseline}
.capa b{color:var(--azul);min-width:150px}
label{display:block;font-weight:600;font-size:.85rem;color:var(--azul2);margin:10px 0 4px}
input,select,textarea{width:100%;padding:9px 11px;border:1px solid var(--borde);border-radius:8px;
  font-size:.92rem;background:#fff;color:#1c2b3a}
input:focus,select:focus,textarea:focus{outline:2px solid var(--azul2)}
.btn{background:var(--azul);color:#fff;border:none;border-radius:8px;padding:11px 22px;
  font-size:.95rem;font-weight:700;cursor:pointer;margin-top:14px}
.btn:hover{background:var(--azul2)}
.btn.sec{background:#fff;color:var(--azul);border:1.5px solid var(--azul)}
.kpi{display:flex;gap:14px;flex-wrap:wrap;margin:12px 0}
.kpi .k{flex:1;min-width:170px;background:#fff;border:1px solid var(--borde);border-radius:12px;padding:14px;text-align:center}
.kpi .k .v{font-size:1.5rem;font-weight:800;color:var(--azul)}
.kpi .k .l{font-size:.78rem;color:var(--gris);text-transform:uppercase;letter-spacing:.5px}
.aviso{background:#fff8e6;border:1px solid #ecd9a0;border-radius:8px;padding:10px 14px;font-size:.85rem;color:#7a5c00;margin-top:12px}
.hash{font-family:Consolas,monospace;font-size:.8rem;color:var(--gris)}
.pasos{counter-reset:p;display:grid;gap:10px}
.paso{background:#fff;border:1px solid var(--borde);border-left:6px solid var(--dorado);border-radius:10px;padding:12px 16px}
.paso::before{counter-increment:p;content:"PASO " counter(p);font-weight:800;color:var(--azul);font-size:.8rem;letter-spacing:1px}
footer{text-align:center;color:var(--gris);font-size:.8rem;padding:22px;border-top:1px solid var(--borde);margin-top:24px}
#estadoExp{white-space:pre-wrap;font-family:Consolas,monospace;font-size:.82rem;background:#0b1f33;color:#cfe3f5;
  border-radius:10px;padding:14px;overflow-x:auto}
svg text{font-family:'Segoe UI',Arial,sans-serif}
</style>
</head>
<body>
<header>
  <h1>⚖️ JUSTICIA-DT Nicaragua</h1>
  <p>Gemelo Digital para Análisis de Escenarios en Juicios Civiles según la Pretensión ·
     Dirigido a Abogados y Notarios Públicos de la República de Nicaragua</p>
  <span class="badge">Metodología DT-PRET · Ley 902 · Código Civil · Datos sintéticos (Fase 1)</span>
</header>

<nav id="nav">
  <button data-tab="tab-arq" class="activo">🏛️ Arquitectura</button>
  <button data-tab="tab-modulos">🧩 9 Módulos</button>
  <button data-tab="tab-flujo">🔁 Flujo de Uso</button>
  <button data-tab="tab-analisis">🤖 Análisis del DT (demo §5)</button>
  <button data-tab="tab-nuevo">📝 Nuevo Caso</button>
</nav>

<main>

<!-- ===================== ARQUITECTURA ===================== -->
<section id="tab-arq" class="tab section-visible">
  <h2>Arquitectura de la aplicación (§3.1)</h2>
  <div class="tarjeta">
    <h3>Cadena de selección → análisis → resultados</h3>
    <div class="cadena">
      <span class="m">Selección de Pretensión<br><small>Declarativa · Constitutiva · De condena · Ejecutiva · Cautelar · Probatoria</small></span>
      <span class="arrow">→</span>
      <span class="m">Subtipo de Pretensión<br><small>Incumplimiento, nulidad, daños, cobro de pesos…</small></span>
      <span class="arrow">→</span>
      <span class="m">Análisis de Escenarios<br><small>Base, allanamiento, reconvención, excepciones, acuerdo, apelación…</small></span>
      <span class="arrow">→</span>
      <span class="m">Resultados por Pretensión<br><small>Éxito · Duración · Costos · Recomendación</small></span>
    </div>
  </div>
  <div class="tarjeta">
    <h3>Capas del gemelo digital (§2.1)</h3>
    <div class="capas">
      <div class="capa"><b>Física (PO)</b><span>Juzgados civiles, expedientes, abogados, notarios — sistema real</span></div>
      <div class="capa"><b>Comunicación</b><span>NICARAO, SGEAN, firma electrónica (Ley 729) — intercambio de datos</span></div>
      <div class="capa"><b>Digital (VO)</b><span>Réplica virtual del proceso según pretensión</span></div>
      <div class="capa"><b>Cibernética</b><span>Nube, IA, procesamiento — análisis y simulación</span></div>
      <div class="capa"><b>Servicio</b><span>Análisis de escenarios por pretensión</span></div>
      <div class="capa"><b>Visualización</b><span>Este dashboard web (HTML/CSS/JS autocontenido)</span></div>
    </div>
  </div>
  <div class="tarjeta">
    <h3>Núcleo DT — Modelo híbrido (§6.1)</h3>
    <div class="cadena">
      <span class="m">C1 Clasificador<br><small>NLP · Random Forest</small></span><span class="arrow">→</span>
      <span class="m">C2 Process Mining<br><small>Conformance · desviaciones</small></span><span class="arrow">→</span>
      <span class="m">C3 Simulación<br><small>Monte Carlo what-if</small></span><span class="arrow">→</span>
      <span class="m">C4 IA Predictiva<br><small>Duración · anomalías</small></span><span class="arrow">→</span>
      <span class="m">C5 Grafo de Conocimiento<br><small>Partes · normas · pretensiones</small></span>
    </div>
    <p style="margin-top:8px;font-size:.85rem;color:var(--gris)">Protocolos: API REST/JSON · mensajería MQTT/Kafka ·
    firma electrónica Ley 729 · trazabilidad SHA-256.</p>
  </div>
  <div class="tarjeta">
    <h3>Pretensiones según Ley 902 (§1.1)</h3>
    <table><thead><tr><th>Tipo</th><th>Descripción</th><th>Duración típica</th></tr></thead>
    <tbody id="tblPretensiones"></tbody></table>
  </div>
</section>

<!-- ===================== 9 MODULOS ===================== -->
<section id="tab-modulos" class="tab">
  <h2>Los 9 módulos de la aplicación (§3.2)</h2>
  <div class="grid g3" id="gridModulos"></div>
</section>

<!-- ===================== FLUJO DE USO ===================== -->
<section id="tab-flujo" class="tab">
  <h2>Flujo de uso según pretensión (§3.3)</h2>
  <div class="pasos">
    <div class="paso"><h3>El abogado selecciona la pretensión (M1)</h3>
      Tipo: Declarativa, Constitutiva, De condena, Ejecutiva, Cautelar, Probatoria + subtipo específico.</div>
    <div class="paso"><h3>El abogado ingresa los datos del caso (M2)</h3>
      Partes procesales, hechos y fundamentos jurídicos, pretensiones específicas, cuantía, juzgado competente, documentos adjuntos.</div>
    <div class="paso"><h3>El DT analiza viabilidad según pretensión (M3)</h3>
      Compara con casos similares históricos, evalúa requisitos, estima duración esperada e identifica obstáculos.</div>
    <div class="paso"><h3>El abogado simula escenarios (M4–M7)</h3>
      ¿Qué pasa si se allana? ¿Si hay reconvención? ¿Si se apela? ¿Si se concilia? + predicción de duración, resultado y alertas.</div>
    <div class="paso"><h3>El DT genera análisis y recomendaciones (M8–M9)</h3>
      Probabilidad de éxito, duración y costos por escenario + recomendación estratégica según pretensión.</h3></div>
  </div>
  <div class="tarjeta">
    <h3>Etapas del flujo estándar por pretensión (Fase de Diseño DT-PRET)</h3>
    <table><thead><tr><th>Pretensión</th><th>Flujo de etapas</th></tr></thead><tbody id="tblFlujos"></tbody></table>
  </div>
</section>

<!-- ===================== ANALISIS DEMO ===================== -->
<section id="tab-analisis" class="tab">
  <h2>Análisis del DT — Ejemplo §5: Incumplimiento de contrato</h2>
  <div class="tarjeta" id="cazDemo">
    <h3>Expediente <span id="demoId"></span> <span class="pill p-azul">Hash integridad: <span class="hash" id="demoHash"></span></span></h3>
    <p id="demoMeta" style="margin-top:6px"></p>
    <div class="kpi" id="demoKpis"></div>
    <div id="demoViab"></div>
    <div class="aviso">⚠️ <b>Nota legal:</b> <span id="demoNota"></span></div>
  </div>
  <div class="grid g2">
    <div class="tarjeta"><h3>M4/M6 · Escenarios what-if (Monte Carlo, 2000 iteraciones)</h3>
      <table><thead><tr><th>Escenario</th><th>Éxito</th><th></th><th>Duración</th><th>Costo USD</th></tr></thead>
      <tbody id="tblEscenarios"></tbody></table></div>
    <div class="tarjeta"><h3>M5 · Predicción de duración por etapa</h3>
      <table><thead><tr><th>Etapa</th><th>Meses</th><th></th></tr></thead><tbody id="tblEtapas"></tbody></table>
      <div class="tarjeta" style="background:#eef3fa;margin-top:10px"><h3>M7 · Detección de anomalías</h3>
      <p>Nivel: <span id="demoNivel"></span></p><ul id="demoAlertas" style="margin:6px 0 0 18px;font-size:.85rem"></ul></div>
    </div>
  </div>
  <div class="grid g2">
    <div class="tarjeta"><h3>M9 · Informe — Recomendación estratégica</h3>
      <blockquote style="border-left:4px solid var(--dorado);padding:8px 14px;background:#fbf7e8;border-radius:6px;font-size:.9rem"
      id="demoRecom"></blockquote>
      <h3 style="margin-top:14px">Ranking de escenarios (éxito)</h3>
      <div id="demoRanking"></div></div>
    <div class="tarjeta"><h3>C5 · Grafo de conocimiento del caso</h3>
      <div id="grafoSvg" style="overflow-x:auto"></div></div>
  </div>
  <div class="tarjeta"><h3>M8 · Consola de seguimiento (salida del motor Python)</h3>
    <div id="estadoExp"></div></div>
</section>

<!-- ===================== NUEVO CASO ===================== -->
<section id="tab-nuevo" class="tab">
  <h2>Nuevo caso — Simulación interactiva en el navegador</h2>
  <div class="grid g2">
    <div class="tarjeta">
      <h3>Paso 1 · Selección de pretensión (M1)</h3>
      <label>Tipo de pretensión</label>
      <select id="inPretension"></select>
      <label>Subtipo</label>
      <select id="inSubtipo"></select>
      <h3 style="margin-top:16px">Paso 2 · Registro de caso (M2)</h3>
      <label>Demandante</label><input id="inDemandante" value="Empresa A">
      <label>Demandado</label><input id="inDemandado" value="Empresa B">
      <label>Cuantía (USD)</label><input id="inCuantia" type="number" min="1" value="50000">
      <label>Juzgado</label><input id="inJuzgado" value="Civil de Managua">
      <label>Pruebas disponibles (marque las que tenga)</label>
      <div id="inPruebas" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px"></div>
      <button class="btn" onclick="calcular()">🔮 Analizar con el Gemelo Digital</button>
      <button class="btn sec" onclick="limpiarFormulario()">Limpiar</button>
    </div>
    <div class="tarjeta">
      <h3>Resultado del DT (M3–M9)</h3>
      <div id="resultadoNuevo"><p style="color:var(--gris)">Complete el formulario y pulse «Analizar».</p></div>
    </div>
  </div>
  <div class="aviso">Motor idéntico al núcleo Python (heurísticas Fase 1 + Monte Carlo determinista con PRNG mulberry32 sembrado por expediente y escenario).
  Este HTML es autocontenido: funciona sin servidor ni conexión a Internet.</div>
</section>

</main>
<footer>
  JUSTICIA-DT Nicaragua · Metodología DT-PRET (Diseño → Modelado → Implementación) · Ley 902 CPC y Código Civil de Nicaragua ·
  Desarrollo ético y legal con datos sintéticos (Fase 1 de la hoja de ruta) · Análisis orientativo — no sustituye el criterio profesional.
</footer>

<script>
/* ============ DATOS INYECTADOS DESDE EL MOTOR PYTHON ============ */
const CATALOGO = /*__CATALOGO__*/;
const DEMO     = /*__DEMO__*/;

/* ============ NÚCLEO DT EN JS (port fiel de app.py) ============ */
function hashStr(s){ // FNV-1a 32 bits -> entero positivo
  let h=2166136261>>>0;
  for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)>>>0;}
  return h>>>0;
}
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
function gauss(rng,mu,sigma){let u=0,v=0;while(u===0)u=rng();while(v===0)v=rng();return mu+sigma*Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}
function gammaSample(rng,k){ // Marsaglia-Tsang
  if(k<1){return gammaSample(rng,k+1)*Math.pow(rng(),1/k);}
  const d=k-1/3,c=1/Math.sqrt(9*d);let x,v,u;
  for(;;){do{x=gauss(rng,0,1);v=1+c*x;}while(v<=0);v=v*v*v;u=rng();
    if(u<1-0.0331*x*x*x*x)return d*v;
    if(Math.log(u)<0.5*x+x+d*(1-v-Math.log(v)))return d*v;}
}
function betaSample(rng,a,b){const x=gammaSample(rng,a),y=gammaSample(rng,b);return(x+y)>0?x/(x+y):0.5;}

function simularEscenario(caso,esc,n=2000){
  const cat=CATALOGO.pretensiones[caso.pretension];
  const [fp,fd,fc]=CATALOGO.escenarios[esc];
  const rng=mulberry32(hashStr("902:"+caso.id+":"+esc));
  const scorePruebas=Math.min(caso.pruebas.length/Math.max(cat.pruebas.length,1),1);
  const exitoBase=0.45+0.25*scorePruebas;
  const p=Math.min(Math.max(exitoBase*fp,0.02),0.98);
  let sum=0;for(let i=0;i<n;i++)sum+=betaSample(rng,2+30*p,2+30*(1-p));
  const prob=sum/n;
  const durBase=cat.duracion_base*fd;
  const costBase=Math.max(800,Math.min(caso.cuantia*0.10,15000))*fc;
  let sd=0,sc=0;for(let i=0;i<n;i++){sd+=gauss(rng,durBase,durBase*0.15);sc+=gauss(rng,costBase,costBase*0.12);}
  return{escenario:esc,probabilidad_exito:+(prob.toFixed(3)),
    duracion_meses:+Math.max(0.5,sd/n).toFixed(1),costo_usd:Math.round(Math.max(500,sc/n))};
}
function predecirEtapas(caso){
  const cat=CATALOGO.pretensiones[caso.pretension];
  const etapas=CATALOGO.flujo_etapas[caso.pretension];
  const pesos=[0.10,0.15,0.15,0.35,0.15,0.10].slice(0,etapas.length);
  const tot=pesos.reduce((a,b)=>a+b,0);const out={};
  etapas.forEach((e,i)=>out[e]=+(cat.duracion_base*pesos[i]/tot).toFixed(1));
  return out;
}
function detectarDesviaciones(traza,pretension){
  const esperado=CATALOGO.flujo_etapas[pretension];const dev=[];
  traza.forEach(e=>{if(!esperado.includes(e))dev.push("Etapa fuera de flujo estándar: "+e);});
  esperado.filter(e=>!e.startsWith("(")).forEach(e=>{if(!traza.includes(e))dev.push("Etapa esperada no ejecutada: "+e);});
  return dev;
}
function detectarAnomalias(dias){
  const vals=Object.values(dias);if(vals.length<2)return[];
  const media=vals.reduce((a,b)=>a+b,0)/vals.length;
  const desv=Math.sqrt(vals.reduce((a,b)=>a+(b-media)*(b-media),0)/vals.length)||1;
  return Object.entries(dias).filter(([,d])=>(d-media)/desv>2).map(([e])=>e);
}
function evaluarViabilidad(caso){
  const cat=CATALOGO.pretensiones[caso.pretension];
  const sp=Math.min(caso.pruebas.length/Math.max(cat.pruebas.length,1),1);
  const v=+(0.5*1+0.5*sp).toFixed(2);const[lo,hi]=cat.duracion_tipica_meses;
  const obs=[];if(sp<0.5)obs.push("Acervo probatorio insuficiente para el estándar de la pretensión.");
  if(caso.cuantia>100000)obs.push("Cuantía alta: mayor riesgo de reconvención y apelación.");
  return{viabilidad:v,veredicto:v>=0.6?"Viable":v>=0.4?"Viable con reservas":"Riesgo alto",
    duracion_esperada_meses:lo+"-"+hi,obstaculos:obs,requisitos_evaluados:cat.requisitos};
}
function clasificar(texto){
  const t=(texto||"").toLowerCase();
  const kc={declarativa:["declare","nulidad","usucapión","usucapion","prescripción","propiedad"],
    constitutiva:["divorcio","resolución","resolucion","extinga","disuelva"],
    de_condena:["condene","pague","cumplimiento","incumplimiento","daños","danos","indemnización"],
    ejecutiva:["pagaré","pagare","letra de cambio","título ejecutivo","titulo ejecutivo","ejecute"],
    cautelar:["embargo","secuestro","anotación preventiva","medida cautelar"],
    probatoria:["anticipo","inspección judicial","testimonio anticipado"]};
  let mejor="de_condena",pts=0;
  for(const[k,v]of Object.entries(kc)){const s=v.filter(w=>t.includes(w)).length;if(s>pts){pts=s;mejor=k;}}
  const sub=Object.keys(CATALOGO.subtipo_a_pretension).find(s=>t.includes(s)||t.includes(s.replace(/_/g," ")))
    ||CATALOGO.pretensiones[mejor].subtipos[0];
  return{pretension:mejor,subtipo:sub,confianza:Math.min(0.5+0.15*pts,0.95)};
}

/* ============ RENDERIZADO ============ */
const fmtUSD=n=>"USD "+n.toLocaleString("en-US");
const pct=n=>Math.round(n*100)+"%";
const $=id=>document.getElementById(id);

function navInit(){
  document.querySelectorAll("#nav button").forEach(b=>b.addEventListener("click",()=>{
    document.querySelectorAll("#nav button").forEach(x=>x.classList.remove("activo"));
    document.querySelectorAll("section.tab").forEach(x=>x.classList.remove("section-visible"));
    b.classList.add("activo");$(b.dataset.tab).classList.add("section-visible");
  }));
}
function renderCatalogo(){
  $("tblPretensiones").innerHTML=Object.values(CATALOGO.pretensiones).map(p=>
    `<tr><td><b>${p.nombre}</b></td><td>${p.descripcion}</td><td>${p.duracion_tipica_meses[0]}–${p.duracion_tipica_meses[1]} meses</td></tr>`).join("");
  $("tblFlujos").innerHTML=Object.entries(CATALOGO.flujo_etapas).map(([k,v])=>
    `<tr><td><b>${CATALOGO.pretensiones[k].nombre}</b></td><td>${v.join(" → ")}</td></tr>`).join("");
  const mods=[["1","Selección de pretensión","Clasificación tipo/subtipo según Ley 902 (manual o automática por NLP)."],
    ["2","Registro de caso","Ingreso y validación de partes, hechos, cuantía, juzgado y pruebas; expediente con hash SHA-256."],
    ["3","Análisis de viabilidad","Comparación con estándares de la pretensión; veredicto y obstáculos."],
    ["4","Simulación de escenarios","What-if Monte Carlo (2000 iteraciones) sobre 10 escenarios."],
    ["5","Predicción de duración","Estimación por etapa procesal y total."],
    ["6","Predicción de resultados","Probabilidad de éxito y ranking de escenarios."],
    ["7","Detección de anomalías","Conformance checking y retrasos >2σ con nivel verde/amarillo/rojo."],
    ["8","Dashboard de seguimiento","Estado actual del expediente (esta interfaz)."],
    ["9","Informe de resultados","Reporte final JSON con recomendación estratégica."]];
  $("gridModulos").innerHTML=mods.map(m=>
    `<div class="tarjeta"><span class="pill p-azul">M${m[0]}</span><h3 style="margin-top:8px">${m[1]}</h3><p style="font-size:.87rem">${m[2]}</p></div>`).join("");
}
function escBarraHTML(r){
  return`<tr><td><b>${r.escenario.replace(/_/g," ")}</b></td><td>${pct(r.probabilidad_exito)}</td>
  <td style="width:34%"><div class="barra"><div style="width:${r.probabilidad_exito*100}%"></div></div></td>
  <td>${r.duracion_meses} m</td><td>${fmtUSD(r.costo_usd)}</td></tr>`;
}
function renderDemo(){
  const inf=DEMO.informe;
  $("demoId").textContent=inf.expediente;$("demoHash").textContent=inf.hash_integridad;
  $("demoMeta").innerHTML=`<b>${inf.caso.pretension}</b> (${inf.caso.subtipo}) · Empresa A vs Empresa B · Juzgado ${inf.caso.juzgado} · Cuantía ${fmtUSD(inf.caso.cuantia_usd)}`;
  const best=inf.prediccion_resultado.mejor_escenario;
  const base=inf.escenarios.find(e=>e.escenario==="base");
  $("demoKpis").innerHTML=`
    <div class="k"><div class="v">${pct(base.probabilidad_exito)}</div><div class="l">Éxito escenario base</div></div>
    <div class="k"><div class="v">${inf.duracion_por_etapa?Object.values(inf.duracion_por_etapa).reduce((a,b)=>a+b,0).toFixed(1):"-"} m</div><div class="l">Duración estimada</div></div>
    <div class="k"><div class="v">${fmtUSD(base.costo_usd)}</div><div class="l">Costo escenario base</div></div>
    <div class="k"><div class="v">${best.replace(/_/g," ")}</div><div class="l">Mejor escenario (M6)</div></div>
    <div class="k"><div class="v">${pct(inf.viabilidad.viabilidad)}</div><div class="l">Viabilidad (M3) · ${inf.viabilidad.veredicto}</div></div>`;
  $("demoViab").innerHTML=`<p style="font-size:.88rem"><b>Obstáculos detectados:</b> ${inf.viabilidad.obstaculos.length?inf.viabilidad.obstaculos.join(" · "):"ninguno relevante"} ·
   <b>Requisitos evaluados:</b> ${inf.viabilidad.requisitos_evaluados.join(", ")} ·
   <b>Duración típica:</b> ${inf.viabilidad.duracion_esperada_meses} meses</p>`;
  $("tblEscenarios").innerHTML=[...inf.escenarios].sort((a,b)=>b.probabilidad_exito-a.probabilidad_exito).map(escBarraHTML).join("");
  $("tblEtapas").innerHTML=Object.entries(inf.duracion_por_etapa).map(([e,m])=>
    `<tr><td>${e}</td><td>${m}</td><td><div class="barra"><div style="width:${m*10}%"></div></div></td></tr>`).join("");
  const niv=inf.anomalias.nivel;
  $("demoNivel").innerHTML=`<span class="pill p-${niv}">${niv.toUpperCase()}</span>`;
  $("demoAlertas").innerHTML=inf.anomalias.alertas.length?inf.anomalias.alertas.map(a=>`<li>[${a.tipo}] ${a.mensaje}</li>`).join(""):"<li>Sin alertas: flujo conforme al estándar.</li>";
  $("demoRecom").textContent=inf.recomendacion;
  $("demoNota").textContent=inf.nota_legal;
  $("demoRanking").innerHTML=inf.prediccion_resultado.ranking.map(([e,p])=>
    `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="min-width:170px;font-size:.85rem">${e.replace(/_/g," ")}</span>
     <div class="barra" style="flex:1"><div style="width:${p*100}%"></div></div><b style="font-size:.82rem">${pct(p)}</b></div>`).join("");
  $("estadoExp").textContent=DEMO.dashboard_texto;
  renderGrafo(DEMO.grafo);
}
function renderGrafo(g){
  const W=520,H=300,cx=W/2,cy=H/2;
  const n=g.nodos.length,pos={};
  const col={parte:"#0b3d6b",pretension:"#c9a227",subtipo:"#155a9c",juzgado:"#1e8a4e",requisito:"#5a6b7d"};
  g.nodos.forEach((nd,i)=>{const a=2*Math.PI*i/n-Math.PI/2;pos[nd.id]=[cx+190*Math.cos(a),cy+110*Math.sin(a)];});
  let svg=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`;
  g.aristas.forEach(ar=>{const[x1,y1]=pos[ar.origen],[x2,y2]=pos[ar.destino];
    svg+=`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#b9c8da" stroke-width="1.5"/>
    <text x="${(x1+x2)/2}" y="${(y1+y2)/2-4}" font-size="8.5" fill="#5a6b7d" text-anchor="middle">${ar.relacion}</text>`;});
  g.nodos.forEach(nd=>{const[x,y]=pos[nd.id];
    svg+=`<circle cx="${x}" cy="${y}" r="16" fill="${col[nd.tipo]||"#888"}" opacity="0.9"/>
    <text x="${x}" y="${y+28}" font-size="9.5" fill="#1c2b3a" text-anchor="middle">${nd.id}</text>`;});
  svg+="</svg>";$("grafoSvg").innerHTML=svg;
}

/* ============ FORMULARIO NUEVO CASO ============ */
function cargarSelects(){
  $("inPretension").innerHTML=Object.entries(CATALOGO.pretensiones).map(([k,v])=>`<option value="${k}">${v.nombre}</option>`).join("");
  cargarSubtipos();cargarPruebas();
}
function cargarSubtipos(){
  const p=$("inPretension").value;
  const extras=["reivindicacion","division_bienes","responsabilidad_civil","arrendamiento","compraventa","servidumbres","resolucion_contrato","danos_perjuicios","cobro_pesos","incumplimiento"]
    .filter(s=>CATALOGO.subtipo_a_pretension[s]===p && !CATALOGO.pretensiones[p].subtipos.includes(s));
  const subs=[...new Set([...CATALOGO.pretensiones[p].subtipos,...extras])];
  $("inSubtipo").innerHTML=subs.map(s=>`<option value="${s}">${s.replace(/_/g," ")}</option>`).join("");
}
function cargarPruebas(){
  const p=$("inPretension").value;
  const todas=[...new Set(Object.values(CATALOGO.pretensiones).flatMap(c=>c.pruebas))];
  const est=new Set(CATALOGO.pretensiones[p].pruebas);
  $("inPruebas").innerHTML=todas.map(t=>
    `<label style="display:flex;gap:6px;align-items:center;font-weight:400;background:${est.has(t)?"#e3edf8":"#fff"};border:1px solid var(--borde);border-radius:8px;padding:6px 10px">
     <input type="checkbox" value="${t}" style="width:auto" ${est.has(t)?"checked":""}> ${t}</label>`).join("");
}
function limpiarFormulario(){
  $("inDemandante").value="";$("inDemandado").value="";$("inCuantia").value="";$("inJuzgado").value="";
  document.querySelectorAll("#inPruebas input").forEach(i=>i.checked=false);
  $("resultadoNuevo").innerHTML='<p style="color:var(--gris)">Complete el formulario y pulse «Analizar».</p>';
}
function calcular(){
  const pretension=$("inPretension").value,subtipo=$("inSubtipo").value;
  const pruebas=[...document.querySelectorAll("#inPruebas input:checked")].map(i=>i.value);
  const demandante=$("inDemandante").value||"Parte A",demandado=$("inDemandado").value||"Parte B";
  const cuantia=parseFloat($("inCuantia").value)||1,juzgado=$("inJuzgado").value||"Civil de Managua";
  const id="NIC-JS-"+hashStr(demandante+demandado+subtipo+cuantia)%100000;
  const caso={id,pretension,subtipo,cuantia,pruebas};
  const viab=evaluarViabilidad(caso);
  const res=Object.keys(CATALOGO.escenarios).map(e=>simularEscenario(caso,e));
  const etapas=predecirEtapas(caso);
  const totE=Object.values(etapas).reduce((a,b)=>a+b,0);
  const dias={};Object.entries(etapas).forEach(([e,m])=>dias[e]=Math.round(m*30));
  const anom=[...detectarDesviaciones(Object.keys(etapas),pretension),...detectarAnomalias(dias).map(a=>"Retraso anómalo (>2σ) en: "+a)];
  const nivel=anom.length>2?"rojo":anom.length?"amarillo":"verde";
  const rank=[...res].sort((a,b)=>b.probabilidad_exito-a.probabilidad_exito);
  const best=res.reduce((m,r)=>(r.probabilidad_exito/(r.duracion_meses*r.costo_usd)*1e5)>(m.probabilidad_exito/(m.duracion_meses*m.costo_usd)*1e5)?r:m,res[0]);
  const cat=CATALOGO.pretensiones[pretension];
  $("resultadoNuevo").innerHTML=`
    <span class="pill p-azul">Expediente ${id}</span>
    <div class="kpi"><div class="k"><div class="v">${pct(rank[0].probabilidad_exito)}</div><div class="l">Mejor éxito · ${rank[0].escenario.replace(/_/g," ")}</div></div>
    <div class="k"><div class="v">${totE.toFixed(1)} m</div><div class="l">Duración base</div></div>
    <div class="k"><div class="v">${viab.veredicto}</div><div class="l">Viabilidad ${pct(viab.viabilidad)}</div></div>
    <div class="k"><div class="v"><span class="pill p-${nivel}">${nivel.toUpperCase()}</span></div><div class="l">Nivel de alertas</div></div></div>
    <h3>Escenarios (M4/M6)</h3>
    <table><thead><tr><th>Escenario</th><th>Éxito</th><th></th><th>Duración</th><th>Costo</th></tr></thead>
    <tbody>${rank.map(escBarraHTML).join("")}</tbody></table>
    <h3 style="margin-top:12px">Etapas (M5)</h3><p style="font-size:.85rem">${Object.entries(etapas).map(([e,m])=>`${e}: <b>${m} m</b>`).join(" · ")}</p>
    <h3 style="margin-top:12px">Recomendación (M9)</h3>
    <blockquote style="border-left:4px solid var(--dorado);padding:8px 14px;background:#fbf7e8;border-radius:6px;font-size:.88rem">
    Para la pretensión de <b>${subtipo.replace(/_/g," ")}</b> (${cat.nombre}), se recomienda explorar el escenario
    '<b>${best.escenario.replace(/_/g," ")}</b>' (éxito ${pct(best.probabilidad_exito)}, ${best.duracion_meses} meses, ${fmtUSD(best.costo_usd)}).
    Evite incidencias que prolonguen el juicio; acredite los requisitos: ${cat.requisitos.join(", ")}.</blockquote>
    ${anom.length?`<h3 style="margin-top:12px">Alertas (M7)</h3><ul style="margin-left:18px;font-size:.85rem">${anom.map(a=>`<li>${a}</li>`).join("")}</ul>`:""}`;
}

/* ============ INICIO ============ */
window.addEventListener("DOMContentLoaded",()=>{
  navInit();renderCatalogo();renderDemo();cargarSelects();
  $("inPretension").addEventListener("change",()=>{cargarSubtipos();cargarPruebas();});
});
</script>
</body>
</html>
"""


def build() -> str:
    catalogo = json.dumps(catalogo_js(), ensure_ascii=False)
    demo = json.dumps(demo_data(), ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace("/*__CATALOGO__*/", catalogo).replace("/*__DEMO__*/", demo)
    return html


if __name__ == "__main__":
    out = build()
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Dashboard HTML generado en {SALIDA} ({len(out):,} bytes)")
