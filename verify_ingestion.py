"""
Verify Data Ingestion

Checks what data is actually being ingested by M1 and stored in the database.
"""

import sqlite3
from datetime import datetime, timedelta

def verify_ingestion():
    """Verify what data exists in the database."""

    db_path = "logs/execution.db"

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("=" * 80)
        print("DATA INGESTION VERIFICATION")
        print("=" * 80)

        # Check what tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        print(f"\n📊 Database Tables ({len(tables)} total):")
        for table in tables:
            print(f"  - {table[0]}")

        print("\n" + "=" * 80)
        print("RAW DATA INGESTION (Last 24 Hours)")
        print("=" * 80)

        # Get 24 hours ago timestamp
        now = datetime.now().timestamp()
        day_ago = now - (24 * 3600)

        # Check trade events table
        print("\n1️⃣  TRADE EVENTS (aggTrade stream)")
        print("-" * 80)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trade_events'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT symbol, COUNT(*) as trade_count,
                           MIN(timestamp) as first_trade,
                           MAX(timestamp) as last_trade
                    FROM trade_events
                    WHERE timestamp > ?
                    GROUP BY symbol
                    ORDER BY symbol
                """, (day_ago,))

                trades = cursor.fetchall()
                if trades:
                    total_trades = sum(t[1] for t in trades)
                    print(f"✅ Total trades: {total_trades:,} across {len(trades)} symbols")
                    print(f"\nPer-Symbol Breakdown:")
                    for symbol, count, first, last in trades:
                        duration = last - first
                        rate = count / (duration / 60) if duration > 0 else 0
                        first_time = datetime.fromtimestamp(first).strftime("%Y-%m-%d %H:%M:%S")
                        last_time = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S")
                        print(f"  {symbol:12} {count:8,} trades  ({rate:6.1f}/min)  {first_time} → {last_time}")
                else:
                    print("⚠️  No trades found in last 24 hours")
            else:
                print("❌ trade_events table does not exist")
        except Exception as e:
            print(f"❌ Error checking trades: {e}")

        # Check liquidation events table
        print("\n2️⃣  LIQUIDATION EVENTS (forceOrder stream)")
        print("-" * 80)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='liquidation_events'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT symbol, COUNT(*) as liq_count,
                           MIN(timestamp) as first_liq,
                           MAX(timestamp) as last_liq
                    FROM liquidation_events
                    WHERE timestamp > ?
                    GROUP BY symbol
                    ORDER BY symbol
                """, (day_ago,))

                liqs = cursor.fetchall()
                if liqs:
                    total_liqs = sum(l[1] for l in liqs)
                    print(f"✅ Total liquidations: {total_liqs:,} across {len(liqs)} symbols")
                    print(f"\nPer-Symbol Breakdown:")
                    for symbol, count, first, last in liqs:
                        first_time = datetime.fromtimestamp(first).strftime("%Y-%m-%d %H:%M:%S") if first else "N/A"
                        last_time = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S") if last else "N/A"
                        print(f"  {symbol:12} {count:8,} liquidations  {first_time} → {last_time}")
                else:
                    print("⚠️  No liquidations found in last 24 hours")
            else:
                print("❌ liquidation_events table does not exist")
        except Exception as e:
            print(f"❌ Error checking liquidations: {e}")

        # Check order book events table
        print("\n3️⃣  ORDER BOOK EVENTS (bookTicker stream)")
        print("-" * 80)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orderbook_events'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT symbol, COUNT(*) as ob_count,
                           MIN(timestamp) as first_ob,
                           MAX(timestamp) as last_ob
                    FROM orderbook_events
                    WHERE timestamp > ?
                    GROUP BY symbol
                    ORDER BY symbol
                """, (day_ago,))

                obs = cursor.fetchall()
                if obs:
                    total_obs = sum(o[1] for o in obs)
                    print(f"✅ Total order book updates: {total_obs:,} across {len(obs)} symbols")
                    print(f"\nPer-Symbol Breakdown:")
                    for symbol, count, first, last in obs:
                        duration = last - first
                        rate = count / (duration / 60) if duration > 0 else 0
                        first_time = datetime.fromtimestamp(first).strftime("%Y-%m-%d %H:%M:%S")
                        last_time = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S")
                        print(f"  {symbol:12} {count:8,} updates  ({rate:6.1f}/min)  {first_time} → {last_time}")
                else:
                    print("⚠️  No order book updates in last 24 hours")
            else:
                print("❌ orderbook_events table does not exist")
        except Exception as e:
            print(f"❌ Error checking order book: {e}")

        # Check OHLC candles
        print("\n4️⃣  OHLC CANDLES (kline_1m stream)")
        print("-" * 80)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ohlc_candles'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT symbol, COUNT(*) as candle_count,
                           MIN(timestamp) as first_candle,
                           MAX(timestamp) as last_candle
                    FROM ohlc_candles
                    WHERE timestamp > ?
                    GROUP BY symbol
                    ORDER BY symbol
                """, (day_ago,))

                candles = cursor.fetchall()
                if candles:
                    total_candles = sum(c[1] for c in candles)
                    print(f"✅ Total 1m candles: {total_candles:,} across {len(candles)} symbols")
                    print(f"\nPer-Symbol Breakdown:")
                    for symbol, count, first, last in candles:
                        duration = (last - first) / 3600
                        first_time = datetime.fromtimestamp(first).strftime("%Y-%m-%d %H:%M:%S")
                        last_time = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S")
                        print(f"  {symbol:12} {count:8,} candles  ({duration:5.1f}h)  {first_time} → {last_time}")
                else:
                    print("⚠️  No OHLC candles in last 24 hours")
            else:
                print("❌ ohlc_candles table does not exist")
        except Exception as e:
            print(f"❌ Error checking OHLC: {e}")

        print("\n" + "=" * 80)
        print("M4 PRIMITIVE COMPUTATION (Last 24 Hours)")
        print("=" * 80)

        # Check primitive values table
        print("\n5️⃣  PRIMITIVE VALUES")
        print("-" * 80)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='primitive_values'")
            if cursor.fetchone():
                # Get recent cycles
                cursor.execute("""
                    SELECT COUNT(*) as cycle_count,
                           MIN(timestamp) as first_cycle,
                           MAX(timestamp) as last_cycle
                    FROM execution_cycles
                    WHERE timestamp > ?
                """, (day_ago,))

                cycle_info = cursor.fetchone()
                if cycle_info and cycle_info[0] > 0:
                    cycle_count, first, last = cycle_info
                    duration = (last - first) / 3600
                    rate = cycle_count / duration if duration > 0 else 0
                    first_time = datetime.fromtimestamp(first).strftime("%Y-%m-%d %H:%M:%S")
                    last_time = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S")

                    print(f"✅ Execution cycles: {cycle_count:,} ({rate:.1f} cycles/hour)")
                    print(f"   Duration: {duration:.1f}h  ({first_time} → {last_time})")

                    # Check which primitives are computing
                    print(f"\n   Primitive Computation Rates (last 1000 cycles):")

                    primitives = [
                        ('zone_penetration_depth', 'Zone Penetration'),
                        ('traversal_compactness', 'Traversal Compactness'),
                        ('central_tendency_deviation', 'Central Tendency'),
                        ('price_velocity', 'Price Velocity'),
                        ('absence_duration', 'Structural Absence'),
                        ('persistence_duration', 'Structural Persistence'),
                        ('liquidation_density', 'Liquidation Density'),
                        ('directional_continuity_value', 'Directional Continuity'),
                        ('trade_burst_count', 'Trade Burst'),
                        ('resting_size_bid', 'Resting Size (Bid)'),
                        ('resting_size_ask', 'Resting Size (Ask)'),
                        ('order_consumption_size', 'Order Consumption'),
                    ]

                    cursor.execute("SELECT MAX(cycle_id) FROM primitive_values")
                    max_cycle = cursor.fetchone()[0]
                    if max_cycle:
                        start_cycle = max(1, max_cycle - 1000)

                        for col, label in primitives:
                            cursor.execute(f"""
                                SELECT COUNT(*) * 100.0 /
                                       (SELECT COUNT(*) FROM primitive_values
                                        WHERE cycle_id >= ?)
                                FROM primitive_values
                                WHERE cycle_id >= ? AND {col} IS NOT NULL
                            """, (start_cycle, start_cycle))

                            rate = cursor.fetchone()[0] or 0
                            status = "✅" if rate > 50 else "⚠️ " if rate > 10 else "❌"
                            print(f"   {status} {label:30} {rate:5.1f}%")
                else:
                    print("⚠️  No execution cycles in last 24 hours")
            else:
                print("❌ primitive_values table does not exist")
        except Exception as e:
            print(f"❌ Error checking primitives: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 80)
        print("EXECUTION & GHOST TRADING (Last 24 Hours)")
        print("=" * 80)

        # Check ghost trades
        print("\n6️⃣  GHOST TRADES")
        print("-" * 80)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ghost_trades'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT COUNT(*) as total_trades,
                           SUM(CASE WHEN is_entry = 0 THEN 1 ELSE 0 END) as completed,
                           SUM(CASE WHEN is_entry = 1 THEN 1 ELSE 0 END) as open,
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                           SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                           SUM(pnl) as total_pnl
                    FROM ghost_trades
                    WHERE timestamp > ?
                """, (day_ago,))

                stats = cursor.fetchone()
                if stats and stats[0] > 0:
                    total, completed, open, wins, losses, total_pnl = stats
                    win_rate = (wins / completed * 100) if completed > 0 else 0

                    print(f"✅ Ghost Trades Summary:")
                    print(f"   Total Trades:     {total:8,}")
                    print(f"   Completed:        {completed:8,}")
                    print(f"   Still Open:       {open:8,}")
                    print(f"   Wins/Losses:      {wins:4,} / {losses:4,}  ({win_rate:.1f}% win rate)")
                    print(f"   Total PNL:        ${total_pnl:+.2f}" if total_pnl else "   Total PNL:        $0.00")

                    # Recent trades (exits only, as they have PNL calculated)
                    cursor.execute("""
                        SELECT symbol, position_side, price, price, pnl, holding_duration_sec
                        FROM ghost_trades
                        WHERE is_entry = 0 AND timestamp > ?
                        ORDER BY timestamp DESC
                        LIMIT 10
                    """, (day_ago,))

                    recent = cursor.fetchall()
                    if recent:
                        print(f"\n   Recent Completed Trades (last 10):")
                        for symbol, side, entry, exit, pnl, holding in recent:
                            holding_min = holding / 60 if holding else 0
                            pnl_str = f"${pnl:+.2f}" if pnl else "$0.00"
                            print(f"   {symbol:12} {side:5} Entry:${entry:9,.2f} Exit:${exit:9,.2f} PNL:{pnl_str:10} Hold:{holding_min:5.1f}m")
                else:
                    print("⚠️  No ghost trades in last 24 hours")
            else:
                print("❌ ghost_trades table does not exist")
        except Exception as e:
            print(f"❌ Error checking ghost trades: {e}")

        # Check mandates
        print("\n7️⃣  MANDATE GENERATION")
        print("-" * 80)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mandates'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT mandate_type, COUNT(*) as count
                    FROM mandates
                    WHERE timestamp > ?
                    GROUP BY mandate_type
                    ORDER BY count DESC
                """, (day_ago,))

                mandates = cursor.fetchall()
                if mandates:
                    total_mandates = sum(m[1] for m in mandates)
                    print(f"✅ Total mandates generated: {total_mandates:,}")
                    print(f"\n   Breakdown by Type:")
                    for mtype, count in mandates:
                        pct = count / total_mandates * 100
                        print(f"   {mtype:10} {count:8,}  ({pct:5.1f}%)")
                else:
                    print("⚠️  No mandates in last 24 hours")
            else:
                print("❌ mandates table does not exist")
        except Exception as e:
            print(f"❌ Error checking mandates: {e}")

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        # Overall summary
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM trade_events WHERE timestamp > ?) as trades,
                (SELECT COUNT(*) FROM liquidation_events WHERE timestamp > ?) as liquidations,
                (SELECT COUNT(*) FROM orderbook_events WHERE timestamp > ?) as orderbook,
                (SELECT COUNT(*) FROM execution_cycles WHERE timestamp > ?) as cycles,
                (SELECT COUNT(*) FROM ghost_trades WHERE timestamp > ?) as ghost_trades
        """, (day_ago, day_ago, day_ago, day_ago, day_ago))

        summary = cursor.fetchone()
        trades, liqs, ob, cycles, gt = summary

        print(f"\n📈 Data Ingestion (Last 24h):")
        print(f"   Trade Events:     {trades:12,}")
        print(f"   Liquidations:     {liqs:12,}")
        print(f"   Order Book:       {ob:12,}")
        print(f"   Execution Cycles: {cycles:12,}")
        print(f"   Ghost Trades:     {gt:12,}")

        # Data sources
        print(f"\n📡 Data Sources (Binance Futures WebSocket):")
        print(f"   ✅ aggTrade      - Real-time trade execution data")
        print(f"   ✅ forceOrder    - Liquidation events")
        print(f"   ✅ bookTicker    - Best bid/ask updates")
        print(f"   ✅ kline_1m      - 1-minute OHLC candles")

        print(f"\n🎯 Configured Symbols (10):")
        print(f"   BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT")
        print(f"   DOGEUSDT, ADAUSDT, AVAXUSDT, TRXUSDT, DOTUSDT")

        print("\n" + "=" * 80)

        conn.close()

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    except FileNotFoundError:
        print(f"❌ Database not found at {db_path}")
        print("   System may not have been run yet.")

if __name__ == "__main__":
    verify_ingestion()
