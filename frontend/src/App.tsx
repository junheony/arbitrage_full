import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useMemo, useState } from "react";
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 lg:py-12">
      {/* Header */}
      <header className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 mb-8">
        <div>
          <h1 className="text-3xl lg:text-4xl font-bold text-white mb-2 flex items-center gap-3">
            <i className="fas fa-chart-line text-primary"></i>
            Arbitrage Command / 아비트리지 커맨드
          </h1>
          <p className="text-sm text-base-content/60">
            <i className="fas fa-radar mr-2"></i>
            Kimchi premium · funding · basis radar / 김프 · 펀딩 · 현선 레이더
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <div className="stats shadow-lg bg-base-200/80 border border-base-300">
            <div className="stat py-4 px-6">
              <div className="stat-title text-xs">Max spread / 최대 스프레드</div>
              <div className="stat-value text-2xl text-primary">
                {topSpread ? `${topSpread.toFixed(2)} bps` : "-"}
              </div>
              <div className="stat-desc text-xs">
                <i className="far fa-clock mr-1"></i>
                {lastUpdated
                  ? dayjs(lastUpdated).fromNow()
                  : "Awaiting data / 데이터 수신 중"}
              </div>
            </div>
          </div>
          <div>
            {authenticated ? (
              <button
                onClick={handleLogout}
                className="btn btn-error btn-sm lg:btn-md gap-2"
              >
                <i className="fas fa-sign-out-alt"></i>
                Logout / 로그아웃
              </button>
            ) : (
              <button
                onClick={() => setShowLogin(true)}
                className="btn btn-primary btn-sm lg:btn-md gap-2"
              >
                <i className="fas fa-sign-in-alt"></i>
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

      {error && (
        <div className="alert alert-error shadow-lg mb-6">
          <i className="fas fa-exclamation-triangle text-xl"></i>
          <span>{error}</span>
        </div>
      )}

      {/* Opportunities Grid */}
      <section className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {isLoading && opportunities.length === 0 ? (
          <div className="col-span-full flex flex-col items-center justify-center py-20 bg-base-200/50 rounded-2xl border-2 border-dashed border-base-300">
            <i className="fas fa-spinner fa-spin text-4xl text-primary mb-4"></i>
            <p className="text-base-content/60">Loading live opportunities… / 실시간 기회를 불러오는 중…</p>
          </div>
        ) : opportunities.length === 0 ? (
          <div className="col-span-full flex flex-col items-center justify-center py-20 bg-base-200/50 rounded-2xl border-2 border-dashed border-base-300">
            <i className="fas fa-search-dollar text-4xl text-base-content/40 mb-4"></i>
            <p className="text-base-content/60">No executable spreads right now / 현재 체결 가능한 스프레드가 없습니다.</p>
          </div>
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
    <article className="card bg-gradient-to-br from-base-200/90 to-base-300/70 shadow-xl border border-base-300 hover:shadow-2xl transition-all duration-200">
      <div className="card-body">
        {/* Card Header */}
        <div className="flex justify-between items-start gap-4 mb-3">
          <div>
            <h2 className="card-title text-2xl text-white mb-2">
              <i className="fas fa-bitcoin-sign text-warning"></i>
              {opportunity.symbol}
            </h2>
            <div className={`badge badge-lg gap-2 ${getBadgeClass(opportunity.type)}`}>
              <i className={`fas ${getTypeIcon(opportunity.type)}`}></i>
              {renderTypeLabel(opportunity.type)}
            </div>
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-base-content/70 mb-4 leading-relaxed">
          <i className="fas fa-info-circle mr-2"></i>
          {opportunity.description}
        </p>

        {/* Execute Result */}
        {executeResult && (
          <div className={`alert ${executeResult.startsWith('✅') ? 'alert-success' : 'alert-error'} mb-4`}>
            <span className="text-sm">{executeResult}</span>
          </div>
        )}

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          {metrics.map((metric) => (
            <div key={metric.label} className="bg-base-100/80 rounded-lg p-3 border border-base-300/50">
              <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">
                {metric.label}
              </div>
              <div className="text-base font-semibold text-white">
                {metric.value}
              </div>
            </div>
          ))}
        </div>

        {/* Legs */}
        <div className="bg-base-100/80 rounded-lg p-4 border border-base-300/50 space-y-3 mb-4">
          {opportunity.legs.map((leg, index) => (
            <div key={index} className="flex justify-between items-center text-sm">
              <div className={`badge ${leg.side === "buy" ? "badge-success" : "badge-error"} gap-2`}>
                <i className={`fas ${leg.side === "buy" ? "fa-arrow-up" : "fa-arrow-down"}`}></i>
                {leg.side === "buy" ? "BUY / 매수" : "SELL / 매도"}
              </div>
              <div className="text-base-content/80">
                <span className="font-bold">{leg.exchange.toUpperCase()}</span>
                <span className="text-base-content/60"> · {renderVenueLabel(leg.venue_type)}</span>
              </div>
              <div className="text-right font-mono">
                <div className="text-white">{leg.price.toLocaleString()}</div>
                <div className="text-xs text-base-content/60">@ {leg.quantity.toFixed(4)}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Action Buttons */}
        <div className="card-actions justify-end gap-2">
          <button
            className="btn btn-sm btn-outline btn-info gap-2"
            onClick={() => handleExecute(true)}
            disabled={isExecuting || !authenticated}
            title={!authenticated ? "Login required / 로그인 필요" : "Simulate execution / 실행 시뮬레이션"}
          >
            {isExecuting ? (
              <>
                <i className="fas fa-spinner fa-spin"></i>
                Processing...
              </>
            ) : (
              <>
                <i className="fas fa-flask"></i>
                Dry Run / 시뮬레이션
              </>
            )}
          </button>
          <button
            className={`btn btn-sm gap-2 ${authenticated ? 'btn-error' : 'btn-disabled'}`}
            onClick={() => {
              if (window.confirm("Execute REAL orders? This will place actual trades! / 실제 주문을 체결하시겠습니까?")) {
                handleExecute(false);
              }
            }}
            disabled={isExecuting || !authenticated}
            title={!authenticated ? "Login required / 로그인 필요" : "Execute real orders / 실제 체결"}
          >
            {isExecuting ? (
              <>
                <i className="fas fa-spinner fa-spin"></i>
                Processing...
              </>
            ) : (
              <>
                <i className="fas fa-bolt"></i>
                Execute / 실행
              </>
            )}
          </button>
        </div>
      </div>
    </article>
  );
}

function getBadgeClass(type: Opportunity["type"]): string {
  switch (type) {
    case "spot_cross":
      return "badge-info";
    case "spot_vs_perp":
      return "badge-secondary";
    case "funding":
      return "badge-warning";
    case "kimchi_premium":
      return "badge-error";
    default:
      return "badge-ghost";
  }
}

function getTypeIcon(type: Opportunity["type"]): string {
  switch (type) {
    case "spot_cross":
      return "fa-exchange-alt";
    case "spot_vs_perp":
      return "fa-chart-area";
    case "funding":
      return "fa-coins";
    case "kimchi_premium":
      return "fa-pepper-hot";
    default:
      return "fa-question";
  }
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
