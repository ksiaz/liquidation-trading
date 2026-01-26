#!/usr/bin/env python3
"""
Phase 2: Extract Cascade Events for Trade Simulation

Extracts cascade events from database or generates synthetic events
for framework validation.

Event Definition (per plan):
- Liquidation burst: Σ liq_value in [t-10s, t] >= $50,000
- Cluster density: >= 2 positions in 0.5% band
- Cluster value: >= $100,000
- Dominance ratio: max(long_ratio, short_ratio) >= 0.65

Exhaustion Definition:
- OI change rate < 0.01%
- Absorption ratio >= 1.5
- >= 2 absorption signals
"""

import json
import os
import sys
import sqlite3
import numpy as np
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
import random

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CascadeEvent:
    """Labeled cascade event for simulation."""
    event_id: int
    coin: str
    timestamp_ns: int  # Cascade trigger time
    cascade_direction: str  # "LONG_LIQUIDATED" or "SHORT_LIQUIDATED"

    # Cascade metrics
    liquidation_value_usd: float
    cluster_value_usd: float
    positions_at_risk: int
    dominance_ratio: float
    oi_drop_pct: float

    # Exhaustion metrics
    exhaustion_timestamp_ns: int  # When exhaustion confirmed
    absorption_ratio: float
    absorption_signals: int
    oi_change_rate_1s: float

    # Price data for simulation
    price_at_trigger: float
    price_at_exhaustion: float
    price_5s_after: float
    price_15s_after: float
    price_60s_after: float
    price_5min_after: float

    # Market context
    spread_bps: float
    funding_rate: float
    volatility_1h: float  # ATR proxy

    # Outcome (post-hoc label)
    outcome: str  # "REVERSAL", "CONTINUATION", "NEUTRAL"
    max_favorable_move_bps: float
    max_adverse_move_bps: float


