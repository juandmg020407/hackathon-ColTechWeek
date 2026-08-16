// Command-center shell: the acopio network first, the lot package as drill-down.

import { getPackage } from './lib/api.js';
import { getNetwork } from './lib/network.js';
import { adapt, formatCop } from './lib/adapt.js';
import { NUTRIENTS, RANGES } from './lib/plotmap.js';
import { plasmaGradient } from './lib/colormap.js';
import { renderTiles, ATTRIBUTION } from './lib/slippy.js';
import { gridGeoBounds, paintSurface, paintOverlay } from './lib/heatsurface.js';
import { ask, speak, stopSpeaking, listen, canSpeak, canListen } from './lib/assistant.js';

const state = {
  nutrient: 'K',
  nav: 'resumen',
  mapMode: 'red',
  riesgoFiltro: 'todos',
  productor: null,
  view: null,
  network: null,
  dataOrigin: '',
  live: false,
};

const fmt = (value, decimals = 1) => Number(value)
  .toLocaleString('es-CO', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const NIVEL_LABEL = { critico: 'crítico', bajo: 'bajo', adecuado: 'bien' };
const SEVERITY_MARK = { critica: '▲', alta: '▲', media: '●', baja: '○', aviso: '○' };
const LEVEL_MARK = { alto: '▲', medio: '●', bajo: '○' };
const NAV_VIEWS = ['resumen', 'mapa', 'productores', 'lote'];

function navFromHash() {
  const target = decodeURIComponent(location.hash.slice(1));
  return NAV_VIEWS.includes(target) ? target : 'resumen';
}

function colorbar() {
  const [min, max] = RANGES[state.nutrient];
  const ticks = [1, 0.75, 0.5, 0.25, 0]
    .map((t) => `<span>${Math.round(min + (max - min) * t)}</span>`).join('');
  return `<div class="colorbar">
    <div class="ramp" style="background:linear-gradient(to top, ${plasmaGradient()})"></div>
    <div class="ticks">${ticks}</div>
  </div>`;
}

function networkBounds() {
  const producers = state.network.productores;
  const pad = 0.03;
  return {
    north: Math.max(...producers.map((p) => p.lat)) + pad,
    south: Math.min(...producers.map((p) => p.lat)) - pad,
    east: Math.max(...producers.map((p) => p.lon)) + pad,
    west: Math.min(...producers.map((p) => p.lon)) - pad,
  };
}

function paintNetworkDots(projector, producers) {
  const overlay = document.getElementById('overlay');
  if (!overlay) return;
  const dots = producers.map((p) => {
    const { x, y } = projector.toPixel(p.lat, p.lon);
    return `<circle cx="${x}" cy="${y}" r="5" class="pdot pdot-${p.riesgo_nivel || 'bajo'}" data-prod="${p.id}"><title>${p.nombre}</title></circle>`;
  }).join('');
  overlay.innerHTML = `<g>${dots}</g>`;
}

function drawMap() {
  const stage = document.getElementById('stage');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return;
  const status = document.getElementById('map-status');
  const tiles = document.getElementById('tiles');
  const overlay = document.getElementById('overlay');
  // Resumen is always the network and Lote always the plot; only Mapa follows the layer switcher.
  const showNetwork = state.nav === 'resumen' || (state.nav === 'mapa' && state.mapMode === 'red');
  try {
    if (showNetwork) {
      const projector = renderTiles(tiles, networkBounds(), rect.width, rect.height);
      const producers = state.riesgoFiltro === 'todos'
        ? state.network.productores
        : state.network.productores.filter((p) => p.riesgo_nivel === state.riesgoFiltro);
      paintNetworkDots(projector, producers);
      if (overlay) for (const circle of overlay.querySelectorAll('.pdot')) {
        circle.addEventListener('click', () => selectProducer(circle.dataset.prod));
      }
    } else {
      const view = state.view;
      const projector = renderTiles(tiles, gridGeoBounds(view.grid), rect.width, rect.height);
      paintSurface(document.getElementById('heat'), view.grid, state.nutrient, projector);
      paintOverlay(overlay, view, projector);
      if (overlay) for (const circle of overlay.querySelectorAll('circle[fill="none"]')) circle.remove();
      if (overlay) overlay.querySelectorAll('.mdot').forEach((m) => m.remove());
    }
    if (status) status.hidden = true;
  } catch (error) {
    if (status) {
      status.hidden = false;
      status.textContent = `No se pudo dibujar el mapa: ${error.message}`;
    }
  }
}

function paintNutrientToggle() {
  const slot = document.getElementById('colorbar-slot');
  if (slot) {
    slot.innerHTML = colorbar();
    document.getElementById('map-nutrient').textContent = state.nutrient;
  }
  for (const button of document.querySelectorAll('.nut')) {
    button.classList.toggle('on', button.dataset.nut === state.nutrient);
    button.setAttribute('aria-pressed', String(button.dataset.nut === state.nutrient));
  }
}

const MAX_LAYOUT_ATTEMPTS = 60;
const LAYOUT_RETRY_MS = 50;

let observer;
let redrawTimer;

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
      <input id="ask-input" type="text" placeholder="Pregunte sobre el lote…" autocomplete="off" aria-label="Pregunte sobre el lote">
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

function wireTabs(initial) {
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
  show(initial || 'receta');
}

function healthHeadline(pct) {
  if (pct >= 80) return 'Tu abastecimiento está estable.';
  if (pct >= 60) return 'Tu abastecimiento aguanta, con puntos que vigilar.';
  return 'Tu abastecimiento está comprometido.';
}

function riskBar(pct) {
  return `<div class="rbar" role="img" aria-label="Riesgo ${pct} %"><i style="width:${pct}%"></i></div>`;
}

function viewResumen() {
  const net = state.network;
  const k = net.kpis;
  const hero = net.prioridades.length
    ? `<div class="hero-title">${healthHeadline(net.salud.pct)}</div>
       <div class="hero-sub">${net.prioridades.length} situaciones requieren atención esta semana.</div>`
    : `<div class="hero-title">Todo está bajo control.</div>`;

  const kpis = [
    { label: 'Productores', value: fmt(k.productores, 0), hint: 'en la red del acopio' },
    { label: 'Lotes', value: fmt(k.lotes, 0), hint: 'monitoreados' },
    { label: 'Área monitoreada', value: fmt(k.area_ha), hint: 'hectáreas' },
    { label: 'En riesgo', value: fmt(k.lotes_riesgo, 0), hint: 'lotes con alerta', warn: true },
  ].map((c) => `<div class="kpi ${c.warn ? 'warn-kpi' : ''}">
      <div class="label">${c.label}</div><div class="value">${c.value}</div><div class="hint">${c.hint}</div>
    </div>`).join('');

  const rail = net.prioridades.map((p) => `<div class="rail-item rv-${p.severidad}">
      <div class="rail-head"><span class="sev">${SEVERITY_MARK[p.severidad] || '●'}</span>${p.titulo}
        <b>${p.lotes} ${p.lotes === 1 ? 'lote' : 'lotes'}</b></div>
      <p>${p.detalle}</p>
      <button class="btn ghost rail-go" type="button" data-go="${p.id === 'pr-medicion' ? 'lote' : 'productores'}">${p.meta} →</button>
    </div>`).join('');

  const atencion = net.productores
    .filter((p) => p.lotes_riesgo > 0)
    .sort((a, b) => b.riesgo_pct - a.riesgo_pct)
    .slice(0, 3)
    .map((p) => `<button class="atencion-item" type="button" data-prod="${p.id}">
      <b>${p.nombre}</b> · ${p.lotes} ${p.lotes === 1 ? 'lote' : 'lotes'} <span class="sev" title="riesgo ${p.riesgo_nivel}">${LEVEL_MARK[p.riesgo_nivel] || '○'}</span>
    </button>`).join('');

  const movimientos = net.movimientos.map((m) => `<li>${m.icono} <b>${m.cantidad}</b> ${m.texto}</li>`).join('');
  const horizonte = net.horizonte.map((h) => `<div class="horizon-row">
      <span class="horizon-icon">${h.icono}</span>
      <span class="horizon-label">${h.etiqueta}</span>
      <span class="horizon-bars">${'█'.repeat(h.barras)}${'░'.repeat(10 - h.barras)}</span>
      <span class="horizon-level lv-${h.nivel}">${h.nivel}</span>
    </div>`).join('');

  return `<div class="rwrap">
    <section class="hero">${hero}<span class="demo-chip">red demostrativa</span></section>

    <div class="kpi-grid">${kpis}</div>

    <div class="net-grid">
      <section class="card map-card">
        <div class="nutrients">
          <span class="layer-title">Riesgo de abastecimiento</span>
          <span class="spacer"></span>
          <span class="uncertain-note">productores por nivel de riesgo</span>
        </div>
        <div class="map-stage" id="stage">
          <div class="tiles" id="tiles"></div>
          <canvas id="heat"></canvas>
          <svg id="overlay"></svg>
          <div class="dot-legend"><span class="pdot pdot-alto"></span> alto <span class="pdot pdot-medio"></span> medio <span class="pdot pdot-bajo"></span> bajo</div>
          <div class="map-status" id="map-status" hidden></div>
          <div class="attribution">${ATTRIBUTION}</div>
        </div>
      </section>

      <section class="card rail">
        <h2>Prioridad hoy</h2>
        ${rail || '<p class="note">Sin acciones pendientes.</p>'}
      </section>
    </div>

    <div class="bot-grid">
      <section class="card health">
        <h2>Salud de abastecimiento</h2>
        <div class="health-pct">${net.salud.pct}%</div>
        ${riskBar(net.salud.pct)}
        <p class="note">${net.salud.lotes_ok} de ${k.lotes} lotes sin alertas críticas.
          <span class="${net.salud.delta_semana < 0 ? 'delta-bad' : 'delta-good'}">${net.salud.delta_semana >= 0 ? '+' : ''}${net.salud.delta_semana} pts vs. la semana pasada</span></p>
        <p class="note">Área en riesgo: <b>${fmt(net.area_riesgo.ha)} ha</b> (${net.area_riesgo.pct}% de tu área).</p>
        <p class="note">Riesgo, próximos 30 días:</p>
        ${horizonte}
      </section>

      <section class="card attention">
        <h2>Productores que requieren atención</h2>
        ${atencion || '<p class="note">Ninguno por ahora.</p>'}
      </section>

      <section class="card moves">
        <h2>Próximos movimientos</h2>
        <ul class="moves-list">${movimientos}</ul>
        <p class="note">${net.proximos_7d} acciones en los próximos 7 días.</p>
      </section>
    </div>
  </div>`;
}

function viewMapa() {
  const filter = ['todos', 'alto', 'medio', 'bajo'].map((f) =>
    `<button class="fchip ${state.riesgoFiltro === f ? 'on' : ''}" type="button" data-filtro="${f}">${f[0].toUpperCase() + f.slice(1)}</button>`).join('');
  const toggles = [
    ['lot', 'Nutrientes del lote'],
    ['red', 'Red del acopio'],
  ].map(([mode, label]) =>
    `<button class="fchip ${state.mapMode === mode ? 'on' : ''}" type="button" data-mode="${mode}">${label}</button>`).join('');

  return `<div class="rwrap">
    <section class="card map-card map-full">
      <div class="nutrients">
        ${toggles}
        ${state.mapMode === 'lot'
          ? `${NUTRIENTS.map((n) => `<button class="nut" data-nut="${n}" aria-pressed="${n === state.nutrient}">${n}</button>`).join('')}
             <span class="spacer"></span>
             <span class="uncertain-note">rayado = sin certeza · ${state.view.coverage.uncertainPct}% del lote</span>`
          : `<span class="spacer"></span><span class="uncertain-note">filtro por riesgo</span>${filter}`}
      </div>
      <div class="map-stage" id="stage">
        <div class="tiles" id="tiles"></div>
        <canvas id="heat"></canvas>
        <svg id="overlay"></svg>
        ${state.mapMode === 'lot' ? `<div class="map-title"><b id="map-nutrient">${state.nutrient}</b> en el lote<span>ppm · celda ${state.view.grid.celda_m} m · ✛ mida aquí</span></div>
        <div id="colorbar-slot"></div>` : `<div class="dot-legend"><span class="pdot pdot-alto"></span> alto <span class="pdot pdot-medio"></span> medio <span class="pdot pdot-bajo"></span> bajo</div>`}
        <div class="map-status" id="map-status" hidden></div>
        <div class="attribution">${ATTRIBUTION}</div>
      </div>
    </section>
  </div>`;
}

function viewProductores() {
  const cards = state.network.productores.map((p) => `<article class="prod-card ${p.piloto ? 'prod-piloto' : ''}">
      <header><b>${p.nombre}</b>${p.piloto ? '<span class="demo-chip">piloto real</span>' : ''}<span class="sev" title="riesgo ${p.riesgo_nivel}">${LEVEL_MARK[p.riesgo_nivel] || '○'}</span></header>
      <div class="prod-facts">${p.lotes} ${p.lotes === 1 ? 'lote' : 'lotes'} · ${fmt(p.area_ha)} ha · ${p.lotes_riesgo} ${p.lotes_riesgo === 1 ? 'en riesgo' : 'en riesgo'}</div>
      <div class="prod-risk"><span>Riesgo</span>${riskBar(p.riesgo_pct)}<b>${p.riesgo_pct}%</b></div>
      <div class="prod-meta">Última medición: ${p.ultima_medicion}</div>
      <button class="btn ghost" type="button" data-prod="${p.id}">${state.productor === p.id ? 'Seleccionado' : 'Ver productor'}</button>
    </article>`).join('');

  const detail = state.productor
    ? (() => {
      const p = state.network.productores.find((x) => x.id === state.productor);
      if (!p) return '';
      return `<section class="card prod-detail">
        <h2>${p.nombre}${p.piloto ? ' · piloto real' : ' · red demostrativa'}</h2>
        <div class="prod-facts">${p.lotes} ${p.lotes === 1 ? 'lote' : 'lotes'} · ${fmt(p.area_ha)} ha</div>
        <div class="prod-risk"><span>Riesgo</span>${riskBar(p.riesgo_pct)}<b>${p.riesgo_pct}%</b></div>
        <div class="prod-meta">Última medición: ${p.ultima_medicion}</div>
        ${p.pkg
          ? `<p class="note">Este lote es el dato real del repositorio.</p>
             <button class="btn" type="button" data-ver-lote="${p.pkg}">Ver lote El Rosal →</button>`
          : `<p class="note">Paquete demostrativo: el piloto El Rosal es el que trae el dato real.</p>`}
      </section>`;
    })()
    : '';

  return `<div class="rwrap">
    <div class="prod-grid">${cards}</div>
    <div class="prod-detail-slot">${detail}</div>
  </div>`;
}

function viewLote() {
  const view = state.view;
  const worstZone = view.zonas[0];

  return `<div class="bcrumb"><button class="btn ghost" type="button" data-nav="productores">← Red del acopio</button></div>
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
    </div>`;
}

function render() {
  const view = state.view;
  const net = state.network;
  const syncLabel = view.stale ? 'vencido' : state.live ? 'al día' : 'sin red · paquete local';

  document.getElementById('app').innerHTML = `<div class="shell">
    <div class="sync ${view.stale ? 'stale' : ''}">
      <span class="dot"></span>${syncLabel} · ${view.sampling.valid} mediciones · ${state.dataOrigin}
      ${net.acopio.demo ? '<span class="demo-chip">red demostrativa</span>' : ''}
      <span class="aviso">${view.aviso || ''}</span>
    </div>

    <div class="topbar">
      <div class="mark">iO</div>
      <div class="brand-name">${net.acopio.nombre}<small>${net.kpis.productores} productores · ${net.kpis.lotes} lotes · Nariño</small></div>
      <span class="spacer"></span>
      <span class="bell" title="${net.prioridades.length} prioridades activas">🔔 ${net.prioridades.length > 0 ? `<b>${net.prioridades.length}</b>` : ''}</span>
      <button class="btn ghost ask-cta" type="button" title="Preguntar a IOmido">🎙 Preguntar</button>
      <span class="user" title="Acopio Pasto">👤</span>
    </div>

    <nav class="nav" aria-label="Vistas del acopio">
      ${['resumen', 'mapa', 'productores', 'lote'].map((n) =>
        `<button class="nav-btn ${state.nav === n ? 'on' : ''}" type="button" data-nav="${n}">
           ${n === 'lote' ? 'Lote El Rosal' : n[0].toUpperCase() + n.slice(1)}
         </button>`).join('')}
    </nav>

    <main class="main" id="main">${state.nav === 'resumen' ? viewResumen() : state.nav === 'mapa' ? viewMapa() : state.nav === 'productores' ? viewProductores() : viewLote()}</main>
  </div>`;

  for (const button of document.querySelectorAll('.nav-btn')) {
    button.addEventListener('click', () => go(button.dataset.nav));
  }
  for (const button of document.querySelectorAll('[data-nav]')) {
    if (!button.classList.contains('nav-btn')) button.addEventListener('click', () => go(button.dataset.nav));
  }
  const askCta = document.querySelector('.ask-cta');
  if (askCta) askCta.addEventListener('click', () => go('lote', 'asistente'));

  for (const button of document.querySelectorAll('.nut')) {
    button.addEventListener('click', () => { state.nutrient = button.dataset.nut; paintNutrientToggle(); scheduleDraw(); });
  }
  for (const button of document.querySelectorAll('[data-mode]')) {
    button.addEventListener('click', () => { state.mapMode = button.dataset.mode; render(); });
  }
  for (const button of document.querySelectorAll('[data-filtro]')) {
    button.addEventListener('click', () => { state.riesgoFiltro = button.dataset.filtro; render(); });
  }
  for (const button of document.querySelectorAll('[data-prod]')) {
    button.addEventListener('click', () => selectProducer(button.dataset.prod));
  }
  for (const button of document.querySelectorAll('[data-ver-lote]')) {
    button.addEventListener('click', () => go('lote'));
  }
  for (const button of document.querySelectorAll('.rail-go')) {
    button.addEventListener('click', () => go(button.dataset.go));
  }

  if (state.nav === 'lote') wireTabs(state.tabInicial);
  if (state.nav === 'resumen' || state.nav === 'mapa' || state.nav === 'lote') {
    paintNutrientToggle();
    observeStage();
  }
}

function selectProducer(id) {
  state.productor = state.productor === id ? null : id;
  render();
}

function go(nav, tab = null) {
  state.nav = NAV_VIEWS.includes(nav) ? nav : 'resumen';
  state.tabInicial = state.nav === 'lote' ? tab : null;
  location.hash = `#${state.nav}`;
  render();
}

window.addEventListener('hashchange', () => {
  const target = navFromHash();
  if (target !== state.nav) go(target);
});

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => scheduleDraw(), 160);
});

async function boot() {
  const [pkg, net] = await Promise.all([getPackage(), getNetwork()]);
  state.view = adapt(pkg.data);
  state.network = net.data;
  state.dataOrigin = pkg.origin;
  state.live = pkg.live;
  state.nav = navFromHash();
  render();
}

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

boot().catch((error) => {
  document.getElementById('app').innerHTML = `<div class="loading">No se pudo cargar el acopio.<br><small>${error.message}</small></div>`;
});