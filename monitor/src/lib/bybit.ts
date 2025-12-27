import axios from 'axios';

interface BybitTicker {
  symbol: string;
  lastPrice: string;
  price24hPcnt: string;
  volume24h: string;
}

interface BybitFundingRate {
  symbol: string;
  fundingRate: string;
  fundingRateTimestamp: string;
}

// Fetch Bybit spot tickers
export async function fetchBybitSpotTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.bybit.com/v5/market/tickers', {
      params: { category: 'spot' },
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.result?.list) {
      for (const ticker of res.data.result.list as BybitTicker[]) {
        if (ticker.symbol.endsWith('USDT')) {
          result.set(ticker.symbol, {
            price: parseFloat(ticker.lastPrice),
            symbol: ticker.symbol,
          });
        }
      }
    }

    console.log(`Bybit spot: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Bybit spot fetch error:', error);
    return new Map();
  }
}

// Fetch Bybit perpetual tickers
export async function fetchBybitPerpTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.bybit.com/v5/market/tickers', {
      params: { category: 'linear' },
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.result?.list) {
      for (const ticker of res.data.result.list as BybitTicker[]) {
        if (ticker.symbol.endsWith('USDT')) {
          result.set(ticker.symbol, {
            price: parseFloat(ticker.lastPrice),
            symbol: ticker.symbol,
          });
        }
      }
    }

    console.log(`Bybit perp: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Bybit perp fetch error:', error);
    return new Map();
  }
}

// Fetch Bybit funding rates
export async function fetchBybitFundingRates(): Promise<Map<string, { rate: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.bybit.com/v5/market/tickers', {
      params: { category: 'linear' },
      timeout: 5000,
    });

    const result = new Map<string, { rate: number; symbol: string }>();

    if (res.data?.result?.list) {
      for (const ticker of res.data.result.list as any[]) {
        if (ticker.symbol.endsWith('USDT') && ticker.fundingRate) {
          result.set(ticker.symbol, {
            rate: parseFloat(ticker.fundingRate) * 100, // Convert to percentage
            symbol: ticker.symbol,
          });
        }
      }
    }

    console.log(`Bybit funding: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Bybit funding fetch error:', error);
    return new Map();
  }
}
