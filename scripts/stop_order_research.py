#!/usr/bin/env python3
"""
Stop Order Research - Analyze correlation between price movement and stop zones.

Hypothesis: Price tends to move toward clusters of stop orders before reversing.

Data collection:
1. Stream stop orders from node (trigger price, size, type)
2. Track price movements
3. Analyze: Does price reach stop clusters? How often? What happens after?
"""

import requests
import json
import time
import os
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import sqlite3

NODE_URL = "http://64.176.65.252:8080"

# Asset mapping
ASSETS = {
    0: "BTC", 1: "ETH", 5: "SOL", 12: "DOGE", 16: "XRP", 11: "ARB",
    6: "AVAX", 7: "BNB", 17: "LINK", 27: "AAVE", 46: "HYPE"
}

@dataclass
class StopOrder:
    timestamp: float
    coin: str
    trigger_price: float
    size: float
    side: str  # BUY or SELL
    tpsl: str  # 'sl' or 'tp'

@dataclass
class PricePoint:
    timestamp: float
    coin: str
    price: float

@dataclass
class StopZone:
    """A cluster of stops at a price level."""
    coin: str
    price_level: float
    total_size: float
    count: int
    tpsl: str
    created_at: float
    touched_at: Optional[float] = None
    price_after_touch: Optional[float] = None


