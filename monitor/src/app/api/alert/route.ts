import { NextResponse } from 'next/server';
import { fetchAllPremiumIndex, getMaxLeverage } from '@/lib/binance';
import { processSpreadAlert, getActiveAlerts, formatSpreadAlert, sendTelegramMessage } from '@/lib/telegram';
import type { SpreadData } from '@/lib/types';
import { DEFAULT_CONFIG } from '@/lib/types';

export const dynamic = 'force-dynamic';

// POST: Check spreads and send alerts
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const {
      botToken,
      chatId,
      minGap = DEFAULT_CONFIG.futuresGapThreshold,
      symbols = DEFAULT_CONFIG.symbols,
    } = body;

    if (!botToken || !chatId) {
      return NextResponse.json({
        success: false,
        error: 'botToken and chatId are required',
      }, { status: 400 });
    }

    const premiumIndex = await fetchAllPremiumIndex();
    const now = Date.now();
    const results: { symbol: string; action: string; spreadPct: number }[] = [];

    for (const [symbol, data] of premiumIndex) {
      if (!symbol.endsWith('USDT')) continue;
      if (symbols.length > 0 && !symbols.includes(symbol)) continue;

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
      activeAlerts: getActiveAlerts().length,
    });
  } catch (error) {
    console.error('Alert processing error:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    }, { status: 500 });
  }
}

// GET: Get active alerts
export async function GET() {
  const activeAlerts = getActiveAlerts();

  return NextResponse.json({
    success: true,
    timestamp: Date.now(),
    count: activeAlerts.length,
    alerts: activeAlerts,
  });
}

// PUT: Manual alert send (for testing)
export async function PUT(request: Request) {
  try {
    const body = await request.json();
    const { botToken, chatId, message } = body;

    if (!botToken || !chatId || !message) {
      return NextResponse.json({
        success: false,
        error: 'botToken, chatId, and message are required',
      }, { status: 400 });
    }

    const sent = await sendTelegramMessage(botToken, chatId, message);

    return NextResponse.json({
      success: sent,
      timestamp: Date.now(),
    });
  } catch (error) {
    console.error('Manual alert error:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    }, { status: 500 });
  }
}
