"""수집 공통 설정."""
import os

# --- 페이스사인 가맹점 지도 공개 엔드포인트 ---
FACESIGN_BASE = "https://campaign2-api.naver.com/facesignmap"
FACESIGN_REFERER = "https://campaign2.naver.com/npay/facesignmap/"
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

# 페이스사인 카테고리 중 약국/의료가 속한 분류
MEDICAL_CATEGORY = "의료"

# "약국"으로 간주할 상호 키워드 (의료 카테고리에서 약국만 추릴 때 사용)
PHARMACY_KEYWORDS = ["약국"]

# 수집 결과에서 이 시도(광역시/도)에 속한 주소만 남긴다. 부산 동백전 대상 지역 한정.
# 페이스사인 수집 격자가 부산 경계를 넘어 경남/울산을 포함하므로 주소로 필터링한다.
REGION_ADDR_PREFIXES = ["부산"]

# --- 수집 대상 지역: 부산 전역 bbox ---
# (south, west, north, east)
BUSAN_BBOX = (35.03, 128.80, 35.40, 129.30)

# 우선 순위가 높은 핵심 구(서면=부산진구, 사상구, 남구). 더 촘촘히 수집.
PRIORITY_BBOXES = {
    "부산진구_서면": (35.13, 129.01, 35.19, 129.09),
    "사상구": (35.14, 128.96, 35.21, 129.02),
    "남구": (35.11, 129.07, 35.17, 129.15),
}

# /nearby 는 1회 호출 최대 50건·반경 ~400m 를 반환하므로 격자로 촘촘히 훑는다.
# step(도 단위). 0.01 ≈ 약 900m~1.1km. 밀집지역(우선순위)은 더 작게.
# 부산 전역을 너무 촘촘히 하면 수천 호출이 되므로 전역은 성기게, 상권은 촘촘히.
GRID_STEP_DEFAULT = 0.016
GRID_STEP_PRIORITY = 0.005

REQUEST_DELAY = 0.05  # 호출 간 지연(초) - 서버 예의

# --- 동백전(지역사랑상품권) 공공데이터 ---
# 두 소스를 모두 활용한다:
#   KOMSCO : 한국조폐공사 "지역사랑상품권 가맹점"(국가중점, 위경도 포함) → 좌표 매칭(주)
#   BUSAN  : 부산광역시 "동백전 가맹점 현황"(가맹점명/도로명주소) → 주소 매칭(보조/교차검증)
#
# 인증키는 공용 1개(DATA_GO_KR_KEY)를 쓰되, 소스별로 다르면 *_KEY 로 개별 지정 가능.
# 엔드포인트/파라미터/필드명은 활용신청 후 상세페이지의 실제 스펙으로 env 를 덮어쓸 수 있다.

DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
DONGBAEK_REGION = os.environ.get("DONGBAEK_REGION", "부산").strip()

# 조폐공사(KOMSCO) — 위경도 포함 카드 가맹점
# 데이터: 한국조폐공사_카드_가맹점기본정보 (data.go.kr ID 15108279)
# 검증된 엔드포인트: https://apis.data.go.kr/B190001/cardFranchisesV4/cardV4
#   파라미터: serviceKey, page, perPage, returnType=JSON
#   응답: {currentCount,totalCount,matchCount,page,perPage,data:[...]}
#   필드: frcs_nm(상호), frcs_addr+frcs_dtl_addr(주소), lat/lot(좌표),
#         ksic_cd/ksic_cd_nm(업종), bzmn_stts_nm(사업자상태), usage_rgn_cd(지역코드 10자리)
KOMSCO_KEY = (os.environ.get("KOMSCO_KEY") or DATA_GO_KR_KEY).strip()
KOMSCO_BASE = os.environ.get("KOMSCO_BASE", "https://apis.data.go.kr/B190001/cardFranchisesV4").strip()
KOMSCO_API_URL = os.environ.get("KOMSCO_API_URL", f"{KOMSCO_BASE}/cardV4").strip()
KOMSCO_PAGE_PARAM = os.environ.get("KOMSCO_PAGE_PARAM", "page").strip()
KOMSCO_SIZE_PARAM = os.environ.get("KOMSCO_SIZE_PARAM", "perPage").strip()
KOMSCO_PAGE_SIZE = int(os.environ.get("KOMSCO_PAGE_SIZE", "1000"))
# 부산 지역코드: 법정동 시도코드 2자리 = 26. usage_rgn_cd 앞 2자리로 필터.
KOMSCO_REGION_SIDO = os.environ.get("KOMSCO_REGION_SIDO", "26").strip()
# 약국 업종코드(ksic_cd) 접두: 475 = 기타 상품 전문 소매(의약·의료용품 포함 계열).
# 상호에 '약국'이 들어가면 우선 약국으로 본다(아래 merge 는 페이스사인 약국이 기준이므로
# KOMSCO 는 좌표/주소 매칭용 전체 부산 가맹점을 받으면 충분).

# 부산광역시(BUSAN) — 동백전 가맹점 현황. 오픈API 없이 **CSV 파일데이터**만 제공.
# data.go.kr 파일데이터 상세에서 CSV 를 내려받아 BUSAN_CSV_PATH 로 지정하거나,
# 다운로드 URL 을 BUSAN_CSV_URL 로 지정한다. (가맹점명/도로명주소/기준일자, 좌표 없음)
BUSAN_KEY = (os.environ.get("BUSAN_KEY") or DATA_GO_KR_KEY).strip()
BUSAN_CSV_PATH = os.environ.get("BUSAN_CSV_PATH", "").strip()   # 로컬 CSV 파일 경로
BUSAN_CSV_URL = os.environ.get("BUSAN_CSV_URL", "").strip()     # CSV 직접 다운로드 URL(선택)

# --- 출력 경로 ---
import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "web" / "data"
FACESIGN_OUT = DATA_DIR / "facesign.json"
DONGBAEK_OUT = DATA_DIR / "dongbaek.json"        # 두 소스 통합 결과
KOMSCO_OUT = DATA_DIR / "dongbaek_komsco.json"   # 조폐공사 원시
BUSAN_OUT = DATA_DIR / "dongbaek_busan.json"     # 부산시 원시
MERGED_OUT = DATA_DIR / "pharmacies.json"
