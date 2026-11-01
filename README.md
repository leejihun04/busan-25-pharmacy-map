# 부산 25% 약국 지도 (Busan 25% Pharmacy Map)

부산에서 **네이버페이 페이스사인 적립(10%) + 동백전 적립(최대 15%)** 을 동시에 받을 수 있는
약국/의료기관을 지도에서 찾아주는 공개 웹 서비스(PWA)입니다.

> ⚠️ 면책: 본 서비스는 공개된 정보를 모아 제공하는 **비공식** 서비스입니다.
> 적립 중복 가능 여부·적립률·가맹 여부는 매장 상황과 각 사업자(네이버페이/부산시) 정책에 따라
> 달라질 수 있으니, **결제 전 매장에 직접 확인**하세요. 전문의약품 가격은 안내하지 않습니다.

## 어떻게 25%가 되나

- **동백전**: 부산 지역화폐. 연매출 10억 이하 가맹점 기본 10% + 착한가격업소 추가 5% → 최대 15% 적립
- **네이버페이 페이스사인**: 얼굴인식 오프라인 결제. 가맹점에서 결제 시 네이버페이 포인트 적립(프로모션 기준 10%)
- **동백전 카드를 네이버페이에 등록**하고, 페이스사인 가맹점(= 동백전 가맹점이기도 한 약국)에서 결제하면 두 적립을 함께 받는 구조

## 데이터 소스

| 데이터 | 출처 | 갱신 |
|---|---|---|
| 페이스사인 가맹 약국 (좌표/주소/상호) | 네이버페이 페이스사인 가맹점 지도 공개 엔드포인트 | 수집 배치(일 1회 권장) |
| 동백전 가맹 여부 (좌표 포함) | 공공데이터포털 "한국조폐공사_카드_가맹점기본정보"(ID 15108279) | 수집 배치 |
| 동백전 가맹 여부 (교차검증) | 부산광역시 "지역화폐(동백전) 가맹점 현황" CSV | 수집 배치 |
| 교집합(25% 가능 약국) | 위 셋을 좌표(60m)·주소로 매칭, 양쪽 확인 시 교차검증 배지 | 빌드 시 |

동백전은 두 출처로 대조합니다: 조폐공사 공공데이터(좌표 매칭)와 부산시 CSV(주소 매칭).
두 곳 모두에서 확인되면 "✓ 교차검증" 배지를 표시해 신뢰도를 높입니다.
동백전 데이터가 없으면(키/CSV 미설정) 교집합 판정 없이 페이스사인 약국만 표시하는 fallback 모드로 동작합니다.

## 디렉터리 구조

```
map/
├── README.md
├── collector/              # 데이터 수집 (Python)
│   ├── collect_facesign.py  # 페이스사인 약국 수집 (격자 기반)
│   ├── collect_dongbaek.py  # 동백전 가맹점 수집 (공공데이터 API)
│   ├── merge.py             # 교집합 매칭 → web/data/pharmacies.json
│   ├── config.py            # 지역 bbox / 설정
│   └── requirements.txt
├── web/                    # 정적 프론트엔드 (PWA)
│   ├── index.html
│   ├── css/style.css
│   ├── js/app.js
│   ├── manifest.webmanifest
│   ├── sw.js
│   ├── icons/
│   └── data/pharmacies.json # 수집 결과 (배포물)
└── deploy/                 # AWS 배포
    ├── deploy.sh            # S3 + CloudFront 배포 스크립트
    └── README.md
```

## 빠른 시작

```bash
# 1) 데이터 수집 (페이스사인만으로도 동작)
cd collector
pip install -r requirements.txt
python collect_facesign.py            # web/data/facesign.json 생성 (부산만 필터)

# (선택) 동백전 교집합 활성화 — 25% 자동 판정
export DATA_GO_KR_KEY="발급키"         # 조폐공사 오픈API 인증키
export BUSAN_CSV_PATH="/path/부산_동백전.csv"   # 부산시 CSV (교차검증용, 선택)
python collect_dongbaek.py            # web/data/dongbaek.json 생성
python merge.py                       # web/data/pharmacies.json 생성

# 2) 로컬 미리보기
cd ../web
python -m http.server 8080            # http://localhost:8080

# 3) AWS 배포
cd ../deploy
./deploy.sh
```

## 검증된 데이터 소스 스펙

- **조폐공사 카드 가맹점**: `GET https://apis.data.go.kr/B190001/cardFranchisesV4/cardV4`
  - 파라미터: `serviceKey, page, perPage, returnType=JSON`
  - 부산 필터: `cond[emd_cd::GTE]=26000000&cond[emd_cd::LT]=27000000`
  - 응답 필드: `frcs_nm`(상호), `frcs_addr`+`frcs_dtl_addr`(주소), `lat`/`lot`(좌표), `ksic_cd_nm`(업종), `bzmn_stts_nm`(상태)
- **페이스사인**: `GET https://campaign2-api.naver.com/facesignmap/nearby?lat=&lng=&category=의료`
  - 격자점 반복 호출 후 `placeId` 로 dedup (1회 최대 50건·반경 ~400m)

## 환경변수

- `DATA_GO_KR_KEY` : 공공데이터포털 serviceKey (동백전 교집합 활성화 시)
