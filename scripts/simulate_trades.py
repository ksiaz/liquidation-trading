#!/usr/bin/env python3
"""
Phase 3: Trade Simulation with Forward-Only Logic

Simulates trades based on cascade events with:
- Realistic latency penalties
- Size-dependent slippage
- Multiple exit strategies
- Cost modeling

NO lookahead - all decisions use only information available at entry time.
"""

import json
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.extract_cascade_trades import CascadeEvent


@dataclass
class SimulatedTrade:
    """Result of simulated trade."""
    event_id: int
    coin: str
    direction: str  # "LONG" or "SHORT"

    # Entry details
    entry_timestamp_ns: int
    entry_price: float
    entry_slippage_bps: float

    # Exit details
    exit_timestamp_ns: int
    exit_price: float
    exit_slippage_bps: float
    exit_type: str  # "fixed_5s", "fixed_15s", etc.

    # PnL
    gross_pnl_bps: float
    fees_bps: float
    net_pnl_bps: float

    # Context
    latency_penalty_ms: float
    spread_bps: float
    volatility_1h: float
    cascade_direction: str
    absorption_ratio: float


class TradeSimulator:
    """Simulates trades from cascade events."""

    # Cost parameters from plan
    TAKER_FEE_BPS = 2.5  # Per side
    BASE_SLIPPAGE_BPS = 2.0
    LATENCY_PENALTY_MS = 100  # 100ms realistic delay
    SLIPPAGE_SIZE_COEFFICIENT = 10.0  # bps per $100k

    # Exit strategies
    EXIT_STRATEGIES = ["fixed_5s", "fixed_15s", "fixed_60s", "tp_sl"]

    def __init__(
        self,
        latency_ms: float = 100.0,
        slippage_mult: float = 1.0,
        exit_strategy: str = "fixed_15s"
    ):
        self.latency_ms = latency_ms
        self.slippage_mult = slippage_mult
        self.exit_strategy = exit_strategy

    def simulate_trade(
        self,
        event: CascadeEvent,
        size_usd: float = 10000.0
    ) -> SimulatedTrade:
        """Simulate a single trade from cascade event.

        Entry: At exhaustion confirmation + latency
        Direction: Opposite to liquidation direction
        Exit: Based on configured strategy
        """
        # Direction: opposite to liquidation
        if event.cascade_direction == "LONG_LIQUIDATED":
            direction = "LONG"  # Buy the dip
            price_direction = 1
        else:
            direction = "SHORT"  # Sell the rip
            price_direction = -1

        # Entry timing
        entry_timestamp_ns = event.exhaustion_timestamp_ns + int(self.latency_ms * 1e6)
        entry_price = event.price_at_exhaustion

        # Entry slippage (adverse movement during latency + crossing spread)
        latency_slippage = self.latency_ms / 1000.0 * event.volatility_1h * 100  # bps
        spread_slippage = event.spread_bps / 2  # Half spread to cross
        size_slippage = (size_usd / 100000) * self.SLIPPAGE_SIZE_COEFFICIENT

        entry_slippage_bps = (
            (self.BASE_SLIPPAGE_BPS + latency_slippage + spread_slippage + size_slippage)
            * self.slippage_mult
        )

        # Adjust entry price for slippage (always adverse)
        # LONG: pay more (entry + slippage), SHORT: receive less (entry - slippage)
        entry_price_adjusted = entry_price * (1 + price_direction * entry_slippage_bps / 10000)

        # Exit based on strategy
        if self.exit_strategy == "fixed_5s":
            exit_price = event.price_5s_after
            exit_delay_ns = int(5 * 1e9)
        elif self.exit_strategy == "fixed_15s":
            exit_price = event.price_15s_after
            exit_delay_ns = int(15 * 1e9)
        elif self.exit_strategy == "fixed_60s":
            exit_price = event.price_60s_after
            exit_delay_ns = int(60 * 1e9)
        elif self.exit_strategy == "tp_sl":
            # TP: +30 bps, SL: -50 bps
            tp_price = entry_price_adjusted * (1 + price_direction * 30 / 10000)
            sl_price = entry_price_adjusted * (1 - price_direction * 50 / 10000)

            # Check which gets hit first (simplified: use 60s exit as proxy)
            final_price = event.price_60s_after
            favorable_move = (final_price - entry_price_adjusted) * price_direction / entry_price_adjusted * 10000

            if favorable_move >= 30:
                exit_price = tp_price
            elif favorable_move <= -50:
                exit_price = sl_price
            else:
                exit_price = final_price
            exit_delay_ns = int(60 * 1e9)
        else:
            raise ValueError(f"Unknown exit strategy: {self.exit_strategy}")

        exit_timestamp_ns = entry_timestamp_ns + exit_delay_ns

        # Exit slippage (crossing spread)
        exit_slippage_bps = (
            (self.BASE_SLIPPAGE_BPS + event.spread_bps / 2)
            * self.slippage_mult
        )

        # Adjust exit price for slippage (always adverse)
        # LONG: receive less (exit - slippage), SHORT: pay more (exit + slippage)
        exit_price_adjusted = exit_price * (1 - price_direction * exit_slippage_bps / 10000)

        # Calculate PnL
        if direction == "LONG":
            gross_pnl_bps = (exit_price_adjusted - entry_price_adjusted) / entry_price_adjusted * 10000
        else:
            gross_pnl_bps = (entry_price_adjusted - exit_price_adjusted) / entry_price_adjusted * 10000

        # Fees: taker fee both sides
        fees_bps = self.TAKER_FEE_BPS * 2

        net_pnl_bps = gross_pnl_bps - fees_bps

        return SimulatedTrade(
            event_id=event.event_id,
            coin=event.coin,
            direction=direction,
            entry_timestamp_ns=entry_timestamp_ns,
            entry_price=entry_price_adjusted,
            entry_slippage_bps=entry_slippage_bps,
            exit_timestamp_ns=exit_timestamp_ns,
            exit_price=exit_price_adjusted,
            exit_slippage_bps=exit_slippage_bps,
            exit_type=self.exit_strategy,
            gross_pnl_bps=gross_pnl_bps,
            fees_bps=fees_bps,
            net_pnl_bps=net_pnl_bps,
            latency_penalty_ms=self.latency_ms,
            spread_bps=event.spread_bps,
            volatility_1h=event.volatility_1h,
            cascade_direction=event.cascade_direction,
            absorption_ratio=event.absorption_ratio,
        )

    def simulate_all(
        self,
        events: List[CascadeEvent],
        size_usd: float = 10000.0
    ) -> List[SimulatedTrade]:
        """Simulate trades for all events."""
        return [self.simulate_trade(e, size_usd) for e in events]


