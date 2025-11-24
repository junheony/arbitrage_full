#!/usr/bin/env python3
"""자동매매 가능 여부 테스트 - 실제 데이터로 전략 조건 체크"""
import asyncio
import sys
from collections import defaultdict

from app.connectors.binance_spot import BinanceSpotConnector
from app.connectors.upbit_spot import UpbitSpotConnector
from app.connectors.bithumb_spot import BithumbSpotConnector
from app.connectors.binance_perp import BinancePerpConnector
from app.connectors.fx_rates import KRWUSDForexConnector
from app.core.config import get_settings
from app.services.auto_trader import ConservativeStrategy, AggressiveStrategy
from app.services.opportunity_engine import OpportunityEngine


async def main():
    settings = get_settings()

    print("=" * 80)
    print("자동매매 가능 여부 테스트")
    print("=" * 80)

    # Initialize connectors
    print("\n커넥터 초기화 중...")
    connectors = [
        KRWUSDForexConnector(),
        BinanceSpotConnector(settings.trading_symbols),
        UpbitSpotConnector(settings.trading_symbols),
        BithumbSpotConnector(settings.trading_symbols),
        BinancePerpConnector(settings.trading_symbols),
    ]

    # Create opportunity engine
    print("기회 엔진 시작 중...")
    engine = OpportunityEngine(connectors=connectors)
    await engine.start()

    # Wait for data collection
    print("데이터 수집 중 (5초 대기)...")
    await asyncio.sleep(5)

    # Get opportunities
    opportunities = engine.latest()
    print(f"\n총 {len(opportunities)}개 기회 발견\n")

    if not opportunities:
        print("⚠️  기회가 발견되지 않았습니다.")
        await engine.stop()
        for connector in connectors:
            if hasattr(connector, 'close'):
                await connector.close()
        return

    # Print all opportunities first
    print("\n[ 발견된 모든 기회 ]")
    print("-" * 80)
    for i, opp in enumerate(opportunities, 1):
        print(f"\n  {i}. {opp.type.value.upper()} | {opp.symbol}")
        print(f"     스프레드: {opp.spread_bps:.2f} bps")
        print(f"     예상 수익: {opp.expected_pnl_pct:+.3f}%")
        print(f"     거래량: ${opp.notional:,.0f}")
        print(f"     레그: {' ↔ '.join(f'{leg.exchange}({leg.side})' for leg in opp.legs)}")

    # Test with different strategies
    conservative = ConservativeStrategy(
        min_spread_bps=50.0,
        min_expected_pnl_pct=0.5,
        min_notional=100.0,  # Minimum $100
    )

    aggressive = AggressiveStrategy(
        min_spread_bps=20.0,
        min_expected_pnl_pct=0.2,
        min_notional=50.0,  # Minimum $50
    )

    print("=" * 80)
    print("전략별 자동매매 가능 기회 분석")
    print("=" * 80)

    # Conservative strategy
    print("\n[ 보수적 전략 ] (스프레드 ≥50bps, 수익 ≥0.5%, 최소금액 $100)")
    print("-" * 80)
    conservative_opps = [opp for opp in opportunities if conservative.should_execute(opp)]
    print(f"✓ 조건 충족: {len(conservative_opps)}개 / {len(opportunities)}개")

    if conservative_opps:
        print("\n상위 3개:")
        for i, opp in enumerate(sorted(conservative_opps, key=lambda x: x.expected_pnl_pct, reverse=True)[:3], 1):
            print(f"\n  {i}. {opp.type.value.upper()} | {opp.symbol}")
            print(f"     스프레드: {opp.spread_bps:.2f} bps")
            print(f"     예상 수익: {opp.expected_pnl_pct:+.3f}%")
            print(f"     거래량: ${opp.notional:,.0f}")
            print(f"     레그: {len(opp.legs)}개 ({' + '.join(f'{leg.exchange}' for leg in opp.legs)})")
    else:
        print("  ✗ 조건을 만족하는 기회 없음")

    # Aggressive strategy
    print("\n\n[ 공격적 전략 ] (스프레드 ≥20bps, 수익 ≥0.2%, 최소금액 $50)")
    print("-" * 80)
    aggressive_opps = [opp for opp in opportunities if aggressive.should_execute(opp)]
    print(f"✓ 조건 충족: {len(aggressive_opps)}개 / {len(opportunities)}개")

    if aggressive_opps:
        print("\n상위 5개:")
        for i, opp in enumerate(sorted(aggressive_opps, key=lambda x: x.expected_pnl_pct, reverse=True)[:5], 1):
            print(f"\n  {i}. {opp.type.value.upper()} | {opp.symbol}")
            print(f"     스프레드: {opp.spread_bps:.2f} bps")
            print(f"     예상 수익: {opp.expected_pnl_pct:+.3f}%")
            print(f"     거래량: ${opp.notional:,.0f}")
            print(f"     레그: {len(opp.legs)}개 ({' + '.join(f'{leg.exchange}' for leg in opp.legs)})")
    else:
        print("  ✗ 조건을 만족하는 기회 없음")

    # Summary by type
    print("\n\n[ 기회 유형별 분포 ]")
    print("-" * 80)
    by_type = defaultdict(list)
    for opp in opportunities:
        by_type[opp.type.value].append(opp)

    for opp_type, type_opps in sorted(by_type.items()):
        conservative_count = sum(1 for o in type_opps if conservative.should_execute(o))
        aggressive_count = sum(1 for o in type_opps if aggressive.should_execute(o))
        avg_spread = sum(o.spread_bps for o in type_opps) / len(type_opps)
        avg_pnl = sum(o.expected_pnl_pct for o in type_opps) / len(type_opps)

        print(f"\n  {opp_type.upper()}: {len(type_opps)}개")
        print(f"    평균 스프레드: {avg_spread:.2f} bps")
        print(f"    평균 수익: {avg_pnl:+.3f}%")
        print(f"    보수적 전략: {conservative_count}개")
        print(f"    공격적 전략: {aggressive_count}개")

    # Cleanup
    print("\n\n엔진 종료 중...")
    await engine.stop()
    for connector in connectors:
        if hasattr(connector, 'close'):
            await connector.close()

    print("\n" + "=" * 80)
    print("결론:")
    print("=" * 80)
    if conservative_opps or aggressive_opps:
        print(f"✅ 자동매매 가능: {len(aggressive_opps)}개 기회 (공격적 전략 기준)")
        print(f"   보수적 전략으로는 {len(conservative_opps)}개 실행 가능")
        print(f"\n💡 실행 시 사용자 리스크 한도(RiskLimit.max_position_size_usd)에 맞게")
        print(f"   거래량이 자동으로 조정됩니다.")
        print(f"   예: 기회=$10,000, 한도=$5,000 → 실제 실행=$5,000 (50% 스케일)")
    else:
        print("⚠️  현재 자동매매 조건을 만족하는 기회 없음")
        print("   (스프레드가 너무 작거나 최소 거래량 미달)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n중단됨")
        sys.exit(0)
