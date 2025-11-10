import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useMemo, useState } from "react";
import "./App.css";
import { useOpportunities } from "./hooks/useOpportunities";
import type { Opportunity, OpportunityMetadata } from "./types";
import { isAuthenticated, clearToken } from "./auth";
import { executeOpportunity } from "./api";
import { LoginModal } from "./LoginModal";

dayjs.extend(relativeTime);

function App() {
  const { opportunities, isLoading, error, lastUpdated } = useOpportunities();
  const [showLogin, setShowLogin] = useState(false);
  const [authenticated, setAuthenticated] = useState(isAuthenticated());

  const topSpread = useMemo(
    () => opportunities[0]?.spread_bps ?? 0,
    [opportunities],
  );

  const handleLogout = () => {
    clearToken();
    setAuthenticated(false);
    alert("Logged out successfully / 로그아웃되었습니다");
  };

  const handleLoginSuccess = () => {
    setShowLogin(false);
    setAuthenticated(true);
    alert("Logged in successfully! / 로그인 성공!");
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Arbitrage Command / 아비트리지 커맨드</h1>
          <span className="app-subtitle">Kimchi premium · funding · basis radar / 김프 · 펀딩 · 현선 레이더</span>
        </div>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
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
          <div>
            {authenticated ? (
              <button
                onClick={handleLogout}
                style={{
                  padding: '8px 16px',
                  background: '#ef4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
              >
                Logout / 로그아웃
              </button>
            ) : (
              <button
                onClick={() => setShowLogin(true)}
                style={{
                  padding: '8px 16px',
                  background: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
              >
                Login / 로그인
              </button>
            )}
          </div>
        </div>
      </header>

      <LoginModal
        isOpen={showLogin}
        onClose={() => setShowLogin(false)}
        onSuccess={handleLoginSuccess}
      />

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
  const [isExecuting, setIsExecuting] = useState(false);
  const [executeResult, setExecuteResult] = useState<string | null>(null);
  const authenticated = isAuthenticated();

  const handleExecute = async (dryRun: boolean = false) => {
    if (!authenticated) {
      alert("Please login first / 먼저 로그인하세요");
      return;
    }

    setIsExecuting(true);
    setExecuteResult(null);

    try {
      const result = await executeOpportunity({
        opportunity_id: opportunity.id,
        dry_run: dryRun,
      });

      setExecuteResult(`✅ ${result.message}`);
    } catch (error) {
      setExecuteResult(`❌ ${error instanceof Error ? error.message : 'Execution failed'}`);
    } finally {
      setIsExecuting(false);
    }
  };

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
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            className="execute-button"
            onClick={() => handleExecute(true)}
            disabled={isExecuting || !authenticated}
            title={!authenticated ? "Login required / 로그인 필요" : "Simulate execution / 실행 시뮬레이션"}
          >
            {isExecuting ? "⏳ Processing..." : "🧪 Dry Run / 시뮬레이션"}
          </button>
          <button
            className="execute-button"
            onClick={() => {
              if (window.confirm("Execute REAL orders? This will place actual trades! / 실제 주문을 체결하시겠습니까?")) {
                handleExecute(false);
              }
            }}
            disabled={isExecuting || !authenticated}
            style={{
              background: authenticated ? '#ef4444' : '#4b5563',
              cursor: !authenticated || isExecuting ? 'not-allowed' : 'pointer'
            }}
            title={!authenticated ? "Login required / 로그인 필요" : "Execute real orders / 실제 체결"}
          >
            {isExecuting ? "⏳ Processing..." : "⚡ Execute / 실행"}
          </button>
        </div>
      </header>

      <p className="card-description">{opportunity.description}</p>

      {executeResult && (
        <div style={{
          padding: '12px',
          borderRadius: '4px',
          background: executeResult.startsWith('✅') ? '#10b981' : '#ef4444',
          color: 'white',
          marginBottom: '16px',
          fontSize: '14px'
        }}>
          {executeResult}
        </div>
      )}

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
