"""조폐공사 카드 가맹점 API(cardFranchisesV4) 진단 스크립트.

데이터: 한국조폐공사_카드_가맹점기본정보 (data.go.kr ID 15108279)
베이스: https://apis.data.go.kr/B190001/cardFranchisesV4

활용신청 후 발급키로 실행하면, 흔한 오퍼레이션명 후보들을 자동 호출해
status=200 + 레코드가 나오는 조합을 찾아준다.

    export DATA_GO_KR_KEY="발급키(Decoding)"
    python3 diagnose_dongbaek.py

출력에서 '✅' 표시된 URL/필드명을 config.py(KOMSCO_API_URL 등)에 반영하면 된다.
"""
import json, os, ssl, sys, urllib.error, urllib.parse, urllib.request

KEY = (os.environ.get("DATA_GO_KR_KEY") or os.environ.get("KOMSCO_KEY") or "").strip()
if not KEY:
    print("키가 없습니다. export DATA_GO_KR_KEY=... 후 실행하세요.")
    sys.exit(1)

BASE = os.environ.get("KOMSCO_BASE", "https://apis.data.go.kr/B190001/cardFranchisesV4").strip()

# cardFranchisesV4 에서 흔히 쓰이는 오퍼레이션명 후보
OPERATIONS = [
    "getBySigngu",      # 시군구별
    "getByUsageRgn",    # 사용처지역코드별
    "getByBrand",
    "getList",
    "getFranchiseV4",
    "cardFranchiseV4",
    "",                 # 베이스 자체
]
# 부산 지역코드(법정동 시도 2자리=26) 를 받을 수 있는 파라미터 후보
REGION_PARAMS = ["", "divId=zipNo&key=26", "zipNo=26", "usageRgnCd=26", "signguCode=26", "ctpvCd=26"]

ctx = ssl.create_default_context()


def call(url, extra=""):
    params = {"serviceKey": KEY, "pageNo": 1, "numOfRows": 3, "type": "json"}
    qs = urllib.parse.urlencode(params, safe="%")
    if extra:
        qs += "&" + extra
    full = url + "?" + qs
    req = urllib.request.Request(full, headers={"Accept": "application/json", "User-Agent": "diag/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"ERROR: {e}"


def rows_of(raw):
    try:
        j = json.loads(raw)
    except Exception:
        return None, None
    if isinstance(j, dict):
        if isinstance(j.get("data"), list):
            return j["data"], list(j.keys())
        body = (j.get("response") or {}).get("body") or {}
        items = body.get("items")
        if isinstance(items, dict):
            items = items.get("item")
        if isinstance(items, list):
            return items, list(j.keys())
    if isinstance(j, list):
        return j, ["<list>"]
    return None, (list(j.keys()) if isinstance(j, dict) else None)


print(f"BASE={BASE}\n키 길이={len(KEY)}\n" + "=" * 64)
found = []
for op in OPERATIONS:
    url = BASE + ("/" + op if op else "")
    for extra in REGION_PARAMS:
        status, raw = call(url, extra)
        rows, keys = rows_of(raw)
        tag = ""
        if status == 200 and rows:
            tag = " ✅ 레코드 있음"
            found.append((url, extra, rows[0]))
        label = f"{url}" + (f"?{extra}" if extra else "")
        print(f"\n{label}\n  status={status}  rows={len(rows) if rows else 0}  topkeys={keys}{tag}")
        if rows:
            print("  fields:", list(rows[0].keys()))
            print("  sample:", json.dumps(rows[0], ensure_ascii=False)[:500])
            break  # 이 오퍼레이션은 동작 확인됨 → 다음 오퍼레이션으로
        else:
            head = raw[:240].replace("\n", " ")
            print("  body:", head)

print("\n" + "=" * 64)
if found:
    url, extra, sample = found[0]
    print("✅ 동작하는 엔드포인트를 찾았습니다:")
    print(f"   export KOMSCO_API_URL='{url}'")
    if extra:
        print(f"   (지역 파라미터: {extra})")
    print("   응답 필드:", list(sample.keys()))
    print("\n이제 collect_dongbaek.py 를 실행하면 됩니다.")
else:
    print("동작 조합을 못 찾았습니다. 상세페이지의 정확한 오퍼레이션명/파라미터를 알려주세요.")
    print("흔한 원인: (1) 활용신청 승인 전 (2) Encoding/Decoding 키 혼동 (3) 오퍼레이션명 상이")
