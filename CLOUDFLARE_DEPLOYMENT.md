# Cloudflare 배포 가이드

## 개요

이 가이드는 아비트리지 시스템을 Cloudflare에 배포하는 방법을 설명합니다.
- **프론트엔드**: Cloudflare Pages (정적 사이트 호스팅)
- **백엔드**: Railway, Render, 또는 Fly.io (Python/FastAPI 호스팅)

## 1. 프론트엔드 배포 (Cloudflare Pages)

### 1.1 Cloudflare Pages 설정

1. **Cloudflare 계정 생성**
   - https://dash.cloudflare.com 접속
   - 계정 생성 및 로그인

2. **Pages 프로젝트 생성**
   - 대시보드에서 "Pages" 선택
   - "Create a project" 클릭
   - "Connect to Git" 선택하여 GitHub/GitLab 연결
   - 또는 "Direct Upload" 선택하여 수동 배포

### 1.2 빌드 설정

Git 연결을 사용하는 경우:

```yaml
Framework preset: Vite
Build command: npm run build
Build output directory: dist
Root directory: /frontend
```

환경 변수 설정:
```bash
NODE_VERSION=20
VITE_API_HTTP_BASE=https://your-backend-url.com/api
VITE_API_WS_BASE=wss://your-backend-url.com/api/ws
```

### 1.3 로컬에서 빌드 후 수동 배포

```bash
# 프론트엔드 디렉토리로 이동
cd frontend

# 환경 변수 설정
echo "VITE_API_HTTP_BASE=https://your-backend-url.com/api" > .env.production
echo "VITE_API_WS_BASE=wss://your-backend-url.com/api/ws" >> .env.production

# 빌드
npm run build

# Wrangler 설치 (한 번만 실행)
npm install -g wrangler

# Cloudflare 로그인
wrangler login

# Pages에 배포
wrangler pages deploy dist --project-name=arbitrage-frontend
```

### 1.4 자동 배포 설정 (GitHub Actions)

`.github/workflows/deploy-frontend.yml` 파일 생성:

```yaml
name: Deploy Frontend to Cloudflare Pages

on:
  push:
    branches:
      - main
    paths:
      - 'frontend/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        working-directory: ./frontend
        run: npm install

      - name: Build
        working-directory: ./frontend
        env:
          VITE_API_HTTP_BASE: ${{ secrets.VITE_API_HTTP_BASE }}
          VITE_API_WS_BASE: ${{ secrets.VITE_API_WS_BASE }}
        run: npm run build

      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy frontend/dist --project-name=arbitrage-frontend
```

GitHub Secrets 설정:
- `CLOUDFLARE_API_TOKEN`: Cloudflare API 토큰
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare 계정 ID
- `VITE_API_HTTP_BASE`: 백엔드 HTTP URL
- `VITE_API_WS_BASE`: 백엔드 WebSocket URL

---

## 2. 백엔드 배포 (Railway 추천)

Cloudflare Workers는 Python을 지원하지 않으므로, Railway, Render, Fly.io 등을 사용해야 합니다.

### 2.1 Railway 배포 (가장 간단)

1. **Railway 계정 생성**
   - https://railway.app 접속
   - GitHub로 로그인

2. **프로젝트 생성**
   - "New Project" 클릭
   - "Deploy from GitHub repo" 선택
   - 저장소 선택

3. **서비스 설정**

   **PostgreSQL 추가**:
   - "Add Service" → "Database" → "PostgreSQL"
   - 자동으로 `DATABASE_URL` 환경 변수가 생성됨

   **백엔드 서비스 설정**:
   - Root directory: `/backend`
   - Build command: `pip install -e .`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

4. **환경 변수 설정**
   ```bash
   SECRET_KEY=your-secret-key-change-in-production-min-32-chars
   ENVIRONMENT=production
   ENABLE_PUBLIC_REST_SPOT=true
   ENABLE_PERP_CONNECTORS=true
   TETHER_TOTAL_EQUITY_USD=100000
   ```

5. **도메인 확인**
   - Railway가 자동으로 도메인 생성 (예: `arbitrage-backend.up.railway.app`)
   - 이 URL을 프론트엔드 환경 변수에 설정

### 2.2 Render 배포

1. **Render 계정 생성**
   - https://render.com 접속
   - GitHub로 로그인

2. **Web Service 생성**
   - "New" → "Web Service"
   - GitHub 저장소 연결
   - Root Directory: `backend`
   - Build Command: `pip install -e .`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

