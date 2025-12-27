import { NextResponse } from 'next/server';
import { fetchAllPremiumIndex, getMaxLeverage } from '@/lib/binance';
import { processSpreadAlert } from '@/lib/telegram';
import type { SpreadData } from '@/lib/types';
import { DEFAULT_CONFIG } from '@/lib/types';

export const dynamic = 'force-dynamic';

// This endpoint is called by Vercel Cron or external cron service
export async function GET(request: Request) {
  // Verify cron secret (optional security)
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (cronSecret && authHeader !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const botToken = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  const minGap = parseFloat(process.env.MIN_GAP_THRESHOLD || '0.5');

  if (!botToken || !chatId) {
    return NextResponse.json({
      success: false,
      error: 'TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables required',
    }, { status: 400 });
  }

  try {
    const premiumIndex = await fetchAllPremiumIndex();
    const now = Date.now();
    const results: { symbol: string; action: string; spreadPct: number }[] = [];

    for (const [symbol, data] of premiumIndex) {
      if (!symbol.endsWith('USDT')) continue;

      // Filter by configured symbols or allow all
      const configSymbols = process.env.MONITOR_SYMBOLS?.split(',') || [];
      if (configSymbols.length > 0 && !configSymbols.includes(symbol)) continue;

      const spread: SpreadData = {
        symbol,
        type: 'futures_gap',
        spreadPct: data.gapPct,
        buyExchange: 'binance_index',
        sellExchange: 'binance_futures',
        buyPrice: data.indexPrice,
        sellPrice: data.markPrice,
        leverage: getMaxLeverage(symbol),
        timestamp: now,
      };

      const result = await processSpreadAlert(spread, minGap, botToken, chatId);

      if (result.action !== 'none') {
        results.push({
          symbol,
          action: result.action,
          spreadPct: spread.spreadPct,
        });
      }
    }

    return NextResponse.json({
      success: true,
      timestamp: now,
      processed: premiumIndex.size,
      alerts: results,
      config: {
        minGap,
        symbols: process.env.MONITOR_SYMBOLS || 'all',
      },
    });
  } catch (error) {
    console.error('Cron job error:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    }, { status: 500 });
  }
}
