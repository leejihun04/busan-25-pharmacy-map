/* 부산 25% 약국 지도 — 프론트 로직 (Leaflet, 바닐라 JS) */
(() => {
  'use strict';

  const SEOMYEON = { lat: 35.1577, lng: 129.0594 }; // 기본 중심(서면)
  const CONSENT_KEY = 'geo_consent_v1';
  const state = {
    all: [],          // 전체 약국
    view: [],         // 현재 필터/정렬 결과
    filter: 'all',
    query: '',
    me: null,         // {lat,lng}
    markers: new Map(),
    selected: null,
  };

  const $ = (s) => document.querySelector(s);
  const map = L.map('map', { zoomControl: false, attributionControl: true })
    .setView([SEOMYEON.lat, SEOMYEON.lng], 15);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap &copy; CARTO | 데이터: 네이버페이 페이스사인·부산 동백전(비공식)',
  }).addTo(map);

  const markerLayer = L.layerGroup().addTo(map);
  const meLayer = L.layerGroup().addTo(map);   // 내 위치 전용(약국 마커 갱신과 분리)

  /* ---------- 유틸 ---------- */
  const toast = (msg, ms = 2600) => {
    const t = $('#toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
  };
  const haversine = (a, b) => {
    if (!a || !b) return Infinity;
    const R = 6371000, r = Math.PI / 180;
    const dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
    const s = Math.sin(dLat/2)**2 + Math.cos(a.lat*r)*Math.cos(b.lat*r)*Math.sin(dLng/2)**2;
    return 2 * R * Math.asin(Math.sqrt(s));
  };
  const fmtDist = (m) => m === Infinity ? '' : (m < 1000 ? `${Math.round(m)}m` : `${(m/1000).toFixed(1)}km`);
  const esc = (s) => (s||'').replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  const dbTag = (p) => {
    if (p.facesign && p.dongbaek === true) {
      const cross = p.crossVerified
        ? '<span class="tag verified" title="조폐공사 공공데이터 + 부산시 동백전 명단 양쪽에서 확인">✓ 교차검증</span>'
        : '';
      return '<span class="tag both">25% 가능</span>' + cross;
    }
    const face = '<span class="tag face">페이스사인 10%</span>';
    let db;
    if (p.dongbaek === true) db = '<span class="tag db-yes">동백전 가맹</span>';
    else if (p.dongbaek === false) db = '<span class="tag db-no">동백전 미확인</span>';
    else db = '<span class="tag db-unknown">동백전 직접확인</span>';
    return face + db;
  };

  /* ---------- 데이터 로드 ---------- */
  async function load() {
    try {
      const res = await fetch('data/pharmacies.json', { cache: 'no-cache' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      state.all = (data.pharmacies || []).filter((p) => p.lat && p.lng);
      state.meta = data;
      buildInfoBody(data);
      refresh();
      toast(`약국 ${state.all.length}곳 불러옴`);
    } catch (e) {
      toast('데이터를 불러오지 못했습니다. 수집을 먼저 실행하세요.');
      console.error(e);
    }
  }

  /* ---------- 필터 + 정렬 ---------- */
  function computeView() {
    let list = state.all.slice();
    if (state.query) {
      const q = state.query.trim().toLowerCase();
      list = list.filter((p) =>
        (p.name||'').toLowerCase().includes(q) || (p.address||'').toLowerCase().includes(q));
    }
    if (state.filter === 'both') list = list.filter((p) => p.dongbaek === true);
    // 거리 계산
    const origin = state.me || SEOMYEON;
    list.forEach((p) => { p._d = haversine(origin, p); });
    if (state.filter === 'near') list = list.filter((p) => p._d <= 1500);
    list.sort((a, b) => a._d - b._d);
    state.view = list;
  }

  function refresh() {
    computeView();
    renderMarkers();
    renderList();
  }

  /* ---------- 마커 ---------- */
  function makeIcon(p) {
    const cls = (p.dongbaek === true) ? 'both' : 'face';
    const label = (p.dongbaek === true) ? '25' : '약';
    return L.divIcon({
      className: '', html: `<div class="pin ${cls}"><b>${label}</b></div>`,
      iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -28],
    });
  }
  function renderMarkers() {
    markerLayer.clearLayers();
    state.markers.clear();
    state.view.forEach((p) => {
      const m = L.marker([p.lat, p.lng], { icon: makeIcon(p) }).addTo(markerLayer);
      m.on('click', () => showDetail(p));
      state.markers.set(p.placeId, m);
    });
  }

  /* ---------- 목록 ---------- */
  function renderList() {
    const el = $('#list');
    $('#sheetCount').textContent = `${state.view.length}곳`;
    if (!state.view.length) {
      el.innerHTML = `<div class="empty">조건에 맞는 약국이 없습니다.<br>필터나 검색어를 바꿔보세요.</div>`;
      return;
    }
    el.innerHTML = state.view.slice(0, 200).map((p) => `
      <button class="card" data-id="${p.placeId}" role="listitem">
        <div class="row1">
          <span class="name">${esc(p.name)}</span>
          <span class="dist">${fmtDist(p._d)}</span>
        </div>
        <div class="addr">${esc(p.address)}</div>
        <div class="tags">${dbTag(p)}</div>
      </button>`).join('');
    el.querySelectorAll('.card').forEach((c) => {
      c.addEventListener('click', () => {
        const p = state.all.find((x) => String(x.placeId) === c.dataset.id);
        if (p) showDetail(p);
      });
    });
  }

  /* ---------- 상세 ---------- */
  function showDetail(p) {
    state.selected = p;
    map.setView([p.lat, p.lng], Math.max(map.getZoom(), 16), { animate: true });
    const mk = state.markers.get(p.placeId);
    if (mk) mk.openPopup?.();

    const el = $('#list');
    const reportUrl = buildReportUrl(p);
    el.innerHTML = `
      <div class="detail">
        <div class="dname">${esc(p.name)}</div>
        <div class="daddr">${esc(p.address)}</div>
        <div class="tags" style="margin-top:12px">${dbTag(p)}</div>
        <div class="dactions">
          <a class="nav" href="${p.naverUrl || ('https://map.naver.com/p/search/' + encodeURIComponent(p.name))}" target="_blank" rel="noopener">네이버 지도에서 보기</a>
          <a class="report" href="${reportUrl}" target="_blank" rel="noopener">정보 제보</a>
        </div>
        ${detailNote(p)}
      </div>`;
    $('#sheetTitle').textContent = '약국 상세';
    $('#sheetBack').hidden = false;
    expandSheet(true);
  }

  function detailNote(p) {
    if (p.dongbaek === true) {
      const srcTxt = (p.dongbaekSources || []).map((s) => s === 'KOMSCO' ? '조폐공사 공공데이터' : (s === 'BUSAN' ? '부산시 동백전 명단' : s)).join(' + ');
      const cross = p.crossVerified
        ? `두 개의 독립 출처(${srcTxt})에서 모두 동백전 가맹으로 확인된 매장입니다.`
        : `동백전 가맹으로 확인된 매장입니다(출처: ${srcTxt}).`;
      return `<div class="note">${cross} 페이스사인 가맹도 확인됨. 적립률·중복 여부는 결제 시점 정책에 따라 다를 수 있으니 매장에서 확인하세요.</div>`;
    }
    if (p.dongbaek === null)
      return `<div class="note">페이스사인 가맹은 확인되었으나 동백전 가맹 여부는 자동 확인되지 않았습니다. 동백전 앱의 가맹점 조회 또는 매장 내 스티커로 확인하세요.</div>`;
    return `<div class="note">페이스사인 가맹 매장입니다. 동백전 가맹으로는 매칭되지 않았습니다. 변동 가능하니 매장에서 확인하세요.</div>`;
  }

  function buildReportUrl(p) {
    const subject = encodeURIComponent(`[약국지도 제보] ${p.name}`);
    const body = encodeURIComponent(
      `매장명: ${p.name}\n주소: ${p.address}\nplaceId: ${p.placeId}\n\n(정정/제보 내용을 적어주세요: 폐업/동백전 가맹 여부/페이스사인 미지원 등)`);
    return `mailto:?subject=${subject}&body=${body}`;
  }

  /* ---------- 시트 드래그 ---------- */
  function expandSheet(on) {
    $('#sheet').classList.toggle('expanded', !!on);
  }
  (() => {
    const grip = $('#sheetGrip'); let startY = 0, expanded = false;
    const sheet = $('#sheet');
    grip.addEventListener('pointerdown', (e) => { startY = e.clientY; expanded = sheet.classList.contains('expanded'); grip.setPointerCapture(e.pointerId); });
    grip.addEventListener('pointerup', (e) => {
      const dy = e.clientY - startY;
      if (dy < -40) expandSheet(true);
      else if (dy > 40) expandSheet(false);
      else expandSheet(!expanded);
    });
  })();

  /* ---------- 위치 동의 & GPS ---------- */
  function openConsent() { $('#consent').hidden = false; }
  function closeConsent() { $('#consent').hidden = true; }

  function requestGeo() {
    if (!navigator.geolocation) { toast('이 브라우저는 위치를 지원하지 않습니다.'); return; }
    toast('위치 확인 중...');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        state.me = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        meLayer.clearLayers();
        L.circleMarker([state.me.lat, state.me.lng], { radius: 8, color: '#fff', fillColor: '#1a73e8', fillOpacity: 1, weight: 3 })
          .addTo(meLayer).bindTooltip('내 위치');
        map.setView([state.me.lat, state.me.lng], 16, { animate: true });
        refresh();
        toast('내 위치를 찾았습니다.');
      },
      (err) => {
        const msg = { 1: '위치 권한이 거부되었습니다. 브라우저 설정에서 허용해 주세요.',
                      2: '위치를 확인할 수 없습니다(신호 없음).',
                      3: '위치 확인 시간이 초과됐습니다. 다시 시도해 주세요.' }[err.code] || err.message;
        toast(msg, 4000);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  }

  function handleLocateClick() {
    const consent = localStorage.getItem(CONSENT_KEY);
    if (consent === 'granted') { requestGeo(); return; }
    if (consent === 'denied') { openConsent(); return; }
    openConsent();
  }

  /* ---------- 안내/면책 본문 ---------- */
  function buildInfoBody(data) {
    const sync = data.facesignSyncYmdt || '-';
    const gen = data.generatedAt || '-';
    const dbOn = data.dongbaekEnabled;
    const both = data.counts?.both25;
    $('#infoBody').innerHTML = `
      <p>${esc(data.disclaimer || '비공식 서비스입니다. 결제 전 매장에 직접 확인하세요.')}</p>
      <h3>데이터 최신성</h3>
      <p>페이스사인 동기화: <code>${esc(sync)}</code><br>
         데이터 생성: <code>${esc(gen)}</code><br>
         동백전 매칭: <code>${dbOn ? ('활성 · 25% 가능 ' + (both ?? '-') + '곳 / 교차검증 ' + (data.counts?.crossVerified ?? '-') + '곳') : '미활성(직접 확인 모드)'}</code></p>
      <h3>신뢰성: 교차검증</h3>
      <p>25% 가능 약국은 <b>한국조폐공사 공공데이터</b>(위경도 포함)와 <b>부산시 동백전 가맹점 명단</b> 두 출처로 대조합니다. 두 곳 모두에서 확인되면 <b>✓ 교차검증</b> 배지를 표시합니다.</p>
      <h3>25% 적립 원리</h3>
      <p>동백전(부산 지역화폐, 최대 15%) 카드를 네이버페이에 등록한 뒤, 페이스사인 가맹 약국에서 페이스사인으로 결제하면 두 적립을 함께 받는 구조입니다. 적립률·중복 가능 여부는 각 사업자 정책에 따라 변동될 수 있습니다.</p>
      <h3>후기 기반 아이디어</h3>
      <p>실제 사용자가 동백전+페이스사인 중복 적립으로 구매한 후기를 바탕으로 만들어졌습니다. 다만 개별 매장·시점에 따라 결과가 다를 수 있으니 참고용으로만 사용하세요.</p>
      <h3>개인정보</h3>
      <p>위치정보는 단말기 내에서만 사용하며 서버로 전송하지 않습니다.</p>`;
  }

  /* ---------- 이벤트 바인딩 ---------- */
  $('#q').addEventListener('input', (e) => {
    state.query = e.target.value;
    $('#qClear').hidden = !state.query;
    $('#sheetBack').hidden = true; $('#sheetTitle').textContent = '주변 약국';
    refresh();
  });
  $('#qClear').addEventListener('click', () => { $('#q').value=''; state.query=''; $('#qClear').hidden=true; refresh(); });

  document.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const f = chip.dataset.filter;
      if (f === 'near' && !state.me) { handleLocateClick(); }
      document.querySelectorAll('.chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      state.filter = f;
      $('#sheetBack').hidden = true; $('#sheetTitle').textContent = '주변 약국';
      refresh();
    });
  });

  $('#locate').addEventListener('click', handleLocateClick);
  $('#sheetBack').addEventListener('click', () => {
    state.selected = null; $('#sheetBack').hidden = true; $('#sheetTitle').textContent = '주변 약국'; renderList();
  });

  // 동의 모달
  $('#consentAgree').addEventListener('change', (e) => { $('#consentOk').disabled = !e.target.checked; });
  $('#consentOk').addEventListener('click', () => { localStorage.setItem(CONSENT_KEY,'granted'); closeConsent(); requestGeo(); });
  $('#consentDeny').addEventListener('click', () => { localStorage.setItem(CONSENT_KEY,'denied'); closeConsent(); toast('수동 탐색 모드입니다. 지도를 움직여 찾아보세요.'); });

  // 정보 모달
  $('#infoBtn').addEventListener('click', () => { $('#info').hidden = false; });
  $('#infoClose').addEventListener('click', () => { $('#info').hidden = true; });
  document.querySelectorAll('.modal').forEach((m) => m.addEventListener('click', (e) => { if (e.target === m) m.hidden = true; }));

  // PWA service worker
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(()=>{}));
  }

  load();
})();
