// Single-viewport dashboard built from one contract package.

import { getPackage } from './lib/api.js';
import { adapt, formatCop } from './lib/adapt.js';
import { NUTRIENTS, RANGES } from './lib/plotmap.js';
import { plasmaGradient } from './lib/colormap.js';
import { renderTiles, ATTRIBUTION } from './lib/slippy.js';
import { gridGeoBounds, paintSurface, paintOverlay } from './lib/heatsurface.js';
import { ask, speak, stopSpeaking, listen, canSpeak, canListen } from './lib/assistant.js';

const state = { nutrient: 'K' };

const fmt = (value, decimals = 1) => Number(value)
  .toLocaleString('es-CO', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const NIVEL_LABEL = { critico: 'crítico', bajo: 'bajo', adecuado: 'bien' };
const SEVERITY_MARK = { critica: '▲', alta: '▲', media: '●', baja: '○' };

function colorbar() {
  const [min, max] = RANGES[state.nutrient];
  const ticks = [1, 0.75, 0.5, 0.25, 0]
    .map((t) => `<span>${Math.round(min + (max - min) * t)}</span>`).join('');
  return `<div class="colorbar">
    <div class="ramp" style="background:linear-gradient(to top, ${plasmaGradient()})"></div>
    <div class="ticks">${ticks}</div>
  </div>`;
}

function drawMap() {
  const view = state.view;
  const stage = document.getElementById('stage');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return;
  const status = document.getElementById('map-status');
  try {
    const projector = renderTiles(document.getElementById('tiles'), gridGeoBounds(view.grid), rect.width, rect.height);
    paintSurface(document.getElementById('heat'), view.grid, state.nutrient, projector);
    paintOverlay(document.getElementById('overlay'), view, projector);
    if (status) status.hidden = true;
  } catch (error) {
    if (status) {
      status.hidden = false;
      status.textContent = `No se pudo dibujar el mapa: ${error.message}`;
    }
  }
}

function paintMap() {
  document.getElementById('colorbar-slot').innerHTML = colorbar();
  document.getElementById('map-nutrient').textContent = state.nutrient;
  for (const button of document.querySelectorAll('.nut')) {
    button.classList.toggle('on', button.dataset.nut === state.nutrient);
    button.setAttribute('aria-pressed', String(button.dataset.nut === state.nutrient));
  }
  scheduleDraw();
}

const MAX_LAYOUT_ATTEMPTS = 60;
const LAYOUT_RETRY_MS = 50;

let observer;
let redrawTimer;

// setTimeout, not requestAnimationFrame: a tab that is not compositing never
// runs animation frames, and the map would stay blank until it gained focus.
function scheduleDraw(attempt = 0) {
  const stage = document.getElementById('stage');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) {
    if (attempt < MAX_LAYOUT_ATTEMPTS) setTimeout(() => scheduleDraw(attempt + 1), LAYOUT_RETRY_MS);
    return;
  }
  drawMap();
}

function observeStage() {
  const stage = document.getElementById('stage');
  if (!stage) return;
  if (observer) observer.disconnect();
  observer = new ResizeObserver(() => {
    clearTimeout(redrawTimer);
    redrawTimer = setTimeout(() => scheduleDraw(), 80);
  });
  observer.observe(stage);
  scheduleDraw();
}

function panelReceta() {
  const { receta, zonas } = state.view;
  const bags = new Map();
  for (const zona of zonas) {
    for (const producto of zona.productos) {
      bags.set(producto.nombre, (bags.get(producto.nombre) || 0) + producto.bultos);
    }
  }

  const rows = [...bags.entries()].map(([name, count]) => `<div class="bag-row">
      <span class="bags" aria-hidden="true">${'▬'.repeat(Math.min(count, 8))}</span>
      <span class="bag-name"><b>${count}</b> ${count === 1 ? 'bulto' : 'bultos'} ${name}</span>
    </div>`).join('');

  const adjustments = (receta.ajustes || []).map((a) => `<li>
      <b>${a.nutriente} ${a.factor < 1 ? '−' : '+'}${Math.round(Math.abs(1 - a.factor) * 100)}%</b> ${a.motivo}
    </li>`).join('');

  return `<div class="recipe">
    ${rows}
    <div class="price">${formatCop(receta.costo_total_cop)}</div>
    <div class="price-was">antes ${formatCop(receta.costo_generico_cop)} · ahorra <b>${formatCop(receta.ahorro_cop)}</b></div>
    <p class="window"><b>Aplique entre ${receta.ventana.desde} y ${receta.ventana.hasta}.</b> ${receta.ventana.motivo}</p>
    ${adjustments ? `<div class="adjust"><h3>Le cambiamos la receta</h3><ul>${adjustments}</ul></div>` : ''}
    <p class="note">Genérico equivalente: ${receta.generico_detalle}.</p>
  </div>`;
}

