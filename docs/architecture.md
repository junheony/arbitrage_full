# Arbitrage Platform Architecture / 아비트리지 플랫폼 아키텍처

## Vision / 비전
- Deliver an all-in-one arbitrage command center covering spot, perpetual futures, and funding-rate plays. / 스팟, 영구선물, 펀딩 전략을 아우르는 올인원 아비트리지 지휘센터를 제공합니다.
- Surface actionable spreads and funding mispricings in real time, with one-click execution via pre-configured exchange accounts. / 미리 연동된 거래소 계정으로 원클릭 체결이 가능한 실시간 기회와 펀딩 미스프라이싱을 노출합니다.
- Provide a transparent view of portfolio exposure, risk, and PnL across venues. / 거래소별 포지션, 위험도, 손익을 투명하게 보여줍니다.

## Core Requirements / 핵심 요구사항
- **Multi-market data ingestion / 다중 마켓 데이터 수집**: Spot and derivatives order books, funding rates, index prices, borrow rates. / 현물·파생 주문장, 펀딩비, 지수 가격, 차입 금리를 수집합니다.
- **Opportunity engine / 기회 엔진**:
  - Cross-exchange spot arbitrage (e.g., `Exchange A BTC/USDT` vs `Exchange B BTC/USDT`). / 거래소 간 현물 스프레드 아비트리지.
  - Spot-perp basis (e.g., `Exchange A spot BTC/USDT` vs `Exchange A perpetual BTC/USD`). / 동일 거래소 현물-선물 베이시스 트레이드.
  - Funding arbitrage (long cash & carry when funding positive, short when negative). / 펀딩베이스 전략(양수일 때 롱, 음수일 때 숏).
  - Support for configurable opportunity templates (thresholds, capital allocation rules). / 임계값·자본배분 규칙이 설정 가능한 템플릿 지원.
- **Execution layer / 실행 레이어**: Unified order router that can bucket capital, submit staggered orders, and manage fills/cancellations. / 자본 버킷팅, 분할 주문, 체결/취소 관리를 수행하는 통합 오더 라우터.
- **Portfolio & risk / 포트폴리오·리스크**: Consolidated balances, exposure by asset/venue, risk metrics (VaR-approx, leverage, margin usage). / 자산·거래소별 잔고와 익스포저, 리스크 지표(VaR 추정, 레버리지, 마진 사용률).
- **GUI**: Real-time dashboards, opportunity list with execution buttons, position monitor, historical analytics. / 실시간 대시보드, 실행 버튼이 있는 기회 목록, 포지션 모니터, 히스토리 분석.
- **Extensibility / 확장성**: Plug-in style connectors for additional exchanges, strategies, signals. / 추가 거래소·전략·신호를 위한 플러그인형 커넥터 구조.

## Reference Insights / 참고 인사이트
- **datamaxiplus.com**: Emphasizes aggregated funding and basis charts; we mirror their modular dashboards (Funding Heatmap, Basis Timeline, Live Opportunities). / 집계된 펀딩·베이시스 차트를 강조하므로 펀딩 히트맵, 베이시스 타임라인, 실시간 기회 모듈형 대시보드를 참고합니다.
- **theddari.com/arbitrage**: Offers compact opportunity cards; replicate actionable cards with quick filters. / 콤팩트한 기회 카드 구성을 제공하므로 빠른 필터와 실행이 가능한 카드 UI를 차용합니다.
- **theddari.com/realtime-funding**: Highlights the need for per-venue funding tables and alerts. / 거래소별 펀딩 테이블과 알림의 필요성을 보여줍니다.
- **perpstats.octav.fi**: Provides historical perp premium analysis; informs our analytics module. / 선물 프리미엄 히스토리를 제공하여 분석 모듈 설계에 참고합니다.
- **김프 테더봇** insights: Strategy focuses on allocating capital based on premium tiers (reverse premium vs normal). We embed configurable tiered allocation curves per strategy. / 김프 테더봇 전략처럼 역프/정프 구간별 자본배분이 핵심이므로 전략별 계단형 배분곡선을 구성합니다.

