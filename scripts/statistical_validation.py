#!/usr/bin/env python3
"""
Phase 4: Statistical Validation

Computes comprehensive statistics for trade simulation:
- Bootstrap confidence intervals
- P-values for positive expectancy
- Distribution analysis
- Out-of-sample validation

CRITICAL: Out-of-sample metrics determine verdict, NOT in-sample.
"""

import json
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple
import numpy as np
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ValidationResult:
    """Statistical validation results."""
    split: str
    trade_count: int

    # Core metrics
    mean_pnl_bps: float
    std_pnl_bps: float
    median_pnl_bps: float

    # Win/loss analysis
    win_rate: float
    profit_factor: float
    avg_win_bps: float
    avg_loss_bps: float

    # Distribution
    skew: float
    kurtosis: float
    tail_loss_5pct: float
    tail_loss_1pct: float

    # Statistical significance
    t_statistic: float
    p_value: float
    ci_lower_95: float
    ci_upper_95: float
    ci_lower_99: float
    ci_upper_99: float

    # Bootstrap results
    bootstrap_mean: float
    bootstrap_std: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float

    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_bps: float
    calmar_ratio: float

    # Verdict components
    expectancy_positive: bool
    statistically_significant: bool
    ci_excludes_zero: bool
    passes_threshold: bool


