#!/usr/bin/env bash
# 부산 25% 약국 지도 — AWS S3 + CloudFront 배포 스크립트 (도메인 구매 불필요).
#
# 전제: AWS CLI 설치 + 자격증명 설정(aws configure 또는 SSO). jq 설치 권장.
# 결과: https://<배포ID>.cloudfront.net 형태의 HTTPS URL 제공 → 모바일 홈화면 저장 가능.
#
# 사용:
#   cd deploy && ./deploy.sh            # 최초: 버킷/배포 생성 + 업로드
#   ./deploy.sh --sync-only             # 코드만 재업로드 + 캐시 무효화
#
set -euo pipefail

# ---- 설정 (필요 시 수정) ----
REGION="${AWS_REGION:-ap-northeast-2}"           # 서울 리전
BUCKET="${BUCKET:-busan-25-pharmacy-$RANDOM}"    # 전역 고유해야 함
WEB_DIR="$(cd "$(dirname "$0")/../web" && pwd)"
STATE_FILE="$(dirname "$0")/.deploy-state"

command -v aws >/dev/null || { echo "AWS CLI가 필요합니다."; exit 1; }

load_state() { [ -f "$STATE_FILE" ] && . "$STATE_FILE" || true; }
save_state() { printf 'BUCKET=%q\nDIST_ID=%q\nOAC_ID=%q\n' "$BUCKET" "${DIST_ID:-}" "${OAC_ID:-}" > "$STATE_FILE"; }

sync_files() {
  echo "▶ S3 업로드: s3://$BUCKET"
  # 데이터는 짧은 캐시(최신성), 정적 자산은 긴 캐시
  aws s3 sync "$WEB_DIR" "s3://$BUCKET" --delete \
    --exclude "data/*" --exclude "*.webmanifest" --exclude "sw.js" \
    --cache-control "public,max-age=86400"
  aws s3 sync "$WEB_DIR/data" "s3://$BUCKET/data" \
    --cache-control "public,max-age=300,must-revalidate" --content-type "application/json"
  aws s3 cp "$WEB_DIR/manifest.webmanifest" "s3://$BUCKET/manifest.webmanifest" \
    --cache-control "public,max-age=3600" --content-type "application/manifest+json"
  aws s3 cp "$WEB_DIR/sw.js" "s3://$BUCKET/sw.js" \
    --cache-control "no-cache" --content-type "application/javascript"
}

invalidate() {
  [ -n "${DIST_ID:-}" ] || return 0
  echo "▶ CloudFront 캐시 무효화"
  aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" >/dev/null
}

if [ "${1:-}" = "--sync-only" ]; then
  load_state
  [ -n "${BUCKET:-}" ] || { echo "상태파일이 없습니다. 먼저 최초 배포를 실행하세요."; exit 1; }
  sync_files; invalidate
  echo "✅ 재배포 완료"
  exit 0
fi

# ---- 최초 배포 ----
echo "▶ S3 버킷 생성: $BUCKET ($REGION)"
if [ "$REGION" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "$BUCKET" >/dev/null
else
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
fi
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

sync_files

echo "▶ CloudFront Origin Access Control 생성"
OAC_ID=$(aws cloudfront create-origin-access-control --origin-access-control-config \
  "Name=oac-$BUCKET,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3" \
  --query 'OriginAccessControl.Id' --output text)

echo "▶ CloudFront 배포 생성"
DIST_JSON=$(cat <<JSON
{
  "CallerReference": "$BUCKET-$(date +%s)",
  "Comment": "Busan 25% Pharmacy Map",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  "Origins": {"Quantity":1,"Items":[{
    "Id":"s3origin","DomainName":"$BUCKET.s3.$REGION.amazonaws.com",
    "OriginAccessControlId":"$OAC_ID","S3OriginConfig":{"OriginAccessIdentity":""}
  }]},
  "DefaultCacheBehavior": {
    "TargetOriginId":"s3origin","ViewerProtocolPolicy":"redirect-to-https",
    "Compress":true,
    "CachePolicyId":"658327ea-f89d-4fab-a63d-7e88639e58f6",
    "AllowedMethods":{"Quantity":2,"Items":["GET","HEAD"]}
  },
  "CustomErrorResponses":{"Quantity":1,"Items":[{
    "ErrorCode":403,"ResponsePagePath":"/index.html","ResponseCode":"200","ErrorCachingMinTTL":10
  }]},
  "PriceClass":"PriceClass_200"
}
JSON
)
DIST_OUT=$(aws cloudfront create-distribution --distribution-config "$DIST_JSON")
DIST_ID=$(echo "$DIST_OUT" | grep -o '"Id": *"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
DIST_DOMAIN=$(echo "$DIST_OUT" | grep -o '"DomainName": *"[A-Za-z0-9.]*cloudfront.net"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')

echo "▶ S3 버킷 정책(CloudFront OAC만 허용)"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3api put-bucket-policy --bucket "$BUCKET" --policy "$(cat <<JSON
{"Version":"2008-10-17","Statement":[{
  "Sid":"AllowCloudFront","Effect":"Allow",
  "Principal":{"Service":"cloudfront.amazonaws.com"},
  "Action":"s3:GetObject","Resource":"arn:aws:s3:::$BUCKET/*",
  "Condition":{"StringEquals":{"AWS:SourceArn":"arn:aws:cloudfront::$ACCOUNT_ID:distribution/$DIST_ID"}}
}]}
JSON
)"

save_state
echo ""
echo "✅ 배포 생성 완료 (전파에 5~15분 소요)"
echo "   바로가기 URL:  https://$DIST_DOMAIN"
echo "   이후 재배포:   ./deploy.sh --sync-only"
