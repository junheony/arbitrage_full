import { NextResponse } from 'next/server';
import { fetchAllPremiumIndex, getMaxLeverage, fetchSpotTickers } from '@/lib/binance';
import { fetchUpbitTickers, fetchUsdKrwRate, calculateKimchiPremium } from '@/lib/upbit';
import { fetchUpbitDepositStatus, fetchBinanceDepositStatus } from '@/lib/deposit-status';
import type { SpreadData } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const minGap = parseFloat(searchParams.get('minGap') || '0.3');
    const minKimchi = parseFloat(searchParams.get('minKimchi') || '1.0');
    const minFunding = parseFloat(searchParams.get('minFunding') || '0.05');
    const types = searchParams.get('types')?.split(',') || ['futures_gap', 'kimchi', 'funding'];

    const now = Date.now();
    const spreads: SpreadData[] = [];

    // Fetch all data in parallel
    const [premiumIndex, binanceSpot, upbitTickers, usdKrwRate, upbitWalletStatus, binanceWalletStatus] = await Promise.all([
      fetchAllPremiumIndex(),
      fetchSpotTickers(),
      fetchUpbitTickers(),
      fetchUsdKrwRate(),
      fetchUpbitDepositStatus(),
      fetchBinanceDepositStatus(),
    ]);

    // 1. Futures Gap (시평갭)
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
          tradeable: true, // Futures trading is always available on same exchange
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

        // Skip if below threshold or invalid
        if (Math.abs(kimchiPct) < minKimchi || kimchiPct === 0) continue;

        // Get wallet status from both exchanges
        const upbitStatus = upbitWalletStatus.get(symbol);
        const binanceStatus = binanceWalletStatus.get(symbol);

        const upbitDeposit = upbitStatus?.depositEnabled ?? null;
        const upbitWithdraw = upbitStatus?.withdrawEnabled ?? null;
        const binanceDeposit = binanceStatus?.depositEnabled ?? null;
        const binanceWithdraw = binanceStatus?.withdrawEnabled ?? null;

        // For kimchi arb:
        // - Positive premium (정프): Buy on Binance, sell on Upbit
        //   Need: Binance withdraw (to send coins), Upbit deposit (to receive coins)
        // - Negative premium (역프): Buy on Upbit, sell on Binance
        //   Need: Upbit withdraw (to send coins), Binance deposit (to receive coins)

        // depositStatus shows what's needed for the trade:
        // buy = can withdraw from buy exchange (to send coins)
        // sell = can deposit to sell exchange (to receive coins)
        const depositStatus = kimchiPct > 0
          ? { buy: binanceWithdraw, sell: upbitDeposit } // 정프: Binance출금, Upbit입금
          : { buy: upbitWithdraw, sell: binanceDeposit }; // 역프: Upbit출금, Binance입금

        // Tradeable if both withdraw from buy and deposit to sell are enabled
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

    // 3. Funding Rate (펀딩비)
    if (types.includes('funding')) {
      for (const [symbol, data] of premiumIndex) {
        if (!symbol.endsWith('USDT')) continue;

        const fundingPct = data.lastFundingRate * 100; // Convert to percentage
        if (Math.abs(fundingPct) < minFunding) continue;

        // Annualized rate (3 times per day * 365 days)
        const annualizedPct = fundingPct * 3 * 365;

        spreads.push({
          symbol,
          type: 'funding',
          spreadPct: fundingPct,
          buyExchange: fundingPct > 0 ? 'Spot' : 'Perp',
          sellExchange: fundingPct > 0 ? 'Perp' : 'Spot',
          buyPrice: annualizedPct,
          sellPrice: data.nextFundingTime,
          leverage: getMaxLeverage(symbol),
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

    // Helper to safely calculate stats
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
      usdKrwRate,
    };

    return NextResponse.json({
      success: true,
      timestamp: now,
      config: {
        minGap,
        minKimchi,
        minFunding,
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
