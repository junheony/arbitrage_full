#!/bin/bash
# Cloudflare Pages 배포 스크립트

set -e  # Exit on error

echo "🚀 Cloudflare Pages 배포 시작..."

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "⚠️  Wrangler가 설치되어 있지 않습니다. 설치 중..."
    npm install -g wrangler
fi

# Check if user is logged in
if ! wrangler whoami &> /dev/null; then
    echo "🔐 Cloudflare 로그인이 필요합니다..."
    wrangler login
fi

# Build the frontend
echo "🔨 프론트엔드 빌드 중..."
npm install
npm run build

# Deploy to Cloudflare Pages
echo "📦 Cloudflare Pages에 배포 중..."
PROJECT_NAME=${1:-arbitrage-frontend}
wrangler pages deploy dist --project-name=$PROJECT_NAME

echo "✅ 배포 완료!"
echo "📝 프로젝트명: $PROJECT_NAME"
echo ""
echo "다음 단계:"
echo "1. Cloudflare 대시보드에서 배포된 URL 확인"
echo "2. 환경 변수 설정 (VITE_API_HTTP_BASE, VITE_API_WS_BASE)"
echo "3. 백엔드 URL 업데이트 후 재배포"
