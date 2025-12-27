import axios from 'axios';

const UPBIT_API = 'https://api.upbit.com/v1';

export interface UpbitTicker {
  market: string;
  trade_price: number;
  signed_change_rate: number;
  acc_trade_volume_24h: number;
  timestamp: number;
}

// Fetch Upbit KRW market tickers
export async function fetchUpbitTickers(): Promise<Map<string, UpbitTicker>> {
  try {
    // Get market list first
    const marketsRes = await axios.get(`${UPBIT_API}/market/all`, { timeout: 5000 });
    const krwMarkets = marketsRes.data
      .filter((m: { market: string }) => m.market.startsWith('KRW-'))
      .map((m: { market: string }) => m.market)
      .join(',');

    // Get tickers
    const tickerRes = await axios.get<UpbitTicker[]>(`${UPBIT_API}/ticker`, {
      params: { markets: krwMarkets },
      timeout: 5000,
    });

    const result = new Map<string, UpbitTicker>();
    for (const t of tickerRes.data) {
      // Convert KRW-BTC to BTCUSDT format for matching
      const symbol = t.market.replace('KRW-', '') + 'USDT';
      result.set(symbol, t);
    }

    return result;
  } catch (error) {
    console.error('Upbit fetch error:', error);
    return new Map();
  }
}

// USD/KRW exchange rate from multiple sources
export async function fetchUsdKrwRate(): Promise<number> {
  // Try multiple sources in order
  const sources = [
    // 1. Dunamu API
    async () => {
      const res = await axios.get('https://quotation-api-cdn.dunamu.com/v1/forex/recent', {
        params: { codes: 'FRX.KRWUSD' },
        timeout: 3000,
      });
      if (res.data?.[0]?.basePrice) return res.data[0].basePrice;
      throw new Error('No data');
    },
    // 2. ExchangeRate API (free tier)
    async () => {
      const res = await axios.get('https://open.er-api.com/v6/latest/USD', { timeout: 3000 });
      if (res.data?.rates?.KRW) return res.data.rates.KRW;
      throw new Error('No data');
    },
    // 3. Calculate from BTC prices (implied rate)
    async () => {
      const [upbitRes, binanceRes] = await Promise.all([
        axios.get(`${UPBIT_API}/ticker`, { params: { markets: 'KRW-BTC' }, timeout: 3000 }),
        axios.get('https://api.binance.com/api/v3/ticker/price', { params: { symbol: 'BTCUSDT' }, timeout: 3000 }),
      ]);
      const upbitBtc = upbitRes.data?.[0]?.trade_price;
      const binanceBtc = parseFloat(binanceRes.data?.price);
      if (upbitBtc && binanceBtc) {
        // Implied rate = Upbit KRW price / Binance USD price
        return upbitBtc / binanceBtc;
      }
      throw new Error('No data');
    },
  ];

  for (const fetchRate of sources) {
    try {
      const rate = await fetchRate();
      if (rate && rate > 1000 && rate < 2000) { // Sanity check
        return rate;
      }
    } catch {
      continue;
    }
  }

  // Final fallback
  console.error('All forex sources failed, using hardcoded fallback');
  return 1450;
}

// Calculate Kimchi Premium
export function calculateKimchiPremium(
  upbitPriceKrw: number,
  binancePriceUsd: number,
  usdKrwRate: number
): number {
  if (!upbitPriceKrw || !binancePriceUsd || !usdKrwRate) return 0;

  const upbitPriceUsd = upbitPriceKrw / usdKrwRate;
  const premium = ((upbitPriceUsd - binancePriceUsd) / binancePriceUsd) * 100;

  // Sanity check - if premium is unreasonable, return 0
  if (isNaN(premium) || Math.abs(premium) > 50) return 0;

  return premium;
}
