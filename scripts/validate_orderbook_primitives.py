"""
Order Book Primitive Ground Truth Validation

Validates that order book primitives correspond to actual market data.
Constitutional: Reports facts, not quality judgments.

Usage:
    python scripts/validate_orderbook_primitives.py logs/execution.db
"""

import sqlite3
import sys
from typing import Dict, List, Optional
import time


def validate_consumption_vs_trades(db_path: str, time_window_sec: float = 3600.0) -> Dict:
    """
    Validate that OrderConsumption events correlate with actual trade flow.

    For each cycle where order_consumption_size > 0:
    - Check if trades occurred at similar price
    - Verify trade volume approximately matches consumed size
    - Check timestamp alignment

    Returns: Dict with validation statistics
    """
    conn = sqlite3.connect(db_path)

    # Get all cycles with consumption events
    consumption_query = """
        SELECT
            pv.cycle_id,
            pv.symbol,
            pv.order_consumption_size,
            ec.timestamp as cycle_timestamp,
            mn.price_center
        FROM primitive_values pv
        JOIN execution_cycles ec ON pv.cycle_id = ec.id
        JOIN m2_node_events mn ON pv.symbol = mn.symbol
        WHERE pv.order_consumption_size > 0
          AND ec.timestamp > ?
          AND mn.event_type = 'CREATED'
        ORDER BY ec.timestamp DESC
    """

    consumptions = conn.execute(
        consumption_query,
        (time.time() - time_window_sec,)
    ).fetchall()

    results = []

    for cycle_id, symbol, consumed_size, cycle_ts, price_center in consumptions:
        # Find trades near this price and time
        price_tolerance = 100.0  # ±$100 (should match node price_band)
        time_tolerance = 5.0     # ±5 seconds

        trade_query = """
            SELECT
                COUNT(*) as trade_count,
                SUM(volume) as total_trade_volume,
                AVG(price) as avg_trade_price
            FROM trade_events
            WHERE symbol = ?
              AND price BETWEEN ? AND ?
              AND timestamp BETWEEN ? AND ?
        """

        trade_result = conn.execute(
            trade_query,
            (
                symbol,
                price_center - price_tolerance,
                price_center + price_tolerance,
                cycle_ts - time_tolerance,
                cycle_ts + time_tolerance
            )
        ).fetchone()

        trade_count, trade_volume, avg_price = trade_result
        trade_volume = trade_volume or 0.0

        # Calculate correlation metrics
        volume_match_ratio = (
            min(consumed_size, trade_volume) / max(consumed_size, trade_volume)
            if max(consumed_size, trade_volume) > 0 else 0.0
        )

        price_match = (
            abs(avg_price - price_center) < price_tolerance
            if avg_price is not None else False
        )

        results.append({
            'cycle_id': cycle_id,
            'symbol': symbol,
            'consumed_size': consumed_size,
            'trade_count': trade_count or 0,
            'trade_volume': trade_volume,
            'volume_match_ratio': volume_match_ratio,
            'price_match': price_match,
            'timestamp': cycle_ts
        })

    conn.close()

    # Aggregate statistics
    if len(results) == 0:
        return {'total_consumptions': 0, 'error': 'No consumption events found'}

    total = len(results)
    with_trades = sum(1 for r in results if r['trade_count'] > 0)
    good_volume_match = sum(1 for r in results if r['volume_match_ratio'] > 0.8)
    good_price_match = sum(1 for r in results if r['price_match'])

    return {
        'total_consumptions': total,
        'consumptions_with_trades': with_trades,
        'consumptions_with_trades_pct': with_trades / total * 100,
        'good_volume_match_count': good_volume_match,
        'good_volume_match_pct': good_volume_match / total * 100,
        'good_price_match_count': good_price_match,
        'good_price_match_pct': good_price_match / total * 100,
        'avg_volume_match_ratio': sum(r['volume_match_ratio'] for r in results) / total,
        'details': results[:20]  # First 20 for inspection
    }


