# 무기한 선물 펀딩비 차익거래 시스템 구현 완료 / Perpetual Futures Funding Rate Arbitrage System Implementation

## 📋 구현 개요 / Implementation Overview

이 문서는 무기한 선물 펀딩비 차익거래 시스템의 전체 구현 내용을 정리합니다.
This document summarizes the complete implementation of the perpetual futures funding rate arbitrage system.

**구현 날짜 / Implementation Date**: 2025-11-11
**포함된 거래소 / Exchanges Included**:
- Binance Perpetual Futures / 바이낸스 무기한 선물
- Bybit Perpetual Futures / 바이빗 무기한 선물
- Hyperliquid DEX / 하이퍼리퀴드 DEX
- Base Network (Synthetix Perps) / Base 네트워크 (Synthetix Perps)

---

## 🎯 구현된 차익거래 전략 / Implemented Arbitrage Strategies

### 1. 펀딩비 차익거래 (Funding Rate Arbitrage)
**전략**: 펀딩비가 다른 거래소 간 델타 중립 포지션
**Strategy**: Delta-neutral positions across exchanges with different funding rates

- **원리**: 낮은 펀딩비 거래소에서 롱, 높은 펀딩비 거래소에서 숏
- **Principle**: Long on low funding exchange, short on high funding exchange
- **수익**: 펀딩비 차이 - 스프레드 비용
- **Profit**: Funding rate differential - spread costs
- **위험 관리**: 최소 OI $100,000, 최대 스프레드 20 bps

### 2. 현물-선물 베이시스 차익거래 (Spot-Perp Basis Arbitrage)
**전략**: 현물과 무기한 선물 간 가격 차이 활용
**Strategy**: Exploit price differences between spot and perpetual futures

- **원리**: 현물과 선물 가격 괴리 시 양방향 포지션
- **Principle**: Take positions when spot and perp prices diverge
- **최소 베이시스**: 10 bps
- **Minimum Basis**: 10 bps

### 3. 선물-선물 스프레드 차익거래 (Perp-Perp Spread Arbitrage)
**전략**: 서로 다른 거래소의 무기한 선물 간 가격 차이
**Strategy**: Price differences between perpetual futures on different exchanges

- **원리**: 가격이 낮은 거래소에서 매수, 높은 거래소에서 매도
- **Principle**: Buy on lower price exchange, sell on higher price exchange

---

## 🏗️ 시스템 아키텍처 / System Architecture

### 신규 파일 / New Files

#### 1. **Models / 모델**
- `backend/app/models/market_data.py`
  - `FundingRate`: 펀딩비 데이터 모델
  - `PerpMarketData`: 통합 무기한 선물 시장 데이터 (호가 + 펀딩비 + OI)

#### 2. **Connectors / 커넥터**
- `backend/app/connectors/perp_base.py`: PerpConnector 인터페이스
- `backend/app/connectors/binance_perp.py`: 바이낸스 무기한 선물 커넥터
- `backend/app/connectors/bybit_perp.py`: 바이빗 무기한 선물 커넥터
- `backend/app/connectors/hyperliquid_perp.py`: 하이퍼리퀴드 DEX 커넥터
- `backend/app/connectors/base_perp.py`: Base 네트워크 (Synthetix) 커넥터

### 수정된 파일 / Modified Files

#### 1. **OpportunityEngine** (`backend/app/services/opportunity_engine.py`)
새로운 메서드 / New Methods:
- `_gather_perp_data()`: 무기한 선물 데이터 수집
- `_generate_funding_arb()`: 펀딩비 차익거래 기회 생성
- `_generate_spot_perp_basis()`: 현물-선물 베이시스 기회 생성
- `_generate_perp_perp_spread()`: 선물-선물 스프레드 기회 생성

#### 2. **Configuration** (`backend/app/core/config.py`)
신규 설정 / New Settings:
```python
enable_perp_connectors: bool  # 무기한 선물 커넥터 활성화
enable_binance_perp: bool     # 바이낸스 활성화
enable_bybit_perp: bool       # 바이빗 활성화
enable_hyperliquid_perp: bool # 하이퍼리퀴드 활성화
enable_base_perp: bool        # Base 네트워크 활성화
min_open_interest_usd: float  # 최소 미결제약정 (기본: $100,000)
```

#### 3. **Opportunity Types** (`backend/app/models/opportunity.py`)
신규 타입 / New Types:
- `FUNDING_ARB`: 펀딩비 차익거래
- `PERP_PERP_SPREAD`: 선물-선물 스프레드

---

## 🔒 리스크 관리 / Risk Management

### 1. 미결제약정 (Open Interest) 필터링
```python
min_oi_usd = 100_000  # 최소 OI: $100,000
```
**목적**: 유동성이 낮은 "잡코" 회피, 대형 사고 방지
**Purpose**: Avoid low-liquidity altcoins, prevent major accidents

### 2. 스프레드 체크 (Spread Checking)
```python
max_spread_bps = 20  # 펀딩 차익거래 최대 스프레드: 20 bps
```
**목적**: 과도한 슬리피지 방지
**Purpose**: Prevent excessive slippage

### 3. 펀딩비 변동성 (Funding Rate Volatility)
```python
min_funding_diff = 0.0001  # 최소 차이: 0.01% per 8H
```
**목적**: 의미 있는 차익거래 기회만 추출
**Purpose**: Only capture meaningful arbitrage opportunities

---

## 📊 데이터 정규화 / Data Normalization

### 펀딩비 8시간 정규화 / Funding Rate 8H Normalization
모든 거래소의 펀딩비를 8시간 기준으로 정규화하여 비교 가능하도록 함:
All funding rates are normalized to 8H intervals for comparison:

