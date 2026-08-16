// Command-center shell: the acopio network first, the lot package as drill-down.

import {
  getPackage, apiBase, postDecision, getProposalWhy, getDecisionHistory,
} from './lib/api.js';
import { getNetwork } from './lib/network.js';
import { adapt, latLonToCell } from './lib/adapt.js';
import { NUTRIENTS, RANGES } from './lib/plotmap.js';
import { plasmaGradient } from './lib/colormap.js';
import { renderTiles, ATTRIBUTION, MIN_ZOOM, MAX_ZOOM } from './lib/slippy.js';
import { gridGeoBounds, paintSurface, paintOverlay } from './lib/heatsurface.js';
import { ask, speak, stopSpeaking, listen, canSpeak, canListen } from './lib/assistant.js';
import { qrSvg } from './lib/qr.js';

const ACTA_PATH = '/informes/acta-plan-el-rosal.pdf';

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
  historial: null,
  historialMsg: '',
  riesgoAbrir: null,
  view: null,
  network: null,
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
// What the person did, and who they were. The backend stores both in English.
const ACTION_LABEL = {
  accept: 'Aceptar', reject: 'Rechazar', modify: 'Modificar', refer: 'Pedir revisión',
};
const ACTOR_LABEL = {
  technician: 'Técnico', farmer: 'Productor', system: 'Sistema',
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
const MODEL_LABEL = {
  'GaussianProcessRegressor-Matern': 'proceso gaussiano Matérn',
  'GaussianProcessRegressor': 'proceso gaussiano',
};
const LEVEL_MARK = { alto: '▲', medio: '●', bajo: '○' };
const KPI_ICON = {
  area: 'M4 7h16v10H4zM4 11h16M9 7v10',
  mediciones: 'M4 5h16v14H4zM8 15l3-4 2 2 3-5',
  critico: 'M12 4 3 20h18zM12 10v4M12 17h.01',
  incierto: 'M9 9a3 3 0 1 1 4 2.8c-.7.3-1 .9-1 1.7M12 17h.01',
};
// Every view routes; the sidebar shows the ones with a screen of their own.
// `perfil` answers "who is this centre"; `configuracion` answers "with what
// assumptions does it calculate". Both routable; only the second is in the menu.
const NAV_VIEWS = [
  'resumen', 'lotes', 'mediciones', 'mapa', 'alertas',
  'recomendaciones', 'historial', 'reportes', 'configuracion',
  'perfil', 'lote', 'productores',
];
const MENU_VIEWS = [
  'resumen', 'lotes', 'mediciones', 'mapa', 'alertas',
  'recomendaciones', 'historial', 'reportes', 'configuracion',
];
const MENU_LABEL = {
  resumen: 'Resumen', lotes: 'Lotes', mediciones: 'Mediciones', mapa: 'Mapas',
  alertas: 'Alertas', recomendaciones: 'Recomendaciones', historial: 'Historial',
  reportes: 'Reportes', configuracion: 'Configuración',
};
// Inline so the shell needs no request; the contract forbids external hosts.
const MENU_ICON = {
  resumen: 'M3 10.5 12 4l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  lotes: 'M4 5h16v4H4zM4 11h16v3H4zM4 16h16v3H4z',
  mediciones: 'M4 4h16v16H4zM8 8h8M8 12h8M8 16h4',
  mapa: 'm9 4 6 2 5-2v14l-5 2-6-2-5 2V6zM9 4v14M15 6v14',
  alertas: 'M12 3a5 5 0 0 0-5 5v4l-2 3h14l-2-3V8a5 5 0 0 0-5-5zM10 19a2 2 0 0 0 4 0',
  recomendaciones: 'M12 3v3M5 7l2 2M19 7l-2 2M6 14a6 6 0 1 1 12 0c0 3-2 4-2 6H8c0-2-2-3-2-6z',
  historial: 'M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4',
  reportes: 'M6 3h8l4 4v14H6zM14 3v4h4M9 13h6M9 17h6',
  configuracion: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM4 12h2M18 12h2M12 4v2M12 18v2M6.5 6.5 8 8M16 16l1.5 1.5M17.5 6.5 16 8M8 16l-1.5 1.5',
};

function navFromHash() {
  const target = decodeURIComponent(location.hash.slice(1));
  return NAV_VIEWS.includes(target) ? target : 'resumen';
}

// Every view now has a screen; an unknown target still lands on the summary.
function reachable(view) {
  return NAV_VIEWS.includes(view) ? view : 'resumen';
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
        circle.addEventListener('click', () => openProducer(circle.dataset.prod));
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
      console.warn('[mapa] no se pudo dibujar:', error.message);
      status.textContent = 'No se pudo dibujar el mapa.';
    }
  }
}

const DRAG_SLOP_PX = 5;

// The offset is only meaningful against the zoom the current bounds fitted to.
// A lot fits at 18 and the tiles stop at 19, so its real range is a single step
// in; the network map, fitted much further out, has plenty of room.
function zoomBounds() {
  const base = state.projector?.baseZoom;
  if (!Number.isFinite(base)) return { min: 0, max: 0 };
  return { min: MIN_ZOOM - base, max: MAX_ZOOM - base };
}

function resetMapView() {
  state.map = { zoomOffset: 0, panX: 0, panY: 0 };
  state.probe = null;
  drawMap();
  showProbe();
  syncZoomButtons();
}

function zoomBy(step) {
  const { min, max } = zoomBounds();
  const next = Math.max(min, Math.min(max, state.map.zoomOffset + step));
  if (next === state.map.zoomOffset) return;
  state.map = { ...state.map, zoomOffset: next };
  drawMap();
  syncZoomButtons();
}

// A control that cannot do anything says so, instead of swallowing the tap.
function syncZoomButtons() {
  const { min, max } = zoomBounds();
  const inButton = document.querySelector('[data-map="in"]');
  const outButton = document.querySelector('[data-map="out"]');
  if (inButton) inButton.disabled = state.map.zoomOffset >= max;
  if (outButton) outButton.disabled = state.map.zoomOffset <= min;
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

  // The zoom and home controls sit inside the stage. Starting a drag on them
  // captures the pointer and the button never receives its click, which made
  // them look dead to a real mouse while synthetic clicks still worked.
  // Producer dots are clickable too: capturing the pointer for a drag would
  // swallow their click exactly as it swallowed the buttons'.
  const onControl = (target) => Boolean(
    target?.closest?.('.map-ctl, .map-probe, .colorbar, .map-panel')
    || target?.classList?.contains('pdot'),
  );

  stage.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || onControl(event.target)) return;
    dragging = true;
    moved = 0;
    startX = event.clientX;
    startY = event.clientY;
    // Capture is a convenience, not a requirement: losing it must not abort
    // the drag, and some synthetic pointers have no capturable id at all.
    try { stage.setPointerCapture(event.pointerId); } catch { /* drag still works */ }
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

  stage.addEventListener('dblclick', (event) => {
    if (onControl(event.target)) return;
    zoomBy(1);
  });
}

