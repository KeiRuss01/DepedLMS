const CACHE_VERSION = "n1-hlms-shell-v29";
const OFFLINE_URL = "/offline/";
const OFFLINE_MODULES_URL = "/offline/modules/";

const APP_SHELL = [
    "/static/accounts/js/appearance.js?v=1",
    "/static/accounts/css/appearance.css?v=1",
    OFFLINE_URL,
    "/static/pwa/js/offline-home.js?v=4",
    OFFLINE_MODULES_URL,
    "/static/vendor/bootstrap/css/bootstrap.min.css",
    "/static/vendor/bootstrap/js/bootstrap.bundle.min.js",
    "/static/vendor/pdfjs/legacy/build/pdf.min.mjs",
    "/static/vendor/pdfjs/legacy/build/pdf.worker.min.mjs",
    "/static/pwa/js/offline-db.js?v=5",
    "/static/pwa/js/offline-sync.js?v=7",
    "/static/pwa/js/offline-module-viewer.js?v=4",
    "/static/pwa/icons/icon-192.svg",
    "/static/pwa/icons/icon-512.svg",
    "/offline/modules/editor/",
    "/static/vendor/bootstrap-icons/font/bootstrap-icons.min.css",
    "/static/vendor/bootstrap-icons/font/fonts/bootstrap-icons.woff2",
    "/static/classroom/css/mobile_module_editor.css",
    "/static/classroom/js/mobile_module_editor.js?v=local-first-12",
    "/static/pwa/js/device-registry.js?v=2",
    "/static/classroom/js/offline-attendance-roster.js?v=2",
    "/offline/attendance/",
    "/static/pwa/js/offline-attendance-entry.js?v=3",
    "/static/pwa/js/offline-attendance-sync.js?v=1",
    "/offline/grades/",
    "/static/pwa/js/offline-gradebook.js?v=3",
    "/static/pwa/js/offline-grade-sync.js?v=2",
    "/static/classroom/js/offline-gradebook-download.js?v=3",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_VERSION)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys
                    .filter((key) => {
                        return (
                            key.startsWith("n1-hlms-") &&
                            key !== CACHE_VERSION
                        );
                    })
                    .map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;

    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);

    if (url.origin !== self.location.origin) {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(async () => {
                const savedPage = await caches.match(
                    request,
                    { ignoreSearch: true }
                );

                return (
                    savedPage ||
                    caches.match(OFFLINE_URL)
                );
            })
        );

        return;
    }

    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(request).then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse;
                }

                return fetch(request).then((networkResponse) => {
                    if (
                        !networkResponse ||
                        networkResponse.status !== 200
                    ) {
                        return networkResponse;
                    }

                    const responseCopy = networkResponse.clone();

                    caches.open(CACHE_VERSION).then((cache) => {
                        cache.put(request, responseCopy);
                    });

                    return networkResponse;
                });
            })
        );
    }
});
