/* Service Worker — 코드/데이터는 네트워크 우선(항상 최신), 지도 타일만 캐시 우선.
   캐시 버전을 올리면 기존 캐시가 전부 폐기된다. 코드 변경 시 CACHE 값을 올릴 것. */
const CACHE = 'pharmacy-map-v3';
const SHELL = [
  './',
  './index.html',
  './css/style.css',
  './js/app.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  // 새 SW를 즉시 활성화(기존 SW 대기 없이)
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // 지도 타일/외부 라이브러리: 캐시 우선(성능)
  if (url.hostname.includes('basemaps.cartocdn.com') || url.hostname.includes('unpkg.com')) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => hit))
    );
    return;
  }

  // 그 외 모든 동일 출처 자원(HTML/CSS/JS/JSON): 네트워크 우선, 실패 시 캐시 폴백
  e.respondWith(
    fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || caches.match('./index.html')))
  );
});