function paintNutrientToggle() {
  const slot = document.getElementById('colorbar-slot');
  if (slot) {
    slot.innerHTML = colorbar();
    const label = document.getElementById('map-nutrient');
    if (label) label.textContent = state.nutrient;
    const average = document.getElementById('map-avg');
    if (average && state.view) average.textContent = `${fmt(gridAverage(state.view.grid, state.nutrient))}%`;
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
  syncZoomButtons();
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
    ${propuesta.requiere_decision && !state.decision ? `<p class="note">Requiere la decisión de un técnico antes de aplicarse.</p>
      <div class="decision-actions">
        <button class="btn" type="button" data-decide="accept" ${apiBase ? '' : 'disabled'}>Aceptar</button>
        <button class="btn ghost" type="button" data-decide="refer" ${apiBase ? '' : 'disabled'}>Pedir revisión</button>
        <button class="btn ghost" type="button" data-why="${propuesta.id}">¿Por qué?</button>
      </div>
      ${apiBase ? '' : '<p class="note">Sin conexión no se puede registrar una decisión.</p>'}` : ''}
    <div class="decision-msg" id="decision-msg" ${state.decisionMsg ? '' : 'hidden'}>${state.decisionMsg || ''}</div>
    ${state.decision?.acta_available ? actaPanel() : ''}
    <div class="why-body" id="why-body" hidden></div>
  </div>`;
}

function actaPanel() {
  const url = `${location.origin}${ACTA_PATH}`;
  const local = /^(localhost|127\.0\.0\.1)$/.test(location.hostname);
  return `<section class="acta-panel" aria-labelledby="acta-title">
    <div class="acta-copy">
      <p class="acta-kicker">Decisión registrada</p>
      <h3 id="acta-title">El acta está lista para campo</h3>
      <p>Escanee el QR o abra el PDF con el reparto de 13 bultos en las tres zonas.</p>
      <div class="acta-actions">
        <a class="btn" href="${url}" target="_blank" rel="noopener">Abrir acta PDF</a>
        <button class="btn ghost" type="button" data-copy-acta>Copiar enlace</button>
      </div>
      <label class="acta-url-label" for="acta-url">Enlace que codifica el QR</label>
      <input class="acta-url" id="acta-url" type="url" value="${url}" spellcheck="false">
      ${local ? '<p class="acta-local">En localhost el celular no puede abrir este enlace. Pegue aquí la URL de Vercel antes de escanear.</p>' : ''}
      <p class="acta-copy-status" aria-live="polite"></p>
    </div>
    <a class="acta-qr" href="${url}" target="_blank" rel="noopener" aria-label="Abrir el acta en PDF">
      ${qrSvg(url, { level: 'Q', title: 'QR del acta de fertilización' })}
      <span>Escanear para abrir</span>
    </a>
  </section>`;
}

function panelRiesgos() {
  const { riesgos, estacional, degradado } = state.view;
  if (riesgos.length === 0) return '<p class="note">Sin riesgos activos para este lote.</p>';

  // Opening from Alertas expands the risk you clicked, not always the first.
  const target = riesgos.findIndex((r) => r.tipo === state.riesgoAbrir);
  const openIndex = target >= 0 ? target : 0;

  const cards = riesgos.map((r, index) => `<article class="risk sev-${r.severidad} ${index === openIndex ? 'open' : ''}">
      <button class="risk-head" type="button" aria-expanded="${index === openIndex}">
        <span class="mark">${SEVERITY_MARK[r.severidad] || '●'}</span>
        <span class="sev-label">${SEVERITY_WORD[r.severidad] || r.severidad}</span>
        <span class="risk-title">${RISK_TITLE[r.tipo] || r.tipo}</span>
      </button>
      <div class="risk-body">
        <p>Ventana ${r.ventana?.start} a ${r.ventana?.end} · confianza ${Math.round((r.confianza ?? 0) * 100)}%</p>
        ${r.accion ? `<ul><li>${translateOne(r.accion)}</li></ul>` : ''}
        ${(r.confianza ?? 1) < 0.5 ? '<p class="low-conf">Esto todavía puede cambiar.</p>' : ''}
        <button class="why" type="button" data-risk="${r.tipo}">¿Por qué?</button>
        <div class="why-body" id="why-${r.tipo}" hidden>
          <p><b>Probabilidad estimada:</b> ${Math.round((r.score ?? 0) * 100)} %</p>
          <p><b>Datos:</b> ${riskInputs(r.entradas)}</p>
          <p><b>Fuentes:</b> ${riskSources(r.fuentes)}</p>
          ${translateList(r.limitaciones).length
    ? `<p><b>Límites:</b></p><ul>${translateList(r.limitaciones).map((l) => `<li>${l}</li>`).join('')}</ul>`
    : ''}
        </div>
      </div>
    </article>`).join('');

  return `<div class="scroll-y">${cards}
    ${estacional?.enso ? `<p class="note"><b>ENSO:</b> ${ensoLabel(estacional.enso.phase ?? estacional.enso.status)}</p>` : ''}
    ${degradado ? '<p class="note warn-text">Alguna fuente no respondió: el clima se muestra como no actual.</p>' : ''}
  </div>`;
}

const ASK_SUGGESTIONS = [
  {
    title: 'Prioridad de hoy',
    detail: 'Qué revisar primero',
    question: '¿Qué debo priorizar hoy en este lote?',
  },
  {
    title: 'Siguiente medición',
    detail: 'Dónde reduce más la incertidumbre',
    question: '¿Dónde debo medir para reducir la incertidumbre?',
  },
  {
    title: 'Plan de bultos',
    detail: 'Cuánto llevar a cada zona',
    question: '¿Qué formulación sugieren y cómo reparto los bultos?',
  },
  {
    title: 'Confianza del mapa',
    detail: 'Qué significa el área rayada',
    question: '¿Por qué hay incertidumbre y qué debo comprobar?',
  },
];

function panelAsistente() {
  const suggestions = ASK_SUGGESTIONS;
  const welcome = apiBase
    ? 'Estoy listo para cruzar las mediciones, las tres zonas, el clima y la propuesta. Pregunte como hablaría con el técnico del acopio.'
    : 'Estoy en modo local. Responderé únicamente con la evidencia guardada en este paquete.';
  const status = apiBase ? 'Conectado al agente' : 'Modo paquete local';
  const statusClass = apiBase ? 'online' : 'offline';
  const { sampling, zonas, riesgos } = state.view;
  const totalBags = (state.view.propuesta?.zonas || []).reduce(
    (total, zone) => total + zone.formulaciones.reduce((sum, item) => sum + item.bags, 0),
    0,
  );

  return `<div class="assistant-workspace">
    <header class="assistant-head">
      <div class="assistant-identity">
        <span class="assistant-mark" aria-hidden="true">IA</span>
        <div>
          <p class="assistant-eyebrow">Copiloto de campo</p>
          <h3>Pregunte antes de decidir</h3>
          <p>Respuestas aterrizadas al lote El Rosal, no consejos genéricos.</p>
        </div>
      </div>
      <span class="assistant-status ${statusClass}"><i></i>${status}</span>
    </header>

    <div class="assistant-evidence" aria-label="Evidencia disponible para responder">
      <span><b>${sampling.valid}</b> mediciones válidas</span>
      <span><b>${zonas.length}</b> zonas calculadas</span>
      <span><b>${riesgos.length}</b> riesgos activos</span>
      <span><b>${totalBags}</b> bultos propuestos</span>
    </div>

    <div class="chat" id="chat" aria-live="polite">
      <div class="bubble bot welcome">
        <span class="bubble-author">IOmido IA</span>
        <p>${welcome}</p>
        <small>Basado en el paquete vigente del lote</small>
      </div>
    </div>

    <div class="suggest" aria-label="Preguntas sugeridas">
      ${suggestions.map((suggestion, index) => `<button class="as-suggest" type="button"
          data-question="${suggestion.question}">
        <span class="suggest-index">0${index + 1}</span>
        <span><b>${suggestion.title}</b><small>${suggestion.detail}</small></span>
        <span class="suggest-arrow" aria-hidden="true">→</span>
      </button>`).join('')}
    </div>

    <form class="ask" id="ask">
      <label for="ask-input">Pregunta sobre este lote</label>
      <div class="ask-composer">
        <input id="ask-input" type="text"
          placeholder="Ej. ¿Qué debería validar antes de aplicar?"
          autocomplete="off" aria-describedby="ask-grounding">
        <button class="btn icon" id="mic" type="button"
          title="${canListen ? 'Preguntar por voz' : 'Voz no disponible aquí'}"
          aria-label="${canListen ? 'Preguntar por voz' : 'Voz no disponible'}"
          ${canListen ? '' : 'disabled'}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3ZM6 11v1a6 6 0 0 0 12 0v-1M12 18v3M9 21h6"/></svg>
        </button>
        <button class="btn ask-submit" type="submit">Consultar <span aria-hidden="true">→</span></button>
      </div>
    </form>
    <p class="assistant-grounding" id="ask-grounding">
      <span></span> No inventa cifras: responde con la evidencia disponible y declara cuando no sabe.
      ${canSpeak ? ' Puede leer la respuesta en voz alta.' : ''}
    </p>
  </div>`;
}

function panelMediciones() {
  const { mediciones, sampling } = state.view;
  const pct = (value) => `${fmt(value, value % 1 === 0 ? 0 : 1)} %`;

  const rows = mediciones.map((m, index) => `<tr class="${m.valido ? '' : 'rejected'}">
      <td>${index + 1}</td>
      <td class="num">${pct(m.N)}</td>
      <td class="num">${pct(m.P)}</td>
      <td class="num">${pct(m.K)}</td>
      <td>${m.valido ? (m.sospechoso ? 'revisar' : 'usada') : 'fuera'}${m.motivo
    ? `<button class="why-dot" type="button" data-motivo="${translateOne(m.motivo)}"
        aria-label="Por qué: ${translateOne(m.motivo)}">?</button>` : ''}</td>
    </tr>${m.motivo ? `<tr class="motivo-row" hidden><td colspan="5" class="note">${translateOne(m.motivo)}</td></tr>` : ''}`).join('');

  return `<div class="scroll-y">
      <table class="readings">
        <thead><tr><th>#</th><th class="num">N</th><th class="num">P</th><th class="num">K</th><th>Estado</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="note">${sampling.valid} de ${sampling.total} mediciones alimentan el modelo. Porcentaje de masa del suelo, lectura cruda del sensor.</p>`;
}

function bubble(role, text, source = '') {
  const chat = document.getElementById('chat');
  const node = document.createElement('div');
  node.className = `bubble ${role}`;
  if (role === 'bot') {
    const author = document.createElement('span');
    author.className = 'bubble-author';
    author.textContent = 'IOmido IA';
    node.appendChild(author);
  }
  const content = document.createElement('p');
  content.textContent = text;
  node.appendChild(content);
  if (source) {
    const citation = document.createElement('small');
    citation.textContent = source;
    node.appendChild(citation);
  }
  chat.appendChild(node);
  chat.scrollTop = chat.scrollHeight;
  return { node, content };
}

async function answer(question) {
  bubble('me', question);
  const pending = bubble('bot', 'Consultando la evidencia del lote…');
  pending.node.classList.add('thinking');
  const reply = await ask(question, state.view);
  pending.node.classList.remove('thinking');
  pending.content.textContent = reply.texto;
  if (reply.fuente) {
    const citation = document.createElement('small');
    citation.textContent = `Fuentes: ${reply.fuente}`;
    pending.node.appendChild(citation);
  }
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
    const lotGrid = document.querySelector('.lote-grid');
    lotGrid?.classList.add('detail-focus');
    lotGrid?.classList.toggle('assistant-focus', name === 'asistente');
    // The map changes width without a re-render; repaint once its CSS transition settles.
    if (lotGrid) setTimeout(() => scheduleDraw(), 240);
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
      const copyActa = body.querySelector('[data-copy-acta]');
      const actaInput = body.querySelector('#acta-url');
      if (actaInput) {
        actaInput.addEventListener('change', () => {
          const qr = body.querySelector('.acta-qr');
          const status = body.querySelector('.acta-copy-status');
          try {
            const nextUrl = new URL(actaInput.value);
            if (!/^https?:$/.test(nextUrl.protocol)) throw new Error('protocol');
            qr.href = nextUrl.href;
            qr.innerHTML = `${qrSvg(nextUrl.href, { level: 'Q', title: 'QR del acta de fertilización' })}<span>Escanear para abrir</span>`;
            actaInput.value = nextUrl.href;
            status.textContent = 'QR actualizado.';
          } catch {
            status.textContent = 'Escriba una URL completa que empiece por http:// o https://.';
          }
        });
      }
      if (copyActa) {
        copyActa.addEventListener('click', async () => {
          const input = body.querySelector('#acta-url');
          const status = body.querySelector('.acta-copy-status');
          try {
            await navigator.clipboard.writeText(input.value);
            status.textContent = 'Enlace copiado.';
          } catch {
            input.select();
            status.textContent = 'Enlace seleccionado: cópielo manualmente.';
          }
        });
      }
      return;
    }

    if (name === 'mediciones') {
      // Hover-only would strand touch users, so the mark toggles a real row.
      for (const dot of body.querySelectorAll('.why-dot')) {
        dot.addEventListener('click', () => {
          const row = dot.closest('tr')?.nextElementSibling;
          if (row?.classList.contains('motivo-row')) {
            row.hidden = !row.hidden;
            dot.setAttribute('aria-expanded', String(!row.hidden));
          }
        });
      }
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
      chip.addEventListener('click', () => answer(chip.dataset.question));
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

// With a live dashboard this percentage is measured coverage, not crop health:
// it says how many plots have readings, so the wording talks about coverage.
function healthHeadline(pct) {
  if (pct >= 80) return 'Casi toda la red está medida.';
  if (pct >= 60) return 'La red está medida en su mayoría.';
  if (pct > 0) return 'Falta medir buena parte de la red.';
  return 'La red todavía no tiene mediciones.';
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
      acta_available: action === 'accept',
    };
    // The identifier belongs in the audit trail, not in the sentence a person
    // reads; it stays reachable on hover.
    const at = new Date(decision.created_at || Date.now())
      .toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })
      .replace(/\.$/, '');
    state.decisionMsg = `<span title="${decision.id}">Decisión registrada a las ${at}.</span>`;
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
    console.warn('[decision] no se pudo registrar:', error.message);
    state.decisionMsg = /respondió 4\d\d/.test(error.message)
      ? 'Este backend no aceptó la decisión. Avise al responsable del sistema.'
      : 'No se pudo registrar la decisión. Revise la conexión y vuelva a intentarlo.';
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
    // The URL and status go to the console; the screen says what it is showing.
    console.warn('[propuesta] explicación remota no disponible:', error.message);
    box.innerHTML = explanation
      ? `${renderWhy(explanation)}<p class="note">Explicación del paquete descargado.</p>`
      : '<p class="note">No se pudo consultar la explicación ahora mismo.</p>';
  }
}