function panelRiesgos() {
  const { riesgos, estacional, degradado } = state.view;
  if (riesgos.length === 0) return '<p class="note">Sin riesgos activos para este lote.</p>';

  const cards = riesgos.map((r, index) => `<article class="risk sev-${r.severidad} ${index === 0 ? 'open' : ''}">
      <button class="risk-head" type="button" aria-expanded="${index === 0}">
        <span class="mark">${SEVERITY_MARK[r.severidad] || '●'}</span>
        <span class="sev-label">${r.severidad}</span>
        <span class="risk-title">${r.titulo}</span>
      </button>
      <div class="risk-body">
        <p>${r.resumen}</p>
        <ul>${r.que_hacer.map((step) => `<li>${step}</li>`).join('')}</ul>
        ${r.confianza === 'baja' ? '<p class="low-conf">Esto todavía puede cambiar.</p>' : ''}
        <button class="why" type="button" data-risk="${r.id}">¿Por qué?</button>
        <div class="why-body" id="why-${r.id}" hidden>
          <p><b>Modelo:</b> ${r.por_que.modelo}</p>
          <p><b>Regla:</b> ${r.por_que.regla}</p>
          <p><b>Datos:</b> ${Object.entries(r.por_que.entradas).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}</p>
          <p><b>Fuentes:</b> ${r.por_que.fuentes.map((f) => `${f.nombre}${f.consultado ? ` (${f.consultado.slice(0, 10)})` : ''}`).join(', ')}</p>
        </div>
      </div>
    </article>`).join('');

  return `<div class="scroll-y">${cards}
    ${estacional ? `<p class="note"><b>${estacional.fenomeno}:</b> ${estacional.estado}. ${estacional.implicacion_local}</p>` : ''}
    ${degradado ? '<p class="note warn-text">Datos de hace unas horas: no pude conectarme a alguna fuente.</p>' : ''}
  </div>`;
}

function panelAsistente() {
  const suggestions = state.view.voz.slice(0, 4).map((v) => v.claves.slice(0, 2).join(' '));
  return `<div class="chat" id="chat"></div>
    <div class="suggest">${suggestions.map((s) => `<button class="chip as-suggest" type="button">¿${s}?</button>`).join('')}</div>
    <form class="ask" id="ask">
      <input id="ask-input" type="text" placeholder="Pregunte sobre su lote…" autocomplete="off" aria-label="Pregunte sobre su lote">
      <button class="btn icon" id="mic" type="button" title="${canListen ? 'Preguntar por voz' : 'Voz no disponible aquí'}" ${canListen ? '' : 'disabled'}>🎙</button>
      <button class="btn" type="submit">Enviar</button>
    </form>
    <p class="note">${canSpeak ? 'Responde en voz alta.' : 'Este navegador no reproduce voz.'} Responde sin red usando el paquete descargado.</p>`;
}

function bubble(role, text) {
  const chat = document.getElementById('chat');
  const node = document.createElement('div');
  node.className = `bubble ${role}`;
  node.textContent = text;
  chat.appendChild(node);
  chat.scrollTop = chat.scrollHeight;
  return node;
}

async function answer(question) {
  bubble('me', question);
  const pending = bubble('bot', '…');
  const reply = await ask(question, state.view);
  pending.textContent = reply.texto;
  if (reply.fuente) pending.title = reply.fuente;
  speak(reply.texto);
}

function wireTabs() {
  const panels = { receta: panelReceta, riesgos: panelRiesgos, asistente: panelAsistente };
  const body = document.getElementById('tab-body');

  const show = (name) => {
    stopSpeaking();
    body.innerHTML = panels[name]();
    for (const tab of document.querySelectorAll('.tab')) {
      tab.classList.toggle('on', tab.dataset.tab === name);
      tab.setAttribute('aria-selected', String(tab.dataset.tab === name));
    }

    if (name === 'riesgos') {
      for (const head of body.querySelectorAll('.risk-head')) {
        head.addEventListener('click', () => {
          const card = head.closest('.risk');
          const open = card.classList.toggle('open');
          head.setAttribute('aria-expanded', String(open));
        });
      }
      for (const why of body.querySelectorAll('.why')) {
        why.addEventListener('click', () => {
          const target = document.getElementById(`why-${why.dataset.risk}`);
          target.hidden = !target.hidden;
          why.textContent = target.hidden ? '¿Por qué?' : 'Ocultar';
        });
      }
      return;
    }

    if (name !== 'asistente') return;

    document.getElementById('ask').addEventListener('submit', (event) => {
      event.preventDefault();
      const input = document.getElementById('ask-input');
      if (!input.value.trim()) return;
      answer(input.value.trim());
      input.value = '';
    });
    for (const chip of body.querySelectorAll('.as-suggest')) {
      chip.addEventListener('click', () => answer(chip.textContent));
    }
    const mic = document.getElementById('mic');
    if (canListen) {
      mic.addEventListener('click', () => {
        mic.classList.add('rec');
        listen({
          onResult: (transcript) => answer(transcript),
          onEnd: () => mic.classList.remove('rec'),
          onError: () => { mic.classList.remove('rec'); bubble('bot', 'No pude escuchar. Escriba la pregunta.'); },
        });
      });
    }
  };

  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => show(tab.dataset.tab));
  }
  show('receta');
}

