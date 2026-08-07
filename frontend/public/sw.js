/* Service worker SmartInvoice — cache des fichiers lus (offline first). */
/* eslint-disable no-restricted-globals */

// Version incrémentée à chaque changement d'`APP_SHELL` : l'ancien cache est
// purgé à l'activation (cf. `activate`).
const CACHE = "smartinvoice-v2";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest",
  "/favicon.ico",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  // On ne met en cache ni l'API (données authentifiées) ni les origines externes.
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  // Réseau d'abord, repli sur le cache pour les lectures (documents, JS, CSS…).
  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches
          .open(CACHE)
          .then((cache) => cache.put(request, copy))
          .catch(() => {});
        return response;
      })
      .catch(() =>
        caches.match(request).then((cached) => cached ?? caches.match("/")),
      ),
  );
});