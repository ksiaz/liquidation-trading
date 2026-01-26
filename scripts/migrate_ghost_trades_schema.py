"""
Migrate Ghost Trades Schema to Enhanced Version

Adds enhanced tracking fields for comprehensive trade analysis.
Safe migration - preserves existing data.
"""

import sqlite3
from pathlib import Path


def migrate_database(db_path: str = "logs/execution.db"):
    """Add enhanced columns to ghost_trades and create new tables."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Starting ghost trades schema migration...")

    # Add new columns to existing ghost_trades table (safe - preserves data)
    new_columns = [
        ("parent_trade_id", "TEXT"),
        ("is_partial_close", "BOOLEAN DEFAULT 0"),
        ("exit_reason", "TEXT"),
        ("pnl_pct", "REAL"),
        ("fees_estimated", "REAL"),
        ("account_equity_after", "REAL"),
        ("entry_cycle_id", "INTEGER"),
        ("exit_cycle_id", "INTEGER"),
        ("winning_policy_name", "TEXT"),
        ("spread_bps", "REAL"),
        ("orderbook_depth_5", "TEXT"),
        ("mark_price", "REAL"),
        ("active_primitives", "TEXT"),
        ("position_fraction", "REAL"),
        ("concurrent_positions", "INTEGER"),
        ("total_exposure_pct", "REAL"),
        ("max_favorable_excursion", "REAL"),
        ("max_adverse_excursion", "REAL"),
        ("mfe_timestamp", "REAL"),
        ("mae_timestamp", "REAL"),
        ("holding_duration_sec", "REAL"),
    ]

    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE ghost_trades ADD COLUMN {col_name} {col_type}")
            print(f"✓ Added column: {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"  Column {col_name} already exists, skipping")
            else:
                raise

    # Create ghost_trade_rejections table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ghost_trade_rejections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER NOT NULL,
            timestamp REAL NOT NULL,

            symbol TEXT NOT NULL,
            attempted_action TEXT NOT NULL,
            attempted_side TEXT,

            rejection_reason TEXT NOT NULL,

            mandate_id INTEGER,
            policy_name TEXT,

            account_balance REAL,
            account_equity REAL,
            open_positions_count INTEGER,

            current_price REAL,
            spread_bps REAL,

            triggering_primitives TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ Created ghost_trade_rejections table")

    # Create ghost_position_lifecycle table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ghost_position_lifecycle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id TEXT NOT NULL,
            symbol TEXT NOT NULL,

            entry_trade_id TEXT NOT NULL,
            entry_cycle_id INTEGER NOT NULL,
            entry_timestamp REAL NOT NULL,
            entry_price REAL NOT NULL,
            entry_quantity REAL NOT NULL,
            entry_side TEXT NOT NULL,

            current_quantity REAL,
            current_unrealized_pnl REAL,
            current_mfe REAL,
            current_mae REAL,

            exit_trade_id TEXT,
            exit_cycle_id INTEGER,
            exit_timestamp REAL,
            exit_price REAL,
            exit_reason TEXT,

            realized_pnl REAL,
            total_holding_time_sec REAL,

            status TEXT NOT NULL,

            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ Created ghost_position_lifecycle table")

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ghost_trades_entry_cycle ON ghost_trades(entry_cycle_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ghost_trades_exit_cycle ON ghost_trades(exit_cycle_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ghost_trades_policy ON ghost_trades(winning_policy_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejections_cycle ON ghost_trade_rejections(cycle_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejections_symbol ON ghost_trade_rejections(symbol)")
    print("✓ Created indexes")

    conn.commit()
    conn.close()

    print("\n✅ Migration completed successfully!")
    print("\nNew capabilities enabled:")
    print("  - Link trades to observation cycles")
    print("  - Track which policies/primitives generated trades")
    print("  - Log trade rejections")
    print("  - Track position lifecycle with MFE/MAE")
    print("  - Measure holding duration and quality")


if __name__ == "__main__":
    migrate_database()
