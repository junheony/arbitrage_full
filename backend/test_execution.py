#!/usr/bin/env python3
"""실제 기회로 실행 테스트"""
import asyncio
from app.services.opportunity_engine import OpportunityEngine
from app.core.config import get_settings


async def main():
    settings = get_settings()

    print("=" * 80)
    print("실제 기회 데이터로 실행 테스트")
    print("=" * 80)

    # OpportunityEngine 시작
    engine = OpportunityEngine(settings)
    await engine.start()

    # 3초 대기 (데이터 수집)
    print("\n데이터 수집 중...")
    await asyncio.sleep(3)

    # 현재 기회 가져오기
    opps = engine.latest()

    print(f"\n총 {len(opps)}개 기회 발견\n")

    # 타입별로 그룹화
    by_type = {}
    for opp in opps:
        if opp.type.value not in by_type:
            by_type[opp.type.value] = []
        by_type[opp.type.value].append(opp)

    # 각 타입별로 상위 1개씩 테스트
    for opp_type, type_opps in by_type.items():
        print(f"\n{'='*80}")
        print(f"[{opp_type.upper()}] 테스트")
        print(f"{'='*80}")

        # 상위 1개 선택
        opp = type_opps[0]

        print(f"\n심볼: {opp.symbol}")
        print(f"예상 수익: {opp.expected_pnl_pct:+.3f}%")
        print(f"스프레드: {opp.spread_bps:.2f} bps")
        print(f"거래량: ${opp.notional:,.0f}")

        print(f"\n레그 구성:")
        for i, leg in enumerate(opp.legs, 1):
            side_icon = "🟢 매수" if leg.side == "buy" else "🔴 매도"
            print(f"  {i}. {side_icon} | {leg.exchange:12} | {leg.symbol:15} @ {leg.price:.6f}")

        # 메타데이터 출력
        if opp.metadata:
            print(f"\n추가 정보:")
            for key, value in opp.metadata.items():
                print(f"  {key}: {value}")

        # 실행 시뮬레이션 정보
        print(f"\n{'─'*80}")
        print("📊 자동 종료 조건:")
        print(f"  ✅ 목표 수익: +0.5% 도달 시")
        print(f"  ✅ 손절: -1.0% 도달 시")
        print(f"  ✅ 스프레드 수렴: 0.05% 미만 시 (갭 해소!)")
        print(f"  ⏱️  체크 주기: 5초마다 자동 체크")

        print(f"\n💡 실행 방법:")
        print(f"  1. UI에서 'TEST' 버튼 → dry_run (시뮬레이션)")
        print(f"  2. UI에서 'EXEC' 버튼 → 실제 주문 제출")
        print(f"\n⚠️  실제 실행 전 필요:")
        print(f"  - 거래소 API 키 등록")
        print(f"  - 리스크 한도 설정")
        print(f"  - 각 거래소에 자금 보유")

    await engine.stop()
    print(f"\n{'='*80}")
    print("테스트 완료")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n중단됨")
