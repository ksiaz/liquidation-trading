#!/usr/bin/env python3
"""
Phase 5: Regime Fragility Test

Split trades by market regime and test edge stability:
- High/low volatility
- Trending/ranging
- High/low funding
- High/low liquidity

EDGE FRAGILE if:
- Expectancy positive in < 3 of 8 regime splits
- Single regime contributes > 60% of total profit
- Any regime has expectancy < -10 bps
"""

import json
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class RegimeResult:
    """Results for a single regime."""
    regime_name: str
    condition: str
    trade_count: int
    mean_pnl_bps: float
    std_pnl_bps: float
    win_rate: float
    total_profit_bps: float
    profit_contribution_pct: float
    expectancy_positive: bool


def load_trades(path: Path) -> List[Dict]:
    """Load simulated trades from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def load_events(path: Path) -> List[Dict]:
    """Load cascade events from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def split_by_regime(
    trades: List[Dict],
    events: List[Dict]
) -> Dict[str, Tuple[List[Dict], str]]:
    """Split trades by regime based on event context.

    Returns dict of regime_name -> (trades, condition_description)
    """
    # Create event lookup by ID
    event_lookup = {e['event_id']: e for e in events}

    # Compute medians for splitting
    volatilities = [e['volatility_1h'] for e in events]
    spreads = [e['spread_bps'] for e in events]
    fundings = [abs(e['funding_rate']) for e in events]
    absorptions = [e['absorption_ratio'] for e in events]

    vol_median = np.median(volatilities)
    spread_median = np.median(spreads)
    funding_median = np.median(fundings)
    absorption_median = np.median(absorptions)

    # Initialize regime buckets
    regimes = {
        'high_volatility': ([], f"volatility_1h > {vol_median:.2f}"),
        'low_volatility': ([], f"volatility_1h <= {vol_median:.2f}"),
        'high_liquidity': ([], f"spread_bps < {spread_median:.1f}"),
        'low_liquidity': ([], f"spread_bps >= {spread_median:.1f}"),
        'high_funding': ([], f"abs(funding) > {funding_median:.4f}"),
        'neutral_funding': ([], f"abs(funding) <= {funding_median:.4f}"),
        'high_absorption': ([], f"absorption_ratio > {absorption_median:.2f}"),
        'low_absorption': ([], f"absorption_ratio <= {absorption_median:.2f}"),
    }

    # Classify each trade
    for trade in trades:
        event_id = trade['event_id']
        if event_id not in event_lookup:
            continue

        event = event_lookup[event_id]

        # Volatility regime
        if event['volatility_1h'] > vol_median:
            regimes['high_volatility'][0].append(trade)
        else:
            regimes['low_volatility'][0].append(trade)

        # Liquidity regime (inverse of spread)
        if event['spread_bps'] < spread_median:
            regimes['high_liquidity'][0].append(trade)
        else:
            regimes['low_liquidity'][0].append(trade)

        # Funding regime
        if abs(event['funding_rate']) > funding_median:
            regimes['high_funding'][0].append(trade)
        else:
            regimes['neutral_funding'][0].append(trade)

        # Absorption regime
        if event['absorption_ratio'] > absorption_median:
            regimes['high_absorption'][0].append(trade)
        else:
            regimes['low_absorption'][0].append(trade)

    return regimes


def analyze_regime(
    regime_name: str,
    trades: List[Dict],
    condition: str,
    total_profit: float
) -> RegimeResult:
    """Analyze a single regime."""
    if not trades:
        return RegimeResult(
            regime_name=regime_name,
            condition=condition,
            trade_count=0,
            mean_pnl_bps=0,
            std_pnl_bps=0,
            win_rate=0,
            total_profit_bps=0,
            profit_contribution_pct=0,
            expectancy_positive=False,
        )

    pnls = [t['net_pnl_bps'] for t in trades]
    regime_profit = sum(pnls)

    return RegimeResult(
        regime_name=regime_name,
        condition=condition,
        trade_count=len(trades),
        mean_pnl_bps=np.mean(pnls),
        std_pnl_bps=np.std(pnls),
        win_rate=len([p for p in pnls if p > 0]) / len(pnls),
        total_profit_bps=regime_profit,
        profit_contribution_pct=(regime_profit / total_profit * 100) if total_profit > 0 else 0,
        expectancy_positive=np.mean(pnls) > 0,
    )


