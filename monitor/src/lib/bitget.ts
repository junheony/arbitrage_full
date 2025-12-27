import axios from 'axios';

interface BitgetTicker {
  symbol: string;
  lastPr: string;
  baseVolume: string;
}

interface BitgetFuturesTicker {
  symbol: string;
  lastPr: string;
  fundingRate: string;
}

// Fetch Bitget spot tickers
export async function fetchBitgetSpotTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.bitget.com/api/v2/spot/market/tickers', {
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as BitgetTicker[]) {
        if (ticker.symbol.endsWith('USDT')) {
          result.set(ticker.symbol, {
            price: parseFloat(ticker.lastPr),
            symbol: ticker.symbol,
          });
        }
      }
    }

    console.log(`Bitget spot: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Bitget spot fetch error:', error);
    return new Map();
  }
}

// Fetch Bitget perpetual tickers
export async function fetchBitgetPerpTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.bitget.com/api/v2/mix/market/tickers', {
      params: { productType: 'USDT-FUTURES' },
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as BitgetFuturesTicker[]) {
        // Bitget uses BTCUSDT format
        if (ticker.symbol.endsWith('USDT')) {
          result.set(ticker.symbol, {
            price: parseFloat(ticker.lastPr),
            symbol: ticker.symbol,
          });
        }
      }
    }

    console.log(`Bitget perp: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Bitget perp fetch error:', error);
    return new Map();
  }
}

// Fetch Bitget funding rates
export async function fetchBitgetFundingRates(): Promise<Map<string, { rate: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.bitget.com/api/v2/mix/market/tickers', {
      params: { productType: 'USDT-FUTURES' },
      timeout: 5000,
    });

    const result = new Map<string, { rate: number; symbol: string }>();

    if (res.data?.data) {
      for (const ticker of res.data.data as BitgetFuturesTicker[]) {
        if (ticker.symbol.endsWith('USDT') && ticker.fundingRate) {
          result.set(ticker.symbol, {
            rate: parseFloat(ticker.fundingRate) * 100,
            symbol: ticker.symbol,
          });
        }
      }
    }

    console.log(`Bitget funding: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Bitget funding fetch error:', error);
    return new Map();
  }
}
