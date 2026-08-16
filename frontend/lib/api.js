// Contract client. One round-trip per screen, per FRONTEND.md.

const DEFAULT_PLOT = 'nar-001';
const REQUEST_TIMEOUT_MS = 8000;

// En el despliegue la API se sirve desde el mismo origen que esta página, así
// que ese es el valor por defecto. Para un backend en otro host se sobreescribe
// antes de cargar el módulo: window.NPK_API_BASE = 'https://api.example.com'.
// Un origen file:// no tiene backend detrás y se queda en el paquete local.
function resolveBase() {
  if (typeof window === 'undefined') return '';
  if (typeof window.NPK_API_BASE === 'string') return window.NPK_API_BASE;
  return /^https?:$/.test(window.location.protocol) ? window.location.origin : '';
}

export const apiBase = resolveBase();

async function fetchJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
  return response.json();
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

export async function listPlots() {
  const url = apiBase ? `${apiBase}/v1/plots` : '/mock/plots.json';
  return fetchJson(url);
}

export async function askAgent(plotId, texto, quiereAudio = false) {
  if (!apiBase) throw new Error('Sin backend: responde el cache local de voz.');
  const response = await fetch(`${apiBase}/v1/agent/ask`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ plot_id: plotId, texto, quiere_audio: quiereAudio }),
  });
  if (!response.ok) throw new Error(`agent/ask respondió ${response.status}`);
  return response.json();
}
