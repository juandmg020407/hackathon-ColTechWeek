// Center context. A live backend supplies every visible aggregate; the checked-
// in network file is used only when the application is offline.

import { apiBase, getCenterDashboard, getCenters } from './api.js';

const DEMO_CONTEXT = '/mock/network.json';
const REQUEST_TIMEOUT_MS = 8000;

async function fetchJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
  return response.json();
}

function synthetic(demo) {
  return { ...demo, real: null };
}

const SEVERITY_LEVEL = {
  critical: 'alto', high: 'alto', medium: 'medio', low: 'bajo', none: 'bajo',
};
const SEVERITY_CARD = {
  critical: 'critica', high: 'alta', medium: 'media', low: 'baja', none: 'baja',
};
const RISK_ICON = { frost: '🌡', drought: '💧', late_blight: '🍃', seasonal: '◌' };

function dateLabel(value) {
  if (!value) return 'Sin mediciones';
  return new Date(value).toLocaleString('es-CO', {
    dateStyle: 'short', timeStyle: 'short',
  });
}

function adaptDashboard(dashboard) {
  const plots = [
    ...dashboard.producers.flatMap((producer) => producer.plots),
    ...dashboard.unassigned_plots,
  ].map((plot) => ({ ...plot, reading_count: plot.measurement_count }));
  const producers = dashboard.producers.map((producer) => {
    const firstPlot = producer.plots[0];
    const location = firstPlot?.location || {};
    return {
      id: producer.id,
      nombre: producer.display_name,
      piloto: producer.data_origin === 'pilot',
      origen_datos: producer.data_origin,
      consentimiento: producer.consent_status,
      lotes: producer.plot_count,
      area_ha: producer.total_area.value,
      lotes_riesgo: producer.plots_at_risk,
      riesgo_nivel: SEVERITY_LEVEL[producer.highest_risk.severity] || 'bajo',
      riesgo_pct: Math.round((producer.highest_risk.score || 0) * 100),
      ultima_medicion: dateLabel(producer.latest_measurement_at),
      lat: location.latitude,
      lon: location.longitude,
      pkg: firstPlot?.id || null,
    };
  }).filter((producer) => Number.isFinite(producer.lat) && Number.isFinite(producer.lon));

  const riskArea = plots
    .filter((plot) => ['medium', 'high', 'critical'].includes(plot.highest_risk.severity))
    .reduce((total, plot) => total + plot.area.value, 0);
  const totalArea = dashboard.summary.total_area.value;
  const measuredPct = dashboard.summary.plot_count
    ? Math.round((dashboard.summary.measured_plot_count / dashboard.summary.plot_count) * 100)
    : 0;

  return {
    generado: new Date().toISOString(),
    ttl_horas: null,
    degradado: plots.some((plot) => plot.degraded),
    aviso: dashboard.data_scope.statement,
    acopio: {
      id: dashboard.center.id,
      nombre: dashboard.center.name,
      municipio: dashboard.center.municipality,
      validacion: dashboard.center.validation_status,
      demo: dashboard.data_scope.contains_demonstration_data,
    },
    kpis: {
      productores: dashboard.summary.producer_count,
      lotes: dashboard.summary.plot_count,
      area_ha: totalArea,
      lotes_riesgo: dashboard.summary.plots_at_risk,
    },
    // The legacy view calls this "salud"; with live data it represents measured
    // coverage, not crop health, and carries no invented week-over-week change.
    salud: {
      pct: measuredPct,
      lotes_ok: dashboard.summary.plot_count - dashboard.summary.plots_at_risk,
      lotes_criticos: dashboard.summary.plots_at_risk,
      pct_semana_pasada: measuredPct,
      delta_semana: 0,
    },
    area_riesgo: {
      ha: Math.round(riskArea * 100) / 100,
      pct: totalArea ? Math.round((riskArea / totalArea) * 100) : 0,
    },
    proximos_7d: dashboard.priority_queue.length,
    prioridades: dashboard.priority_queue.map((priority) => ({
      id: priority.id,
      severidad: SEVERITY_CARD[priority.severity] || 'media',
      titulo: priority.title,
      lotes: 1,
      productores: priority.producer_id ? 1 : 0,
      detalle: priority.detail,
      meta: 'Abrir lote',
      plot_id: priority.plot_id,
    })),
    horizonte: dashboard.risk_horizon.map((risk) => ({
      id: risk.type,
      icono: RISK_ICON[risk.type] || '◌',
      etiqueta: risk.label,
      nivel: SEVERITY_LEVEL[risk.severity] || 'bajo',
      barras: Math.round((risk.max_score || 0) * 10),
    })),
    productores: producers,
    movimientos: [
      { icono: '🧭', cantidad: dashboard.summary.pending_proposals, texto: 'propuestas pendientes' },
      { icono: '🧪', cantidad: dashboard.summary.measurements_for_review, texto: 'mediciones para revisar' },
      { icono: '✓', cantidad: dashboard.summary.measured_plot_count, texto: 'lotes medidos' },
    ],
    real: { centro: dashboard.center, lotes: plots, dashboard },
    demo_note: dashboard.data_scope.statement,
  };
}

export async function getNetwork() {
  const demo = await fetchJson(DEMO_CONTEXT);
  if (!apiBase) {
    return { data: synthetic(demo), origin: 'contexto sintético', live: false };
  }
  try {
    const centers = await getCenters();
    const center = centers.centers?.[0];
    if (!center) throw new Error('el backend no declara ningún centro');
    const response = await getCenterDashboard(center.id);
    return {
      data: adaptDashboard(response.dashboard),
      origin: 'backend',
      live: true,
    };
  } catch (error) {
    console.warn('[network] backend no disponible, se usa el contexto sintético:', error.message);
    return { data: synthetic(demo), origin: 'contexto sintético', live: false };
  }
}
