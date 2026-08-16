// Command-center shell: the acopio network first, the lot package as drill-down.

import {
  getPackage, apiBase, postDecision, getProposalWhy, getDecisionHistory,
} from './lib/api.js';
import { getNetwork } from './lib/network.js';
import { adapt, latLonToCell } from './lib/adapt.js';
import { NUTRIENTS, RANGES } from './lib/plotmap.js';
import { plasmaGradient } from './lib/colormap.js';
import { renderTiles, ATTRIBUTION } from './lib/slippy.js';
import { gridGeoBounds, paintSurface, paintOverlay } from './lib/heatsurface.js';
import { ask, speak, stopSpeaking, listen, canSpeak, canListen } from './lib/assistant.js';

const state = {
  nutrient: 'K',
  map: { zoomOffset: 0, panX: 0, panY: 0 },
  projector: null,
  probe: null,
  nav: 'resumen',
  mapMode: 'red',
  riesgoFiltro: 'todos',
  productor: null,
  decision: null,
  decisionMsg: '',
  view: null,
  network: null,
  dataOrigin: '',
  live: false,
};

const fmt = (value, decimals = 1) => Number(value)
  .toLocaleString('es-CO', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const NIVEL_LABEL = { critico: 'crítico', bajo: 'bajo', adecuado: 'bien' };
const DECISION_LABEL = {
  pending: 'pendiente', accepted: 'aceptada', rejected: 'rechazada',
  deferred: 'derivada', referred: 'derivada', modified: 'modificada',
  pending_review: 'pendiente de revisión',
  pending_technical_review: 'pendiente de revisión técnica',
  referred_to_technician: 'derivada a un técnico',
};
const VALIDATION_LABEL = {
  requires_technical_validation: 'Plan candidato: requiere validación técnica antes de aplicarse.',
  demo_unvalidated: 'Perfil de demostración sin validar.',
};
const SEVERITY_MARK = {
  critica: '▲', alta: '▲', media: '●', baja: '○', aviso: '○',
  critical: '▲', high: '▲', medium: '●', low: '○',
};
const SEVERITY_WORD = { critical: 'crítica', high: 'alta', medium: 'media', low: 'baja' };
const RISK_TITLE = { frost: 'Helada', drought: 'Sequía', late_blight: 'Gota', seasonal: 'Estacional' };
const LEVEL_MARK = { alto: '▲', medio: '●', bajo: '○' };
// Every view still routes: #mapa and #productores stay reachable by URL.
const NAV_VIEWS = ['resumen', 'mapa', 'productores', 'lote'];
// The MVP menu shows only these two. Widening it is a one-line change.
const MENU_VIEWS = ['resumen', 'lote'];

function navFromHash() {
  const target = decodeURIComponent(location.hash.slice(1));
  return NAV_VIEWS.includes(target) ? target : 'resumen';
}

// A jump into a view the menu hides would strand the user, so it lands on the
// summary instead. The target view itself is untouched.
function reachable(view) {
  return MENU_VIEWS.includes(view) ? view : 'resumen';
}

function colorbar() {
  const [min, max] = RANGES[state.nutrient];
  const ticks = [1, 0.75, 0.5, 0.25, 0]
    .map((t) => `<span>${Math.round(min + (max - min) * t)} %</span>`).join('');
  return `<div class="colorbar">
    <div class="ramp" style="background:linear-gradient(to top, ${plasmaGradient()})"></div>
    <div class="ticks">${ticks}</div>
  </div>`;
}

function networkBounds() {
  const producers = state.network.productores
    .filter((producer) => Number.isFinite(producer.lat) && Number.isFinite(producer.lon));
  const points = producers.length
    ? producers.map((producer) => ({ lat: producer.lat, lon: producer.lon }))
    : (state.view?.contorno || []).map(([lat, lon]) => ({ lat, lon }));
  if (!points.length) throw new Error('No hay ubicaciones para representar la red.');
  const pad = 0.03;
  return {
    north: Math.max(...points.map((point) => point.lat)) + pad,
    south: Math.min(...points.map((point) => point.lat)) - pad,
    east: Math.max(...points.map((point) => point.lon)) + pad,
    west: Math.min(...points.map((point) => point.lon)) - pad,
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

// The MVP summary watches one real plot, so it draws that plot. The network
// layer is left for the map view and for a summary without a loaded package.
function showingNetwork() {
  return (state.nav === 'mapa' && state.mapMode === 'red')
    || (state.nav === 'resumen' && !state.view);
}

function drawMap() {
  const stage = document.getElementById('stage');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return;
  const status = document.getElementById('map-status');
  const tiles = document.getElementById('tiles');
  const overlay = document.getElementById('overlay');
  const showNetwork = showingNetwork();
  try {
    if (showNetwork) {
      const projector = renderTiles(tiles, networkBounds(), rect.width, rect.height, state.map);
      state.projector = projector;
      const producers = state.riesgoFiltro === 'todos'
        ? state.network.productores
        : state.network.productores.filter((p) => p.riesgo_nivel === state.riesgoFiltro);
      paintNetworkDots(projector, producers);
      if (overlay) for (const circle of overlay.querySelectorAll('.pdot')) {
        circle.addEventListener('click', () => selectProducer(circle.dataset.prod));
      }
    } else {
      const view = state.view;
      const projector = renderTiles(tiles, gridGeoBounds(view.grid), rect.width, rect.height, state.map);
      state.projector = projector;
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

const DRAG_SLOP_PX = 5;
const ZOOM_LIMIT = 4;

function resetMapView() {
  state.map = { zoomOffset: 0, panX: 0, panY: 0 };
  state.probe = null;
  drawMap();
  showProbe();
}

function zoomBy(step) {
  const next = Math.max(-2, Math.min(ZOOM_LIMIT, state.map.zoomOffset + step));
  if (next === state.map.zoomOffset) return;
  state.map = { ...state.map, zoomOffset: next };
  drawMap();
}

// Reads the grid cell under a point of the stage, so a tap answers "what is here".
function probeAt(clientX, clientY) {
  const stage = document.getElementById('stage');
  const view = state.view;
  if (!stage || !state.projector || !view || showingNetwork()) return null;
  const rect = stage.getBoundingClientRect();
  const { lat, lon } = state.projector.toLatLon(clientX - rect.left, clientY - rect.top);
  const { grid } = view;
  const { c, r } = latLonToCell(lat, lon, grid);
  if (c < 0 || c >= grid.cols || r < 0 || r >= grid.rows) return null;
  const index = r * grid.cols + c;
  if (!grid.mask[index]) return null;
  return {
    index,
    N: grid.N[index],
    P: grid.P[index],
    K: grid.K[index],
    sigma: grid.sigma[index],
    incierto: grid.sigma[index] > grid.sigma_umbral,
  };
}

function showProbe() {
  const box = document.getElementById('map-probe');
  if (!box) return;
  const p = state.probe;
  if (!p) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.innerHTML = `<b>N ${fmt(p.N)} % · P ${fmt(p.P)} % · K ${fmt(p.K)} %</b>`
    + `<span>${p.incierto ? 'el modelo no tiene certeza aquí' : `incertidumbre ${fmt(p.sigma)} %`}</span>`;
}

function wireMapGestures() {
  const stage = document.getElementById('stage');
  if (!stage || stage.dataset.wired === '1') return;
  stage.dataset.wired = '1';

  const layers = () => [document.getElementById('tiles'), document.getElementById('heat'), document.getElementById('overlay')].filter(Boolean);
  let dragging = false;
  let moved = 0;
  let startX = 0;
  let startY = 0;

  stage.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    dragging = true;
    moved = 0;
    startX = event.clientX;
    startY = event.clientY;
    stage.setPointerCapture(event.pointerId);
    stage.classList.add('grabbing');
  });

  stage.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    moved = Math.max(moved, Math.hypot(dx, dy));
    // Translate the painted layers while dragging; the tiles are rebuilt on release.
    for (const layer of layers()) layer.style.transform = `translate(${dx}px, ${dy}px)`;
  });

  const release = (event) => {
    if (!dragging) return;
    dragging = false;
    stage.classList.remove('grabbing');
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    for (const layer of layers()) layer.style.transform = '';
    if (moved > DRAG_SLOP_PX) {
      state.map = { ...state.map, panX: state.map.panX - dx, panY: state.map.panY - dy };
      drawMap();
      return;
    }
    state.probe = probeAt(event.clientX, event.clientY);
    showProbe();
  };

  stage.addEventListener('pointerup', release);
  stage.addEventListener('pointercancel', () => { dragging = false; stage.classList.remove('grabbing'); });

  stage.addEventListener('wheel', (event) => {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 1 : -1);
  }, { passive: false });

  stage.addEventListener('dblclick', () => zoomBy(1));
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

function panelPropuesta() {
  const { propuesta } = state.view;
  if (!propuesta || !propuesta.zonas.length) {
    return '<p class="note">Todavía no hay una propuesta para este lote.</p>';
  }

  const zones = propuesta.zonas.map((zona) => {
    const formulations = zona.formulaciones.map((f) => `<div class="form-row">
        <span class="grade">${f.label}</span>
        <span class="form-qty"><b>${f.bags}</b> ${f.bags === 1 ? 'bulto' : 'bultos'} de ${f.bag_weight.value} ${f.bag_weight.unit}</span>
      </div>`).join('');

    const need = zona.evaluacion?.crop_requirement;
    const have = zona.evaluacion?.estimated_crop_available;
    const balance = need && have ? NUTRIENTS.map((n) => `<li>
        <b>${n}</b> ${fmt(have[n])} de ${fmt(need[n])} kg/ha disponibles
        <span class="lv-${zona.nivel[n]}">${NIVEL_LABEL[zona.nivel[n]]}</span>
      </li>`).join('') : '';

    return `<article class="zone-prop">
      <header><b>Zona ${zona.id.replace('zone-', '')}</b> · ${fmt(zona.area_ha, 2)} ha</header>
      <p class="note">Formulación NPK sugerida</p>
      ${formulations}
      ${balance ? `<ul class="balance">${balance}</ul>` : ''}
    </article>`;
  }).join('');

  return `<div class="proposal">
    ${zones}
    <p class="note">Un grado <b>30-30-40</b> es 30 % N, 30 % P y 40 % K de la masa del bulto.</p>
    ${decisionBlock(propuesta)}
  </div>`;
}

function decisionBlock(propuesta) {
  const estado = state.decision?.resulting_status || propuesta.estado;
  const aplicada = state.decision ? state.decision.applied : propuesta.aplicada;

  return `<div class="decision" id="decision">
    <div class="decision-state">
      <span class="pill pill-${estado}">${DECISION_LABEL[estado] || estado}</span>
      ${aplicada ? '<span class="pill pill-applied">aplicada</span>' : '<span class="note">no aplicada</span>'}
    </div>
    ${propuesta.validacion ? `<p class="note">${VALIDATION_LABEL[propuesta.validacion] || propuesta.validacion}</p>` : ''}
    ${propuesta.requiere_decision ? `<p class="note">Requiere la decisión de un técnico antes de aplicarse.</p>
      <div class="decision-actions">
        <button class="btn" type="button" data-decide="accept" ${apiBase ? '' : 'disabled'}>Aceptar</button>
        <button class="btn ghost" type="button" data-decide="refer" ${apiBase ? '' : 'disabled'}>Pedir revisión</button>
        <button class="btn ghost" type="button" data-why="${propuesta.id}">¿Por qué?</button>
      </div>
      ${apiBase ? '' : '<p class="note">Sin conexión no se puede registrar una decisión.</p>'}` : ''}
    <div class="decision-msg" id="decision-msg" ${state.decisionMsg ? '' : 'hidden'}>${state.decisionMsg || ''}</div>
    <div class="why-body" id="why-body" hidden></div>
  </div>`;
}

function panelRiesgos() {
  const { riesgos, estacional, degradado } = state.view;
  if (riesgos.length === 0) return '<p class="note">Sin riesgos activos para este lote.</p>';

  const cards = riesgos.map((r, index) => `<article class="risk sev-${r.severidad} ${index === 0 ? 'open' : ''}">
      <button class="risk-head" type="button" aria-expanded="${index === 0}">
        <span class="mark">${SEVERITY_MARK[r.severidad] || '●'}</span>
        <span class="sev-label">${SEVERITY_WORD[r.severidad] || r.severidad}</span>
        <span class="risk-title">${RISK_TITLE[r.tipo] || r.tipo}</span>
      </button>
      <div class="risk-body">
        <p>Ventana ${r.ventana?.start} a ${r.ventana?.end} · confianza ${Math.round((r.confianza ?? 0) * 100)}%</p>
        ${r.accion ? `<ul><li>${r.accion}</li></ul>` : ''}
        ${(r.confianza ?? 1) < 0.5 ? '<p class="low-conf">Esto todavía puede cambiar.</p>' : ''}
        <button class="why" type="button" data-risk="${r.tipo}">¿Por qué?</button>
        <div class="why-body" id="why-${r.tipo}" hidden>
          <p><b>Probabilidad estimada:</b> ${Math.round((r.score ?? 0) * 100)}%</p>
          <p><b>Datos:</b> ${Object.entries(r.entradas || {}).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}</p>
          <p><b>Fuentes:</b> ${r.fuentes.map((f) => `${f.name}${f.fetched_at ? ` (${f.fetched_at.slice(0, 10)})` : ''}${f.stale || f.failed ? ' · no actual' : ''}`).join(', ')}</p>
          ${r.limitaciones ? `<p><b>Límites:</b> ${r.limitaciones}</p>` : ''}
        </div>
      </div>
    </article>`).join('');

  return `<div class="scroll-y">${cards}
    ${estacional?.enso ? `<p class="note"><b>ENSO:</b> ${estacional.enso.phase ?? estacional.enso.status ?? ''}</p>` : ''}
    ${degradado ? '<p class="note warn-text">Alguna fuente no respondió: el clima se muestra como no actual.</p>' : ''}
  </div>`;
}

const ASK_SUGGESTIONS = [
  'qué debo priorizar',
  'dónde debo medir',
  'qué formulación sugieren',
  'por qué hay incertidumbre',
];

function panelAsistente() {
  const suggestions = ASK_SUGGESTIONS;
  const welcome = apiBase
    ? 'Estoy conectado al agente. Pregúntame por este lote, su propuesta, riesgos o mediciones.'
    : 'Modo sin conexión: responderé solo con el paquete descargado de este lote.';
  return `<div class="chat" id="chat" aria-live="polite"><div class="bubble bot">${welcome}</div></div>
    <div class="suggest">${suggestions.map((s) => `<button class="chip as-suggest" type="button">¿${s}?</button>`).join('')}</div>
    <form class="ask" id="ask">
      <input id="ask-input" type="text" placeholder="Pregunte sobre el lote…" autocomplete="off" aria-label="Pregunte sobre el lote">
      <button class="btn icon" id="mic" type="button" title="${canListen ? 'Preguntar por voz' : 'Voz no disponible aquí'}" ${canListen ? '' : 'disabled'}>🎙</button>
      <button class="btn" type="submit">Enviar</button>
    </form>
    <p class="note">${canSpeak ? 'Responde en voz alta.' : 'Este navegador no reproduce voz.'} ${apiBase ? 'Las respuestas usan evidencia del backend.' : 'Sin red no consulta el modelo.'}</p>`;
}

function panelMediciones() {
  const { mediciones, sampling } = state.view;
  const pct = (value) => `${fmt(value, value % 1 === 0 ? 0 : 1)} %`;

  const rows = mediciones.map((m, index) => `<tr class="${m.valido ? '' : 'rejected'}">
      <td>${index + 1}</td>
      <td class="num">${pct(m.N)}</td>
      <td class="num">${pct(m.P)}</td>
      <td class="num">${pct(m.K)}</td>
      <td>${m.valido ? (m.sospechoso ? 'revisar' : 'usada') : 'fuera'}${m.motivo ? `<span class="why-dot" title="${m.motivo}">?</span>` : ''}</td>
    </tr>`).join('');

  return `<div class="scroll-y">
      <table class="readings">
        <thead><tr><th>#</th><th class="num">N</th><th class="num">P</th><th class="num">K</th><th>Estado</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="note">${sampling.valid} de ${sampling.total} mediciones alimentan el modelo. Porcentaje de masa del suelo, lectura cruda del sensor.</p>`;
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
  const panels = {
    propuesta: panelPropuesta,
    riesgos: panelRiesgos,
    mediciones: panelMediciones,
    asistente: panelAsistente,
  };
  const body = document.getElementById('tab-body');

  const show = (name) => {
    stopSpeaking();
    body.innerHTML = panels[name]();
    for (const tab of document.querySelectorAll('.tab')) {
      tab.classList.toggle('on', tab.dataset.tab === name);
      tab.setAttribute('aria-selected', String(tab.dataset.tab === name));
    }

    if (name === 'propuesta') {
      showDecisionMsg();
      for (const button of body.querySelectorAll('[data-decide]')) {
        button.addEventListener('click', () => decide(button.dataset.decide));
      }
      const why = body.querySelector('[data-why]');
      if (why) why.addEventListener('click', () => showWhy(why.dataset.why));
      return;
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
  const openMeasurements = document.querySelector('[data-open-measurements]');
  if (openMeasurements) openMeasurements.addEventListener('click', () => show('mediciones'));
  show(initial || 'propuesta');
}

function healthHeadline(pct) {
  if (pct >= 80) return 'Tu abastecimiento está estable.';
  if (pct >= 60) return 'Tu abastecimiento aguanta, con puntos que vigilar.';
  return 'Tu abastecimiento está comprometido.';
}

// The screen never invents the outcome: it shows what the backend resolved.
async function decide(action) {
  const { propuesta } = state.view;
  const buttons = document.querySelectorAll('[data-decide]');
  for (const b of buttons) b.disabled = true;
  state.decisionMsg = 'Registrando la decisión…';
  showDecisionMsg();

  try {
    const response = await postDecision({
      proposalId: propuesta.id,
      action,
      actor: { type: 'technician', id: 'demo-technician' },
      note: action === 'refer' ? 'Revisión pedida desde el tablero del acopio.' : null,
    });
    const decision = response.decision || response;
    state.decision = {
      id: decision.id,
      resulting_status: decision.resulting_status,
      applied: propuesta.aplicada,
    };
    state.decisionMsg = `Decisión <b>${decision.id}</b> registrada.`;
    try {
      // history is one object holding the proposal, its decisions and the audit trail.
      const { history } = await getDecisionHistory(propuesta.id);
      if (history?.proposal) state.decision.applied = history.proposal.applied;
      const count = history?.decisions?.length || 0;
      if (count) {
        state.decisionMsg += ` ${count} ${count === 1 ? 'decisión' : 'decisiones'} en el historial.`;
      }
    } catch (error) {
      console.warn('[decision] historial no disponible:', error.message);
    }
    wireTabs('propuesta');
  } catch (error) {
    state.decisionMsg = `No se pudo registrar: ${error.message}`;
    showDecisionMsg();
    for (const b of buttons) b.disabled = false;
  }
}

function showDecisionMsg() {
  const box = document.getElementById('decision-msg');
  if (!box) return;
  box.innerHTML = state.decisionMsg;
  box.hidden = !state.decisionMsg;
}

async function showWhy(proposalId) {
  const box = document.getElementById('why-body');
  if (!box) return;
  if (!box.hidden) { box.hidden = true; return; }
  box.hidden = false;
  box.textContent = 'Consultando…';
  const explanation = state.view.propuesta?.explicacion;
  try {
    const remote = await getProposalWhy(proposalId);
    const why = remote.why || remote.explanation || remote;
    box.innerHTML = renderWhy(why);
  } catch (error) {
    box.innerHTML = explanation
      ? `${renderWhy(explanation)}<p class="note">Del paquete descargado: ${error.message}</p>`
      : `<p class="note">No se pudo consultar la explicación: ${error.message}</p>`;
  }
}

function renderWhy(why) {
  const steps = (why.steps || []).map((s) => `<li><b>${s.step}</b> ${s.detail || ''}</li>`).join('');
  const unknowns = (why.unknowns || []).map((u) => `<li>${u}</li>`).join('');
  return `${why.summary ? `<p>${why.summary}</p>` : ''}
    ${steps ? `<ul>${steps}</ul>` : ''}
    ${unknowns ? `<p class="note"><b>Lo que no se sabe</b></p><ul>${unknowns}</ul>` : ''}`;
}

function riskBar(pct) {
  return `<div class="rbar" role="img" aria-label="Riesgo ${pct} %"><i style="width:${pct}%"></i></div>`;
}

// The MVP watches a single real plot, so the summary is a decision queue: what
// needs a hand today, and one way into the file. The network dashboard below is
// kept whole for when there are many plots to compare.
function viewResumen() {
  const view = state.view;
  const net = state.network;
  if (!view) return viewResumenRed();

  const pendiente = view.propuesta?.requiere_decision && !state.decision;
  const riesgoTop = view.riesgos[0];
  const decidido = state.decision?.resulting_status;

  const titular = pendiente
    ? 'Una propuesta espera su decisión.'
    : riesgoTop
      ? `${RISK_TITLE[riesgoTop.tipo] || 'Riesgo'} por delante en El Rosal.`
      : 'El Rosal está al día.';

  const kpis = [
    { label: 'Área del lote', value: `${fmt(view.plot.area_ha, 2)} ha`, hint: view.plot.municipality || view.plot.municipio || '' },
    { label: 'Mediciones', value: `${view.sampling.valid}/${view.sampling.total}`, hint: 'alimentan el modelo' },
    { label: 'En nivel crítico', value: `${fmt(view.criticalSharePct)}%`, hint: `${fmt(view.criticalAreaHa, 2)} ha del lote`, warn: view.criticalSharePct > 40 },
    { label: 'Sin certeza', value: `${view.coverage.uncertainPct}%`, hint: 'del lote, según el modelo' },
  ].map((c) => `<div class="kpi ${c.warn ? 'warn-kpi' : ''}">
      <div class="label">${c.label}</div><div class="value">${c.value}</div><div class="hint">${c.hint}</div>
    </div>`).join('');

  const cola = [];
  if (pendiente) {
    cola.push({
      sev: 'alta',
      titulo: 'Propuesta sin decidir',
      detalle: 'El plan de fertilización por zonas está calculado, pero nadie lo ha aceptado ni devuelto a revisión.',
      meta: 'Abrir la propuesta',
      tab: 'propuesta',
    });
  } else if (decidido) {
    cola.push({
      sev: 'baja',
      titulo: `Propuesta ${DECISION_LABEL[decidido] || decidido}`,
      detalle: 'La decisión quedó registrada con su responsable y su hora.',
      meta: 'Ver la propuesta',
      tab: 'propuesta',
    });
  }
  if (riesgoTop) {
    cola.push({
      sev: riesgoTop.severidad === 'high' || riesgoTop.severidad === 'critical' ? 'alta' : 'media',
      titulo: `${RISK_TITLE[riesgoTop.tipo] || riesgoTop.tipo} · severidad ${SEVERITY_WORD[riesgoTop.severidad] || riesgoTop.severidad}`,
      // The backend writes the recommended action in English; the card in the lot
      // view shows it verbatim, so here the summary states the window instead.
      detalle: riesgoTop.ventana?.start
        ? `Ventana del ${riesgoTop.ventana.start.slice(0, 10)} al ${riesgoTop.ventana.end.slice(0, 10)}`
          + `${Number.isFinite(riesgoTop.confianza) ? `, con ${Math.round(riesgoTop.confianza * 100)} % de confianza` : ''}.`
        : 'Riesgo detectado por el modelo climático.',
      meta: 'Ver por qué',
      tab: 'riesgos',
    });
  }
  if (view.nextSample) {
    cola.push({
      sev: 'media',
      titulo: 'Falta medir donde el modelo duda',
      detalle: `El punto sugerido está a ${fmt(view.nextSample.distancia_m, 0)} m de la medición más cercana,`
        + ` con ${fmt(view.nextSample.incertidumbre)} puntos de incertidumbre.`,
      meta: 'Ver en el mapa',
      tab: 'propuesta',
    });
  }

  const rail = cola.map((c) => `<div class="rail-item rv-${c.sev}">
      <div class="rail-head"><span class="sev">${SEVERITY_MARK[c.sev] || '●'}</span>${c.titulo}</div>
      <p>${c.detalle}</p>
      <button class="btn ghost rail-go" type="button" data-go="lote" data-tab-go="${c.tab}">${c.meta} →</button>
    </div>`).join('');

  return `<div class="rwrap rwrap-mvp">
    <section class="hero">
      <div class="hero-title">${titular}</div>
      <div class="hero-sub">${view.plot.name} · ${view.cultivo?.crop || ''} ${view.cultivo?.variety || ''} · medido ${new Date(view.generado).toLocaleDateString('es-CO')}</div>
    </section>

    ${net?.real ? `<section class="card real-plots">
      <h2>Lotes del centro · datos reales</h2>
      <ul class="moves-list">${net.real.lotes.map((l) => `<li>
        <b>${l.name}</b> · ${l.municipality} · ${l.reading_count} ${l.reading_count === 1 ? 'medición' : 'mediciones'}
      </li>`).join('')}</ul>
      <p class="note">Del backend: <code>/v1/centers/{id}/dashboard</code>.</p>
    </section>` : ''}

    <div class="kpi-grid">${kpis}</div>

    <div class="mvp-main net-grid">
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
          <div class="map-title"><b id="map-nutrient">${state.nutrient}</b> en el lote<span>% de masa · celda ${view.grid.celda_m} m · ✛ mida aquí</span></div>
          <div id="colorbar-slot"></div>
          <div class="map-ctl">
            <button type="button" data-map="in" aria-label="Acercar">+</button>
            <button type="button" data-map="out" aria-label="Alejar">−</button>
            <button type="button" data-map="reset" aria-label="Centrar el mapa">⌖</button>
          </div>
          <div class="map-probe" id="map-probe" hidden></div>
          <div class="map-status" id="map-status" hidden></div>
          <div class="attribution">${ATTRIBUTION}</div>
        </div>
      </section>

      <section class="card rail">
        <h2>Prioridad hoy</h2>
        ${rail || '<p class="note">Sin acciones pendientes.</p>'}
      </section>
    </div>

    <button class="btn open-lote" type="button" data-nav="lote">Abrir ${view.plot.name} →</button>

    ${view.stale ? '<p class="note">El paquete pasó su ventana de validez: conviene recalcularlo.</p>' : ''}
  </div>`;
}

function viewResumenRed() {
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

  return `<div class="rwrap resumen-c">
    <section class="hero">${hero}<span class="demo-chip">productores demostrativos</span></section>

    ${net.real ? `<section class="card real-plots">
      <h2>Lotes del centro · datos reales</h2>
      <ul class="moves-list">${net.real.lotes.map((l) => `<li>
        <b>${l.name}</b> · ${l.municipality} · ${l.reading_count} ${l.reading_count === 1 ? 'medición' : 'mediciones'}
      </li>`).join('')}</ul>
      <p class="note">Del backend: <code>/v1/centers/{id}/dashboard</code>.</p>
    </section>` : ''}

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
          <div class="map-ctl">
            <button type="button" data-map="in" aria-label="Acercar">+</button>
            <button type="button" data-map="out" aria-label="Alejar">−</button>
            <button type="button" data-map="reset" aria-label="Centrar el mapa">⌖</button>
          </div>
          <div class="map-probe" id="map-probe" hidden></div>
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
        ${state.mapMode === 'lot' ? `<div class="map-title"><b id="map-nutrient">${state.nutrient}</b> en el lote<span>% de masa · celda ${state.view.grid.celda_m} m · ✛ mida aquí</span></div>
        <div id="colorbar-slot"></div>` : `<div class="dot-legend"><span class="pdot pdot-alto"></span> alto <span class="pdot pdot-medio"></span> medio <span class="pdot pdot-bajo"></span> bajo</div>`}
        <div class="map-ctl">
            <button type="button" data-map="in" aria-label="Acercar">+</button>
            <button type="button" data-map="out" aria-label="Alejar">−</button>
            <button type="button" data-map="reset" aria-label="Centrar el mapa">⌖</button>
          </div>
          <div class="map-probe" id="map-probe" hidden></div>
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

  return `<div class="bcrumb"><button class="btn ghost" type="button" data-nav="${reachable('productores')}">← Red del acopio</button></div>
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
          <div class="map-title"><b id="map-nutrient">${state.nutrient}</b> en el lote<span>% de masa · celda ${view.grid.celda_m} m · ✛ mida aquí</span></div>
          <div id="colorbar-slot"></div>
          <div class="map-ctl">
            <button type="button" data-map="in" aria-label="Acercar">+</button>
            <button type="button" data-map="out" aria-label="Alejar">−</button>
            <button type="button" data-map="reset" aria-label="Centrar el mapa">⌖</button>
          </div>
          <div class="map-probe" id="map-probe" hidden></div>
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
          <p>Se conserva en el historial, pero no alimenta el modelo.</p>
          <div class="amber-actions"><button class="btn ghost" type="button" data-open-measurements>Ver mediciones →</button></div>
        </div>` : ''}

        <section class="card tabs-card">
          <div class="tabs" role="tablist">
            <button class="tab" data-tab="propuesta" role="tab" aria-selected="true">Propuesta</button>
            <button class="tab" data-tab="riesgos" role="tab" aria-selected="false">Lo que viene${view.riesgos.length ? ` <span class="badge-n">${view.riesgos.length}</span>` : ''}</button>
            <button class="tab" data-tab="mediciones" role="tab" aria-selected="false">Mediciones</button>
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
  const syncLabel = view.stale ? 'paquete degradado' : state.live ? 'al día' : 'sin red · paquete local';

  document.getElementById('app').innerHTML = `<div class="shell">
    <div class="sync ${view.stale ? 'stale' : ''}">
      <span class="dot"></span>${syncLabel} · ${view.sampling.valid} mediciones · ${state.dataOrigin}
      ${net.acopio.demo ? '<span class="demo-chip">red demostrativa</span>' : ''}
      <span class="aviso">${view.aviso || ''}</span>
    </div>

    <div class="topbar">
      <div class="mark">iO</div>
      <div class="brand-name">${net.acopio.nombre}<small>${net.real
        ? `${net.real.lotes.length} ${net.real.lotes.length === 1 ? 'lote' : 'lotes'} · ${net.acopio.municipio}`
        : `${net.kpis.productores} productores · ${net.kpis.lotes} lotes · ${net.acopio.municipio}`}</small></div>
      <span class="spacer"></span>
      <span class="bell" title="${net.prioridades.length} prioridades activas">🔔 ${net.prioridades.length > 0 ? `<b>${net.prioridades.length}</b>` : ''}</span>
      <button class="btn ghost ask-cta" type="button" title="Preguntar a IOmido">🎙 Preguntar</button>
      <span class="user" title="Acopio Pasto">👤</span>
    </div>

    <nav class="nav" aria-label="Vistas del acopio">
      ${MENU_VIEWS.map((n) =>
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
    button.addEventListener('click', () => go(reachable(button.dataset.go), button.dataset.tabGo || null));
  }

  for (const button of document.querySelectorAll('[data-map]')) {
    button.addEventListener('click', () => {
      if (button.dataset.map === 'reset') resetMapView();
      else zoomBy(button.dataset.map === 'in' ? 1 : -1);
    });
  }
  if (state.nav === 'lote') wireTabs(state.tabInicial);
  if (state.nav === 'resumen' || state.nav === 'mapa' || state.nav === 'lote') {
    paintNutrientToggle();
    observeStage();
    wireMapGestures();
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
