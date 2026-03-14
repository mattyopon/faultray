const CACHE_NAME = 'chaosproof-v1';
const STATIC_ASSETS = [
    '/static/style.css',
    '/static/graph.js',
    '/static/manifest.json'
];

// Install - precache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate - clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch - network-first for API calls, cache-first for static assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    if (url.pathname.startsWith('/api/')) {
        // Network-first strategy for API calls
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    return response;
                })
                .catch(() => {
                    return caches.match(event.request);
                })
        );
    } else if (url.pathname.startsWith('/static/')) {
        // Cache-first strategy for static assets
        event.respondWith(
            caches.match(event.request)
                .then((cached) => {
                    if (cached) {
                        return cached;
                    }
                    return fetch(event.request).then((response) => {
                        if (response.ok) {
                            const clone = response.clone();
                            caches.open(CACHE_NAME).then((cache) => {
                                cache.put(event.request, clone);
                            });
                        }
                        return response;
                    });
                })
        );
    }
});