3. **PostgreSQL 추가**
   - "New" → "PostgreSQL"
   - 데이터베이스 생성 후 `DATABASE_URL` 복사
   - Web Service 환경 변수에 추가

### 2.3 Fly.io 배포

```bash
# Fly CLI 설치
curl -L https://fly.io/install.sh | sh

# 로그인
fly auth login

# 백엔드 디렉토리로 이동
cd backend

# 앱 생성
fly launch --name arbitrage-backend

# 환경 변수 설정
fly secrets set SECRET_KEY=your-secret-key-min-32-chars
fly secrets set ENVIRONMENT=production
fly secrets set ENABLE_PUBLIC_REST_SPOT=true

# PostgreSQL 추가
fly postgres create --name arbitrage-db
fly postgres attach arbitrage-db

# 배포
fly deploy
```

---

## 3. 전체 배포 체크리스트

### 3.1 백엔드 배포 먼저

1. ✅ Railway/Render/Fly.io에 백엔드 배포
2. ✅ PostgreSQL 데이터베이스 연결
3. ✅ 환경 변수 설정
4. ✅ 백엔드 URL 확인 (예: `https://arbitrage-backend.up.railway.app`)

### 3.2 프론트엔드 배포

1. ✅ 백엔드 URL을 프론트엔드 환경 변수에 설정
   ```bash
   VITE_API_HTTP_BASE=https://arbitrage-backend.up.railway.app/api
   VITE_API_WS_BASE=wss://arbitrage-backend.up.railway.app/api/ws
   ```
2. ✅ Cloudflare Pages에 배포
3. ✅ 프론트엔드 URL 확인 (예: `https://arbitrage-frontend.pages.dev`)

### 3.3 테스트

1. ✅ 프론트엔드 접속 확인
2. ✅ 회원가입/로그인 테스트
3. ✅ 김치프리미엄 기회 확인
4. ✅ WebSocket 실시간 업데이트 확인

---

## 4. 김치프리미엄 활성화 확인

김치프리미엄 기능이 이미 활성화되어 있습니다:
- `opportunity_engine.py`에서 `_generate_kimchi_premium()` 활성화됨
- Upbit, Bithumb 커넥터 작동 중
- Tether Bot 곡선 설정 완료

### 급등 코인 추적

현재 56개 메이저 코인을 추적 중입니다. 추가 코인을 추적하려면:

1. `backend/app/core/config.py`의 `trading_symbols` 리스트에 추가
2. 예시:
   ```python
   trading_symbols: list[str] = Field(
       default_factory=lambda: [
           # 기존 코인들...
           "FLUID/USDT",  # 플루이드 추가
           "INTUI/USDT",  # 인튜이션 추가 (정확한 심볼명 확인 필요)
       ],
   )
   ```

**주의**:
- 정확한 심볼명은 Binance, Upbit 등에서 확인 필요
- 한국 거래소에 상장되지 않은 코인은 김치프리미엄 기회가 나타나지 않음

---

## 5. 비용 예상

### Cloudflare Pages
- **무료 플랜**: 500 빌드/월, 무제한 트래픽
- **Pro 플랜**: $20/월

### Railway
- **무료 플랜**: $5 크레딧/월
- **Pro 플랜**: $20/월 + 사용량

### Render
- **무료 플랜**: 가능 (느림, 대기 시간 있음)
- **Starter 플랜**: $7/월

### Fly.io
- **무료 플랜**: 3개 VM, 3GB 스토리지
- **종량제**: 사용량에 따라 과금

**추천**: Railway ($20/월) + Cloudflare Pages (무료) = **총 $20/월**

---

## 6. 보안 체크리스트

- ✅ `SECRET_KEY` 변경 (최소 32자)
- ✅ HTTPS 강제 활성화
- ✅ CORS 설정 확인
- ✅ API 키는 환경 변수로 관리
- ✅ 데이터베이스 자동 백업 설정
- ✅ 로그 모니터링 설정
- ✅ Rate limiting 설정

---

## 7. 문제 해결

### CORS 에러
백엔드 `main.py`에서 CORS 설정 확인:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-url.pages.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### WebSocket 연결 실패
- WSS (보안 WebSocket) 사용 확인
- 백엔드가 WebSocket을 지원하는지 확인 (Railway, Render는 지원)

### 김치프리미엄 기회가 안 보임
- 한국 거래소 API가 정상 작동하는지 확인
- 추적하는 코인이 Upbit/Bithumb에 상장되어 있는지 확인
- 환율 데이터가 정상적으로 조회되는지 확인

---

더 자세한 내용은 README.md를 참고하세요.
