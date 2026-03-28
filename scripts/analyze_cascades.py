#!/usr/bin/env python3
"""
Analyze cascade lifecycle data from PG.

Usage:
    python scripts/analyze_cascades.py                # all data
    python scripts/analyze_cascades.py --hours 24     # last 24h
    python scripts/analyze_cascades.py --cascade ID   # specific cascade
"""

import argparse
import psycopg2
import time
from collections import defaultdict
from datetime import datetime


def get_conn():
    return psycopg2.connect(
        dbname="liquidation_trading", user="liqtrade",
        password="liqtrade", host="localhost"
    )


def analyze(hours=None, cascade_id=None):
    conn = get_conn()
    cur = conn.cursor()

    where = "WHERE 1=1"
    params = []
    if hours:
        where += " AND ts > %s"
        params.append(time.time() - hours * 3600)
    if cascade_id:
        where += " AND cascade_id = %s"
        params.append(cascade_id)

    # 1. Cascade summary
    cur.execute(f"""
        SELECT cascade_id, symbol, min(ts), max(ts), max(peak_z),
               count(*), min(price_at_start),
               avg(shadow_mfe_5m), avg(shadow_mae_5m)
        FROM cascade_lifecycle {where}
        GROUP BY cascade_id, symbol
        ORDER BY min(ts) DESC
    """, params)

    cascades = cur.fetchall()
    print(f"{'='*80}")
    print(f"Cascade Lifecycle Analysis — {len(cascades)} cascades")
    print(f"{'='*80}\n")

    if not cascades:
        print("No data yet. Wait for cascades to occur.")
        conn.close()
        return

    print(f"{'Time':>14s}  {'Symbol':>10s}  {'PeakZ':>6s}  {'Snaps':>5s}  "
          f"{'Duration':>8s}  {'MFE5m':>7s}  {'MAE5m':>7s}  {'Edge':>7s}")

    for c in cascades[:30]:
        cid, sym, start, end, peak, snaps, start_px, mfe, mae = c
        t = datetime.fromtimestamp(start).strftime('%m-%d %H:%M')
        dur = f"{end - start:.0f}s"
        mfe_s = f"{mfe:+.1f}bp" if mfe is not None else "?"
        mae_s = f"{mae:.1f}bp" if mae is not None else "?"
        edge = f"{(mfe or 0) - (mae or 0):+.1f}bp"
        print(f"{t:>14s}  {sym:>10s}  {peak:>6.1f}  {snaps:>5d}  "
              f"{dur:>8s}  {mfe_s:>7s}  {mae_s:>7s}  {edge:>7s}")

    # 2. Optimal entry point: at what z-level and time-since-peak is MFE maximized?
    cur.execute(f"""
        SELECT
            CASE WHEN liq_z >= 5 THEN '5+'
                 WHEN liq_z >= 3 THEN '3-5'
                 WHEN liq_z >= 2 THEN '2-3'
                 WHEN liq_z >= 1 THEN '1-2'
                 ELSE '<1' END as z_bucket,
            count(*),
            avg(shadow_mfe_5m),
            avg(shadow_mae_5m),
            avg(shadow_mfe_5m) - avg(shadow_mae_5m) as edge
        FROM cascade_lifecycle {where}
          AND shadow_mfe_5m IS NOT NULL
        GROUP BY z_bucket
        ORDER BY edge DESC
    """, params)

    print(f"\n{'─'*40}")
    print(f"Shadow PnL by Z-Level at Entry:")
    print(f"{'Z Bucket':>10s}  {'N':>6s}  {'MFE5m':>7s}  {'MAE5m':>7s}  {'Edge':>7s}")
    for r in cur.fetchall():
        print(f"{r[0]:>10s}  {r[1]:>6d}  {r[2]:>+6.1f}bp  {r[3]:>6.1f}bp  {r[4]:>+6.1f}bp")

    # 3. Optimal entry by time since peak
    cur.execute(f"""
        SELECT
            CASE WHEN time_since_peak < 5 THEN '0-5s'
                 WHEN time_since_peak < 15 THEN '5-15s'
                 WHEN time_since_peak < 30 THEN '15-30s'
                 WHEN time_since_peak < 60 THEN '30-60s'
                 ELSE '60s+' END as delay_bucket,
            count(*),
            avg(shadow_mfe_5m),
            avg(shadow_mae_5m),
            avg(shadow_mfe_5m) - avg(shadow_mae_5m) as edge
        FROM cascade_lifecycle {where}
          AND shadow_mfe_5m IS NOT NULL AND time_since_peak >= 0
        GROUP BY delay_bucket
        ORDER BY edge DESC
    """, params)

    print(f"\n{'─'*40}")
    print(f"Shadow PnL by Time Since Peak Z:")
    print(f"{'Delay':>10s}  {'N':>6s}  {'MFE5m':>7s}  {'MAE5m':>7s}  {'Edge':>7s}")
    for r in cur.fetchall():
        print(f"{r[0]:>10s}  {r[1]:>6d}  {r[2]:>+6.1f}bp  {r[3]:>6.1f}bp  {r[4]:>+6.1f}bp")

    # 4. Multi-coin context
    cur.execute(f"""
        SELECT
            CASE WHEN n_coins_active = 0 THEN 'isolated'
                 WHEN n_coins_active <= 2 THEN '1-2 coins'
                 ELSE '3+ coins' END as multi,
            count(*),
            avg(shadow_mfe_5m) - avg(shadow_mae_5m) as edge
        FROM cascade_lifecycle {where}
          AND shadow_mfe_5m IS NOT NULL
        GROUP BY multi
        ORDER BY edge DESC
    """, params)

    print(f"\n{'─'*40}")
    print(f"Shadow PnL by Multi-Coin Context:")
    print(f"{'Context':>12s}  {'N':>6s}  {'Edge':>7s}")
    for r in cur.fetchall():
        print(f"{r[0]:>12s}  {r[1]:>6d}  {r[2]:>+6.1f}bp")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, help="Look back N hours")
    parser.add_argument("--cascade", type=str, help="Specific cascade ID")
    args = parser.parse_args()
    analyze(hours=args.hours, cascade_id=args.cascade)
