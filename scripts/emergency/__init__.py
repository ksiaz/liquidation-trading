"""
Emergency Scripts Package.

Provides tools for emergency shutdown and position management:
- kill_switch.sh: Full emergency shutdown
- close_positions.py: Close all positions at market
- cancel_orders.py: Cancel all open orders

Usage:
    # Full shutdown
    ./scripts/emergency/kill_switch.sh

    # Dry run (see what would happen)
    ./scripts/emergency/kill_switch.sh --dry-run

    # Individual operations
    python scripts/emergency/close_positions.py --force
    python scripts/emergency/cancel_orders.py --all

See docs/runbooks/emergency_shutdown.md for detailed procedures.
"""
