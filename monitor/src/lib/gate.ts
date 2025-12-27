import axios from 'axios';

interface GateTicker {
  currency_pair: string;
  last: string;
  base_volume: string;
}

interface GateFuturesTicker {
  contract: string;
  last: string;
  funding_rate: string;
}

// Fetch Gate.io spot tickers
export async function fetchGateSpotTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.gateio.ws/api/v4/spot/tickers', {
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (Array.isArray(res.data)) {
      for (const ticker of res.data as GateTicker[]) {
        // Gate uses BTC_USDT format
        if (ticker.currency_pair.endsWith('_USDT')) {
          const symbol = ticker.currency_pair.replace('_', '');
          result.set(symbol, {
            price: parseFloat(ticker.last),
            symbol,
          });
        }
      }
    }

    console.log(`Gate spot: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Gate spot fetch error:', error);
    return new Map();
  }
}

// Fetch Gate.io perpetual tickers
export async function fetchGatePerpTickers(): Promise<Map<string, { price: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.gateio.ws/api/v4/futures/usdt/tickers', {
      timeout: 5000,
    });

    const result = new Map<string, { price: number; symbol: string }>();

    if (Array.isArray(res.data)) {
      for (const ticker of res.data as GateFuturesTicker[]) {
        // Gate uses BTC_USDT format for futures too
        if (ticker.contract.endsWith('_USDT')) {
          const symbol = ticker.contract.replace('_', '');
          result.set(symbol, {
            price: parseFloat(ticker.last),
            symbol,
          });
        }
      }
    }

    console.log(`Gate perp: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Gate perp fetch error:', error);
    return new Map();
  }
}

// Fetch Gate.io funding rates
export async function fetchGateFundingRates(): Promise<Map<string, { rate: number; symbol: string }>> {
  try {
    const res = await axios.get('https://api.gateio.ws/api/v4/futures/usdt/tickers', {
      timeout: 5000,
    });

    const result = new Map<string, { rate: number; symbol: string }>();

    if (Array.isArray(res.data)) {
      for (const ticker of res.data as GateFuturesTicker[]) {
        if (ticker.contract.endsWith('_USDT') && ticker.funding_rate) {
          const symbol = ticker.contract.replace('_', '');
          result.set(symbol, {
            rate: parseFloat(ticker.funding_rate) * 100,
            symbol,
          });
        }
      }
    }

    console.log(`Gate funding: ${result.size} pairs loaded`);
    return result;
  } catch (error) {
    console.error('Gate funding fetch error:', error);
    return new Map();
  }
}