function renderWhy(why) {
  const steps = (why.steps || [])
    .map((s) => `<li><b>${translateOne(s.step)}</b> ${translateOne(s.detail || '')}</li>`).join('');
  const unknowns = (why.unknowns || []).map((u) => `<li>${translateOne(u)}</li>`).join('');
  return `${why.summary ? `<p>${translateOne(why.summary)}</p>` : ''}
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
    { label: 'Área del lote', value: `${fmt(view.plot.area_ha, 2)} ha`, hint: place(view.plot.municipality || view.plot.municipio), tone: 'green', icon: KPI_ICON.area,
      ayuda: 'Área que encierra el contorno declarado del lote.' },
    { label: 'Mediciones', value: `${view.sampling.valid}/${view.sampling.total}`, hint: 'alimentan el modelo', tone: 'blue', icon: KPI_ICON.mediciones,
      ayuda: `De ${view.sampling.total} lecturas recibidas, ${view.sampling.valid} caen dentro del lote y alimentan el modelo.` },
    { label: 'En nivel crítico', value: `${fmt(view.criticalSharePct)}%`, hint: `${fmt(view.criticalAreaHa, 2)} ha del lote`, warn: view.criticalSharePct > 40, tone: 'red', icon: KPI_ICON.critico,
      ayuda: 'Parte del lote cuyas zonas tienen menos de la mitad del nutriente que pide el cultivo.' },
    { label: 'Sin certeza', value: `${view.coverage.uncertainPct}%`, hint: 'del lote, según el modelo', tone: 'grey', icon: KPI_ICON.incierto,
      ayuda: 'Celdas donde la incertidumbre del modelo pasa su umbral. En el mapa van rayadas: ahí el modelo no sabe.' },
  ].map((c) => `<div class="kpi ${c.warn ? 'warn-kpi' : ''}" title="${c.ayuda}">
      <span class="kpi-icon tone-${c.tone}" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="${c.icon}"/></svg></span>
      <div class="kpi-text">
        <div class="label">${c.label}</div><div class="value">${c.value}</div><div class="hint">${c.hint}</div>
      </div>
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

  const rail = cola.map((c) => `<article class="prio-card rv-${c.sev}">
      <span class="prio-icon" aria-hidden="true">${SEVERITY_MARK[c.sev] || '●'}</span>
      <div class="prio-body">
        <b>${c.titulo}</b>
        <p>${c.detalle}</p>
        <button class="btn ghost rail-go" type="button" data-go="lote" data-tab-go="${c.tab}">${c.meta} →</button>
      </div>
    </article>`).join('');

  return `<div class="rwrap rwrap-mvp">
    <section class="hero">
      <div class="hero-title">${titular}</div>
      <div class="hero-sub">${view.plot.name} · ${view.cultivo?.crop || ''} ${view.cultivo?.variety || ''} · medido ${new Date(view.generado).toLocaleDateString('es-CO')}</div>
    </section>

    <section class="card facts-card">
      <div class="kpi-grid">${kpis}</div>
    </section>

    <div class="mvp-main">
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
          <div class="map-panel">
            <b><span id="map-nutrient">${state.nutrient}</span> en el lote</b>
            <span class="note">% de masa · celda ${view.grid.celda_m} m · ✛ mida aquí</span>
            <div class="map-avg"><span class="map-avg-mark" aria-hidden="true">🌿</span>
              <span><b id="map-avg">${fmt(gridAverage(view.grid, state.nutrient))}%</b>
              <small>Promedio estimado</small></span>
            </div>
          </div>
          <div id="colorbar-slot"></div>
          <div class="map-ctl">
            <button type="button" data-map="in" aria-label="Acercar">+</button>
            <button type="button" data-map="out" aria-label="Alejar">−</button>
            <button type="button" data-map="reset" title="Volver a las coordenadas de origen" aria-label="Volver a las coordenadas de origen">✳</button>
          </div>
          <div class="map-probe" id="map-probe" hidden></div>
          <div class="map-status" id="map-status" hidden></div>
          <div class="attribution">${ATTRIBUTION}</div>
        </div>
      </section>
    </div>

    <section class="card prio-card-wrap">
      <h2>Prioridad hoy</h2>
      <div class="prio-grid">${rail || '<p class="note">Sin acciones pendientes.</p>'}</div>
    </section>

  </div>`;
}

