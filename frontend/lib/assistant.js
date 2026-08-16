// Answers from the offline voice cache first; the network is the fallback, not the path.

import { askAgent, apiBase } from './api.js';

const VOICE_LANG = 'es-CO';
const MIN_KEY_HITS = 2;

function normalize(text) {
  return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function words(text) {
  return normalize(text).split(/[^a-z0-9]+/).filter(Boolean);
}

export function matchLocal(question, voz) {
  const asked = words(question);
  let best = null;
  let hits = 0;
  for (const entry of voz) {
    const score = entry.claves.filter((key) => asked.includes(normalize(key))).length;
    if (score > hits) {
      hits = score;
      best = entry;
    }
  }
  return hits >= MIN_KEY_HITS ? best : null;
}

// The offline cache is whatever the package still carries; the v2 contract does
// not ship one, so in practice this asks the agent and degrades to a local note.
export async function ask(question, view) {
  const local = matchLocal(question, view.voz || []);
  if (local) return { texto: local.texto, fuente: 'paquete descargado' };

  if (apiBase) {
    try {
      const agent = await askAgent(view.plot.id, question);
      return {
        texto: agent.answer,
        fuente: (agent.sources || []).map((s) => s.name || s).join(', ') || 'agente del backend',
      };
    } catch (error) {
      console.warn('[assistant] el agente no respondió:', error.message);
    }
  }

  return { texto: offlineAnswer(view), fuente: 'sin conexión · paquete descargado' };
}

// Without the agent we still answer from the package instead of saying nothing.
function offlineAnswer(view) {
  const next = view.nextSample;
  if (!next) return 'Sin conexión no puedo responder eso. El paquete descargado sí trae el mapa, la propuesta y los riesgos.';
  return `Sin conexión, del paquete descargado: mida cerca de ${next.punto[0].toFixed(6)}, ${next.punto[1].toFixed(6)}, `
    + `a ${Math.round(next.distancia_m)} m de la medición más cercana.`;
}

export const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window;

export function speak(text) {
  if (!canSpeak) return false;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = VOICE_LANG;
  utterance.rate = 1.02;
  window.speechSynthesis.speak(utterance);
  return true;
}

export function stopSpeaking() {
  if (canSpeak) window.speechSynthesis.cancel();
}

const Recognition = typeof window !== 'undefined'
  && (window.SpeechRecognition || window.webkitSpeechRecognition);

export const canListen = Boolean(Recognition);

export function listen({ onResult, onEnd, onError }) {
  if (!Recognition) return null;
  const recognition = new Recognition();
  recognition.lang = VOICE_LANG;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.addEventListener('result', (event) => onResult(event.results[0][0].transcript));
  recognition.addEventListener('end', () => onEnd?.());
  recognition.addEventListener('error', (event) => onError?.(event.error));
  recognition.start();
  return recognition;
}