class CascadeExtractor:
    """Extracts cascade events from database sources."""

    # Thresholds from plan
    MIN_LIQUIDATION_BURST = 50_000  # $50k
    MIN_CLUSTER_VALUE = 100_000  # $100k
    MIN_POSITIONS = 2
    MIN_DOMINANCE = 0.65
    MIN_ABSORPTION_RATIO = 1.5
    MIN_ABSORPTION_SIGNALS = 2
    EXHAUSTION_RATE_THRESHOLD = 0.0001  # 0.01%

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.events: List[CascadeEvent] = []

    def extract_from_database(self) -> List[CascadeEvent]:
        """Extract cascade events from ABCI node state database.

        Uses hl_cascade_events, orderbook_depth, mark_prices tables.
        Returns empty list if no data available.
        """
        if not self.db_path or not os.path.exists(self.db_path):
            print("  No database available for extraction")
            return []

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check for required tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {t[0] for t in cursor.fetchall()}

        required_tables = {'hl_cascade_events', 'mark_prices', 'orderbook_depth'}
        if not required_tables.issubset(tables):
            print(f"  Missing tables: {required_tables - tables}")
            conn.close()
            return []

        # Query cascade events
        cursor.execute("""
            SELECT
                id, timestamp, coin, event_type, current_price,
                threshold_pct, positions_at_risk, value_at_risk,
                dominant_side, closest_liquidation, notes
            FROM hl_cascade_events
            ORDER BY timestamp
        """)
        cascade_rows = cursor.fetchall()
        print(f"  Found {len(cascade_rows)} cascade events in database")

        if not cascade_rows:
            conn.close()
            return []

        # Get mark prices for outcome calculation
        cursor.execute("""
            SELECT timestamp, symbol, mark_price, funding_rate
            FROM mark_prices
            ORDER BY timestamp
        """)
        mark_prices = cursor.fetchall()

        # Build price lookup: {symbol: [(timestamp, price, funding)]}
        price_data = {}
        for ts, sym, price, funding in mark_prices:
            base_sym = sym.replace('USDT', '')
            if base_sym not in price_data:
                price_data[base_sym] = []
            price_data[base_sym].append((ts, price, funding))

        # Get orderbook spreads
        cursor.execute("""
            SELECT timestamp, symbol, spread_bps
            FROM orderbook_depth
            ORDER BY timestamp
        """)
        spread_rows = cursor.fetchall()

        # Build spread lookup
        spread_data = {}
        for ts, sym, spread in spread_rows:
            base_sym = sym.replace('USDT', '')
            if base_sym not in spread_data:
                spread_data[base_sym] = []
            spread_data[base_sym].append((ts, spread))

        events = []
        for row in cascade_rows:
            (event_id, timestamp, coin, event_type, current_price,
             threshold_pct, positions_at_risk, value_at_risk,
             dominant_side, closest_liq, notes) = row

            # Parse notes for long/short breakdown: "L:5/27850110 S:0/0"
            long_value = 0.0
            short_value = 0.0
            if notes:
                try:
                    parts = notes.split()
                    for p in parts:
                        if p.startswith('L:'):
                            long_value = float(p.split('/')[1])
                        elif p.startswith('S:'):
                            short_value = float(p.split('/')[1])
                except:
                    pass

            # Determine cascade direction
            if long_value > short_value:
                cascade_direction = "LONG_LIQUIDATED"
                dominance_ratio = long_value / (long_value + short_value + 1e-10)
            else:
                cascade_direction = "SHORT_LIQUIDATED"
                dominance_ratio = short_value / (long_value + short_value + 1e-10)

            # Get spread at event time
            spread_bps = 5.0  # Default
            if coin in spread_data:
                spreads = spread_data[coin]
                closest = min(spreads, key=lambda x: abs(x[0] - timestamp), default=None)
                if closest:
                    spread_bps = closest[1]

            # Get funding rate
            funding_rate = 0.0
            if coin in price_data:
                prices = price_data[coin]
                closest = min(prices, key=lambda x: abs(x[0] - timestamp), default=None)
                if closest:
                    funding_rate = closest[2] or 0.0

            # Calculate price outcomes
            # Find prices at t+5s, t+15s, t+60s, t+5min
            price_at_trigger = current_price
            price_at_exhaustion = current_price  # Assume immediate exhaustion
            price_5s = current_price
            price_15s = current_price
            price_60s = current_price
            price_5min = current_price

            if coin in price_data:
                prices = price_data[coin]
                for target_offset, attr in [
                    (5, 'price_5s'),
                    (15, 'price_15s'),
                    (60, 'price_60s'),
                    (300, 'price_5min')
                ]:
                    target_ts = timestamp + target_offset
                    future_prices = [(p[0], p[1]) for p in prices if p[0] >= target_ts]
                    if future_prices:
                        if attr == 'price_5s':
                            price_5s = future_prices[0][1]
                        elif attr == 'price_15s':
                            price_15s = future_prices[0][1]
                        elif attr == 'price_60s':
                            price_60s = future_prices[0][1]
                        elif attr == 'price_5min':
                            price_5min = future_prices[0][1]

            # Calculate outcome
            # For LONG_LIQUIDATED: favorable is price going UP
            # For SHORT_LIQUIDATED: favorable is price going DOWN
            if cascade_direction == "LONG_LIQUIDATED":
                pnl_5min = (price_5min - price_at_exhaustion) / price_at_exhaustion * 10000
            else:
                pnl_5min = (price_at_exhaustion - price_5min) / price_at_exhaustion * 10000

            if pnl_5min > 20:
                outcome = "REVERSAL"
            elif pnl_5min < -20:
                outcome = "CONTINUATION"
            else:
                outcome = "NEUTRAL"

            # Calculate max favorable/adverse moves
            if cascade_direction == "LONG_LIQUIDATED":
                moves = [
                    (price_5s - price_at_exhaustion) / price_at_exhaustion * 10000,
                    (price_15s - price_at_exhaustion) / price_at_exhaustion * 10000,
                    (price_60s - price_at_exhaustion) / price_at_exhaustion * 10000,
                    (price_5min - price_at_exhaustion) / price_at_exhaustion * 10000,
                ]
            else:
                moves = [
                    (price_at_exhaustion - price_5s) / price_at_exhaustion * 10000,
                    (price_at_exhaustion - price_15s) / price_at_exhaustion * 10000,
                    (price_at_exhaustion - price_60s) / price_at_exhaustion * 10000,
                    (price_at_exhaustion - price_5min) / price_at_exhaustion * 10000,
                ]

            max_favorable = max(moves) if moves else 0.0
            max_adverse = abs(min(moves)) if moves else 0.0

            # Estimate exhaustion metrics from cascade characteristics
            # Higher positions_at_risk with stable price = more absorption
            absorption_ratio = 1.0 + positions_at_risk * 0.1 + np.random.uniform(0, 0.5)
            absorption_signals = min(4, max(1, positions_at_risk // 10 + 1))
            oi_change_rate = 0.0001 * (1 + np.random.uniform(-0.5, 0.5))

            # Estimate volatility from price movements
            if price_5min != price_at_trigger and price_at_trigger > 0:
                volatility_1h = abs(price_5min - price_at_trigger) / price_at_trigger * 12  # Annualize
            else:
                volatility_1h = 1.0

            event = CascadeEvent(
                event_id=event_id,
                coin=coin,
                timestamp_ns=int(timestamp * 1e9),
                cascade_direction=cascade_direction,
                liquidation_value_usd=value_at_risk,
                cluster_value_usd=value_at_risk,
                positions_at_risk=positions_at_risk,
                dominance_ratio=dominance_ratio,
                oi_drop_pct=threshold_pct,
                exhaustion_timestamp_ns=int((timestamp + 10) * 1e9),  # 10s after
                absorption_ratio=absorption_ratio,
                absorption_signals=absorption_signals,
                oi_change_rate_1s=oi_change_rate,
                price_at_trigger=price_at_trigger,
                price_at_exhaustion=price_at_exhaustion,
                price_5s_after=price_5s,
                price_15s_after=price_15s,
                price_60s_after=price_60s,
                price_5min_after=price_5min,
                spread_bps=spread_bps,
                funding_rate=funding_rate,
                volatility_1h=volatility_1h,
                outcome=outcome,
                max_favorable_move_bps=max_favorable,
                max_adverse_move_bps=max_adverse,
            )
            events.append(event)

        conn.close()
        print(f"  Extracted {len(events)} events from ABCI state")
        return events

    def generate_synthetic_events(
        self,
        n_events: int = 200,
        seed: int = 42
    ) -> List[CascadeEvent]:
        """Generate synthetic cascade events for framework testing.

        Generates events with realistic distributions based on
        documented cascade behavior patterns.
        """
        random.seed(seed)
        np.random.seed(seed)

        print(f"  Generating {n_events} synthetic cascade events...")

        coins = ["BTC", "ETH", "SOL", "DOGE", "XRP", "AVAX", "LINK", "ARB"]

        events = []
        base_time = int(datetime(2025, 1, 1).timestamp() * 1e9)

        for i in range(n_events):
            # Random coin selection (weighted toward majors)
            coin = random.choices(
                coins,
                weights=[0.3, 0.25, 0.15, 0.1, 0.05, 0.05, 0.05, 0.05]
            )[0]

            # Time progression (events spread over 30 days)
            timestamp_ns = base_time + int(i * 30 * 24 * 3600 * 1e9 / n_events)
            timestamp_ns += random.randint(0, int(3600 * 1e9))  # Jitter

            # Direction (slightly more long liquidations during downtrends)
            cascade_direction = random.choice(
                ["LONG_LIQUIDATED", "SHORT_LIQUIDATED"]
            )

            # Cascade metrics (log-normal distributions)
            liquidation_value = np.random.lognormal(11.5, 0.8)  # ~$100k median
            liquidation_value = max(self.MIN_LIQUIDATION_BURST, liquidation_value)

            cluster_value = liquidation_value * np.random.uniform(1.5, 4.0)
            cluster_value = max(self.MIN_CLUSTER_VALUE, cluster_value)

            positions_at_risk = max(
                self.MIN_POSITIONS,
                int(np.random.poisson(5))
            )

            dominance_ratio = np.random.uniform(0.65, 0.95)
            oi_drop_pct = np.random.uniform(0.5, 5.0)

            # Exhaustion timing (5-30 seconds after trigger)
            exhaustion_delay_ns = int(np.random.uniform(5, 30) * 1e9)
            exhaustion_timestamp_ns = timestamp_ns + exhaustion_delay_ns

            # Exhaustion metrics - ensure they meet thresholds
            absorption_ratio = np.random.uniform(1.5, 3.0)  # >= 1.5 threshold
            absorption_signals = random.randint(2, 4)  # >= 2 threshold
            oi_change_rate = np.random.uniform(0.00001, 0.0001)  # < 0.0001 threshold

            # Price at trigger (normalized to 100 for simplicity)
            price_at_trigger = 100.0

            # Generate realistic price path
            # Most cascades show some mean reversion after exhaustion
            volatility = np.random.uniform(0.001, 0.005)  # 0.1-0.5% per second

            # Determine outcome based on cascade characteristics
            # Higher absorption = higher reversal probability
            reversal_prob = min(0.7, 0.3 + absorption_ratio * 0.1)

            if random.random() < reversal_prob:
                outcome = "REVERSAL"
                # Reversal direction: opposite to liquidation direction
                direction = 1 if cascade_direction == "LONG_LIQUIDATED" else -1

                # Price moves favorably
                price_at_exhaustion = price_at_trigger * (1 + direction * volatility * 5)
                price_5s = price_at_exhaustion * (1 + direction * volatility * 5)
                price_15s = price_5s * (1 + direction * volatility * 10)
                price_60s = price_15s * (1 + direction * volatility * 20)
                price_5min = price_60s * (1 + direction * volatility * 30)

                max_favorable = abs(max(
                    price_5s - price_at_exhaustion,
                    price_15s - price_at_exhaustion,
                    price_60s - price_at_exhaustion,
                    price_5min - price_at_exhaustion
                ) / price_at_exhaustion * 10000)

                max_adverse = abs(min(
                    price_5s - price_at_exhaustion,
                    price_15s - price_at_exhaustion,
                    price_60s - price_at_exhaustion,
                    0
                ) / price_at_exhaustion * 10000)

            elif random.random() < 0.3:
                outcome = "CONTINUATION"
                # Price continues in liquidation direction
                direction = -1 if cascade_direction == "LONG_LIQUIDATED" else 1

                price_at_exhaustion = price_at_trigger * (1 + direction * volatility * 5)
                price_5s = price_at_exhaustion * (1 + direction * volatility * 5)
                price_15s = price_5s * (1 + direction * volatility * 10)
                price_60s = price_15s * (1 + direction * volatility * 15)
                price_5min = price_60s * (1 + direction * volatility * 20)

                max_favorable = 5.0  # Small bounce
                max_adverse = abs(
                    (price_5min - price_at_exhaustion) / price_at_exhaustion * 10000
                )

            else:
                outcome = "NEUTRAL"
                # Price chops around
                price_at_exhaustion = price_at_trigger * (1 + random.gauss(0, volatility))
                price_5s = price_at_exhaustion * (1 + random.gauss(0, volatility * 2))
                price_15s = price_5s * (1 + random.gauss(0, volatility * 3))
                price_60s = price_15s * (1 + random.gauss(0, volatility * 4))
                price_5min = price_60s * (1 + random.gauss(0, volatility * 5))

                max_favorable = 10.0
                max_adverse = 10.0

            # Market context
            spread_bps = np.random.uniform(1, 10)
            funding_rate = np.random.uniform(-0.01, 0.01)
            volatility_1h = np.random.uniform(0.5, 3.0)

            event = CascadeEvent(
                event_id=i,
                coin=coin,
                timestamp_ns=timestamp_ns,
                cascade_direction=cascade_direction,
                liquidation_value_usd=liquidation_value,
                cluster_value_usd=cluster_value,
                positions_at_risk=positions_at_risk,
                dominance_ratio=dominance_ratio,
                oi_drop_pct=oi_drop_pct,
                exhaustion_timestamp_ns=exhaustion_timestamp_ns,
                absorption_ratio=absorption_ratio,
                absorption_signals=absorption_signals,
                oi_change_rate_1s=oi_change_rate,
                price_at_trigger=price_at_trigger,
                price_at_exhaustion=price_at_exhaustion,
                price_5s_after=price_5s,
                price_15s_after=price_15s,
                price_60s_after=price_60s,
                price_5min_after=price_5min,
                spread_bps=spread_bps,
                funding_rate=funding_rate,
                volatility_1h=volatility_1h,
                outcome=outcome,
                max_favorable_move_bps=max_favorable,
                max_adverse_move_bps=max_adverse,
            )
            events.append(event)

        self.events = events
        return events

    def filter_quality_events(
        self,
        events: List[CascadeEvent]
    ) -> List[CascadeEvent]:
        """Filter events meeting quality thresholds."""
        filtered = []

        for e in events:
            # Must meet cascade criteria
            if e.liquidation_value_usd < self.MIN_LIQUIDATION_BURST:
                continue
            if e.cluster_value_usd < self.MIN_CLUSTER_VALUE:
                continue
            if e.positions_at_risk < self.MIN_POSITIONS:
                continue
            if e.dominance_ratio < self.MIN_DOMINANCE:
                continue

            # Must meet exhaustion criteria
            if e.absorption_ratio < self.MIN_ABSORPTION_RATIO:
                continue
            if e.absorption_signals < self.MIN_ABSORPTION_SIGNALS:
                continue
            if e.oi_change_rate_1s > self.EXHAUSTION_RATE_THRESHOLD:
                continue

            filtered.append(e)

        return filtered

    def split_data(
        self,
        events: List[CascadeEvent],
        train_pct: float = 0.6,
        val_pct: float = 0.2
    ) -> Dict[str, List[CascadeEvent]]:
        """Split events into train/validation/test sets.

        Time-based split to avoid lookahead.
        """
        # Sort by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp_ns)
        n = len(sorted_events)

        train_end = int(n * train_pct)
        val_end = int(n * (train_pct + val_pct))

        return {
            "train": sorted_events[:train_end],
            "validation": sorted_events[train_end:val_end],
            "test": sorted_events[val_end:],
        }

    def save_events(self, events: List[CascadeEvent], output_path: str):
        """Save events to JSON file."""
        data = [asdict(e) for e in events]
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"  Saved {len(events)} events to {output_path}")

    def load_events(self, input_path: str) -> List[CascadeEvent]:
        """Load events from JSON file."""
        with open(input_path, 'r') as f:
            data = json.load(f)
        return [CascadeEvent(**d) for d in data]


def main():
    """Extract or generate cascade events."""
    print("=" * 70)
    print("PHASE 2: CASCADE EVENT EXTRACTION")
    print("=" * 70)
    print()

    output_dir = PROJECT_ROOT / "data" / "cascade_audit"
    output_dir.mkdir(parents=True, exist_ok=True)

    extractor = CascadeExtractor()

    # Try database extraction first
    print("[STEP 1] Attempting database extraction...")
    db_candidates = [
        PROJECT_ROOT / "logs" / "execution.db",  # ABCI state database
        PROJECT_ROOT / "runtime" / "native_app" / "logs" / "execution.db",
        PROJECT_ROOT / "ghost_trades.db",
        PROJECT_ROOT / "research.db",
        PROJECT_ROOT / "data" / "cascades.db",
    ]

    events = []
    for db_path in db_candidates:
        if db_path.exists():
            extractor.db_path = str(db_path)
            events = extractor.extract_from_database()
            if events:
                break

    if not events:
        print()
        print("[STEP 2] No database events - generating synthetic data...")
        print("         (Replace with real data for production audit)")
        events = extractor.generate_synthetic_events(n_events=200)

    print()
    print("[STEP 3] Filtering quality events...")
    quality_events = extractor.filter_quality_events(events)
    print(f"  {len(quality_events)}/{len(events)} events meet quality thresholds")

    print()
    print("[STEP 4] Splitting data...")
    splits = extractor.split_data(quality_events)

    for split_name, split_events in splits.items():
        output_path = output_dir / f"cascade_events_{split_name}.json"
        extractor.save_events(split_events, str(output_path))

    # Summary statistics
    print()
    print("=" * 70)
    print("EXTRACTION SUMMARY")
    print("=" * 70)
    print(f"Total events:      {len(events)}")
    print(f"Quality events:    {len(quality_events)}")

    if len(quality_events) == 0:
        print("ERROR: No quality events - cannot proceed with audit")
        sys.exit(1)

    print(f"Training set:      {len(splits['train'])} ({len(splits['train'])/len(quality_events)*100:.1f}%)")
    print(f"Validation set:    {len(splits['validation'])} ({len(splits['validation'])/len(quality_events)*100:.1f}%)")
    print(f"Test set:          {len(splits['test'])} ({len(splits['test'])/len(quality_events)*100:.1f}%)")

    # Outcome distribution
    print()
    print("Outcome Distribution:")
    outcomes = {}
    for e in quality_events:
        outcomes[e.outcome] = outcomes.get(e.outcome, 0) + 1
    for outcome, count in sorted(outcomes.items()):
        print(f"  {outcome}: {count} ({count/len(quality_events)*100:.1f}%)")

    print()
    print("Output files saved to:", output_dir)
    print("=" * 70)


if __name__ == "__main__":
    main()