// Average over the cells inside the plot only: the grid is a rectangle, the lot
// is not, so counting masked-out cells would drag the number toward nothing.
function gridAverage(grid, nutrient) {
  let sum = 0;
  let count = 0;
  const values = grid[nutrient] || [];
  for (let i = 0; i < values.length; i += 1) {
    if (!grid.mask[i] || !Number.isFinite(values[i])) continue;
    sum += values[i];
    count += 1;
  }
  return count ? sum / count : 0;
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
            <button type="button" data-map="reset" title="Volver a las coordenadas de origen" aria-label="Volver a las coordenadas de origen">✳</button>
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
        <h2>Cobertura de medición</h2>
        <div class="health-pct">${net.salud.pct}%</div>
        ${riskBar(net.salud.pct)}
        <p class="note">${net.salud.lotes_ok} de ${k.lotes} lotes sin alertas críticas.
          ${net.salud.delta_semana
            ? `<span class="${net.salud.delta_semana < 0 ? 'delta-bad' : 'delta-good'}">${net.salud.delta_semana > 0 ? '+' : ''}${net.salud.delta_semana} pts vs. la semana pasada</span>`
            : ''}</p>
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
            <button type="button" data-map="reset" title="Volver a las coordenadas de origen" aria-label="Volver a las coordenadas de origen">✳</button>
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

  // Reached from a dot on the map, and absent from the sidebar, so it needs its
  // own way back or it is a dead end.
  return `<div class="rwrap">
    <div class="bcrumb"><button class="btn ghost" type="button" data-nav="mapa">← Volver al mapa</button></div>
    <div class="prod-grid">${cards}</div>
    <div class="prod-detail-slot">${detail}</div>
  </div>`;
}

function viewLote() {
  const view = state.view;
  const worstZone = view.zonas[0];

  return `<div class="bcrumb"><button class="btn ghost" type="button" data-nav="${reachable('productores')}">← Red del acopio</button></div>
    <div class="grid lote-grid">
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
            <button type="button" data-map="reset" title="Volver a las coordenadas de origen" aria-label="Volver a las coordenadas de origen">✳</button>
          </div>
          <div class="map-probe" id="map-probe" hidden></div>
          <div class="map-status" id="map-status" hidden></div>
          <div class="attribution">${ATTRIBUTION}</div>
        </div>
      </section>

      <div class="col">
        <div class="kpis">
          <div class="kpi"><div class="label">Zona más pobre</div><div class="value warn">${NIVEL_LABEL[worstZone.peor]}</div><div class="hint">${fmt(worstZone.area_ha, 2)} ha · zona ${worstZone.id.replace('zone-', '')}</div></div>
          <div class="kpi"><div class="label">Le falta</div><div class="value">${fmt(view.criticalSharePct)}%</div><div class="hint">del lote en nivel crítico</div></div>
        </div>

        ${view.descartados.length ? `<div class="amber">
          <b>Una medición quedó fuera</b>
          <p>${translateOne(view.descartados[0].motivo)}</p>
          <p>Se conserva en el historial, pero no alimenta el modelo.</p>
          <div class="amber-actions"><button class="btn ghost" type="button" data-open-measurements>Ver mediciones →</button></div>
        </div>` : ''}

        <section class="card tabs-card">
          <div class="tabs" role="tablist">
            <button class="tab" data-tab="propuesta" role="tab" aria-selected="true">Propuesta</button>
            <button class="tab" data-tab="riesgos" role="tab" aria-selected="false">Lo que viene${view.riesgos.length ? ` <span class="badge-n">${view.riesgos.length}</span>` : ''}</button>
            <button class="tab" data-tab="mediciones" role="tab" aria-selected="false">Mediciones</button>
            <button class="tab ai-tab" data-tab="asistente" role="tab" aria-selected="false"><span>IA</span> Preguntar</button>
          </div>
          <div class="tab-body" id="tab-body"></div>
        </section>
      </div>
    </div>`;
}

