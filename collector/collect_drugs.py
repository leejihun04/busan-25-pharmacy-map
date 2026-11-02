"""약국별 비만치료제(마운자로/위고비 등) 취급 정보 수집기.

네이버 플레이스 약국 페이지(m.place.naver.com/pharmacy/{placeId}/home)의
window.__APOLLO_STATE__ JSON과 본문에서 비만치료제 키워드를 탐지한다.
약국이 직접 등록한 메뉴/소개/공지에 적힌 품목이라, '취급 안내' 수준의 신뢰도를 가진다.

중요(정직성): 키워드가 없다고 '취급 안 함'은 아니다(등록 안 했을 수 있음).
또 실시간 재고가 아니라 '취급 품목 안내'이므로, 방문 전 전화 확인을 권장한다.

입력:  web/data/pharmacies.json 의 placeId 목록
출력:  web/data/drugs.json  { "<placeId>": {"drugs":[...], "checkedAt":"..."} }
       merge 시 pharmacies.json 에 병합됨.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import config as C

PLACE_URL = "https://m.place.naver.com/{path}/{pid}/home"
UA = C.USER_AGENT
DRUG_REQUEST_DELAY = float(os.environ.get("DRUG_REQUEST_DELAY", "0.8"))  # 네이버 429 회피

# 탐지 대상 비만치료제(GLP-1 등). 표시 표준화를 위해 정식 표기로 매핑.
DRUG_KEYWORDS = {
    "마운자로": "마운자로",
    "위고비": "위고비",
    "삭센다": "삭센다",
    "오젬픽": "오젬픽",
    "리벨서스": "리벨서스",
    "트루리시티": "트루리시티",
    "큐시미아": "큐시미아",
    "제프바운드": "젭바운드",
    "젭바운드": "젭바운드",
}


def fetch_drugs(pid, kind="약국", retries=4) -> tuple[list[str], bool]:
    """반환: (약품목록, ok). ok=False 면 요청 실패(429 등)로 신뢰 불가.
    약국은 pharmacy, 의원/병원은 hospital 경로를 사용한다."""
    path = "pharmacy" if kind == "약국" else "hospital"
    url = PLACE_URL.format(path=path, pid=pid)
    delay = 2.0
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2  # 지수 백오프
                continue
            print(f"  ! {pid} HTTP {e.code}", file=sys.stderr)
            return [], False
        except Exception as e:
            print(f"  ! {pid} 실패: {e}", file=sys.stderr)
            return [], False

        hay = html
        m = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});", html, re.S)
        if m:
            hay = m.group(1)
        found = []
        for kw, canon in DRUG_KEYWORDS.items():
            if kw in hay and canon not in found:
                found.append(canon)
        return found, True
    return [], False


def main() -> None:
    merged = json.loads(C.MERGED_OUT.read_text(encoding="utf-8")) if C.MERGED_OUT.exists() else None
    src = merged or (json.loads(C.FACESIGN_OUT.read_text(encoding="utf-8")))
    pharmacies = src.get("pharmacies", [])
    out_path = C.DATA_DIR / "drugs.json"

    # 이어받기: 기존 결과가 있으면 재사용(이미 확인된 placeId 는 건너뜀)
    prev = {}
    if out_path.exists():
        prev = json.loads(out_path.read_text(encoding="utf-8")).get("byPlaceId", {})
    print(f"대상 약국 {len(pharmacies)}곳 약품 취급정보 수집 (기존 {len(prev)}곳 재사용, delay={DRUG_REQUEST_DELAY}s)...")

    out: dict[str, dict] = dict(prev)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    hit = len(prev)
    done = 0
    for i, p in enumerate(pharmacies, 1):
        pid = p.get("placeId")
        if pid is None:
            continue
        key = str(pid)
        if key in out:  # 이미 취급 표시 확인됨 → 건너뜀
            continue
        drugs, ok = fetch_drugs(pid, p.get("kind", "약국"))
        done += 1
        if not ok:
            continue  # 요청 실패(429 등)는 저장 안 함 → 다음 실행 때 재시도
        # 확인 완료: 약 있으면 drugs 기록, 없으면 빈 목록으로 기록(재조회 방지)
        out[key] = {"drugs": drugs, "checkedAt": now}
        if drugs:
            hit += 1
        if done % 20 == 0:
            print(f"  ...{i}/{len(pharmacies)} (취급표시 {hit}곳 / 확인 {len(out)}곳)")
            _save(out_path, out, now)
        time.sleep(DRUG_REQUEST_DELAY)

    _save(out_path, out, now)
    withdrugs = sum(1 for v in out.values() if v.get("drugs"))
    print(f"완료: 확인 {len(out)}곳 중 비만약 취급 표시 {withdrugs}곳 → {out_path}")


def _save(path, out, now):
    result = {"collectedAt": now, "source": "naver_place_pharmacy", "count": len(out), "byPlaceId": out}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
