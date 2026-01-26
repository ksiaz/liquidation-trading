#!/usr/bin/env python3
"""
Phase 6: Adversarial Stress Test

Try to KILL the edge with perturbations:
- Timing jitter (±50-200ms)
- Delayed entry (+500ms)
- Doubled slippage
- Increased size (3x)
- Remove best 10% of trades
- Remove best day
- Signal noise (±10% thresholds)

EDGE UNSTABLE if:
- Any 2+ perturbations destroy edge
- Timing jitter alone kills edge
- Edge depends on top 10% of trades
"""

import json
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple
import numpy as np
from copy import deepcopy

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class StressResult:
    """Result of a stress test."""
    test_name: str
    description: str
    original_mean_bps: float
    stressed_mean_bps: float
    original_win_rate: float
    stressed_win_rate: float
    change_pct: float
    survives: bool
    kill_reason: str


def load_trades(path: Path) -> List[Dict]:
    """Load simulated trades from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def compute_stats(trades: List[Dict]) -> Tuple[float, float]:
    """Compute mean PnL and win rate."""
    if not trades:
        return 0, 0
    pnls = [t['net_pnl_bps'] for t in trades]
    return np.mean(pnls), len([p for p in pnls if p > 0]) / len(pnls)


class StressTester:
    """Applies adversarial perturbations to trades."""

    def __init__(self, trades: List[Dict]):
        self.original_trades = trades
        self.original_mean, self.original_win_rate = compute_stats(trades)

    def test_timing_jitter(self, jitter_range_ms: Tuple[int, int] = (50, 200)) -> StressResult:
        """Test with random timing jitter.

        Simulates execution timing variance that might change fill prices.
        """
        np.random.seed(42)
        stressed_trades = []

        for t in self.original_trades:
            t_copy = deepcopy(t)
            # Jitter affects entry slippage (adverse movement during delay)
            jitter_ms = np.random.uniform(jitter_range_ms[0], jitter_range_ms[1])
            jitter_cost_bps = jitter_ms / 1000 * t['volatility_1h'] * 50  # Volatility impact

            # Apply jitter as additional cost (can be positive or negative)
            direction = 1 if np.random.random() > 0.5 else -1
            t_copy['net_pnl_bps'] -= abs(jitter_cost_bps) * 0.5  # Average impact

            stressed_trades.append(t_copy)

        mean, win_rate = compute_stats(stressed_trades)
        survives = mean > 0

        return StressResult(
            test_name="timing_jitter",
            description=f"Random timing jitter ±{jitter_range_ms}ms",
            original_mean_bps=self.original_mean,
            stressed_mean_bps=mean,
            original_win_rate=self.original_win_rate,
            stressed_win_rate=win_rate,
            change_pct=(mean - self.original_mean) / abs(self.original_mean) * 100 if self.original_mean != 0 else 0,
            survives=survives,
            kill_reason="" if survives else "Timing jitter destroys positive expectancy"
        )

    def test_delayed_entry(self, delay_ms: float = 500) -> StressResult:
        """Test with fixed entry delay.

        Simulates slower execution infrastructure.
        """
        stressed_trades = []

        for t in self.original_trades:
            t_copy = deepcopy(t)
            # Delay adds slippage cost
            delay_cost_bps = delay_ms / 1000 * t['volatility_1h'] * 30  # Cost of delay
            t_copy['net_pnl_bps'] -= delay_cost_bps
            stressed_trades.append(t_copy)

        mean, win_rate = compute_stats(stressed_trades)
        survives = mean > 0

        return StressResult(
            test_name="delayed_entry",
            description=f"Entry delayed by {delay_ms}ms",
            original_mean_bps=self.original_mean,
            stressed_mean_bps=mean,
            original_win_rate=self.original_win_rate,
            stressed_win_rate=win_rate,
            change_pct=(mean - self.original_mean) / abs(self.original_mean) * 100 if self.original_mean != 0 else 0,
            survives=survives,
            kill_reason="" if survives else "500ms delay destroys positive expectancy"
        )

    def test_doubled_slippage(self) -> StressResult:
        """Test with 2x slippage costs."""
        stressed_trades = []

        for t in self.original_trades:
            t_copy = deepcopy(t)
            # Double the slippage impact
            extra_slippage = t['entry_slippage_bps'] + t['exit_slippage_bps']
            t_copy['net_pnl_bps'] -= extra_slippage
            stressed_trades.append(t_copy)

        mean, win_rate = compute_stats(stressed_trades)
        survives = mean > 0

        return StressResult(
            test_name="doubled_slippage",
            description="Slippage costs doubled",
            original_mean_bps=self.original_mean,
            stressed_mean_bps=mean,
            original_win_rate=self.original_win_rate,
            stressed_win_rate=win_rate,
            change_pct=(mean - self.original_mean) / abs(self.original_mean) * 100 if self.original_mean != 0 else 0,
            survives=survives,
            kill_reason="" if survives else "Doubled slippage destroys positive expectancy"
        )

    def test_increased_size(self, size_mult: float = 3.0) -> StressResult:
        """Test with larger trade size (more market impact)."""
        stressed_trades = []

        for t in self.original_trades:
            t_copy = deepcopy(t)
            # Larger size = more slippage (non-linear)
            size_impact_bps = (size_mult - 1) * t['entry_slippage_bps'] * 0.5
            t_copy['net_pnl_bps'] -= size_impact_bps
            stressed_trades.append(t_copy)

        mean, win_rate = compute_stats(stressed_trades)
        # For size test, check if expectancy drops by > 50%
        pct_drop = (self.original_mean - mean) / abs(self.original_mean) * 100 if self.original_mean != 0 else 0
        survives = pct_drop < 50

        return StressResult(
            test_name="increased_size",
            description=f"Trade size increased {size_mult}x",
            original_mean_bps=self.original_mean,
            stressed_mean_bps=mean,
            original_win_rate=self.original_win_rate,
            stressed_win_rate=win_rate,
            change_pct=-pct_drop,
            survives=survives,
            kill_reason="" if survives else f"Size increase causes {pct_drop:.1f}% drop (threshold: 50%)"
        )

    def test_remove_best_10pct(self) -> StressResult:
        """Test with top 10% of trades removed.

        Checks if edge depends on outliers.
        """
        sorted_trades = sorted(self.original_trades, key=lambda t: t['net_pnl_bps'], reverse=True)
        cutoff = int(len(sorted_trades) * 0.1)
        stressed_trades = sorted_trades[cutoff:]

        mean, win_rate = compute_stats(stressed_trades)
        survives = mean > 0

        return StressResult(
            test_name="remove_best_10pct",
            description="Top 10% of trades removed",
            original_mean_bps=self.original_mean,
            stressed_mean_bps=mean,
            original_win_rate=self.original_win_rate,
            stressed_win_rate=win_rate,
            change_pct=(mean - self.original_mean) / abs(self.original_mean) * 100 if self.original_mean != 0 else 0,
            survives=survives,
            kill_reason="" if survives else "Edge depends on top 10% outliers"
        )

    def test_remove_best_day(self) -> StressResult:
        """Test with best trading day removed.

        Checks if edge depends on single lucky day.
        """
        # Group by approximate day (using timestamp buckets)
        trades_by_day = {}
        for t in self.original_trades:
            day = t['entry_timestamp_ns'] // (24 * 3600 * 1e9)  # Day bucket
            if day not in trades_by_day:
                trades_by_day[day] = []
            trades_by_day[day].append(t)

        # Find best day
        day_profits = {day: sum(t['net_pnl_bps'] for t in trades)
                      for day, trades in trades_by_day.items()}
        best_day = max(day_profits, key=day_profits.get)

        # Remove best day's trades
        stressed_trades = [t for t in self.original_trades
                         if t['entry_timestamp_ns'] // (24 * 3600 * 1e9) != best_day]

        if not stressed_trades:
            # All trades were on one day
            return StressResult(
                test_name="remove_best_day",
                description="Best trading day removed",
                original_mean_bps=self.original_mean,
                stressed_mean_bps=0,
                original_win_rate=self.original_win_rate,
                stressed_win_rate=0,
                change_pct=-100,
                survives=False,
                kill_reason="All trades on single day"
            )

        mean, win_rate = compute_stats(stressed_trades)
        survives = mean > 0

        return StressResult(
            test_name="remove_best_day",
            description=f"Best day removed ({len(trades_by_day[best_day])} trades, {day_profits[best_day]:.1f} bps)",
            original_mean_bps=self.original_mean,
            stressed_mean_bps=mean,
            original_win_rate=self.original_win_rate,
            stressed_win_rate=win_rate,
            change_pct=(mean - self.original_mean) / abs(self.original_mean) * 100 if self.original_mean != 0 else 0,
            survives=survives,
            kill_reason="" if survives else "Edge depends on single lucky day"
        )

    def test_signal_noise(self, noise_pct: float = 0.10) -> StressResult:
        """Test with noise added to signal (simulates threshold uncertainty).

        Adds random perturbation to trade PnL (simulating less perfect signals).
        """
        np.random.seed(42)
        stressed_trades = []

        for t in self.original_trades:
            t_copy = deepcopy(t)
            # Add noise proportional to volatility
            noise_bps = np.random.normal(0, t['volatility_1h'] * 100 * noise_pct)
            t_copy['net_pnl_bps'] += noise_bps
            stressed_trades.append(t_copy)

        mean, win_rate = compute_stats(stressed_trades)
        # For noise test, check win rate threshold
        survives = win_rate > 0.40

        return StressResult(
            test_name="signal_noise",
            description=f"±{noise_pct*100:.0f}% signal noise added",
            original_mean_bps=self.original_mean,
            stressed_mean_bps=mean,
            original_win_rate=self.original_win_rate,
            stressed_win_rate=win_rate,
            change_pct=(mean - self.original_mean) / abs(self.original_mean) * 100 if self.original_mean != 0 else 0,
            survives=survives,
            kill_reason="" if survives else f"Win rate drops below 40% ({win_rate*100:.1f}%)"
        )

    def run_all_tests(self) -> List[StressResult]:
        """Run all stress tests."""
        return [
            self.test_timing_jitter(),
            self.test_delayed_entry(),
            self.test_doubled_slippage(),
            self.test_increased_size(),
            self.test_remove_best_10pct(),
            self.test_remove_best_day(),
            self.test_signal_noise(),
        ]


def check_stability(results: List[StressResult]) -> Tuple[bool, List[str]]:
    """Check if edge is unstable.

    Returns: (is_unstable, reasons)
    """
    reasons = []
    failures = [r for r in results if not r.survives]

    # Check 1: Any 2+ perturbations destroy edge
    if len(failures) >= 2:
        reasons.append(f"{len(failures)} perturbations destroy edge (threshold: 2)")

    # Check 2: Timing jitter alone kills edge
    timing_result = next((r for r in results if r.test_name == "timing_jitter"), None)
    if timing_result and not timing_result.survives:
        reasons.append("Timing jitter alone destroys edge (critical)")

    # Check 3: Edge depends on top 10%
    top10_result = next((r for r in results if r.test_name == "remove_best_10pct"), None)
    if top10_result and not top10_result.survives:
        reasons.append("Edge depends on top 10% of trades (outlier dependent)")

    return len(reasons) > 0, reasons


def main():
    parser = argparse.ArgumentParser(description="Adversarial stress testing")
    parser.add_argument("--split", default="test", help="Data split to test")
    parser.add_argument("--exit", default="fixed_15s", help="Exit strategy used")
    args = parser.parse_args()

    print("=" * 70)
    print("PHASE 6: ADVERSARIAL STRESS TEST")
    print("=" * 70)

    data_dir = PROJECT_ROOT / "data" / "cascade_audit"
    trade_path = data_dir / f"simulated_trades_{args.split}_{args.exit}.json"

    if not trade_path.exists():
        print(f"Error: {trade_path} not found")
        sys.exit(1)

    trades = load_trades(trade_path)
    print(f"\nLoaded {len(trades)} trades from {args.split} split")
    print(f"Original mean PnL: {np.mean([t['net_pnl_bps'] for t in trades]):.2f} bps")

    # Run all tests
    tester = StressTester(trades)
    results = tester.run_all_tests()

    # Print results
    print("\n" + "-" * 70)
    print(f"{'Test':<25} {'Original':>10} {'Stressed':>10} {'Change':>10} {'Result':>10}")
    print("-" * 70)

    for r in results:
        status = "PASS" if r.survives else "FAIL"
        print(f"{r.test_name:<25} {r.original_mean_bps:>10.1f} {r.stressed_mean_bps:>10.1f} {r.change_pct:>9.1f}% {status:>10}")

    # Check stability
    is_unstable, reasons = check_stability(results)

    print("\n" + "=" * 70)
    print("STABILITY VERDICT")
    print("=" * 70)

    if is_unstable:
        print("\nVERDICT: EDGE UNSTABLE")
        print("\nReasons:")
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("\nVERDICT: EDGE STABLE")
        print("\nEdge survives adversarial perturbations:")
        for r in results:
            if r.survives:
                print(f"  - {r.test_name}: {r.stressed_mean_bps:.1f} bps (survived)")

    # Failed tests
    failures = [r for r in results if not r.survives]
    if failures:
        print(f"\nFailed tests ({len(failures)}):")
        for r in failures:
            print(f"  - {r.test_name}: {r.kill_reason}")

    print("=" * 70)

    # Save results
    output_path = data_dir / f"adversarial_stress_{args.split}_{args.exit}.json"
    with open(output_path, 'w') as f:
        json.dump({
            'is_unstable': is_unstable,
            'reasons': reasons,
            'tests': [
                {
                    'name': r.test_name,
                    'description': r.description,
                    'original_mean_bps': float(r.original_mean_bps),
                    'stressed_mean_bps': float(r.stressed_mean_bps),
                    'change_pct': float(r.change_pct),
                    'survives': int(r.survives),
                    'kill_reason': r.kill_reason,
                }
                for r in results
            ]
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
