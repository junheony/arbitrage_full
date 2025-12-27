import { NextResponse } from 'next/server';
import { fetchAllPremiumIndex, getMaxLeverage, fetchSpotTickers } from '@/lib/binance';
import { fetchUpbitTickers, fetchUsdKrwRate, calculateKimchiPremium } from '@/lib/upbit';
import { fetchUpbitDepositStatus, fetchBinanceDepositStatus } from '@/lib/deposit-status';
import { fetchBybitSpotTickers, fetchBybitFundingRates } from '@/lib/bybit';
import { fetchOkxSpotTickers, fetchOkxFundingRates } from '@/lib/okx';
import { fetchGateSpotTickers, fetchGateFundingRates } from '@/lib/gate';
import { fetchBitgetSpotTickers, fetchBitgetFundingRates } from '@/lib/bitget';
import { fetchBingxSpotTickers, fetchBingxFundingRates } from '@/lib/bingx';
import type { SpreadData } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type ExchangeName = 'Binance' | 'Bybit' | 'OKX' | 'Gate' | 'Bitget' | 'BingX' | 'Upbit';

interface ExchangePrice {
  exchange: ExchangeName;
  price: number;
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const minGap = parseFloat(searchParams.get('minGap') || '0.3');
    const minKimchi = parseFloat(searchParams.get('minKimchi') || '1.0');
    const minFunding = parseFloat(searchParams.get('minFunding') || '0.05');
    const minCex = parseFloat(searchParams.get('minCex') || '0.5'); // CEX arbitrage threshold
    const types = searchParams.get('types')?.split(',') || ['futures_gap', 'kimchi', 'funding', 'cex_arb'];

    const now = Date.now();
    const spreads: SpreadData[] = [];

    // Fetch all data in parallel
    const [
      premiumIndex,
      binanceSpot,
      upbitTickers,
      usdKrwRate,
      upbitWalletStatus,
      binanceWalletStatus,
      bybitSpot,
      bybitFunding,
      okxSpot,
      okxFunding,
      gateSpot,
      gateFunding,
      bitgetSpot,
      bitgetFunding,
      bingxSpot,
      bingxFunding,
    ] = await Promise.all([
      fetchAllPremiumIndex(),
      fetchSpotTickers(),
      fetchUpbitTickers(),
      fetchUsdKrwRate(),
      fetchUpbitDepositStatus(),
      fetchBinanceDepositStatus(),
      fetchBybitSpotTickers(),
      fetchBybitFundingRates(),
      fetchOkxSpotTickers(),
      fetchOkxFundingRates(),
      fetchGateSpotTickers(),
      fetchGateFundingRates(),
      fetchBitgetSpotTickers(),
      fetchBitgetFundingRates(),
      fetchBingxSpotTickers(),
      fetchBingxFundingRates(),
    ]);

    // 1. Futures Gap (시평갭) - Binance only
    if (types.includes('futures_gap')) {
      for (const [symbol, data] of premiumIndex) {
        if (!symbol.endsWith('USDT')) continue;

        const gapPct = data.gapPct;
        if (Math.abs(gapPct) < minGap) continue;

        spreads.push({
          symbol,
          type: 'futures_gap',
          spreadPct: gapPct,
          buyExchange: gapPct > 0 ? 'Binance Index' : 'Binance Perp',
          sellExchange: gapPct > 0 ? 'Binance Perp' : 'Binance Index',
          buyPrice: data.indexPrice,
          sellPrice: data.markPrice,
          leverage: getMaxLeverage(symbol),
          timestamp: now,
          tradeable: true,
        });
      }
    }

    // 2. Kimchi Premium (김치프리미엄)
    if (types.includes('kimchi')) {
      for (const [symbol, upbitData] of upbitTickers) {
        const binanceData = binanceSpot.get(symbol);
        if (!binanceData) continue;

        const kimchiPct = calculateKimchiPremium(
          upbitData.trade_price,
          binanceData.price,
          usdKrwRate
        );

        if (Math.abs(kimchiPct) < minKimchi || kimchiPct === 0) continue;

        const upbitStatus = upbitWalletStatus.get(symbol);
        const binanceStatus = binanceWalletStatus.get(symbol);

        const upbitDeposit = upbitStatus?.depositEnabled ?? null;
        const upbitWithdraw = upbitStatus?.withdrawEnabled ?? null;
        const binanceDeposit = binanceStatus?.depositEnabled ?? null;
        const binanceWithdraw = binanceStatus?.withdrawEnabled ?? null;

        const depositStatus = kimchiPct > 0
          ? { buy: binanceWithdraw, sell: upbitDeposit }
          : { buy: upbitWithdraw, sell: binanceDeposit };

        const isTradeable = depositStatus.buy === true && depositStatus.sell === true;

        spreads.push({
          symbol,
          type: 'kimchi',
          spreadPct: kimchiPct,
          buyExchange: kimchiPct > 0 ? 'Binance' : 'Upbit',
          sellExchange: kimchiPct > 0 ? 'Upbit' : 'Binance',
          buyPrice: binanceData.price,
          sellPrice: upbitData.trade_price / usdKrwRate,
          timestamp: now,
          depositStatus,
          tradeable: isTradeable,
        });
      }
    }