## High-Level Topology / 상위 토폴로지

```
 ┌─────────────────────┐      ┌──────────────────────┐
 │  Exchange Connectors│◀────▶│  Market Data Bus     │
 └─────────────────────┘      └──────────────────────┘
             ▲                         │
             │                         ▼
 ┌─────────────────────┐      ┌──────────────────────┐
 │Execution Controller │◀────▶│ Opportunity Engine   │
 └─────────────────────┘      └──────────────────────┘
             ▲                         │
             │                         ▼
       ┌───────────────────────────────────────────┐
       │       Portfolio & Risk Service            │
       └───────────────────────────────────────────┘
                             │
                             ▼
                   ┌───────────────────┐
                   │   GUI (Web/Electron)
                   └───────────────────┘
```

## Backend Overview / 백엔드 개요
- **Language / 언어**: Python 3.11+
- **Framework / 프레임워크**: FastAPI for REST + WebSocket. / REST·웹소켓을 위한 FastAPI.
- **Task scheduling / 작업 스케줄링**: asyncio background tasks + APScheduler for interval jobs. / asyncio 백그라운드 작업과 APScheduler 기반 주기 작업.
- **Data store / 데이터 저장소**:
  - Redis (real-time cache, pub/sub). / 실시간 캐시 및 pub/sub 용 Redis.
  - PostgreSQL or DuckDB (historical analytics, backtesting). / 히스토리 분석·백테스트용 PostgreSQL 또는 DuckDB.
  - For MVP use SQLite for persistence. / MVP 단계에서는 SQLite 사용.
- **Message bus / 메시지 버스**: `asyncio.Queue` for internal events, optional Redis streams for distributed scale. / 내부 이벤트용 `asyncio.Queue`, 확장 시 Redis Streams 옵션.
- **Connectors / 커넥터**: Public REST spot collectors (Binance, OKX, Upbit, Bithumb), USD/KRW FX feed with fallback, CCXT-based extensions, and simulation feeds for development. / 바이낸스·OKX·업비트·빗썸 현물, USD/KRW 환율 대체 소스, CCXT 확장과 개발용 시뮬레이터 제공.
- **Opportunity Engine / 기회 엔진**:
  - Normalizes order books into unified schema. / 주문장을 단일 스키마로 정규화.
  - Maintains rolling fair-value metrics (VWAP, index). / VWAP, 인덱스 등 공정가를 계산.
  - Evaluates strategy rules (thresholds, capital weight curves). / 전략 임계값과 자본 가중 곡선을 평가.
  - Emits `Opportunity` objects with estimated PnL, risk, execution plan. / 예상 손익·리스크·실행 계획이 담긴 `Opportunity` 객체 발행.
- **Execution Controller / 실행 컨트롤러**:
  - Risk checks: capital availability, max leverage, latency tolerance. / 자본 가용성, 최대 레버리지, 지연 허용치 점검.
  - Order templates: Market sweep, post-only ladder, TWAP. / 마켓 스윕, 포스트온리 레더, TWAP 템플릿.
  - Monitors fills and updates portfolio service. / 체결 모니터링 및 포트폴리오 업데이트.

## Frontend Overview / 프론트엔드 개요
- **Stack / 스택**: Vite + React + TypeScript.
- **UI Framework / UI 프레임워크**: Mantine + Zustand (state management) + Recharts/Perspective for visualizations. / Mantine, Zustand 상태관리, Recharts/Perspective 시각화.
- **Key Views / 주요 화면**:
  - **Live Opportunities Grid / 실시간 기회 그리드**: Cards with spread %, notional, risk, quick-execute buttons. / 스프레드·노치널·리스크·원클릭 실행 버튼이 있는 카드.
  - **Funding Heatmap / 펀딩 히트맵**: Matrix of funding rates across venues/time. / 거래소·시간대별 펀딩비 매트릭스.
  - **Portfolio Dashboard / 포트폴리오 대시보드**: Positions, PnL waterfall, margin usage. / 포지션, 손익 워터폴, 마진 사용률.
  - **Execution Console / 실행 콘솔**: Manual trade tickets, strategy toggles, logs. / 수동 주문 티켓, 전략 토글, 로그.