def check_fragility(results: List[RegimeResult]) -> Tuple[bool, List[str]]:
    """Check if edge is fragile.

    Returns: (is_fragile, reasons)
    """
    reasons = []

    # Check 1: Expectancy positive in < 3 of 8 regimes
    positive_count = sum(1 for r in results if r.expectancy_positive and r.trade_count > 0)
    if positive_count < 3:
        reasons.append(f"Only {positive_count}/8 regimes have positive expectancy (threshold: 3)")

    # Check 2: Single regime contributes > 60% of profit
    max_contribution = max(r.profit_contribution_pct for r in results if r.trade_count > 0)
    if max_contribution > 60:
        dominant = [r for r in results if r.profit_contribution_pct == max_contribution][0]
        reasons.append(f"Single regime ({dominant.regime_name}) contributes {max_contribution:.1f}% of profit (threshold: 60%)")

    # Check 3: Any regime has expectancy < -10 bps
    for r in results:
        if r.trade_count > 0 and r.mean_pnl_bps < -10:
            reasons.append(f"Regime {r.regime_name} has negative expectancy: {r.mean_pnl_bps:.1f} bps")

    return len(reasons) > 0, reasons


def main():
    parser = argparse.ArgumentParser(description="Regime fragility analysis")
    parser.add_argument("--split", default="test", help="Data split to analyze")
    parser.add_argument("--exit", default="fixed_15s", help="Exit strategy used")
    args = parser.parse_args()

    print("=" * 70)
    print("PHASE 5: REGIME FRAGILITY TEST")
    print("=" * 70)

    data_dir = PROJECT_ROOT / "data" / "cascade_audit"

    # Load trades and events
    trade_path = data_dir / f"simulated_trades_{args.split}_{args.exit}.json"
    event_path = data_dir / f"cascade_events_{args.split}.json"

    if not trade_path.exists() or not event_path.exists():
        print(f"Error: Required files not found")
        sys.exit(1)

    trades = load_trades(trade_path)
    events = load_events(event_path)

    print(f"\nLoaded {len(trades)} trades from {args.split} split")

    # Total profit for contribution calculation
    total_profit = sum(t['net_pnl_bps'] for t in trades)

    # Split by regimes
    regimes = split_by_regime(trades, events)

    # Analyze each regime
    results = []
    for regime_name, (regime_trades, condition) in regimes.items():
        result = analyze_regime(regime_name, regime_trades, condition, total_profit)
        results.append(result)

    # Print results
    print("\n" + "-" * 70)
    print(f"{'Regime':<20} {'N':>6} {'Mean PnL':>10} {'Win Rate':>10} {'Contrib':>10}")
    print("-" * 70)

    for r in sorted(results, key=lambda x: x.mean_pnl_bps, reverse=True):
        status = "+" if r.expectancy_positive else "-"
        print(f"{r.regime_name:<20} {r.trade_count:>6} {r.mean_pnl_bps:>10.1f} {r.win_rate*100:>9.1f}% {r.profit_contribution_pct:>9.1f}%  {status}")

    print("-" * 70)
    print(f"{'TOTAL':<20} {len(trades):>6} {np.mean([t['net_pnl_bps'] for t in trades]):>10.1f} {len([t for t in trades if t['net_pnl_bps']>0])/len(trades)*100:>9.1f}% {100:>9.1f}%")

    # Check fragility
    is_fragile, reasons = check_fragility(results)

    print("\n" + "=" * 70)
    print("FRAGILITY VERDICT")
    print("=" * 70)

    if is_fragile:
        print("\nVERDICT: EDGE FRAGILE")
        print("\nReasons:")
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("\nVERDICT: EDGE ROBUST")
        print("\nEdge maintains positive expectancy across diverse regimes:")
        positive_regimes = [r for r in results if r.expectancy_positive and r.trade_count > 0]
        for r in positive_regimes:
            print(f"  - {r.regime_name}: {r.mean_pnl_bps:.1f} bps ({r.trade_count} trades)")

    print("=" * 70)

    # Save results
    output_path = data_dir / f"regime_fragility_{args.split}_{args.exit}.json"
    with open(output_path, 'w') as f:
        json.dump({
            'is_fragile': is_fragile,
            'reasons': reasons,
            'regimes': [
                {
                    'name': r.regime_name,
                    'condition': r.condition,
                    'trade_count': r.trade_count,
                    'mean_pnl_bps': float(r.mean_pnl_bps),
                    'win_rate': float(r.win_rate),
                    'profit_contribution_pct': float(r.profit_contribution_pct),
                    'expectancy_positive': int(r.expectancy_positive),
                }
                for r in results
            ]
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