// The history screen is the only one that needs its own round-trip.
async function loadHistorial() {
  const id = state.view.propuesta?.id;
  if (!apiBase || !id) {
    state.historial = [];
    state.historialMsg = apiBase
      ? 'Este lote no tiene propuesta, así que no hay decisiones que mostrar.'
      : 'Sin conexión no se puede leer el historial: vive en el backend, no en el paquete.';
    render();
    return;
  }
  try {
    const { history } = await getDecisionHistory(id);
    state.historial = history?.decisions || [];
    state.historialMsg = state.historial.length ? '' : 'Sin decisiones registradas todavía.';
  } catch (error) {
    state.historial = [];
    // The URL and status belong in the console, not on screen. A 404 here means
    // the deployed backend does not expose the history route yet.
    console.warn('[historial] no disponible:', error.message);
    state.historialMsg = /respondió 404/.test(error.message)
      ? 'Este backend todavía no expone el historial de decisiones.'
      : 'No se pudo leer el historial ahora mismo. Vuelva a intentarlo.';
  }
  render();
}

function viewFor(nav) {
  const screens = {
    resumen: viewResumen,
    lotes: viewLotes,
    mediciones: viewMediciones,
    mapa: viewMapa,
    alertas: viewAlertas,
    recomendaciones: viewRecomendaciones,
    historial: viewHistorial,
    reportes: viewReportes,
    configuracion: viewConfiguracion,
    perfil: viewPerfil,
    productores: viewProductores,
    lote: viewLote,
  };
  return (screens[nav] || viewResumen)();
}

function panelCard(title, body, note) {
  return `<div class="rwrap"><section class="card wide-card">
    <h2>${title}</h2>${body}
    ${note ? `<p class="note">${note}</p>` : ''}
  </section></div>`;
}

function viewLotes() {
  const net = state.network;
  const view = state.view;
  const lotes = net.real?.lotes || [];
  const rows = lotes.length
    ? lotes.map((l) => `<tr>
        <td><b>${l.name}</b></td><td>${place(l.municipality)}</td>
        <td class="num">${l.reading_count}</td>
        <td>${l.id === view.plot.id ? `${fmt(view.plot.area_ha, 2)} ha` : '—'}</td>
        <td><button class="btn ghost" type="button" data-nav="lote">Abrir</button></td>
      </tr>`).join('')
    : `<tr><td colspan="5" class="note">Sin backend no hay listado de lotes: el paquete local trae solo
        <b>${view.plot.name}</b>.</td></tr>`;

  return panelCard('Lotes del centro', `<div class="table-wrap"><table class="data">
      <thead><tr><th>Lote</th><th>Municipio</th><th class="num">Mediciones</th><th>Área</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>`);
}

function viewMediciones() {
  const view = state.view;
  const all = [...view.puntos.map((p) => ({ ...p, usada: true })),
    ...view.descartados.map((p) => ({ ...p, usada: false }))];
  const rows = all.map((p, i) => `<tr class="${p.usada ? '' : 'row-out'}">
      <td class="num">${String(i + 1).padStart(2, '0')}</td>
      <td class="num">${p.N} %</td><td class="num">${p.P} %</td><td class="num">${p.K} %</td>
      <td>${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}</td>
      <td>${p.usada ? 'usada' : `fuera <span class="note">${translateOne(p.motivo) || 'geometría'}</span>`}</td>
    </tr>`).join('');

  return panelCard(`Mediciones · ${view.sampling.valid} de ${view.sampling.total} alimentan el modelo`,
    `<div class="table-wrap"><table class="data">
      <thead><tr><th class="num">#</th><th class="num">N</th><th class="num">P</th><th class="num">K</th>
        <th>Coordenadas</th><th>Estado</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`,
    'Los valores son porcentaje de masa del suelo, en convención elemental.');
}

function viewAlertas() {
  const view = state.view;
  if (!view.riesgos.length) return panelCard('Alertas', '<p class="note">Sin riesgos activos para este lote.</p>');
  const cards = view.riesgos.map((r) => `<article class="alert-row sev-${r.severidad}">
      <span class="alert-mark">${SEVERITY_MARK[r.severidad] || '●'}</span>
      <div>
        <b>${RISK_TITLE[r.tipo] || r.tipo} · severidad ${SEVERITY_WORD[r.severidad] || r.severidad}</b>
        <p class="note">Ventana del ${r.ventana?.start} al ${r.ventana?.end}
          · confianza ${Math.round((r.confianza ?? 0) * 100)} %
          · probabilidad ${Math.round((r.score ?? 0) * 100)} %</p>
        ${r.accion ? `<p class="note">${translateOne(r.accion)}</p>` : ''}
        <p class="note">Fuentes: ${r.fuentes.map((f) => `${f.name}${f.stale || f.failed ? ' (no actual)' : ''}`).join(' · ')}</p>
      </div>
      <button class="btn ghost" type="button" data-nav="lote" data-tab-go="riesgos" data-risk-go="${r.tipo}">Ver detalles →</button>
    </article>`).join('');
  return panelCard('Alertas climáticas', cards);
}

function viewRecomendaciones() {
  const view = state.view;
  if (!view.propuesta?.zonas.length) return panelCard('Recomendaciones', '<p class="note">Todavía no hay propuesta.</p>');
  const zones = view.propuesta.zonas.map((z) => `<article class="zone-prop">
      <header><b>Zona ${z.id.replace('zone-', '')}</b> · ${fmt(z.area_ha, 2)} ha · ${NIVEL_LABEL[z.peor]}</header>
      ${z.formulaciones.map((f) => `<div class="form-row">
        <span class="grade">${f.label}</span>
        <span class="form-qty"><b>${f.bags}</b> ${f.bags === 1 ? 'bulto' : 'bultos'} de ${f.bag_weight.value} ${f.bag_weight.unit}</span>
      </div>`).join('')}
    </article>`).join('');
  return panelCard('Recomendaciones por zona', `<div class="proposal">${zones}
    <button class="btn" type="button" data-nav="lote" data-tab-go="propuesta">Abrir la propuesta y decidir →</button></div>`,
  'Un grado <b>30-30-40</b> es 30 % N, 30 % P y 40 % K de la masa del bulto.');
}

