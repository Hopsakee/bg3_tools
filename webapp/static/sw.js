/*
 * Offline lezen. De bedoeling: wat je onderweg al bekeken hebt, blijft
 * leesbaar zonder verbinding -- precies het geval waarvoor je de app op je
 * Boox zet.
 *
 * Strategie per soort verzoek:
 *   navigatie  -> eerst het netwerk (je wilt verse gegevens), bij een fout de
 *                 cache, en anders de offlinepagina.
 *   statisch   -> eerst de cache (die verandert alleen bij een nieuwe versie),
 *                 met een stille verversing op de achtergrond.
 *   POST enz.  -> nooit aanraken. Een notitie opslaan hoort te falen als er
 *                 geen verbinding is, niet stilletjes in een cache te landen.
 */

const VERSION = "bg3-partyboek-v1";
const SHELL = [
  "/static/app.css",
  "/static/icon.svg",
  "/static/register-sw.js",
  "/manifest.webmanifest",
  "/offline",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(VERSION).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() =>
          caches.match(request).then((hit) => hit || caches.match("/offline"))
        )
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((hit) => {
      const fresh = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(VERSION).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => hit);
      return hit || fresh;
    })
  );
});
