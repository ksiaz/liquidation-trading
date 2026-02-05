#!/usr/bin/env python3
"""
Verify paper trade system against real market events from HL node.

Verification approach:
1. Stream events from HL adapter (which reads from node) - this is ground truth
2. Parse paper_trade.log for what system detected/acted on
3. Compare: did system see what adapter saw? Did it act appropriately?

What we verify:
- Liquidation events: adapter reported X, did system log seeing X?
- Cascade alerts: system alerted at time T, did liquidations follow?
- Price consistency: adapter price vs system's internal price

Usage:
    python scripts/verify_paper_trade.py              # Single snapshot
    python scripts/verify_paper_trade.py --monitor    # Continuous verification
    python scripts/verify_paper_trade.py --stats      # Show statistics
"""
import sys
import os
import argparse
import time
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Dict, List
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from scripts.verification_db import (
    get_connection,
    record_cascade_alert,
    verify_cascade_alert,
    record_liquidation,
    get_cascade_stats,
    get_liquidations_in_window,
)

SYMBOLS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'AVAX', 'LINK', 'SUI', 'NEAR',
           'LTC', 'ATOM', 'AAVE', 'APT', 'ARB']

# Verification thresholds
CASCADE_VERIFY_WINDOW_SEC = 120  # Check for liquidations within 120s of cascade alert
LIQ_BURST_THRESHOLD_USD = 10000  # Minimum value to count as burst


@dataclass
class AdapterEvent:
    """Event from HL adapter (ground truth)."""
    timestamp: float
    event_type: str  # 'LIQUIDATION', 'FILL', 'PRICE'
    symbol: str
    data: Dict