class StopOrderCollector:
    """Collect stop orders from node for analysis."""

    def __init__(self, db_path: str = "stop_research.db"):
        self.db_path = db_path
        self.stops: List[StopOrder] = []
        self.prices: Dict[str, float] = {}
        self.price_history: Dict[str, List[PricePoint]] = defaultdict(list)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for persistent storage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stop_orders (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                coin TEXT,
                trigger_price REAL,
                size REAL,
                side TEXT,
                tpsl TEXT,
                price_at_placement REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                coin TEXT,
                price REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stop_touches (
                id INTEGER PRIMARY KEY,
                coin TEXT,
                stop_price REAL,
                stop_size REAL,
                tpsl TEXT,
                touched_at REAL,
                price_before REAL,
                price_after_1m REAL,
                price_after_5m REAL,
                reversal_pct REAL
            )
        """)

        conn.commit()
        conn.close()

    def fetch_current_prices(self) -> Dict[str, float]:
        """Get current prices from node."""
        try:
            resp = requests.get(f"{NODE_URL}/mids", timeout=5)
            if resp.status_code == 200:
                raw = resp.json()
                prices = {}
                for asset_id_str, price in raw.items():
                    asset_id = int(asset_id_str)
                    coin = ASSETS.get(asset_id, f"A{asset_id}")
                    prices[coin] = float(price)
                return prices
        except Exception as e:
            print(f"Error fetching prices: {e}")
        return {}

    def parse_stop_orders_from_blocks(self, block_data: str) -> List[StopOrder]:
        """Parse stop orders from block JSON data."""
        stops = []

        for line in block_data.split('\n'):
            if not line.strip().startswith('{'):
                continue
            try:
                d = json.loads(line)
                block_time = d.get('abci_block', {}).get('time', '')

                # Parse timestamp
                try:
                    ts = datetime.fromisoformat(block_time[:26]).timestamp()
                except:
                    ts = time.time()

                for bundle in d.get('abci_block', {}).get('signed_action_bundles', []):
                    if len(bundle) < 2:
                        continue
                    for sa in bundle[1].get('signed_actions', []):
                        action = sa.get('action', {})
                        if action.get('type') == 'order':
                            for order in action.get('orders', []):
                                t = order.get('t', {})
                                if 'trigger' in t:
                                    trigger = t['trigger']
                                    asset_id = order.get('a')
                                    coin = ASSETS.get(asset_id, f"A{asset_id}")

                                    stops.append(StopOrder(
                                        timestamp=ts,
                                        coin=coin,
                                        trigger_price=float(trigger.get('triggerPx', 0)),
                                        size=float(order.get('s', 0)),
                                        side='BUY' if order.get('b') else 'SELL',
                                        tpsl=trigger.get('tpsl', '?')
                                    ))
            except:
                pass

        return stops

    def find_stop_zones(self, coin: str, price_tolerance_pct: float = 0.5) -> List[Dict]:
        """Find clusters of stops near similar price levels."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get recent stops for this coin
        cursor.execute("""
            SELECT trigger_price, size, tpsl, timestamp
            FROM stop_orders
            WHERE coin = ? AND timestamp > ?
            ORDER BY trigger_price
        """, (coin, time.time() - 3600))  # Last hour

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return []

        # Cluster stops by price level
        zones = []
        current_zone = None

        for price, size, tpsl, ts in rows:
            if current_zone is None:
                current_zone = {
                    'price': price,
                    'total_size': size,
                    'count': 1,
                    'tpsl': tpsl,
                    'prices': [price]
                }
            else:
                # Check if within tolerance of zone
                zone_price = sum(current_zone['prices']) / len(current_zone['prices'])
                if abs(price - zone_price) / zone_price * 100 <= price_tolerance_pct:
                    current_zone['total_size'] += size
                    current_zone['count'] += 1
                    current_zone['prices'].append(price)
                else:
                    # Save current zone and start new one
                    if current_zone['count'] >= 2:  # Only save clusters
                        current_zone['avg_price'] = sum(current_zone['prices']) / len(current_zone['prices'])
                        zones.append(current_zone)
                    current_zone = {
                        'price': price,
                        'total_size': size,
                        'count': 1,
                        'tpsl': tpsl,
                        'prices': [price]
                    }

        # Don't forget last zone
        if current_zone and current_zone['count'] >= 2:
            current_zone['avg_price'] = sum(current_zone['prices']) / len(current_zone['prices'])
            zones.append(current_zone)

        return zones

    def analyze_stop_touches(self, coin: str) -> Dict:
        """Analyze what happens when price reaches stop zones."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                tpsl,
                COUNT(*) as count,
                AVG(reversal_pct) as avg_reversal,
                SUM(CASE WHEN reversal_pct > 0.5 THEN 1 ELSE 0 END) as reversals
            FROM stop_touches
            WHERE coin = ?
            GROUP BY tpsl
        """, (coin,))

        results = {}
        for row in cursor.fetchall():
            tpsl, count, avg_reversal, reversals = row
            results[tpsl] = {
                'touches': count,
                'avg_reversal_pct': avg_reversal or 0,
                'reversal_rate': (reversals or 0) / count if count > 0 else 0
            }

        conn.close()
        return results

    def save_stop(self, stop: StopOrder, current_price: float):
        """Save a stop order to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO stop_orders (timestamp, coin, trigger_price, size, side, tpsl, price_at_placement)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (stop.timestamp, stop.coin, stop.trigger_price, stop.size, stop.side, stop.tpsl, current_price))
        conn.commit()
        conn.close()

    def save_price(self, coin: str, price: float):
        """Save price point to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO price_history (timestamp, coin, price)
            VALUES (?, ?, ?)
        """, (time.time(), coin, price))
        conn.commit()
        conn.close()


def research_correlation():
    """Main research function - collect data and analyze correlations."""
    collector = StopOrderCollector()

    print("=== STOP ORDER RESEARCH ===")
    print("Collecting data to analyze price-stop correlations...\n")

    # Get current prices
    prices = collector.fetch_current_prices()
    print(f"Current prices: BTC=${prices.get('BTC', 0):,.0f}, ETH=${prices.get('ETH', 0):,.0f}")

    # Find existing stop zones
    print("\n=== STOP ZONES (from recent data) ===")
    for coin in ['BTC', 'ETH', 'SOL']:
        zones = collector.find_stop_zones(coin)
        if zones:
            current = prices.get(coin, 0)
            print(f"\n{coin} (current: ${current:,.2f}):")
            for z in sorted(zones, key=lambda x: -x['total_size'])[:5]:
                dist = ((z['avg_price'] - current) / current * 100) if current else 0
                print(f"  ${z['avg_price']:,.2f} ({dist:+.1f}%): {z['count']} stops, {z['total_size']:.2f} size, type={z['tpsl']}")

    # Show historical analysis if data exists
    print("\n=== HISTORICAL ANALYSIS ===")
    for coin in ['BTC', 'ETH']:
        analysis = collector.analyze_stop_touches(coin)
        if analysis:
            print(f"\n{coin}:")
            for tpsl, data in analysis.items():
                label = "Stop-Loss" if tpsl == 'sl' else "Take-Profit"
                print(f"  {label}: {data['touches']} touches, {data['avg_reversal_pct']:.2f}% avg reversal, {data['reversal_rate']*100:.0f}% reversal rate")


def live_collection(duration_minutes: int = 60):
    """Collect live stop order data for specified duration."""
    import subprocess

    collector = StopOrderCollector()
    print(f"Collecting stop order data for {duration_minutes} minutes...")

    start_time = time.time()
    end_time = start_time + duration_minutes * 60

    stops_collected = 0
    prices_collected = 0

    while time.time() < end_time:
        # Get current prices
        prices = collector.fetch_current_prices()
        for coin, price in prices.items():
            if coin in ASSETS.values():
                collector.save_price(coin, price)
                prices_collected += 1

        # Try to get recent blocks from node (this part would need SSH or local node)
        # For now, just track prices

        elapsed = (time.time() - start_time) / 60
        remaining = duration_minutes - elapsed
        print(f"\rCollected {prices_collected} price points, {stops_collected} stops. {remaining:.1f} min remaining...", end='')

        time.sleep(1)  # Sample every second

    print(f"\n\nCollection complete!")
    print(f"Total: {prices_collected} price points, {stops_collected} stop orders")

    # Run analysis
    research_correlation()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "collect":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        live_collection(duration)
    else:
        research_correlation()
