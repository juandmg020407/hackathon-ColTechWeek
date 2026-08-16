// Cache-first service worker: after the first load the app opens without network.

const CACHE = 'iomido-v9';
const SHELL = [
  '/',
  '/index.html',
  '/favicon.svg',
  '/pitch.html',
  '/style.css',
  '/pitch.css',
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
  '/mock/package-nar-001.json',
  '/mock/network.json',
];
const PACKAGE_PATH = '/v1/plots/';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => Promise.allSettled(SHELL.map((url) => cache.add(url))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith(PACKAGE_PATH)) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request)),
    );
    return;
  }

  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