def load_trades(path: Path) -> List[Dict]:
    """Load simulated trades from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def bootstrap_mean(data: np.ndarray, n_iterations: int = 10000) -> Tuple[float, float, float, float]:
    """Bootstrap confidence interval for mean.

    Returns: (bootstrap_mean, bootstrap_std, ci_lower, ci_upper)
    """
    n = len(data)
    bootstrap_means = []

    for _ in range(n_iterations):
        sample = np.random.choice(data, size=n, replace=True)
        bootstrap_means.append(np.mean(sample))

    bootstrap_means = np.array(bootstrap_means)

    return (
        np.mean(bootstrap_means),
        np.std(bootstrap_means),
        np.percentile(bootstrap_means, 2.5),
        np.percentile(bootstrap_means, 97.5)
    )


def compute_drawdown(pnls: np.ndarray) -> float:
    """Compute maximum drawdown from PnL series."""
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    return np.max(drawdown)


def validate_trades(trades: List[Dict], split: str) -> ValidationResult:
    """Compute all validation statistics for a set of trades."""

    pnls = np.array([t['net_pnl_bps'] for t in trades])
    n = len(pnls)

    if n == 0:
        raise ValueError("No trades to validate")

    # Core metrics
    mean_pnl = np.mean(pnls)
    std_pnl = np.std(pnls)
    median_pnl = np.median(pnls)

    # Win/loss analysis
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    win_rate = len(wins) / n
    profit_factor = abs(np.sum(wins) / np.sum(losses)) if len(losses) > 0 and np.sum(losses) != 0 else float('inf')
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0

    # Distribution analysis
    skew = stats.skew(pnls)
    kurtosis = stats.kurtosis(pnls)
    tail_loss_5 = np.percentile(pnls, 5)
    tail_loss_1 = np.percentile(pnls, 1)

    # T-test for positive expectancy
    t_stat, p_value = stats.ttest_1samp(pnls, 0)
    # One-tailed test for positive expectancy
    p_value_one_tail = p_value / 2 if t_stat > 0 else 1 - p_value / 2

    # Confidence intervals (parametric)
    se = std_pnl / np.sqrt(n)
    ci_95 = stats.t.interval(0.95, n-1, loc=mean_pnl, scale=se)
    ci_99 = stats.t.interval(0.99, n-1, loc=mean_pnl, scale=se)

    # Bootstrap
    bs_mean, bs_std, bs_ci_lower, bs_ci_upper = bootstrap_mean(pnls)

    # Risk metrics
    # Sharpe: assume daily trading, annualize with sqrt(252)
    # Simplified: trades per day estimate
    trades_per_day_est = max(1, n / 30)  # Assume 30 days of data
    sharpe = (mean_pnl / std_pnl) * np.sqrt(trades_per_day_est * 252) if std_pnl > 0 else 0

    # Sortino: use only downside deviation
    downside = pnls[pnls < 0]
    downside_std = np.std(downside) if len(downside) > 0 else std_pnl
    sortino = (mean_pnl / downside_std) * np.sqrt(trades_per_day_est * 252) if downside_std > 0 else 0

    # Drawdown
    max_dd = compute_drawdown(pnls)
    calmar = (mean_pnl * trades_per_day_est * 252) / max_dd if max_dd > 0 else float('inf')

    # Verdict components (from plan thresholds)
    expectancy_positive = mean_pnl > 0
    statistically_significant = p_value_one_tail < 0.05
    ci_excludes_zero = bs_ci_lower > 0
    passes_threshold = (
        mean_pnl > 0 and
        win_rate > 0.45 and
        profit_factor > 1.2 and
        sharpe > 1.0
    )

    return ValidationResult(
        split=split,
        trade_count=n,
        mean_pnl_bps=mean_pnl,
        std_pnl_bps=std_pnl,
        median_pnl_bps=median_pnl,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win_bps=avg_win,
        avg_loss_bps=avg_loss,
        skew=skew,
        kurtosis=kurtosis,
        tail_loss_5pct=tail_loss_5,
        tail_loss_1pct=tail_loss_1,
        t_statistic=t_stat,
        p_value=p_value_one_tail,
        ci_lower_95=ci_95[0],
        ci_upper_95=ci_95[1],
        ci_lower_99=ci_99[0],
        ci_upper_99=ci_99[1],
        bootstrap_mean=bs_mean,
        bootstrap_std=bs_std,
        bootstrap_ci_lower=bs_ci_lower,
        bootstrap_ci_upper=bs_ci_upper,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_bps=max_dd,
        calmar_ratio=calmar,
        expectancy_positive=expectancy_positive,
        statistically_significant=statistically_significant,
        ci_excludes_zero=ci_excludes_zero,
        passes_threshold=passes_threshold,
    )


def print_results(result: ValidationResult):
    """Print formatted validation results."""
    print(f"\n{'='*60}")
    print(f"VALIDATION RESULTS: {result.split.upper()}")
    print(f"{'='*60}")

    print(f"\n--- Core Metrics ---")
    print(f"Trade Count:        {result.trade_count}")
    print(f"Mean PnL:           {result.mean_pnl_bps:.2f} bps")
    print(f"Std PnL:            {result.std_pnl_bps:.2f} bps")
    print(f"Median PnL:         {result.median_pnl_bps:.2f} bps")

    print(f"\n--- Win/Loss Analysis ---")
    print(f"Win Rate:           {result.win_rate*100:.1f}%")
    print(f"Profit Factor:      {result.profit_factor:.2f}")
    print(f"Avg Win:            {result.avg_win_bps:.2f} bps")
    print(f"Avg Loss:           {result.avg_loss_bps:.2f} bps")

    print(f"\n--- Distribution ---")
    print(f"Skew:               {result.skew:.2f}")
    print(f"Kurtosis:           {result.kurtosis:.2f}")
    print(f"Tail Loss (5%):     {result.tail_loss_5pct:.2f} bps")
    print(f"Tail Loss (1%):     {result.tail_loss_1pct:.2f} bps")

    print(f"\n--- Statistical Significance ---")
    print(f"T-Statistic:        {result.t_statistic:.3f}")
    print(f"P-Value (one-tail): {result.p_value:.4f}")
    print(f"95% CI:             [{result.ci_lower_95:.2f}, {result.ci_upper_95:.2f}] bps")
    print(f"99% CI:             [{result.ci_lower_99:.2f}, {result.ci_upper_99:.2f}] bps")

    print(f"\n--- Bootstrap (10k iterations) ---")
    print(f"Bootstrap Mean:     {result.bootstrap_mean:.2f} bps")
    print(f"Bootstrap Std:      {result.bootstrap_std:.2f} bps")
    print(f"Bootstrap 95% CI:   [{result.bootstrap_ci_lower:.2f}, {result.bootstrap_ci_upper:.2f}] bps")

    print(f"\n--- Risk Metrics ---")
    print(f"Sharpe Ratio:       {result.sharpe_ratio:.2f}")
    print(f"Sortino Ratio:      {result.sortino_ratio:.2f}")
    print(f"Max Drawdown:       {result.max_drawdown_bps:.2f} bps")
    print(f"Calmar Ratio:       {result.calmar_ratio:.2f}")

    print(f"\n--- Verdict Components ---")
    print(f"Expectancy > 0:     {'PASS' if result.expectancy_positive else 'FAIL'}")
    print(f"Stat Significant:   {'PASS' if result.statistically_significant else 'FAIL'} (p < 0.05)")
    print(f"CI Excludes 0:      {'PASS' if result.ci_excludes_zero else 'FAIL'}")
    print(f"Passes Thresholds:  {'PASS' if result.passes_threshold else 'FAIL'}")


def main():
    parser = argparse.ArgumentParser(description="Statistical validation of trades")
    parser.add_argument("--split", choices=["train", "validation", "test", "all"],
                       default="test", help="Data split to validate")
    parser.add_argument("--exit", default="fixed_15s", help="Exit strategy used in simulation")
    args = parser.parse_args()

    print("=" * 70)
    print("PHASE 4: STATISTICAL VALIDATION")
    print("=" * 70)

    data_dir = PROJECT_ROOT / "data" / "cascade_audit"

    if args.split == "all":
        splits = ["train", "validation", "test"]
    else:
        splits = [args.split]

    results = {}

    for split in splits:
        trade_path = data_dir / f"simulated_trades_{split}_{args.exit}.json"
        if not trade_path.exists():
            print(f"\nWarning: {trade_path} not found, skipping")
            continue

        print(f"\nLoading {split} trades...")
        trades = load_trades(trade_path)
        print(f"  Loaded {len(trades)} trades")

        result = validate_trades(trades, split)
        results[split] = result
        print_results(result)

    # Final verdict based on OUT-OF-SAMPLE results only
    if "test" in results:
        test_result = results["test"]

        print("\n" + "=" * 70)
        print("OUT-OF-SAMPLE VERDICT (THIS IS WHAT MATTERS)")
        print("=" * 70)

        all_pass = (
            test_result.expectancy_positive and
            test_result.statistically_significant and
            test_result.ci_excludes_zero
        )

        if all_pass and test_result.passes_threshold:
            print("VERDICT: EDGE APPEARS REAL")
            print("         Statistical evidence supports positive expectancy")
        elif all_pass:
            print("VERDICT: EDGE WEAK")
            print("         Positive expectancy but fails quality thresholds")
        elif test_result.expectancy_positive:
            print("VERDICT: EDGE NOT SIGNIFICANT")
            print("         Positive mean but not statistically significant")
        else:
            print("VERDICT: NO EDGE")
            print("         Negative or zero expectancy in out-of-sample")

        print("\n" + "=" * 70)

    # Save results (convert numpy types to Python types)
    output_path = data_dir / f"validation_results_{args.exit}.json"

    def serialize(obj):
        """Convert numpy types to Python types."""
        d = asdict(obj)
        for k, v in d.items():
            if isinstance(v, (np.bool_, np.integer)):
                d[k] = int(v)
            elif isinstance(v, np.floating):
                d[k] = float(v)
            elif isinstance(v, bool):
                d[k] = int(v)  # JSON doesn't have bool, use 0/1
        return d

    with open(output_path, 'w') as f:
        json.dump({k: serialize(v) for k, v in results.items()}, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
