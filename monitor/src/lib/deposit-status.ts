import axios from 'axios';
import crypto from 'crypto';
import { v4 as uuidv4 } from 'uuid';

interface DepositStatus {
  symbol: string;
  exchange: string;
  depositEnabled: boolean;
  withdrawEnabled: boolean;
  network?: string;
}

// Generate Upbit JWT token
function generateUpbitToken(): string | null {
  const accessKey = process.env.UPBIT_ACCESS_KEY;
  const secretKey = process.env.UPBIT_SECRET_KEY;

  if (!accessKey || !secretKey) {
    return null;
  }

  const payload = {
    access_key: accessKey,
    nonce: uuidv4(),
  };

  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const signature = crypto.createHmac('sha256', secretKey).update(`${header}.${body}`).digest('base64url');

  return `${header}.${body}.${signature}`;
}

// Generate Binance signature
function generateBinanceSignature(queryString: string): string | null {
  const secretKey = process.env.BINANCE_SECRET_KEY;
  if (!secretKey) return null;
  return crypto.createHmac('sha256', secretKey).update(queryString).digest('hex');
}

// Binance capital config response
interface BinanceCoinInfo {
  coin: string;
  depositAllEnable: boolean;
  withdrawAllEnable: boolean;
  name: string;
  free: string;
  locked: string;
  freeze: string;
  withdrawing: string;
  ipoing: string;
  ipoable: string;
  storage: string;
  isLegalMoney: boolean;
  trading: boolean;
}

// Binance deposit/withdraw status with authentication
export async function fetchBinanceDepositStatus(): Promise<Map<string, DepositStatus>> {
  try {
    const apiKey = process.env.BINANCE_API_KEY;
    const secretKey = process.env.BINANCE_SECRET_KEY;

    // If no API key, use public API as fallback
    if (!apiKey || !secretKey) {
      console.log('No Binance API key configured, using public API');
      return fetchBinancePublicStatus();
    }

    const timestamp = Date.now();
    const queryString = `timestamp=${timestamp}`;
    const signature = generateBinanceSignature(queryString);

    const res = await axios.get<BinanceCoinInfo[]>('https://api.binance.com/sapi/v1/capital/config/getall', {
      params: {
        timestamp,
        signature,
      },
      headers: {
        'X-MBX-APIKEY': apiKey,
      },
      timeout: 5000,
    });

    const result = new Map<string, DepositStatus>();
    for (const coin of res.data) {
      result.set(coin.coin + 'USDT', {
        symbol: coin.coin,
        exchange: 'binance',
        depositEnabled: coin.depositAllEnable,
        withdrawEnabled: coin.withdrawAllEnable,
      });
    }

    console.log(`Binance wallet status: ${result.size} coins loaded`);
    return result;
  } catch (error) {
    console.error('Binance wallet status fetch error:', error);
    return fetchBinancePublicStatus();
  }
}

// Fallback: Binance public API (trading status only)
async function fetchBinancePublicStatus(): Promise<Map<string, DepositStatus>> {
  try {
    const res = await axios.get('https://api.binance.com/api/v3/exchangeInfo', { timeout: 5000 });

    const result = new Map<string, DepositStatus>();
    for (const symbol of res.data.symbols) {
      if (symbol.quoteAsset !== 'USDT') continue;

      const baseAsset = symbol.baseAsset;
      const isTrading = symbol.status === 'TRADING';

      result.set(baseAsset + 'USDT', {
        symbol: baseAsset,
        exchange: 'binance',
        depositEnabled: isTrading, // Approximation
        withdrawEnabled: isTrading,
      });
    }

    return result;
  } catch (error) {
    console.error('Binance public status fetch error:', error);
    return new Map();
  }
}

// Upbit wallet status response
interface UpbitWalletStatus {
  currency: string;
  wallet_state: 'working' | 'withdraw_only' | 'deposit_only' | 'paused' | 'unsupported';
  block_state: 'normal' | 'delayed' | 'inactive';
  block_height: number | null;
  block_updated_at: string | null;
  block_elapsed_minutes: number | null;
}

// Upbit wallet status via backend proxy (fixed IP required by Upbit)
// Falls back to empty map if proxy unavailable - will show "?" in UI
export async function fetchUpbitDepositStatus(): Promise<Map<string, DepositStatus>> {
  const proxyUrl = process.env.UPBIT_PROXY_URL;

  // If no proxy URL configured, return empty (Upbit status unknown)
  if (!proxyUrl) {
    console.log('No UPBIT_PROXY_URL configured, Upbit wallet status will show as unknown');
    return new Map();
  }

  try {
    const proxyToken = process.env.UPBIT_PROXY_TOKEN || '';

    console.log(`Fetching Upbit wallet status via proxy: ${proxyUrl}`);

    // Cloudflare Worker responds at root path with token as query param
    const url = proxyToken ? `${proxyUrl}?token=${proxyToken}` : proxyUrl;

    const res = await axios.get<{
      success: boolean;
      count: number;
      data: Record<string, { deposit: boolean; withdraw: boolean; state: string }>;
    }>(url, {
      timeout: 10000,
    });

    if (!res.data.success) {
      console.error('Upbit proxy returned error');
      return new Map();
    }

    console.log(`Upbit proxy response: ${res.data.count} currencies`);

    const result = new Map<string, DepositStatus>();
    for (const [currency, status] of Object.entries(res.data.data)) {
      result.set(currency + 'USDT', {
        symbol: currency,
        exchange: 'upbit',
        depositEnabled: status.deposit,
        withdrawEnabled: status.withdraw,
      });
    }

    return result;
  } catch (error: unknown) {
    const axiosError = error as { response?: { status?: number; data?: unknown } };
    console.error('Upbit proxy fetch error:', {
      message: error instanceof Error ? error.message : 'Unknown',
      status: axiosError.response?.status,
    });
    return new Map();
  }
}

// Combined status
export interface CombinedDepositStatus {
  symbol: string;
  binance: { deposit: boolean; withdraw: boolean } | null;
  upbit: { deposit: boolean; withdraw: boolean } | null;
  tradeable: boolean; // Can execute arbitrage
}

export async function fetchAllDepositStatus(): Promise<Map<string, CombinedDepositStatus>> {
  const [binanceStatus, upbitStatus] = await Promise.all([
    fetchBinanceDepositStatus(),
    fetchUpbitDepositStatus(),
  ]);

  const result = new Map<string, CombinedDepositStatus>();
  const allSymbols = new Set([...binanceStatus.keys(), ...upbitStatus.keys()]);

  for (const symbol of allSymbols) {
    const binance = binanceStatus.get(symbol);
    const upbit = upbitStatus.get(symbol);

    // Tradeable if:
    // - Binance deposit/withdraw enabled
    // - Upbit deposit/withdraw enabled
    const tradeable = !!(
      binance?.depositEnabled && binance?.withdrawEnabled &&
      upbit?.depositEnabled && upbit?.withdrawEnabled
    );

    result.set(symbol, {
      symbol: symbol.replace('USDT', ''),
      binance: binance ? { deposit: binance.depositEnabled, withdraw: binance.withdrawEnabled } : null,
      upbit: upbit ? { deposit: upbit.depositEnabled, withdraw: upbit.withdrawEnabled } : null,
      tradeable,
    });
  }

  return result;
}
