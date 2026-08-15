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

export async function ask(question, view) {
  const local = matchLocal(question, view.voz);
  if (local) return { texto: local.texto, fuente: 'paquete descargado' };

  if (apiBase) {
    try {
      const remote = await askAgent(view.plot.id, question, false);
      return { texto: remote.texto, fuente: (remote.fuentes || []).join(', ') };
    } catch {
      // falls through to the offline notice
    }
  }

  return {
    texto: 'Eso no lo tengo guardado en el teléfono. Pregúnteme por el abono, cuándo aplicar, cuánto cuesta o qué viene con el clima.',
    fuente: 'sin conexión',
  };
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
