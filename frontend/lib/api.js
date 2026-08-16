// Contract client. Every call to the v2 backend goes through here.

const DEFAULT_PLOT = 'nar-001';
const REQUEST_TIMEOUT_MS = 8000;

// Point this at the backend when it exists: window.NPK_API_BASE = 'https://api.example.com'
export const apiBase = (typeof window !== 'undefined' && window.NPK_API_BASE) || '';

// Only needed when the backend runs with WRITE_API_KEY set.
const writeKey = () => (typeof window !== 'undefined' && window.NPK_WRITE_KEY) || '';

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS), ...options });
  if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
  return response.json();
}

function requireBase() {
  if (!apiBase) throw new Error('Sin backend: esta operación necesita conexión.');
  return apiBase;
}

function get(path) {
  return fetchJson(`${requireBase()}${path}`);
}

function send(path, body, { raw = false } = {}) {
  const headers = raw ? {} : { 'content-type': 'application/json' };
  const key = writeKey();
  if (key) headers['X-API-Key'] = key;
  return fetchJson(`${requireBase()}${path}`, {
    method: 'POST',
    headers,
    ...(body === undefined ? {} : { body: raw ? body : JSON.stringify(body) }),
  });
}

export async function getPackage(plotId = DEFAULT_PLOT) {
  const local = `/mock/package-${plotId}.json`;
  if (!apiBase) {
    return { data: await fetchJson(local), origin: 'paquete local', live: false };
  }
  try {
    const data = await fetchJson(`${apiBase}/v1/plots/${plotId}/package`);
    return { data, origin: 'backend', live: true };
  } catch (error) {
    // El backend no responde. Se sirve el último paquete bueno en vez de una
    // pantalla en blanco: es la misma regla que el backend aplica con sus
    // fuentes externas. Una demo en 2G no se puede caer porque falle la red.
    console.warn('[api] backend no disponible, se usa el paquete local:', error.message);
    return { data: await fetchJson(local), origin: 'paquete local', live: false };
  }
}

// Configuración
export const getCenters = () => get('/v1/centers');
export const getPlots = () => get('/v1/plots');

// Lecturas
export const postReading = (reading) => send('/v1/readings', reading);
export const postReadingsBulk = (readings) => send('/v1/readings/bulk', { readings });
export const importReadings = (plotId, file) => {
  const form = new FormData();
  form.append('file', file);
  return send(`/v1/readings/import?plot_id=${encodeURIComponent(plotId)}`, form, { raw: true });
};
export const recompute = (plotId) => send(`/v1/plots/${plotId}/recompute`);

// Gobernanza
export const getProposalWhy = (proposalId) => get(`/v1/proposals/${proposalId}/why`);
export const postDecision = ({ proposalId, action, actor, modification = null, note = null }) =>
  send('/v1/decisions', {
    proposal_id: proposalId, action, actor, modification, note,
  });
export const getDecision = (decisionId) => get(`/v1/decisions/${decisionId}`);
export const getDecisionHistory = (identifier) => get(`/v1/decisions/${identifier}/history`);
export const getGovernance = () => get('/v1/governance');
export const getAudit = () => get('/v1/audit');

// Modelos
export const getModels = () => get('/v1/models');
export const getModelMetrics = (modelId) => get(`/v1/models/${modelId}/metrics`);

// Conversación. La respuesta útil vive en response.agent.answer.
export async function askAgent(plotId, question) {
  const response = await send('/v1/agent/ask', { plot_id: plotId, question });
  return response.agent;
}