def load_events(path: Path) -> List[CascadeEvent]:
    """Load cascade events from JSON."""
    with open(path, 'r') as f:
        data = json.load(f)
    return [CascadeEvent(**d) for d in data]


def save_trades(trades: List[SimulatedTrade], path: Path):
    """Save simulated trades to JSON."""
    data = [asdict(t) for t in trades]
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def compute_summary(trades: List[SimulatedTrade]) -> Dict:
    """Compute summary statistics for trades."""
    if not trades:
        return {"error": "No trades"}

    pnls = [t.net_pnl_bps for t in trades]
    gross_pnls = [t.gross_pnl_bps for t in trades]

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    return {
        "trade_count": len(trades),
        "mean_net_pnl_bps": np.mean(pnls),
        "std_net_pnl_bps": np.std(pnls),
        "mean_gross_pnl_bps": np.mean(gross_pnls),
        "win_rate": len(wins) / len(pnls) if pnls else 0,
        "profit_factor": abs(sum(wins) / sum(losses)) if losses else float('inf'),
        "max_pnl_bps": max(pnls),
        "min_pnl_bps": min(pnls),
        "total_fees_bps": sum(t.fees_bps for t in trades),
        "total_slippage_bps": sum(t.entry_slippage_bps + t.exit_slippage_bps for t in trades),
    }


def main():
    parser = argparse.ArgumentParser(description="Simulate cascade trades")
    parser.add_argument("--split", choices=["train", "validation", "test", "all"],
                       default="train", help="Data split to simulate")
    parser.add_argument("--exit", choices=TradeSimulator.EXIT_STRATEGIES,
                       default="fixed_15s", help="Exit strategy")
    parser.add_argument("--latency", type=float, default=100.0,
                       help="Latency penalty in ms")
    parser.add_argument("--slippage-mult", type=float, default=1.0,
                       help="Slippage multiplier")
    parser.add_argument("--size", type=float, default=10000.0,
                       help="Trade size in USD")
    args = parser.parse_args()

    print("=" * 70)
    print("PHASE 3: TRADE SIMULATION")
    print("=" * 70)
    print()
    print(f"Exit strategy:  {args.exit}")
    print(f"Latency:        {args.latency}ms")
    print(f"Slippage mult:  {args.slippage_mult}x")
    print(f"Trade size:     ${args.size:,.0f}")
    print()

    data_dir = PROJECT_ROOT / "data" / "cascade_audit"
    output_dir = data_dir

    # Load events
    if args.split == "all":
        splits = ["train", "validation", "test"]
    else:
        splits = [args.split]

    all_trades = []

    for split in splits:
        event_path = data_dir / f"cascade_events_{split}.json"
        if not event_path.exists():
            print(f"Warning: {event_path} not found, skipping")
            continue

        print(f"[{split.upper()}] Loading events...")
        events = load_events(event_path)
        print(f"  Loaded {len(events)} events")

        # Simulate
        simulator = TradeSimulator(
            latency_ms=args.latency,
            slippage_mult=args.slippage_mult,
            exit_strategy=args.exit
        )

        print(f"  Simulating trades...")
        trades = simulator.simulate_all(events, size_usd=args.size)

        # Summary
        summary = compute_summary(trades)
        print(f"  Results:")
        print(f"    Trade count:    {summary['trade_count']}")
        print(f"    Mean net PnL:   {summary['mean_net_pnl_bps']:.2f} bps")
        print(f"    Std PnL:        {summary['std_net_pnl_bps']:.2f} bps")
        print(f"    Win rate:       {summary['win_rate']*100:.1f}%")
        print(f"    Profit factor:  {summary['profit_factor']:.2f}")
        print()

        # Save trades
        trade_path = output_dir / f"simulated_trades_{split}_{args.exit}.json"
        save_trades(trades, trade_path)
        print(f"  Saved to {trade_path}")
        print()

        all_trades.extend(trades)

    # Overall summary if multiple splits
    if len(splits) > 1:
        print("=" * 70)
        print("OVERALL SUMMARY")
        print("=" * 70)
        summary = compute_summary(all_trades)
        print(f"Total trades:     {summary['trade_count']}")
        print(f"Mean net PnL:     {summary['mean_net_pnl_bps']:.2f} bps")
        print(f"Std PnL:          {summary['std_net_pnl_bps']:.2f} bps")
        print(f"Win rate:         {summary['win_rate']*100:.1f}%")
        print(f"Profit factor:    {summary['profit_factor']:.2f}")
        print(f"Gross PnL:        {summary['mean_gross_pnl_bps']:.2f} bps")
        print(f"Total costs:      {(summary['total_fees_bps'] + summary['total_slippage_bps'])/summary['trade_count']:.2f} bps/trade avg")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
