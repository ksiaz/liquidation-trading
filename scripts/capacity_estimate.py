#!/usr/bin/env python3
"""
Phase 7: Capacity & Scaling Estimate

Estimates maximum deployable capital:
- Market impact modeling
- Fill probability vs size
- Slippage curve
- Realistic capacity

Capacity Thresholds:
- < $10k/day: LOW VALUE
- $10k-$100k/day: LIMITED
- $100k-$1M/day: VIABLE
- > $1M/day: SCALABLE
"""

import json
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CapacityEstimate:
    """Capacity estimation results."""
    # Trade frequency
    trades_per_day: float
    trades_per_week: float
    trades_per_month: float

    # Size limits
    max_size_per_trade_usd: float
    size_limit_reason: str

    # Impact modeling
    impact_at_10k_bps: float
    impact_at_50k_bps: float
    impact_at_100k_bps: float
    breakeven_size_usd: float

    # Capacity
    daily_capacity_usd: float
    monthly_capacity_usd: float
    annual_capacity_usd: float

    # Verdict
    capacity_tier: str  # LOW_VALUE, LIMITED, VIABLE, SCALABLE


def load_trades(path: Path) -> List[Dict]:
    """Load simulated trades from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def load_events(path: Path) -> List[Dict]:
    """Load cascade events from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def estimate_impact(size_usd: float, base_spread_bps: float, depth_usd: float = 500000) -> float:
    """Estimate market impact for a given size.

    Simple linear impact model: impact = spread/2 + size/depth * coefficient
    """
    spread_crossing = base_spread_bps / 2
    depth_impact = (size_usd / depth_usd) * 10  # 10 bps per 100% of depth
    return spread_crossing + depth_impact


def find_breakeven_size(
    mean_pnl_bps: float,
    base_spread_bps: float,
    depth_usd: float = 500000
) -> float:
    """Find size at which impact equals expected profit.

    Impact = spread/2 + (size/depth) * 10
    Breakeven when: 2 * impact = mean_pnl (round trip)
    """
    if mean_pnl_bps <= base_spread_bps:
        return 0  # Already unprofitable at smallest size

    # 2 * (spread/2 + size/depth * 10) = mean_pnl
    # spread + 20 * size/depth = mean_pnl
    # size/depth = (mean_pnl - spread) / 20
    # size = depth * (mean_pnl - spread) / 20

    breakeven = depth_usd * (mean_pnl_bps - base_spread_bps) / 20
    return max(0, breakeven)


def estimate_capacity(
    trades: List[Dict],
    events: List[Dict],
    data_days: float = 30
) -> CapacityEstimate:
    """Estimate capacity from trade data."""

    # Trade frequency
    n_trades = len(trades)
    trades_per_day = n_trades / data_days
    trades_per_week = trades_per_day * 7
    trades_per_month = trades_per_day * 30

    # Average spread and PnL
    avg_spread = np.mean([e['spread_bps'] for e in events])
    mean_pnl = np.mean([t['net_pnl_bps'] for t in trades])

    # Assumed depth (conservative estimate for Hyperliquid majors)
    typical_depth_usd = 500000  # $500k in top 2% of book

    # Impact at various sizes
    impact_10k = estimate_impact(10000, avg_spread, typical_depth_usd)
    impact_50k = estimate_impact(50000, avg_spread, typical_depth_usd)
    impact_100k = estimate_impact(100000, avg_spread, typical_depth_usd)

    # Breakeven size
    breakeven = find_breakeven_size(mean_pnl, avg_spread, typical_depth_usd)

    # Max practical size (50% of breakeven to maintain edge)
    max_size = breakeven * 0.5 if breakeven > 0 else 10000
    max_size = min(max_size, 100000)  # Cap at $100k per trade
    max_size = max(max_size, 5000)  # Floor at $5k per trade

    size_reason = f"50% of breakeven ({breakeven:.0f} USD) capped at 100k"

    # Daily capacity
    daily_capacity = max_size * trades_per_day
    monthly_capacity = daily_capacity * 30
    annual_capacity = daily_capacity * 252

    # Tier classification
    if daily_capacity < 10000:
        tier = "LOW_VALUE"
    elif daily_capacity < 100000:
        tier = "LIMITED"
    elif daily_capacity < 1000000:
        tier = "VIABLE"
    else:
        tier = "SCALABLE"

    return CapacityEstimate(
        trades_per_day=trades_per_day,
        trades_per_week=trades_per_week,
        trades_per_month=trades_per_month,
        max_size_per_trade_usd=max_size,
        size_limit_reason=size_reason,
        impact_at_10k_bps=impact_10k,
        impact_at_50k_bps=impact_50k,
        impact_at_100k_bps=impact_100k,
        breakeven_size_usd=breakeven,
        daily_capacity_usd=daily_capacity,
        monthly_capacity_usd=monthly_capacity,
        annual_capacity_usd=annual_capacity,
        capacity_tier=tier,
    )


