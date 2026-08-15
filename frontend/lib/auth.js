// Authentication seam. Presentational callers hand credentials here and get a session back.

import { apiBase } from './api.js';

const SESSION_KEY = 'npk.session';

// Mock mode is the default until the backend exists. Set window.NPK_API_BASE to switch.
export const usingMock = !apiBase;

export function currentSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
  } catch {
    return null;
  }
}

export function signOut() {
  sessionStorage.removeItem(SESSION_KEY);
}

function persist(session) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

async function mockSignIn({ user, password }) {
  await new Promise((resolve) => setTimeout(resolve, 550));
  if (!user || !password) throw new Error('Escribe tu usuario y tu contraseña.');
  if (password.length < 4) throw new Error('La contraseña es demasiado corta.');
  return persist({
    user,
    lot: 'pasto-01',
    issuedAt: new Date().toISOString(),
    mock: true,
  });
}

async function mockSignUp({ name, user, password, confirm }) {
  await new Promise((resolve) => setTimeout(resolve, 650));
  if (!name || !user || !password) throw new Error('Completa todos los campos.');
  if (password.length < 8) throw new Error('La contraseña necesita al menos 8 caracteres.');
  if (password !== confirm) throw new Error('Las dos contraseñas no coinciden.');
  return persist({
    user,
    name,
    lot: 'pasto-01',
    issuedAt: new Date().toISOString(),
    mock: true,
  });
}

async function apiSignUp({ name, user, password }) {
  const response = await fetch(`${apiBase}/api/auth/register`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name, user, password }),
    credentials: 'include',
  });
  if (response.status === 409) throw new Error('Ese usuario ya existe.');
  if (!response.ok) throw new Error('No pudimos crear la cuenta. Intenta de nuevo.');
  return persist({ ...(await response.json()), mock: false });
}

export async function signUp(form) {
  if (form.password !== form.confirm) throw new Error('Las dos contraseñas no coinciden.');
  return usingMock ? mockSignUp(form) : apiSignUp(form);
}

async function apiSignIn({ user, password }) {
  const response = await fetch(`${apiBase}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ user, password }),
    credentials: 'include',
  });
  if (response.status === 401) throw new Error('Usuario o contraseña incorrectos.');
  if (!response.ok) throw new Error('No pudimos entrar. Intenta de nuevo.');
  return persist({ ...(await response.json()), mock: false });
}

export function signIn(credentials) {
  return usingMock ? mockSignIn(credentials) : apiSignIn(credentials);
}
