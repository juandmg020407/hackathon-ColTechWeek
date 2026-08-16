// Network contract client: one round-trip per screen, same seam as api.js.

const DEFAULT_ACOPIO = 'ac-pasto';
const REQUEST_TIMEOUT_MS = 8000;

export const apiBase = (typeof window !== 'undefined' && window.NPK_API_BASE) || '';

async function fetchJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
  return response.json();
}

export async function getNetwork(acopioId = DEFAULT_ACOPIO) {
  const url = apiBase
    ? `${apiBase}/v1/acopios/${acopioId}/network`
    : `/mock/network.json`;
  const data = await fetchJson(url);
  return { data, origin: apiBase ? 'backend' : 'paquete local', live: Boolean(apiBase) };
}