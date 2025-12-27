import axios from 'axios';

interface OkxTicker {
  instId: string;
  last: string;
  vol24h: string;
}

interface OkxFundingRate {
  instId: string;
  fundingRate: string;
  fundingTime: string;
}

// Fetch OKX spot tickers
export async function fetchOkxSpotTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://www.okx.com/api/v5/market/tickers', {
      params: { instType: 'SPOT' },
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as OkxTicker[]) {
        // OKX uses BTC-USDT format, convert to BTCUSDT
        if (ticker.instId.endsWith('-USDT')) {
          const symbol = ticker.instId.replace('-', '');
          result.set(symbol, {
            price: parseFloat(ticker.last),
            symbol,
          });
        }
      }
    }

    console.log(`OKX spot: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('OKX spot fetch error:', error);
    return new Map();
  }
}

// Fetch OKX perpetual tickers
export async function fetchOkxPerpTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://www.okx.com/api/v5/market/tickers', {
      params: { instType: 'SWAP' },
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as OkxTicker[]) {
        // OKX uses BTC-USDT-SWAP format
        if (ticker.instId.includes('-USDT-SWAP')) {
          const symbol = ticker.instId.replace('-USDT-SWAP', 'USDT');
          result.set(symbol, {
            price: parseFloat(ticker.last),
            symbol,
          });
        }
      }
    }

    console.log(`OKX perp: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('OKX perp fetch error:', error);
    return new Map();
  }
}

// Fetch OKX funding rates
export async function fetchOkxFundingRates(): Promise<Map<string, { rate: number; symbol: string }>> {
  try {
    const res = await axios.get('https://www.okx.com/api/v5/public/funding-rate', {
      params: { instType: 'SWAP' },
      timeout: 5000,
    });

    const result = new Map<string, { rate: number; symbol: string }>();

    if (res.data?.data) {
      for (const item of res.data.data as OkxFundingRate[]) {
        if (item.instId.includes('-USDT-SWAP')) {
          const symbol = item.instId.replace('-USDT-SWAP', 'USDT');
          result.set(symbol, {
            rate: parseFloat(item.fundingRate) * 100,
            symbol,
          });
        }
      }
    }

    console.log(`OKX funding: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('OKX funding fetch error:', error);
    return new Map();
  }
}
