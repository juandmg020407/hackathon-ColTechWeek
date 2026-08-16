// Answers from the offline voice cache first; the network is the fallback, not the path.

import { askAgent, apiBase } from './api.js';

const VOICE_LANG = 'es-CO';
const MIN_KEY_HITS = 2;
const RISK_LABEL = { frost: 'helada', drought: 'sequía', late_blight: 'gota', seasonal: 'estacional' };
const SEVERITY_LABEL = { critical: 'crítica', high: 'alta', medium: 'media', low: 'baja' };

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

  return { texto: offlineAnswer(question, view), fuente: 'sin conexión · paquete descargado' };
}

// Sin el agente se cubren las preguntas operativas mas comunes directamente
// desde el package. Una pregunta desconocida no recibe una respuesta inventada.
function offlineAnswer(question, view) {
  const text = normalize(question);
  const next = view.nextSample;

  if (/donde|medir|mido|siguiente punto/.test(text)) {
    if (!next) return 'El paquete descargado no trae un siguiente punto de medición.';
    return `Del paquete descargado: mida cerca de ${next.punto[0].toFixed(6)}, ${next.punto[1].toFixed(6)}, `
      + `a ${Math.round(next.distancia_m)} m de la medición más cercana.`;
  }

  if (/formula|formulacion|bulto|propuesta|aplicar/.test(text)) {
    const plans = (view.propuesta?.zonas || []).map((zone) => {
      const bags = zone.formulaciones.map((item) => `${item.bags} bulto${item.bags === 1 ? '' : 's'} ${item.label}`).join(' y ');
      return `zona ${zone.id.replace('zone-', '')}: ${bags || 'sin bultos'}`;
    });
    if (!plans.length) return 'El paquete descargado todavía no trae una propuesta para este lote.';
    return `La propuesta candidata indica ${plans.join('; ')}. Sigue pendiente de validación técnica y no está aplicada.`;
  }

  if (/riesgo|clima|helada|sequia|gota|lluvia/.test(text)) {
    if (!view.riesgos.length) return 'El paquete descargado no reporta riesgos activos para este lote.';
    const risks = view.riesgos.map((risk) => `${RISK_LABEL[risk.tipo] || risk.tipo}: ${SEVERITY_LABEL[risk.severidad] || risk.severidad}`).join('; ');
    return `El paquete reporta ${risks}.${view.degradado ? ' Las fuentes no están actuales.' : ''}`;
  }

  if (/incertid|confianza|segur|precision/.test(text)) {
    return `${view.coverage.uncertainPct}% del lote está marcado sin certeza. El modelo usa ${view.sampling.valid} de ${view.sampling.total} mediciones; revise el mapa antes de decidir.`;
  }

  if (/prior|urgente/.test(text)) {
    const measurement = view.descartados.length
      ? `revise la medición que quedó fuera del lote y manténgala fuera del modelo`
      : `revise la cobertura de mediciones`;
    const risk = view.riesgos[0]
      ? ` Después atienda el riesgo ${RISK_LABEL[view.riesgos[0].tipo] || view.riesgos[0].tipo} de severidad ${SEVERITY_LABEL[view.riesgos[0].severidad] || view.riesgos[0].severidad}.`
      : '';
    return `Primero ${measurement}.${risk} La propuesta sigue pendiente de validación técnica.`;
  }

  if (/estado|suelo|nutriente|lote/.test(text)) {
    const zones = view.zonas.map((zone) => `zona ${zone.id.replace('zone-', '')}: N ${zone.npk.N.toFixed(2)} %, P ${zone.npk.P.toFixed(2)} %, K ${zone.npk.K.toFixed(2)} %`).join('; ');
    return `El lote tiene ${view.sampling.valid} mediciones válidas y ${view.zonas.length} zonas. ${zones}.`;
  }

  return 'Sin conexión no tengo evidencia para esa pregunta. Puedo explicar el estado del lote, la propuesta, los riesgos, la incertidumbre o el siguiente punto de medición.';
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