- **Real-time updates / 실시간 업데이트**: WebSocket subscription to FastAPI streaming channels. / FastAPI 웹소켓 스트림 구독.
- **Notifications / 알림**: Desktop alerts for threshold breaches. / 임계값 초과 시 데스크톱 알림.

## Strategy Layer / 전략 레이어
- **Capital Allocation Curve / 자본 배분 곡선**: Piecewise linear mapping from premium to capital %, calibrated per strategy (implements 김프 테더봇 logic). / 프리미엄 구간별 자본 비중을 결정하는 계단형 곡선으로 김프 테더봇 로직을 반영.
- **Tether Bot Signals / 테더봇 시그널**: Combines kimchi premium, FX rate, and allocation curve to output target weights, notional, and action bias (buy vs sell KRW). / 김프와 환율·배분곡선을 결합해 목표 비중·권장 노치널·실행 방향을 계산.
- **Trade Frequency Controls / 거래 빈도 제어**: Configurable cool-down or max trades per window to balance ROI vs execution cost. / ROI와 실행비용 균형을 위한 쿨다운·시간당 최대 체결 수 설정.
- **Risk Mitigation / 리스크 완화**:
  - Spread-based stop-loss & take-profit. / 스프레드 기준 손절·익절.
  - Hedge orders for delta neutrality. / 델타 뉴트럴 유지를 위한 헤지 주문.
  - Circuit breakers on connectivity or slippage. / 연결 이상·슬리피지 시 서킷브레이커.

## Deployment & Ops / 배포·운영
- Containerized via Docker Compose: / Docker Compose 기반 컨테이너 구성:
  - `backend`: FastAPI app. / FastAPI 백엔드.
  - `worker`: Async task runner (data ingestion/execution). / 비동기 작업 실행기.
  - `frontend`: Vite dev server or static build behind Nginx. / Vite 개발 서버 또는 Nginx 뒤 정적 빌드.
  - `redis`, `postgres`.
- Secrets managed with `.env` files + Vault (future). / `.env`와 향후 Vault를 통한 시크릿 관리.
- Observability: Prometheus metrics, Loki logs. / Prometheus 메트릭, Loki 로그.
- CI: GitHub Actions for tests, lint, type checks, end-to-end smoke tests. / 테스트·린트·타입체크·E2E 스모크를 위한 GitHub Actions.

## Initial Milestones / 초기 마일스톤
1. MVP data ingestion with simulated connectors (Binance/OKX spot & perp tickers via public REST). / 퍼블릭 REST로 바이낸스·OKX 시세를 모사하는 커넥터와 함께 MVP 데이터 수집.
2. Build opportunity engine for cross-exchange spot spread with simple risk gating. / 기본 리스크 필터가 포함된 거래소 간 현물 스프레드 엔진 구축.
3. Create GUI showing live spreads and manual execution stub. / 실시간 스프레드와 수동 실행 스텁을 제공하는 GUI 제작.
4. Integrate funding data (perp stats) and implement capital allocation curves. / 펀딩 데이터 연동 및 자본 배분 곡선 구현.
5. Add real exchange execution (testnet) with risk management and order tracking. / 실거래소(테스트넷) 실행, 리스크 관리, 주문 추적 추가.

## Open Questions / 추가 확인 사항
- Preferred exchanges and API keys availability? / 선호 거래소와 API 키 준비 여부?
- Custody approach (centralized vs subaccounts per strategy). / 자산 보관 방식(통합 계정 vs 전략별 서브계정)?
- Requirements for latency (<100ms?) or is near-real-time acceptable? / 요구 지연시간(100ms 이하?) 혹은 준실시간으로 충분한가?
- Compliance constraints (jurisdictions, KYC). / 지역 규제·KYC 제약은 무엇인가?