function render() {
  const view = state.view;
  const worstZone = view.zonas[0];
  const syncLabel = view.stale ? 'vencido' : state.live ? 'al día' : 'sin red · paquete local';

  document.getElementById('app').innerHTML = `<div class="shell">
    <div class="sync ${view.stale ? 'stale' : ''}">
      <span class="dot"></span>${syncLabel} · ${view.sampling.valid} mediciones · ${state.dataOrigin}
      ${view.aviso ? `<span class="aviso">${view.aviso}</span>` : ''}
    </div>

    <div class="topbar">
      <div class="mark">iO</div>
      <div class="brand-name">${view.plot.nombre}<small>${view.plot.municipio} · ${view.plot.area_ha} ha · ${view.plot.cultivo}</small></div>
      <span class="spacer"></span>
      <a class="btn ghost" href="pitch.html">Pitch</a>
    </div>

    <div class="grid">
      <section class="card map-card">
        <div class="nutrients">
          ${NUTRIENTS.map((n) => `<button class="nut" data-nut="${n}" aria-pressed="${n === state.nutrient}">${n}</button>`).join('')}
          <span class="spacer"></span>
          <span class="uncertain-note">rayado = sin certeza · ${view.coverage.uncertainPct}% del lote</span>
        </div>
        <div class="map-stage" id="stage">
          <div class="tiles" id="tiles"></div>
          <canvas id="heat"></canvas>
          <svg id="overlay"></svg>
          <div class="map-title"><b id="map-nutrient">${state.nutrient}</b> en el lote<span>ppm · celda ${view.grid.celda_m} m · ✛ mida aquí</span></div>
          <div id="colorbar-slot"></div>
          <div class="map-status" id="map-status" hidden></div>
          <div class="attribution">${ATTRIBUTION}</div>
        </div>
      </section>

      <div class="col">
        <div class="kpis">
          <div class="kpi"><div class="label">Zona más pobre</div><div class="value warn">${NIVEL_LABEL[worstZone.peor]}</div><div class="hint">${fmt(worstZone.area_ha, 2)} ha · ${worstZone.id}</div></div>
          <div class="kpi"><div class="label">Le falta</div><div class="value">${fmt(view.criticalSharePct)}%</div><div class="hint">del lote en nivel crítico</div></div>
        </div>

        ${view.descartados.length ? `<div class="amber">
          <b>Una medición quedó fuera</b>
          <p>${view.descartados[0].motivo}</p>
          <div class="amber-actions"><button class="btn ghost" type="button">Corregir ubicación</button><button class="btn ghost" type="button">Guardar igual</button></div>
        </div>` : ''}

        <section class="card tabs-card">
          <div class="tabs" role="tablist">
            <button class="tab" data-tab="receta" role="tab" aria-selected="true">Receta</button>
            <button class="tab" data-tab="riesgos" role="tab" aria-selected="false">Lo que viene${view.riesgos.length ? ` <span class="badge-n">${view.riesgos.length}</span>` : ''}</button>
            <button class="tab" data-tab="asistente" role="tab" aria-selected="false">Preguntar</button>
          </div>
          <div class="tab-body" id="tab-body"></div>
        </section>
      </div>
    </div>
  </div>`;

  for (const button of document.querySelectorAll('.nut')) {
    button.addEventListener('click', () => { state.nutrient = button.dataset.nut; paintMap(); });
  }

  wireTabs();
  paintMap();
  observeStage();
}

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => scheduleDraw(), 160);
});

async function boot() {
  const { data, origin, live } = await getPackage();
  state.view = adapt(data);
  state.dataOrigin = origin;
  state.live = live;
  render();
}

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

boot().catch((error) => {
  document.getElementById('app').innerHTML = `<div class="loading">No se pudo cargar el lote.<br><small>${error.message}</small></div>`;
});
