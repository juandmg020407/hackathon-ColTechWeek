// Contract client. Every call to the v2 backend goes through here.

const DEFAULT_PLOT = 'nar-001';
const REQUEST_TIMEOUT_MS = 8000;
const AGENT_REQUEST_TIMEOUT_MS = 25000;

const BACKEND_DEV_PORT = '8000';
const LOCAL_HOST = /^(localhost|127\.0\.0\.1)$/;

// En el despliegue la API se sirve desde el mismo origen que esta página, así
// que ese es el valor por defecto. Para cualquier otro backend se sobreescribe
// antes de cargar el módulo: window.NPK_API_BASE = 'https://api.example.com'.
//
// Un preview estático local en otro puerto no tiene API detrás: devolver el
// origen ahí dispara peticiones que el navegador registra como error antes de
// que el código pueda capturarlas. Sin base, la app va directo al paquete
// local y la consola queda limpia.
function resolveBase() {
  if (typeof window === 'undefined') return '';
  if (typeof window.NPK_API_BASE === 'string') return window.NPK_API_BASE;

  const { protocol, hostname, port, origin } = window.location;
  if (!/^https?:$/.test(protocol)) return '';
  if (LOCAL_HOST.test(hostname) && port !== BACKEND_DEV_PORT) return '';
  return origin;
}

export const apiBase = resolveBase();

// Only needed when the backend runs with WRITE_API_KEY set.
const writeKey = () => (typeof window !== 'undefined' && window.NPK_WRITE_KEY) || '';

async function fetchJson(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs), ...options });
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

function send(path, body, {
  raw = false,
  timeoutMs = REQUEST_TIMEOUT_MS,
  method = 'POST',
} = {}) {
  const headers = raw ? {} : { 'content-type': 'application/json' };
  const key = writeKey();
  if (key) headers['X-API-Key'] = key;
  return fetchJson(`${requireBase()}${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: raw ? body : JSON.stringify(body) }),
  }, timeoutMs);
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
export const getCenterDashboard = (centerId) => get(`/v1/centers/${encodeURIComponent(centerId)}/dashboard`);
export const getProducers = (centerId) => get(`/v1/centers/${encodeURIComponent(centerId)}/producers`);
export const getProducer = (producerId) => get(`/v1/producers/${encodeURIComponent(producerId)}`);
export const getProducerPlots = (producerId) => get(`/v1/producers/${encodeURIComponent(producerId)}/plots`);
export const createProducer = (centerId, producer) => send(
  `/v1/centers/${encodeURIComponent(centerId)}/producers`, producer,
);
export const updateProducer = (producerId, producer) => send(
  `/v1/producers/${encodeURIComponent(producerId)}`,
  producer,
  { method: 'PUT' },
);
export const getPlots = ({ centerId, producerId } = {}) => {
  const params = new URLSearchParams();
  if (centerId) params.set('center_id', centerId);
  if (producerId) params.set('producer_id', producerId);
  const queryString = params.toString();
  const query = queryString ? `?${queryString}` : '';
  return get(`/v1/plots${query}`);
};
export const getPlot = (plotId) => get(`/v1/plots/${encodeURIComponent(plotId)}`);
export const getPlotReadings = (plotId, { validOnly = false } = {}) => get(
  `/v1/plots/${encodeURIComponent(plotId)}/readings?valid_only=${validOnly}`,
);

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
  const response = await send(
    '/v1/agent/ask',
    { plot_id: plotId, question },
    { timeoutMs: AGENT_REQUEST_TIMEOUT_MS },
  );
  return response.agent;
}