- **Binance**: 8시간마다 (그대로 사용) / 8H intervals (use as-is)
- **Bybit**: 8시간마다 (그대로 사용) / 8H intervals (use as-is)
- **Hyperliquid**: 시간당 → 8배 / Hourly → multiply by 8
- **Base (Synthetix)**: 일일 → 3으로 나눔 / Daily → divide by 3

---

## 🚀 사용 방법 / Usage

### 1. 환경 설정 / Environment Configuration

`backend/.env` 파일 수정:
```bash
# 무기한 선물 커넥터 활성화 / Enable perpetual futures connectors
ENABLE_PERP_CONNECTORS=true

# 개별 거래소 활성화 / Enable individual exchanges
ENABLE_BINANCE_PERP=true
ENABLE_BYBIT_PERP=true
ENABLE_HYPERLIQUID_PERP=true
ENABLE_BASE_PERP=true

# 최소 미결제약정 설정 / Set minimum open interest
MIN_OPEN_INTEREST_USD=100000
```

### 2. 백엔드 시작 / Start Backend
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 3. 로그 확인 / Check Logs
시작 시 다음과 같은 로그가 표시됩니다:
```
INFO:app.main:Binance perpetual futures connector enabled / 바이낸스 무기한 선물 커넥터 활성화
INFO:app.main:Bybit perpetual futures connector enabled / 바이빗 무기한 선물 커넥터 활성화
INFO:app.main:Hyperliquid DEX perpetual connector enabled / 하이퍼리퀴드 DEX 무기한 선물 커넥터 활성화
INFO:app.main:Base network (Synthetix) perpetual connector enabled / Base 네트워크 (Synthetix) 무기한 선물 커넥터 활성화
```

---

## 📈 API 응답 예시 / API Response Example

### 펀딩비 차익거래 기회 / Funding Rate Arbitrage Opportunity
```json
{
  "id": "uuid",
  "type": "funding_arb",
  "symbol": "BTC/USDT:USDT",
  "spread_bps": 25.0,
  "expected_pnl_pct": 0.15,
  "notional": 10000.0,
  "description": "Funding arb: Long binance @0.0050%/8H, Short bybit @0.0300%/8H",
  "legs": [
    {
      "exchange": "binance",
      "venue_type": "perp",
      "side": "buy",
      "symbol": "BTC/USDT:USDT",
      "price": 94250.0,
      "quantity": 0.106
    },
    {
      "exchange": "bybit",
      "venue_type": "perp",
      "side": "sell",
      "symbol": "BTC/USDT:USDT",
      "price": 94245.0,
      "quantity": 0.106
    }
  ],
  "metadata": {
    "funding_diff_8h_pct": 0.025,
    "long_exchange": "binance",
    "long_funding_8h_pct": 0.005,
    "long_oi_usd": 5000000.0,
    "short_exchange": "bybit",
    "short_funding_8h_pct": 0.03,
    "short_oi_usd": 4500000.0,
    "total_spread_bps": 5.3
  }
}
```

---

## ⚠️ 주의 사항 / Important Notes

### 1. 프로덕션 사용 전 / Before Production Use
- [ ] 실제 API 키 설정 / Configure real API keys
- [ ] 충분한 테스트 수행 / Perform thorough testing
- [ ] 소액으로 시작 / Start with small amounts
- [ ] 리스크 한도 설정 / Set risk limits

### 2. 모니터링 / Monitoring
- 펀딩비 변동성 주시 / Monitor funding rate volatility
- OI 변화 추적 / Track OI changes
- 스프레드 이상 감지 / Detect spread anomalies
- 슬리피지 모니터링 / Monitor slippage

### 3. 거래소별 특징 / Exchange-Specific Notes

#### Binance / 바이낸스
- 펀딩 주기: 8시간 (00:00, 08:00, 16:00 UTC)
- API 제한: 초당 1,200 요청
- 높은 유동성, 안정적인 펀딩비

#### Bybit / 바이빗
- 펀딩 주기: 8시간
- API v5 사용
- 알트코인 펀딩비 변동성 높음

#### Hyperliquid / 하이퍼리퀴드
- DEX, 펀딩 주기: 1시간 (8H로 정규화)
- 낮은 수수료, 높은 슬리피지 가능
- 일부 심볼 유동성 낮음

#### Base (Synthetix) / Base (Synthetix)
- 오라클 기반 가격 (주문장 없음)
- 연속 펀딩 (일일 기준, 8H로 정규화)
- Layer 2, 빠른 정산

---

## 🔄 향후 개선 사항 / Future Improvements

### 1. 프론트엔드 / Frontend
- [ ] 펀딩비 실시간 차트
- [ ] OI 변화 그래프
- [ ] 거래소별 필터링
- [ ] 알림 시스템

### 2. 백엔드 / Backend
- [ ] 펀딩비 히스토리 저장
- [ ] 변동성 예측 모델
- [ ] 자동 실행 시스템
- [ ] 포지션 관리

### 3. 거래소 확장 / Exchange Expansion
- [ ] EdgeX 추가
- [ ] Lighter 추가
- [ ] Variational 추가
- [ ] GRVT 추가

---

## 📝 참고 자료 / References

- [Binance Futures API Documentation](https://binance-docs.github.io/apidocs/futures/en/)
- [Bybit API Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [Hyperliquid API Documentation](https://hyperliquid.gitbook.io/hyperliquid-docs)
- [Synthetix Perps Documentation](https://docs.synthetix.io/perps)

---

**구현 완료 / Implementation Complete**: ✅ 2025-11-11
