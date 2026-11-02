"""동백전(지역사랑상품권) 부산 가맹점 수집기 — 두 소스 통합.

소스 2개를 모두 수집하여 web/data/dongbaek.json 으로 통합한다.

  1) KOMSCO : 한국조폐공사 "지역사랑상품권 가맹점"(국가중점, 위경도 포함)
               → 좌표 기반 매칭의 주 소스
  2) BUSAN  : 부산광역시 "동백전 가맹점 현황"(가맹점명/도로명주소, 좌표 없음)
               → 주소 기반 교차검증 보조 소스

사용:
    export DATA_GO_KR_KEY="발급키"          # 조폐공사 오픈API 인증키
    # (1) 조폐공사 엔드포인트 — 먼저 diagnose_dongbaek.py 로 오퍼레이션명 확인 후:
    export KOMSCO_API_URL="https://apis.data.go.kr/B190001/cardFranchisesV4/<오퍼레이션>"
    # (2) 부산시 동백전 — 오픈API 없음. data.go.kr 에서 CSV 내려받아 경로 지정:
    export BUSAN_CSV_PATH="/path/to/busan_dongbaek.csv"
    python3 collect_dongbaek.py

어느 소스든 실패/미설정이면 그 소스만 비우고 계속 진행한다(merge 는 가능한 소스로 동작).
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import config as C

_CTX = ssl.create_default_context()

# 응답 레코드에서 값을 꺼낼 때 시도할 후보 필드명.
# 조폐공사 cardV4 검증 필드: frcs_nm, frcs_addr, frcs_dtl_addr, lat, lot,
#   ksic_cd, ksic_cd_nm, bzmn_stts_nm, usage_rgn_cd, emd_cd, emd_nm, pvsn_inst_cd
FIELD_CANDIDATES = {
    "name":    ["frcs_nm", "frcsNm", "가맹점명", "storNm", "bizNm", "card_frcs_nm"],
    "addr":    ["frcs_addr", "adongRoadNmAddr", "lnmAddr", "roadNmAddr", "주소", "addr"],
    "addr2":   ["frcs_dtl_addr", "상세주소", "detailAddress"],
    "lat":     ["lat", "y", "위도", "latitude", "la"],
    "lng":     ["lot", "lng", "x", "경도", "longitude", "lo"],
    "sido":    ["ctpvNm", "시도", "sidoNm"],
    "sigungu": ["signguNm", "시군구", "emd_nm", "sggNm"],
    "indutype":["ksic_cd_nm", "ksicNm", "induty", "업종", "ksic"],
    "indutype_cd":["ksic_cd", "ksicCd"],
    "status":  ["bzmn_stts_nm", "bzmnSttsNm", "사업자상태", "status"],
    "rgn_cd":  ["usage_rgn_cd", "emd_cd"],
}


def _pick(rec: dict, key: str):
    for cand in FIELD_CANDIDATES[key]:
        if cand in rec and rec[cand] not in (None, ""):
            return rec[cand]
    return None


def _to_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _extract_rows(payload) -> list[dict]:
    """data.go.kr 응답의 다양한 구조에서 레코드 리스트를 꺼낸다."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    # odcloud 형태: {"data":[...], "currentCount":n, "totalCount":N}
    if isinstance(payload.get("data"), list):
        return payload["data"]
    # 표준 형태: {"response":{"body":{"items":{"item":[...]}}}}
    body = (payload.get("response") or {}).get("body") or {}
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item")
    if isinstance(items, list):
        return items
    if isinstance(items, dict):  # 단건
        return [items]
    return []


def _total_count(payload) -> int | None:
    if isinstance(payload, dict):
        for k in ("totalCount", "total_count", "matchCount"):
            if k in payload:
                try:
                    return int(payload[k])
                except (TypeError, ValueError):
                    pass
        body = (payload.get("response") or {}).get("body") or {}
        if "totalCount" in body:
            try:
                return int(body["totalCount"])
            except (TypeError, ValueError):
                pass
    return None


