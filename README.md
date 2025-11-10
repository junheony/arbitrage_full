# Arbitrage Command Platform / 아비트리지 커맨드 플랫폼

All-in-one GUI platform for detecting and executing crypto arbitrage opportunities (cross-exchange spot, spot-perp basis, funding strategies). / 거래소 간 현물, 현선 베이시스, 펀딩 전략을 탐지·체결하는 올인원 GUI 플랫폼입니다.

## Repository Layout / 저장소 구성
- `backend/` – FastAPI service with simulated exchange connectors and opportunity engine. / 시뮬레이터 커넥터와 기회 엔진을 포함한 FastAPI 서비스.
- `frontend/` – Vite + React dashboard that streams opportunities in real time. / 실시간 기회를 스트리밍하는 Vite + React 대시보드.
- `docs/architecture.md` – Detailed system architecture, components, and roadmap. / 시스템 아키텍처, 구성요소, 로드맵 문서.

## Getting Started / 시작하기

### Backend / 백엔드
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[dev]
uvicorn app.main:app --reload --port 8000
```

Enable real spot market feeds via CCXT by exporting:
```bash
export ENABLE_CCXT_SPOT=true
# optional: override exchanges or symbols (JSON encoded)
# export CCXT_SPOT_EXCHANGES='["binance", "okx"]'
# export TRADING_SYMBOLS='["BTC/USDT", "ETH/USDT"]'
```
실제 현물 시세를 연동하려면 위 환경변수를 설정하세요.

### Frontend / 프론트엔드
```bash
cd frontend
npm install
npm run dev
```

Default configuration expects the backend on `http://localhost:8000`. Override using: / 기본 설정은 백엔드가 `http://localhost:8000`에 있다고 가정하며, 아래 환경변수로 변경할 수 있습니다.
- `VITE_API_HTTP_BASE` – e.g., `http://localhost:8000/api`
- `VITE_API_WS_BASE` – e.g., `ws://localhost:8000/api/ws`

Create `.env` files as needed (see `.env.example` templates once created). / 필요한 경우 `.env` 파일을 생성하고 예시 템플릿을 참고하세요.

## Current Capabilities / 현재 기능
- Public REST spot feeds for Binance, OKX, Upbit, Bithumb, plus USD/KRW forex fallback. / 바이낸스·OKX·업비트·빗썸 현물과 USD/KRW 환율(대체 소스 포함) 수집.
- Opportunity engine producing cross-exchange and kimchi-premium signals with tether-bot allocation metadata. / 거래소 간 스프레드와 김프 테더봇 배분 신호를 생성.
- Automatic demo opportunities when data unavailable so the GUI always renders actionable cards. / 실데이터 부재 시에도 데모 카드가 노출되어 UI가 항상 표시됩니다.
- React dashboard showing live cards with expected returns, target allocations, and execution stubs. / 기대 수익률과 목표 배분까지 표시하는 실시간 카드형 대시보드.

REST endpoints / REST 엔드포인트:
- `GET /api/opportunities` – latest spreads and kimchi signals (includes demo fallback). / 최신 스프레드·김프 시그널(데모 포함).
- `GET /api/signals/tether-bot` – tether bot-focused allocations. / 테더봇 리밸런싱 신호.

## Next Steps / 다음 단계
1. **Exchange Integrations / 거래소 연동** – Replace simulators with CCXT (spot) and dedicated perp clients (Binance Futures, Bybit, OKX). Support sandbox/testnet keys. / 시뮬레이터 대신 CCXT(현물)와 전용 선물 클라이언트로 교체하고 테스트넷 키를 지원합니다.
2. **Strategy Expansion / 전략 확장** – Add spot-vs-perp basis, funding calculators, and capital allocation curves per 김프 테더봇 spec. / 현선 베이시스, 펀딩 계산기, 김프 테더봇식 자본 배분 곡선 추가.
3. **Execution Layer / 실행 레이어** – Implement smart order router with safety checks, order tracking, and cancel/retry logic. / 안전장치, 주문 추적, 취소·재시도 로직을 갖춘 스마트 오더 라우터 구현.
4. **Portfolio Service / 포트폴리오 서비스** – Track balances, margin usage, PnL, and hedge requirements across venues. / 거래소별 잔고, 마진 사용률, 손익, 헤지 요구량을 추적.
5. **Alerting & Automation / 알림·자동화** – Threshold alerts, auto-trigger toggles, and historical analytics similar to perpstats dashboards. / 임계값 알림, 자동 실행 토글, perpstats 스타일의 히스토리 분석 추가.

Refer to `docs/architecture.md` for detailed component breakdown and milestone plan. / 상세 구성과 마일스톤은 `docs/architecture.md`에서 확인하세요.
