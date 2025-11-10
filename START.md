# 🚀 빠른 시작 가이드 / Quick Start Guide

## API 키 없이 GUI만 보기 / View GUI Without API Keys

이 가이드는 실제 거래소 API 키 없이 데모 모드로 애플리케이션을 실행하는 방법입니다.
This guide shows how to run the application in demo mode without real exchange API keys.

---

## 옵션 1: 수동 실행 (권장) / Option 1: Manual Run (Recommended)

### 1단계: 백엔드 실행 / Step 1: Run Backend

터미널을 열고 다음 명령을 실행하세요:
Open a terminal and run:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e .[dev]

# 백엔드 시작 / Start backend
uvicorn app.main:app --reload --port 8000
```

**백엔드가 http://localhost:8000 에서 실행됩니다**
Backend will run at http://localhost:8000

API 문서를 보려면: http://localhost:8000/docs
To see API docs: http://localhost:8000/docs

### 2단계: 프론트엔드 실행 / Step 2: Run Frontend

**새 터미널**을 열고 다음 명령을 실행하세요:
Open a **new terminal** and run:

```bash
cd frontend
npm install
npm run dev
```

**프론트엔드가 http://localhost:5174 에서 실행됩니다**
Frontend will run at http://localhost:5174

---

## 옵션 2: Docker Compose

```bash
# 프로젝트 루트에서 / From project root
docker-compose up -d

# 로그 보기 / View logs
docker-compose logs -f

# 종료하기 / Stop
docker-compose down
```

접속:
- Frontend: http://localhost:5174
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## 데모 모드에서 할 수 있는 것 / What You Can Do in Demo Mode

### ✅ 가능한 기능 / Available Features:

1. **회원가입 및 로그인** / Register & Login
   - 새 계정 생성
   - JWT 토큰 기반 인증

2. **실시간 차익거래 기회 보기** / View Live Arbitrage Opportunities
   - 시뮬레이션된 시장 데이터
   - WebSocket 실시간 업데이트
   - 예상 수익률, 스프레드, 필요 자본 표시

3. **Dry Run 실행** / Execute Dry Run
   - 실제 주문 없이 실행 로직 테스트
   - 리스크 체크 확인
   - 실행 로그 기록

4. **포트폴리오 보기** / View Portfolio
   - 잔고 추적
   - PnL 계산
   - 노출도 모니터링

### ⚠️ 제한 사항 / Limitations:

- **실제 거래소 주문은 제출되지 않습니다** / Real exchange orders are NOT submitted
- 시뮬레이션된 시장 데이터만 표시 / Only simulated market data shown
- 실제 API 키가 없어도 모든 기능 테스트 가능 / All features can be tested without real API keys

---

## 🔍 확인 사항 / Verification

### 백엔드가 정상적으로 시작되었는지 확인:
Check if backend started successfully:

```bash
curl http://localhost:8000/health
```

응답: `{"status":"ok"}` 또는 유사한 내용
Response: `{"status":"ok"}` or similar

### 프론트엔드 접속:

브라우저에서 http://localhost:5174 열기
Open http://localhost:5174 in browser

---

## 🛠️ 문제 해결 / Troubleshooting

### 백엔드가 시작되지 않는 경우:

```bash
# Python 버전 확인 / Check Python version
python3 --version  # Should be 3.9 or higher

# 의존성 재설치 / Reinstall dependencies
cd backend
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[dev]
```

### 프론트엔드가 시작되지 않는 경우:

```bash
# Node 버전 확인 / Check Node version
node --version  # Should be 18 or higher

# node_modules 재설치 / Reinstall node_modules
cd frontend
rm -rf node_modules
npm install
```

### 포트가 이미 사용 중인 경우:

**백엔드 (8000 포트)**:
```bash
# 다른 포트로 실행 / Run on different port
uvicorn app.main:app --reload --port 8001
```

그 다음 `frontend/.env`에서 `VITE_API_HTTP_BASE`를 변경하세요.
Then change `VITE_API_HTTP_BASE` in `frontend/.env`.

**프론트엔드 (5174 포트)**:
`vite.config.ts`의 `port` 값을 다른 번호로 변경하세요.
Change the `port` value in `vite.config.ts` to a different number.

---

## 📝 다음 단계 / Next Steps

데모를 확인한 후:
After testing the demo:

1. **실제 거래소 API 키 추가** / Add real exchange API keys
   - UI의 설정 페이지에서 추가 (구현 예정)
   - 또는 데이터베이스에 직접 추가

2. **리스크 한도 설정** / Configure risk limits
   - 포지션 크기 제한
   - 일일 손실 제한
   - 레버리지 제한

3. **실제 거래 시작** / Start real trading
   - **먼저 소액으로 테스트!** / Test with small amounts first!
   - 실행 로그 모니터링 / Monitor execution logs
   - 실시간 포트폴리오 추적 / Track portfolio in real-time

---

**🎉 즐거운 테스트 되세요! / Happy Testing!**
