#!/usr/bin/env python3
"""
Verify paper trade system against real market events from HL node.

Verification approach:
1. Continuous liquidation stream from HL adapter - persisted to DB
2. Parse paper_trade.log for cascade alerts
3. Verify alerts against liquidations that occurred in their time window

Key fix: Continuous streaming with DB persistence, not short sampling windows.

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
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, List, Set
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
class LiquidationEvent:
    """Liquidation event from HL node."""
    timestamp: float
    symbol: str
    side: str
    price: float
    size: float
    value_usd: float
    liquidated_account: str = ""


class PersistentLiquidationCollector:
    """
    Continuous liquidation collector with DB persistence.

    - Opens StreamLiquidations once, keeps it open
    - Writes each event to DB immediately (persistence)
    - Maintains rolling buffer for fast in-memory queries
    - Handles gRPC disconnect/reconnect
    """

    def __init__(self, buffer_size: int = 10000):
        self._buffer: deque = deque(maxlen=buffer_size)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._total_received = 0
        self._last_event_time: Optional[float] = None
        self._reconnect_count = 0

    def start(self):
        """Start continuous liquidation streaming."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()
        print(f"[COLLECTOR] Started continuous liquidation stream")

    def stop(self):
        """Stop streaming."""
        self._running = False
        print(f"[COLLECTOR] Stopped. Total received: {self._total_received}, reconnects: {self._reconnect_count}")

    def _get_stub(self):
        """Get gRPC stub."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hl-adapter'))
        import grpc
        import events_pb2
        import events_pb2_grpc

        channel = grpc.insecure_channel('localhost:50051')
        stub = events_pb2_grpc.HLNodeAdapterStub(channel)
        return stub, events_pb2

    def _stream_loop(self):
        """Main streaming loop with reconnect handling."""
        while self._running:
            try:
                stub, pb2 = self._get_stub()
                request = pb2.StreamRequest(symbols=SYMBOLS)

                print(f"[COLLECTOR] Connected to gRPC stream")

                for event in stub.StreamLiquidations(request):
                    if not self._running:
                        break

                    # Parse event
                    liq = LiquidationEvent(
                        timestamp=event.timestamp_ms / 1000.0,
                        symbol=event.symbol,
                        side=event.side,
                        price=float(event.price),
                        size=float(event.size),
                        value_usd=float(event.value_usd),
                        liquidated_account=getattr(event, 'liquidated_account', ''),
                    )

                    # Add to buffer
                    with self._lock:
                        self._buffer.append(liq)
                        self._total_received += 1
                        self._last_event_time = liq.timestamp

                    # Persist to DB immediately
                    try:
                        record_liquidation(
                            symbol=liq.symbol,
                            side=liq.side,
                            value_usd=liq.value_usd,
                            price=liq.price,
                            source='HL_NODE',
                            timestamp=liq.timestamp
                        )
                    except Exception as e:
                        # Don't crash on DB errors
                        pass

                    # Log significant liquidations
                    if liq.value_usd >= 50000:
                        print(f"[COLLECTOR] {liq.symbol} ${liq.value_usd:,.0f} @ {liq.price:.2f} ({liq.side})")

            except Exception as e:
                if self._running:
                    self._reconnect_count += 1
                    print(f"[COLLECTOR] Stream error, reconnecting in 2s... ({e})")
                    time.sleep(2)

    def get_liquidations_in_window(self, symbol: str, start_ts: float, end_ts: float) -> List[LiquidationEvent]:
        """Get liquidations for symbol in time window from buffer."""
        with self._lock:
            return [l for l in self._buffer
                    if l.symbol == symbol and start_ts <= l.timestamp <= end_ts]

    def get_liquidation_value_in_window(self, symbol: str, start_ts: float, end_ts: float) -> float:
        """Get total liquidation value in window."""
        liqs = self.get_liquidations_in_window(symbol, start_ts, end_ts)
        return sum(l.value_usd for l in liqs)

    def get_all_liquidations_in_window(self, start_ts: float, end_ts: float) -> List[LiquidationEvent]:
        """Get all liquidations in time window (any symbol)."""
        with self._lock:
            return [l for l in self._buffer if start_ts <= l.timestamp <= end_ts]

    def get_recent(self, seconds: float = 60) -> List[LiquidationEvent]:
        """Get liquidations in last N seconds."""
        cutoff = time.time() - seconds
        with self._lock:
            return [l for l in self._buffer if l.timestamp >= cutoff]

    def get_stats(self) -> Dict:
        """Get collector statistics."""
        with self._lock:
            return {
                'buffer_size': len(self._buffer),
                'total_received': self._total_received,
                'last_event_time': self._last_event_time,
                'reconnect_count': self._reconnect_count,
            }


# Global collector instance - persists across verification cycles
_collector: Optional[PersistentLiquidationCollector] = None


def get_collector() -> PersistentLiquidationCollector:
    """Get or create the persistent collector."""
    global _collector
    if _collector is None:
        _collector = PersistentLiquidationCollector()
    return _collector


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


def parse_cascade_alerts(log_path: str = '/tmp/paper_trade.log') -> List[Dict]:
    """Parse cascade alerts from paper trade log."""
    alerts = []

    try:
        with open(log_path, 'r') as f:
            f.seek(0, 2)
            file_size = f.tell()
            read_size = min(1000000, file_size)
            f.seek(max(0, file_size - read_size))
            content = f.read()

        for line in content.split('\n'):
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
                    alerts.append({
                        'timestamp': timestamp or time.time(),
                        'symbol': match.group(1),
                        'positions': int(match.group(2)),
                        'value_at_risk': float(match.group(3).replace(',', '')),
                        'dominant': match.group(4),
                    })
    except Exception:
        pass

    return alerts


def parse_m2_stats(log_path: str = '/tmp/paper_trade.log') -> Optional[str]:
    """Parse latest M2 stats from log."""
    try:
        with open(log_path, 'r') as f:
            f.seek(0, 2)
            file_size = f.tell()
            read_size = min(500000, file_size)
            f.seek(max(0, file_size - read_size))
            content = f.read()

        for line in reversed(content.split('\n')):
            if '[M2-DIAG] Stats:' in line:
                return line.split('Stats:')[1].strip()
    except:
        pass
    return None


# Track which alerts have been verified (by timestamp+symbol key)
_verified_alerts: Set[str] = set()


def _alert_key(alert: Dict) -> str:
    """Generate unique key for an alert."""
    return f"{alert['symbol']}_{alert['timestamp']:.0f}"


def verify_alerts_against_liquidations(
    alerts: List[Dict],
    collector: PersistentLiquidationCollector,
    record_to_db: bool = True
) -> Dict:
    """
    Verify cascade alerts against actual liquidation events.

    Only verifies alerts that:
    1. Are older than CASCADE_VERIFY_WINDOW_SEC (window has closed)
    2. Haven't been verified before
    """
    global _verified_alerts

    results = {
        'total': len(alerts),
        'verified': 0,
        'false_positive': 0,
        'pending': 0,
        'newly_verified': 0,
        'details': [],
    }

    now = time.time()

    for alert in alerts:
        alert_ts = alert['timestamp']
        symbol = alert['symbol']
        key = _alert_key(alert)
        time_since = now - alert_ts

        # Skip already verified
        if key in _verified_alerts:
            continue

        if time_since > CASCADE_VERIFY_WINDOW_SEC:
            # Window has closed - can verify now
            window_start = alert_ts
            window_end = alert_ts + CASCADE_VERIFY_WINDOW_SEC

            # Query liquidations from collector buffer
            liq_value = collector.get_liquidation_value_in_window(symbol, window_start, window_end)
            liqs = collector.get_liquidations_in_window(symbol, window_start, window_end)

            # Also query from DB (in case buffer rolled over)
            db_liqs = get_liquidations_in_window(symbol, window_start, window_end)
            db_value = sum(l.get('value_usd', 0) for l in db_liqs) if db_liqs else 0

            # Use max of buffer and DB
            total_liq_value = max(liq_value, db_value)
            total_liq_count = max(len(liqs), len(db_liqs) if db_liqs else 0)

            burst_detected = total_liq_value >= LIQ_BURST_THRESHOLD_USD

            if burst_detected:
                results['verified'] += 1
            else:
                results['false_positive'] += 1

            results['newly_verified'] += 1
            _verified_alerts.add(key)

            detail = {
                'symbol': symbol,
                'alert_time': datetime.fromtimestamp(alert_ts).strftime('%H:%M:%S'),
                'value_at_risk': alert['value_at_risk'],
                'actual_liq_value': total_liq_value,
                'liq_count': total_liq_count,
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
                    liq_burst_value=total_liq_value,
                    time_to_burst=liqs[0].timestamp - alert_ts if liqs else None
                )
        else:
            results['pending'] += 1

    return results


def run_verification(collector: PersistentLiquidationCollector, verbose: bool = True) -> Dict:
    """Run verification cycle."""
    now = datetime.now()

    if verbose:
        print("=" * 70)
        print(f"VERIFICATION: System vs Node - {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

    # 1. Adapter status
    adapter_status = get_adapter_status()

    if verbose:
        print("\n[1] HL ADAPTER")
        if 'error' in adapter_status:
            print(f"  ✗ ERROR: {adapter_status['error']}")
        else:
            icon = '✓' if adapter_status['status'] == 'HEALTHY' else '⚠'
            print(f"  {icon} Status: {adapter_status['status']}")
            print(f"    Block lag: {adapter_status['lag_seconds']:.1f}s")
            print(f"    Total emitted: {adapter_status['liquidations_emitted']:,} liqs")

    # 2. Collector stats
    collector_stats = collector.get_stats()
    recent_liqs = collector.get_recent(300)  # Last 5 min

    if verbose:
        print("\n[2] LIQUIDATION COLLECTOR (Continuous)")
        print(f"  Buffer: {collector_stats['buffer_size']} events")
        print(f"  Total received: {collector_stats['total_received']}")
        print(f"  Reconnects: {collector_stats['reconnect_count']}")
        print(f"  Last 5min: {len(recent_liqs)} liquidations")

        if recent_liqs:
            total_value = sum(l.value_usd for l in recent_liqs)
            print(f"    Total value: ${total_value:,.0f}")
            for liq in recent_liqs[-3:]:
                t = datetime.fromtimestamp(liq.timestamp).strftime('%H:%M:%S')
                print(f"    {liq.symbol} @ {t}: ${liq.value_usd:,.0f} ({liq.side})")

    # 3. M2 stats
    m2_stats = parse_m2_stats()
    if verbose:
        print("\n[3] SYSTEM STATE")
        if m2_stats:
            print(f"  M2: {m2_stats}")

    # 4. Cascade verification
    if verbose:
        print("\n[4] CASCADE ALERT VERIFICATION")

    alerts = parse_cascade_alerts()
    recent_alerts = [a for a in alerts if time.time() - a['timestamp'] < 600]  # Last 10 min

    verification = verify_alerts_against_liquidations(recent_alerts, collector)

    if verbose:
        print(f"  Alerts (last 10min): {verification['total']}")
        print(f"  ✓ Verified (liqs followed): {verification['verified']}")
        print(f"  ✗ False positive (no liqs): {verification['false_positive']}")
        print(f"  ⏳ Pending (window open): {verification['pending']}")
        print(f"  📝 Newly verified this cycle: {verification['newly_verified']}")

        if verification['details']:
            print("\n  Recent verifications:")
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
    """Continuous verification with persistent liquidation collection."""
    print(f"Starting verification monitor (interval={interval}s)")
    print("Opening continuous liquidation stream...")

    collector = get_collector()
    collector.start()

    # Wait for stream to connect
    time.sleep(3)

    try:
        while True:
            run_verification(collector, verbose=True)
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

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.monitor:
        monitor_loop(args.interval)
    else:
        # Single run - still use persistent collector
        collector = get_collector()
        collector.start()
        time.sleep(5)
        run_verification(collector, verbose=True)
        collector.stop()


if __name__ == '__main__':
    main()