    // 3. Funding Rate (펀딩비) - All exchanges
    if (types.includes('funding')) {
      // Collect all funding rates by symbol
      const allFundingRates = new Map<string, { exchange: ExchangeName; rate: number }[]>();

      const addFunding = (
        rates: Map<string, { rate: number; symbol: string }>,
        exchange: ExchangeName
      ) => {
        for (const [symbol, data] of rates) {
          if (!allFundingRates.has(symbol)) {
            allFundingRates.set(symbol, []);
          }
          allFundingRates.get(symbol)!.push({ exchange, rate: data.rate });
        }
      };

      // Add Binance funding from premium index
      for (const [symbol, data] of premiumIndex) {
        if (!allFundingRates.has(symbol)) {
          allFundingRates.set(symbol, []);
        }
        allFundingRates.get(symbol)!.push({
          exchange: 'Binance',
          rate: data.lastFundingRate * 100,
        });
      }

      addFunding(bybitFunding, 'Bybit');
      addFunding(okxFunding, 'OKX');
      addFunding(gateFunding, 'Gate');
      addFunding(bitgetFunding, 'Bitget');
      addFunding(bingxFunding, 'BingX');

      // Find highest funding rate for each symbol
      for (const [symbol, rates] of allFundingRates) {
        if (rates.length === 0) continue;

        // Sort by absolute rate
        rates.sort((a, b) => Math.abs(b.rate) - Math.abs(a.rate));
        const best = rates[0];

        if (Math.abs(best.rate) < minFunding) continue;

        const annualizedPct = best.rate * 3 * 365;

        spreads.push({
          symbol,
          type: 'funding',
          spreadPct: best.rate,
          buyExchange: best.rate > 0 ? 'Spot' : `${best.exchange} Perp`,
          sellExchange: best.rate > 0 ? `${best.exchange} Perp` : 'Spot',
          buyPrice: annualizedPct,
          sellPrice: 0,
          leverage: getMaxLeverage(symbol),
          timestamp: now,
          tradeable: true,
        });
      }
    }

    // 4. CEX Arbitrage (거래소간 재정거래)
    if (types.includes('cex_arb')) {
      // Collect all spot prices by symbol
      const allSpotPrices = new Map<string, ExchangePrice[]>();

      const addPrices = (
        tickers: Map<string, { price: number; symbol: string }>,
        exchange: ExchangeName
      ) => {
        for (const [symbol, data] of tickers) {
          if (!symbol.endsWith('USDT')) continue;
          if (!allSpotPrices.has(symbol)) {
            allSpotPrices.set(symbol, []);
          }
          allSpotPrices.get(symbol)!.push({ exchange, price: data.price });
        }
      };

      addPrices(binanceSpot, 'Binance');
      addPrices(bybitSpot, 'Bybit');
      addPrices(okxSpot, 'OKX');
      addPrices(gateSpot, 'Gate');
      addPrices(bitgetSpot, 'Bitget');
      addPrices(bingxSpot, 'BingX');

      // Find arbitrage opportunities
      for (const [symbol, prices] of allSpotPrices) {
        if (prices.length < 2) continue;

        // Sort by price
        prices.sort((a, b) => a.price - b.price);
        const lowest = prices[0];
        const highest = prices[prices.length - 1];

        if (lowest.price === 0) continue;

        const spreadPct = ((highest.price - lowest.price) / lowest.price) * 100;

        if (spreadPct < minCex) continue;

        spreads.push({
          symbol,
          type: 'cex_arb' as any,
          spreadPct,
          buyExchange: lowest.exchange,
          sellExchange: highest.exchange,
          buyPrice: lowest.price,
          sellPrice: highest.price,
          timestamp: now,
          tradeable: true,
        });
      }
    }

    // Sort by absolute spread descending
    spreads.sort((a, b) => Math.abs(b.spreadPct) - Math.abs(a.spreadPct));

    // Calculate stats by type
    const futuresGaps = spreads.filter(s => s.type === 'futures_gap');
    const kimchiSpreads = spreads.filter(s => s.type === 'kimchi');
    const fundingSpreads = spreads.filter(s => s.type === 'funding');
    const cexArbSpreads = spreads.filter(s => s.type === 'cex_arb');

    const safeAvg = (arr: number[]) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
    const safeMax = (arr: number[]) => arr.length > 0 ? Math.max(...arr) : 0;

    const stats = {
      total: spreads.length,
      futures_gap: {
        count: futuresGaps.length,
        maxGap: safeMax(futuresGaps.map(s => Math.abs(s.spreadPct))),
        avgGap: safeAvg(futuresGaps.map(s => Math.abs(s.spreadPct))),
      },
      kimchi: {
        count: kimchiSpreads.length,
        avgPremium: safeAvg(kimchiSpreads.map(s => s.spreadPct)),
        maxPremium: safeMax(kimchiSpreads.map(s => s.spreadPct)),
        tradeable: kimchiSpreads.filter(s => s.tradeable).length,
      },
      funding: {
        count: fundingSpreads.length,
        avgRate: safeAvg(fundingSpreads.map(s => s.spreadPct)),
        maxRate: safeMax(fundingSpreads.map(s => Math.abs(s.spreadPct))),
      },
      cex_arb: {
        count: cexArbSpreads.length,
        avgSpread: safeAvg(cexArbSpreads.map(s => s.spreadPct)),
        maxSpread: safeMax(cexArbSpreads.map(s => s.spreadPct)),
      },
      usdKrwRate,
      exchanges: {
        binance: binanceSpot.size,
        bybit: bybitSpot.size,
        okx: okxSpot.size,
        gate: gateSpot.size,
        bitget: bitgetSpot.size,
        bingx: bingxSpot.size,
        upbit: upbitTickers.size,
      },
    };

    return NextResponse.json({
      success: true,
      timestamp: now,
      config: {
        minGap,
        minKimchi,
        minFunding,
        minCex,
        types,
      },
      stats,
      spreads,
    });
  } catch (error) {
    console.error('Spreads fetch error:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    }, { status: 500 });
  }
}
