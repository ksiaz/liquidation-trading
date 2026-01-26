#!/usr/bin/env python3
"""
Manipulation Detection Research

Detect potential malicious trading patterns from node data:
1. Stop hunting - pushing price to hit stop clusters then reversing
2. Spoofing - placing and quickly canceling orders to fake liquidity
3. Layering - stacking orders to manipulate perceived depth
4. Wash trading - trading against yourself
5. Coordinated trading - multiple wallets acting together

Data source: Hyperliquid node replica_cmds (order flow)
"""

import json
import os
import glob
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
from datetime import datetime
import time

# Asset mapping
ASSETS = {
    0: "BTC", 1: "ETH", 5: "SOL", 12: "DOGE", 16: "XRP", 11: "ARB",
    6: "AVAX", 7: "BNB", 17: "LINK", 27: "AAVE", 46: "HYPE"
}


@dataclass
class OrderEvent:
    timestamp: float
    wallet: str
    asset: int
    coin: str
    side: str  # BUY or SELL
    price: float
    size: float
    order_type: str  # 'limit', 'trigger', 'cancel'
    cloid: str = ""  # Client order ID for tracking
    is_reduce: bool = False


class ManipulationDetector:
    """Detect manipulation patterns in order flow."""

    def __init__(self):
        self.orders: List[OrderEvent] = []
        self.cancels: Dict[str, OrderEvent] = {}  # cloid -> cancel event
        self.wallet_activity: Dict[str, List[OrderEvent]] = defaultdict(list)
        self.price_by_asset: Dict[int, List[Tuple[float, float]]] = defaultdict(list)  # asset -> [(ts, price)]

        # Detection results
        self.spoofing_alerts: List[Dict] = []
        self.stop_hunt_alerts: List[Dict] = []
        self.wash_trade_alerts: List[Dict] = []
        self.coordinated_alerts: List[Dict] = []

    def parse_block_file(self, filepath: str) -> List[OrderEvent]:
        """Parse order events from a block file."""
        events = []

        try:
            with open(filepath, 'r') as f:
                for line in f:
                    if not line.strip().startswith('{'):
                        continue

                    try:
                        d = json.loads(line)
                        ab = d.get('abci_block', {})
                        block_time = ab.get('time', '')

                        # Parse timestamp
                        try:
                            ts = datetime.fromisoformat(block_time[:26]).timestamp()
                        except:
                            ts = time.time()

                        for bundle in ab.get('signed_action_bundles', []):
                            if len(bundle) < 2:
                                continue

                            wallet = bundle[0]

                            for sa in bundle[1].get('signed_actions', []):
                                action = sa.get('action', {})
                                atype = action.get('type', '')

                                if atype == 'order':
                                    for order in action.get('orders', []):
                                        t = order.get('t', {})
                                        order_type = list(t.keys())[0] if t else 'unknown'

                                        events.append(OrderEvent(
                                            timestamp=ts,
                                            wallet=wallet,
                                            asset=order.get('a', 0),
                                            coin=ASSETS.get(order.get('a'), f"A{order.get('a')}"),
                                            side='BUY' if order.get('b') else 'SELL',
                                            price=float(order.get('p', 0)),
                                            size=float(order.get('s', 0)),
                                            order_type=order_type,
                                            cloid=order.get('c', ''),
                                            is_reduce=order.get('r', False)
                                        ))

                                        # Track price
                                        if order.get('p'):
                                            self.price_by_asset[order.get('a')].append(
                                                (ts, float(order.get('p')))
                                            )

                                elif atype == 'cancel':
                                    # Track cancellation
                                    cloid = action.get('a', {}).get('cloid', '')
                                    if cloid:
                                        events.append(OrderEvent(
                                            timestamp=ts,
                                            wallet=wallet,
                                            asset=action.get('a', {}).get('asset', 0),
                                            coin=ASSETS.get(action.get('a', {}).get('asset'), '?'),
                                            side='CANCEL',
                                            price=0,
                                            size=0,
                                            order_type='cancel',
                                            cloid=cloid
                                        ))

                                elif atype == 'cancelByCloid':
                                    # Another cancel format
                                    for cancel in action.get('cancels', []):
                                        cloid = cancel.get('cloid', '')
                                        if cloid:
                                            events.append(OrderEvent(
                                                timestamp=ts,
                                                wallet=wallet,
                                                asset=cancel.get('asset', 0),
                                                coin=ASSETS.get(cancel.get('asset'), '?'),
                                                side='CANCEL',
                                                price=0,
                                                size=0,
                                                order_type='cancel',
                                                cloid=cloid
                                            ))
                    except Exception as e:
                        pass

        except Exception as e:
            print(f"Error parsing {filepath}: {e}")

        return events

    def detect_spoofing(self, time_window_ms: float = 5000) -> List[Dict]:
        """
        Detect spoofing: orders placed and canceled within short time window.

        Pattern:
        - Large order placed
        - Same order canceled within milliseconds
        - Intent: fake liquidity to influence other traders
        """
        alerts = []

        # Group by wallet
        wallet_orders = defaultdict(list)
        wallet_cancels = defaultdict(list)

        for event in self.orders:
            if event.order_type == 'cancel':
                wallet_cancels[event.wallet].append(event)
            elif event.order_type == 'limit':
                wallet_orders[event.wallet].append(event)

        # Find orders that were quickly canceled
        for wallet, orders in wallet_orders.items():
            cancels = wallet_cancels.get(wallet, [])

            for order in orders:
                if not order.cloid:
                    continue

                # Find matching cancel
                for cancel in cancels:
                    if cancel.cloid == order.cloid:
                        time_diff_ms = (cancel.timestamp - order.timestamp) * 1000

                        if 0 < time_diff_ms < time_window_ms:
                            alerts.append({
                                'type': 'SPOOFING',
                                'wallet': wallet,
                                'coin': order.coin,
                                'side': order.side,
                                'price': order.price,
                                'size': order.size,
                                'lifetime_ms': time_diff_ms,
                                'timestamp': order.timestamp
                            })
                        break

        self.spoofing_alerts = alerts
        return alerts

    def detect_layering(self, min_orders: int = 5, time_window_s: float = 2.0) -> List[Dict]:
        """
        Detect layering: multiple orders stacked at different prices, then canceled.

        Pattern:
        - Wallet places many orders at different price levels
        - Orders canceled together shortly after
        - Intent: create illusion of depth
        """
        alerts = []

        # Group orders by wallet and time window
        wallet_windows = defaultdict(list)

        for event in self.orders:
            if event.order_type == 'limit':
                # Find time window bucket
                bucket = int(event.timestamp / time_window_s)
                key = (event.wallet, event.asset, bucket)
                wallet_windows[key].append(event)

        # Find windows with many orders
        for (wallet, asset, bucket), orders in wallet_windows.items():
            if len(orders) >= min_orders:
                # Check if mostly same side
                buy_count = sum(1 for o in orders if o.side == 'BUY')
                sell_count = len(orders) - buy_count

                if buy_count >= min_orders or sell_count >= min_orders:
                    # Check if prices are layered (different levels)
                    prices = sorted(set(o.price for o in orders))
                    if len(prices) >= 3:  # At least 3 different price levels
                        alerts.append({
                            'type': 'LAYERING',
                            'wallet': wallet,
                            'coin': orders[0].coin,
                            'side': 'BUY' if buy_count > sell_count else 'SELL',
                            'order_count': len(orders),
                            'price_levels': len(prices),
                            'price_range': f"${min(prices):,.2f} - ${max(prices):,.2f}",
                            'total_size': sum(o.size for o in orders),
                            'timestamp': orders[0].timestamp
                        })

        return alerts

    def detect_wash_trading(self) -> List[Dict]:
        """
        Detect wash trading: same wallet on both sides of a trade.

        Pattern:
        - Wallet places buy and sell orders at same price
        - Orders likely to match against each other
        """
        alerts = []

        # Group by wallet, asset, and approximate time
        wallet_pairs = defaultdict(lambda: {'buys': [], 'sells': []})

        for event in self.orders:
            if event.order_type != 'limit':
                continue

            bucket = int(event.timestamp / 60)  # 1-minute buckets
            key = (event.wallet, event.asset, bucket)

            if event.side == 'BUY':
                wallet_pairs[key]['buys'].append(event)
            else:
                wallet_pairs[key]['sells'].append(event)

        # Find wallets with both buys and sells
        for (wallet, asset, bucket), sides in wallet_pairs.items():
            buys = sides['buys']
            sells = sides['sells']

            if buys and sells:
                # Check for overlapping prices
                buy_prices = set(round(o.price, 4) for o in buys)
                sell_prices = set(round(o.price, 4) for o in sells)
                overlap = buy_prices & sell_prices

                if overlap:
                    alerts.append({
                        'type': 'WASH_TRADING',
                        'wallet': wallet,
                        'coin': buys[0].coin,
                        'overlapping_prices': len(overlap),
                        'buy_orders': len(buys),
                        'sell_orders': len(sells),
                        'timestamp': buys[0].timestamp
                    })

        self.wash_trade_alerts = alerts
        return alerts

    def detect_coordinated_trading(self, time_window_s: float = 1.0) -> List[Dict]:
        """
        Detect coordinated trading: multiple wallets acting together.

        Pattern:
        - Multiple different wallets place similar orders within short time
        - Same asset, same direction, similar timing
        """
        alerts = []

        # Group by asset, side, and time bucket
        action_groups = defaultdict(list)

        for event in self.orders:
            if event.order_type != 'limit':
                continue

            bucket = int(event.timestamp / time_window_s)
            key = (event.asset, event.side, bucket)
            action_groups[key].append(event)

        # Find groups with multiple wallets
        for (asset, side, bucket), events in action_groups.items():
            wallets = set(e.wallet for e in events)

            if len(wallets) >= 3:  # At least 3 different wallets
                total_size = sum(e.size for e in events)
                avg_price = sum(e.price for e in events) / len(events)

                alerts.append({
                    'type': 'COORDINATED',
                    'coin': events[0].coin,
                    'side': side,
                    'wallet_count': len(wallets),
                    'order_count': len(events),
                    'total_size': total_size,
                    'avg_price': avg_price,
                    'timestamp': events[0].timestamp
                })

        self.coordinated_alerts = alerts
        return alerts

    def analyze_stop_hunting(self, price_threshold_pct: float = 0.5) -> List[Dict]:
        """
        Detect stop hunting: large orders pushing price to stop clusters.

        Pattern:
        - Large order in one direction
        - Price moves to hit stop levels
        - Quick reversal after stops triggered
        """
        alerts = []

        # Find large orders followed by price reversal
        for event in self.orders:
            if event.order_type != 'limit' or event.size < 1.0:
                continue

            # Get price movement after this order
            later_prices = [
                (ts, px) for ts, px in self.price_by_asset.get(event.asset, [])
                if ts > event.timestamp and ts < event.timestamp + 60
            ]

            if len(later_prices) < 5:
                continue

            # Calculate price movement
            start_price = event.price
            max_price = max(px for _, px in later_prices)
            min_price = min(px for _, px in later_prices)
            end_price = later_prices[-1][1]

            if event.side == 'BUY':
                # Look for spike up then reversal down
                spike_pct = (max_price - start_price) / start_price * 100
                reversal_pct = (max_price - end_price) / max_price * 100

                if spike_pct > price_threshold_pct and reversal_pct > spike_pct * 0.5:
                    alerts.append({
                        'type': 'STOP_HUNT',
                        'wallet': event.wallet,
                        'coin': event.coin,
                        'direction': 'UP',
                        'trigger_size': event.size,
                        'spike_pct': spike_pct,
                        'reversal_pct': reversal_pct,
                        'timestamp': event.timestamp
                    })

            else:  # SELL
                # Look for spike down then reversal up
                if min_price == 0:
                    continue
                spike_pct = (start_price - min_price) / start_price * 100
                reversal_pct = (end_price - min_price) / min_price * 100

                if spike_pct > price_threshold_pct and reversal_pct > spike_pct * 0.5:
                    alerts.append({
                        'type': 'STOP_HUNT',
                        'wallet': event.wallet,
                        'coin': event.coin,
                        'direction': 'DOWN',
                        'trigger_size': event.size,
                        'spike_pct': spike_pct,
                        'reversal_pct': reversal_pct,
                        'timestamp': event.timestamp
                    })

        self.stop_hunt_alerts = alerts
        return alerts

    def run_all_detections(self):
        """Run all manipulation detection algorithms."""
        print("\n=== MANIPULATION DETECTION RESULTS ===\n")

        # Spoofing
        spoofing = self.detect_spoofing()
        print(f"Spoofing alerts: {len(spoofing)}")
        for alert in spoofing[:5]:
            print(f"  {alert['coin']} {alert['side']} ${alert['price']:,.2f} x{alert['size']:.2f} - lived {alert['lifetime_ms']:.0f}ms")

        # Layering
        layering = self.detect_layering()
        print(f"\nLayering alerts: {len(layering)}")
        for alert in layering[:5]:
            print(f"  {alert['wallet'][:12]}... {alert['coin']} {alert['side']} - {alert['order_count']} orders across {alert['price_levels']} levels")

        # Wash trading
        wash = self.detect_wash_trading()
        print(f"\nWash trading alerts: {len(wash)}")
        for alert in wash[:5]:
            print(f"  {alert['wallet'][:12]}... {alert['coin']} - {alert['overlapping_prices']} overlapping prices")

        # Coordinated trading
        coordinated = self.detect_coordinated_trading()
        print(f"\nCoordinated trading alerts: {len(coordinated)}")
        for alert in coordinated[:5]:
            print(f"  {alert['coin']} {alert['side']} - {alert['wallet_count']} wallets, {alert['order_count']} orders")

        # Stop hunting
        stop_hunt = self.analyze_stop_hunting()
        print(f"\nStop hunting alerts: {len(stop_hunt)}")
        for alert in stop_hunt[:5]:
            print(f"  {alert['wallet'][:12]}... {alert['coin']} {alert['direction']} - spike {alert['spike_pct']:.2f}%, reversal {alert['reversal_pct']:.2f}%")

        return {
            'spoofing': len(spoofing),
            'layering': len(layering),
            'wash_trading': len(wash),
            'coordinated': len(coordinated),
            'stop_hunting': len(stop_hunt)
        }


def analyze_from_node(ssh_host: str = "root@64.176.65.252"):
    """Analyze manipulation patterns from node data."""
    import subprocess

    print("Fetching block data from node...")

    # Get recent block files
    cmd = f"ssh {ssh_host} 'cat $(ls -t ~/hl/data/replica_cmds/*/2*/* | head -3)'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error fetching data: {result.stderr}")
        return

    detector = ManipulationDetector()

    # Parse the block data
    for line in result.stdout.split('\n'):
        events = detector.parse_block_file_line(line)
        detector.orders.extend(events)

    print(f"Parsed {len(detector.orders)} order events")

    # Run detections
    detector.run_all_detections()


if __name__ == "__main__":
    # For testing, create detector and show capabilities
    print("=== MANIPULATION DETECTOR ===")
    print("\nCapabilities:")
    print("  1. Spoofing detection (orders quickly canceled)")
    print("  2. Layering detection (stacked orders at multiple levels)")
    print("  3. Wash trading detection (same wallet both sides)")
    print("  4. Coordinated trading detection (multiple wallets acting together)")
    print("  5. Stop hunting detection (price spikes to hit stops then reverses)")
    print("\nRun with: python manipulation_detector.py")
    print("\nNote: Requires SSH access to node for live data analysis")
