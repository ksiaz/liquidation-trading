#!/usr/bin/env python3
"""
Phase 8: Generate Final Verdict

Aggregates all analysis results into final hostile quant verdict.

EDGE STATUS:
- REAL: Statistically significant, robust, passes all tests
- WEAK: Positive expectancy but fails quality thresholds
- FRAGILE: Works only in narrow regimes
- FAKE: No statistical significance or negative expectancy
- INVALID: Data leakage detected
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_json(path: Path) -> dict:
    """Load JSON file."""
    if not path.exists():
        return None
    with open(path, 'r') as f:
        return json.load(f)


def determine_edge_status(
    validation: dict,
    fragility: dict,
    stress: dict,
    capacity: dict
) -> tuple:
    """Determine final edge status.

    Returns: (status, reasons)
    """
    reasons = []

    # Check validation results (test split)
    test = validation.get('test', {})
    expectancy_positive = test.get('expectancy_positive', 0)
    stat_significant = test.get('statistically_significant', 0)
    ci_excludes_zero = test.get('ci_excludes_zero', 0)
    passes_threshold = test.get('passes_threshold', 0)

    # Check fragility
    is_fragile = fragility.get('is_fragile', True) if fragility else True

    # Check stress
    is_unstable = stress.get('is_unstable', True) if stress else True

    # Check capacity
    capacity_tier = capacity.get('capacity_tier', 'LOW_VALUE') if capacity else 'LOW_VALUE'

    # Determine status
    if not expectancy_positive:
        return "FAKE", ["Negative or zero expectancy in out-of-sample data"]

    if not stat_significant:
        reasons.append("Not statistically significant (p >= 0.05)")
        return "FAKE", reasons

    if not ci_excludes_zero:
        reasons.append("95% CI includes zero")
        return "WEAK", reasons

    if is_fragile:
        frag_reasons = fragility.get('reasons', []) if fragility else []
        return "FRAGILE", frag_reasons

    if is_unstable:
        stress_reasons = stress.get('reasons', []) if stress else []
        if len([r for r in stress.get('tests', []) if not r.get('survives', 1)]) >= 2:
            return "WEAK", stress_reasons

    if not passes_threshold:
        return "WEAK", ["Fails quality thresholds (win rate, profit factor, or Sharpe)"]

    if capacity_tier == "LOW_VALUE":
        return "WEAK", ["Capacity too low for practical deployment"]

    # Passed all checks
    return "REAL", ["All validation checks passed"]


def format_verdict(
    validation: dict,
    fragility: dict,
    stress: dict,
    capacity: dict,
    exit_strategy: str
) -> str:
    """Format the final verdict report."""

    status, reasons = determine_edge_status(validation, fragility, stress, capacity)
    test = validation.get('test', {}) if validation else {}

    output = []
    output.append("═" * 70)
    output.append("                    HOSTILE QUANT AUDIT VERDICT")
    output.append("═" * 70)
    output.append("")
    output.append("HYPOTHESIS: Price reverses with positive expectancy after")
    output.append("            liquidation cascade exhaustion")
    output.append("")
    output.append(f"EDGE STATUS: {status}")
    output.append("")

    # Core metrics
    output.append("─" * 70)
    output.append("CORE METRICS (Out-of-Sample)")
    output.append("─" * 70)
    output.append(f"Expected Value per Trade:    {test.get('mean_pnl_bps', 0):.2f} bps")
    output.append(f"95% Confidence Interval:     [{test.get('bootstrap_ci_lower', 0):.2f}, {test.get('bootstrap_ci_upper', 0):.2f}] bps")
    output.append(f"Win Rate:                    {test.get('win_rate', 0)*100:.1f}%")
    output.append(f"Profit Factor:               {test.get('profit_factor', 0):.2f}")
    output.append(f"Sharpe Ratio:                {test.get('sharpe_ratio', 0):.2f}")
    output.append(f"Max Drawdown:                {test.get('max_drawdown_bps', 0):.2f} bps")
    output.append(f"Trade Count (OOS):           {test.get('trade_count', 0)}")
    output.append("")

    # Cost-adjusted
    output.append("─" * 70)
    output.append("COST-ADJUSTED PERFORMANCE")
    output.append("─" * 70)
    gross = test.get('mean_pnl_bps', 0) + 5  # Approximate gross (add back fees)
    output.append(f"Gross Expectancy:            {gross:.2f} bps")
    output.append(f"Fees + Slippage:            -{5:.2f} bps")
    output.append(f"Net Expectancy:              {test.get('mean_pnl_bps', 0):.2f} bps")
    output.append(f"Survives Costs:              {'YES' if test.get('mean_pnl_bps', 0) > 0 else 'NO'}")
    output.append("")

    # Regime analysis
    output.append("─" * 70)
    output.append("REGIME ANALYSIS")
    output.append("─" * 70)
    if fragility:
        regimes = fragility.get('regimes', [])
        positive_count = sum(1 for r in regimes if r.get('expectancy_positive', 0))
        max_contrib = max((r.get('profit_contribution_pct', 0) for r in regimes), default=0)
        worst_regime = min(regimes, key=lambda r: r.get('mean_pnl_bps', 0)) if regimes else {}
        output.append(f"Regimes with positive EV:    {positive_count} / {len(regimes)}")
        output.append(f"Worst regime:                {worst_regime.get('name', 'N/A')} ({worst_regime.get('mean_pnl_bps', 0):.2f} bps)")
        output.append(f"Concentration risk:          {max_contrib:.1f}% from single regime")
    else:
        output.append("Regime analysis not available")
    output.append("")

    # Stress tests
    output.append("─" * 70)
    output.append("STRESS TEST RESULTS")
    output.append("─" * 70)
    if stress:
        tests = stress.get('tests', [])
        for test_result in tests:
            name = test_result.get('name', 'unknown').replace('_', ' ').title()
            survives = "PASS" if test_result.get('survives', 0) else "FAIL"
            output.append(f"{name:<30} {survives}")
    else:
        output.append("Stress tests not available")
    output.append("")

    # Capacity
    output.append("─" * 70)
    output.append("CAPACITY ESTIMATE")
    output.append("─" * 70)
    if capacity:
        output.append(f"Max size per trade:          ${capacity.get('max_size_per_trade_usd', 0):,.0f}")
        output.append(f"Trades per day:              {capacity.get('trades_per_day', 0):.1f}")
        output.append(f"Daily capacity:              ${capacity.get('daily_capacity_usd', 0):,.0f}")
        output.append(f"Annual capacity:             ${capacity.get('annual_capacity_usd', 0)/1e6:.2f}M")
        output.append(f"Tier:                        {capacity.get('capacity_tier', 'UNKNOWN')}")
    else:
        output.append("Capacity estimate not available")
    output.append("")

    # Failure risks
    output.append("─" * 70)
    output.append("PRIMARY FAILURE RISKS")
    output.append("─" * 70)
    risk_count = 1
    if fragility and fragility.get('is_fragile'):
        for reason in fragility.get('reasons', [])[:3]:
            output.append(f"{risk_count}. {reason}")
            risk_count += 1
    if stress and stress.get('is_unstable'):
        for reason in stress.get('reasons', [])[:3]:
            if risk_count <= 3:
                output.append(f"{risk_count}. {reason}")
                risk_count += 1
    if risk_count == 1:
        output.append("1. No critical risks identified")
    output.append("")

    # Final recommendation
    output.append("═" * 70)

    if status == "REAL":
        recommendation = "DEPLOY"
        output.append(f"RECOMMENDATION: {recommendation}")
        output.append("")
        output.append("Statistical evidence supports positive expectancy.")
        output.append("Edge appears real and robust under stress testing.")
    elif status == "WEAK":
        recommendation = "RESEARCH"
        output.append(f"RECOMMENDATION: {recommendation}")
        output.append("")
        output.append("Edge shows promise but fails quality thresholds.")
        output.append("Further research needed before deployment.")
    elif status == "FRAGILE":
        recommendation = "LIMIT"
        output.append(f"RECOMMENDATION: {recommendation}")
        output.append("")
        output.append("Edge exists but only in specific regimes.")
        output.append("Deploy with regime filters and reduced size.")
    else:  # FAKE
        recommendation = "ABANDON"
        output.append(f"RECOMMENDATION: {recommendation}")
        output.append("")
        output.append("No statistically significant edge detected.")
        output.append("Do not deploy capital on this strategy.")

    output.append("═" * 70)
    output.append("")
    output.append(f"Generated: {datetime.now().isoformat()}")
    output.append(f"Exit Strategy: {exit_strategy}")
    output.append(f"Data: Synthetic (replace with real data for production audit)")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Generate final verdict")
    parser.add_argument("--split", default="test", help="Data split analyzed")
    parser.add_argument("--exit", default="fixed_15s", help="Exit strategy used")
    parser.add_argument("--output", default=None, help="Output file (stdout if not specified)")
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / "data" / "cascade_audit"

    # Load all results
    validation = load_json(data_dir / f"validation_results_{args.exit}.json")
    fragility = load_json(data_dir / f"regime_fragility_{args.split}_{args.exit}.json")
    stress = load_json(data_dir / f"adversarial_stress_{args.split}_{args.exit}.json")
    capacity = load_json(data_dir / f"capacity_estimate_{args.split}_{args.exit}.json")

    # Generate verdict
    verdict = format_verdict(validation, fragility, stress, capacity, args.exit)

    # Output
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(verdict)
        print(f"Verdict saved to {output_path}")
    else:
        print(verdict)


if __name__ == "__main__":
    main()
