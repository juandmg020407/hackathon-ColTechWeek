// Center context. Real identity and plot list come from the backend; the rest of
// the network is synthetic demo scaffolding and is always labelled as such.

import { apiBase, getCenters, getPlots } from './api.js';

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

export async function getNetwork() {
  const demo = await fetchJson(DEMO_CONTEXT);
  if (!apiBase) {
    return { data: synthetic(demo), origin: 'contexto sintético', live: false };
  }
  try {
    const [centers, plots] = await Promise.all([getCenters(), getPlots()]);
    const center = centers.centers?.[0];
    if (!center) throw new Error('el backend no declara ningún centro');
    return {
      data: {
        ...demo,
        acopio: {
          id: center.id,
          nombre: center.name,
          municipio: center.municipality,
          validacion: center.validation_status,
          demo: false,
        },
        real: { centro: center, lotes: plots.plots || [] },
      },
      origin: 'backend',
      live: true,
    };
  } catch (error) {
    console.warn('[network] backend no disponible, se usa el contexto sintético:', error.message);
    return { data: synthetic(demo), origin: 'contexto sintético', live: false };
  }
}