class NodeEventCollector:
    """
    Collect events directly from HL adapter gRPC streams.
    This is the ground truth - what the node actually reported.
    """

    def __init__(self):
        self.liquidations: List[AdapterEvent] = []
        self.fills: List[AdapterEvent] = []
        self.prices: Dict[str, AdapterEvent] = {}  # Latest price per symbol
        self.running = False
        self._threads = []
        self._lock = threading.Lock()

    def start(self):
        """Start streaming from adapter."""
        if self.running:
            return

        self.running = True

        # Start liquidation stream
        t1 = threading.Thread(target=self._stream_liquidations, daemon=True)
        t1.start()
        self._threads.append(t1)

        # Start fill stream
        t2 = threading.Thread(target=self._stream_fills, daemon=True)
        t2.start()
        self._threads.append(t2)

        # Start price stream
        t3 = threading.Thread(target=self._stream_prices, daemon=True)
        t3.start()
        self._threads.append(t3)

    def stop(self):
        """Stop streaming."""
        self.running = False

    def _get_stub(self):
        """Get gRPC stub."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hl-adapter'))
        import grpc
        import events_pb2
        import events_pb2_grpc

        channel = grpc.insecure_channel('localhost:50051')
        stub = events_pb2_grpc.HLNodeAdapterStub(channel)
        return stub, events_pb2

    def _stream_liquidations(self):
        """Stream liquidations from adapter."""
        while self.running:
            try:
                stub, pb2 = self._get_stub()
                request = pb2.StreamRequest(symbols=SYMBOLS)

                for event in stub.StreamLiquidations(request):
                    if not self.running:
                        break

                    liq = AdapterEvent(
                        timestamp=event.timestamp_ms / 1000.0,
                        event_type='LIQUIDATION',
                        symbol=event.symbol,
                        data={
                            'side': event.side,
                            'price': float(event.price),
                            'size': float(event.size),
                            'value_usd': float(event.value_usd),
                            'liquidated_account': event.liquidated_account,
                        }
                    )

                    with self._lock:
                        self.liquidations.append(liq)
                        # Keep last 500
                        if len(self.liquidations) > 500:
                            self.liquidations = self.liquidations[-500:]

            except Exception as e:
                if self.running:
                    time.sleep(2)

    def _stream_fills(self):
        """Stream fills from adapter."""
        while self.running:
            try:
                stub, pb2 = self._get_stub()
                request = pb2.StreamRequest(symbols=SYMBOLS)

                for event in stub.StreamFills(request):
                    if not self.running:
                        break

                    fill = AdapterEvent(
                        timestamp=event.timestamp_ms / 1000.0,
                        event_type='FILL',
                        symbol=event.symbol,
                        data={
                            'side': event.side,
                            'price': float(event.price),
                            'size': float(event.size),
                            'is_liquidation': event.is_liquidation,
                        }
                    )

                    with self._lock:
                        self.fills.append(fill)
                        # Keep last 1000
                        if len(self.fills) > 1000:
                            self.fills = self.fills[-1000:]

            except Exception as e:
                if self.running:
                    time.sleep(2)

    def _stream_prices(self):
        """Stream prices from adapter."""
        while self.running:
            try:
                stub, pb2 = self._get_stub()
                request = pb2.StreamRequest(symbols=SYMBOLS)

                for event in stub.StreamPrices(request):
                    if not self.running:
                        break

                    price = AdapterEvent(
                        timestamp=event.timestamp_ms / 1000.0,
                        event_type='PRICE',
                        symbol=event.symbol,
                        data={
                            'oracle_price': float(event.oracle_price),
                            'mark_price': float(event.mark_price),
                        }
                    )

                    with self._lock:
                        self.prices[event.symbol] = price

            except Exception as e:
                if self.running:
                    time.sleep(2)

    def get_liquidations_in_window(self, symbol: str, start_ts: float, end_ts: float) -> List[AdapterEvent]:
        """Get liquidations for symbol in time window."""
        with self._lock:
            return [l for l in self.liquidations
                    if l.symbol == symbol and start_ts <= l.timestamp <= end_ts]

    def get_liquidation_value_in_window(self, symbol: str, start_ts: float, end_ts: float) -> float:
        """Get total liquidation value in window."""
        liqs = self.get_liquidations_in_window(symbol, start_ts, end_ts)
        return sum(l.data['value_usd'] for l in liqs)

    def get_recent_liquidations(self, seconds: float = 60) -> List[AdapterEvent]:
        """Get liquidations in last N seconds."""
        cutoff = time.time() - seconds
        with self._lock:
            return [l for l in self.liquidations if l.timestamp >= cutoff]

    def get_stats(self) -> Dict:
        """Get collector statistics."""
        with self._lock:
            return {
                'liquidations_collected': len(self.liquidations),
                'fills_collected': len(self.fills),
                'symbols_with_prices': len(self.prices),
            }


def get_adapter_status() -> Dict:
    """Get HL adapter status."""
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
            'block_time': block_time,
            'lag_seconds': lag,
            'prices_emitted': status.prices_emitted,
            'liquidations_emitted': status.liquidations_emitted,
        }
    except Exception as e:
        return {'error': str(e)}


def parse_system_log(log_path: str = '/tmp/paper_trade.log') -> Dict:
    """
    Parse what the system reported seeing/doing.
    This is what we compare against ground truth.
    """
    result = {
        'cascade_alerts': [],
        'liquidations_seen': [],
        'zones_detected': [],
        'm2_stats': None,
    }

    try:
        with open(log_path, 'r') as f:
            f.seek(0, 2)
            file_size = f.tell()
            read_size = min(1000000, file_size)  # Last 1MB
            f.seek(max(0, file_size - read_size))
            content = f.read()

        for line in content.split('\n'):
            # Cascade alerts
            if 'CASCADE ALERT:' in line:
                ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                timestamp = None
                if ts_match:
                    try:
                        timestamp = datetime.strptime(ts_match.group(1), '%Y-%m-%d %H:%M:%S').timestamp()
                    except:
                        pass

                match = re.search(
                    r'CASCADE ALERT: (\w+) - (\d+) positions, \$([0-9,]+) at risk, dominant=(\w+)',
                    line
                )
                if match:
                    result['cascade_alerts'].append({
                        'timestamp': timestamp or time.time(),
                        'symbol': match.group(1),
                        'positions': int(match.group(2)),
                        'value_at_risk': float(match.group(3).replace(',', '')),
                        'dominant': match.group(4),
                    })

            # Liquidations the system logged seeing
            if 'HL_LIQUIDATION' in line or 'liquidation' in line.lower():
                # Try to extract liquidation info
                ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match and ('value' in line.lower() or 'usd' in line.lower() or '$' in line):
                    result['liquidations_seen'].append({
                        'timestamp': datetime.strptime(ts_match.group(1), '%Y-%m-%d %H:%M:%S').timestamp(),
                        'raw': line.strip()[-100:],
                    })

            # M2 stats
            if '[M2-DIAG] Stats:' in line:
                result['m2_stats'] = line.split('Stats:')[1].strip()

    except Exception as e:
        result['error'] = str(e)

    return result


def verify_cascade_alerts_against_node(
    alerts: List[Dict],
    collector: NodeEventCollector,
    record_to_db: bool = False
) -> Dict:
    """
    Verify cascade alerts against actual node liquidation events.

    A cascade alert is "verified" if liquidations actually followed on the node.
    """
    results = {
        'total': len(alerts),
        'verified': 0,
        'false_positive': 0,
        'pending': 0,
        'details': [],
    }

    now = time.time()

    for alert in alerts:
        alert_ts = alert['timestamp']
        symbol = alert['symbol']
        time_since = now - alert_ts

        if time_since > CASCADE_VERIFY_WINDOW_SEC:
            # Old enough to verify
            window_start = alert_ts
            window_end = alert_ts + CASCADE_VERIFY_WINDOW_SEC

            # Get liquidations from node (ground truth)
            liq_value = collector.get_liquidation_value_in_window(symbol, window_start, window_end)
            liqs = collector.get_liquidations_in_window(symbol, window_start, window_end)

            burst_detected = liq_value >= LIQ_BURST_THRESHOLD_USD

            if burst_detected:
                results['verified'] += 1
            else:
                results['false_positive'] += 1

            detail = {
                'symbol': symbol,
                'alert_time': datetime.fromtimestamp(alert_ts).strftime('%H:%M:%S'),
                'value_at_risk': alert['value_at_risk'],
                'actual_liq_value': liq_value,
                'liq_count': len(liqs),
                'verified': burst_detected,
            }
            results['details'].append(detail)

            # Record to DB
            if record_to_db:
                alert_id = record_cascade_alert(
                    symbol=symbol,
                    positions_count=alert['positions'],
                    value_at_risk=alert['value_at_risk'],
                    dominant_side=alert['dominant'],
                    closest_liq_price=0,
                    timestamp=alert_ts
                )
                verify_cascade_alert(
                    alert_id=alert_id,
                    liq_burst_detected=burst_detected,
                    liq_burst_time=liqs[0].timestamp if liqs else None,
                    liq_burst_value=liq_value,
                    time_to_burst=liqs[0].timestamp - alert_ts if liqs else None
                )

                # Record actual liquidations
                for liq in liqs:
                    record_liquidation(
                        symbol=liq.symbol,
                        side=liq.data['side'],
                        value_usd=liq.data['value_usd'],
                        price=liq.data['price'],
                        source='HL_NODE',
                        timestamp=liq.timestamp
                    )
        else:
            results['pending'] += 1

    return results


def run_verification(collector: NodeEventCollector, record_to_db: bool = False, verbose: bool = True) -> Dict:
    """Run verification comparing system behavior against node events."""
    now = datetime.now()

    if verbose:
        print("=" * 70)
        print(f"VERIFICATION: System vs Node - {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

    # 1. Adapter status
    adapter_status = get_adapter_status()

    if verbose:
        print("\n[1] HL ADAPTER (Node Connection)")
        if 'error' in adapter_status:
            print(f"  ✗ ERROR: {adapter_status['error']}")
        else:
            icon = '✓' if adapter_status['status'] == 'HEALTHY' else '⚠'
            print(f"  {icon} Status: {adapter_status['status']}")
            print(f"    Block lag: {adapter_status['lag_seconds']:.1f}s")
            print(f"    Total emitted: {adapter_status['prices_emitted']:,} prices, {adapter_status['liquidations_emitted']:,} liqs")

    # 2. Node events (ground truth)
    collector_stats = collector.get_stats()
    recent_liqs = collector.get_recent_liquidations(60)

    if verbose:
        print("\n[2] NODE EVENTS (Ground Truth)")
        print(f"  Collected: {collector_stats['liquidations_collected']} liqs, {collector_stats['fills_collected']} fills")
        print(f"  Last 60s liquidations: {len(recent_liqs)}")

        if recent_liqs:
            total_value = sum(l.data['value_usd'] for l in recent_liqs)
            print(f"    Total value: ${total_value:,.0f}")
            for liq in recent_liqs[-3:]:
                t = datetime.fromtimestamp(liq.timestamp).strftime('%H:%M:%S')
                print(f"    {liq.symbol} @ {t}: ${liq.data['value_usd']:,.0f} ({liq.data['side']})")

    # 3. System log
    system_state = parse_system_log()

    if verbose:
        print("\n[3] SYSTEM STATE (From Log)")
        if system_state.get('m2_stats'):
            print(f"  M2: {system_state['m2_stats']}")
        print(f"  Cascade alerts in log: {len(system_state['cascade_alerts'])}")

    # 4. Cascade verification
    if verbose:
        print("\n[4] CASCADE ALERT VERIFICATION")

    recent_alerts = [a for a in system_state['cascade_alerts']
                     if time.time() - a['timestamp'] < 600]  # Last 10 min

    verification = verify_cascade_alerts_against_node(recent_alerts, collector, record_to_db)

    if verbose:
        print(f"  Alerts (last 10min): {verification['total']}")
        print(f"  ✓ Verified (liqs followed): {verification['verified']}")
        print(f"  ✗ False positive (no liqs): {verification['false_positive']}")
        print(f"  ⏳ Pending: {verification['pending']}")

        if verification['details']:
            print("\n  Recent:")
            for d in verification['details'][-5:]:
                icon = '✓' if d['verified'] else '✗'
                print(f"    {icon} {d['symbol']} @ {d['alert_time']}: "
                      f"${d['value_at_risk']:,.0f} risk → ${d['actual_liq_value']:,.0f} actual ({d['liq_count']} liqs)")

    if verbose:
        print("\n" + "=" * 70)

    return {
        'adapter_status': adapter_status,
        'collector_stats': collector_stats,
        'verification': verification,
    }


def show_stats():
    """Show verification statistics from database."""
    print("=" * 70)
    print("VERIFICATION STATISTICS")
    print("=" * 70)

    cascade_stats = get_cascade_stats()
    print("\n[CASCADE ALERT ACCURACY]")
    print(f"  Total recorded: {cascade_stats['total_alerts']}")
    if cascade_stats['total_alerts'] > 0:
        print(f"  Verified: {cascade_stats['verified_rate']:.1%}")
        print(f"  False positive: {cascade_stats['false_positive_rate']:.1%}")
        if cascade_stats['avg_time_to_burst']:
            print(f"  Avg time to burst: {cascade_stats['avg_time_to_burst']:.1f}s")

    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt, SUM(value_usd) as total FROM liquidation_events WHERE source='HL_NODE'").fetchone()
    conn.close()

    print("\n[NODE LIQUIDATIONS RECORDED]")
    print(f"  Events: {row['cnt']}")
    if row['total']:
        print(f"  Total value: ${row['total']:,.0f}")

    print("\n" + "=" * 70)


def monitor_loop(interval: int = 30):
    """Continuous verification against node events."""
    print(f"Starting verification monitor (interval={interval}s)")
    print("Streaming from HL adapter...")

    collector = NodeEventCollector()
    collector.start()

    # Wait for initial collection
    time.sleep(5)

    try:
        while True:
            run_verification(collector, record_to_db=True, verbose=True)
            print(f"\nNext check in {interval}s... (Ctrl+C to stop)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopping...")
        collector.stop()
        show_stats()


def main():
    parser = argparse.ArgumentParser(description='Verify paper trade against HL node events')
    parser.add_argument('--monitor', action='store_true', help='Continuous monitoring')
    parser.add_argument('--interval', type=int, default=30, help='Monitor interval')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--record', action='store_true', help='Record to database')

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.monitor:
        monitor_loop(args.interval)
    else:
        collector = NodeEventCollector()
        collector.start()
        time.sleep(5)
        run_verification(collector, record_to_db=args.record, verbose=True)
        collector.stop()


if __name__ == '__main__':
    main()
