import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useMemo, useState } from "react";
import { useOpportunities } from "./hooks/useOpportunities";
import { usePositions } from "./hooks/usePositions";
import type { Opportunity, OpportunityMetadata } from "./types";
import { isAuthenticated, clearToken } from "./auth";
import { executeOpportunity, closePosition } from "./api";
import { LoginModal } from "./LoginModal";

dayjs.extend(relativeTime);

type SortField = 'spread_bps' | 'expected_pnl_pct' | 'timestamp' | 'notional';
type SortOrder = 'asc' | 'desc';
type ViewMode = 'grid' | 'table';

function App() {
  const { opportunities, isLoading, error, lastUpdated } = useOpportunities();
  const { positions, stats } = usePositions();
  const [showLogin, setShowLogin] = useState(false);
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  const [sortField, setSortField] = useState<SortField>('expected_pnl_pct');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [showPositions, setShowPositions] = useState(false);

  const filteredAndSortedOpportunities = useMemo(() => {
    let filtered = opportunities;

    // Apply type filter
    if (typeFilter !== 'all') {
      filtered = filtered.filter(opp => opp.type === typeFilter);
    }

    // Apply sorting
    return [...filtered].sort((a, b) => {
      let aVal = a[sortField];
      let bVal = b[sortField];

      if (sortField === 'timestamp') {
        aVal = new Date(a.timestamp).getTime();
        bVal = new Date(b.timestamp).getTime();
      }

      if (sortOrder === 'asc') {
        return aVal > bVal ? 1 : -1;
      } else {
        return aVal < bVal ? 1 : -1;
      }
    });
  }, [opportunities, sortField, sortOrder, typeFilter]);

  const topSpread = useMemo(
    () => filteredAndSortedOpportunities[0]?.spread_bps ?? 0,
    [filteredAndSortedOpportunities],
  );

  const opportunityTypes = useMemo(() => {
    const types = new Set(opportunities.map(o => o.type));
    return Array.from(types);
  }, [opportunities]);

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
          <h1 className="text-3xl lg:text-4xl font-bold text-white mb-2">
            📈 Arbitrage Command / 아비트리지 커맨드
          </h1>
          <p className="text-sm text-base-content/60">
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
                {lastUpdated
                  ? dayjs(lastUpdated).fromNow()
                  : "Awaiting data / 데이터 수신 중"}
              </div>
            </div>
            {authenticated && stats && (
              <div className="stat py-4 px-6">
                <div className="stat-title text-xs">Open PnL / 미실현 손익</div>
                <div className={`stat-value text-2xl ${stats.open_pnl_usd >= 0 ? 'text-success' : 'text-error'}`}>
                  ${stats.open_pnl_usd.toFixed(2)}
                </div>
                <div className="stat-desc text-xs">
                  {stats.open_positions} open / {stats.open_positions}개 포지션
                </div>
              </div>
            )}
          </div>
          <div>
            {authenticated ? (
              <button
                onClick={handleLogout}
                className="btn btn-error btn-sm lg:btn-md"
              >
                Logout / 로그아웃
              </button>
            ) : (
              <button
                onClick={() => setShowLogin(true)}
                className="btn btn-primary btn-sm lg:btn-md"
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

      {error && (
        <div className="alert alert-error shadow-lg mb-6">
          <span>⚠️ {error}</span>
        </div>
      )}

      {/* Filters and Controls */}
      <section className="mb-6 bg-base-200/80 rounded-xl p-6 border border-base-300">
        <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between">
          {/* Type Filter */}
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-sm font-semibold text-base-content/80">Type:</span>
            <button
              onClick={() => setTypeFilter('all')}
              className={`btn btn-sm ${typeFilter === 'all' ? 'btn-primary' : 'btn-ghost'}`}
            >
              All ({opportunities.length})
            </button>
            {opportunityTypes.map(type => (
              <button
                key={type}
                onClick={() => setTypeFilter(type)}
                className={`btn btn-sm ${typeFilter === type ? 'btn-primary' : 'btn-ghost'}`}
              >
                {renderTypeLabel(type)} ({opportunities.filter(o => o.type === type).length})
              </button>
            ))}
          </div>

          {/* Sort Controls */}
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-sm font-semibold text-base-content/80">Sort:</span>
            <select
              className="select select-sm select-bordered"
              value={sortField}
              onChange={(e) => setSortField(e.target.value as SortField)}
            >
              <option value="expected_pnl_pct">Expected PNL %</option>
              <option value="spread_bps">Spread (bps)</option>
              <option value="notional">Notional</option>
              <option value="timestamp">Time</option>
            </select>
            <button
              onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
              className="btn btn-sm btn-ghost"
              title={sortOrder === 'asc' ? 'Ascending' : 'Descending'}
            >
              {sortOrder === 'asc' ? '↑' : '↓'}
            </button>
            <button
              onClick={() => setViewMode(viewMode === 'grid' ? 'table' : 'grid')}
              className="btn btn-sm btn-ghost"
              title={viewMode === 'grid' ? 'Switch to table view' : 'Switch to grid view'}
            >
              {viewMode === 'grid' ? '📊' : '🔲'}
            </button>
          </div>
        </div>
      </section>

      {/* Open Positions Section */}
      {authenticated && positions.length > 0 && (
        <section className="mb-6 bg-base-200/80 rounded-xl p-6 border border-base-300">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-white">
              📊 Open Positions / 오픈 포지션 ({positions.length})
            </h2>
            <button
              onClick={() => setShowPositions(!showPositions)}
              className="btn btn-sm btn-ghost"
            >
              {showPositions ? '▲ Hide / 숨기기' : '▼ Show / 보기'}
            </button>
          </div>

          {showPositions && (
            <div className="overflow-x-auto">
              <table className="table table-zebra w-full">
                <thead>
                  <tr className="text-base-content/80">
                    <th>Symbol / 심볼</th>
                    <th>Type / 유형</th>
                    <th>Entry / 진입</th>
                    <th>PnL % / 손익률</th>
                    <th>PnL $ / 손익</th>
                    <th>Target / 목표</th>
                    <th>Stop / 손절</th>
                    <th>Legs / 레그</th>
                    <th>Actions / 액션</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position) => (
                    <tr key={position.id} className="hover">
                      <td className="font-semibold">{position.symbol}</td>
                      <td>
                        <span className="badge badge-sm badge-outline">
                          {position.position_type.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="text-xs">
                        {dayjs(position.entry_time).format('MM/DD HH:mm')}
                        <br />
                        <span className="text-base-content/50">
                          ${position.entry_notional.toLocaleString()}
                        </span>
                      </td>
                      <td>
                        <span className={`font-semibold ${position.current_pnl_pct >= 0 ? 'text-success' : 'text-error'}`}>
                          {position.current_pnl_pct >= 0 ? '+' : ''}{position.current_pnl_pct.toFixed(2)}%
                        </span>
                      </td>
                      <td>
                        <span className={`font-semibold ${position.current_pnl_usd >= 0 ? 'text-success' : 'text-error'}`}>
                          {position.current_pnl_usd >= 0 ? '+$' : '-$'}
                          {Math.abs(position.current_pnl_usd).toFixed(2)}
                        </span>
                      </td>
                      <td className="text-xs text-success">+{position.target_profit_pct}%</td>
                      <td className="text-xs text-error">-{position.stop_loss_pct}%</td>
                      <td className="text-xs">
                        {position.entry_legs.map((leg, idx) => (
                          <div key={idx} className="text-base-content/60">
                            {leg.exchange} {leg.side}
                          </div>
                        ))}
                      </td>
                      <td>
                        <button
                          onClick={async () => {
                            if (confirm(`Close position for ${position.symbol}? / ${position.symbol} 포지션을 청산하시겠습니까?`)) {
                              try {
                                await closePosition(position.id);
                                alert('Position close request submitted / 포지션 청산 요청 제출됨');
                              } catch (error) {
                                alert(`Failed to close position: ${error} / 포지션 청산 실패`);
                              }
                            }
                          }}
                          className="btn btn-xs btn-error"
                        >
                          Close / 청산
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Opportunities Display */}
      {isLoading && opportunities.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 bg-base-200/50 rounded-2xl border-2 border-dashed border-base-300">
          <span className="loading loading-spinner loading-lg text-primary mb-4"></span>
          <p className="text-base-content/60">Loading live opportunities… / 실시간 기회를 불러오는 중…</p>
        </div>
      ) : filteredAndSortedOpportunities.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 bg-base-200/50 rounded-2xl border-2 border-dashed border-base-300">
          <p className="text-4xl mb-4">🔍</p>
          <p className="text-base-content/60">
            {opportunities.length === 0
              ? "No executable spreads right now / 현재 체결 가능한 스프레드가 없습니다."
              : "No opportunities matching filters / 필터 조건에 맞는 기회가 없습니다."}
          </p>
        </div>
      ) : viewMode === 'grid' ? (
        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredAndSortedOpportunities.map((opportunity) => (
            <OpportunityCard key={opportunity.id} opportunity={opportunity} />
          ))}
        </section>
      ) : (
        <section className="overflow-x-auto">
          <table className="table table-zebra w-full bg-base-200/80">
            <thead>
              <tr className="text-base-content/80">
                <th>Type</th>
                <th>Symbol</th>
                <th>PNL %</th>
                <th>Spread (bps)</th>
                <th>Notional</th>
                <th>Legs</th>
                <th>Time</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredAndSortedOpportunities.map((opportunity) => (
                <OpportunityRow key={opportunity.id} opportunity={opportunity} />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

interface OpportunityCardProps {
  opportunity: Opportunity;
}

function OpportunityRow({ opportunity }: OpportunityCardProps) {
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

      // Auto-clear result after 5 seconds
      setTimeout(() => setExecuteResult(null), 5000);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Execution failed / 실행 실패';
      setExecuteResult(`❌ ${errorMessage}`);

      // Auto-clear error after 8 seconds
      setTimeout(() => setExecuteResult(null), 8000);
    } finally {
      // Always reset executing state
      setIsExecuting(false);
    }
  };

  return (
    <tr className="hover">
      <td>
        <div className={`badge badge-sm ${getBadgeClass(opportunity.type)}`}>
          {renderTypeLabel(opportunity.type).split(' / ')[0]}
        </div>
      </td>
      <td className="font-semibold whitespace-nowrap">{opportunity.symbol}</td>
      <td className="text-success font-bold whitespace-nowrap">{opportunity.expected_pnl_pct.toFixed(3)}%</td>
      <td className="whitespace-nowrap">{opportunity.spread_bps.toFixed(2)}</td>
      <td className="whitespace-nowrap">${(opportunity.notional/1000).toFixed(1)}k</td>
      <td className="text-xs min-w-[200px]">
        {opportunity.legs.map((leg, idx) => (
          <div key={idx} className="flex items-center gap-1.5 mb-1">
            <span className={leg.side === 'buy' ? 'text-success font-bold' : 'text-error font-bold'}>
              {leg.side === 'buy' ? '↑' : '↓'}
            </span>
            <span className="text-sm">{getExchangeLogo(leg.exchange)}</span>
            <span className="font-bold text-white">{getExchangeLabel(leg.exchange)}</span>
            <span className="text-base-content/60">@{formatPrice(leg.price)}</span>
          </div>
        ))}
      </td>
      <td className="text-xs whitespace-nowrap">{dayjs(opportunity.timestamp).format("HH:mm:ss")}</td>
      <td>
        <div className="flex gap-1">
          <button
            className="btn btn-xs btn-info"
            onClick={() => handleExecute(true)}
            disabled={isExecuting || !authenticated}
            title="Dry run"
          >
            🧪
          </button>
          <button
            className="btn btn-xs btn-error"
            onClick={() => {
              if (window.confirm("Execute REAL orders?")) {
                handleExecute(false);
              }
            }}
            disabled={isExecuting || !authenticated}
            title="Execute"
          >
            ⚡
          </button>
        </div>
      </td>
    </tr>
  );
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

      // Auto-clear result after 5 seconds
      setTimeout(() => setExecuteResult(null), 5000);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Execution failed / 실행 실패';
      setExecuteResult(`❌ ${errorMessage}`);

      // Auto-clear error after 8 seconds
      setTimeout(() => setExecuteResult(null), 8000);
    } finally {
      // Always reset executing state
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

  // Get primary exchange for card styling
  const primaryExchange = opportunity.legs[0]?.exchange || "default";
  const cardColorClass = getExchangeColor(primaryExchange);

  return (
    <article className={`card bg-gradient-to-br ${cardColorClass} shadow border hover:shadow-lg transition-all duration-150`}>
      <div className="card-body p-4">
        {/* Compact Header with Exchange Logo */}
        <div className="flex justify-between items-center mb-2 gap-2">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className="text-2xl shrink-0">{getExchangeLogo(primaryExchange)}</span>
            <div className="min-w-0 flex-1">
              <h3 className="font-bold text-base text-white truncate">{opportunity.symbol}</h3>
              <div className="text-xs text-base-content/60 truncate">{getExchangeLabel(primaryExchange)}</div>
            </div>
            <div className={`badge badge-sm ${getBadgeClass(opportunity.type)} shrink-0`}>
              {renderTypeLabel(opportunity.type).split(' / ')[0]}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-lg font-bold text-success whitespace-nowrap">{opportunity.expected_pnl_pct.toFixed(3)}%</div>
            <div className="text-xs text-base-content/60 whitespace-nowrap">{opportunity.spread_bps.toFixed(1)} bps</div>
          </div>
        </div>

        {/* Execute Result */}
        {executeResult && (
          <div className={`alert alert-sm ${executeResult.startsWith('✅') ? 'alert-success' : 'alert-error'} py-2 mb-2`}>
            <span className="text-xs">{executeResult}</span>
          </div>
        )}

        {/* Compact Legs with Exchange Logos */}
        <div className="space-y-1 mb-3">
          {opportunity.legs.map((leg, index) => (
            <div key={index} className="flex justify-between items-center text-xs bg-base-100/60 rounded px-2 py-1 gap-2">
              <div className="flex items-center gap-1.5 min-w-0 flex-1">
                <span className={leg.side === "buy" ? "text-success font-bold text-sm" : "text-error font-bold text-sm"}>
                  {leg.side === "buy" ? "↑" : "↓"}
                </span>
                <span className="text-base shrink-0">{getExchangeLogo(leg.exchange)}</span>
                <span className="font-bold text-white truncate">{getExchangeLabel(leg.exchange)}</span>
                <span className="text-base-content/50 text-[10px] whitespace-nowrap">{renderVenueLabel(leg.venue_type).split(' / ')[0]}</span>
              </div>
              <div className="font-mono text-right whitespace-nowrap shrink-0">
                <span className="text-white font-semibold">{formatPrice(leg.price)}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Compact Metrics */}
        <div className="grid grid-cols-3 gap-2 mb-3 text-xs">
          <div className="bg-base-100/60 rounded px-2 py-1">
            <div className="text-base-content/50">Notional</div>
            <div className="font-semibold">${(opportunity.notional/1000).toFixed(1)}k</div>
          </div>
          <div className="bg-base-100/60 rounded px-2 py-1">
            <div className="text-base-content/50">Time</div>
            <div className="font-semibold">{dayjs(opportunity.timestamp).format("HH:mm:ss")}</div>
          </div>
          {metadata?.target_allocation_pct !== undefined && (
            <div className="bg-base-100/60 rounded px-2 py-1">
              <div className="text-base-content/50">Alloc</div>
              <div className="font-semibold">{metadata.target_allocation_pct.toFixed(0)}%</div>
            </div>
          )}
        </div>

        {/* Compact Action Buttons */}
        <div className="flex gap-2">
          <button
            className="btn btn-xs btn-outline btn-info flex-1"
            onClick={() => handleExecute(true)}
            disabled={isExecuting || !authenticated}
            title="Dry run"
          >
            {isExecuting ? <span className="loading loading-spinner loading-xs"></span> : "🧪 Test"}
          </button>
          <button
            className={`btn btn-xs flex-1 ${authenticated ? 'btn-error' : 'btn-disabled'}`}
            onClick={() => {
              if (window.confirm("Execute REAL orders?")) {
                handleExecute(false);
              }
            }}
            disabled={isExecuting || !authenticated}
            title="Execute"
          >
            {isExecuting ? <span className="loading loading-spinner loading-xs"></span> : "⚡ Execute"}
          </button>
        </div>
      </div>
    </article>
  );
}

function formatPrice(price: number): string {
  // Smart price formatting based on magnitude
  if (price >= 1000) {
    return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } else if (price >= 1) {
    return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 5 });
  } else if (price >= 0.01) {
    return price.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  } else {
    return price.toLocaleString(undefined, { minimumFractionDigits: 6, maximumFractionDigits: 8 });
  }
}

function getSymbolEmoji(symbol: string): string {
  if (symbol.includes("BTC")) return "₿";
  if (symbol.includes("ETH")) return "Ξ";
  if (symbol.includes("XRP")) return "✕";
  return "💱";
}

function getExchangeLabel(exchange: string): string {
  const labels: Record<string, string> = {
    binance: "Binance",
    bybit: "Bybit",
    okx: "OKX",
    upbit: "Upbit",
    bithumb: "Bithumb",
    hyperliquid: "Hyperliquid",
    lighter: "Lighter",
    edgex: "EdgeX",
  };
  return labels[exchange.toLowerCase()] || exchange.toUpperCase();
}

function getExchangeLogo(exchange: string): string {
  const logos: Record<string, string> = {
    binance: "🟡",
    bybit: "🟠",
    okx: "⚫",
    upbit: "🔵",
    bithumb: "🟢",
    hyperliquid: "🟣",
    lighter: "⚪",
    edgex: "🔴",
  };
  return logos[exchange.toLowerCase()] || "📊";
}

function getExchangeColor(exchange: string): string {
  const colors: Record<string, string> = {
    binance: "from-yellow-500/10 to-yellow-600/5 border-yellow-500/30",
    bybit: "from-orange-500/10 to-orange-600/5 border-orange-500/30",
    okx: "from-slate-500/10 to-slate-600/5 border-slate-500/30",
    upbit: "from-blue-500/10 to-blue-600/5 border-blue-500/30",
    bithumb: "from-green-500/10 to-green-600/5 border-green-500/30",
    hyperliquid: "from-purple-500/10 to-purple-600/5 border-purple-500/30",
    lighter: "from-gray-500/10 to-gray-600/5 border-gray-500/30",
    edgex: "from-red-500/10 to-red-600/5 border-red-500/30",
  };
  return colors[exchange.toLowerCase()] || "from-base-200/90 to-base-300/70 border-base-300";
}

function getBadgeClass(type: Opportunity["type"]): string {
  switch (type) {
    case "spot_cross":
      return "badge-info";
    case "spot_vs_perp":
      return "badge-secondary";
    case "funding_arb":
      return "badge-warning";
    case "perp_perp_spread":
      return "badge-accent";
    case "kimchi_premium":
      return "badge-error";
    default:
      return "badge-ghost";
  }
}

function renderTypeLabel(type: Opportunity["type"]): string {
  switch (type) {
    case "spot_cross":
      return "Spot cross / 현물 교차";
    case "spot_vs_perp":
      return "Spot vs perp basis / 현선 베이시스";
    case "funding_arb":
      return "Funding arb / 펀딩 차익";
    case "perp_perp_spread":
      return "Perp spread / 선물 스프레드";
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
