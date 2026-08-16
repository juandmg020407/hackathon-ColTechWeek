// Service worker: la red manda mientras exista, y el caché es el respaldo para
// trabajar sin señal. Servir el caché primero congelaba la aplicación en la
// versión del despliegue anterior hasta que alguien recargaba a la fuerza.

const CACHE = 'iomido-v12';
const SHELL = [
  '/',
  '/index.html',
  '/favicon.svg',
  '/pitch.html',
  '/login.html',
  '/register.html',
  '/style.css',
  '/pitch.css',
  '/auth.css',
  '/app.js',
  '/assets/field.webp',
  '/manifest.webmanifest',
  '/lib/api.js',
  '/lib/network.js',
  '/lib/adapt.js',
  '/lib/plotmap.js',
  '/lib/colormap.js',
  '/lib/slippy.js',
  '/lib/heatsurface.js',
  '/lib/assistant.js',
  '/lib/qr.js',
  '/informes/acta-plan-el-rosal.pdf',
  '/mock/package-nar-001.json',
  '/mock/network.json',
];
const PACKAGE_PATH = '/v1/plots/';
// Un archivo binario solo cambia si cambia su nombre: ahí el caché sí puede ir
// primero sin arriesgarse a servir algo viejo.
const IMMUTABLE = /\.(webp|png|jpe?g|svg|gif|pdf|woff2?|ico)$/i;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // `reload` salta el caché HTTP del navegador: si no, el precache podía
      // guardar la copia vieja que el propio navegador tenía en disco.
      .then((cache) => Promise.allSettled(
        SHELL.map((url) => cache.add(new Request(url, { cache: 'reload' }))),
      ))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    const replacesOldVersion = keys.some((key) => key !== CACHE && key.startsWith('iomido-'));
    await Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)));
    await self.clients.claim();

    if (!replacesOldVersion) return;
    // Las pestañas abiertas siguen mostrando el HTML de la versión anterior
    // aunque este worker ya tenga el control. Se recargan una sola vez, al
    // activarse la versión nueva, para que nadie tenga que forzar la recarga.
    const windows = await self.clients.matchAll({ type: 'window' });
    await Promise.all(windows.map((client) => client.navigate(client.url).catch(() => {})));
  })());
});

async function putInCache(request, response) {
  if (!response || !response.ok) return;
  const cache = await caches.open(CACHE);
  await cache.put(request, response.clone());
}

async function networkFirst(request) {
  try {
    // `no-cache` revalida contra el servidor: responde 304 y no cuesta ancho de
    // banda cuando el archivo no cambió, pero nunca devuelve algo obsoleto.
    const response = request.mode === 'navigate'
      ? await fetch(request.url, { cache: 'no-cache', credentials: 'same-origin' })
      : await fetch(request, { cache: 'no-cache' });
    await putInCache(request, response);
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.mode === 'navigate') {
      const shell = await caches.match('/index.html');
      if (shell) return shell;
    }
    throw error;
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  await putInCache(request, response);
  return response;
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith(PACKAGE_PATH) || event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request));
    return;
  }

  if (IMMUTABLE.test(url.pathname)) {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  event.respondWith(networkFirst(event.request));
});
