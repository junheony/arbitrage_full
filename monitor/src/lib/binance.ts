import axios from 'axios';
import type {
  FuturesData,
  PriceData,
  BinanceFuturesTicker,
  BinanceFundingRate,
  BinanceSpotTicker,
  SpreadData
} from './types';

const FUTURES_BASE = 'https://fapi.binance.com';
const SPOT_BASE = 'https://api.binance.com';

// Fetch all futures tickers with index prices
export async function fetchFuturesTickers(): Promise<Map<string, FuturesData>> {
  const [tickerRes, fundingRes] = await Promise.all([
    axios.get<BinanceFuturesTicker[]>(`${FUTURES_BASE}/fapi/v1/ticker/24hr`),
    axios.get<BinanceFundingRate[]>(`${FUTURES_BASE}/fapi/v1/fundingRate`),
  ]);

  const fundingMap = new Map<string, BinanceFundingRate>();
  for (const f of fundingRes.data) {
    fundingMap.set(f.symbol, f);
  }

  const result = new Map<string, FuturesData>();
  const now = Date.now();

  for (const t of tickerRes.data) {
    const funding = fundingMap.get(t.symbol);
    result.set(t.symbol, {
      symbol: t.symbol,
      price: parseFloat(t.lastPrice),
      indexPrice: parseFloat(t.indexPrice),
      markPrice: parseFloat(t.markPrice),
      fundingRate: funding ? parseFloat(funding.fundingRate) : 0,
      nextFundingTime: funding ? funding.fundingTime : 0,
      timestamp: now,
    });
  }

  return result;
}

// Fetch spot prices
export async function fetchSpotTickers(): Promise<Map<string, PriceData>> {
  const res = await axios.get<BinanceSpotTicker[]>(`${SPOT_BASE}/api/v3/ticker/price`);

  const result = new Map<string, PriceData>();
  const now = Date.now();

  for (const t of res.data) {
    result.set(t.symbol, {
      symbol: t.symbol,
      price: parseFloat(t.price),
      timestamp: now,
    });
  }

  return result;
}

// Calculate futures gap (시평갭)
export function calculateFuturesGap(futuresData: FuturesData): SpreadData {
  const gapPct = ((futuresData.price - futuresData.indexPrice) / futuresData.indexPrice) * 100;

  return {
    symbol: futuresData.symbol,
    type: 'futures_gap',
    spreadPct: gapPct,
    buyExchange: gapPct > 0 ? 'binance_spot' : 'binance_futures',
    sellExchange: gapPct > 0 ? 'binance_futures' : 'binance_spot',
    buyPrice: gapPct > 0 ? futuresData.indexPrice : futuresData.price,
    sellPrice: gapPct > 0 ? futuresData.price : futuresData.indexPrice,
    timestamp: futuresData.timestamp,
  };
}

// Get max leverage for symbol (simplified)
export function getMaxLeverage(symbol: string): number {
  const highLeverageSymbols = ['BTCUSDT', 'ETHUSDT'];
  if (highLeverageSymbols.includes(symbol)) return 125;

  const mediumLeverageSymbols = ['XRPUSDT', 'SOLUSDT', 'DOGEUSDT', 'ADAUSDT'];
  if (mediumLeverageSymbols.includes(symbol)) return 75;

  return 50; // Default for altcoins
}

// Find all significant futures gaps
export async function findFuturesGaps(minGapPct: number = 0.5): Promise<SpreadData[]> {
  const futures = await fetchFuturesTickers();
  const gaps: SpreadData[] = [];

  for (const [symbol, data] of futures) {
    if (!symbol.endsWith('USDT')) continue;

    const gap = calculateFuturesGap(data);
    gap.leverage = getMaxLeverage(symbol);

    if (Math.abs(gap.spreadPct) >= minGapPct) {
      gaps.push(gap);
    }
  }

  // Sort by absolute spread descending
  gaps.sort((a, b) => Math.abs(b.spreadPct) - Math.abs(a.spreadPct));

  return gaps;
}

// Fetch premium index (more accurate gap calculation)
export async function fetchPremiumIndex(symbol: string): Promise<{
  symbol: string;
  markPrice: number;
  indexPrice: number;
  lastFundingRate: number;
  interestRate: number;
  nextFundingTime: number;
} | null> {
  try {
    const res = await axios.get(`${FUTURES_BASE}/fapi/v1/premiumIndex`, {
      params: { symbol }
    });
    return {
      symbol: res.data.symbol,
      markPrice: parseFloat(res.data.markPrice),
      indexPrice: parseFloat(res.data.indexPrice),
      lastFundingRate: parseFloat(res.data.lastFundingRate),
      interestRate: parseFloat(res.data.interestRate),
      nextFundingTime: res.data.nextFundingTime,
    };
  } catch {
    return null;
  }
}

// Batch fetch premium index for multiple symbols
export async function fetchAllPremiumIndex(): Promise<Map<string, {
  symbol: string;
  markPrice: number;
  indexPrice: number;
  lastFundingRate: number;
  nextFundingTime: number;
  gapPct: number;
}>> {
  const res = await axios.get(`${FUTURES_BASE}/fapi/v1/premiumIndex`);
  const result = new Map();

  for (const item of res.data) {
    const markPrice = parseFloat(item.markPrice);
    const indexPrice = parseFloat(item.indexPrice);
    const gapPct = ((markPrice - indexPrice) / indexPrice) * 100;

    result.set(item.symbol, {
      symbol: item.symbol,
      markPrice,
      indexPrice,
      lastFundingRate: parseFloat(item.lastFundingRate),
      nextFundingTime: item.nextFundingTime,
      gapPct,
    });
  }

  return result;
}
