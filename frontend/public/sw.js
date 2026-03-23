/**
 * Enterprise FizzBuzz Platform — Service Worker
 *
 * Ensures uninterrupted access to the Operations Center during network
 * partitions. Implements a cache-first strategy for the application shell
 * and a network-first strategy for API requests, guaranteeing that
 * mission-critical FizzBuzz monitoring remains operational even when
 * connectivity to the evaluation cluster is intermittent.
 */

const CACHE_NAME = 'efb-platform-v1';

const PRECACHE_URLS = [
  '/',
  '/evaluate',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Network-first for navigation requests to ensure fresh content
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(event.request).then((cached) => cached || caches.match('/'))
      )
    );
    return;
  }

  // Cache-first for static assets
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        // Cache successful GET responses for static assets
        if (
          response.ok &&
          event.request.method === 'GET' &&
          event.request.url.startsWith(self.location.origin)
        ) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      });
    })
  );
});
