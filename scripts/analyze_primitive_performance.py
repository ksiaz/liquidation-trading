"""
Primitive Performance Analysis

Analyzes which primitive combinations lead to profitable trades.
Constitutional: Factual correlation only, not prediction.

Usage:
    python scripts/analyze_primitive_performance.py logs/execution.db
"""

import sqlite3
import sys
from typing import Dict, List
from collections import defaultdict


def analyze_primitive_performance(db_path: str, min_trades: int = 10) -> Dict:
    """
    Analyze which primitive combinations lead to profitable trades.

    Returns statistics on:
    - Win rate by primitive type
    - Average PNL by primitive combination
    - Holding duration by primitive pattern

    Args:
        db_path: Path to execution database
        min_trades: Minimum trades required to include primitive combination

    Returns:
        Dict with analysis results
    """
    conn = sqlite3.connect(db_path)

    # Get all policy outcomes with ghost trade results
    query = """
        SELECT
            po.symbol,
            po.active_primitives,
            po.realized_pnl,
            po.holding_duration_sec,
            po.exit_reason,
            po.mandate_type
        FROM policy_outcomes po
        WHERE po.realized_pnl IS NOT NULL
          AND po.executed_action = 'ENTRY'
    """

    outcomes = conn.execute(query).fetchall()
    conn.close()

    if len(outcomes) == 0:
        return {'error': 'No completed trades found'}

    # Aggregate by primitive combination
    primitive_stats = defaultdict(lambda: {
        'trades': 0,
        'wins': 0,
        'losses': 0,
        'total_pnl': 0.0,
        'avg_holding_sec': 0.0,
        'exit_reasons': defaultdict(int)
    })

    import json
    for symbol, primitives_json, pnl, duration, exit_reason, mandate_type in outcomes:
        primitives = tuple(sorted(json.loads(primitives_json)))

        stats = primitive_stats[primitives]
        stats['trades'] += 1
        if pnl > 0:
            stats['wins'] += 1
        else:
            stats['losses'] += 1
        stats['total_pnl'] += pnl
        stats['avg_holding_sec'] += duration or 0.0
        stats['exit_reasons'][exit_reason or 'UNKNOWN'] += 1

    # Calculate final metrics
    results = []
    for primitives, stats in primitive_stats.items():
        if stats['trades'] < min_trades:
            continue  # Skip low-sample combinations

        win_rate = stats['wins'] / stats['trades'] * 100
        avg_pnl = stats['total_pnl'] / stats['trades']
        avg_holding = stats['avg_holding_sec'] / stats['trades']

        results.append({
            'primitives': list(primitives),
            'trade_count': stats['trades'],
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'total_pnl': stats['total_pnl'],
            'avg_holding_sec': avg_holding,
            'exit_reasons': dict(stats['exit_reasons'])
        })

    # Sort by win rate descending
    results.sort(key=lambda x: x['win_rate'], reverse=True)

    return {
        'total_outcomes': len(outcomes),
        'primitive_combinations': len(results),
        'top_performers': results[:10],
        'worst_performers': results[-10:] if len(results) > 10 else []
    }


def print_primitive_performance_report(db_path: str):
    """Print readable performance report."""
    print("=" * 80)
    print("PRIMITIVE PERFORMANCE ANALYSIS")
    print("=" * 80)

    stats = analyze_primitive_performance(db_path)

    if 'error' in stats:
        print(f"\nError: {stats['error']}")
        print("\nRun system with ghost trading enabled to collect trade outcomes.")
        return

    print(f"\nTotal completed trades: {stats['total_outcomes']}")
    print(f"Unique primitive combinations: {stats['primitive_combinations']}")

    print("\n" + "=" * 80)
    print("TOP 10 PERFORMING PRIMITIVE COMBINATIONS")
    print("=" * 80)

    for i, combo in enumerate(stats['top_performers'], 1):
        print(f"\n#{i} - Win Rate: {combo['win_rate']:.1f}% ({combo['trade_count']} trades)")
        print(f"  Primitives: {', '.join(combo['primitives'])}")
        print(f"  Avg PNL: ${combo['avg_pnl']:+.2f}")
        print(f"  Total PNL: ${combo['total_pnl']:+.2f}")
        print(f"  Avg Hold Time: {combo['avg_holding_sec']:.0f}s")
        print(f"  Exit Reasons: {combo['exit_reasons']}")

    if stats['worst_performers']:
        print("\n" + "=" * 80)
        print("WORST 10 PERFORMING PRIMITIVE COMBINATIONS")
        print("=" * 80)

        for i, combo in enumerate(stats['worst_performers'], 1):
            print(f"\n#{i} - Win Rate: {combo['win_rate']:.1f}% ({combo['trade_count']} trades)")
            print(f"  Primitives: {', '.join(combo['primitives'])}")
            print(f"  Avg PNL: ${combo['avg_pnl']:+.2f}")
            print(f"  Total PNL: ${combo['total_pnl']:+.2f}")
            print(f"  Exit Reasons: {combo['exit_reasons']}")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "logs/execution.db"

    print(f"Analyzing primitive performance from: {db_path}\n")

    try:
        print_primitive_performance_report(db_path)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
