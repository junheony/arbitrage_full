import { NextResponse } from 'next/server';
import { fetchAllPremiumIndex, fetchSpotTickers } from '@/lib/binance';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export async function GET() {
  try {
    const [premiumIndex, spotTickers] = await Promise.all([
      fetchAllPremiumIndex(),
      fetchSpotTickers(),
    ]);

    // Convert Maps to objects for JSON serialization
    const futures: Record<string, {
      symbol: string;
      markPrice: number;
      indexPrice: number;
      lastFundingRate: number;
      nextFundingTime: number;
      gapPct: number;
    }> = {};

    const spot: Record<string, {
      symbol: string;
      price: number;
      timestamp: number;
    }> = {};

    for (const [key, value] of premiumIndex) {
      futures[key] = value;
    }

    for (const [key, value] of spotTickers) {
      spot[key] = value;
    }

    return NextResponse.json({
      success: true,
      timestamp: Date.now(),
      data: {
        futures,
        spot,
        futuresCount: Object.keys(futures).length,
        spotCount: Object.keys(spot).length,
      }
    });
  } catch (error) {
    console.error('Price fetch error:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    }, { status: 500 });
  }
}
