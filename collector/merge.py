"""페이스사인 약국 ∩ 동백전 가맹점 매칭 → web/data/pharmacies.json 생성.

- 페이스사인 약국이 base.
- 동백전 데이터가 있으면 주소/좌표로 매칭하여 dongbaek=True 표시(=25% 가능 후보).
- 동백전 데이터가 없으면(키 미발급) 전부 dongbaek=None(미확인) 으로 두고 fallback 안내.
"""
from __future__ import annotations

import json
import math
import re
import time

import config as C


def _norm_addr(a: str | None) -> str:
    if not a:
        return ""
    a = re.sub(r"\s+", " ", a).strip()
    # 상세(층/호/건물명) 제거하여 도로명+번지 수준으로 정규화
    a = re.sub(r"\s*\d+층.*$", "", a)
    a = re.sub(r"\s*지하\d+.*$", "", a)
    a = re.sub(r"\s*\d+호.*$", "", a)
    # 시도 접두 통일: '부산광역시' → '부산'
    a = a.replace("부산광역시", "부산")
    return a.strip()


def _addr_key(a: str) -> str:
    """도로명 + 건물번호까지만 남긴 매칭 키 (예: '부산 부산진구 중앙대로 733')."""
    a = _norm_addr(a)
    m = re.match(r"^(.*?\S+(?:로|길)\s*\d+(?:-\d+)?)", a)
    return m.group(1) if m else a


def _haversine(a_lat, a_lng, b_lat, b_lng) -> float:
    if None in (a_lat, a_lng, b_lat, b_lng):
        return float("inf")
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _load(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _load_drugs() -> dict:
    """약국별 비만약 취급정보 (drugs.json) 로드 → {placeId(str): {drugs, checkedAt}}."""
    d = _load(C.DATA_DIR / "drugs.json")
    return (d or {}).get("byPlaceId", {})


def _match_dongbaek(pharm: dict, db_coord: list[dict], db_addr_index: dict) -> dict | None:
    """좌표 근접(<=60m, 조폐공사) 또는 도로명주소 키 일치(부산시 포함)로 매칭.

    반환: 매칭된 가맹점 레코드(+ _matchBy, _crossVerified) 또는 None.
    _crossVerified: 좌표(조폐공사)와 주소(부산시 등) 양쪽 모두에서 확인되면 True.
    """
    coord_hit = None
    coord_d = 60.0
    for m in db_coord:
        d = _haversine(pharm.get("lat"), pharm.get("lng"), m.get("lat"), m.get("lng"))
        if d <= coord_d:
            coord_d, coord_hit = d, m

    key = _addr_key(pharm.get("address") or "")
    addr_hit = db_addr_index.get(key) if key else None

    if coord_hit:
        cross = bool(addr_hit)  # 좌표+주소 둘 다 잡히면 교차검증
        return {**coord_hit, "_matchBy": "coord", "_matchDistM": round(coord_d, 1),
                "_crossVerified": cross,
                "_sources": sorted({coord_hit.get("_src"), addr_hit.get("_src")} if addr_hit else {coord_hit.get("_src")})}
    if addr_hit:
        return {**addr_hit, "_matchBy": "addr", "_crossVerified": False,
                "_sources": [addr_hit.get("_src")]}
    return None


def merge() -> dict:
    fs = _load(C.FACESIGN_OUT)
    if not fs:
        raise SystemExit("facesign.json 이 없습니다. 먼저 collect_facesign.py 를 실행하세요.")
    db = _load(C.DONGBAEK_OUT)
    db_enabled = bool(db and db.get("enabled"))
    db_merchants = (db or {}).get("merchants", [])
    drugs_idx = _load_drugs()

    # 매칭용 인덱스 구성
    db_coord = [m for m in db_merchants if m.get("lat") and m.get("lng")]
    # 주소 인덱스: 같은 키에 여러 소스가 있으면 부산시(BUSAN)를 우선 보관
    # (교차검증 목적상 좌표=조폐공사와 다른 출처인 부산시 존재 여부가 중요).
    db_addr_index: dict[str, dict] = {}
    for m in db_merchants:
        k = _addr_key(m.get("address") or "")
        if not k:
            continue
        cur = db_addr_index.get(k)
        if cur is None or (cur.get("_src") != "BUSAN" and m.get("_src") == "BUSAN"):
            db_addr_index[k] = m

    out_list = []
    matched = 0
    cross_n = 0
    match_by = {"coord": 0, "addr": 0}
    src_hit = {"KOMSCO": 0, "BUSAN": 0}
    for p in fs.get("pharmacies", []):
        item = {
            "placeId": p.get("placeId"),
            "name": p.get("name"),
            "address": p.get("address"),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "category": p.get("category"),
            "naverUrl": p.get("url"),
            "facesign": True,          # 페이스사인 가맹(수집 기준)
            "dongbaek": None,          # None=미확인, True=가맹확인, False=미매칭
        }
        # 비만치료제 취급 표시(네이버 플레이스 등록 정보 기반)
        di = drugs_idx.get(str(p.get("placeId")))
        if di and di.get("drugs"):
            item["drugs"] = di["drugs"]
            item["drugsCheckedAt"] = di.get("checkedAt")
        if db_enabled:
            m = _match_dongbaek(p, db_coord, db_addr_index)
            if m:
                item["dongbaek"] = True
                item["dongbaekStatus"] = m.get("status")
                item["dongbaekMatchBy"] = m.get("_matchBy")
                item["dongbaekSources"] = m.get("_sources")
                item["crossVerified"] = bool(m.get("_crossVerified"))
                matched += 1
                if item["crossVerified"]:
                    cross_n += 1
                match_by[m.get("_matchBy", "addr")] = match_by.get(m.get("_matchBy", "addr"), 0) + 1
                for s in (m.get("_sources") or []):
                    if s in src_hit:
                        src_hit[s] += 1
            else:
                item["dongbaek"] = False
        out_list.append(item)

    # 25% 가능(양쪽 확인) 우선 정렬
    def rank(it):
        return (0 if it.get("dongbaek") is True else (1 if it.get("dongbaek") is None else 2), it["name"] or "")
    out_list.sort(key=rank)

    result = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "facesignSyncYmdt": fs.get("syncYmdt"),
        "dongbaekEnabled": db_enabled,
        "dongbaekCollectedAt": (db or {}).get("collectedAt") if db_enabled else None,
        "dongbaekSources": (db or {}).get("sources") if db_enabled else None,
        "counts": {
            "pharmacy": len(out_list),
            "both25": matched if db_enabled else None,
            "crossVerified": cross_n if db_enabled else None,
            "withDrugInfo": sum(1 for it in out_list if it.get("drugs")),
            "matchBy": match_by if db_enabled else None,
            "sourceHit": src_hit if db_enabled else None,
        },
        "disclaimer": (
            "비공식 서비스입니다. 적립 중복·적립률·가맹 여부는 매장/정책에 따라 다를 수 있으니 "
            "결제 전 매장에 직접 확인하세요."
        ),
        "pharmacies": out_list,
    }
    return result


def main() -> None:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = merge()
    C.MERGED_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    both = result["counts"]["both25"]
    cross = result["counts"]["crossVerified"]
    print(
        f"완료: 약국 {result['counts']['pharmacy']}곳"
        + (f" / 25% 가능 {both}곳 (교차검증 {cross}곳)" if both is not None else " / 동백전 fallback 모드(미확인)")
        + f"\n→ {C.MERGED_OUT}"
    )


if __name__ == "__main__":
    main()
