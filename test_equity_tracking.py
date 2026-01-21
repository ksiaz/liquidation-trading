"""Test Equity Tracking in Execution Trace

Verifies that entry/exit prices, position size, and PnL appear in execution results.
"""

from decimal import Decimal
import time
from runtime.executor.controller import ExecutionController
from runtime.arbitration.types import Mandate, MandateType
from runtime.position.types import Direction
from runtime.risk.types import AccountState

def test_equity_tracking():
    """Test that equity fields appear in execution results."""
    print("=" * 70)
    print("EQUITY TRACKING TEST")
    print("=" * 70)
    print()

    # Initialize controller
    controller = ExecutionController()

    # Create account state
    account = AccountState(
        equity=Decimal("10000.0"),
        margin_available=Decimal("10000.0"),
        timestamp=1.0
    )

    mark_prices = {"BTCUSDT": Decimal("50000.0")}

    # Create ENTRY mandate
    print("1. Testing ENTRY action...")
    entry_mandate = Mandate(
        symbol="BTCUSDT",
        type=MandateType.ENTRY,
        authority=5.0,
        timestamp=time.time()
    )

    # Execute ENTRY
    stats = controller.process_cycle([entry_mandate], account, mark_prices)
    results = controller._execution_log

    if len(results) > 0:
        result = results[0]
        log_dict = result.to_log_dict()

        print(f"   Action: {log_dict.get('action')}")
        print(f"   Entry Price: {log_dict.get('entry_price')}")
        print(f"   Position Size: {log_dict.get('position_size')}")
        print(f"   Price: {log_dict.get('price')}")

        # Verify fields present
        assert log_dict.get('entry_price') is not None, "Missing entry_price"
        assert log_dict.get('position_size') is not None, "Missing position_size"
        print("   ✓ ENTRY fields present")
    else:
        print("   ✗ No execution results")
        return False

    print()
    print("2. Testing EXIT action...")

    # Create EXIT mandate
    exit_mandate = Mandate(
        symbol="BTCUSDT",
        type=MandateType.EXIT,
        authority=5.0,
        timestamp=time.time()
    )

    # Execute EXIT
    stats = controller.process_cycle([exit_mandate], account, mark_prices)
    results = controller._execution_log

    if len(results) > 1:
        result = results[-1]  # Get the EXIT result (last one)
        log_dict = result.to_log_dict()

        print(f"   Action: {log_dict.get('action')}")
        print(f"   Entry Price: {log_dict.get('entry_price')}")
        print(f"   Exit Price: {log_dict.get('exit_price')}")
        print(f"   Position Size: {log_dict.get('position_size')}")
        print(f"   Price Change %: {log_dict.get('price_change_pct')}")
        print(f"   Realized PnL USD: {log_dict.get('realized_pnl_usd')}")

        # Verify fields present
        assert log_dict.get('entry_price') is not None, "Missing entry_price on exit"
        assert log_dict.get('exit_price') is not None, "Missing exit_price"
        assert log_dict.get('price_change_pct') is not None, "Missing price_change_pct"
        assert log_dict.get('realized_pnl_usd') is not None, "Missing realized_pnl_usd"
        print("   ✓ EXIT fields present with PnL calculation")
    else:
        print("   ✗ No execution results")
        return False

    print()
    print("=" * 70)
    print("✓ ALL EQUITY TRACKING TESTS PASSED")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = test_equity_tracking()
    exit(0 if success else 1)