def validate_absorption_vs_price_stability(db_path: str, time_window_sec: float = 3600.0) -> Dict:
    """
    Validate that AbsorptionEvent corresponds to actual price stability.

    For each cycle where absorption_event = TRUE:
    - Check OHLC data for price movement
    - Verify movement < 1% (absorption tolerance)
    - Compare to recent_prices from M3

    Returns: Dict with validation statistics
    """
    conn = sqlite3.connect(db_path)

    # Get all cycles with absorption events
    absorption_query = """
        SELECT
            pv.cycle_id,
            pv.symbol,
            pv.order_consumption_size,
            ec.timestamp as cycle_timestamp,
            mn.price_center
        FROM primitive_values pv
        JOIN execution_cycles ec ON pv.cycle_id = ec.id
        JOIN m2_node_events mn ON pv.symbol = mn.symbol
        WHERE pv.absorption_event = 1
          AND ec.timestamp > ?
          AND mn.event_type = 'CREATED'
        ORDER BY ec.timestamp DESC
    """

    absorptions = conn.execute(
        absorption_query,
        (time.time() - time_window_sec,)
    ).fetchall()

    results = []

    for cycle_id, symbol, consumed_size, cycle_ts, price_center in absorptions:
        # Find OHLC candle covering this timestamp
        candle_query = """
            SELECT open, high, low, close
            FROM ohlc_candles
            WHERE symbol = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
        """

        candle = conn.execute(candle_query, (symbol, cycle_ts)).fetchone()

        if candle:
            open_price, high, low, close = candle
            price_movement_pct = abs(high - low) / close * 100

            # Absorption requires < 1% movement
            is_stable = price_movement_pct < 1.0

            results.append({
                'cycle_id': cycle_id,
                'symbol': symbol,
                'consumed_size': consumed_size,
                'price_movement_pct': price_movement_pct,
                'is_stable': is_stable,
                'high': high,
                'low': low,
                'timestamp': cycle_ts
            })

    conn.close()

    # Aggregate statistics
    if len(results) == 0:
        return {'total_absorptions': 0, 'error': 'No absorption events found'}

    total = len(results)
    truly_stable = sum(1 for r in results if r['is_stable'])

    return {
        'total_absorptions': total,
        'truly_stable_count': truly_stable,
        'truly_stable_pct': truly_stable / total * 100,
        'false_positive_count': total - truly_stable,
        'false_positive_pct': (total - truly_stable) / total * 100,
        'avg_price_movement_pct': sum(r['price_movement_pct'] for r in results) / total,
        'details': results[:20]
    }


def get_refill_count(db_path: str, time_window_sec: float = 3600.0) -> int:
    """Get count of refill events in time window."""
    conn = sqlite3.connect(db_path)

    query = """
        SELECT COUNT(*)
        FROM primitive_values pv
        JOIN execution_cycles ec ON pv.cycle_id = ec.id
        WHERE pv.refill_event = 1
          AND ec.timestamp > ?
    """

    count = conn.execute(query, (time.time() - time_window_sec,)).fetchone()[0]
    conn.close()

    return count


def generate_orderbook_validation_report(db_path: str):
    """Generate comprehensive order book primitive validation report."""
    print("=" * 80)
    print("ORDER BOOK PRIMITIVE VALIDATION REPORT")
    print("=" * 80)

    # 1. Consumption vs Trades
    print("\n[1] ORDER CONSUMPTION vs. TRADE FLOW")
    consumption_stats = validate_consumption_vs_trades(db_path)

    if 'error' in consumption_stats:
        print(f"  {consumption_stats['error']}")
    else:
        print(f"  Total consumption events: {consumption_stats['total_consumptions']}")
        print(f"  Consumptions with trades: {consumption_stats['consumptions_with_trades']} "
              f"({consumption_stats['consumptions_with_trades_pct']:.1f}%)")
        print(f"  Good volume match (>80%): {consumption_stats['good_volume_match_count']} "
              f"({consumption_stats['good_volume_match_pct']:.1f}%)")
        print(f"  Average volume match ratio: {consumption_stats['avg_volume_match_ratio']:.2f}")

    # 2. Absorption vs Price Stability
    print("\n[2] ABSORPTION EVENT vs. PRICE STABILITY")
    absorption_stats = validate_absorption_vs_price_stability(db_path)

    if 'error' in absorption_stats:
        print(f"  {absorption_stats['error']}")
    else:
        print(f"  Total absorption events: {absorption_stats['total_absorptions']}")
        print(f"  Truly stable (<1% movement): {absorption_stats['truly_stable_count']} "
              f"({absorption_stats['truly_stable_pct']:.1f}%)")
        print(f"  False positives: {absorption_stats['false_positive_count']} "
              f"({absorption_stats['false_positive_pct']:.1f}%)")
        print(f"  Average price movement: {absorption_stats['avg_price_movement_pct']:.2f}%")

    # 3. Refill Events (basic check)
    print("\n[3] REFILL EVENTS")
    refill_count = get_refill_count(db_path)
    print(f"  Total refill events: {refill_count}")

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    # Success criteria
    if 'error' in consumption_stats or 'error' in absorption_stats:
        print("⚠️  INSUFFICIENT DATA FOR VALIDATION")
        print("   Run system for at least 1 hour to collect data")
        return

    consumption_valid = consumption_stats['consumptions_with_trades_pct'] > 80
    absorption_valid = absorption_stats['truly_stable_pct'] > 90

    if consumption_valid and absorption_valid:
        print("✅ ORDER BOOK PRIMITIVES ARE VALID")
        print("   - Consumption correlates with trades")
        print("   - Absorption corresponds to price stability")
    else:
        print("⚠️  VALIDATION ISSUES DETECTED")
        if not consumption_valid:
            print(f"   - Low consumption-trade correlation: "
                  f"{consumption_stats['consumptions_with_trades_pct']:.1f}% (need >80%)")
        if not absorption_valid:
            print(f"   - High absorption false positives: "
                  f"{absorption_stats['false_positive_pct']:.1f}% (need <10%)")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "logs/execution.db"

    print(f"Validating order book primitives from: {db_path}\n")

    try:
        generate_orderbook_validation_report(db_path)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
