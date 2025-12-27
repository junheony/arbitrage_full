import axios from 'axios';

interface BingxTicker {
  symbol: string;
  lastPrice: string;
  volume: string;
}

interface BingxFuturesTicker {
  symbol: string;
  lastPrice: string;
  lastFundingRate: string;
}

// Fetch BingX spot tickers
export async function fetchBingxSpotTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://open-api.bingx.com/openApi/spot/v1/ticker/24hr', {
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as BingxTicker[]) {
        // BingX uses BTC-USDT format
        if (ticker.symbol.endsWith('-USDT')) {
          const symbol = ticker.symbol.replace('-', '');
          result.set(symbol, {
            price: parseFloat(ticker.lastPrice),
            symbol,
          });
        }
      }
    }

    console.log(`BingX spot: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('BingX spot fetch error:', error);
    return new Map();
  }
}

// Fetch BingX perpetual tickers
export async function fetchBingxPerpTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://open-api.bingx.com/openApi/swap/v2/quote/ticker', {
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as BingxFuturesTicker[]) {
        // BingX uses BTC-USDT format
        if (ticker.symbol.endsWith('-USDT')) {
          const symbol = ticker.symbol.replace('-', '');
          result.set(symbol, {
            price: parseFloat(ticker.lastPrice),
            symbol,
          });
        }
      }
    }

    console.log(`BingX perp: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('BingX perp fetch error:', error);
    return new Map();
  }
}

// Fetch BingX funding rates
export async function fetchBingxFundingRates(): Promise<Map<string, { rate: number; symbol: string }>> {
  try {
    const res = await axios.get('https://open-api.bingx.com/openApi/swap/v2/quote/ticker', {
      timeout: 5000,
    });

    const result = new Map<string, { rate: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as BingxFuturesTicker[]) {
        if (ticker.symbol.endsWith('-USDT') && ticker.lastFundingRate) {
          const symbol = ticker.symbol.replace('-', '');
          result.set(symbol, {
            rate: parseFloat(ticker.lastFundingRate) * 100,
            symbol,
          });
        }
      }
    }

    console.log(`BingX funding: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('BingX funding fetch error:', error);
    return new Map();
  }
}
