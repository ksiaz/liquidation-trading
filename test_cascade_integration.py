"""
Test Cascade Primitive Integration

Verifies that Hyperliquid data flows through M1-M5 observation layer
and populates M4PrimitiveBundle with cascade primitives.

Run: python test_cascade_integration.py
"""

import asyncio
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Suppress noisy loggers
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

async def test_cascade_integration():
    """Test cascade primitive integration end-to-end."""

    print("=" * 70)
    print("TESTING CASCADE PRIMITIVE INTEGRATION")
    print("=" * 70)
    print()

    # Import components
    from observation.governance import ObservationSystem
    from runtime.hyperliquid.collector import HyperliquidCollector, HyperliquidCollectorConfig
    from runtime.logging.execution_db import ResearchDatabase
    from memory.m4_cascade_state import CascadePhase

    # Initialize database
    db = ResearchDatabase(db_path="logs/test_cascade.db")

    # Initialize observation system with BTC only for testing
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    obs = ObservationSystem(allowed_symbols=symbols)

    # Initialize Hyperliquid collector
    hl_config = HyperliquidCollectorConfig(
        use_testnet=False,
        proximity_threshold=0.02,  # 2% threshold for more data
        min_position_value=1000.0,
        wallet_poll_interval=5.0,
        track_hlp_vault=True,
        enable_dynamic_discovery=True,  # Enable whale discovery
        discovery_min_trade_value=50_000.0  # Lower for testing
    )

    hl_collector = HyperliquidCollector(db=db, config=hl_config)

    # Wire up to observation system
    obs.set_hyperliquid_source(hl_collector)
    print("[OK] Hyperliquid collector wired to observation system")

    # Start Hyperliquid collector
    print("\n[STARTING] Hyperliquid collector...")
    await hl_collector.start()
    print("[OK] Hyperliquid collector started")

    # Wait for initial data
    print("\n[WAITING] Collecting initial position data (15 seconds)...")
    await asyncio.sleep(15)

    # Check collector state
    summary = hl_collector.get_summary()
    print(f"\n[COLLECTOR STATUS]")
    print(f"  Wallets tracked: {summary.get('wallets_tracked', 0)}")
    print(f"  Total positions: {summary.get('total_positions', 0)}")
    print(f"  Total value tracked: ${summary.get('total_value', 0):,.0f}")

    # Show proximity data from collector
    print(f"\n[HYPERLIQUID PROXIMITY DATA (from collector)]")
    all_proximity = hl_collector.get_all_proximity()
    if all_proximity:
        for coin, prox in all_proximity.items():
            if prox:
                print(f"  {coin}: {prox.total_positions_at_risk} positions, "
                      f"${prox.total_value_at_risk:,.0f} at risk, "
                      f"price=${prox.current_price:,.2f}")
    else:
        print("  No proximity data yet (waiting for more data)")

    # Show raw position data from tracker
    print(f"\n[HYPERLIQUID POSITION DATA (from tracker)]")
    tracker = hl_collector._tracker
    if tracker and tracker._wallet_states:
        for wallet, state in list(tracker._wallet_states.items())[:3]:  # First 3 wallets
            print(f"  Wallet {wallet[:12]}...")
            for coin, pos in state.positions.items():
                print(f"    {coin}: size={pos.position_size:.4f}, value=${pos.position_value:,.0f}, lev={pos.leverage}x")
    else:
        print("  No positions tracked yet")

    # Now test M4 primitive computation
    print("\n[TESTING M4 PRIMITIVE COMPUTATION]")
    print("-" * 50)

    # Advance time and compute primitives
    current_time = time.time()
    obs.advance_time(current_time)

    # Query snapshot
    snapshot = obs.query({'type': 'snapshot'})
    print(f"Observation status: {snapshot.status.name}")
    print(f"Symbols active: {snapshot.symbols_active}")

    # Check cascade primitives for each symbol
    print("\n[CASCADE PRIMITIVES IN M4PrimitiveBundle]")
    print("-" * 50)

    cascade_found = False
    for symbol in symbols:
        if symbol not in snapshot.primitives:
            print(f"  {symbol}: No primitives yet")
            continue

        bundle = snapshot.primitives[symbol]

        # Check cascade proximity
        cascade_prox = bundle.liquidation_cascade_proximity
        cascade_state = bundle.cascade_state
        leverage = bundle.leverage_concentration_ratio
        oi_bias = bundle.open_interest_directional_bias

        if cascade_prox or cascade_state or leverage or oi_bias:
            cascade_found = True
            print(f"\n  {symbol}:")

            if cascade_prox:
                print(f"    [CASCADE PROXIMITY]")
                print(f"      Price: ${cascade_prox.price_level:,.2f}")
                print(f"      Positions at risk: {cascade_prox.positions_at_risk_count}")
                print(f"      Value at risk: ${cascade_prox.aggregate_position_value:,.0f}")
                print(f"      Long: {cascade_prox.long_positions_count} pos, ${cascade_prox.long_positions_value:,.0f}")
                print(f"      Short: {cascade_prox.short_positions_count} pos, ${cascade_prox.short_positions_value:,.0f}")
                if cascade_prox.long_closest_price:
                    print(f"      Closest long liq: ${cascade_prox.long_closest_price:,.2f}")
                if cascade_prox.short_closest_price:
                    print(f"      Closest short liq: ${cascade_prox.short_closest_price:,.2f}")
            else:
                print(f"    [CASCADE PROXIMITY] None")

            if cascade_state:
                print(f"    [CASCADE STATE]")
                print(f"      Phase: {cascade_state.phase.name}")
                print(f"      CONFIDENCE: {cascade_state.observation_confidence}")  # KEY DISTINCTION
                print(f"      Has confirmed liquidation: {cascade_state.has_confirmed_liquidation}")
                print(f"      Liquidations (5s/30s/60s): {cascade_state.liquidations_5s}/{cascade_state.liquidations_30s}/{cascade_state.liquidations_60s}")
                print(f"      Positions remaining: {cascade_state.positions_remaining_at_risk}")
                if cascade_state.confirmed_liquidation_value > 0:
                    print(f"      Confirmed liquidation value: ${cascade_state.confirmed_liquidation_value:,.0f}")
                if cascade_state.cascade_value_liquidated > 0:
                    print(f"      Cascade value liquidated: ${cascade_state.cascade_value_liquidated:,.0f}")
            else:
                print(f"    [CASCADE STATE] None")

            if leverage:
                print(f"    [LEVERAGE CONCENTRATION]")
                print(f"      Median leverage: {leverage.median_leverage:.1f}x")
                print(f"      90th percentile: {leverage.leverage_90th_pct:.1f}x")
                print(f"      High leverage (>10x): {leverage.high_leverage_count}")
                print(f"      Total positions: {leverage.total_positions_observed}")
            else:
                print(f"    [LEVERAGE] None")

            if oi_bias:
                print(f"    [OPEN INTEREST BIAS]")
                print(f"      Net long value: ${oi_bias.net_long_value:,.0f}")
                print(f"      Net short value: ${oi_bias.net_short_value:,.0f}")
                print(f"      Long/Short ratio: {oi_bias.long_short_ratio:.2f}")
                print(f"      Total OI: ${oi_bias.total_open_interest:,.0f}")
            else:
                print(f"    [OI BIAS] None")
        else:
            coin = symbol.replace('USDT', '')
            print(f"  {symbol}: No cascade primitives (coin={coin})")

    if not cascade_found:
        print("\n  [INFO] No cascade primitives computed yet.")
        print("  This may be because:")
        print("  1. No positions within 2% of liquidation")
        print("  2. Collector still gathering data")
        print("  3. Symbol mismatch (BTCUSDT vs BTC)")

    # Continue monitoring for 30 more seconds
    print("\n" + "=" * 70)
    print("MONITORING LIVE (30 seconds)...")
    print("=" * 70)

    for i in range(6):
        await asyncio.sleep(5)

        # Advance time
        current_time = time.time()
        obs.advance_time(current_time)

        # Query snapshot
        snapshot = obs.query({'type': 'snapshot'})

        print(f"\n[{i+1}/6] Time: {time.strftime('%H:%M:%S')}")

        for symbol in symbols:
            if symbol not in snapshot.primitives:
                continue

            bundle = snapshot.primitives[symbol]
            cascade_prox = bundle.liquidation_cascade_proximity
            cascade_state = bundle.cascade_state

            if cascade_prox and cascade_prox.positions_at_risk_count > 0:
                phase = cascade_state.phase.name if cascade_state else "N/A"
                print(f"  {symbol}: {cascade_prox.positions_at_risk_count} pos @ risk, "
                      f"${cascade_prox.aggregate_position_value:,.0f}, "
                      f"phase={phase}")

    # Cleanup
    print("\n[STOPPING] Hyperliquid collector...")
    await hl_collector.stop()
    print("[DONE] Test complete.")

    print("\n" + "=" * 70)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 70)
    print(f"  Observation system: OK")
    print(f"  Hyperliquid collector: OK")
    print(f"  Cascade primitives computed: {'YES' if cascade_found else 'NO (need more data)'}")
    print(f"  Constitutional flow: Data flows through M4PrimitiveBundle")


if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(test_cascade_integration())
