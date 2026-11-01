"""네이버페이 페이스사인 가맹 약국 수집기.

페이스사인 가맹점 지도가 사용하는 공개 엔드포인트(/nearby)를 격자(grid)로 훑어
부산 전역의 '의료' 카테고리 매장을 모으고, 상호에 '약국'이 포함된 곳을 약국으로 표시한다.

/nearby 는 1회 최대 50건 + 반경 ~400m 만 반환하므로, 지역을 격자점으로 쪼개
각 점에서 호출하고 placeId 로 중복 제거한다.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from typing import Iterable

import config as C


def _get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    url = f"{C.FACESIGN_BASE}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": C.USER_AGENT,
            "Referer": C.FACESIGN_REFERER,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.load(resp)
    if payload.get("code") != "success":
        raise RuntimeError(f"endpoint {path} returned code={payload.get('code')}")
    return payload.get("data", {})


def fetch_meta() -> dict:
    """카테고리/브랜드 메타 + syncYmdt(동기화 시각)."""
    return _get("/meta", {})


def fetch_nearby(lat: float, lng: float, category: str) -> list[dict]:
    try:
        data = _get("/nearby", {"lat": round(lat, 6), "lng": round(lng, 6), "category": category})
    except Exception as e:  # 개별 격자점 실패는 건너뜀
        print(f"  ! nearby({lat:.4f},{lng:.4f}) 실패: {e}", file=sys.stderr)
        return []
    return data.get("stores", [])


def _grid_points(bbox: tuple[float, float, float, float], step: float) -> Iterable[tuple[float, float]]:
    south, west, north, east = bbox
    lat = south
    while lat <= north + 1e-9:
        lng = west
        while lng <= east + 1e-9:
            yield lat, lng
            lng += step
        lat += step


def collect() -> dict:
    meta = fetch_meta()
    sync_ymdt = meta.get("syncYmdt")
    print(f"페이스사인 동기화 시각(syncYmdt): {sync_ymdt}")

    seen: dict[int, dict] = {}

    # 우선순위 구역을 더 촘촘히 먼저 수집
    regions: list[tuple[str, tuple, float]] = [
        (name, bbox, C.GRID_STEP_PRIORITY) for name, bbox in C.PRIORITY_BBOXES.items()
    ]
    regions.append(("부산전역", C.BUSAN_BBOX, C.GRID_STEP_DEFAULT))

    for name, bbox, step in regions:
        pts = list(_grid_points(bbox, step))
        print(f"[{name}] 격자 {len(pts)}개 수집 중 (step={step})...")
        for i, (lat, lng) in enumerate(pts, 1):
            for s in fetch_nearby(lat, lng, C.MEDICAL_CATEGORY):
                pid = s.get("placeId")
                if pid is not None:
                    # distM 은 격자점 기준이라 저장 의미 없음 → 제거
                    s.pop("distM", None)
                    seen[pid] = s
            time.sleep(C.REQUEST_DELAY)
            if i % 100 == 0:
                print(f"  ...{i}/{len(pts)} (누적 고유 매장 {len(seen)})")

    stores = list(seen.values())

    def _in_region(s: dict) -> bool:
        addr = (s.get("address") or "").strip()
        return any(addr.startswith(p) for p in C.REGION_ADDR_PREFIXES)

    before = len(stores)
    stores = [s for s in stores if _in_region(s)]
    print(f"지역 필터({'/'.join(C.REGION_ADDR_PREFIXES)}): {before} → {len(stores)} (비대상 {before - len(stores)}곳 제외)")

    pharmacies = [s for s in stores if any(k in (s.get("name") or "") for k in C.PHARMACY_KEYWORDS)]

    result = {
        "source": "naver_facesign_map",
        "syncYmdt": sync_ymdt,
        "collectedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "categories": meta.get("categories"),
        "counts": {"medical": len(stores), "pharmacy": len(pharmacies)},
        # 약국만 내보낸다 (병원/한의원 등 의료 전체는 medical_all 로 보관)
        "pharmacies": sorted(pharmacies, key=lambda x: x.get("name", "")),
        "medical_all": sorted(stores, key=lambda x: x.get("name", "")),
    }
    return result


def main() -> None:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = collect()
    C.FACESIGN_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"\n완료: 약국 {result['counts']['pharmacy']}곳 / 의료 전체 {result['counts']['medical']}곳"
        f"\n→ {C.FACESIGN_OUT}"
    )


if __name__ == "__main__":
    main()
