// Price data types
export interface PriceData {
  symbol: string;
  price: number;
  timestamp: number;
}

export interface FuturesData extends PriceData {
  indexPrice: number;
  markPrice: number;
  fundingRate: number;
  nextFundingTime: number;
}

export interface SpreadData {
  symbol: string;
  type: 'futures_gap' | 'cex_dex' | 'kimchi' | 'funding' | 'cex_arb';
  spreadPct: number;
  buyExchange: string;
  sellExchange: string;
  buyPrice: number;
  sellPrice: number;
  leverage?: number;
  timestamp: number;
  // Deposit/Withdraw status
  depositStatus?: {
    buy: boolean | null;  // Can deposit to buy exchange
    sell: boolean | null; // Can withdraw from sell exchange
  };
  tradeable?: boolean; // Both deposit and withdraw enabled
}

export interface AlertConfig {
  minSpreadPct: number;
  telegramChatId: string;
  telegramBotToken: string;
}

// Binance API response types
export interface BinanceFuturesTicker {
  symbol: string;
  lastPrice: string;
  indexPrice: string;
  markPrice: string;
}

export interface BinanceFundingRate {
  symbol: string;
  fundingRate: string;
  fundingTime: number;
}

export interface BinanceSpotTicker {
  symbol: string;
  price: string;
}

// DEX types
export interface DexPoolData {
  token0: string;
  token1: string;
  reserve0: string;
  reserve1: string;
  price: number;
}

// Alert types
export interface Alert {
  id: string;
  spread: SpreadData;
  sentAt: number;
  status: 'open' | 'closed';
  closedAt?: number;
}

// Monitoring config
export interface MonitorConfig {
  symbols: string[];
  futuresGapThreshold: number;  // e.g., 1.0 for 1%
  cexDexThreshold: number;
  kimchiThreshold: number;
  fundingThreshold: number;
  pollIntervalMs: number;
}

export const DEFAULT_CONFIG: MonitorConfig = {
  symbols: [
    'BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'SOLUSDT', 'DOGEUSDT',
    'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT', 'MATICUSDT',
    'UNIUSDT', 'LTCUSDT', 'BCHUSDT', 'ATOMUSDT', 'FILUSDT',
    'APTUSDT', 'ARBUSDT', 'OPUSDT', 'SUIUSDT', 'SEIUSDT',
    'FLOWUSDT', 'ONTUSDT', 'NEOUSDT', 'QTUMUSDT', 'ZILUSDT'
  ],
  futuresGapThreshold: 0.5,  // 0.5%
  cexDexThreshold: 5.0,      // 5%
  kimchiThreshold: 2.0,      // 2%
  fundingThreshold: 0.1,     // 0.1% per 8h
  pollIntervalMs: 3000,
};