function viewHistorial() {
  const when = (iso) => new Date(iso).toLocaleString('es-CO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });

  const rows = (state.historial || []).map((d) => `<tr>
      <td>${when(d.created_at)}</td>
      <td>${ACTION_LABEL[d.action] || d.action}</td>
      <td>${DECISION_LABEL[d.resulting_status] || d.resulting_status}</td>
      <td${d.actor_id ? ` title="${d.actor_id}"` : ''}>${ACTOR_LABEL[d.actor_type] || d.actor_type || '—'}</td>
    </tr>`).join('');
  const body = rows
    ? `<div class="table-wrap"><table class="data"><thead><tr>
        <th>Cuándo</th><th>Acción</th><th>Estado resultante</th><th>Quién</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`
    : `<p class="note">${state.historialMsg || 'Sin decisiones registradas todavía.'}</p>`;
  return panelCard('Historial de decisiones', body);
}

function viewReportes() {
  const view = state.view;
  const m = view.modelo;
  const perNutrient = m?.metrics?.per_nutrient;
  const meanRmse = m?.metrics?.mean_rmse;

  // The backend reports GP against an IDW baseline per nutrient. Showing the
  // raw object helps nobody; the comparison is the point.
  const compare = perNutrient
    ? `<div class="table-wrap"><table class="data">
        <thead><tr><th>Nutriente</th><th class="num">Error medio · modelo</th><th class="num">Error medio · referencia</th>
          <th class="num">Cobertura del intervalo 95 %</th></tr></thead>
        <tbody>${NUTRIENTS.map((n) => {
    const row = perNutrient[n];
    if (!row) return '';
    return `<tr><td><b>${n}</b></td>
            <td class="num">${fmt(row.gp?.mae, 2)} pp</td>
            <td class="num">${fmt(row.idw?.mae, 2)} pp</td>
            <td class="num">${Math.round((row.gp?.interval_95_coverage ?? 0) * 100)} %</td></tr>`;
  }).join('')}</tbody></table></div>`
    : '';

  const verdict = meanRmse
    ? `<p class="note">La tabla mide el <b>error medio</b>. Castigando más los fallos grandes
        (error cuadrático medio) el orden se invierte: <b>${fmt(meanRmse.gp, 2)} pp</b> el modelo
        espacial contra <b>${fmt(meanRmse.idw, 2)} pp</b> la referencia.
        ${m.metrics.gp_better_than_idw
    ? 'El modelo espacial mejora la referencia en este conjunto.'
    : 'Por eso, con estos datos, <b>no se afirma</b> que el modelo espacial supere a la referencia.'}</p>`
    : '';

  const limits = translateList(m?.limitations);
  // The package repeats the model's limitations inside its warnings; show each once.
  const warnings = translateList(view.avisos).filter((a) => !limits.includes(a));

  return panelCard('Cómo se calculó', `
    <p class="note">Modelo <b>${MODEL_LABEL[m?.model_name] || m?.model_name || 'espacial'}</b>
      ${m?.model_version || ''} · <b>${m?.observation_count ?? view.sampling.valid}</b> mediciones dentro del lote
      ${m?.inference_ms ? ` · ${fmt(m.inference_ms, 0)} ms de cálculo` : ''}</p>
    ${compare}
    ${verdict}
    ${limits.length ? `<h2>Hasta dónde llega</h2><ul class="balance">${limits.map((l) => `<li>${l}</li>`).join('')}</ul>` : ''}
    ${warnings.length ? `<h2>Avisos</h2><ul class="balance">${warnings.map((a) => `<li>${a}</li>`).join('')}</ul>` : ''}
    <p class="note">«pp» son puntos porcentuales de masa. Una cobertura por debajo del 95 %
      significa que el intervalo del modelo se queda corto más veces de lo previsto.</p>`);
}

// The backend writes its limitations and warnings in English. Each is mapped
// word for word; anything unmapped is shown as it came rather than guessed at.
const BACKEND_ES = new Map([
  ['Sensor percentages have not been calibrated against laboratory samples.',
    'Los porcentajes del sensor no se han calibrado contra muestras de laboratorio.'],
  ['Spatial predictions support sampling and review; they are not laboratory measurements.',
    'Las predicciones espaciales sirven para muestrear y revisar; no son mediciones de laboratorio.'],
  ['Small dataset (18 in-plot observations); metrics have high variance.',
    'Conjunto pequeño (18 mediciones dentro del lote): las métricas varían mucho.'],
  ['The crop profile is demo_unvalidated; no candidate plan is an applied prescription.',
    'El perfil de cultivo es de demostración y no está validado: ningún plan es una prescripción aplicada.'],
  ['GP is not claimed to outperform IDW for this input set.',
    'No se afirma que el modelo espacial supere al método de referencia con estos datos.'],
  ['measurement is outside the declared plot boundary',
    'la medición cae fuera del contorno declarado del lote'],
  ['reading is outside the declared plot boundary',
    'la lectura cae fuera del contorno declarado del lote'],

  // Acciones sugeridas por el motor de riesgos
  ['Review the local station and protect exposed areas before the forecast minimum.',
    'Revise la estación local y proteja las zonas expuestas antes de la mínima prevista.'],
  ['Prioritize soil moisture verification and postpone nutrient application if water is unavailable.',
    'Priorice comprobar la humedad del suelo y aplace la fertilización si no hay agua.'],
  ['Inspect lower leaves and ask the technician to validate preventive action.',
    'Revise las hojas bajas y pida al técnico que valide una acción preventiva.'],

  // Límites que el motor declara en cada riesgo
  ['Rules are decision support and have not been locally validated as a supervised classifier.',
    'Las reglas son apoyo a la decisión; no se han validado localmente como clasificador supervisado.'],
  ['No synthetic labels were used; probabilities are transparent rule scores.',
    'No se usaron etiquetas sintéticas: las probabilidades son puntajes de reglas a la vista.'],
  ['Coarse climate products can smooth high-altitude extremes.',
    'Los productos climáticos de baja resolución suavizan los extremos de alta montaña.'],
  ['Weather suitability is not evidence that the pathogen is present.',
    'Que el clima sea favorable no prueba que el patógeno esté presente.'],

  // Explicación de la propuesta: resumen, pasos y lo que queda sin saber
  ["Candidate integer formulation plans were derived from spatial estimates, explicit demo agronomy assumptions and the center's active catalog.",
    'Los planes candidatos salen de las estimaciones espaciales, de supuestos agronómicos de demostración declarados y del catálogo activo del centro.'],
  ['spatial inference', 'inferencia espacial'],
  ['agronomic accounting', 'balance agronómico'],
  ['integer optimization', 'optimización entera'],
  ['climate context', 'contexto climático'],
  ['Three Matern Gaussian Processes produced means and uncertainty.',
    'Tres procesos gaussianos Matérn produjeron las medias y la incertidumbre.'],
  ['Soil percentage was converted to sampled-layer mass and availability; it was not subtracted from bag percentage.',
    'El porcentaje del suelo se convirtió a masa de la capa muestreada y a disponibilidad; no se restó del porcentaje del bulto.'],
  ['Each zone used exact bounded integer search with shortfall, excess, bag count and formulation count in that order.',
    'Cada zona usó búsqueda entera exacta y acotada, priorizando faltante, exceso, número de bultos y número de formulaciones, en ese orden.'],
  ['Risk rules used the fused sources and can block application timing.',
    'Las reglas de riesgo usaron las fuentes combinadas y pueden bloquear el momento de aplicación.'],
  ['The sensor has not been calibrated against laboratory samples.',
    'El sensor no se ha calibrado contra muestras de laboratorio.'],
  ['The crop profile has not been validated by a local agronomist.',
    'El perfil de cultivo no lo ha validado un agrónomo local.'],
  ['Offline or stale climate data must be refreshed before field action.',
    'Los datos climáticos sin conexión o vencidos hay que actualizarlos antes de actuar en campo.'],

  // El perfil agronómico llega en español sin tildes desde el YAML del backend.
  ['lote demostrativo de Pasto, Narino; no transferible sin validacion local',
    'lote demostrativo de Pasto, Nariño; no transferible sin validación local'],
  ['Supuesto de demostracion IOmido v1; requiere revision de un ingeniero agronomo local.',
    'Supuesto de demostración IOmido v1; requiere revisión de un ingeniero agrónomo local.'],
  ['No es una prescripcion validada.', 'No es una prescripción validada.'],
  ['Supuesto de muestreo de demostracion IOmido v1.', 'Supuesto de muestreo de demostración IOmido v1.'],
  ['Debe confirmarse con el protocolo de campo.', 'Debe confirmarse con el protocolo de campo.'],
  ['Estimacion demostrativa para suelo volcanico; requiere medicion del lote.',
    'Estimación demostrativa para suelo volcánico; requiere medición del lote.'],
  ['No proviene de una muestra de densidad aparente del lote.',
    'No proviene de una muestra de densidad aparente del lote.'],
  ['Factor operacional conservador de demostracion IOmido v1.',
    'Factor operacional conservador de demostración IOmido v1.'],
  ['Debe calibrarse contra analisis de laboratorio y respuesta del cultivo.',
    'Debe calibrarse contra análisis de laboratorio y respuesta del cultivo.'],
  ['Limite de seguridad de demostracion IOmido v1.', 'Límite de seguridad de demostración IOmido v1.'],
  ['Requiere validacion tecnica antes de cualquier aplicacion.',
    'Requiere validación técnica antes de cualquier aplicación.'],
  ['Objetivo ilustrativo de la demo IOmido.', 'Objetivo ilustrativo de la demo IOmido.'],
]);

// Names the risk engine uses for its inputs.
const INPUT_LABEL = {
  minimum_temperature_c: 'temperatura mínima',
  enso_phase: 'fase ENSO',
  precipitation_mm: 'precipitación',
  evapotranspiration_mm: 'evapotranspiración',
  water_balance_mm: 'balance hídrico',
  seasonal_rainfall_anomaly_pct: 'anomalía de lluvia estacional',
  favorable_hours_48h: 'horas favorables (últimas 48 h)',
};
const INPUT_UNIT = {
  minimum_temperature_c: ' °C',
  precipitation_mm: ' mm',
  evapotranspiration_mm: ' mm',
  water_balance_mm: ' mm',
  seasonal_rainfall_anomaly_pct: ' %',
  favorable_hours_48h: ' h',
};
const ENSO_ES = { 'El Nino': 'El Niño', 'La Nina': 'La Niña', Neutral: 'neutra' };

// The backend ships ENSO phases without accents; the UI writes them properly.
function ensoLabel(phase) {
  return ENSO_ES[phase] || phase || '';
}

// Place names arrive unaccented from the database. Only the ones we actually
// serve are corrected; anything else is shown exactly as it came.
const PLACE_ES = new Map([['Narino', 'Nariño'], ['Pasto, Narino', 'Pasto, Nariño']]);

function place(name) {
  if (!name) return '';
  return PLACE_ES.get(name.trim()) || name.replace(/\bNarino\b/g, 'Nariño');
}

function riskInputs(entradas) {
  return Object.entries(entradas || {})
    .map(([k, v]) => {
      const label = INPUT_LABEL[k] || k.replace(/_/g, ' ');
      // Numbers follow the Spanish convention, so 2.4 reads as 2,4.
      const value = typeof v === 'number' ? fmt(v) : (ENSO_ES[v] || v);
      return `${label} ${value}${INPUT_UNIT[k] || ''}`;
    })
    .join(' · ');
}

function riskSources(fuentes) {
  return (fuentes || []).map((f) => `${f.name}${f.fetched_at ? ` (${f.fetched_at.slice(0, 10)})` : ''}`
    + `${f.stale || f.failed ? ' · no actual' : ''}`).join(', ');
}

const SOURCE_OFFLINE = /^(.+): network access is disabled; using a versioned offline fixture; data is not presented as current$/;

function translateOne(text) {
  if (typeof text !== 'string') return text;
  const mapped = BACKEND_ES.get(text.trim());
  if (mapped) return mapped;
  const offline = text.trim().match(SOURCE_OFFLINE);
  if (offline) {
    return `${offline[1]}: sin acceso a la red; se usó un archivo local con fecha, así que el dato no es actual.`;
  }
  return text;
}

function translateList(value) {
  const items = Array.isArray(value)
    ? value
    : String(value || '').split(',').map((s) => s.trim()).filter(Boolean);
  return [...new Set(items.map(translateOne))];
}

function viewPerfil() {
  const net = state.network;
  const view = state.view;
  const summary = net.real?.dashboard?.summary;
  const lotes = net.real?.lotes || [];

  const cifras = summary ? [
    ['Productores', summary.producer_count],
    ['Lotes', summary.plot_count],
    ['Lotes medidos', summary.measured_plot_count],
    ['Lotes con alerta', summary.plots_at_risk],
    ['Propuestas pendientes', summary.pending_proposals],
    ['Mediciones por revisar', summary.measurements_for_review],
  ].map(([label, value]) => `<tr><td>${label}</td><td class="num"><b>${value}</b></td></tr>`).join('') : '';

  const filas = lotes.length
    ? lotes.map((l) => `<tr>
        <td><b>${l.name}</b></td><td>${place(l.municipality)}</td>
        <td class="num">${l.reading_count}</td>
        <td><button class="btn ghost" type="button" data-nav="lote">Abrir</button></td>
      </tr>`).join('')
    : `<tr><td colspan="4" class="note">Sin conexión solo se conoce
        <b>${view.plot.name}</b>, el lote del paquete descargado.</td></tr>`;

  return `<div class="rwrap"><section class="card wide-card">
      <h2>El centro</h2>
      <div class="table-wrap"><table class="data"><tbody>
        <tr><td>Nombre</td><td><b>${net.acopio.nombre}</b></td></tr>
        <tr><td>Municipio</td><td>${place(net.acopio.municipio)}</td></tr>
        ${net.acopio.validacion ? `<tr><td>Estado</td><td>${VALIDATION_LABEL[net.acopio.validacion] || net.acopio.validacion}</td></tr>` : ''}
        ${cifras}
      </tbody></table></div>
      ${net.acopio.demo ? '<p class="note">Parte de la red que se muestra es demostrativa y está rotulada como tal.</p>' : ''}
    </section>

    <section class="card wide-card">
      <h2>Sus lotes</h2>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Lote</th><th>Municipio</th><th class="num">Mediciones</th><th></th></tr></thead>
        <tbody>${filas}</tbody></table></div>
    </section>

    <section class="card wide-card">
      <h2>Quién opera</h2>
      <div class="table-wrap"><table class="data"><tbody>
        <tr><td>Responsable</td><td><b>Juan Morales</b> · Administrador</td></tr>
        <tr><td>Decisiones</td><td>Las registra un técnico y quedan en auditoría</td></tr>
      </tbody></table></div>
      <p class="note">Las condiciones con las que se calcula viven en
        <button class="btn ghost" type="button" data-nav="configuracion">Configuración →</button></p>
    </section>
  </div>`;
}

// Names the agronomy profile uses for the parameters it cites.
const PARAM_LABEL = {
  requirement_kg_ha: 'Requerimiento del cultivo',
  sampling_depth_cm: 'Profundidad de muestreo',
  bulk_density_g_cm3: 'Densidad aparente',
  availability_fraction: 'Fracción disponible',
  maximum_application_kg_ha: 'Máximo por aplicación',
  maximum_bags_per_zone: 'Máximo de bultos por zona',
  target_yield_t_ha: 'Rendimiento objetivo',
};

function viewConfiguracion() {
  const view = state.view;
  const p = view.cultivo || {};
  const req = p.requirement_kg_ha || {};
  const max = p.maximum_application_kg_ha || {};
  const avail = p.availability_fraction || {};

  const citas = (p.sources || []).map((s) => `<tr>
      <td>${PARAM_LABEL[s.parameter] || s.parameter}</td>
      <td>${translateOne(s.citation)}${s.note ? ` <span class="note">${translateOne(s.note)}</span>` : ''}</td>
    </tr>`).join('');

  return `<div class="rwrap">
    <section class="card wide-card">
      <h2>Perfil de cultivo</h2>
      <div class="table-wrap"><table class="data"><tbody>
        <tr><td>Cultivo</td><td><b>${p.crop || ''} ${p.variety || ''}</b> · etapa ${p.stage || ''}</td></tr>
        <tr><td>Alcance</td><td>${translateOne(p.scope) || '—'}</td></tr>
        <tr><td>Rendimiento objetivo</td><td>${p.target_yield_t_ha ?? '—'} t/ha</td></tr>
        <tr><td>Vigente desde</td><td>${p.effective_from || '—'}</td></tr>
        <tr><td>Validación</td><td>${VALIDATION_LABEL[p.validation_status] || p.validation_status || '—'}
          ${p.validated_by_role ? '' : ' · sin firma profesional'}</td></tr>
      </tbody></table></div>
    </section>

    <section class="card wide-card">
      <h2>Con qué calcula</h2>
      <div class="table-wrap"><table class="data"><tbody>
        <tr><td>Requerimiento</td><td>N ${req.N} · P ${req.P} · K ${req.K} kg/ha</td></tr>
        <tr><td>Máximo por aplicación</td><td>N ${max.N} · P ${max.P} · K ${max.K} kg/ha</td></tr>
        <tr><td>Fracción disponible</td><td>N ${avail.N} · P ${avail.P} · K ${avail.K}</td></tr>
        <tr><td>Máximo de bultos por zona</td><td>${p.maximum_bags_per_zone ?? '—'}</td></tr>
        <tr><td>Profundidad de muestreo</td><td>${p.sampling_depth_cm ?? '—'} cm</td></tr>
        <tr><td>Densidad aparente</td><td>${Number.isFinite(p.bulk_density_g_cm3) ? fmt(p.bulk_density_g_cm3, 2) : '—'} g/cm³</td></tr>
        <tr><td>Unidad del suelo</td><td>porcentaje de masa, convención elemental</td></tr>
      </tbody></table></div>
    </section>

    ${citas ? `<section class="card wide-card">
      <h2>De dónde sale cada supuesto</h2>
      <div class="table-wrap"><table class="data"><tbody>${citas}</tbody></table></div>
      <p class="note">Ninguno de estos valores es una prescripción validada: requieren
        que un ingeniero agrónomo local los revise antes de usarlos en campo.</p>
    </section>` : ''}
  </div>`;
}

function render() {
  const view = state.view;
  const net = state.network;
  // The package's own degraded flag is not a headline: it says a climate source
  // fell back to a fixture, which each risk card already declares. Reportes
  // still lists every warning verbatim.
  const syncLabel = state.live ? 'al día' : 'sin red';

  const alertas = view.riesgos.length;

  document.getElementById('app').innerHTML = `<div class="shell">
    <aside class="side" id="side">
      <div class="side-brand">
        <span class="mark">iO</span>
        <span class="side-brand-name">IOmido<small>Inteligencia Operativa</small></span>
      </div>

      <nav class="side-nav" aria-label="Secciones">
        ${MENU_VIEWS.map((n) => `<button class="side-item ${state.nav === n ? 'on' : ''}" type="button"
            data-nav="${n}" aria-current="${state.nav === n ? 'page' : 'false'}">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="${MENU_ICON[n]}"/></svg>
            <span>${MENU_LABEL[n]}</span>
            ${n === 'alertas' && alertas ? `<b class="side-badge">${alertas}</b>` : ''}
          </button>`).join('')}
      </nav>

      <div class="side-foot">
        <div class="side-center">
          <span class="side-label">Centro de acopio</span>
          <b>${net.acopio.nombre}</b>
          <span class="note">${place(net.acopio.municipio)}</span>
          <button class="btn ghost" type="button" data-nav="perfil">Ver perfil</button>
        </div>
        <div class="side-user">
          <span class="side-avatar" aria-hidden="true">JM</span>
          <span class="side-user-name">Juan Morales<small>Administrador</small></span>
        </div>
      </div>
    </aside>

    <div class="content">
      <div class="sync">
        <span class="dot"></span>${syncLabel} · ${view.sampling.valid} mediciones
        ${net.acopio.demo ? '<span class="demo-chip">red demostrativa</span>' : ''}
        <span class="spacer"></span>
        <button class="icon-btn bell" type="button" data-nav="alertas" aria-label="${alertas} alertas activas">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="${MENU_ICON.alertas}"/></svg>
          ${alertas ? `<b class="side-badge">${alertas}</b>` : ''}
        </button>
        <button class="btn ghost ask-cta" type="button">Preguntar</button>
        <button class="icon-btn" type="button" data-nav="perfil" aria-label="Perfil del centro">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0"/></svg>
        </button>
      </div>

      <header class="page-head">
        <span class="page-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 21c5-2 8-6 8-11V5l-8-2-8 2v5c0 5 3 9 8 11z"/></svg>
        </span>
        <div>
          <h1>${net.acopio.nombre}</h1>
          <p>${net.real
            ? `${net.real.lotes.length} ${net.real.lotes.length === 1 ? 'lote' : 'lotes'} · ${place(net.acopio.municipio)}`
            : `${net.kpis.lotes} lotes · ${place(net.acopio.municipio)}`}</p>
        </div>
      </header>

      <main class="main" id="main">${viewFor(state.nav)}</main>
    </div>
  </div>`;

  for (const button of document.querySelectorAll('[data-nav]')) {
    button.addEventListener('click', () => {
      state.riesgoAbrir = button.dataset.riskGo || null;
      go(reachable(button.dataset.nav), button.dataset.tabGo || null);
    });
  }
  if (state.nav === 'historial' && !state.historial) loadHistorial();
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

// A dot on the map has nowhere to show a producer, so tapping one opens the
// Productores screen with that producer already expanded.
function openProducer(id) {
  state.productor = id;
  go('productores');
  const card = document.querySelector(`[data-prod="${id}"]`)?.closest('.prod-card, .prod-detail');
  if (card) card.scrollIntoView({ block: 'nearest' });
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
  state.live = pkg.live;
  state.nav = navFromHash();
  render();
}

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

boot().catch((error) => {
  document.getElementById('app').innerHTML = `<div class="loading">No se pudo cargar el acopio.<br><small>${error.message}</small></div>`;
});
