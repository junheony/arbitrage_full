'use client';

import { useState, useEffect, useCallback } from 'react';

interface SpreadData {
  symbol: string;
  type: 'futures_gap' | 'kimchi' | 'funding' | 'cex_arb';
  spreadPct: number;
  buyExchange: string;
  sellExchange: string;
  buyPrice: number;
  sellPrice: number;
  leverage?: number;
  timestamp: number;
  tradeable?: boolean;
  depositStatus?: {
    buy: boolean | null;
    sell: boolean | null;
  };
}

interface Stats {
  total: number;
  futures_gap: { count: number; maxGap: number; avgGap: number };
  kimchi: { count: number; avgPremium: number; maxPremium: number };
  funding: { count: number; avgRate: number; maxRate: number };
  cex_arb: { count: number; avgSpread: number; maxSpread: number };
  usdKrwRate: number;
  exchanges?: Record<string, number>;
}

interface ApiResponse {
  success: boolean;
  timestamp: number;
  stats: Stats;
  spreads: SpreadData[];
}

type TabType = 'all' | 'futures_gap' | 'kimchi' | 'funding' | 'cex_arb';

export default function Home() {
  const [spreads, setSpreads] = useState<SpreadData[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number>(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>('all');

  const [minGap, setMinGap] = useState(0.5);
  const [minKimchi, setMinKimchi] = useState(1.5);
  const [minFunding, setMinFunding] = useState(0.05);
  const [minCex, setMinCex] = useState(0.5);

  const [showConfig, setShowConfig] = useState(false);
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');

  useEffect(() => {
    const saved = localStorage.getItem('monitor_config');
    if (saved) {
      const config = JSON.parse(saved);
      setBotToken(config.botToken || '');
      setChatId(config.chatId || '');
    }
  }, []);

  const saveConfig = () => {
    localStorage.setItem('monitor_config', JSON.stringify({ botToken, chatId }));
    setShowConfig(false);
  };

  const fetchSpreads = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        minGap: minGap.toString(),
        minKimchi: minKimchi.toString(),
        minFunding: minFunding.toString(),
        minCex: minCex.toString(),
      });
      const res = await fetch(`/api/spreads?${params}`);
      const data: ApiResponse = await res.json();

      if (data.success) {
        setSpreads(data.spreads);
        setStats(data.stats);
        setLastUpdate(data.timestamp);
        setError(null);
      } else {
        setError('Failed to fetch data');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, [minGap, minKimchi, minFunding, minCex]);

  useEffect(() => {
    fetchSpreads();
    if (autoRefresh) {
      const interval = setInterval(fetchSpreads, 3000);
      return () => clearInterval(interval);
    }
  }, [fetchSpreads, autoRefresh]);

  const sendTestAlert = async () => {
    if (!botToken || !chatId) {
      alert('Configure Telegram first');
      return;
    }
    try {
      const res = await fetch('/api/alert', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          botToken, chatId,
          message: '🧪 <b>Test Alert</b>\n모니터 연결 테스트',
        }),
      });
      const data = await res.json();
      alert(data.success ? 'Test sent!' : 'Failed');
    } catch { alert('Failed'); }
  };

  const formatTime = (ts: number) => {
    return new Date(ts).toLocaleTimeString('ko-KR', {
      timeZone: 'Asia/Seoul',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const filteredSpreads = activeTab === 'all'
    ? spreads
    : spreads.filter(s => s.type === activeTab);

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'futures_gap': return '시평갭';
      case 'kimchi': return '김프';
      case 'funding': return '펀딩';
      case 'cex_arb': return 'CEX';
      default: return type;
    }
  };

  const getRowClass = (type: string) => {
    switch (type) {
      case 'futures_gap': return 'row-futures';
      case 'kimchi': return 'row-kimchi';
      case 'funding': return 'row-funding';
      case 'cex_arb': return 'row-cex';
      default: return '';
    }
  };

  const getBadgeClass = (type: string) => {
    switch (type) {
      case 'futures_gap': return 'badge-futures';
      case 'kimchi': return 'badge-kimchi';
      case 'funding': return 'badge-funding';
      case 'cex_arb': return 'badge-cex';
      default: return '';
    }
  };

  const formatSpread = (s: SpreadData) => {
    const cls = s.spreadPct > 0 ? 'spread-positive' : 'spread-negative';
    if (s.type === 'funding') {
      return (
        <span className={cls}>
          {s.spreadPct > 0 ? '+' : ''}{s.spreadPct.toFixed(4)}%
          <span className="text-gray-500 text-xs ml-2">
            ({s.buyPrice > 0 ? '+' : ''}{s.buyPrice.toFixed(0)}%/yr)
          </span>
        </span>
      );
    }
    return (
      <span className={cls}>
        {s.spreadPct > 0 ? '+' : ''}{s.spreadPct.toFixed(2)}%
      </span>
    );
  };

  const getTabCount = (tab: TabType) => {
    if (!stats) return 0;
    switch (tab) {
      case 'futures_gap': return stats.futures_gap.count;
      case 'kimchi': return stats.kimchi.count;
      case 'funding': return stats.funding.count;
      case 'cex_arb': return stats.cex_arb?.count || 0;
      default: return 0;
    }
  };

  return (
    <div className="min-h-screen p-6 max-w-7xl mx-auto">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-white">
            ARB MONITOR
          </h1>
          <div className="flex items-center gap-4 text-sm text-gray-400">
            <span>{lastUpdate ? formatTime(lastUpdate) : '--:--:--'}</span>
            <button onClick={() => setShowConfig(!showConfig)}>
              Settings
            </button>
          </div>
        </div>

        {/* 김프 버튼 (메인) */}
        {stats && (
          <div
            className="kimchi-button mb-6"
            onClick={() => setActiveTab(activeTab === 'kimchi' ? 'all' : 'kimchi')}
          >
            <div className="kimchi-label">
              김프 <span className="kimchi-rate">₩{stats.usdKrwRate.toFixed(0)}</span>
            </div>
            <div className={`kimchi-value ${stats.kimchi.avgPremium >= 0 ? 'positive' : 'negative'}`}>
              {stats.kimchi.avgPremium >= 0 ? '+' : ''}{stats.kimchi.avgPremium.toFixed(2)}%
            </div>
            <div className="kimchi-sub">
              {stats.kimchi.count}개 종목 • max {stats.kimchi.maxPremium.toFixed(1)}%
            </div>
          </div>
        )}

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="stat-card">
              <div className="label">시평갭</div>
              <div className="value text-yellow-400">
                {stats.futures_gap.count}
                <span className="text-sm text-gray-500 ml-2">
                  max {stats.futures_gap.maxGap.toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="stat-card">
              <div className="label">펀딩비</div>
              <div className="value text-red-400">
                {stats.funding.count}
                <span className="text-sm text-gray-500 ml-2">
                  max {stats.funding.maxRate.toFixed(2)}%
                </span>
              </div>
            </div>
            <div className="stat-card">
              <div className="label">CEX 재정</div>
              <div className="value text-purple-400">
                {stats.cex_arb?.count || 0}
                <span className="text-sm text-gray-500 ml-2">
                  max {(stats.cex_arb?.maxSpread || 0).toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="stat-card">
              <div className="label">Total</div>
              <div className="value text-white">{stats.total}</div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {(['all', 'futures_gap', 'kimchi', 'funding', 'cex_arb'] as TabType[]).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`tab-button ${activeTab === tab ? `active tab-${tab === 'futures_gap' ? 'futures' : tab}` : ''}`}
            >
              {tab === 'all' ? 'ALL' : getTypeLabel(tab)}
              {tab !== 'all' && (
                <span className="ml-2 text-gray-500">
                  {getTabCount(tab)}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-4 items-center text-sm">
          <label className="flex items-center gap-2">
            <span className="text-gray-500">시평갭 ≥</span>
            <input type="number" value={minGap} onChange={(e) => setMinGap(parseFloat(e.target.value) || 0)} step="0.1" />
            <span className="text-gray-500">%</span>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-gray-500">김프 ≥</span>
            <input type="number" value={minKimchi} onChange={(e) => setMinKimchi(parseFloat(e.target.value) || 0)} step="0.5" />
            <span className="text-gray-500">%</span>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-gray-500">펀딩 ≥</span>
            <input type="number" value={minFunding} onChange={(e) => setMinFunding(parseFloat(e.target.value) || 0)} step="0.01" />
            <span className="text-gray-500">%</span>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-gray-500">CEX ≥</span>
            <input type="number" value={minCex} onChange={(e) => setMinCex(parseFloat(e.target.value) || 0)} step="0.1" />
            <span className="text-gray-500">%</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-4 h-4 accent-green-500"
            />
            <span className="text-gray-400">Auto</span>
          </label>
          <button onClick={fetchSpreads} disabled={loading}>
            Refresh
          </button>
        </div>
      </header>

      {/* Config Panel */}
      {showConfig && (
        <div className="card mb-6">
          <h2 className="text-sm mb-4 text-gray-400 font-semibold">Telegram Settings</h2>
          <div className="grid gap-4 max-w-md">
            <input
              type="password"
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              placeholder="Bot Token"
              className="w-full"
            />
            <input
              type="text"
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              placeholder="Chat ID"
              className="w-full"
            />
            <div className="flex gap-2">
              <button onClick={saveConfig}>Save</button>
              <button onClick={sendTestAlert}>Test</button>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="text-red-400 mb-4 p-4 border border-red-400/30 rounded-lg bg-red-400/10">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && spreads.length === 0 && (
        <div className="text-center py-16">
          <span className="loading text-gray-500">Loading...</span>
        </div>
      )}

      {/* Table */}
      {filteredSpreads.length > 0 && (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{width: '70px'}}>Type</th>
                <th style={{width: '100px'}}>Symbol</th>
                <th style={{width: '120px'}}>Spread</th>
                <th style={{width: '180px'}}>Route</th>
                <th>Buy</th>
                <th>Sell</th>
                <th style={{width: '130px'}}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredSpreads.map((s, i) => (
                <tr key={`${s.type}-${s.symbol}-${i}`} className={`${getRowClass(s.type)} ${s.tradeable === false ? 'opacity-50' : ''}`}>
                  <td>
                    <span className={`badge ${getBadgeClass(s.type)}`}>
                      {getTypeLabel(s.type)}
                    </span>
                  </td>
                  <td>
                    <span className="symbol-name">{s.symbol.replace('USDT', '')}</span>
                  </td>
                  <td>{formatSpread(s)}</td>
                  <td>
                    <div className="flex items-center gap-1 text-sm">
                      <span className="text-blue-400">{s.buyExchange}</span>
                      <span className="text-gray-600">→</span>
                      <span className="text-orange-400">{s.sellExchange}</span>
                    </div>
                  </td>
                  <td className="price">
                    {s.type === 'funding' ? '-' : `$${s.buyPrice.toFixed(s.buyPrice < 1 ? 4 : 2)}`}
                  </td>
                  <td className="price">
                    {s.type === 'funding' ? '-' : `$${s.sellPrice.toFixed(s.sellPrice < 1 ? 4 : 2)}`}
                  </td>
                  <td>
                    {s.type === 'kimchi' ? (
                      <div className="text-xs">
                        {Math.abs(s.spreadPct) > 10 ? (
                          <span className="text-red-400 font-medium">⚠ 중단의심</span>
                        ) : (
                          <div className="flex flex-col gap-0.5">
                            <span className="text-gray-500">
                              {s.buyExchange}: <span className={s.depositStatus?.buy === true ? 'text-green-400' : s.depositStatus?.buy === false ? 'text-red-400' : 'text-yellow-400'}>{s.depositStatus?.buy === true ? '출금✓' : s.depositStatus?.buy === false ? '출금✗' : '?'}</span>
                            </span>
                            <span className="text-gray-500">
                              {s.sellExchange}: <span className={s.depositStatus?.sell === true ? 'text-green-400' : s.depositStatus?.sell === false ? 'text-red-400' : 'text-yellow-400'}>{s.depositStatus?.sell === true ? '입금✓' : s.depositStatus?.sell === false ? '입금✗' : '?'}</span>
                            </span>
                          </div>
                        )}
                      </div>
                    ) : s.type === 'futures_gap' ? (
                      <span className="text-xs text-gray-500">{s.leverage}x</span>
                    ) : s.type === 'cex_arb' ? (
                      <span className="text-xs text-purple-400">Cross-CEX</span>
                    ) : (
                      <span className="text-xs text-gray-500">
                        {s.spreadPct > 0 ? 'Long→' : 'Short→'}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty */}
      {!loading && filteredSpreads.length === 0 && !error && (
        <div className="text-center py-16 text-gray-500">
          No opportunities above threshold
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 text-center text-xs text-gray-600">
        v0.3.0 • Binance • Bybit • OKX • Gate • Bitget • BingX • Upbit
      </footer>
    </div>
  );
}
