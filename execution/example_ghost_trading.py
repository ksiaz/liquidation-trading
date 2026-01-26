"""
Example Ghost Trading Script

Demonstrates ghost position tracking with:
- $1000 initial balance
- 5% position sizing
- Trade execution simulation
- PNL tracking and statistics

Usage:
    python execution/example_ghost_trading.py
"""

import os
import time
from execution.ep4_ghost_tracker import GhostPositionTracker


def main():
    """Run example ghost trading session."""

    # Get API key from environment (optional, for better rate limits)
    api_key = os.environ.get("BINANCE_API_KEY")

    print("\n" + "="*60)
    print("GHOST TRADING EXAMPLE")
    print("="*60)
    print(f"Symbol: BTCUSDT")
    print(f"Initial Balance: $1,000")
    print(f"Position Size: 5% per trade")
    print("="*60 + "\n")

    # Initialize tracker with $1000 balance, 5% position size
    tracker = GhostPositionTracker(
        initial_balance=1000.0,
        position_size_pct=0.05,
        symbol="BTCUSDT",
        api_key=api_key
    )

    # Show initial state
    tracker.print_summary()

    # Example 1: Open LONG position
    print("\n[ACTION] Opening LONG position on BTCUSDT...")
    success, error, trade = tracker.open_position(
        symbol="BTCUSDT",
        side="LONG"
    )

    if success and trade:
        print(f"✓ Position opened: {trade.quantity:.4f} BTC @ ${trade.price:,.2f}")
    else:
        print(f"✗ Failed: {error}")
        return

    # Wait a moment for price movement (in live testing)
    print("\nWaiting 3 seconds for price movement...")
    time.sleep(3)

    # Show current state with unrealized PNL
    tracker.print_summary()

    # Check unrealized PNL
    snapshot = tracker._adapter.capture_snapshot()
    current_price = (snapshot.best_bid + snapshot.best_ask) / 2
    unrealized = tracker.calculate_unrealized_pnl("BTCUSDT", current_price)

    if unrealized is not None:
        print(f"Current BTC Price: ${current_price:,.2f}")
        print(f"Unrealized PNL: ${unrealized:+,.2f}\n")

    # Example 2: Close position
    print("[ACTION] Closing LONG position...")
    success, error, trade = tracker.close_position(symbol="BTCUSDT")

    if success and trade:
        pnl_indicator = "📈" if trade.pnl and trade.pnl > 0 else "📉"
        print(f"✓ Position closed: {trade.quantity:.4f} BTC @ ${trade.price:,.2f}")
        print(f"{pnl_indicator} PNL: ${trade.pnl:+,.2f}")
    else:
        print(f"✗ Failed: {error}")
        return

    # Show final state
    tracker.print_summary()
    tracker.print_trade_history()

    # Example 3: Multiple trades
    print("\n[EXAMPLE] Executing multiple trades...\n")

    # Trade 1: LONG
    print("[1/3] Opening LONG position...")
    tracker.open_position(symbol="BTCUSDT", side="LONG")
    time.sleep(2)
    tracker.close_position(symbol="BTCUSDT")

    time.sleep(1)

    # Trade 2: SHORT
    print("[2/3] Opening SHORT position...")
    tracker.open_position(symbol="BTCUSDT", side="SHORT")
    time.sleep(2)
    tracker.close_position(symbol="BTCUSDT")

    time.sleep(1)

    # Trade 3: LONG
    print("[3/3] Opening LONG position...")
    tracker.open_position(symbol="BTCUSDT", side="LONG")
    time.sleep(2)
    tracker.close_position(symbol="BTCUSDT")

    # Final summary
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    tracker.print_summary()
    tracker.print_trade_history()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
