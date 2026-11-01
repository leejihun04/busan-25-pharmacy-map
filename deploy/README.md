# 배포 가이드 (AWS S3 + CloudFront)

도메인 구매 없이 **CloudFront 기본 HTTPS URL**(`https://xxxx.cloudfront.net`)로 공개합니다.
HTTPS라서 모바일 브라우저의 **홈 화면에 추가(PWA 설치)** 가 동작합니다.

## 사전 준비
1. AWS 계정 + AWS CLI 설치
2. 자격증명 설정: `aws configure` (또는 SSO)

## 최초 배포
```bash
cd deploy
./deploy.sh
```
완료되면 출력되는 `https://xxxx.cloudfront.net` 이 바로가기 URL입니다.
(배포 전파에 5~15분 걸릴 수 있습니다.)

## 데이터/코드 갱신 후 재배포
```bash
# 1) 데이터 다시 수집
cd ../collector
python collect_facesign.py
DATA_GO_KR_KEY=... python collect_dongbaek.py   # 동백전 매칭 시
python merge.py
# 2) 업로드 + 캐시 무효화
cd ../deploy
./deploy.sh --sync-only
```

## 비용
- S3 저장/요청 + CloudFront 전송: 소규모 트래픽이면 월 **수백 원~수천 원** 수준(프리티어 적용 시 더 낮음).
- Google AdSense 수익으로 충당하는 것이 목표.

## 자동 갱신(선택)
데이터 최신성을 위해 수집→업로드를 주기적으로 돌리려면:
- 로컬/서버 cron 으로 위 "재배포" 2단계를 매일 실행, 또는
- AWS Lambda + EventBridge(cron) 로 수집 후 S3 업로드 + CloudFront invalidation.

## 홈 화면 저장 안내 (사용자용)
- iOS Safari: 공유 → "홈 화면에 추가"
- Android Chrome: 메뉴 → "앱 설치" 또는 "홈 화면에 추가"