def main():
    parser = argparse.ArgumentParser(description="Capacity estimation")
    parser.add_argument("--split", default="test", help="Data split to analyze")
    parser.add_argument("--exit", default="fixed_15s", help="Exit strategy used")
    parser.add_argument("--days", type=float, default=30, help="Data period in days")
    args = parser.parse_args()

    print("=" * 70)
    print("PHASE 7: CAPACITY & SCALING ESTIMATE")
    print("=" * 70)

    data_dir = PROJECT_ROOT / "data" / "cascade_audit"
    trade_path = data_dir / f"simulated_trades_{args.split}_{args.exit}.json"
    event_path = data_dir / f"cascade_events_{args.split}.json"

    if not trade_path.exists() or not event_path.exists():
        print(f"Error: Required files not found")
        sys.exit(1)

    trades = load_trades(trade_path)
    events = load_events(event_path)

    print(f"\nLoaded {len(trades)} trades from {args.split} split")
    print(f"Data period: {args.days} days")

    # Estimate capacity
    estimate = estimate_capacity(trades, events, args.days)

    # Print results
    print("\n" + "-" * 50)
    print("TRADE FREQUENCY")
    print("-" * 50)
    print(f"Trades per day:    {estimate.trades_per_day:.2f}")
    print(f"Trades per week:   {estimate.trades_per_week:.1f}")
    print(f"Trades per month:  {estimate.trades_per_month:.0f}")

    print("\n" + "-" * 50)
    print("MARKET IMPACT MODEL")
    print("-" * 50)
    print(f"Impact at $10k:    {estimate.impact_at_10k_bps:.1f} bps")
    print(f"Impact at $50k:    {estimate.impact_at_50k_bps:.1f} bps")
    print(f"Impact at $100k:   {estimate.impact_at_100k_bps:.1f} bps")
    print(f"Breakeven size:    ${estimate.breakeven_size_usd:,.0f}")

    print("\n" + "-" * 50)
    print("SIZE LIMITS")
    print("-" * 50)
    print(f"Max size/trade:    ${estimate.max_size_per_trade_usd:,.0f}")
    print(f"Reason:            {estimate.size_limit_reason}")

    print("\n" + "-" * 50)
    print("CAPACITY ESTIMATES")
    print("-" * 50)
    print(f"Daily capacity:    ${estimate.daily_capacity_usd:,.0f}")
    print(f"Monthly capacity:  ${estimate.monthly_capacity_usd:,.0f}")
    print(f"Annual capacity:   ${estimate.annual_capacity_usd:,.0f}")

    print("\n" + "=" * 70)
    print("CAPACITY VERDICT")
    print("=" * 70)

    tier_descriptions = {
        "LOW_VALUE": "Not worth deploying - capacity too low",
        "LIMITED": "Side strategy only - limited capital allocation",
        "VIABLE": "Core strategy candidate - meaningful capacity",
        "SCALABLE": "Primary capital allocation - high capacity",
    }

    print(f"\nTier: {estimate.capacity_tier}")
    print(f"Assessment: {tier_descriptions[estimate.capacity_tier]}")

    if estimate.capacity_tier == "LOW_VALUE":
        print("\nWARNING: Daily capacity below $10k makes this strategy impractical")
    elif estimate.capacity_tier == "LIMITED":
        print(f"\nNOTE: Can deploy ${estimate.daily_capacity_usd:,.0f}/day, suitable for portion of portfolio")
    elif estimate.capacity_tier == "VIABLE":
        print(f"\nCapacity of ${estimate.annual_capacity_usd/1e6:.1f}M/year supports meaningful allocation")
    else:
        print(f"\nHigh capacity (${estimate.annual_capacity_usd/1e6:.1f}M/year) - scalable strategy")

    print("=" * 70)

    # Save results
    output_path = data_dir / f"capacity_estimate_{args.split}_{args.exit}.json"
    with open(output_path, 'w') as f:
        json.dump({
            'trades_per_day': float(estimate.trades_per_day),
            'trades_per_month': float(estimate.trades_per_month),
            'max_size_per_trade_usd': float(estimate.max_size_per_trade_usd),
            'breakeven_size_usd': float(estimate.breakeven_size_usd),
            'daily_capacity_usd': float(estimate.daily_capacity_usd),
            'monthly_capacity_usd': float(estimate.monthly_capacity_usd),
            'annual_capacity_usd': float(estimate.annual_capacity_usd),
            'capacity_tier': estimate.capacity_tier,
            'impact_model': {
                '10k': float(estimate.impact_at_10k_bps),
                '50k': float(estimate.impact_at_50k_bps),
                '100k': float(estimate.impact_at_100k_bps),
            }
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
