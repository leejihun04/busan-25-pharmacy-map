/* 자폭 Service Worker.
   과거 버전 SW가 코드를 캐시해 갱신을 막는 문제가 있어 SW 사용을 중단한다.
   이미 설치된 SW가 이 파일을 받으면 모든 캐시를 비우고 스스로 등록 해제한다. */
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: 'window' });
    clients.forEach((c) => c.navigate(c.url));
  })());
});

// 캐시 개입 없이 항상 네트워크로 통과
self.addEventListener('fetch', () => {});
