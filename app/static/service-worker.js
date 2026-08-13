const STATIC_CACHE = 'brickshelf-static-v15';
const PAGE_CACHE = 'brickshelf-pages-v1';
const IMAGE_CACHE = 'brickshelf-images-v1';
const OFFLINE_URL = '/static/offline.html';
const STATIC_ASSETS = [OFFLINE_URL, '/static/css/style.css', '/static/js/app.js', '/static/img/brickshelf-icon.svg', '/static/manifest.webmanifest'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  const keep = new Set([STATIC_CACHE, PAGE_CACHE, IMAGE_CACHE]);
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => !keep.has(key)).map((key) => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('message', (event) => {
  if (event.data === 'CLEAR_PRIVATE_CACHE') {
    event.waitUntil(Promise.all([caches.delete(PAGE_CACHE), caches.delete(IMAGE_CACHE)]));
  }
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then((response) => {
      if (response.ok) caches.open(PAGE_CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    }).catch(async () => (await caches.match(request)) || caches.match(OFFLINE_URL)));
    return;
  }
  if (url.origin === self.location.origin) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) caches.open(STATIC_CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    })));
    return;
  }
  if (request.destination === 'image') {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      caches.open(IMAGE_CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    })));
  }
});