def _fetch_page(url, key, page, size, page_param, size_param, region_extra="") -> tuple[list[dict], int | None]:
    params = {
        "serviceKey": key,
        page_param: page,
        size_param: size,
        "returnType": "json",
        "type": "json",  # 일부 API 는 type 파라미터 사용(무시돼도 무해)
    }
    qs = urllib.parse.urlencode(params, safe="%")
    if region_extra:
        qs += "&" + region_extra
    full = url + "?" + qs
    req = urllib.request.Request(full, headers={"Accept": "application/json", "User-Agent": "collector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_CTX) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200]!r}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON 아님(스펙 불일치 가능): {raw[:200]!r}")
    return _extract_rows(payload), _total_count(payload)


def _region_match(rec: dict) -> bool:
    region = C.DONGBAEK_REGION
    if not region:
        return True
    sido = str(_pick(rec, "sido") or "")
    addr = str(_pick(rec, "addr") or "")
    return region in sido or region in addr


def _collect_komsco() -> dict:
    """조폐공사 카드 가맹점 API 수집 (위경도 포함).

    cond[emd_cd::GTE]=26000000 & cond[emd_cd::LT]=27000000 로 부산만 서버필터.
    totalCount 는 전체값이라 신뢰 불가 → 빈 페이지가 나올 때까지 페이징.
    """
    name = "KOMSCO"
    key = C.KOMSCO_KEY
    url = C.KOMSCO_API_URL
    if not key:
        print(f"[{name}] 인증키 미설정 → 건너뜀", file=sys.stderr)
        return {"enabled": False, "reason": "no_key", "merchants": []}
    if not url:
        print(f"[{name}] API URL 미설정 → 건너뜀", file=sys.stderr)
        return {"enabled": False, "reason": "no_url", "merchants": []}

    # 부산 법정동코드 범위 서버필터 (emd_cd 8자리: 26000000~26999999)
    sido = C.KOMSCO_REGION_SIDO
    lo = f"{sido}000000"
    hi = f"{int(sido)+1:02d}000000"
    region_extra = (
        f"cond%5Bemd_cd%3A%3AGTE%5D={lo}&cond%5Bemd_cd%3A%3ALT%5D={hi}"
    )

    merchants: list[dict] = []

    def fetch_one(page):
        try:
            rows, _ = _fetch_page(url, key, page, C.KOMSCO_PAGE_SIZE,
                                  C.KOMSCO_PAGE_PARAM, C.KOMSCO_SIZE_PARAM, region_extra)
            return page, rows
        except Exception as e:
            return page, e

    # 1페이지 먼저 받아 동작 확인
    p1, rows1 = fetch_one(1)
    if isinstance(rows1, Exception):
        return {"enabled": False, "reason": "fetch_error", "error": str(rows1), "merchants": []}
    if not rows1:
        return {"enabled": True, "count": 0, "coordsCount": 0, "pharmacyCount": 0, "merchants": []}

    from concurrent.futures import ThreadPoolExecutor
    page_rows = {1: rows1}
    next_page = 2
    stop = False
    # 빈 페이지가 나올 때까지 배치(동시성 크기)로 병렬 요청
    while not stop:
        batch = list(range(next_page, next_page + C.KOMSCO_CONCURRENCY))
        with ThreadPoolExecutor(max_workers=C.KOMSCO_CONCURRENCY) as ex:
            results = list(ex.map(fetch_one, batch))
        for pg, rows in results:
            if isinstance(rows, Exception):
                continue
            if not rows:
                stop = True
            else:
                page_rows[pg] = rows
                if len(rows) < C.KOMSCO_PAGE_SIZE:
                    stop = True
        next_page += C.KOMSCO_CONCURRENCY
        print(f"[{name}] ~{next_page-1}페이지까지 수집(누적 페이지 {len(page_rows)})")
        if next_page > 2000:  # 안전장치
            break

    for pg in sorted(page_rows):
        for rec in page_rows[pg]:
            m = _normalize(rec, name)
            if m["status"] and "폐업" in str(m["status"]):
                continue
            merchants.append(m)

    coord_n = sum(1 for m in merchants if m["lat"] and m["lng"])
    pharm_n = sum(1 for m in merchants if "약국" in (m.get("name") or ""))
    print(f"[{name}] 완료: {len(merchants)}곳 (좌표보유 {coord_n}, 약국 {pharm_n})")
    return {"enabled": True, "count": len(merchants), "coordsCount": coord_n,
            "pharmacyCount": pharm_n, "merchants": merchants}


def _collect_busan_csv() -> dict:
    """부산시 동백전 가맹점 CSV 수집 (오픈API 없음 → CSV 파일데이터).

    BUSAN_CSV_PATH(로컬) 또는 BUSAN_CSV_URL(다운로드) 로 CSV 를 읽는다.
    컬럼 예: 가맹점명, 도로명주소, 데이터기준일자 (좌표 없음).
    """
    name = "BUSAN"
    path = C.BUSAN_CSV_PATH
    raw_bytes = None

    if path and os.path.exists(path):
        raw_bytes = open(path, "rb").read()
    elif C.BUSAN_CSV_URL:
        try:
            req = urllib.request.Request(C.BUSAN_CSV_URL, headers={"User-Agent": "collector/1.0"})
            with urllib.request.urlopen(req, timeout=60, context=_CTX) as r:
                raw_bytes = r.read()
        except Exception as e:
            print(f"[{name}] CSV 다운로드 실패: {e}", file=sys.stderr)
            return {"enabled": False, "reason": "download_error", "merchants": []}
    else:
        print(f"[{name}] BUSAN_CSV_PATH/URL 미설정 → 건너뜀", file=sys.stderr)
        return {"enabled": False, "reason": "no_csv", "merchants": []}

    # 인코딩 자동 판별(한국 공공 CSV 는 EUC-KR/CP949 가 흔함)
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        print(f"[{name}] CSV 인코딩 판별 실패", file=sys.stderr)
        return {"enabled": False, "reason": "encoding_error", "merchants": []}

    import csv, io
    reader = csv.DictReader(io.StringIO(text))
    cols = reader.fieldnames or []

    def find_col(cands):
        for c in cols:
            cl = c.replace(" ", "")
            for cand in cands:
                if cand in cl:
                    return c
        return None

    col_name = find_col(["가맹점명", "상호", "업체명", "점포명"])
    col_addr = find_col(["도로명주소", "주소", "소재지"])
    print(f"[{name}] CSV 컬럼: {cols} → name={col_name}, addr={col_addr}")

    merchants = []
    for row in reader:
        nm = (row.get(col_name) if col_name else None) or None
        ad = (row.get(col_addr) if col_addr else None) or None
        if not nm:
            continue
        if C.DONGBAEK_REGION not in str(ad or "") and C.DONGBAEK_REGION not in (nm or ""):
            # 부산시 데이터면 전부 부산이지만, 혹시 몰라 느슨히 통과
            pass
        merchants.append({
            "name": nm, "address": ad, "lat": None, "lng": None,
            "sigungu": None, "indutype": None, "status": None, "_src": name,
        })
    print(f"[{name}] 완료: {len(merchants)}곳 (CSV, 좌표 없음)")
    return {"enabled": True, "count": len(merchants), "coordsCount": 0, "merchants": merchants}


def _normalize(rec: dict, src: str) -> dict:
    addr = _pick(rec, "addr")
    addr2 = _pick(rec, "addr2")
    full_addr = " ".join(x for x in [addr, addr2] if x) or None
    return {
        "name": _pick(rec, "name"),
        "address": full_addr,
        "lat": _to_float(_pick(rec, "lat")),
        "lng": _to_float(_pick(rec, "lng")),
        "sigungu": _pick(rec, "sigungu"),
        "indutype": _pick(rec, "indutype"),
        "indutypeCd": _pick(rec, "indutype_cd"),
        "status": _pick(rec, "status"),
        "rgnCd": _pick(rec, "rgn_cd"),
        "_src": src,
    }


def collect() -> dict:
    komsco = _collect_komsco()
    busan = _collect_busan_csv()

    # 원시 소스 저장(디버깅/교차검증용)
    C.KOMSCO_OUT.write_text(json.dumps(komsco, ensure_ascii=False, indent=2), encoding="utf-8")
    C.BUSAN_OUT.write_text(json.dumps(busan, ensure_ascii=False, indent=2), encoding="utf-8")

    merged = list(komsco.get("merchants", [])) + list(busan.get("merchants", []))
    enabled = komsco.get("enabled") or busan.get("enabled")
    return {
        "source": "data.go.kr (KOMSCO + Busan)",
        "enabled": enabled,
        "collectedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "region": C.DONGBAEK_REGION,
        "sources": {
            "komsco": {k: komsco.get(k) for k in ("enabled", "reason", "count", "coordsCount")},
            "busan": {k: busan.get(k) for k in ("enabled", "reason", "count", "coordsCount")},
        },
        "count": len(merged),
        "merchants": merged,
    }


def main() -> None:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = collect()
    C.DONGBAEK_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    s = result["sources"]
    print(
        f"\n통합 완료: 동백전 가맹점 {result['count']}곳"
        f" (조폐공사 {s['komsco'].get('count') or 0} / 부산시 {s['busan'].get('count') or 0})"
        f"\n→ {C.DONGBAEK_OUT}"
    )
    if not result["enabled"]:
        print("※ 두 소스 모두 비활성입니다. KOMSCO_API_URL/BUSAN_API_URL 과 키를 확인하세요.", file=sys.stderr)


if __name__ == "__main__":
    main()
