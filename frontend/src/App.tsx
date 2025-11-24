import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useMemo, useState, useEffect } from "react";
import { useOpportunities } from "./hooks/useOpportunities";
import { usePositions } from "./hooks/usePositions";
import type { Opportunity } from "./types";
import { isAuthenticated, clearToken } from "./auth";
import { executeOpportunity, closePosition } from "./api";
import { LoginModal } from "./LoginModal";

dayjs.extend(relativeTime);

type SortField = 'spread_bps' | 'expected_pnl_pct' | 'timestamp' | 'notional';
type SortOrder = 'asc' | 'desc';
type ViewMode = 'compact' | 'detailed';

function App() {
  const { opportunities, isLoading, error, lastUpdated } = useOpportunities();
  const { positions, stats } = usePositions();
  const [showLogin, setShowLogin] = useState(false);
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  const [sortField, setSortField] = useState<SortField>('expected_pnl_pct');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('compact');
  const [showPositions, setShowPositions] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const filteredAndSortedOpportunities = useMemo(() => {
    let filtered = opportunities;

    if (typeFilter !== 'all') {
      filtered = filtered.filter(opp => opp.type === typeFilter);
    }

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

  // Calculate average kimchi premium from metadata
  const avgKimchiPremium = useMemo(() => {
    const kimchiOpps = opportunities.filter(o => o.type === 'kimchi_premium');
    if (kimchiOpps.length === 0) return null;

    // Get avg from metadata (all opportunities should have same avg)
    const firstOpp = kimchiOpps[0];
    return firstOpp.metadata?.premium_pct ?? null;
  }, [opportunities]);

  const handleLogout = () => {
    clearToken();
    setAuthenticated(false);
  };

  const handleLoginSuccess = () => {
    setShowLogin(false);
    setAuthenticated(true);
  };

  return (
    <div className="min-h-screen p-4 lg:p-6">
      {/* Terminal Header */}
      <header className="terminal-card mb-4 p-4 scanline">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          {/* Title Section */}
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex gap-1">
                <div className="w-3 h-3 rounded-full bg-red-500 pulse-dot"></div>
                <div className="w-3 h-3 rounded-full bg-yellow-500 pulse-dot" style={{animationDelay: '0.3s'}}></div>
                <div className="w-3 h-3 rounded-full bg-green-500 pulse-dot" style={{animationDelay: '0.6s'}}></div>
              </div>
              <h1 className="text-2xl lg:text-3xl font-bold terminal-text text-green-400 glow-green">
                ARBITRAGE COMMAND CENTER
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs terminal-text text-gray-400">
              <span>김프 · 펀딩 · 현선 레이더</span>
              <span>|</span>
              <span>{currentTime.toLocaleTimeString('ko-KR')}</span>
              <span>|</span>
              <span className={lastUpdated ? 'text-green-400' : 'text-red-400'}>
                {lastUpdated ? `LIVE · ${dayjs(lastUpdated).fromNow()}` : 'OFFLINE'}
              </span>
            </div>
          </div>

          {/* Stats Section */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="terminal-card px-4 py-2">
              <div className="text-[10px] text-gray-500 terminal-text">MAX SPREAD</div>
              <div className="text-xl font-bold terminal-text text-green-400 glow-green">
                {topSpread ? `${topSpread.toFixed(2)}` : "--"} <span className="text-sm">bps</span>
              </div>
            </div>

            {avgKimchiPremium !== null && (
              <div className="terminal-card px-4 py-2">
                <div className="text-[10px] text-gray-500 terminal-text">AVG 김프</div>
                <div className={`text-xl font-bold terminal-text ${
                  avgKimchiPremium >= 0
                    ? 'text-blue-400 glow-blue'
                    : 'text-purple-400 glow-purple'
                }`}>
                  {avgKimchiPremium >= 0 ? '+' : ''}{avgKimchiPremium.toFixed(2)}<span className="text-sm">%</span>
                </div>
              </div>
            )}

            {authenticated && stats && (
              <div className="terminal-card px-4 py-2">
                <div className="text-[10px] text-gray-500 terminal-text">OPEN PNL</div>
                <div className={`text-xl font-bold terminal-text ${stats.open_pnl_usd >= 0 ? 'text-green-400 glow-green' : 'text-red-400 glow-red'}`}>
                  ${stats.open_pnl_usd.toFixed(2)}
                </div>
                <div className="text-[10px] text-gray-500 terminal-text">{stats.open_positions} positions</div>
              </div>
            )}

            <button
              onClick={() => authenticated ? handleLogout() : setShowLogin(true)}
              className={`px-4 py-2 terminal-text text-sm font-semibold border ${
                authenticated
                  ? 'border-red-500 text-red-400 hover:bg-red-500/10'
                  : 'border-green-500 text-green-400 hover:bg-green-500/10'
              } transition-all`}
            >
              {authenticated ? '⏻ LOGOUT' : '⏻ LOGIN'}
            </button>
          </div>
        </div>
      </header>

      <LoginModal
        isOpen={showLogin}
        onClose={() => setShowLogin(false)}
        onSuccess={handleLoginSuccess}
      />

      {error && (
        <div className="terminal-card border-red-500 bg-red-500/10 p-3 mb-4">
          <span className="text-red-400 terminal-text text-sm">⚠ ERROR: {error}</span>
        </div>
      )}

      {/* Controls */}
      <section className="terminal-card mb-4 p-3">
        <div className="flex flex-wrap gap-2 items-center justify-between text-xs terminal-text">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-gray-500">FILTER:</span>
            <button
              onClick={() => setTypeFilter('all')}
              className={`px-3 py-1 border transition-all ${
                typeFilter === 'all'
                  ? 'border-green-500 bg-green-500/20 text-green-400'
                  : 'border-gray-700 text-gray-400 hover:border-gray-500'
              }`}
            >
              ALL [{opportunities.length}]
            </button>
            {opportunityTypes.map(type => (
              <button
                key={type}
                onClick={() => setTypeFilter(type)}
                className={`px-3 py-1 border transition-all ${
                  typeFilter === type
                    ? 'border-green-500 bg-green-500/20 text-green-400'
                    : 'border-gray-700 text-gray-400 hover:border-gray-500'
                }`}
              >
                {getTypeShort(type)} [{opportunities.filter(o => o.type === type).length}]
              </button>
            ))}
          </div>

          <div className="flex gap-2 items-center">
            <span className="text-gray-500">SORT:</span>
            <select
              className="bg-transparent border border-gray-700 text-gray-400 px-2 py-1 text-xs terminal-text"
              value={sortField}
              onChange={(e) => setSortField(e.target.value as SortField)}
            >
              <option value="expected_pnl_pct">PNL %</option>
              <option value="spread_bps">SPREAD</option>
              <option value="notional">SIZE</option>
              <option value="timestamp">TIME</option>
            </select>
            <button
              onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
              className="border border-gray-700 text-gray-400 px-2 py-1 hover:border-gray-500"
            >
              {sortOrder === 'asc' ? '↑' : '↓'}
            </button>
            <button
              onClick={() => setViewMode(viewMode === 'compact' ? 'detailed' : 'compact')}
              className="border border-gray-700 text-gray-400 px-2 py-1 hover:border-gray-500"
            >
              {viewMode === 'compact' ? 'COMPACT' : 'DETAIL'}
            </button>
          </div>
        </div>
      </section>

      {/* Open Positions */}
      {authenticated && positions.length > 0 && (
        <section className="terminal-card mb-4 p-3">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold terminal-text text-blue-400 glow-blue">
              ◈ OPEN POSITIONS [{positions.length}]
            </h2>
            <button
              onClick={() => setShowPositions(!showPositions)}
              className="text-xs terminal-text text-gray-400 hover:text-gray-300"
            >
              {showPositions ? '▲ HIDE' : '▼ SHOW'}
            </button>
          </div>

          {showPositions && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs terminal-text">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-800">
                    <th className="text-left py-2 px-2">SYMBOL</th>
                    <th className="text-left py-2 px-2">TYPE</th>
                    <th className="text-right py-2 px-2">ENTRY</th>
                    <th className="text-right py-2 px-2">PNL %</th>
                    <th className="text-right py-2 px-2">PNL $</th>
                    <th className="text-right py-2 px-2">TARGET</th>
                    <th className="text-right py-2 px-2">STOP</th>
                    <th className="text-left py-2 px-2">LEGS</th>
                    <th className="text-center py-2 px-2">ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position) => (
                    <tr key={position.id} className="data-row border-b border-gray-900">
                      <td className="py-2 px-2 font-bold text-white">{position.symbol}</td>
                      <td className="py-2 px-2 text-gray-400">{position.position_type.replace('_', ' ')}</td>
                      <td className="py-2 px-2 text-right text-gray-400">
                        {dayjs(position.entry_time).format('HH:mm')}
                      </td>
                      <td className={`py-2 px-2 text-right font-bold ${position.current_pnl_pct >= 0 ? 'text-green-400 glow-green' : 'text-red-400 glow-red'}`}>
                        {position.current_pnl_pct >= 0 ? '+' : ''}{position.current_pnl_pct.toFixed(2)}%
                      </td>
                      <td className={`py-2 px-2 text-right font-bold ${position.current_pnl_usd >= 0 ? 'text-green-400 glow-green' : 'text-red-400 glow-red'}`}>
                        {position.current_pnl_usd >= 0 ? '+' : ''}{position.current_pnl_usd.toFixed(2)}
                      </td>
                      <td className="py-2 px-2 text-right text-green-400">+{position.target_profit_pct}%</td>
                      <td className="py-2 px-2 text-right text-red-400">-{position.stop_loss_pct}%</td>
                      <td className="py-2 px-2 text-gray-400">
                        {position.entry_legs.map((leg, idx) => (
                          <span key={idx} className="mr-2">{leg.exchange}</span>
                        ))}
                      </td>
                      <td className="py-2 px-2 text-center">
                        <button
                          onClick={async () => {
                            if (confirm(`Close ${position.symbol}?`)) {
                              try {
                                await closePosition(position.id);
                              } catch (error) {
                                alert(`Failed: ${error}`);
                              }
                            }
                          }}
                          className="border border-red-500 text-red-400 px-2 py-1 text-[10px] hover:bg-red-500/10"
                        >
                          CLOSE
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

      {/* Opportunities Table */}
      {isLoading && opportunities.length === 0 ? (
        <div className="terminal-card p-12 text-center">
          <div className="text-green-400 terminal-text mb-2 glow-green">
            <span className="animate-pulse">█████ LOADING DATA STREAM █████</span>
          </div>
          <p className="text-gray-500 terminal-text text-xs">Connecting to market feeds...</p>
        </div>
      ) : filteredAndSortedOpportunities.length === 0 ? (
        <div className="terminal-card p-12 text-center">
          <p className="text-gray-500 terminal-text">
            {opportunities.length === 0
              ? "[ NO EXECUTABLE OPPORTUNITIES ]"
              : "[ NO MATCHES FOR FILTER ]"}
          </p>
        </div>
      ) : (
        <section className="terminal-card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs terminal-text">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800 bg-gray-900/50">
                  <th className="text-left py-3 px-3 sticky left-0 bg-gray-900/95">SYMBOL</th>
                  <th className="text-left py-3 px-2">TYPE</th>
                  <th className="text-right py-3 px-2">PNL %</th>
                  <th className="text-right py-3 px-2">SPREAD</th>
                  <th className="text-right py-3 px-2">FUNDING 24H</th>
                  <th className="text-right py-3 px-2">SIZE</th>
                  <th className="text-left py-3 px-2">LEGS</th>
                  <th className="text-right py-3 px-2">TIME</th>
                  <th className="text-center py-3 px-3">EXEC</th>
                </tr>
              </thead>
              <tbody>
                {filteredAndSortedOpportunities.map((opportunity, idx) => (
                  <OpportunityRow
                    key={opportunity.id}
                    opportunity={opportunity}
                    index={idx}
                    viewMode={viewMode}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Footer Stats */}
      <footer className="mt-4 text-center text-xs terminal-text text-gray-600">
        <span>{filteredAndSortedOpportunities.length} opportunities displayed</span>
        {' · '}
        <span>Last update: {lastUpdated ? dayjs(lastUpdated).format('HH:mm:ss') : '--:--:--'}</span>
      </footer>
    </div>
  );
}

interface OpportunityRowProps {
  opportunity: Opportunity;
  index: number;
  viewMode: ViewMode;
}

function OpportunityRow({ opportunity, index, viewMode }: OpportunityRowProps) {
  const [isExecuting, setIsExecuting] = useState(false);
  const [executeResult, setExecuteResult] = useState<string | null>(null);
  const authenticated = isAuthenticated();

  const handleExecute = async (dryRun: boolean = false) => {
    if (!authenticated) {
      alert("Please login first");
      return;
    }

    setIsExecuting(true);
    setExecuteResult(null);

    try {
      const result = await executeOpportunity({
        opportunity_id: opportunity.id,
        dry_run: dryRun,
      });

      setExecuteResult(`✓ ${result.message}`);
      setTimeout(() => setExecuteResult(null), 5000);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed';
      setExecuteResult(`✗ ${errorMessage}`);
      setTimeout(() => setExecuteResult(null), 8000);
    } finally {
      setIsExecuting(false);
    }
  };

  const rowColor = index % 2 === 0 ? 'bg-gray-900/30' : 'bg-transparent';

  return (
    <>
      <tr className={`data-row border-b border-gray-900 ${rowColor}`}>
        <td className="py-2 px-3 font-bold text-white sticky left-0 bg-inherit">
          {opportunity.symbol}
        </td>
        <td className="py-2 px-2">
          <span className={`px-2 py-0.5 border text-[10px] ${getTypeBorderClass(opportunity.type)}`}>
            {getTypeShort(opportunity.type)}
          </span>
        </td>
        <td className="py-2 px-2 text-right font-bold text-green-400 glow-green">
          +{opportunity.expected_pnl_pct.toFixed(3)}%
        </td>
        <td className="py-2 px-2 text-right text-gray-300">
          {opportunity.spread_bps.toFixed(2)} bps
        </td>
        <td className="py-2 px-2 text-right">
          {opportunity.metadata?.funding_rate_24h_pct !== undefined ? (
            <span className={
              opportunity.metadata.funding_rate_24h_pct > 0
                ? 'text-red-400'  // Paying funding
                : opportunity.metadata.funding_rate_24h_pct < 0
                ? 'text-green-400'  // Receiving funding
                : 'text-gray-400'
            }>
              {opportunity.metadata.funding_rate_24h_pct > 0 ? '-' : '+'}
              {Math.abs(opportunity.metadata.funding_rate_24h_pct).toFixed(3)}%
            </span>
          ) : (
            <span className="text-gray-600">--</span>
          )}
        </td>
        <td className="py-2 px-2 text-right text-gray-300">
          ${(opportunity.notional/1000).toFixed(1)}k
        </td>
        <td className="py-2 px-2">
          {viewMode === 'compact' ? (
            <span className="text-gray-400">
              {opportunity.legs.map((leg, idx) => (
                <span key={idx} className="mr-2">
                  <span className={leg.side === 'buy' ? 'text-green-400' : 'text-red-400'}>
                    {leg.side === 'buy' ? '↑' : '↓'}
                  </span>
                  <span className={
                    isKoreanExchange(leg.exchange)
                      ? 'text-orange-400 font-bold'
                      : 'text-blue-300'
                  }>
                    {getExchangeShort(leg.exchange)}
                  </span>
                  {idx < opportunity.legs.length - 1 && opportunity.type === 'kimchi_premium' && (
                    <span className="text-gray-600 mx-1">vs</span>
                  )}
                </span>
              ))}
            </span>
          ) : (
            <div className="flex flex-col gap-0.5">
              {opportunity.legs.map((leg, idx) => (
                <div key={idx} className="flex items-center gap-1">
                  <span className={leg.side === 'buy' ? 'text-green-400' : 'text-red-400'}>
                    {leg.side === 'buy' ? '↑' : '↓'}
                  </span>
                  <span className={
                    isKoreanExchange(leg.exchange)
                      ? 'text-orange-400 font-bold'
                      : 'text-blue-300'
                  }>
                    {getExchangeShort(leg.exchange)}
                  </span>
                  <span className="text-gray-500">@{formatPrice(leg.price)}</span>
                </div>
              ))}
            </div>
          )}
        </td>
        <td className="py-2 px-2 text-right text-gray-500">
          {dayjs(opportunity.timestamp).format("HH:mm:ss")}
        </td>
        <td className="py-2 px-3 text-center">
          <div className="flex gap-1 justify-center">
            <button
              className="border border-blue-500 text-blue-400 px-2 py-1 text-[10px] hover:bg-blue-500/10 disabled:opacity-30"
              onClick={() => handleExecute(true)}
              disabled={isExecuting || !authenticated}
              title="Dry run"
            >
              TEST
            </button>
            <button
              className="border border-red-500 text-red-400 px-2 py-1 text-[10px] hover:bg-red-500/10 disabled:opacity-30"
              onClick={() => {
                if (window.confirm("Execute REAL orders?")) {
                  handleExecute(false);
                }
              }}
              disabled={isExecuting || !authenticated}
              title="Execute"
            >
              EXEC
            </button>
          </div>
        </td>
      </tr>
      {executeResult && (
        <tr className={rowColor}>
          <td colSpan={9} className="py-1 px-3">
            <div className={`text-[10px] ${executeResult.startsWith('✓') ? 'text-green-400' : 'text-red-400'}`}>
              {executeResult}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function formatPrice(price: number): string {
  if (price >= 1000) {
    return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } else if (price >= 1) {
    return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  } else {
    return price.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  }
}

function getExchangeShort(exchange: string): string {
  const shorts: Record<string, string> = {
    binance: "⚡ BINANCE",
    binance_spot: "⚡ BINANCE",
    binance_perp: "⚡ BIN-PERP",
    bybit: "📊 BYBIT",
    okx: "🔷 OKX",
    upbit: "🇰🇷 UPBIT",
    bithumb: "🇰🇷 BITHUMB",
    hyperliquid: "💧 HYPERL",
    lighter: "⚡ LIGHTER",
    edgex: "🔺 EDGEX",
    exchangerate_api: "💱 FX",
    dunamu_fx: "💱 FX",
  };
  return shorts[exchange.toLowerCase()] || exchange.toUpperCase();
}

function isKoreanExchange(exchange: string): boolean {
  const lowerExchange = exchange.toLowerCase();
  return lowerExchange === 'upbit' || lowerExchange === 'bithumb';
}

function getTypeShort(type: Opportunity["type"]): string {
  switch (type) {
    case "spot_cross":
      return "SPOT-X";
    case "spot_vs_perp":
      return "SPOT-PERP";
    case "funding_arb":
      return "FUNDING";
    case "perp_perp_spread":
      return "PERP-PERP";
    case "kimchi_premium":
      return "KIMCHI";
    default:
      return (type as string).toUpperCase();
  }
}

function getTypeBorderClass(type: Opportunity["type"]): string {
  switch (type) {
    case "spot_cross":
      return "border-blue-500 text-blue-400";
    case "spot_vs_perp":
      return "border-purple-500 text-purple-400";
    case "funding_arb":
      return "border-yellow-500 text-yellow-400";
    case "perp_perp_spread":
      return "border-cyan-500 text-cyan-400";
    case "kimchi_premium":
      return "border-red-500 text-red-400";
    default:
      return "border-gray-500 text-gray-400";
  }
}

export default App;
