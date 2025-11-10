import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useMemo } from "react";
import "./App.css";
import { useOpportunities } from "./hooks/useOpportunities";
import type { Opportunity, OpportunityMetadata } from "./types";

dayjs.extend(relativeTime);

function App() {
  const { opportunities, isLoading, error, lastUpdated } = useOpportunities();
  const topSpread = useMemo(
    () => opportunities[0]?.spread_bps ?? 0,
    [opportunities],
  );

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Arbitrage Command / 아비트리지 커맨드</h1>
          <span className="app-subtitle">Kimchi premium · funding · basis radar / 김프 · 펀딩 · 현선 레이더</span>
        </div>
        <div className="status-block">
          <span className="status-label">Max spread / 최대 스프레드</span>
          <span className="status-value">
            {topSpread ? `${topSpread.toFixed(2)} bps` : "-"}
          </span>
          <span className="status-updated">
            {lastUpdated
              ? dayjs(lastUpdated).fromNow()
              : "Awaiting data / 데이터 수신 중"}
          </span>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <section className="opportunity-grid">
        {isLoading && opportunities.length === 0 ? (
          <div className="empty-state">Loading live opportunities… / 실시간 기회를 불러오는 중…</div>
        ) : opportunities.length === 0 ? (
          <div className="empty-state">No executable spreads right now / 현재 체결 가능한 스프레드가 없습니다.</div>
        ) : (
          opportunities.map((opportunity) => (
            <OpportunityCard key={opportunity.id} opportunity={opportunity} />
          ))
        )}
      </section>
    </div>
  );
}

interface OpportunityCardProps {
  opportunity: Opportunity;
}

function OpportunityCard({ opportunity }: OpportunityCardProps) {
  const metadata = opportunity.metadata;
  const metrics = [
    {
      label: "Expected return / 기대 수익률",
      value: `${opportunity.expected_pnl_pct.toFixed(2)} %`,
    },
    {
      label: "Spread / 스프레드",
      value: `${opportunity.spread_bps.toFixed(2)} bps`,
    },
    {
      label: "Deployed capital / 투입 자본",
      value: `$${opportunity.notional.toLocaleString()}`,
    },
    {
      label: "Detected at / 발견 시간",
      value: dayjs(opportunity.timestamp).format("HH:mm:ss"),
    },
  ];

  if (metadata?.target_allocation_pct !== undefined) {
    metrics.push({
      label: "Target allocation / 목표 비중",
      value: `${metadata.target_allocation_pct.toFixed(2)} %`,
    });
  }
  if (metadata?.recommended_notional !== undefined) {
    metrics.push({
      label: "Recommended notional / 권장 노치널",
      value: `$${metadata.recommended_notional.toLocaleString()}`,
    });
  }
  if (metadata?.recommended_action) {
    metrics.push({
      label: "Action / 실행 방향",
      value: renderActionLabel(metadata.recommended_action),
    });
  }
  if (metadata?.fx_rate !== undefined) {
    metrics.push({
      label: "USD/KRW",
      value: metadata.fx_rate.toLocaleString(),
    });
  }

  return (
    <article className="opportunity-card">
      <header className="card-header">
        <div>
          <h2>{opportunity.symbol}</h2>
          <span className={`pill pill-${opportunity.type}`}>
            {renderTypeLabel(opportunity.type)}
          </span>
        </div>
        <button className="execute-button" disabled>
          One-click execution (coming soon) / 원클릭 체결 (준비 중)
        </button>
      </header>

      <p className="card-description">{opportunity.description}</p>

      <div className="card-metrics">
        {metrics.map((metric) => (
          <Metric key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>

      <div className="legs">
        {opportunity.legs.map((leg, index) => (
          <div key={index} className="leg">
            <div className="leg-side">
              {leg.side === "buy" ? "BUY / 매수" : "SELL / 매도"}
            </div>
            <div>
              <strong>{leg.exchange.toUpperCase()}</strong> · {renderVenueLabel(leg.venue_type)}
            </div>
            <div>
              {leg.price.toLocaleString()} @ {leg.quantity.toFixed(4)}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

interface MetricProps {
  label: string;
  value: string;
}

function Metric({ label, value }: MetricProps) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

function renderTypeLabel(type: Opportunity["type"]): string {
  switch (type) {
    case "spot_cross":
      return "Spot cross / 현물 교차";
    case "spot_vs_perp":
      return "Spot vs perp basis / 현선 베이시스";
    case "funding":
      return "Funding / 펀딩";
    case "kimchi_premium":
      return "Kimchi premium / 김프";
    default:
      return type;
  }
}

function renderVenueLabel(venue: Opportunity["legs"][number]["venue_type"]): string {
  if (venue === "spot") {
    return "spot / 현물";
  }
  if (venue === "perp") {
    return "perp / 선물";
  }
  return "fx / 환율";
}

function renderActionLabel(action: OpportunityMetadata["recommended_action"]): string {
  if (action === "sell_krw") {
    return "Sell KRW exposure / 국내 프리미엄 축소";
  }
  if (action === "buy_krw") {
    return "Buy KRW exposure / 국내 프리미엄 확대";
  }
  return String(action);
}

export default App;
