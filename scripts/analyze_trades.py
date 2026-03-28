#!/usr/bin/env python3
"""
Analyze ghost trades from PostgreSQL.

Replaces log-grep analysis — all context data persisted in PG entry_context JSONB.

Usage:
    python scripts/analyze_trades.py                    # last 24h
    python scripts/analyze_trades.py --hours 48         # last 48h
    python scripts/analyze_trades.py --since "2026-03-19 19:46"  # since timestamp
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta

import psycopg2


def get_conn():
    return psycopg2.connect(
        dbname="liquidation_trading",
        user="liqtrade",
        password="liqtrade",
        host="localhost"
    )


def analyze(hours=24, since=None):
    conn = get_conn()
    cur = conn.cursor()

    if since:
        cutoff_ts = datetime.strptime(since, "%Y-%m-%d %H:%M").timestamp()
    else:
        cutoff_ts = time.time() - hours * 3600

    # Get all entries with context
    cur.execute("""
        SELECT e.trade_id, e.symbol, e.position_side, e.price, e.timestamp,
               e.entry_context,
               x.pnl, x.exit_reason, x.holding_duration_sec, x.timestamp as exit_ts
        FROM ghost_trades e
        LEFT JOIN ghost_trades x ON x.entry_trade_id = e.trade_id AND x.is_entry = 0
        WHERE e.is_entry = 1 AND e.timestamp >= %s
        ORDER BY e.timestamp
    """, (cutoff_ts,))

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"No trades found since {datetime.fromtimestamp(cutoff_ts):%Y-%m-%d %H:%M}")
        return

    print(f"{'='*80}")
    print(f"Trade Analysis — {len(rows)} entries since {datetime.fromtimestamp(cutoff_ts):%Y-%m-%d %H:%M}")
    print(f"{'='*80}\n")

    total_pnl = 0
    wins = 0
    losses = 0
    open_count = 0
    phase_stats = {}  # phase → {count, pnl, wins}
    dca_stats = {}    # level → {count, pnl, wins}
    wall_stats = {}   # wall status → {count, pnl, wins}

    for row in rows:
        trade_id, symbol, side, price, ts, ctx_json, pnl, exit_reason, hold_sec, exit_ts = row

        ctx = json.loads(ctx_json) if isinstance(ctx_json, str) else (ctx_json if isinstance(ctx_json, dict) else {})
        phase = ctx.get("decel_phase", "?")
        dca_level = ctx.get("dca_level", "?")
        rolling_z = ctx.get("rolling_z", "?")
        ratio = ctx.get("decel_ratio", "?")
        wall_gold = ctx.get("wall_gold", None)
        wall_rev = ctx.get("wall_consec_rev", None)

        # Format time
        entry_time = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")

        # Status
        if pnl is not None:
            status = f"{'W' if pnl > 0 else 'L'} ${pnl:+.2f}"
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            else:
                losses += 1
        else:
            status = "OPEN"
            open_count += 1

        hold_str = f"{hold_sec:.0f}s" if hold_sec else ""
        exit_str = exit_reason or ""

        wall_str = "GOLD" if wall_gold else (f"w{wall_rev}" if wall_rev is not None else "")

        print(f"  {entry_time}  {symbol:10s} {side:5s}  "
              f"phase={phase:10s} ratio={ratio!s:5s}  "
              f"dca={dca_level!s:2s}  z={rolling_z!s:5s}  "
              f"wall={wall_str:4s}  "
              f"{status:12s}  {hold_str:6s}  {exit_str}")

        # Aggregate by phase
        if phase != "?":
            if phase not in phase_stats:
                phase_stats[phase] = {"count": 0, "pnl": 0, "wins": 0, "losses": 0}
            phase_stats[phase]["count"] += 1
            if pnl is not None:
                phase_stats[phase]["pnl"] += pnl
                if pnl > 0:
                    phase_stats[phase]["wins"] += 1
                else:
                    phase_stats[phase]["losses"] += 1

        # Aggregate by DCA level
        if dca_level != "?":
            lvl = str(dca_level)
            if lvl not in dca_stats:
                dca_stats[lvl] = {"count": 0, "pnl": 0, "wins": 0, "losses": 0}
            dca_stats[lvl]["count"] += 1
            if pnl is not None:
                dca_stats[lvl]["pnl"] += pnl
                if pnl > 0:
                    dca_stats[lvl]["wins"] += 1
                else:
                    dca_stats[lvl]["losses"] += 1

        # Aggregate by wall status
        wkey = "GOLD" if wall_gold else ("WALL" if wall_rev and wall_rev >= 1 else "none")
        if wkey not in wall_stats:
            wall_stats[wkey] = {"count": 0, "pnl": 0, "wins": 0, "losses": 0}
        wall_stats[wkey]["count"] += 1
        if pnl is not None:
            wall_stats[wkey]["pnl"] += pnl
            if pnl > 0:
                wall_stats[wkey]["wins"] += 1
            else:
                wall_stats[wkey]["losses"] += 1

    closed = wins + losses
    print(f"\n{'─'*80}")
    print(f"Summary: {closed} closed ({wins}W/{losses}L), {open_count} open, "
          f"PnL=${total_pnl:+.2f}")
    if closed > 0:
        print(f"Win rate: {wins/closed:.1%}")

    if phase_stats:
        print(f"\n{'─'*40}")
        print(f"By Decel Phase:")
        print(f"  {'Phase':12s}  {'N':>3s}  {'W':>3s}  {'L':>3s}  {'WR':>5s}  {'PnL':>8s}")
        for phase in sorted(phase_stats.keys()):
            s = phase_stats[phase]
            wr = f"{s['wins']/(s['wins']+s['losses']):.0%}" if (s['wins']+s['losses']) > 0 else "-"
            print(f"  {phase:12s}  {s['count']:3d}  {s['wins']:3d}  {s['losses']:3d}  {wr:>5s}  ${s['pnl']:+.2f}")

    if dca_stats:
        print(f"\n{'─'*40}")
        print(f"By DCA Level:")
        print(f"  {'Level':>5s}  {'N':>3s}  {'W':>3s}  {'L':>3s}  {'WR':>5s}  {'PnL':>8s}")
        for lvl in sorted(dca_stats.keys()):
            s = dca_stats[lvl]
            wr = f"{s['wins']/(s['wins']+s['losses']):.0%}" if (s['wins']+s['losses']) > 0 else "-"
            print(f"  L{lvl:>4s}  {s['count']:3d}  {s['wins']:3d}  {s['losses']:3d}  {wr:>5s}  ${s['pnl']:+.2f}")

    if wall_stats:
        print(f"\n{'─'*40}")
        print(f"By Wall Status:")
        print(f"  {'Status':>6s}  {'N':>3s}  {'W':>3s}  {'L':>3s}  {'WR':>5s}  {'PnL':>8s}")
        for wkey in ['GOLD', 'WALL', 'none']:
            s = wall_stats.get(wkey)
            if not s: continue
            wr = f"{s['wins']/(s['wins']+s['losses']):.0%}" if (s['wins']+s['losses']) > 0 else "-"
            print(f"  {wkey:>6s}  {s['count']:3d}  {s['wins']:3d}  {s['losses']:3d}  {wr:>5s}  ${s['pnl']:+.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze ghost trades from PG")
    parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default: 24)")
    parser.add_argument("--since", type=str, help="Start time, e.g. '2026-03-19 19:46'")
    args = parser.parse_args()

    analyze(hours=args.hours, since=args.since)
