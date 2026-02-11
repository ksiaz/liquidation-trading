#!/usr/bin/env python3
"""
OBSERVATIONAL CALIBRATION PHASE
================================
Purpose: Measure empirical distributions of signals without evaluating performance.
Mode: HL-ONLY, NO TRADING, NO OPTIMIZATION

This script:
1. Reads HL node data (prices, liquidations) - NO BINANCE
2. Feeds into M1 observation system
3. Logs all raw events and M4 primitives
4. Produces distribution statistics

CONSTRAINTS (ENFORCED):
- NO order placement
- NO PnL calculation
- NO threshold tuning
- NO edge inference
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from collections import defaultdict
import statistics

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "hl-adapter"))

# Configuration enforcement
CALIBRATION_CONFIG = {
    "hl_node_enabled": True,
    "binance_ingestion_enabled": False,  # DISABLED
    "live_execution_enabled": False,     # DISABLED
    "strategies_enabled": True,          # For observation only
    "order_submission_enabled": False,   # DISABLED
}

print("=" * 60, file=sys.stderr)
print("OBSERVATIONAL CALIBRATION MODE", file=sys.stderr)
print("=" * 60, file=sys.stderr)
for key, value in CALIBRATION_CONFIG.items():
    status = "ENABLED" if value else "DISABLED"
    print(f"  {key}: {status}", file=sys.stderr)
print("=" * 60, file=sys.stderr)


@dataclass
class RawLiquidationRecord:
    """Raw liquidation event - no filtering."""
    timestamp_ms: int
    symbol: str
    side: str           # Original: LONG/SHORT
    order_side: str     # Canonical: BUY/SELL
    quantity: float
    quote_qty: float
    price: float
    mark_price: Optional[float]
    method: str
    liquidated_wallet: str
    liquidator_wallet: Optional[str]
    # Cascade context
    cascade_id: Optional[str] = None
    liquidation_index: int = 0
    time_since_previous_ms: Optional[int] = None
    cumulative_quote_qty: float = 0.0
    cascade_duration_ms: int = 0


@dataclass
class PrimitiveSnapshot:
    """M4 primitive values at observation time."""
    timestamp: float
    symbol: str
    # Zone geometry
    zone_penetration_depth: Optional[float] = None
    zone_penetration_pct: Optional[float] = None
    # Kinematics
    price_traversal_velocity: Optional[float] = None
    traversal_compactness: Optional[float] = None
    # Cascade
    cascade_intensity: Optional[float] = None
    liquidation_rate: Optional[float] = None
    positions_at_risk: Optional[int] = None
    aggregate_risk_value: Optional[float] = None
    # Order book (if available)
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    imbalance: Optional[float] = None
    # Absorption
    absorption_detected: Optional[bool] = None
    consumption_size: Optional[float] = None


@dataclass
class StrategyProposalRecord:
    """Strategy proposal - observation only, no judgment."""
    timestamp: float
    strategy_name: str
    symbol: str
    proposal_type: str  # ENTRY, EXIT, HOLD, BLOCK
    confidence: Optional[float]
    triggering_primitives: Dict[str, Any]
    arbitration_outcome: Optional[str] = None
    blocking_reason: Optional[str] = None


class ObservationalCalibrator:
    """Collects raw observations without evaluation."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Raw event storage
        self.liquidations: List[RawLiquidationRecord] = []
        self.primitives: List[PrimitiveSnapshot] = []
        self.proposals: List[StrategyProposalRecord] = []

        # Cascade tracking
        self.active_cascades: Dict[str, List[RawLiquidationRecord]] = defaultdict(list)
        self.cascade_counter = 0
        self.last_liq_time: Dict[str, int] = {}

        # Primitive distributions (for live stats)
        self.primitive_values: Dict[str, List[float]] = defaultdict(list)

        # Counters
        self.total_liquidations = 0
        self.total_cascades = 0
        self.total_proposals = 0

        # Cascade detection parameters (from observed patterns)
        self.CASCADE_GAP_MS = 5000  # 5 second gap ends cascade

    def record_liquidation(
        self,
        timestamp_ms: int,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        mark_price: Optional[float],
        method: str,
        liquidated_wallet: str,
        liquidator_wallet: Optional[str] = None,
    ):
        """Record raw liquidation event."""
        # Map side to canonical
        order_side = "SELL" if side == "LONG" else "BUY"
        quote_qty = quantity * price

        # Cascade detection
        cascade_id = None
        liq_index = 0
        time_since_prev = None
        cumulative_qty = quote_qty
        cascade_duration = 0

        prev_time = self.last_liq_time.get(symbol)
        if prev_time and (timestamp_ms - prev_time) < self.CASCADE_GAP_MS:
            # Part of existing cascade
            cascade_key = f"{symbol}_cascade_{self.cascade_counter}"
            if cascade_key in self.active_cascades:
                cascade_id = cascade_key
                liq_index = len(self.active_cascades[cascade_key])
                time_since_prev = timestamp_ms - prev_time
                # Sum up cumulative
                for prev_liq in self.active_cascades[cascade_key]:
                    cumulative_qty += prev_liq.quote_qty
                cascade_duration = timestamp_ms - self.active_cascades[cascade_key][0].timestamp_ms
        else:
            # New cascade
            self.cascade_counter += 1
            cascade_key = f"{symbol}_cascade_{self.cascade_counter}"
            cascade_id = cascade_key
            self.active_cascades[cascade_key] = []
            self.total_cascades += 1

        record = RawLiquidationRecord(
            timestamp_ms=timestamp_ms,
            symbol=symbol,
            side=side,
            order_side=order_side,
            quantity=quantity,
            quote_qty=quote_qty,
            price=price,
            mark_price=mark_price,
            method=method,
            liquidated_wallet=liquidated_wallet,
            liquidator_wallet=liquidator_wallet,
            cascade_id=cascade_id,
            liquidation_index=liq_index,
            time_since_previous_ms=time_since_prev,
            cumulative_quote_qty=cumulative_qty,
            cascade_duration_ms=cascade_duration,
        )

        self.liquidations.append(record)
        if cascade_id:
            self.active_cascades[cascade_id].append(record)
        self.last_liq_time[symbol] = timestamp_ms
        self.total_liquidations += 1

        # Track distribution values
        self.primitive_values["quote_qty"].append(quote_qty)
        if time_since_prev:
            self.primitive_values["time_between_liqs_ms"].append(time_since_prev)

    def record_primitives(self, snapshot: PrimitiveSnapshot):
        """Record M4 primitive values."""
        self.primitives.append(snapshot)

        # Track distributions
        for field, value in asdict(snapshot).items():
            if value is not None and isinstance(value, (int, float)) and field not in ("timestamp",):
                self.primitive_values[field].append(float(value))

    def record_proposal(self, proposal: StrategyProposalRecord):
        """Record strategy proposal."""
        self.proposals.append(proposal)
        self.total_proposals += 1

    def compute_distributions(self) -> Dict[str, Dict[str, float]]:
        """Compute distribution statistics for all primitives."""
        distributions = {}

        for name, values in self.primitive_values.items():
            if len(values) < 2:
                continue

            sorted_vals = sorted(values)
            n = len(sorted_vals)

            distributions[name] = {
                "count": n,
                "min": sorted_vals[0],
                "max": sorted_vals[-1],
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "p5": sorted_vals[int(n * 0.05)] if n > 20 else None,
                "p25": sorted_vals[int(n * 0.25)] if n > 4 else None,
                "p50": sorted_vals[int(n * 0.50)],
                "p75": sorted_vals[int(n * 0.75)] if n > 4 else None,
                "p95": sorted_vals[int(n * 0.95)] if n > 20 else None,
                "stdev": statistics.stdev(values) if n > 1 else 0,
            }

        return distributions

    def write_outputs(self):
        """Write all collected data to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. Raw liquidations (JSONL)
        liq_path = self.output_dir / f"liquidations_{timestamp}.jsonl"
        with open(liq_path, "w") as f:
            for liq in self.liquidations:
                f.write(json.dumps(asdict(liq)) + "\n")
        print(f"Wrote {len(self.liquidations)} liquidations to {liq_path}", file=sys.stderr)

        # 2. Primitives (JSONL)
        prim_path = self.output_dir / f"primitives_{timestamp}.jsonl"
        with open(prim_path, "w") as f:
            for prim in self.primitives:
                f.write(json.dumps(asdict(prim)) + "\n")
        print(f"Wrote {len(self.primitives)} primitives to {prim_path}", file=sys.stderr)

        # 3. Proposals (JSONL)
        prop_path = self.output_dir / f"proposals_{timestamp}.jsonl"
        with open(prop_path, "w") as f:
            for prop in self.proposals:
                f.write(json.dumps(asdict(prop)) + "\n")
        print(f"Wrote {len(self.proposals)} proposals to {prop_path}", file=sys.stderr)

        # 4. Distribution report (JSON)
        distributions = self.compute_distributions()
        dist_path = self.output_dir / f"distributions_{timestamp}.json"
        with open(dist_path, "w") as f:
            json.dump(distributions, f, indent=2)
        print(f"Wrote distributions to {dist_path}", file=sys.stderr)

        # 5. Coverage report
        coverage = {
            "total_liquidations": self.total_liquidations,
            "total_cascades": self.total_cascades,
            "total_proposals": self.total_proposals,
            "symbols_observed": len(set(l.symbol for l in self.liquidations)),
            "cascade_sizes": {},
        }

        # Cascade size distribution
        cascade_sizes = defaultdict(int)
        for cascade_id, events in self.active_cascades.items():
            size = len(events)
            cascade_sizes[size] += 1
        coverage["cascade_sizes"] = dict(cascade_sizes)

        cov_path = self.output_dir / f"coverage_{timestamp}.json"
        with open(cov_path, "w") as f:
            json.dump(coverage, f, indent=2)
        print(f"Wrote coverage to {cov_path}", file=sys.stderr)

        return {
            "liquidations": str(liq_path),
            "primitives": str(prim_path),
            "proposals": str(prop_path),
            "distributions": str(dist_path),
            "coverage": str(cov_path),
        }


def read_historical_liquidations(calibrator: ObservationalCalibrator, hours: int = 24):
    """Read historical liquidation data from node_fills."""
    from datetime import datetime, timedelta

    data_path = Path.home() / "hl" / "data" / "node_fills" / "hourly"

    # Get dates to process
    now = datetime.utcnow()
    dates_to_check = []
    for i in range(2):  # Today and yesterday
        date = now - timedelta(days=i)
        dates_to_check.append(date.strftime("%Y%m%d"))

    total_processed = 0
    liq_count = 0

    for date_str in dates_to_check:
        date_dir = data_path / date_str
        if not date_dir.exists():
            continue

        for hour_file in sorted(date_dir.iterdir()):
            if not hour_file.is_file():
                continue

            print(f"Processing {date_str}/{hour_file.name}...", file=sys.stderr)

            with open(hour_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        wallet = data[0]
                        fill = data[1]

                        # Only process liquidations
                        if "liquidation" not in fill:
                            continue

                        liq_data = fill["liquidation"]

                        calibrator.record_liquidation(
                            timestamp_ms=fill["time"],
                            symbol=fill["coin"],
                            side="LONG" if fill["side"] == "B" else "SHORT",
                            quantity=float(fill["sz"]),
                            price=float(fill["px"]),
                            mark_price=float(liq_data.get("markPx")) if liq_data.get("markPx") else None,
                            method=liq_data.get("method", "unknown"),
                            liquidated_wallet=liq_data.get("liquidatedUser", wallet),
                            liquidator_wallet=liq_data.get("liquidator"),
                        )
                        liq_count += 1

                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        continue

                    total_processed += 1
                    if total_processed % 10000 == 0:
                        print(f"  Processed {total_processed} lines, {liq_count} liquidations...", file=sys.stderr)

    print(f"Total: {total_processed} fills processed, {liq_count} liquidations found", file=sys.stderr)
    return liq_count


def main():
    """Run observational calibration."""
    # Create output directory
    output_dir = Path(__file__).parent.parent / "calibration_data"
    calibrator = ObservationalCalibrator(output_dir)

    print("\n=== STEP 1: Reading Historical HL Data ===", file=sys.stderr)
    liq_count = read_historical_liquidations(calibrator)

    if liq_count == 0:
        print("ERROR: No liquidation data found. Cannot proceed.", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== STEP 2: Computing Distributions ===", file=sys.stderr)
    distributions = calibrator.compute_distributions()

    # Print summary
    print("\n=== DISTRIBUTION SUMMARY ===", file=sys.stderr)
    for name, stats in sorted(distributions.items()):
        if stats.get("count", 0) > 0:
            print(f"\n{name}:", file=sys.stderr)
            print(f"  Count: {stats['count']}", file=sys.stderr)
            print(f"  Range: [{stats['min']:.4f}, {stats['max']:.4f}]", file=sys.stderr)
            print(f"  Mean: {stats['mean']:.4f}, Median: {stats['median']:.4f}", file=sys.stderr)
            if stats.get('p5') is not None:
                print(f"  P5/P25/P50/P75/P95: {stats['p5']:.4f}/{stats['p25']:.4f}/{stats['p50']:.4f}/{stats['p75']:.4f}/{stats['p95']:.4f}", file=sys.stderr)

    print("\n=== STEP 3: Writing Output Files ===", file=sys.stderr)
    outputs = calibrator.write_outputs()

    print("\n=== CALIBRATION COMPLETE ===", file=sys.stderr)
    print(f"Total liquidations: {calibrator.total_liquidations}", file=sys.stderr)
    print(f"Total cascades: {calibrator.total_cascades}", file=sys.stderr)
    print(f"Output files:", file=sys.stderr)
    for name, path in outputs.items():
        print(f"  {name}: {path}", file=sys.stderr)

    # Print what this data does NOT tell us
    print("\n" + "=" * 60, file=sys.stderr)
    print("WHAT THIS DATA DOES NOT TELL US YET", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("- Profitability of any strategy", file=sys.stderr)
    print("- Whether there is tradeable edge", file=sys.stderr)
    print("- Optimal entry/exit timing", file=sys.stderr)
    print("- Risk-adjusted returns", file=sys.stderr)
    print("- Correct threshold values", file=sys.stderr)
    print("- Correlation with price direction", file=sys.stderr)
    print("=" * 60, file=sys.stderr)


if __name__ == "__main__":
    main()
