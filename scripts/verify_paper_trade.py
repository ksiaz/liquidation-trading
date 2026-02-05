#!/usr/bin/env python3
"""
Verify paper trade internal state against real market data.

Compares:
- HL adapter status and lag
- Binance prices (ground truth) vs paper trade prices
- Zone detections and cascade alerts
- Warmup progress

Usage:
    python scripts/verify_paper_trade.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import time
import re
from datetime import datetime, timezone

# Symbols we're tracking
SYMBOLS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'AVAX', 'LINK', 'HYPE', 'SUI', 'NEAR',
           'LTC', 'ATOM', 'AAVE', 'APT', 'ARB']


def get_binance_prices():
    """Get current Binance futures prices for comparison."""
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        prices = {}
        for item in data:
            symbol = item['symbol'].replace('USDT', '')
            if symbol in SYMBOLS:
                prices[symbol] = float(item['price'])
        return prices
    except Exception as e:
        print(f"  ERROR fetching Binance prices: {e}")
        return {}


def get_hl_adapter_status():
    """Get HL adapter status via gRPC."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hl-adapter'))
        import grpc
        import events_pb2
        import events_pb2_grpc

        channel = grpc.insecure_channel('localhost:50051')
        stub = events_pb2_grpc.HLNodeAdapterStub(channel)
        status = stub.GetStatus(events_pb2.Empty())

        block_time = datetime.fromtimestamp(status.latest_block_time_ns / 1e9, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        lag = (now - block_time).total_seconds()

        return {
            'status': ['UNKNOWN', 'HEALTHY', 'LAGGING', 'STALE', 'ERROR'][status.status],
            'block_height': status.latest_block_height,
            'block_time': block_time.strftime('%H:%M:%S'),
            'lag_seconds': lag,
            'prices_emitted': status.prices_emitted,
            'liquidations_emitted': status.liquidations_emitted,
            'uptime': status.uptime_seconds,
        }
    except Exception as e:
        return {'error': str(e)}


def parse_paper_trade_log(log_path='/tmp/paper_trade.log'):
    """Parse paper trade log for internal state."""
    state = {
        'cascade_alerts': [],
        'zone_detections': [],
        'prices_seen': {},
        'm2_stats': None,
        'warmup_status': {},
        'diag_prices': {},  # Symbol -> price from DIAG output
    }

    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()[-1000:]  # Last 1000 lines

        current_symbol = None
        for line in lines:
            # Track current symbol from DIAG
            if '[DIAG]' in line and 'mandate generation' in line:
                match = re.search(r'\[DIAG\] (\w+) mandate', line)
                if match:
                    current_symbol = match.group(1)

            # Current prices from DIAG
            if 'current_price:' in line and current_symbol:
                match = re.search(r'current_price:\s*([\d.]+)', line)
                if match:
                    state['diag_prices'][current_symbol] = float(match.group(1))

            # Cascade alerts
            if 'CASCADE ALERT:' in line:
                parts = line.split('CASCADE ALERT:')[1].strip()
                state['cascade_alerts'].append(parts[:100])

            # Zone detections with details
            if 'zone=demand' in line or 'zone=supply' in line:
                match = re.search(r'zone=(\w+), disp=(\w+), retest=(\w+)', line)
                if match:
                    state['zone_detections'].append({
                        'type': match.group(1),
                        'disp': match.group(2),
                        'retest': match.group(3),
                    })

            # M2 stats
            if '[M2-DIAG] Stats:' in line:
                state['m2_stats'] = line.split('Stats:')[1].strip()

            # Warmup status
            if 'WARMUP GATE' in line and 'fills=' in line:
                match = re.search(r'(\w+USDT?).*fills=(\d+)', line)
                if match:
                    symbol = match.group(1)
                    fills = int(match.group(2))
                    state['warmup_status'][symbol] = fills

    except Exception as e:
        state['error'] = str(e)

    return state


def main():
    print("=" * 70)
    print(f"PAPER TRADE VERIFICATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. HL Adapter Status
    print("\n[1] HL ADAPTER STATUS")
    hl_status = get_hl_adapter_status()
    if 'error' in hl_status:
        print(f"  ERROR: {hl_status['error']}")
    else:
        status_color = '✓' if hl_status['status'] == 'HEALTHY' else '⚠'
        print(f"  {status_color} Status: {hl_status['status']}")
        print(f"    Block: {hl_status['block_height']} ({hl_status['block_time']} UTC)")
        print(f"    Lag: {hl_status['lag_seconds']:.1f}s")
        print(f"    Prices: {hl_status['prices_emitted']:,} | Liqs: {hl_status['liquidations_emitted']:,}")
        print(f"    Uptime: {hl_status['uptime']//60}m {hl_status['uptime']%60}s")

    # 2. Parse paper trade state
    pt_state = parse_paper_trade_log()

    # 3. Price Comparison
    print("\n[2] PRICE COMPARISON (Binance vs Paper Trade)")
    binance_prices = get_binance_prices()
    print(f"  {'Symbol':<8} {'Binance':>12} {'Paper':>12} {'Diff':>10}")
    print(f"  {'-'*8} {'-'*12} {'-'*12} {'-'*10}")

    for sym in ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']:
        binance_p = binance_prices.get(sym)
        # Try both formats
        paper_p = pt_state['diag_prices'].get(sym) or pt_state['diag_prices'].get(f'{sym}USDT')

        if binance_p:
            binance_str = f"${binance_p:,.2f}"
            if paper_p:
                diff_pct = (paper_p - binance_p) / binance_p * 100
                paper_str = f"${paper_p:,.2f}"
                diff_str = f"{diff_pct:+.3f}%"
            else:
                paper_str = "N/A"
                diff_str = "-"
            print(f"  {sym:<8} {binance_str:>12} {paper_str:>12} {diff_str:>10}")

    # 4. M2 / Geometry Status
    print("\n[3] GEOMETRY STATUS")
    if pt_state.get('m2_stats'):
        print(f"  M2 Stats: {pt_state['m2_stats']}")

    zones = pt_state.get('zone_detections', [])
    if zones:
        demand = sum(1 for z in zones if z['type'] == 'demand')
        supply = sum(1 for z in zones if z['type'] == 'supply')
        disp_true = sum(1 for z in zones if z['disp'] == 'True')
        retest_true = sum(1 for z in zones if z['retest'] == 'True')
        print(f"  Zones (recent): {len(zones)} (demand={demand}, supply={supply})")
        print(f"  Displacement=True: {disp_true} | Retest=True: {retest_true}")
    else:
        print("  No zones detected in recent logs")

    # 5. Cascade Status
    print("\n[4] CASCADE STATUS")
    alerts = pt_state.get('cascade_alerts', [])
    if alerts:
        print(f"  Alerts (recent): {len(alerts)}")
        for alert in alerts[-3:]:
            print(f"    • {alert}")
    else:
        print("  No cascade alerts in recent logs")

    # 6. Warmup Progress
    print("\n[5] WARMUP PROGRESS")
    warmup = pt_state.get('warmup_status', {})
    ready = [s for s, f in warmup.items() if f >= 200]
    pending = sorted([(s, f) for s, f in warmup.items() if f < 200], key=lambda x: -x[1])

    if ready:
        print(f"  ✓ Ready: {', '.join(ready)}")
    if pending:
        print(f"  ⏳ Pending (top 5):")
        for sym, fills in pending[:5]:
            pct = fills / 200 * 100
            bar = '█' * int(pct / 10) + '░' * (10 - int(pct / 10))
            print(f"     {sym:<12} [{bar}] {fills}/200 ({pct:.0f}%)")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
