// Contract client. One round-trip per screen, per FRONTEND.md.

const DEFAULT_PLOT = 'nar-001';
const REQUEST_TIMEOUT_MS = 8000;

// Point this at the backend when it exists: window.NPK_API_BASE = 'https://api.example.com'
export const apiBase = (typeof window !== 'undefined' && window.NPK_API_BASE) || '';

async function fetchJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
  return response.json();
}

export async function getPackage(plotId = DEFAULT_PLOT) {
  const url = apiBase
    ? `${apiBase}/v1/plots/${plotId}/package`
    : `/mock/package-${plotId}.json`;
  const data = await fetchJson(url);
  return { data, origin: apiBase ? 'backend' : 'paquete local', live: Boolean(apiBase) };
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
