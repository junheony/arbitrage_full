# Binance Futures Gap Monitor (시평갭 모니터)

바이낸스 선물 시장의 가격 갭(시평갭)을 실시간으로 모니터링하고 텔레그램 알림을 보내는 시스템입니다.

## 기능

- **실시간 시평갭 모니터링**: 바이낸스 선물 vs 인덱스 가격 차이 추적
- **자동 갱신**: 3초마다 데이터 업데이트
- **텔레그램 알림**: 설정한 임계값 초과 시 자동 알림
- **터미널 스타일 UI**: 깔끔한 모니터링 대시보드

## 시평갭이란?

```
시평갭 = (선물가격 - 인덱스가격) / 인덱스가격 × 100

예시: FLOWUSDT +2.114%
- 선물가격이 인덱스보다 2.114% 높음
- 청산 캐스케이드나 급격한 변동 시 발생
- 갭이 좁혀지면 수익 기회
```

## 로컬 실행

```bash
cd monitor
npm install
npm run dev
```

http://localhost:3000 에서 확인

## Vercel 배포

### 1. Vercel CLI 설치

```bash
npm i -g vercel
```

### 2. 배포

```bash
cd monitor
vercel
```

### 3. 환경변수 설정 (선택사항 - 자동 알림용)

Vercel 대시보드에서 환경변수 설정:

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-1001234567890
MIN_GAP_THRESHOLD=0.5
CRON_SECRET=your-secret-key
```

### 4. Cron 설정 (자동 알림)

외부 cron 서비스 (cron-job.org 등)에서 1분마다 호출:

```
GET https://your-app.vercel.app/api/cron
Authorization: Bearer your-secret-key
```

## API 엔드포인트

| 엔드포인트 | 메소드 | 설명 |
|-----------|--------|------|
| `/api/prices` | GET | 전체 가격 데이터 |
| `/api/spreads?minGap=0.3` | GET | 갭 목록 (임계값 이상) |
| `/api/alert` | POST | 수동 알림 체크 |
| `/api/alert` | PUT | 테스트 메시지 발송 |
| `/api/cron` | GET | 자동 알림 (cron용) |

## 텔레그램 봇 설정

1. @BotFather에서 봇 생성
2. 봇 토큰 복사
3. 봇과 대화 시작 또는 그룹에 추가
4. Chat ID 확인: `https://api.telegram.org/bot<TOKEN>/getUpdates`

## 프로젝트 구조

```
monitor/
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   ├── prices/route.ts   # 가격 API
│   │   │   ├── spreads/route.ts  # 갭 API
│   │   │   ├── alert/route.ts    # 알림 API
│   │   │   └── cron/route.ts     # 자동 알림
│   │   ├── page.tsx              # 대시보드 UI
│   │   ├── layout.tsx
│   │   └── globals.css
│   └── lib/
│       ├── types.ts              # 타입 정의
│       ├── binance.ts            # 바이낸스 API
│       └── telegram.ts           # 텔레그램 알림
├── vercel.json
└── package.json
```

## 향후 추가 예정

- [ ] CEX-DEX 스프레드 모니터링
- [ ] 김치프리미엄 추적
- [ ] 펀딩비 모니터링
- [ ] 알림 히스토리 저장
