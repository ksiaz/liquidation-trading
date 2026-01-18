"""
Liquidation Trading System - Comprehensive Dashboard

Architecture:
1. Initializes ObservationSystem (M1-M5 Sealed).
2. Starts CollectorService (Runtime Driver).
3. Polls ObservationSystem for State.
4. Renders comprehensive dashboard with:
   - Price ticker for all symbols
   - Liquidation proximity table (sorted by $ value)
   - Cascade state panel
   - Positions & P&L tracking
   - Order book depth visualization
   - Trade history from database
"""

import sys
import os

# Fix path to include project root FIRST
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Configure temp directories to use D drive (must be early, before other imports)
import runtime.env_setup  # noqa: F401

import asyncio
import threading
import time
import sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                              QLabel, QHBoxLayout, QFrame, QStackedWidget,
                              QGridLayout, QGroupBox, QScrollArea, QSplitter,
                              QTableWidget, QTableWidgetItem, QHeaderView,
                              QAbstractItemView, QPushButton, QTabWidget, QLineEdit)
from PySide6.QtCore import QTimer, Slot, Qt, QMargins, QDateTime
from PySide6.QtGui import QFont, QColor, QPen, QBrush
from PySide6.QtCharts import (QChart, QChartView, QCandlestickSeries, QCandlestickSet,
                              QLineSeries, QDateTimeAxis, QValueAxis, QScatterSeries)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Signal

from observation import ObservationSystem, ObservationSnapshot
from observation.types import ObservationStatus, SystemHaltedException
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS

# Live position tracker (new clean implementation)
from runtime.hyperliquid.live_tracker import LiveTrackerSync, Position, DEFAULT_WHALES

# WebSocket-based real-time position tracker (sub-50ms latency)
try:
    from runtime.hyperliquid.ws_position_tracker import (
        HybridPositionTracker, WSPositionTracker, TrackedPosition, DangerSignal
    )
    from runtime.hyperliquid.shared_state import get_shared_state, PositionSnapshot
    HAS_WS_TRACKER = True
except ImportError as e:
    print(f"[WARNING] WebSocket tracker not available: {e}")
    HAS_WS_TRACKER = False
    HybridPositionTracker = None
    get_shared_state = None

# Fade executor import (optional - only used if enabled)
try:
    from runtime.hyperliquid.liquidation_fade import LiquidationFadeExecutor, FadeConfig
    HAS_FADE_EXECUTOR = True
except ImportError:
    HAS_FADE_EXECUTOR = False
    LiquidationFadeExecutor = None
    FadeConfig = None


# ==============================================================================
# Constants
# ==============================================================================

DB_PATH = "D:/liquidation-trading/logs/execution.db"
HL_INDEXED_DB_PATH = "D:/liquidation-trading/indexed_wallets.db"

# Staleness threshold - positions older than this are considered stale for display
POSITION_STALENESS_SECONDS = 180  # 3 minutes - accuracy over stability
# Hard delete threshold - positions older than this are permanently removed
POSITION_DELETE_SECONDS = 300  # 5 minutes - don't keep zombie data


def get_indexed_db_connection(timeout: float = 5.0) -> sqlite3.Connection:
    """Get a connection to the indexed wallets database with WAL mode."""
    conn = sqlite3.connect(HL_INDEXED_DB_PATH, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


# ==============================================================================
# Live API Data Fetch (bypasses database for real-time monitoring)
# ==============================================================================

HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"

# Cache for live data to avoid hammering API
_live_positions_cache = {
    'data': [],
    'mids': {},
    'timestamp': 0,
    'wallets': set()
}

def fetch_live_positions_near_liq(
    max_distance_pct: float = 5.0,
    min_value: float = 10000,
    cache_ttl: float = 2.0
) -> List[Dict]:
    """
    Fetch LIVE position data directly from Hyperliquid API.

    Bypasses database for real-time monitoring of positions near liquidation.
    Uses short-lived cache to avoid rate limiting.

    Args:
        max_distance_pct: Maximum distance to liquidation to include
        min_value: Minimum position value
        cache_ttl: Cache time-to-live in seconds

    Returns:
        List of position dicts with live distance calculations
    """
    global _live_positions_cache

    now = time.time()

    # Return cached data if fresh enough
    if now - _live_positions_cache['timestamp'] < cache_ttl and _live_positions_cache['data']:
        return _live_positions_cache['data']

    try:
        # Step 1: Get wallets to check from database (just addresses, fast query)
        if not os.path.exists(HL_INDEXED_DB_PATH):
            return []

        conn = get_indexed_db_connection(timeout=2.0)
        cursor = conn.execute("""
            SELECT DISTINCT wallet_address, coin, liquidation_price, side
            FROM positions
            WHERE distance_to_liq_pct > 0 AND distance_to_liq_pct < ?
              AND position_value >= ?
            ORDER BY distance_to_liq_pct ASC
            LIMIT 100
        """, (max_distance_pct * 2, min_value / 2))  # Wider filter, we'll recalculate

        db_positions = list(cursor.fetchall())
        wallets_to_check = set(row['wallet_address'] for row in db_positions)
        conn.close()

        if not wallets_to_check:
            _live_positions_cache['data'] = []
            _live_positions_cache['timestamp'] = now
            return []

        # Step 2: Get all mid prices (single API call)
        mids_resp = requests.post(
            HYPERLIQUID_API,
            json={'type': 'allMids'},
            timeout=3
        )
        if mids_resp.status_code != 200:
            return _live_positions_cache.get('data', [])

        mids = {k: float(v) for k, v in mids_resp.json().items()}
        _live_positions_cache['mids'] = mids

        # Step 3: Fetch live position data for each wallet
        live_positions = []

        for wallet in list(wallets_to_check)[:50]:  # Limit to 50 wallets (better coverage)
            try:
                resp = requests.post(
                    HYPERLIQUID_API,
                    json={'type': 'clearinghouseState', 'user': wallet},
                    timeout=3
                )
                if resp.status_code != 200:
                    continue

                state = resp.json()
                for pos_data in state.get('assetPositions', []):
                    pos = pos_data.get('position', {})
                    coin = pos.get('coin', '')
                    szi = float(pos.get('szi', 0))

                    if abs(szi) == 0:
                        continue

                    side = 'LONG' if szi > 0 else 'SHORT'
                    entry_price = float(pos.get('entryPx', 0))
                    position_value = float(pos.get('positionValue', 0))
                    liq_str = pos.get('liquidationPx')
                    leverage_info = pos.get('leverage', {})
                    leverage = float(leverage_info.get('value', 1)) if isinstance(leverage_info, dict) else 1.0
                    unrealized_pnl = float(pos.get('unrealizedPnl', 0))

                    # If no liq price from API, position is well-collateralized - skip
                    if liq_str is None:
                        continue
                    liq_price = float(liq_str)
                    if liq_price <= 0:
                        continue

                    # Calculate LIVE distance
                    current_price = mids.get(coin, 0)
                    if current_price > 0 and liq_price > 0:
                        if side == 'LONG':
                            distance_pct = ((current_price - liq_price) / current_price) * 100
                        else:
                            distance_pct = ((liq_price - current_price) / current_price) * 100
                    else:
                        distance_pct = 999.0

                    # Filter by distance and value
                    if distance_pct <= 0 or distance_pct > max_distance_pct:
                        continue
                    if position_value < min_value:
                        continue

                    live_positions.append({
                        'wallet_address': wallet,
                        'coin': coin,
                        'side': side,
                        'entry_price': entry_price,
                        'position_size': abs(szi),
                        'position_value': position_value,
                        'leverage': leverage,
                        'liquidation_price': liq_price,
                        'current_price': current_price,
                        'unrealized_pnl': unrealized_pnl,
                        'distance_to_liq_pct': distance_pct,
                        'is_live': True,  # Flag indicating this is live data
                        'updated_at': now
                    })

            except Exception:
                continue

        # Sort by distance
        live_positions.sort(key=lambda x: x['distance_to_liq_pct'])

        # Update cache
        _live_positions_cache['data'] = live_positions
        _live_positions_cache['timestamp'] = now
        _live_positions_cache['wallets'] = wallets_to_check

        return live_positions

    except Exception as e:
        print(f"[LIVE] Error fetching live positions: {e}")
        return _live_positions_cache.get('data', [])


def get_live_mid_price(coin: str) -> float:
    """Get live mid price for a coin from cache or API."""
    global _live_positions_cache

    # Use cached mids if fresh (< 2 seconds)
    if time.time() - _live_positions_cache['timestamp'] < 2.0:
        return _live_positions_cache['mids'].get(coin, 0)

    # Fetch fresh
    try:
        resp = requests.post(HYPERLIQUID_API, json={'type': 'allMids'}, timeout=2)
        if resp.status_code == 200:
            mids = resp.json()
            _live_positions_cache['mids'] = {k: float(v) for k, v in mids.items()}
            _live_positions_cache['timestamp'] = time.time()
            return float(mids.get(coin, 0))
    except Exception:
        pass

    return _live_positions_cache['mids'].get(coin, 0)


# ==============================================================================
# Live Position Tracker (new clean implementation - no database dependency)
# ==============================================================================

# Global live tracker instance
_live_tracker: Optional[LiveTrackerSync] = None

def get_live_tracker() -> LiveTrackerSync:
    """Get or create the global live tracker instance."""
    global _live_tracker
    if _live_tracker is None:
        print("[LiveTracker] Starting with auto-discovery...")
        _live_tracker = LiveTrackerSync(
            wallets=DEFAULT_WHALES,
            auto_discover=True,
            min_account_value=25000,  # Lower threshold for more coverage
        )
        _live_tracker.start()
        print(f"[LiveTracker] Started with {len(DEFAULT_WHALES)} seed wallets")
    return _live_tracker

def position_to_dict(pos: Position) -> Dict:
    """Convert Position dataclass to dict format for UI table."""
    return {
        'wallet_address': pos.wallet,
        'coin': pos.coin,
        'side': pos.side,
        'entry_price': pos.entry_price,
        'position_size': pos.size,
        'position_value': pos.notional,
        'leverage': pos.leverage,
        'liquidation_price': pos.liq_price,
        'current_price': pos.current_price,
        'unrealized_pnl': pos.pnl,
        'distance_to_liq_pct': pos.distance_pct,
        'liq_touched': pos.liq_touched,
        'liq_breached': pos.liq_breached,
        'recent_high': pos.recent_high,
        'recent_low': pos.recent_low,
        'is_live': True,
        'updated_at': time.time()
    }

def get_cached_live_positions() -> List[Dict]:
    """Get live positions from background tracker (non-blocking)."""
    tracker = get_live_tracker()
    positions = tracker.get_positions(max_distance=10.0)
    return [position_to_dict(p) for p in positions]

def get_live_wallet_count() -> int:
    """Get number of wallets being tracked."""
    tracker = get_live_tracker()
    return tracker.get_wallet_count()


COLORS = {
    "background": "#0d0d1a",
    "panel_bg": "#151525",
    "header": "#6cf",
    "long": "#4f4",
    "short": "#f44",
    "profit": "#4f4",
    "loss": "#f44",
    "warning": "#ff0",
    "critical": "#f80",
    "running": "#4f4",
    "idle": "#666",
    "text": "#eee",
    "text_dim": "#888",
    "border": "#335",
}


# ==============================================================================
# Data Aggregation Functions
# ==============================================================================

def format_value(value: float) -> str:
    """Format large dollar values compactly."""
    if value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value/1_000:.0f}K"
    else:
        return f"${value:.0f}"


def aggregate_liquidation_proximity(snapshot: ObservationSnapshot) -> List[Dict]:
    """Collect all liquidations across all symbols, sort by value."""
    all_positions = []

    for symbol, bundle in snapshot.primitives.items():
        if bundle is None or bundle.liquidation_cascade_proximity is None:
            continue

        prox = bundle.liquidation_cascade_proximity
        price = prox.price_level

        # Add long positions
        if prox.long_positions_count > 0:
            # Calculate distance to closest liquidation
            if prox.long_closest_price and price > 0:
                dist_pct = abs(price - prox.long_closest_price) / price * 100
            else:
                dist_pct = 999

            all_positions.append({
                'symbol': symbol.replace("USDT", ""),
                'side': 'LONG',
                'value': prox.long_positions_value,
                'distance_pct': dist_pct,
                'closest_price': prox.long_closest_price,
                'count': prox.long_positions_count,
                'price': price
            })

        # Add short positions
        if prox.short_positions_count > 0:
            if prox.short_closest_price and price > 0:
                dist_pct = abs(prox.short_closest_price - price) / price * 100
            else:
                dist_pct = 999

            all_positions.append({
                'symbol': symbol.replace("USDT", ""),
                'side': 'SHORT',
                'value': prox.short_positions_value,
                'distance_pct': dist_pct,
                'closest_price': prox.short_closest_price,
                'count': prox.short_positions_count,
                'price': price
            })

    # Sort by distance to liquidation (closest first)
    return sorted(all_positions, key=lambda x: x['distance_pct'])


def aggregate_prices(snapshot: ObservationSnapshot) -> Dict[str, Dict]:
    """Get current prices for all symbols."""
    prices = {}

    for symbol, bundle in snapshot.primitives.items():
        if bundle is None:
            continue

        price = None
        if bundle.liquidation_cascade_proximity:
            price = bundle.liquidation_cascade_proximity.price_level

        prices[symbol] = {
            'price': price,
            'symbol_short': symbol.replace("USDT", "")
        }

    return prices


def aggregate_cascade_state_from_hyperliquid() -> Dict:
    """Aggregate cascade state from Hyperliquid positions (ground truth)."""
    if not os.path.exists(HL_INDEXED_DB_PATH):
        return {
            'phase': 'NO_DATA',
            'positions_at_risk': 0,
            'total_at_risk': 0,
            'closest_pct': None,
            'closest_symbol': None,
            'clusters': []
        }

    try:
        conn = get_indexed_db_connection()
        stale_threshold = time.time() - POSITION_STALENESS_SECONDS

        # Get positions close to liquidation (within 10%)
        cursor = conn.execute("""
            SELECT coin, side, position_value, distance_to_liq_pct, liquidation_price, entry_price
            FROM positions
            WHERE distance_to_liq_pct >= 0 AND distance_to_liq_pct <= 10
              AND position_value >= 10000
              AND updated_at >= ?
            ORDER BY distance_to_liq_pct ASC
        """, (stale_threshold,))

        positions_at_risk = []
        for row in cursor.fetchall():
            positions_at_risk.append({
                'coin': row[0],
                'side': row[1],
                'value': float(row[2]),
                'dist_pct': float(row[3]),
                'liq_price': float(row[4]),
                'entry_price': float(row[5])
            })

        conn.close()

        if not positions_at_risk:
            return {
                'phase': 'NONE',
                'positions_at_risk': 0,
                'total_at_risk': 0,
                'closest_pct': None,
                'closest_symbol': None,
                'clusters': []
            }

        # Aggregate by coin
        by_coin = {}
        for pos in positions_at_risk:
            coin = pos['coin']
            if coin not in by_coin:
                by_coin[coin] = {'count': 0, 'value': 0, 'closest': 999}
            by_coin[coin]['count'] += 1
            by_coin[coin]['value'] += pos['value']
            by_coin[coin]['closest'] = min(by_coin[coin]['closest'], pos['dist_pct'])

        # Find closest
        closest_pos = positions_at_risk[0]  # Already sorted by distance
        closest_pct = closest_pos['dist_pct']
        closest_symbol = closest_pos['coin']

        # Determine phase based on proximity
        if closest_pct < 1.0:
            phase = 'LIQUIDATING'
        elif closest_pct < 3.0:
            phase = 'PROXIMITY'
        else:
            phase = 'MONITORING'

        # Find clusters (multiple positions at similar levels for same coin)
        clusters = []
        for coin, data in by_coin.items():
            if data['count'] >= 2 and data['value'] >= 100_000:
                clusters.append({
                    'coin': coin,
                    'count': data['count'],
                    'value': data['value'],
                    'closest_pct': data['closest']
                })

        return {
            'phase': phase,
            'positions_at_risk': len(positions_at_risk),
            'total_at_risk': sum(p['value'] for p in positions_at_risk),
            'closest_pct': closest_pct,
            'closest_symbol': closest_symbol,
            'clusters': sorted(clusters, key=lambda x: x['closest_pct'])
        }

    except Exception as e:
        print(f"Error computing cascade state: {e}")
        return {
            'phase': 'ERROR',
            'positions_at_risk': 0,
            'total_at_risk': 0,
            'closest_pct': None,
            'closest_symbol': None,
            'clusters': []
        }


def aggregate_cascade_state(snapshot: ObservationSnapshot) -> Dict:
    """Aggregate cascade state - uses Hyperliquid data for accuracy."""
    # Use Hyperliquid position data as ground truth
    return aggregate_cascade_state_from_hyperliquid()


def get_orderbook_depth(snapshot: ObservationSnapshot) -> List[Dict]:
    """Get order book depth for top symbols."""
    depth = []

    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        bundle = snapshot.primitives.get(symbol)
        if bundle is None or bundle.resting_size is None:
            depth.append({
                'symbol': symbol.replace("USDT", ""),
                'bid_size': 0,
                'bid_price': 0,
                'ask_size': 0,
                'ask_price': 0
            })
            continue

        rs = bundle.resting_size
        bid_price = rs.best_bid_price or 0
        ask_price = rs.best_ask_price or 0

        # Convert quantity to dollar value (size * price)
        bid_qty = rs.bid_size if hasattr(rs, 'bid_size') else 0
        ask_qty = rs.ask_size if hasattr(rs, 'ask_size') else 0

        depth.append({
            'symbol': symbol.replace("USDT", ""),
            'bid_size': bid_qty * bid_price if bid_price else 0,  # Dollar value
            'bid_price': bid_price,
            'ask_size': ask_qty * ask_price if ask_price else 0,  # Dollar value
            'ask_price': ask_price
        })

    return depth


def load_recent_trades(limit: int = 15) -> List[Dict]:
    """Load recent ghost trades from execution.db."""
    if not os.path.exists(DB_PATH):
        return []

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT symbol, side, price, timestamp, is_entry, pnl, pnl_pct,
                   holding_duration_sec, exit_reason, winning_policy_name
            FROM ghost_trades
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return trades
    except Exception as e:
        print(f"Error loading trades: {e}")
        return []


def load_hyperliquid_positions(limit: int = 30, max_distance_pct: float = 10.0, sort_by: str = "impact", min_value: float = 10000.0) -> List[Dict]:
    """
    Load individual Hyperliquid positions.

    Args:
        limit: Max positions to return
        max_distance_pct: Only show positions within this distance of liquidation
        sort_by: "impact" (size * impact DESC) or "distance" (closest to liq first)
        min_value: Minimum position value to display (default $50k)
    """
    if not os.path.exists(HL_INDEXED_DB_PATH):
        return []

    try:
        conn = get_indexed_db_connection()

        # Filter: distance > 0.1% (exclude stale/liquidated), distance < max, value >= min
        min_distance_pct = 0.1

        # Only show positions updated recently (fresh data)
        stale_threshold = time.time() - POSITION_STALENESS_SECONDS

        if sort_by == "distance":
            # Sort by distance to liquidation (closest first)
            cursor = conn.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at,
                       liq_touched, liq_breached, recent_high, recent_low
                FROM positions
                WHERE distance_to_liq_pct > ? AND distance_to_liq_pct <= ? AND distance_to_liq_pct < 999
                  AND position_value >= ? AND updated_at >= ?
                ORDER BY distance_to_liq_pct ASC
                LIMIT ?
            """, (min_distance_pct, max_distance_pct, min_value, stale_threshold, limit))
        else:
            # Sort by impact (size * impact, highest first)
            cursor = conn.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at,
                       liq_touched, liq_breached, recent_high, recent_low,
                       (position_value * impact_score) as combined_score
                FROM positions
                WHERE distance_to_liq_pct > ? AND distance_to_liq_pct <= ? AND impact_score > 0
                  AND position_value >= ? AND updated_at >= ?
                ORDER BY combined_score DESC
                LIMIT ?
            """, (min_distance_pct, max_distance_pct, min_value, stale_threshold, limit))

        positions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return positions
    except Exception as e:
        print(f"Error loading HL positions: {e}")
        return []


def load_liquidation_heatmap_data(coin: str = "BTC", price_range_pct: float = 10.0, bucket_size_pct: float = 0.5) -> Dict:
    """
    Load and aggregate liquidation levels for heatmap visualization.

    Groups positions by their liquidation price into buckets relative to current price.
    Returns data structure optimized for heatmap rendering.

    Args:
        coin: Coin to analyze (e.g., "BTC", "ETH")
        price_range_pct: How far above/below current price to show (default 10%)
        bucket_size_pct: Size of each price bucket as % (default 0.5%)

    Returns:
        Dict with:
        - current_price: float
        - buckets: List of {price_level, pct_from_current, long_value, short_value, total_value, position_count}
        - total_long_value: Total value of long liquidations
        - total_short_value: Total value of short liquidations
        - max_bucket_value: Highest value in any bucket (for scaling)
    """
    if not os.path.exists(HL_INDEXED_DB_PATH):
        return {"current_price": 0, "buckets": [], "total_long_value": 0, "total_short_value": 0, "max_bucket_value": 0}

    try:
        conn = get_indexed_db_connection()

        # Get current price for the coin (from freshest position)
        stale_threshold = time.time() - POSITION_STALENESS_SECONDS
        price_cursor = conn.execute("""
            SELECT entry_price FROM positions
            WHERE coin = ? AND entry_price > 0 AND updated_at >= ?
            ORDER BY updated_at DESC LIMIT 1
        """, (coin, stale_threshold))
        price_row = price_cursor.fetchone()
        if not price_row:
            conn.close()
            return {"current_price": 0, "buckets": [], "total_long_value": 0, "total_short_value": 0, "max_bucket_value": 0}

        current_price = float(price_row['entry_price'])

        # Calculate price range
        min_price = current_price * (1 - price_range_pct / 100)
        max_price = current_price * (1 + price_range_pct / 100)

        # Query all positions with liquidation prices in range (only fresh data)
        cursor = conn.execute("""
            SELECT side, position_value, liquidation_price
            FROM positions
            WHERE coin = ?
              AND liquidation_price > 0
              AND liquidation_price BETWEEN ? AND ?
              AND position_value >= 10000
              AND updated_at >= ?
        """, (coin, min_price, max_price, stale_threshold))

        positions = cursor.fetchall()
        conn.close()

        # Create buckets
        num_buckets = int(2 * price_range_pct / bucket_size_pct) + 1
        buckets = []

        for i in range(num_buckets):
            pct_from_current = -price_range_pct + (i * bucket_size_pct)
            price_level = current_price * (1 + pct_from_current / 100)
            buckets.append({
                "price_level": price_level,
                "pct_from_current": pct_from_current,
                "long_value": 0.0,
                "short_value": 0.0,
                "total_value": 0.0,
                "position_count": 0
            })

        # Aggregate positions into buckets
        total_long = 0.0
        total_short = 0.0

        for pos in positions:
            liq_price = float(pos['liquidation_price'])
            value = float(pos['position_value'])
            side = pos['side']

            # Find the right bucket
            pct_from_current = ((liq_price / current_price) - 1) * 100
            bucket_idx = int((pct_from_current + price_range_pct) / bucket_size_pct)

            if 0 <= bucket_idx < len(buckets):
                buckets[bucket_idx]["position_count"] += 1
                buckets[bucket_idx]["total_value"] += value

                if side == "LONG":
                    buckets[bucket_idx]["long_value"] += value
                    total_long += value
                else:
                    buckets[bucket_idx]["short_value"] += value
                    total_short += value

        # Find max bucket value for scaling
        max_bucket_value = max((b["total_value"] for b in buckets), default=0)

        return {
            "current_price": current_price,
            "buckets": buckets,
            "total_long_value": total_long,
            "total_short_value": total_short,
            "max_bucket_value": max_bucket_value,
            "coin": coin
        }

    except Exception as e:
        print(f"Error loading heatmap data: {e}")
        return {"current_price": 0, "buckets": [], "total_long_value": 0, "total_short_value": 0, "max_bucket_value": 0}


# Global orderbook cache (updated by background thread)
_orderbook_cache: Dict[str, Dict] = {}


def update_orderbook_cache(coin: str, orderbook: Dict):
    """Update the global orderbook cache (called from async context)."""
    global _orderbook_cache
    _orderbook_cache[coin] = orderbook


def get_cached_orderbook(coin: str) -> Optional[Dict]:
    """Get cached orderbook data."""
    return _orderbook_cache.get(coin)


def compute_absorption_analysis(heatmap_data: Dict, orderbook: Optional[Dict]) -> Dict:
    """
    Compute absorption analysis comparing liquidation volume vs orderbook depth.

    Returns analysis of whether the book can absorb potential liquidation cascades.

    Key insight:
    - Liquidation value > Book depth at level → Cascade continues (thin book)
    - Liquidation value < Book depth at level → Cascade absorbed (thick book)
    """
    if not heatmap_data or not heatmap_data.get("buckets"):
        return {"levels": [], "can_absorb_longs": True, "can_absorb_shorts": True}

    if not orderbook:
        return {"levels": [], "can_absorb_longs": None, "can_absorb_shorts": None, "no_book_data": True}

    current_price = heatmap_data.get("current_price", 0)
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    analysis_levels = []
    total_long_liq = 0
    total_short_liq = 0
    total_bid_depth = 0
    total_ask_depth = 0

    for bucket in heatmap_data["buckets"]:
        pct = bucket["pct_from_current"]
        long_val = bucket["long_value"]
        short_val = bucket["short_value"]

        # Find orderbook depth at this level
        bid_depth_at_level = 0
        ask_depth_at_level = 0

        # For levels below current price, check bid depth (support)
        if pct < 0:
            for bid in bids:
                if bid["pct_from_mid"] >= pct:
                    bid_depth_at_level = bid["cumulative"]
            total_long_liq += long_val
            total_bid_depth = max(total_bid_depth, bid_depth_at_level)

        # For levels above current price, check ask depth (resistance)
        if pct > 0:
            for ask in asks:
                if ask["pct_from_mid"] <= pct:
                    ask_depth_at_level = ask["cumulative"]
                else:
                    break
            total_short_liq += short_val
            total_ask_depth = max(total_ask_depth, ask_depth_at_level)

        # Compute absorption ratio
        if pct < 0 and long_val > 0:
            absorption_ratio = bid_depth_at_level / long_val if long_val > 0 else float('inf')
            can_absorb = absorption_ratio >= 1.0
        elif pct > 0 and short_val > 0:
            absorption_ratio = ask_depth_at_level / short_val if short_val > 0 else float('inf')
            can_absorb = absorption_ratio >= 1.0
        else:
            absorption_ratio = float('inf')
            can_absorb = True

        if long_val > 10000 or short_val > 10000:
            analysis_levels.append({
                "pct_from_current": pct,
                "liq_value": long_val if pct < 0 else short_val,
                "book_depth": bid_depth_at_level if pct < 0 else ask_depth_at_level,
                "absorption_ratio": min(absorption_ratio, 10.0),  # Cap at 10x
                "can_absorb": can_absorb,
                "side": "LONG" if pct < 0 else "SHORT"
            })

    # Overall absorption assessment
    can_absorb_longs = total_bid_depth >= total_long_liq * 0.5 if total_long_liq > 0 else True
    can_absorb_shorts = total_ask_depth >= total_short_liq * 0.5 if total_short_liq > 0 else True

    return {
        "levels": analysis_levels,
        "total_long_liq": total_long_liq,
        "total_short_liq": total_short_liq,
        "total_bid_depth": total_bid_depth,
        "total_ask_depth": total_ask_depth,
        "can_absorb_longs": can_absorb_longs,
        "can_absorb_shorts": can_absorb_shorts,
        "long_absorption_ratio": total_bid_depth / total_long_liq if total_long_liq > 0 else float('inf'),
        "short_absorption_ratio": total_ask_depth / total_short_liq if total_short_liq > 0 else float('inf')
    }


def create_absorption_analysis_for_strategy(
    coin: str,
    heatmap_data: Optional[Dict] = None,
    orderbook: Optional[Dict] = None
) -> Optional['AbsorptionAnalysis']:
    """
    Create AbsorptionAnalysis object for cascade sniper strategy.

    Combines orderbook depth data with liquidation proximity data to compute
    absorption ratios that determine if book can absorb cascade volume.

    Args:
        coin: Asset symbol (e.g., "BTC")
        heatmap_data: Output from load_liquidation_heatmap_data()
        orderbook: Cached orderbook data from OrderbookRefresher

    Returns:
        AbsorptionAnalysis for strategy, or None if data insufficient
    """
    # Import here to avoid circular import
    from external_policy.ep2_strategy_cascade_sniper import AbsorptionAnalysis

    # Get orderbook from cache if not provided
    if orderbook is None:
        orderbook = get_cached_orderbook(coin)

    if orderbook is None:
        return None

    # Get heatmap data if not provided
    if heatmap_data is None:
        heatmap_data = load_liquidation_heatmap_data(coin)

    if not heatmap_data or not heatmap_data.get("buckets"):
        # No liquidation data - create analysis with zero liquidation values
        mid_price = orderbook.get("mid_price", 0)
        return AbsorptionAnalysis(
            coin=coin,
            mid_price=mid_price,
            bid_depth_2pct=orderbook.get("total_bid_depth", 0),
            ask_depth_2pct=orderbook.get("total_ask_depth", 0),
            long_liq_value=0,
            short_liq_value=0,
            absorption_ratio_longs=float('inf'),  # No longs to absorb
            absorption_ratio_shorts=float('inf'),  # No shorts to absorb
            timestamp=time.time()
        )

    # Compute absorption using existing function
    analysis = compute_absorption_analysis(heatmap_data, orderbook)

    mid_price = orderbook.get("mid_price", 0)
    total_long_liq = analysis.get("total_long_liq", 0)
    total_short_liq = analysis.get("total_short_liq", 0)
    total_bid_depth = analysis.get("total_bid_depth", 0)
    total_ask_depth = analysis.get("total_ask_depth", 0)

    # Compute absorption ratios (avoid division by zero)
    absorption_ratio_longs = total_bid_depth / total_long_liq if total_long_liq > 0 else float('inf')
    absorption_ratio_shorts = total_ask_depth / total_short_liq if total_short_liq > 0 else float('inf')

    return AbsorptionAnalysis(
        coin=coin,
        mid_price=mid_price,
        bid_depth_2pct=total_bid_depth,
        ask_depth_2pct=total_ask_depth,
        long_liq_value=total_long_liq,
        short_liq_value=total_short_liq,
        absorption_ratio_longs=absorption_ratio_longs,
        absorption_ratio_shorts=absorption_ratio_shorts,
        timestamp=time.time()
    )


def count_primitives(bundle) -> int:
    """Count non-None primitives in a bundle."""
    if bundle is None:
        return 0

    fields = [
        bundle.zone_penetration,
        bundle.price_traversal_velocity,
        bundle.traversal_compactness,
        bundle.structural_absence_duration,
        bundle.resting_size,
        bundle.order_consumption,
        bundle.refill_event,
        bundle.supply_demand_zone,
        bundle.order_block,
        bundle.liquidation_cascade_proximity,
        bundle.cascade_state,
    ]
    return sum(1 for f in fields if f is not None)


# ==============================================================================
# Background Position Refresher
# ==============================================================================

class PositionRefresher(threading.Thread):
    """Background thread that polls Hyperliquid API and updates position data.

    Features:
    - Normal refresh: All wallets every 30 seconds
    - ZOOM MODE: Wallets with positions within 0.2% of liquidation get refreshed every 2-3 seconds
    """

    HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"
    REFRESH_INTERVAL = 10  # seconds for normal refresh (was 30)
    ZOOM_REFRESH_INTERVAL = 1.0  # 1 second for priority wallets - user requirement
    ZOOM_THRESHOLD_PCT = 5.0  # positions within this % of liq get priority refresh
    CRITICAL_THRESHOLD_PCT = 1.0  # positions within 1% get highest priority

    # Core whale wallets (always track these)
    CORE_WHALES = [
        '0x023a3d0580a72d352f4c1595e52597c119f9f6a3',  # $27M+ exposure
        '0x010461c14e146ac35fe42271bdc1134ee31c703a',  # Liquidator $18M
        '0x0fd468a730d62dc1c0d914d49ec78cfa07b74e4a',  # $9.6M BTC short
    ]

    # Dynamic wallet list - loaded from database
    TRACKED_WHALES = []  # Will be populated from DB

    # Minimum position value to track changes
    MIN_WHALE_POSITION = 50000  # $50k for whale alerts (lowered from $100k)
    MIN_WALLET_VALUE = 10000  # $10k minimum to track a wallet (lowered from $50k for more retail coverage)
    MIN_RISKY_POSITION = 5000  # $5k minimum for positions near liquidation

    def __init__(self, db_path: str):
        super().__init__(daemon=True)
        self.db_path = db_path
        self._running = True
        self._last_refresh = 0
        self._last_zoom_refresh = 0
        self._last_wallet_discovery = 0
        self._priority_wallets: set = set()  # Wallets with positions near liquidation
        self._zoom_positions: list = []  # Current zoom targets for UI
        self._zoom_mode = False

        # Whale tracking
        self._previous_positions: Dict[str, Dict] = {}  # wallet -> {coin: position_data}
        self._whale_alerts: list = []  # Recent whale activity alerts
        self._max_alerts = 50  # Keep last N alerts

        # Liquidation callback for fade executor
        self._on_liquidation = None

        # Wallet discovery callback (for WSTracker sync)
        self._on_wallet_discovered = None

        # Dynamic wallet discovery
        self._discovered_wallets: set = set()  # Wallets found from trades
        self._load_wallets_from_db()  # Load high-value wallets on init

        # Zone alert tracking (to detect when positions move into danger)
        self._previous_zones: Dict[str, str] = {}  # "wallet_coin" -> zone
        self._last_zone_alert = 0

    def set_liquidation_callback(self, callback):
        """Set callback for liquidation events."""
        self._on_liquidation = callback

    def set_wallet_discovery_callback(self, callback):
        """Set callback for newly discovered wallets (for WSTracker sync)."""
        self._on_wallet_discovered = callback

    def _load_wallets_from_db(self):
        """Load high-value wallets from indexed_wallets database."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()

            # Get wallets with significant position value (increased limit for more coverage)
            cursor.execute("""
                SELECT DISTINCT address FROM indexed_wallets
                WHERE position_value > ?
                ORDER BY position_value DESC
                LIMIT 200
            """, (self.MIN_WALLET_VALUE,))

            db_wallets = [row[0] for row in cursor.fetchall()]
            conn.close()

            # Combine core whales + DB wallets
            self.TRACKED_WHALES = list(self.CORE_WHALES)
            for w in db_wallets:
                if w not in self.TRACKED_WHALES:
                    self.TRACKED_WHALES.append(w)

            print(f"[PositionRefresher] Loaded {len(self.TRACKED_WHALES)} wallets to track")

        except Exception as e:
            print(f"[PositionRefresher] Error loading wallets from DB: {e}")
            self.TRACKED_WHALES = list(self.CORE_WHALES)

    def _discover_wallets_from_trades(self):
        """Discover new wallets from recent trades across major coins."""
        try:
            # Expanded coin list for better coverage
            coins = [
                'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'WIF', 'TRUMP', 'NOT', 'PEPE',
                'LINK', 'AVAX', 'SUI', 'APT', 'ARB', 'OP', 'INJ', 'SEI', 'TIA',
                'JTO', 'PYTH', 'WLD', 'BLUR', 'STX', 'IMX', 'MEME', 'BONK',
                'ORDI', 'SATS', 'RATS', 'BRETT', 'BOME', 'FLOKI', 'SHIB'
            ]
            new_wallets = set()

            for coin in coins:
                try:
                    resp = requests.post(
                        self.HYPERLIQUID_API,
                        json={'type': 'recentTrades', 'coin': coin},
                        timeout=5
                    )
                    if resp.status_code == 200:
                        trades = resp.json()
                        for trade in trades:
                            users = trade.get('users', [])
                            for u in users:
                                if u and u not in self.TRACKED_WHALES:
                                    new_wallets.add(u)
                except:
                    pass

            # Check positions for new wallets, add if significant
            added = 0
            for wallet in new_wallets:
                if wallet in self._discovered_wallets:
                    continue

                try:
                    state = self._get_clearinghouse_state(wallet)
                    if not state:
                        continue

                    # Calculate total value
                    total = 0
                    near_liq = False
                    for p in state.get('assetPositions', []):
                        pos = p.get('position', {})
                        size = abs(float(pos.get('szi', 0)))
                        entry = float(pos.get('entryPx', 0))
                        total += size * entry

                        # Check if near liquidation
                        liq_px = pos.get('liquidationPx')
                        if liq_px and float(liq_px) > 0:
                            dist = abs(float(liq_px) - entry) / entry * 100 if entry > 0 else 999
                            if dist < 10:
                                near_liq = True

                    if total >= self.MIN_WALLET_VALUE or near_liq:
                        self.TRACKED_WHALES.append(wallet)
                        self._discovered_wallets.add(wallet)
                        added += 1
                        if near_liq:
                            print(f"[DISCOVERY] Added {wallet[:10]}... (${total:,.0f}, NEAR LIQ)")
                        # Notify WSTracker of new wallet
                        if self._on_wallet_discovered:
                            self._on_wallet_discovered(wallet)

                except:
                    pass

                if added >= 20:  # Increased limit per cycle for better coverage
                    break

            if added > 0:
                print(f"[DISCOVERY] Added {added} new wallets, now tracking {len(self.TRACKED_WHALES)}")

        except Exception as e:
            print(f"[DISCOVERY] Error: {e}")

    def _scan_stale_wallets(self):
        """Scan stale wallets from indexed_wallets DB to find retail positions at risk.

        This method scans wallets that haven't been checked recently and adds
        any with positions close to liquidation, even if they're small.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()

            # Get wallets with old position data that might have risky positions
            cursor.execute("""
                SELECT address, position_value
                FROM indexed_wallets
                WHERE position_value > 5000
                  AND (last_position_check IS NULL
                       OR last_position_check < datetime('now', '-2 hours'))
                ORDER BY position_value DESC
                LIMIT 30
            """)
            stale_wallets = cursor.fetchall()
            conn.close()

            added = 0
            risky_found = 0

            for wallet, old_value in stale_wallets:
                if wallet in self.TRACKED_WHALES or wallet in self._discovered_wallets:
                    continue

                try:
                    state = self._get_clearinghouse_state(wallet)
                    if not state:
                        continue

                    positions = state.get('assetPositions', [])
                    active = [p for p in positions if float(p.get('position', {}).get('szi', 0) or 0) != 0]

                    if not active:
                        continue

                    # Check each position for risk
                    total_value = 0
                    has_risky_position = False
                    has_high_impact = False

                    for p in active:
                        pos = p.get('position', {})
                        coin = pos.get('coin', '')
                        szi = float(pos.get('szi', 0) or 0)
                        entry = float(pos.get('entryPx', 0) or 0)
                        liq_str = pos.get('liquidationPx')
                        liq = float(liq_str) if liq_str else 0
                        val = abs(szi * entry)
                        total_value += val

                        if liq > 0 and entry > 0:
                            # Calculate distance to liquidation
                            if szi > 0:  # LONG
                                dist = (entry - liq) / entry * 100
                            else:  # SHORT
                                dist = (liq - entry) / entry * 100

                            # Track if close to liquidation (< 10%)
                            if 0 < dist < 10:
                                has_risky_position = True
                                risky_found += 1

                            # Check if it's a shitcoin with potential impact
                            shitcoins = ['TRUMP', 'WIF', 'PEPE', 'BONK', 'NOT', 'BRETT',
                                         'FARTCOIN', 'CHILLGUY', 'YZY', 'PUMP', 'XPL', 'KAITO']
                            if coin in shitcoins and val > 5000:
                                has_high_impact = True

                    # Add wallet if it has risky positions or high impact shitcoin exposure
                    if has_risky_position or has_high_impact or total_value >= self.MIN_WALLET_VALUE:
                        self.TRACKED_WHALES.append(wallet)
                        self._discovered_wallets.add(wallet)
                        added += 1

                        if has_risky_position:
                            print(f"[STALE-SCAN] Added {wallet[:10]}... (${total_value:,.0f}, RISKY POSITION)")
                        elif has_high_impact:
                            print(f"[STALE-SCAN] Added {wallet[:10]}... (${total_value:,.0f}, SHITCOIN EXPOSURE)")

                        # Notify WSTracker of new wallet
                        if self._on_wallet_discovered:
                            self._on_wallet_discovered(wallet)

                except Exception:
                    pass

                # Rate limit
                time.sleep(0.1)

                if added >= 10:  # Limit additions per cycle
                    break

            if added > 0:
                print(f"[STALE-SCAN] Scanned stale wallets: added {added}, found {risky_found} risky, now tracking {len(self.TRACKED_WHALES)}")

        except Exception as e:
            print(f"[STALE-SCAN] Error: {e}")

    def stop(self):
        self._running = False

    def get_zoom_status(self) -> Dict:
        """Return current zoom mode status for UI."""
        return {
            'active': self._zoom_mode,
            'priority_wallets': len(self._priority_wallets),
            'positions': self._zoom_positions.copy()
        }

    def get_whale_alerts(self) -> list:
        """Return recent whale activity alerts."""
        return self._whale_alerts.copy()

    def _detect_whale_changes(self, wallet: str, new_positions: Dict[str, Dict]) -> list:
        """Compare new positions with previous snapshot, detect changes."""
        alerts = []
        wallet_short = wallet[:10] + '...'
        prev_positions = self._previous_positions.get(wallet, {})
        now = time.time()

        # Check for new or increased positions
        for coin, pos in new_positions.items():
            value = pos.get('value', 0)
            if value < self.MIN_WHALE_POSITION:
                continue

            side = pos.get('side', 'LONG')
            prev = prev_positions.get(coin, {})
            prev_value = prev.get('value', 0)

            if prev_value == 0:
                # NEW POSITION
                alerts.append({
                    'type': 'NEW',
                    'wallet': wallet_short,
                    'coin': coin,
                    'side': side,
                    'value': value,
                    'change_pct': 100,
                    'timestamp': now,
                    'msg': f"🆕 {wallet_short} opened {side} {coin} ${value:,.0f}"
                })
            elif value > prev_value * 1.2:
                # INCREASED > 20%
                change_pct = (value - prev_value) / prev_value * 100
                alerts.append({
                    'type': 'INCREASE',
                    'wallet': wallet_short,
                    'coin': coin,
                    'side': side,
                    'value': value,
                    'prev_value': prev_value,
                    'change_pct': change_pct,
                    'timestamp': now,
                    'msg': f"📈 {wallet_short} increased {side} {coin} +{change_pct:.0f}% → ${value:,.0f}"
                })

        # Check for closed positions
        for coin, prev in prev_positions.items():
            prev_value = prev.get('value', 0)
            if prev_value < self.MIN_WHALE_POSITION:
                continue

            if coin not in new_positions or new_positions[coin].get('value', 0) < prev_value * 0.2:
                side = prev.get('side', 'LONG')
                alerts.append({
                    'type': 'CLOSED',
                    'wallet': wallet_short,
                    'coin': coin,
                    'side': side,
                    'value': prev_value,
                    'change_pct': -100,
                    'timestamp': now,
                    'msg': f"🔻 {wallet_short} CLOSED {side} {coin} (was ${prev_value:,.0f})"
                })

        return alerts

    def _track_whales(self):
        """Track whale wallet positions and detect changes."""
        # Combine static tracked whales with dynamically discovered liquidators
        all_tracked = list(self.TRACKED_WHALES)
        dynamic = getattr(self, '_dynamic_tracked_wallets', set())
        all_tracked.extend(list(dynamic))

        for wallet in all_tracked:
            try:
                state = self._get_clearinghouse_state(wallet)
                if not state:
                    continue

                # Build current positions dict
                new_positions = {}
                for pos in state.get('assetPositions', []):
                    p = pos.get('position', {})
                    coin = p.get('coin', '')
                    szi = float(p.get('szi', 0))
                    entry_px = float(p.get('entryPx', 0))
                    value = abs(szi * entry_px)

                    if value >= self.MIN_WHALE_POSITION:
                        new_positions[coin] = {
                            'side': 'LONG' if szi > 0 else 'SHORT',
                            'value': value,
                            'size': abs(szi),
                            'entry_price': entry_px
                        }

                # Detect changes
                alerts = self._detect_whale_changes(wallet, new_positions)

                # Store alerts
                if alerts:
                    self._whale_alerts.extend(alerts)
                    # Keep only last N alerts
                    if len(self._whale_alerts) > self._max_alerts:
                        self._whale_alerts = self._whale_alerts[-self._max_alerts:]

                    # Print alerts
                    for alert in alerts:
                        print(f"[WHALE] {alert['msg']}")

                # Update previous positions
                self._previous_positions[wallet] = new_positions

            except Exception as e:
                print(f"[WHALE] Error tracking {wallet[:10]}...: {e}")

    def run(self):
        """Main refresh loop with priority handling."""
        print("[PositionRefresher] Started background position refresh")
        print(f"[PositionRefresher] Tracking {len(self.TRACKED_WHALES)} wallets (from DB + core)")

        # === STARTUP FAST-PATH: Immediately refresh core whales ===
        # This populates positions before the main loop starts
        print("[PositionRefresher] Fast-refreshing core whales on startup...")
        self._startup_fast_refresh()

        # Initialize timestamps to current time so blocking ops don't run immediately
        startup_time = time.time()
        last_full_refresh = startup_time  # Full refresh just happened in startup
        last_zoom_refresh = 0
        last_whale_track = startup_time  # Don't run whale tracking immediately
        last_discovery = startup_time    # Don't run discovery immediately
        last_stale_scan = startup_time   # Don't run stale scan immediately
        WHALE_TRACK_INTERVAL = 15  # Track whales every 15 seconds
        DISCOVERY_INTERVAL = 30  # Discover new wallets every 30 seconds (faster coverage)
        STALE_SCAN_INTERVAL = 120  # Scan stale wallets every 2 minutes

        loop_count = 0
        while self._running:
            now = time.time()
            loop_count += 1

            try:
                # ===== PRIORITY FIRST: ALWAYS RUN BEFORE ANYTHING ELSE =====
                # This ensures positions near liquidation stay fresh even if other operations block
                if self._priority_wallets:
                    if loop_count <= 5 or loop_count % 20 == 0:
                        print(f"[LOOP] Iteration {loop_count}: {len(self._priority_wallets)} priority wallets")
                    self._refresh_priority_wallets()
                    last_zoom_refresh = now
                elif loop_count <= 5:
                    print(f"[LOOP] Iteration {loop_count}: NO priority wallets")

                # ===== FULL REFRESH: Run BEFORE whale tracking =====
                # This populates priority wallets and keeps data fresh
                if (now - last_full_refresh) >= self.REFRESH_INTERVAL:
                    self._refresh_positions()
                    last_full_refresh = now
                    self._last_refresh = now
                    # After full refresh, immediately check priority again
                    if self._priority_wallets:
                        self._refresh_priority_wallets()

                # ===== LOWER PRIORITY OPERATIONS (can block) =====
                # Whale tracking: every 15 seconds
                if (now - last_whale_track) >= WHALE_TRACK_INTERVAL:
                    self._track_whales()
                    last_whale_track = now

                # Wallet discovery: every 30 seconds
                if (now - last_discovery) >= DISCOVERY_INTERVAL:
                    self._discover_wallets_from_trades()
                    last_discovery = now

                # Stale wallet scan: every 2 minutes (find retail positions at risk)
                if (now - last_stale_scan) >= STALE_SCAN_INTERVAL:
                    self._scan_stale_wallets()
                    last_stale_scan = now

            except Exception as e:
                import traceback
                print(f"[PositionRefresher] Error: {e}")
                traceback.print_exc()

            # Debug: show loop progress
            if loop_count <= 5:
                print(f"[LOOP] End of iteration {loop_count}")

            # Faster loop for responsive priority refresh
            time.sleep(0.25)

        print("[PositionRefresher] Stopped")

    def _startup_fast_refresh(self):
        """Fast startup refresh of core whales to immediately identify priority positions."""
        try:
            start = time.time()

            # Get mid prices first
            mid_prices = self._get_all_mids()
            if not mid_prices:
                print("[PositionRefresher] Warning: No mid prices available")
                return

            print(f"[PositionRefresher] Got {len(mid_prices)} mid prices")

            # Cache mid prices
            self._cached_mids = mid_prices
            self._mids_cache_time = time.time()

            # Use cached volumes or empty dict
            volumes = getattr(self, '_cached_volumes', {})

            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")

            # Fetch all core whale states in parallel
            print(f"[PositionRefresher] Fetching {len(self.CORE_WHALES)} core whale states...")
            wallet_states = {}
            with ThreadPoolExecutor(max_workers=20) as executor:
                future_to_wallet = {
                    executor.submit(self._get_clearinghouse_state, wallet): wallet
                    for wallet in self.CORE_WHALES
                }
                for future in as_completed(future_to_wallet):
                    wallet = future_to_wallet[future]
                    try:
                        state = future.result()
                        if state:
                            wallet_states[wallet] = state
                    except Exception as e:
                        print(f"[PositionRefresher] Startup error for {wallet[:10]}...: {e}")

            print(f"[PositionRefresher] Got states for {len(wallet_states)} wallets")

            # Update positions in DB (skip candle fetch for speed)
            for wallet, state in wallet_states.items():
                self._update_wallet_positions(conn, wallet, state, mid_prices, volumes, skip_candle_fetch=True)

            conn.commit()

            # Now identify priority wallets
            self._identify_priority_wallets(conn)

            conn.close()

            elapsed = time.time() - start
            print(f"[PositionRefresher] Startup: {len(wallet_states)} core whales in {elapsed:.1f}s, {len(self._priority_wallets)} priority")

        except Exception as e:
            import traceback
            print(f"[PositionRefresher] Startup FAILED: {e}")
            traceback.print_exc()

    def _refresh_priority_wallets(self):
        """Fast refresh for wallets with positions near liquidation."""
        if not self._priority_wallets:
            return

        start_time = time.time()

        # Cache mid prices for 2 seconds to reduce API calls
        mid_prices = getattr(self, '_cached_mids', {})
        mids_age = getattr(self, '_mids_cache_time', 0)
        if time.time() - mids_age > 2:  # Refresh every 2 seconds max
            mid_prices = self._get_all_mids()
            self._cached_mids = mid_prices
            self._mids_cache_time = time.time()

        if not mid_prices:
            return

        # Get volumes for impact calculation (cache for 60 seconds to reduce API calls)
        volumes = getattr(self, '_cached_volumes', {})
        volumes_age = getattr(self, '_volumes_cache_time', 0)
        if time.time() - volumes_age > 60:
            volumes = self._get_asset_volumes()
            self._cached_volumes = volumes
            self._volumes_cache_time = time.time()

        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        updated = 0
        liquidated = []

        # Track position state changes
        position_changes = getattr(self, '_position_states', {})

        # === PARALLEL API CALLS ===
        # Fetch all wallet states in parallel to minimize latency
        wallet_start = time.time()
        wallet_list = list(self._priority_wallets)
        wallet_states = {}

        with ThreadPoolExecutor(max_workers=min(10, len(wallet_list))) as executor:
            future_to_wallet = {
                executor.submit(self._get_clearinghouse_state, wallet): wallet
                for wallet in wallet_list
            }
            for future in as_completed(future_to_wallet):
                wallet = future_to_wallet[future]
                try:
                    state = future.result()
                    wallet_states[wallet] = state
                except Exception as e:
                    print(f"[ZOOM] Error fetching {wallet[:10]}...: {e}")

        # === PROCESS RESULTS ===
        for wallet, state in wallet_states.items():
            try:
                if state:
                    positions = state.get('assetPositions', [])
                    if positions:
                        # Skip candle fetch for priority refresh speed
                        self._update_wallet_positions(conn, wallet, state, mid_prices, volumes, skip_candle_fetch=True)
                        updated += 1

                        # Track detailed position state for liquidation detection
                        for pos_data in positions:
                            pos = pos_data.get('position', {})
                            coin = pos.get('coin', '')
                            size = abs(float(pos.get('szi', 0)))
                            key = f"{wallet[:12]}_{coin}"

                            prev_state = position_changes.get(key, {})
                            prev_size = prev_state.get('size', size)

                            # Detect partial liquidation (size reduced >20%)
                            if prev_size > 0 and size < prev_size * 0.8:
                                reduction_pct = ((prev_size - size) / prev_size) * 100
                                liq_price = pos.get('liquidationPx', 'N/A')
                                print(f"[ZOOM] ⚠️ PARTIAL LIQ: {wallet[:10]}... {coin} size reduced {reduction_pct:.0f}% ({prev_size:.2f} → {size:.2f})")
                                print(f"[ZOOM]    Time: {time.strftime('%H:%M:%S')} | Liq price: {liq_price}")

                                self._whale_alerts.append({
                                    'type': 'PARTIAL_LIQ',
                                    'wallet': wallet[:10] + '...',
                                    'coin': coin,
                                    'reduction_pct': reduction_pct,
                                    'prev_size': prev_size,
                                    'new_size': size,
                                    'timestamp': time.time(),
                                    'msg': f"⚠️ {coin} partially liquidated -{reduction_pct:.0f}%"
                                })

                                # Trigger liquidation callback for fade executor
                                if self._on_liquidation and reduction_pct >= 50:
                                    liq_event = {
                                        'type': 'PARTIAL_LIQUIDATION',
                                        'coin': coin,
                                        'wallet': wallet,
                                        'value': float(pos.get('positionValue', 0)),
                                        'reduction_pct': reduction_pct,
                                        'timestamp': time.time()
                                    }
                                    try:
                                        self._on_liquidation(liq_event)
                                    except Exception as e:
                                        print(f"[ZOOM] Liquidation callback error: {e}")

                            # Update state
                            position_changes[key] = {
                                'size': size,
                                'value': float(pos.get('positionValue', 0)),
                                'entry_price': float(pos.get('entryPx', 0)),
                                'liq_price': pos.get('liquidationPx'),
                                'last_update': time.time()
                            }
                    else:
                        # Position closed/liquidated!
                        liquidated.append(wallet)
                        self._priority_wallets.discard(wallet)
                        print(f"[ZOOM] ⚡ FULL LIQUIDATION: {wallet[:10]}... at {time.strftime('%H:%M:%S')}")

                        # Trigger liquidation callback for fade executor
                        if self._on_liquidation:
                            for zpos in self._zoom_positions:
                                if zpos.get('wallet', '').startswith(wallet[:10]):
                                    liq_event = {
                                        'type': 'FULL_LIQUIDATION',
                                        'coin': zpos.get('coin'),
                                        'wallet': wallet,
                                        'value': zpos.get('value', 0),
                                        'liq_price': zpos.get('liq_price', 0),
                                        'timestamp': time.time()
                                    }
                                    try:
                                        self._on_liquidation(liq_event)
                                    except Exception as e:
                                        print(f"[ZOOM] Liquidation callback error: {e}")
                                    break
            except Exception as e:
                print(f"[ZOOM] Error processing {wallet[:10]}...: {e}")

        self._position_states = position_changes

        conn.commit()
        conn.close()

        elapsed = time.time() - start_time
        wallet_elapsed = time.time() - wallet_start
        if elapsed > 1.0:  # Only log if taking too long
            print(f"[ZOOM] Priority refresh: {updated}/{len(self._priority_wallets)} wallets in {elapsed:.1f}s (API: {wallet_elapsed:.1f}s)")

        if liquidated:
            print(f"[ZOOM] ⚡ LIQUIDATED: {len(liquidated)} positions closed!")
            # Try to identify liquidators
            self._identify_liquidators(liquidated)

        if updated > 0:
            # Update zoom positions list
            self._update_zoom_positions()

    def _identify_liquidators(self, liquidated_wallets: list):
        """Identify who liquidated the positions by checking recent trades."""
        for wallet in liquidated_wallets:
            try:
                # Get what coin they had from our zoom positions
                coin = None
                for pos in self._zoom_positions:
                    if pos.get('wallet', '').startswith(wallet[:10]):
                        coin = pos.get('coin')
                        break

                if not coin:
                    continue

                # Get recent trades for that coin
                response = requests.post(self.HYPERLIQUID_API, json={
                    'type': 'recentTrades',
                    'coin': coin
                }, timeout=5)

                if response.status_code == 200:
                    trades = response.json()
                    # Look for trades involving this wallet
                    for trade in trades[:20]:
                        users = trade.get('users', [])
                        if any(wallet.lower().startswith(u[:10].lower()) for u in users):
                            # Found the liquidation trade
                            px = trade.get('px')
                            sz = trade.get('sz')
                            # The other user is the liquidator
                            liquidator = [u for u in users if not wallet.lower().startswith(u[:10].lower())]
                            if liquidator:
                                liquidator = liquidator[0]
                                print(f"[ZOOM] ⚡ LIQUIDATOR IDENTIFIED: {liquidator[:12]}...")
                                print(f"[ZOOM]    Liquidated {coin} @ ${px} size={sz}")

                                # Add to whale alerts
                                self._whale_alerts.append({
                                    'type': 'LIQUIDATION',
                                    'wallet': wallet[:10] + '...',
                                    'liquidator': liquidator[:12] + '...',
                                    'coin': coin,
                                    'price': float(px) if px else 0,
                                    'size': float(sz) if sz else 0,
                                    'timestamp': time.time(),
                                    'msg': f"⚡ {coin} liquidated @ ${px} by {liquidator[:12]}..."
                                })

                                # Add liquidator to tracked whales for future monitoring
                                if liquidator not in self.TRACKED_WHALES:
                                    print(f"[ZOOM] 🎯 Adding liquidator to tracked wallets")
                                    # Note: This adds to instance, not class
                                    self._dynamic_tracked_wallets = getattr(self, '_dynamic_tracked_wallets', set())
                                    self._dynamic_tracked_wallets.add(liquidator)
                            break

            except Exception as e:
                print(f"[ZOOM] Error identifying liquidator: {e}")

    def _refresh_positions(self):
        """Poll positions for all tracked wallets."""
        print(f"[PositionRefresher] Starting full refresh...")

        if not os.path.exists(self.db_path):
            print(f"[PositionRefresher] DB not found: {self.db_path}")
            return

        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        cursor = conn.cursor()

        # Use tracked whale list, not just positions in DB (positions may be stale/deleted)
        wallets = list(self.TRACKED_WHALES)[:100]  # Limit to 100 for performance
        print(f"[PositionRefresher] Refreshing {len(wallets)} tracked wallets")

        # Get all mid prices
        mid_prices = self._get_all_mids()
        volumes = self._get_asset_volumes()

        updated = 0
        skipped = 0
        for wallet in wallets:
            # Skip priority wallets - they're refreshed separately at higher frequency
            if wallet in self._priority_wallets:
                skipped += 1
                continue

            try:
                state = self._get_clearinghouse_state(wallet)
                if state:
                    self._update_wallet_positions(conn, wallet, state, mid_prices, volumes)
                    updated += 1
            except Exception as e:
                print(f"[PositionRefresher] Error polling {wallet[:10]}...: {e}")

            # Reduced delay between requests (was 0.1)
            time.sleep(0.05)

        conn.commit()

        # Cleanup truly old positions (5 minutes) - prevents zombie data
        delete_threshold = time.time() - POSITION_DELETE_SECONDS
        cursor.execute("DELETE FROM positions WHERE updated_at < ?", (delete_threshold,))
        deleted = cursor.rowcount
        if deleted > 0:
            print(f"[PositionRefresher] Cleaned up {deleted} old positions (>5min)")
        conn.commit()

        # Identify priority wallets for zoom mode
        self._identify_priority_wallets(conn)

        conn.close()
        print(f"[PositionRefresher] Updated {updated} wallets")

    def _identify_priority_wallets(self, conn):
        """Find wallets with positions close to liquidation and enable zoom mode."""
        cursor = conn.cursor()
        stale_threshold = time.time() - POSITION_STALENESS_SECONDS

        # Find positions within zoom threshold (close to liquidation)
        # Only include positions where 0 < distance <= threshold (actually close to liq)
        cursor.execute("""
            SELECT wallet_address, coin, side, position_value, distance_to_liq_pct, liquidation_price
            FROM positions
            WHERE distance_to_liq_pct > 0
              AND distance_to_liq_pct <= ?
              AND position_value >= 10000
              AND updated_at >= ?
            ORDER BY distance_to_liq_pct ASC
        """, (self.ZOOM_THRESHOLD_PCT, stale_threshold))

        new_priority = set()
        zoom_positions = []

        for row in cursor.fetchall():
            wallet, coin, side, value, dist_pct, liq_price = row
            new_priority.add(wallet)
            zoom_positions.append({
                'wallet': wallet[:10] + '...',
                'coin': coin,
                'side': side,
                'value': float(value),
                'dist_pct': float(dist_pct),
                'liq_price': float(liq_price)
            })

        # Update state
        old_count = len(self._priority_wallets)
        self._priority_wallets = new_priority
        self._zoom_positions = zoom_positions
        self._zoom_mode = len(new_priority) > 0

        # Log changes
        if len(new_priority) > old_count:
            print(f"[ZOOM] 🔍 ZOOM MODE ACTIVATED: {len(new_priority)} wallets within {self.ZOOM_THRESHOLD_PCT}% of liquidation")
            for pos in zoom_positions[:3]:  # Show top 3
                print(f"[ZOOM]   → {pos['coin']} {pos['side']} ${pos['value']:,.0f} @ {pos['dist_pct']:.2f}%")
        elif len(new_priority) == 0 and old_count > 0:
            print(f"[ZOOM] Zoom mode deactivated - no positions near liquidation")

        # Check for zone changes and alert
        self._check_zone_alerts(conn)

    def _check_zone_alerts(self, conn):
        """Check for positions entering danger zones and alert."""
        cursor = conn.cursor()

        # Get all positions with distance data
        cursor.execute("""
            SELECT wallet_address, coin, side, position_value, distance_to_liq_pct, impact_score
            FROM positions
            WHERE distance_to_liq_pct IS NOT NULL
              AND distance_to_liq_pct > 0
              AND position_value > 20000
            ORDER BY distance_to_liq_pct ASC
        """)

        current_zones = {}
        alerts = []

        for row in cursor.fetchall():
            wallet, coin, side, value, dist, impact = row
            key = f"{wallet}_{coin}"

            # Determine zone
            if dist < 1:
                zone = "DANGER"
            elif dist < 3:
                zone = "WARNING"
            elif dist < 5:
                zone = "WATCH"
            else:
                zone = "SAFE"

            current_zones[key] = zone

            # Check if zone changed
            prev_zone = self._previous_zones.get(key)
            if prev_zone and prev_zone != zone:
                # Zone changed - check if it got worse
                zone_order = {"SAFE": 0, "WATCH": 1, "WARNING": 2, "DANGER": 3}
                if zone_order.get(zone, 0) > zone_order.get(prev_zone, 0):
                    alerts.append({
                        'coin': coin,
                        'side': side,
                        'value': value,
                        'dist': dist,
                        'impact': impact or 0,
                        'from_zone': prev_zone,
                        'to_zone': zone,
                        'wallet': wallet[:10] + '...'
                    })

        # Update tracking
        self._previous_zones = current_zones

        # Print alerts
        now = time.time()
        if alerts and (now - self._last_zone_alert) > 10:  # Rate limit alerts
            self._last_zone_alert = now
            print(f"\n{'='*60}")
            print(f"⚠️  ZONE ALERTS - {len(alerts)} position(s) moved closer to liquidation")
            print(f"{'='*60}")
            for alert in alerts:
                impact_str = f" (impact: {alert['impact']:.0f}%)" if alert['impact'] > 10 else ""
                print(f"  🔴 {alert['coin']} {alert['side']} ${alert['value']:,.0f}")
                print(f"     {alert['from_zone']} → {alert['to_zone']} @ {alert['dist']:.2f}%{impact_str}")
            print(f"{'='*60}\n")

    def _update_zoom_positions(self):
        """Update zoom position details from database."""
        if not os.path.exists(self.db_path):
            return

        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        stale_threshold = time.time() - POSITION_STALENESS_SECONDS

        cursor.execute("""
            SELECT wallet_address, coin, side, position_value, distance_to_liq_pct, liquidation_price
            FROM positions
            WHERE distance_to_liq_pct > 0
              AND distance_to_liq_pct <= ?
              AND position_value >= 10000
              AND updated_at >= ?
            ORDER BY distance_to_liq_pct ASC
        """, (self.ZOOM_THRESHOLD_PCT, stale_threshold))

        zoom_positions = []
        for row in cursor.fetchall():
            wallet, coin, side, value, dist_pct, liq_price = row
            zoom_positions.append({
                'wallet': wallet[:10] + '...',
                'coin': coin,
                'side': side,
                'value': float(value),
                'dist_pct': float(dist_pct),
                'liq_price': float(liq_price)
            })

        self._zoom_positions = zoom_positions
        conn.close()

    def _get_clearinghouse_state(self, wallet: str) -> Optional[Dict]:
        """Get clearinghouse state for a wallet."""
        try:
            resp = requests.post(
                self.HYPERLIQUID_API,
                json={"type": "clearinghouseState", "user": wallet},
                timeout=10
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    def _get_all_mids(self) -> Dict[str, float]:
        """Get all mid prices."""
        try:
            resp = requests.post(
                self.HYPERLIQUID_API,
                json={"type": "allMids"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return {k: float(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _get_asset_volumes(self) -> Dict[str, float]:
        """Get 24h volumes for all assets."""
        try:
            resp = requests.post(
                self.HYPERLIQUID_API,
                json={"type": "metaAndAssetCtxs"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) >= 2:
                    meta = data[0]
                    asset_ctxs = data[1]
                    universe = meta.get('universe', [])
                    volumes = {}
                    for i, ctx in enumerate(asset_ctxs):
                        if i < len(universe):
                            coin = universe[i].get('name', '')
                            volumes[coin] = float(ctx.get('dayNtlVlm', 0))
                    return volumes
        except Exception:
            pass
        return {}

    def _fetch_recent_high_low(self, coin: str, minutes: int = 15) -> tuple:
        """Fetch recent high/low from candles for liq touch detection.

        Returns (high, low) for the last N minutes.
        """
        try:
            import time as time_module
            end_time = int(time_module.time() * 1000)
            start_time = end_time - (minutes * 60 * 1000)

            resp = requests.post(
                self.HYPERLIQUID_API,
                json={
                    'type': 'candleSnapshot',
                    'req': {
                        'coin': coin,
                        'interval': '1m',
                        'startTime': start_time,
                        'endTime': end_time
                    }
                },
                timeout=10
            )

            if resp.status_code == 200:
                candles = resp.json()
                if isinstance(candles, list) and candles:
                    highs = [float(c.get('h', 0)) for c in candles]
                    lows = [float(c.get('l', float('inf'))) for c in candles]
                    return max(highs), min(lows)
        except Exception:
            pass
        return 0.0, float('inf')

    def _update_wallet_positions(self, conn, wallet: str, state: Dict,
                                  mid_prices: Dict[str, float], volumes: Dict[str, float],
                                  skip_candle_fetch: bool = False):
        """Update positions for a wallet in the database.

        Also deletes positions that no longer exist (closed or liquidated).
        Args:
            skip_candle_fetch: If True, skip candle API calls for liq touch detection (faster)
        """
        positions = state.get('assetPositions', [])

        # Track which coins have active positions
        active_coins = set()

        for pos_data in positions:
            pos = pos_data.get('position', {})
            coin = pos.get('coin', '')
            szi = float(pos.get('szi', 0))

            if abs(szi) == 0:
                continue

            active_coins.add(coin)
            side = 'LONG' if szi > 0 else 'SHORT'
            entry_price = float(pos.get('entryPx', 0))
            position_value = float(pos.get('positionValue', 0))
            leverage_info = pos.get('leverage', {})
            leverage = float(leverage_info.get('value', 1)) if isinstance(leverage_info, dict) else 1.0
            margin_used = float(pos.get('marginUsed', 0))
            unrealized_pnl = float(pos.get('unrealizedPnl', 0))

            # If no liq price from API, position is well-collateralized - skip
            liq_price = pos.get('liquidationPx')
            if liq_price is None:
                continue
            liq_price = float(liq_price)
            if liq_price <= 0:
                continue

            # Calculate distance to liquidation (negative = past liquidation)
            current_price = mid_prices.get(coin, 0)
            distance_pct = 999.0
            if current_price > 0 and liq_price and liq_price > 0:
                if side == 'LONG':
                    distance_pct = ((current_price - liq_price) / current_price) * 100
                else:
                    distance_pct = ((liq_price - current_price) / current_price) * 100
                # Don't clamp to 0 - negative means PAST liquidation level

            # Calculate impact score
            daily_volume = volumes.get(coin, 0)
            impact_score = (position_value / daily_volume * 100) if daily_volume > 0 else 0

            # Check if liq level was touched recently
            liq_touched = 0
            liq_breached = 0
            recent_high = 0.0
            recent_low = float('inf')

            # If distance is negative, position has already breached liq level - skip it
            # These are "zombie" positions that passed liq but account hasn't liquidated (cross-margin)
            if distance_pct < 0:
                # Don't store zombie positions - they're not useful for trading signals
                continue

            # Check candles for positions close to liq (within 5%)
            # Skip candle fetch for priority refresh to maintain speed
            if not skip_candle_fetch and 0 < distance_pct < 5 and liq_price and liq_price > 0:
                try:
                    recent_high, recent_low = self._fetch_recent_high_low(coin, minutes=15)

                    if side == 'LONG':
                        # For longs, check if low went below liq
                        if recent_low <= liq_price:
                            liq_breached = 1
                            liq_touched = 1
                        elif recent_low <= liq_price * 1.01:  # Within 1% of liq
                            liq_touched = 1
                    else:
                        # For shorts, check if high went above liq
                        if recent_high >= liq_price:
                            liq_breached = 1
                            liq_touched = 1
                        elif recent_high >= liq_price * 0.99:  # Within 1% of liq
                            liq_touched = 1
                except Exception:
                    pass

            # Upsert position
            conn.execute("""
                INSERT OR REPLACE INTO positions
                (wallet_address, coin, side, entry_price, position_size, position_value,
                 leverage, liquidation_price, margin_used, unrealized_pnl,
                 distance_to_liq_pct, daily_volume, impact_score, updated_at,
                 liq_touched, liq_breached, recent_high, recent_low)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet, coin, side, entry_price, abs(szi), position_value,
                leverage, liq_price, margin_used, unrealized_pnl,
                distance_pct, daily_volume, impact_score, time.time(),
                liq_touched, liq_breached, recent_high, recent_low if recent_low != float('inf') else 0
            ))

        # Delete positions for this wallet that no longer exist (closed or liquidated)
        if active_coins:
            # First, detect which positions are being liquidated/closed
            placeholders = ','.join('?' * len(active_coins))
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT coin, side, position_value, liquidation_price, distance_to_liq_pct
                FROM positions
                WHERE wallet_address = ? AND coin NOT IN ({placeholders})
            """, (wallet, *active_coins))
            liquidated = cursor.fetchall()

            # Log liquidation events
            for pos in liquidated:
                coin = pos['coin']
                side = pos['side']
                value = pos['position_value']
                liq_px = pos['liquidation_price']
                dist = pos['distance_to_liq_pct']
                print(f"[LIQUIDATED] ⚡ {coin} {side} ${value:,.0f} @ ${liq_px:,.2f} (was {dist:.1f}% away)")

            # Now delete them
            conn.execute(f"""
                DELETE FROM positions
                WHERE wallet_address = ? AND coin NOT IN ({placeholders})
            """, (wallet, *active_coins))
        else:
            # Empty API response - check if wallet previously had positions
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM positions WHERE wallet_address = ?", (wallet,))
            result = cursor.fetchone()
            prev_count = result[0] if result else 0

            if prev_count > 3:
                # Suspicious - wallet had positions but now returns empty
                # Could be API error, don't delete
                print(f"[WARNING] Wallet {wallet[:12]}... returned empty but had {prev_count} positions - keeping data")
            else:
                # Wallet genuinely has no positions, delete any stale records
                conn.execute("DELETE FROM positions WHERE wallet_address = ?", (wallet,))


# ==============================================================================
# Background Orderbook Refresher
# ==============================================================================

class OrderbookRefresher(threading.Thread):
    """Background thread that polls Hyperliquid L2 orderbook data."""

    HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"
    REFRESH_INTERVAL = 2  # seconds - orderbook needs frequent updates
    COINS = ["BTC", "ETH", "SOL"]

    def __init__(self):
        super().__init__(daemon=True)
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        """Main refresh loop."""
        print("[OrderbookRefresher] Started background orderbook refresh")
        while self._running:
            try:
                for coin in self.COINS:
                    book = self._get_l2_book(coin)
                    if book:
                        update_orderbook_cache(coin, book)
            except Exception as e:
                print(f"[OrderbookRefresher] Error: {e}")

            # Sleep in small increments
            for _ in range(self.REFRESH_INTERVAL * 2):
                if not self._running:
                    break
                time.sleep(0.5)

        print("[OrderbookRefresher] Stopped")

    def _get_l2_book(self, coin: str) -> Optional[Dict]:
        """Get L2 order book for a coin."""
        try:
            resp = requests.post(
                self.HYPERLIQUID_API,
                json={"type": "l2Book", "coin": coin},
                timeout=5
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            levels = data.get("levels", [[], []])

            if len(levels) < 2:
                return None

            bids_raw = levels[0]
            asks_raw = levels[1]

            # Calculate mid price
            if bids_raw and asks_raw:
                try:
                    mid_price = (float(bids_raw[0]["px"]) + float(asks_raw[0]["px"])) / 2
                except (ValueError, KeyError):
                    mid_price = 0
            else:
                mid_price = 0

            # Parse bids
            bids = []
            cumulative = 0.0
            for level in bids_raw[:20]:
                try:
                    price = float(level["px"])
                    size = float(level["sz"])
                    value = price * size
                    cumulative += value
                    pct_from_mid = ((price / mid_price) - 1) * 100 if mid_price > 0 else 0
                    bids.append({
                        "price": price,
                        "size": size,
                        "value": value,
                        "cumulative": cumulative,
                        "pct_from_mid": pct_from_mid
                    })
                except (ValueError, KeyError):
                    continue

            # Parse asks
            asks = []
            cumulative = 0.0
            for level in asks_raw[:20]:
                try:
                    price = float(level["px"])
                    size = float(level["sz"])
                    value = price * size
                    cumulative += value
                    pct_from_mid = ((price / mid_price) - 1) * 100 if mid_price > 0 else 0
                    asks.append({
                        "price": price,
                        "size": size,
                        "value": value,
                        "cumulative": cumulative,
                        "pct_from_mid": pct_from_mid
                    })
                except (ValueError, KeyError):
                    continue

            return {
                "coin": coin,
                "mid_price": mid_price,
                "bids": bids,
                "asks": asks,
                "total_bid_depth": bids[-1]["cumulative"] if bids else 0,
                "total_ask_depth": asks[-1]["cumulative"] if asks else 0,
                "timestamp": time.time()
            }

        except Exception as e:
            print(f"[OrderbookRefresher] Error fetching {coin}: {e}")
            return None


# ==============================================================================
# Widget Classes
# ==============================================================================

class RedScreenOfDeath(QWidget):
    """Fatal error display."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #440000; color: #ff3333;")
        layout = QVBoxLayout()

        title = QLabel("SYSTEM HALTED")
        title.setFont(QFont("Consolas", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.detail = QLabel("")
        self.detail.setStyleSheet("font-size: 16px; color: white;")
        self.detail.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.detail)
        layout.addStretch()
        self.setLayout(layout)

    def set_error(self, message):
        self.detail.setText(f"{message}")


class PriceTickerWidget(QFrame):
    """Horizontal price ticker showing all symbols."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")
        self.setFixedHeight(32)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(20)

        self.price_labels = {}
        for symbol in TOP_10_SYMBOLS:
            short = symbol.replace("USDT", "")
            label = QLabel(f"{short} --")
            label.setFont(QFont("Consolas", 10))
            label.setStyleSheet(f"color: {COLORS['text_dim']};")
            self.price_labels[symbol] = label
            layout.addWidget(label)

        layout.addStretch()
        self.setLayout(layout)

    def update_data(self, prices: Dict[str, Dict]):
        """Update price display."""
        for symbol, data in prices.items():
            if symbol in self.price_labels:
                price = data.get('price')
                short = data.get('symbol_short', symbol)
                if price:
                    if price >= 1000:
                        text = f"{short} ${price:,.0f}"
                    elif price >= 1:
                        text = f"{short} ${price:.2f}"
                    else:
                        text = f"{short} ${price:.4f}"
                    self.price_labels[symbol].setText(text)
                    self.price_labels[symbol].setStyleSheet(f"color: {COLORS['text']};")


class LiquidationProximityTable(QTableWidget):
    """Table showing all liquidation proximity data sorted by value."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Symbol", "Side", "Count", "Value", "Dist %"])

        # Style
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                gridline-color: #222;
                alternate-background-color: #1a1a2a;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 4px;
                border: none;
            }}
            QTableWidget::item {{
                padding: 2px;
                background-color: {COLORS['panel_bg']};
            }}
            QTableWidget::item:alternate {{
                background-color: #1a1a2a;
            }}
        """)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

    def update_data(self, positions: List[Dict]):
        """Update table with aggregated positions."""
        self.setRowCount(len(positions))

        for row, pos in enumerate(positions):
            # Symbol
            item = QTableWidgetItem(pos['symbol'])
            item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 0, item)

            # Side
            side_item = QTableWidgetItem(pos['side'])
            side_item.setFont(QFont("Consolas", 9))
            color = COLORS['long'] if pos['side'] == 'LONG' else COLORS['short']
            side_item.setForeground(QColor(color))
            self.setItem(row, 1, side_item)

            # Count
            count_item = QTableWidgetItem(str(pos['count']))
            count_item.setFont(QFont("Consolas", 9))
            self.setItem(row, 2, count_item)

            # Value
            value_item = QTableWidgetItem(format_value(pos['value']))
            value_item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 3, value_item)

            # Distance %
            dist = pos['distance_pct']
            dist_item = QTableWidgetItem(f"{dist:.2f}%")
            dist_item.setFont(QFont("Consolas", 9))

            # Color by proximity
            if dist < 0.2:
                dist_item.setForeground(QColor(COLORS['short']))  # Red - critical
            elif dist < 0.35:
                dist_item.setForeground(QColor(COLORS['critical']))  # Orange
            elif dist < 0.5:
                dist_item.setForeground(QColor(COLORS['warning']))  # Yellow
            else:
                dist_item.setForeground(QColor(COLORS['text_dim']))

            self.setItem(row, 4, dist_item)

        self.resizeRowsToContents()


class HyperliquidPositionsTable(QTableWidget):
    """Table showing individual Hyperliquid positions by potential market impact."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(["Address", "Coin", "Side", "Value", "Liq Price", "Dist %", "Impact"])

        # Style
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                gridline-color: #222;
                alternate-background-color: #1a1a2a;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 4px;
                border: none;
            }}
            QTableWidget::item {{
                padding: 2px;
                background-color: {COLORS['panel_bg']};
            }}
            QTableWidget::item:alternate {{
                background-color: #1a1a2a;
            }}
        """)

        # Set column widths - prioritize Coin and critical data visibility
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.setColumnWidth(0, 70)   # Address (narrow)
        self.setColumnWidth(1, 75)   # Coin (important!)
        self.setColumnWidth(2, 50)   # Side
        self.setColumnWidth(3, 60)   # Value
        self.setColumnWidth(4, 75)   # Liq Price
        self.setColumnWidth(5, 50)   # Dist %
        self.setColumnWidth(6, 65)   # Price/Impact
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

    def update_data(self, positions: List[Dict]):
        """Update table with individual Hyperliquid positions."""
        self.setRowCount(len(positions))

        # Check if using live data (WS source)
        is_live_data = positions and positions[0].get('is_live', False)
        if is_live_data:
            self.setHorizontalHeaderLabels(["🔴 LIVE", "Coin", "Side", "Value", "Liq Price", "Dist %", "Price"])
        else:
            self.setHorizontalHeaderLabels(["Address", "Coin", "Side", "Value", "Liq Price", "Dist %", "Impact"])

        for row, pos in enumerate(positions):
            # Address (shortened) - show LIVE indicator for live data
            addr = pos.get('wallet_address', '')
            short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
            if pos.get('is_live'):
                addr_item = QTableWidgetItem(f"● {short_addr}")
                addr_item.setForeground(QColor("#ff4444"))  # Red dot for live
            else:
                addr_item = QTableWidgetItem(short_addr)
                addr_item.setForeground(QColor(COLORS['text_dim']))
            addr_item.setFont(QFont("Consolas", 8))
            self.setItem(row, 0, addr_item)

            # Coin
            coin_item = QTableWidgetItem(pos.get('coin', ''))
            coin_item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 1, coin_item)

            # Side
            side = pos.get('side', '')
            side_item = QTableWidgetItem(side)
            side_item.setFont(QFont("Consolas", 9))
            color = COLORS['long'] if side == 'LONG' else COLORS['short']
            side_item.setForeground(QColor(color))
            self.setItem(row, 2, side_item)

            # Value
            value = pos.get('position_value', 0)
            value_item = QTableWidgetItem(format_value(value))
            value_item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 3, value_item)

            # Liquidation Price - high precision for accurate tracking
            liq_price = pos.get('liquidation_price', 0)
            if liq_price and liq_price > 0:
                if liq_price >= 10000:
                    liq_text = f"${liq_price:,.0f}"  # BTC: $91,312
                elif liq_price >= 100:
                    liq_text = f"${liq_price:,.2f}"  # SOL: $187.42
                elif liq_price >= 1:
                    liq_text = f"${liq_price:.4f}"   # XRP: $2.0712
                elif liq_price >= 0.01:
                    liq_text = f"${liq_price:.5f}"   # SHIB: $0.00002
                else:
                    liq_text = f"${liq_price:.6f}"   # Tiny shitcoins
            else:
                liq_text = "--"
            liq_item = QTableWidgetItem(liq_text)
            liq_item.setFont(QFont("Consolas", 9))
            liq_item.setForeground(QColor(COLORS['warning']))
            self.setItem(row, 4, liq_item)

            # Distance % (negative = past liquidation) with liq touch status
            dist = pos.get('distance_to_liq_pct', 999)
            liq_touched = pos.get('liq_touched', 0)
            liq_breached = pos.get('liq_breached', 0)

            if liq_breached:
                # Price went past liquidation level - likely liquidated
                dist_item = QTableWidgetItem("⚡ LIQ!")
                dist_item.setForeground(QColor("#ff0000"))  # Bright red
            elif liq_touched:
                # Price touched/very close to liq level recently
                dist_item = QTableWidgetItem(f"🔥 {dist:.1f}%")
                dist_item.setForeground(QColor("#ff6600"))  # Orange - touched liq
            elif dist < 0:
                dist_item = QTableWidgetItem("⚡ LIQ!")
                dist_item.setForeground(QColor("#ff0000"))  # Bright red
            elif dist < 0.1:
                dist_item = QTableWidgetItem(f"⚠️ {dist:.2f}%")
                dist_item.setForeground(QColor(COLORS['short']))  # Red - critical
            else:
                dist_item = QTableWidgetItem(f"{dist:.1f}%")
                # Color by proximity
                if dist < 1.0:
                    dist_item.setForeground(QColor(COLORS['short']))  # Red - critical
                elif dist < 3.0:
                    dist_item.setForeground(QColor(COLORS['critical']))  # Orange
                elif dist < 5.0:
                    dist_item.setForeground(QColor(COLORS['warning']))  # Yellow
                else:
                    dist_item.setForeground(QColor(COLORS['text_dim']))
            dist_item.setFont(QFont("Consolas", 9))

            self.setItem(row, 5, dist_item)

            # Impact Score (% of daily volume) OR Current Price (for live data)
            if pos.get('is_live') and pos.get('current_price'):
                # Show current price for live data
                curr_price = pos.get('current_price', 0)
                if curr_price >= 10000:
                    price_text = f"${curr_price:,.0f}"
                elif curr_price >= 100:
                    price_text = f"${curr_price:,.2f}"
                elif curr_price >= 1:
                    price_text = f"${curr_price:.4f}"
                elif curr_price >= 0.01:
                    price_text = f"${curr_price:.5f}"
                else:
                    price_text = f"${curr_price:.6f}"
                impact_item = QTableWidgetItem(price_text)
                impact_item.setFont(QFont("Consolas", 9))
                impact_item.setForeground(QColor(COLORS['text']))
            else:
                # Show impact for database data
                impact = pos.get('impact_score', 0)
                if impact >= 1.0:
                    impact_text = f"{impact:.1f}%"
                elif impact >= 0.1:
                    impact_text = f"{impact:.2f}%"
                else:
                    impact_text = f"{impact:.3f}%"
                impact_item = QTableWidgetItem(impact_text)
                impact_item.setFont(QFont("Consolas", 9, QFont.Bold))

                # Color by impact (high impact = more dangerous)
                if impact >= 1.0:
                    impact_item.setForeground(QColor(COLORS['short']))  # Red - huge impact
                elif impact >= 0.1:
                    impact_item.setForeground(QColor(COLORS['critical']))  # Orange
                elif impact >= 0.01:
                    impact_item.setForeground(QColor(COLORS['warning']))  # Yellow
                else:
                    impact_item.setForeground(QColor(COLORS['text']))

            self.setItem(row, 6, impact_item)

        self.resizeRowsToContents()


class LiquidationHeatmapWidget(QFrame):
    """
    Visual heatmap showing liquidation level concentrations.

    Displays horizontal bars at each price level showing:
    - Red bars (left): Short liquidations (above current price)
    - Green bars (right): Long liquidations (below current price)
    - Bar width proportional to $ value at that level
    - Current price marked with horizontal line
    """

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")
        self.setMinimumHeight(300)
        self.setMinimumWidth(250)

        self._data = None
        self._coin = "BTC"
        self._price_range = 5.0  # +/- 5% from current price
        self._bucket_size = 0.25  # 0.25% buckets

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Header with coin selector
        header_layout = QHBoxLayout()

        title = QLabel("LIQUIDATION HEATMAP")
        title.setFont(QFont("Consolas", 9, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Coin buttons
        self.coin_buttons = {}
        for coin in ["BTC", "ETH", "SOL"]:
            btn = QPushButton(coin)
            btn.setCheckable(True)
            btn.setChecked(coin == self._coin)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['header']};
                    color: #000;
                    border: none;
                    padding: 2px 6px;
                    font-size: 9px;
                    font-weight: bold;
                    border-radius: 2px;
                }}
                QPushButton:!checked {{
                    background-color: {COLORS['panel_bg']};
                    color: {COLORS['text_dim']};
                    border: 1px solid {COLORS['border']};
                }}
            """)
            btn.clicked.connect(lambda checked, c=coin: self._set_coin(c))
            header_layout.addWidget(btn)
            self.coin_buttons[coin] = btn

        layout.addLayout(header_layout)

        # Summary row
        self.summary_label = QLabel("Loading...")
        self.summary_label.setFont(QFont("Consolas", 8))
        self.summary_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.summary_label)

        # Absorption status row
        self.absorption_label = QLabel("")
        self.absorption_label.setFont(QFont("Consolas", 8))
        self.absorption_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.absorption_label)

        # Scroll area for heatmap bars
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {COLORS['panel_bg']};
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['panel_bg']};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['border']};
                border-radius: 4px;
            }}
        """)

        self.heatmap_container = QWidget()
        self.heatmap_layout = QVBoxLayout()
        self.heatmap_layout.setContentsMargins(0, 0, 0, 0)
        self.heatmap_layout.setSpacing(1)
        self.heatmap_container.setLayout(self.heatmap_layout)
        scroll.setWidget(self.heatmap_container)

        layout.addWidget(scroll)

        # Legend
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(10)

        long_legend = QLabel("■ Long Liqs (below)")
        long_legend.setFont(QFont("Consolas", 8))
        long_legend.setStyleSheet(f"color: {COLORS['long']};")
        legend_layout.addWidget(long_legend)

        short_legend = QLabel("■ Short Liqs (above)")
        short_legend.setFont(QFont("Consolas", 8))
        short_legend.setStyleSheet(f"color: {COLORS['short']};")
        legend_layout.addWidget(short_legend)

        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        self.setLayout(layout)

    def _set_coin(self, coin: str):
        """Change the selected coin."""
        self._coin = coin
        for c, btn in self.coin_buttons.items():
            btn.setChecked(c == coin)
        self.refresh_data()

    def refresh_data(self):
        """Reload heatmap data from database and compute absorption analysis."""
        self._data = load_liquidation_heatmap_data(
            coin=self._coin,
            price_range_pct=self._price_range,
            bucket_size_pct=self._bucket_size
        )

        # Get orderbook for absorption analysis
        orderbook = get_cached_orderbook(self._coin)
        self._absorption = compute_absorption_analysis(self._data, orderbook)

        self._render_heatmap()

    def _render_heatmap(self):
        """Render the heatmap visualization."""
        # Clear existing bars
        while self.heatmap_layout.count():
            item = self.heatmap_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._data or not self._data.get("buckets"):
            no_data = QLabel("No liquidation data available")
            no_data.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 20px;")
            no_data.setAlignment(Qt.AlignCenter)
            self.heatmap_layout.addWidget(no_data)
            self.summary_label.setText("No data")
            return

        current_price = self._data["current_price"]
        max_value = self._data["max_bucket_value"]
        total_long = self._data["total_long_value"]
        total_short = self._data["total_short_value"]

        # Update summary
        self.summary_label.setText(
            f"{self._coin} @ ${current_price:,.0f} | "
            f"Longs: {format_value(total_long)} | "
            f"Shorts: {format_value(total_short)}"
        )

        # Update absorption status
        if hasattr(self, '_absorption') and self._absorption:
            abs_data = self._absorption
            if abs_data.get('no_book_data'):
                self.absorption_label.setText("Book: No data")
                self.absorption_label.setStyleSheet(f"color: {COLORS['text_dim']};")
            else:
                bid_depth = abs_data.get('total_bid_depth', 0)
                ask_depth = abs_data.get('total_ask_depth', 0)
                can_absorb_longs = abs_data.get('can_absorb_longs', True)
                can_absorb_shorts = abs_data.get('can_absorb_shorts', True)

                # Build status text
                long_status = "OK" if can_absorb_longs else "THIN"
                short_status = "OK" if can_absorb_shorts else "THIN"

                long_color = COLORS['long'] if can_absorb_longs else COLORS['short']
                short_color = COLORS['long'] if can_absorb_shorts else COLORS['short']

                self.absorption_label.setText(
                    f"Book: Bids {format_value(bid_depth)} ({long_status}) | "
                    f"Asks {format_value(ask_depth)} ({short_status})"
                )

                # Color based on worst case
                if not can_absorb_longs or not can_absorb_shorts:
                    self.absorption_label.setStyleSheet(f"color: {COLORS['warning']}; font-weight: bold;")
                else:
                    self.absorption_label.setStyleSheet(f"color: {COLORS['long']};")
        else:
            self.absorption_label.setText("Book: Loading...")

        if max_value == 0:
            no_data = QLabel("No positions in range")
            no_data.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 20px;")
            no_data.setAlignment(Qt.AlignCenter)
            self.heatmap_layout.addWidget(no_data)
            return

        # Render bars from highest price to lowest (top to bottom)
        buckets = sorted(self._data["buckets"], key=lambda b: -b["pct_from_current"])

        for bucket in buckets:
            pct = bucket["pct_from_current"]
            price = bucket["price_level"]
            long_val = bucket["long_value"]
            short_val = bucket["short_value"]
            total = bucket["total_value"]

            # Skip empty buckets
            if total < 1000:
                continue

            # Create row widget
            row = QWidget()
            row.setFixedHeight(18)
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            # Price label (left side)
            if price >= 1000:
                price_text = f"${price:,.0f}"
            elif price >= 1:
                price_text = f"${price:.2f}"
            else:
                price_text = f"${price:.4f}"

            pct_text = f"{pct:+.1f}%"
            price_label = QLabel(f"{pct_text}")
            price_label.setFixedWidth(45)
            price_label.setFont(QFont("Consolas", 8))
            price_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Highlight current price level
            if abs(pct) < self._bucket_size:
                price_label.setStyleSheet(f"color: {COLORS['header']}; font-weight: bold;")
            elif pct > 0:
                price_label.setStyleSheet(f"color: {COLORS['short']};")  # Above = shorts get liquidated
            else:
                price_label.setStyleSheet(f"color: {COLORS['long']};")  # Below = longs get liquidated

            row_layout.addWidget(price_label)

            # Bar container (center)
            bar_container = QWidget()
            bar_container.setFixedHeight(14)
            bar_layout = QHBoxLayout()
            bar_layout.setContentsMargins(0, 0, 0, 0)
            bar_layout.setSpacing(0)

            # Calculate bar widths (max 100px each side)
            max_bar_width = 80
            long_width = int((long_val / max_value) * max_bar_width) if max_value > 0 else 0
            short_width = int((short_val / max_value) * max_bar_width) if max_value > 0 else 0

            # Short bar (left side, red) - shorts liquidate above current price
            short_bar = QFrame()
            short_bar.setFixedSize(max_bar_width, 12)
            if short_width > 0 and pct > 0:  # Only show shorts above current price
                intensity = min(255, int(150 + (short_val / max_value) * 105))
                short_bar.setStyleSheet(f"""
                    background: qlineargradient(x1:1, y1:0, x2:0, y2:0,
                        stop:0 rgba({intensity}, 68, 68, 255),
                        stop:{short_width/max_bar_width:.2f} rgba({intensity}, 68, 68, 255),
                        stop:{short_width/max_bar_width + 0.01:.2f} transparent);
                    border-radius: 2px;
                """)
            else:
                short_bar.setStyleSheet("background: transparent;")
            bar_layout.addWidget(short_bar)

            # Center marker (current price line)
            center = QFrame()
            center.setFixedSize(2, 14)
            if abs(pct) < self._bucket_size:
                center.setStyleSheet(f"background-color: {COLORS['header']};")
            else:
                center.setStyleSheet(f"background-color: {COLORS['border']};")
            bar_layout.addWidget(center)

            # Long bar (right side, green) - longs liquidate below current price
            long_bar = QFrame()
            long_bar.setFixedSize(max_bar_width, 12)
            if long_width > 0 and pct < 0:  # Only show longs below current price
                intensity = min(255, int(150 + (long_val / max_value) * 105))
                long_bar.setStyleSheet(f"""
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(68, {intensity}, 68, 255),
                        stop:{long_width/max_bar_width:.2f} rgba(68, {intensity}, 68, 255),
                        stop:{long_width/max_bar_width + 0.01:.2f} transparent);
                    border-radius: 2px;
                """)
            else:
                long_bar.setStyleSheet("background: transparent;")
            bar_layout.addWidget(long_bar)

            bar_container.setLayout(bar_layout)
            row_layout.addWidget(bar_container)

            # Value label (right side)
            value_label = QLabel(format_value(total))
            value_label.setFixedWidth(50)
            value_label.setFont(QFont("Consolas", 8))
            value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            if total >= 1_000_000:
                value_label.setStyleSheet(f"color: {COLORS['short']}; font-weight: bold;")
            elif total >= 100_000:
                value_label.setStyleSheet(f"color: {COLORS['warning']};")
            else:
                value_label.setStyleSheet(f"color: {COLORS['text_dim']};")

            row_layout.addWidget(value_label)

            row.setLayout(row_layout)
            self.heatmap_layout.addWidget(row)

        # Add stretch at bottom
        self.heatmap_layout.addStretch()

    def update_data(self, data: Dict = None):
        """Update with new data or refresh from database."""
        if data:
            self._data = data
            self._render_heatmap()
        else:
            self.refresh_data()


class CascadeStateWidget(QFrame):
    """Panel showing cascade state machine status."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Title
        title = QLabel("CASCADE STATE")
        title.setFont(QFont("Consolas", 10, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        layout.addWidget(title)

        # Phase
        self.phase_label = QLabel("NONE")
        self.phase_label.setFont(QFont("Consolas", 16, QFont.Bold))
        self.phase_label.setAlignment(Qt.AlignCenter)
        self.phase_label.setStyleSheet(f"color: {COLORS['idle']}; padding: 5px;")
        layout.addWidget(self.phase_label)

        # Stats
        self.liq_label = QLabel("Liquidations (30s): 0")
        self.liq_label.setFont(QFont("Consolas", 9))
        self.liq_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.liq_label)

        self.total_label = QLabel("Total at risk: $0 (0 pos)")
        self.total_label.setFont(QFont("Consolas", 9))
        self.total_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.total_label)

        self.closest_label = QLabel("Closest: --")
        self.closest_label.setFont(QFont("Consolas", 9))
        self.closest_label.setStyleSheet(f"color: {COLORS['warning']};")
        layout.addWidget(self.closest_label)

        # Zoom mode indicator
        self.zoom_label = QLabel("")
        self.zoom_label.setFont(QFont("Consolas", 9, QFont.Bold))
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet(f"color: {COLORS['header']}; background-color: #1a3a3a; padding: 3px; border-radius: 3px;")
        self.zoom_label.hide()  # Hidden by default
        layout.addWidget(self.zoom_label)

        self.setLayout(layout)

    def update_data(self, state: Dict):
        """Update cascade state display."""
        phase = state.get('phase', 'NONE')
        self.phase_label.setText(phase)

        # Color by phase
        phase_colors = {
            "NONE": COLORS['idle'],
            "NO_DATA": COLORS['idle'],
            "MONITORING": COLORS['text_dim'],
            "PROXIMITY": COLORS['warning'],
            "LIQUIDATING": COLORS['critical'],
            "CASCADING": COLORS['short'],
            "ERROR": COLORS['short'],
        }
        color = phase_colors.get(phase, COLORS['idle'])
        self.phase_label.setStyleSheet(f"color: {color}; padding: 5px;")

        positions_at_risk = state.get('positions_at_risk', 0)
        self.liq_label.setText(f"Positions at risk: {positions_at_risk}")
        self.total_label.setText(
            f"Value at risk: {format_value(state.get('total_at_risk', 0))}"
        )

        closest = state.get('closest_pct')
        closest_sym = state.get('closest_symbol')
        if closest is not None and closest_sym:
            self.closest_label.setText(f"Closest: {closest_sym} ({closest:.1f}%)")
            # Color based on proximity
            if closest < 1.0:
                self.closest_label.setStyleSheet(f"color: {COLORS['short']}; font-weight: bold;")
            elif closest < 3.0:
                self.closest_label.setStyleSheet(f"color: {COLORS['warning']};")
            else:
                self.closest_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        else:
            self.closest_label.setText("Closest: --")
            self.closest_label.setStyleSheet(f"color: {COLORS['text_dim']};")

    def update_zoom_status(self, zoom_status: Dict):
        """Update zoom mode indicator."""
        if zoom_status.get('active'):
            count = zoom_status.get('priority_wallets', 0)
            positions = zoom_status.get('positions', [])
            if positions:
                top_pos = positions[0]
                self.zoom_label.setText(
                    f"🔍 ZOOM: {count} wallet(s) | {top_pos['coin']} {top_pos['dist_pct']:.2f}%"
                )
            else:
                self.zoom_label.setText(f"🔍 ZOOM: {count} wallet(s)")
            self.zoom_label.setStyleSheet(
                f"color: {COLORS['warning']}; background-color: #3a2a1a; "
                f"padding: 3px; border-radius: 3px; font-weight: bold;"
            )
            self.zoom_label.show()
        else:
            self.zoom_label.hide()


class CascadeWarningWidget(QFrame):
    """Panel showing cascade warnings - positions that will enter danger zone with price movement."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("⚠️ CASCADE WARNING")
        title.setFont(QFont("Consolas", 9, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['warning']};")
        title_row.addWidget(title)
        title_row.addStretch()

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(20, 20)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['border']};
                color: {COLORS['text']};
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['header']};
            }}
        """)
        self.refresh_btn.clicked.connect(self._refresh_cascade_data)
        title_row.addWidget(self.refresh_btn)
        layout.addLayout(title_row)

        # Summary labels - separate LONG (drop) and SHORT (rise) risk
        self.summary_longs = QLabel("▼ 5% drop: $0 LONGS at risk")
        self.summary_longs.setFont(QFont("Consolas", 9))
        self.summary_longs.setStyleSheet(f"color: {COLORS['short']};")
        layout.addWidget(self.summary_longs)

        self.summary_shorts = QLabel("▲ 5% rise: $0 SHORTS at risk")
        self.summary_shorts.setFont(QFont("Consolas", 9))
        self.summary_shorts.setStyleSheet(f"color: {COLORS['long']};")
        layout.addWidget(self.summary_shorts)

        self.summary_cascade = QLabel("Cascade risk: $0")
        self.summary_cascade.setFont(QFont("Consolas", 8))
        self.summary_cascade.setStyleSheet(f"color: {COLORS['warning']};")
        layout.addWidget(self.summary_cascade)

        # Coin breakdown table
        self.coin_table = QTableWidget()
        self.coin_table.setColumnCount(4)
        self.coin_table.setHorizontalHeaderLabels(["Coin", "Move", "Value", "Impact"])
        self.coin_table.setMaximumHeight(120)
        self.coin_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                font-size: 10px;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 2px;
                border: none;
                font-size: 9px;
            }}
            QTableWidget::item {{
                padding: 2px;
            }}
        """)
        self.coin_table.horizontalHeader().setStretchLastSection(True)
        self.coin_table.verticalHeader().setVisible(False)
        self.coin_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.coin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.coin_table)

        self.setLayout(layout)

        # Cache for cascade data
        self._cascade_data = []
        self._last_refresh = 0

    def _refresh_cascade_data(self):
        """Refresh cascade warning data from database.

        Improved calculation:
        1. Separates LONG (affected by drops) vs SHORT (affected by rises)
        2. Uses current price for value calculation
        3. Calculates cascade risk (high impact positions trigger more liquidations)
        """
        import sqlite3
        import time

        try:
            conn = sqlite3.connect(HL_INDEXED_DB_PATH, timeout=5)
            cursor = conn.cursor()

            # Get all positions with liquidation info
            cursor.execute("""
                SELECT coin, side, position_size, entry_price, liquidation_price,
                       impact_score, daily_volume
                FROM positions
                WHERE liquidation_price IS NOT NULL
                  AND liquidation_price > 0
                  AND position_size != 0
            """)

            rows = cursor.fetchall()
            conn.close()

            # Get current prices
            resp = requests.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'allMids'},
                timeout=5
            )
            mids = resp.json() if resp.status_code == 200 else {}

            # Separate tracking for LONGS (drop risk) and SHORTS (rise risk)
            longs_5pct = 0  # LONGS at risk from 5% drop
            shorts_5pct = 0  # SHORTS at risk from 5% rise
            cascade_risk = 0  # High-impact positions that trigger cascades

            targets_by_coin = {}

            for coin, side, size, entry, liq_px, impact, daily_vol in rows:
                current = float(mids.get(coin, 0))
                if current <= 0 or not size:
                    continue

                # Calculate current value (use current price, not entry)
                current_value = abs(float(size) * current)
                if current_value < 10000:  # Skip small positions
                    continue

                # Calculate distance to liquidation
                dist_now = abs(current - liq_px) / current * 100
                if dist_now < 3:  # Already in danger zone, skip
                    continue

                impact = impact or 0

                # Calculate move needed to bring position to 3% from liq
                target_dist = 3.0
                if side == 'LONG':
                    # LONG liquidates when price DROPS
                    # liq_px is below current price
                    price_at_danger = liq_px / (1 - target_dist / 100)
                    move_needed = (current - price_at_danger) / current * 100

                    if 0 < move_needed <= 5:
                        longs_5pct += current_value
                        # High impact positions add to cascade risk
                        if impact > 20:
                            cascade_risk += current_value * (impact / 100)
                else:
                    # SHORT liquidates when price RISES
                    # liq_px is above current price
                    price_at_danger = liq_px / (1 + target_dist / 100)
                    move_needed = (price_at_danger - current) / current * 100

                    if 0 < move_needed <= 5:
                        shorts_5pct += current_value
                        if impact > 20:
                            cascade_risk += current_value * (impact / 100)

                if move_needed < 0 or move_needed > 15:
                    continue

                # Track by coin for table
                if coin not in targets_by_coin:
                    targets_by_coin[coin] = {
                        'long_value': 0, 'short_value': 0,
                        'min_move': 100, 'impact': 0, 'side': side
                    }

                if side == 'LONG':
                    targets_by_coin[coin]['long_value'] += current_value
                else:
                    targets_by_coin[coin]['short_value'] += current_value

                targets_by_coin[coin]['min_move'] = min(targets_by_coin[coin]['min_move'], move_needed)
                targets_by_coin[coin]['impact'] = max(targets_by_coin[coin]['impact'], impact)

            # Update UI - separate LONG and SHORT risk
            self.summary_longs.setText(f"▼ 5% drop: ${longs_5pct:,.0f} LONGS")
            self.summary_shorts.setText(f"▲ 5% rise: ${shorts_5pct:,.0f} SHORTS")
            self.summary_cascade.setText(f"⚡ Cascade risk: ${cascade_risk:,.0f}")

            # Color based on risk level
            if longs_5pct > 5_000_000:
                self.summary_longs.setStyleSheet(f"color: {COLORS['short']}; font-weight: bold;")
            elif longs_5pct > 1_000_000:
                self.summary_longs.setStyleSheet(f"color: {COLORS['critical']};")
            else:
                self.summary_longs.setStyleSheet(f"color: {COLORS['text_dim']};")

            if shorts_5pct > 5_000_000:
                self.summary_shorts.setStyleSheet(f"color: {COLORS['long']}; font-weight: bold;")
            elif shorts_5pct > 1_000_000:
                self.summary_shorts.setStyleSheet(f"color: {COLORS['warning']};")
            else:
                self.summary_shorts.setStyleSheet(f"color: {COLORS['text_dim']};")

            if cascade_risk > 1_000_000:
                self.summary_cascade.setStyleSheet(f"color: {COLORS['critical']}; font-weight: bold;")
            else:
                self.summary_cascade.setStyleSheet(f"color: {COLORS['text_dim']};")

            # Update table - show total value and dominant side
            for coin in targets_by_coin:
                data = targets_by_coin[coin]
                data['value'] = data['long_value'] + data['short_value']
                # Show which side dominates
                if data['long_value'] > data['short_value']:
                    data['side'] = 'L'
                else:
                    data['side'] = 'S'

            sorted_coins = sorted(targets_by_coin.items(), key=lambda x: x[1]['value'], reverse=True)[:8]
            self.coin_table.setRowCount(len(sorted_coins))

            for i, (coin, data) in enumerate(sorted_coins):
                # Coin with side indicator
                coin_text = f"{coin} {data['side']}"
                self.coin_table.setItem(i, 0, QTableWidgetItem(coin_text))
                self.coin_table.setItem(i, 1, QTableWidgetItem(f"{data['min_move']:.1f}%"))
                self.coin_table.setItem(i, 2, QTableWidgetItem(f"${data['value']/1000:.0f}k"))
                self.coin_table.setItem(i, 3, QTableWidgetItem(f"{data['impact']:.0f}%"))

                # Color by side
                if data['side'] == 'L':
                    self.coin_table.item(i, 0).setForeground(QColor(COLORS['short']))
                else:
                    self.coin_table.item(i, 0).setForeground(QColor(COLORS['long']))

                # Color high impact red
                if data['impact'] > 30:
                    self.coin_table.item(i, 3).setForeground(QColor(COLORS['short']))
                elif data['impact'] > 10:
                    self.coin_table.item(i, 3).setForeground(QColor(COLORS['warning']))

                # Color small moves orange
                if data['min_move'] < 3:
                    self.coin_table.item(i, 1).setForeground(QColor(COLORS['critical']))

            self._last_refresh = time.time()

        except Exception as e:
            print(f"[CascadeWarning] Error: {e}")

    def showEvent(self, event):
        """Refresh data when widget becomes visible."""
        super().showEvent(event)
        if time.time() - self._last_refresh > 30:
            self._refresh_cascade_data()


class WhaleBiasWidget(QFrame):
    """Panel showing whale long/short bias for major coins."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("📊 WHALE BIAS")
        title.setFont(QFont("Consolas", 9, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        title_row.addWidget(title)
        title_row.addStretch()

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(20, 20)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['border']};
                color: {COLORS['text']};
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['header']};
            }}
        """)
        self.refresh_btn.clicked.connect(self._refresh_bias_data)
        title_row.addWidget(self.refresh_btn)
        layout.addLayout(title_row)

        # Summary label
        self.summary_label = QLabel("Loading whale positioning...")
        self.summary_label.setFont(QFont("Consolas", 8))
        self.summary_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.summary_label)

        # Bias table
        self.bias_table = QTableWidget()
        self.bias_table.setColumnCount(5)
        self.bias_table.setHorizontalHeaderLabels(["Coin", "Long $", "Short $", "Bias", "Signal"])
        self.bias_table.setMaximumHeight(140)
        self.bias_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                font-size: 10px;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 2px;
                border: none;
                font-size: 9px;
            }}
            QTableWidget::item {{
                padding: 2px;
            }}
        """)
        self.bias_table.horizontalHeader().setStretchLastSection(True)
        self.bias_table.verticalHeader().setVisible(False)
        self.bias_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.bias_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.bias_table)

        # Retail sentiment row
        self.retail_label = QLabel("Retail: -- wallets tracked")
        self.retail_label.setFont(QFont("Consolas", 8))
        self.retail_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.retail_label)

        self.setLayout(layout)

        # Cache
        self._last_refresh = 0
        self._bias_data = {}

    def _refresh_bias_data(self):
        """Refresh whale bias data from database."""
        import sqlite3
        import time

        try:
            conn = sqlite3.connect(HL_INDEXED_DB_PATH, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()

            # Get bias for major coins
            coins = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'HYPE']
            bias_data = []

            for coin in coins:
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN side='LONG' THEN ABS(position_value) ELSE 0 END) as long_val,
                        SUM(CASE WHEN side='SHORT' THEN ABS(position_value) ELSE 0 END) as short_val,
                        COUNT(DISTINCT wallet_address) as wallet_count
                    FROM positions
                    WHERE coin = ?
                """, (coin,))
                row = cursor.fetchone()

                long_val = float(row[0] or 0)
                short_val = float(row[1] or 0)
                total = long_val + short_val

                if total > 0:
                    long_pct = long_val / total * 100
                    short_pct = short_val / total * 100

                    # Determine signal
                    if short_pct > 75:
                        signal = "🔥 SQUEEZE"
                        signal_color = COLORS['long']
                    elif short_pct > 60:
                        signal = "↗ BEARISH"
                        signal_color = COLORS['short']
                    elif long_pct > 75:
                        signal = "⚠ DUMP RISK"
                        signal_color = COLORS['short']
                    elif long_pct > 60:
                        signal = "↘ BULLISH"
                        signal_color = COLORS['long']
                    else:
                        signal = "→ NEUTRAL"
                        signal_color = COLORS['text_dim']

                    bias_data.append({
                        'coin': coin,
                        'long_val': long_val,
                        'short_val': short_val,
                        'long_pct': long_pct,
                        'short_pct': short_pct,
                        'signal': signal,
                        'signal_color': signal_color,
                        'wallets': row[2] or 0
                    })

            # Get retail wallet count (small wallets <$100k)
            cursor.execute("""
                SELECT COUNT(DISTINCT wallet_address)
                FROM positions
                WHERE ABS(position_value) < 100000
            """)
            retail_count = cursor.fetchone()[0] or 0

            # Get total tracked wallets
            cursor.execute("SELECT COUNT(DISTINCT wallet_address) FROM positions")
            total_wallets = cursor.fetchone()[0] or 0

            conn.close()

            # Update table
            self.bias_table.setRowCount(len(bias_data))
            for i, data in enumerate(bias_data):
                # Coin
                item = QTableWidgetItem(data['coin'])
                item.setTextAlignment(Qt.AlignCenter)
                self.bias_table.setItem(i, 0, item)

                # Long value
                long_str = f"${data['long_val']/1e6:.1f}M" if data['long_val'] >= 1e6 else f"${data['long_val']/1e3:.0f}k"
                item = QTableWidgetItem(long_str)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setForeground(QColor(COLORS['long']))
                self.bias_table.setItem(i, 1, item)

                # Short value
                short_str = f"${data['short_val']/1e6:.1f}M" if data['short_val'] >= 1e6 else f"${data['short_val']/1e3:.0f}k"
                item = QTableWidgetItem(short_str)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setForeground(QColor(COLORS['short']))
                self.bias_table.setItem(i, 2, item)

                # Bias bar (text representation)
                bias_str = f"L:{data['long_pct']:.0f}% S:{data['short_pct']:.0f}%"
                item = QTableWidgetItem(bias_str)
                item.setTextAlignment(Qt.AlignCenter)
                # Color based on dominant side
                if data['short_pct'] > 60:
                    item.setForeground(QColor(COLORS['short']))
                elif data['long_pct'] > 60:
                    item.setForeground(QColor(COLORS['long']))
                self.bias_table.setItem(i, 3, item)

                # Signal
                item = QTableWidgetItem(data['signal'])
                item.setTextAlignment(Qt.AlignCenter)
                item.setForeground(QColor(data['signal_color']))
                self.bias_table.setItem(i, 4, item)

            # Update summary
            total_long = sum(d['long_val'] for d in bias_data)
            total_short = sum(d['short_val'] for d in bias_data)
            if total_long + total_short > 0:
                overall_short_pct = total_short / (total_long + total_short) * 100
                self.summary_label.setText(
                    f"Overall: {overall_short_pct:.0f}% SHORT | {total_wallets} wallets"
                )
                if overall_short_pct > 65:
                    self.summary_label.setStyleSheet(f"color: {COLORS['short']};")
                elif overall_short_pct < 35:
                    self.summary_label.setStyleSheet(f"color: {COLORS['long']};")
                else:
                    self.summary_label.setStyleSheet(f"color: {COLORS['text_dim']};")

            # Update retail label
            self.retail_label.setText(f"Retail (<$100k): {retail_count} wallets tracked")

            self._last_refresh = time.time()
            self._bias_data = bias_data

        except Exception as e:
            print(f"[WhaleBias] Error: {e}")

    def showEvent(self, event):
        """Refresh data when widget becomes visible."""
        super().showEvent(event)
        if time.time() - self._last_refresh > 30:
            self._refresh_bias_data()


class PositionsPnLWidget(QTableWidget):
    """Table showing current positions and P&L."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Symbol", "Side", "Entry", "Current", "P&L"])

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                alternate-background-color: #1a1a2a;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 4px;
                border: none;
            }}
            QTableWidget::item {{
                background-color: {COLORS['panel_bg']};
            }}
            QTableWidget::item:alternate {{
                background-color: #1a1a2a;
            }}
        """)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)

        # Placeholder
        self.setRowCount(1)
        item = QTableWidgetItem("No open positions")
        item.setForeground(QColor(COLORS['text_dim']))
        self.setItem(0, 0, item)

    def update_data(self, positions: List[Dict]):
        """Update positions display."""
        if not positions:
            self.setRowCount(1)
            item = QTableWidgetItem("No open positions")
            item.setForeground(QColor(COLORS['text_dim']))
            self.setItem(0, 0, item)
            return

        self.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self.setItem(row, 0, QTableWidgetItem(pos.get('symbol', '')))

            side_item = QTableWidgetItem(pos.get('side', ''))
            color = COLORS['long'] if pos.get('side') == 'LONG' else COLORS['short']
            side_item.setForeground(QColor(color))
            self.setItem(row, 1, side_item)

            self.setItem(row, 2, QTableWidgetItem(f"${pos.get('entry_price', 0):,.2f}"))
            self.setItem(row, 3, QTableWidgetItem(f"${pos.get('current_price', 0):,.2f}"))

            pnl = pos.get('pnl_pct', 0)
            pnl_item = QTableWidgetItem(f"{pnl:+.2f}%")
            pnl_item.setForeground(QColor(COLORS['profit'] if pnl >= 0 else COLORS['loss']))
            self.setItem(row, 4, pnl_item)


class OrderBookDepthWidget(QFrame):
    """Widget showing order book depth for top symbols."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title = QLabel("ORDER BOOK DEPTH")
        title.setFont(QFont("Consolas", 10, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        layout.addWidget(title)

        self.symbol_labels = {}
        for symbol in ["BTC", "ETH", "SOL"]:
            sym_layout = QVBoxLayout()
            sym_layout.setSpacing(1)

            sym_label = QLabel(f"{symbol}")
            sym_label.setFont(QFont("Consolas", 9, QFont.Bold))
            sym_label.setStyleSheet(f"color: {COLORS['text']};")
            sym_layout.addWidget(sym_label)

            bid_label = QLabel("Bid: --")
            bid_label.setFont(QFont("Consolas", 8))
            bid_label.setStyleSheet(f"color: {COLORS['long']};")
            sym_layout.addWidget(bid_label)

            ask_label = QLabel("Ask: --")
            ask_label.setFont(QFont("Consolas", 8))
            ask_label.setStyleSheet(f"color: {COLORS['short']};")
            sym_layout.addWidget(ask_label)

            self.symbol_labels[symbol] = {'bid': bid_label, 'ask': ask_label}
            layout.addLayout(sym_layout)

        layout.addStretch()
        self.setLayout(layout)

    def update_data(self, depth: List[Dict]):
        """Update order book depth display."""
        for d in depth:
            sym = d['symbol']
            if sym in self.symbol_labels:
                labels = self.symbol_labels[sym]

                bid_size = d.get('bid_size', 0)
                bid_price = d.get('bid_price', 0)
                if bid_size and bid_price:
                    labels['bid'].setText(f"Bid: {format_value(bid_size)} @ ${bid_price:,.0f}")
                else:
                    labels['bid'].setText("Bid: --")

                ask_size = d.get('ask_size', 0)
                ask_price = d.get('ask_price', 0)
                if ask_size and ask_price:
                    labels['ask'].setText(f"Ask: {format_value(ask_size)} @ ${ask_price:,.0f}")
                else:
                    labels['ask'].setText("Ask: --")


class TradeHistoryWidget(QFrame):
    """Widget showing recent trade history from database."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title = QLabel("TRADE HISTORY")
        title.setFont(QFont("Consolas", 10, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        layout.addWidget(title)

        self.trade_labels = []
        for i in range(10):
            label = QLabel("")
            label.setFont(QFont("Consolas", 8))
            label.setStyleSheet(f"color: {COLORS['text_dim']};")
            self.trade_labels.append(label)
            layout.addWidget(label)

        layout.addStretch()
        self.setLayout(layout)

        # Load initial trades
        self.refresh_trades()

    def refresh_trades(self):
        """Reload trades from database."""
        trades = load_recent_trades(limit=10)
        self.update_data(trades)

    def update_data(self, trades: List[Dict]):
        """Update trade history display."""
        for i, label in enumerate(self.trade_labels):
            if i < len(trades):
                trade = trades[i]
                ts = trade.get('timestamp', 0)
                time_str = datetime.fromtimestamp(ts).strftime('%H:%M') if ts else '--:--'
                symbol = trade.get('symbol', '').replace('USDT', '')
                side = trade.get('side', '')
                price = trade.get('price', 0)
                is_entry = trade.get('is_entry', True)

                action = "ENTRY" if is_entry else "EXIT"
                text = f"{time_str} {action:5} {symbol:4} {side:5} @ ${price:,.0f}"
                label.setText(text)

                color = COLORS['long'] if is_entry else COLORS['short']
                label.setStyleSheet(f"color: {color};")
            else:
                label.setText("")


class PrimitivesStatusRow(QFrame):
    """Compact row showing primitives count per symbol."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")
        self.setFixedHeight(24)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)

        label = QLabel("Primitives:")
        label.setFont(QFont("Consolas", 9))
        label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(label)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Consolas", 9))
        self.status_label.setStyleSheet(f"color: {COLORS['text']};")
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

    def update_data(self, counts: Dict[str, int]):
        """Update primitives count display."""
        parts = [f"{sym.replace('USDT', '')}({cnt})" for sym, cnt in counts.items() if cnt > 0]
        self.status_label.setText("  ".join(parts[:8]))  # Show up to 8


class ActivityLogRow(QFrame):
    """Single-line activity log at bottom."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")
        self.setFixedHeight(24)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 10, 2)

        self.label = QLabel("Dashboard started - click a position to view liquidation level")
        self.label.setFont(QFont("Consolas", 9))
        self.label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.label)

        self.setLayout(layout)

        self.messages = []

    def add_message(self, msg: str):
        """Add a new activity message."""
        ts = time.strftime("%H:%M:%S")
        self.messages.append(f"[{ts}] {msg}")
        self.messages = self.messages[-3:]  # Keep last 3
        self.label.setText("  |  ".join(self.messages))
        self.label.setStyleSheet(f"color: {COLORS['text']};")


# ==============================================================================
# Trading Chart Widget (Lightweight Charts via WebEngine)
# ==============================================================================

LIGHTWEIGHT_CHART_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #151525; overflow: hidden; }
        #chart { width: 100%; height: 100%; }
    </style>
</head>
<body>
    <div id="chart"></div>
    <script>
        const chart = LightweightCharts.createChart(document.getElementById('chart'), {
            width: window.innerWidth,
            height: window.innerHeight,
            layout: {
                background: { type: 'solid', color: '#151525' },
                textColor: '#888',
            },
            grid: {
                vertLines: { color: '#335' },
                horzLines: { color: '#335' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#335',
            },
            timeScale: {
                borderColor: '#335',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        const candleSeries = chart.addCandlestickSeries({
            upColor: '#4f4',
            downColor: '#f44',
            borderDownColor: '#f44',
            borderUpColor: '#4f4',
            wickDownColor: '#f44',
            wickUpColor: '#4f4',
            priceFormat: {
                type: 'price',
                precision: 8,
                minMove: 0.00000001,
            },
        });

        // Store price lines for liquidation levels
        let priceLinesMap = {};
        let currentPriceLine = null;
        window.hasInitialized = false;  // Initialize flag for chart fitting

        // Helper to determine precision based on price magnitude
        function getPrecision(price) {
            if (price >= 1000) return 2;
            if (price >= 1) return 4;
            if (price >= 0.01) return 6;
            return 8;
        }

        window.updateCandles = function(candles) {
            if (!candles || candles.length === 0) return;
            // Convert timestamps from ms to seconds
            const data = candles.map(c => ({
                time: Math.floor(c.time / 1000),
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close
            }));

            // Auto-adjust precision based on price
            const avgPrice = data.length > 0 ? data[data.length-1].close : 1;
            const precision = getPrecision(avgPrice);
            const minMove = Math.pow(10, -precision);

            candleSeries.applyOptions({
                priceFormat: {
                    type: 'price',
                    precision: precision,
                    minMove: minMove,
                }
            });

            candleSeries.setData(data);

            // Fit content when switching coins/timeframes (hasInitialized = false)
            if (!window.hasInitialized) {
                chart.timeScale().fitContent();
                // Also reset price scale to auto-fit the new data range
                chart.priceScale('right').applyOptions({ autoScale: true });
                window.hasInitialized = true;
            }
        };

        window.setCurrentPrice = function(price) {
            if (currentPriceLine) {
                candleSeries.removePriceLine(currentPriceLine);
            }
            currentPriceLine = candleSeries.createPriceLine({
                price: price,
                color: '#00ffff',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'Price',
            });
        };

        window.clearLiqLevels = function() {
            for (let id in priceLinesMap) {
                candleSeries.removePriceLine(priceLinesMap[id]);
            }
            priceLinesMap = {};
        };

        window.addLiqLevel = function(id, price, value, side, distance) {
            // Color based on side and distance
            let color;
            if (side === 'LONG') {
                color = distance < 2 ? '#ff0000' : distance < 5 ? '#ff4444' : '#ff6666';
            } else {
                color = distance < 2 ? '#00ff00' : distance < 5 ? '#44ff44' : '#66ff66';
            }

            // Short label for axis (shows on right price scale)
            const valueStr = value >= 1000000 ? `${(value/1000000).toFixed(1)}M` : `${Math.floor(value/1000)}K`;

            const line = candleSeries.createPriceLine({
                price: price,
                color: color,
                lineWidth: value > 500000 ? 2 : 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: '',  // Remove title from line itself (was obscuring view)
            });
            priceLinesMap[id] = line;

            // Add marker at left edge for label (if we have visible range)
            try {
                const visibleRange = chart.timeScale().getVisibleLogicalRange();
                if (visibleRange) {
                    const leftTime = Math.floor(visibleRange.from);
                    // Store marker info for batch update
                    if (!window.liqMarkers) window.liqMarkers = [];
                    window.liqMarkers.push({
                        time: leftTime,
                        position: side === 'LONG' ? 'belowBar' : 'aboveBar',
                        color: color,
                        shape: 'square',
                        text: `${valueStr} ${side.charAt(0)}`,
                        size: 0.5
                    });
                }
            } catch(e) {}
        };

        window.addEventListener('resize', () => {
            chart.applyOptions({ width: window.innerWidth, height: window.innerHeight });
        });
    </script>
</body>
</html>
'''

class TradingChartWidget(QFrame):
    """TradingView-quality candlestick chart using lightweight-charts."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Top row: Coin selector + Timeframe + Price
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        # Coin selector buttons
        self._coin_buttons = {}
        for coin in ['BTC', 'ETH', 'SOL', 'DOGE', 'WIF']:
            btn = QPushButton(coin)
            btn.setFixedHeight(24)
            btn.setFont(QFont("Consolas", 9))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['background']};
                    color: {COLORS['text_dim']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 3px;
                    padding: 2px 8px;
                }}
                QPushButton:checked {{
                    background-color: {COLORS['header']};
                    color: {COLORS['background']};
                }}
            """)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, c=coin: self._on_coin_clicked(c))
            top_row.addWidget(btn)
            self._coin_buttons[coin] = btn

        top_row.addWidget(QLabel(" | "))

        # Timeframe selector
        self._tf_buttons = {}
        for tf in ['1m', '5m', '15m', '1h']:
            btn = QPushButton(tf)
            btn.setFixedHeight(24)
            btn.setFixedWidth(35)
            btn.setFont(QFont("Consolas", 8))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['background']};
                    color: {COLORS['text_dim']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 3px;
                }}
                QPushButton:checked {{
                    background-color: {COLORS['warning']};
                    color: {COLORS['background']};
                }}
            """)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tf: self._on_tf_clicked(t))
            top_row.addWidget(btn)
            self._tf_buttons[tf] = btn
        self._tf_buttons['1m'].setChecked(True)
        self._current_tf = '1m'

        top_row.addStretch()

        # Current coin label (prominent display of selected coin)
        self._coin_label = QLabel("BTC")
        self._coin_label.setFont(QFont("Consolas", 14, QFont.Bold))
        self._coin_label.setStyleSheet(f"color: {COLORS['warning']}; padding: 0 10px;")
        top_row.addWidget(self._coin_label)

        # Current price label
        self._price_label = QLabel("$0.00")
        self._price_label.setFont(QFont("Consolas", 12, QFont.Bold))
        self._price_label.setStyleSheet(f"color: {COLORS['header']};")
        top_row.addWidget(self._price_label)

        layout.addLayout(top_row)

        # WebEngine view for lightweight-charts
        self._web_view = QWebEngineView()
        self._web_view.setHtml(LIGHTWEIGHT_CHART_HTML)
        self._web_view.setStyleSheet("background: #151525;")
        layout.addWidget(self._web_view)

        self.setLayout(layout)

        # State
        self._current_coin = 'BTC'
        self._coin_buttons['BTC'].setChecked(True)
        self._last_candles: Dict[str, list] = {}
        self._chart_ready = False
        self._fast_refresh_mode = True  # Start with fast refresh enabled
        self._last_coin_click_time = time.time()  # Track when coin was last clicked
        self._last_liq_hash = ""  # Track if liq levels changed
        self._last_candle_time = 0  # Track last candle timestamp

        # Wait for page to load before refreshing
        self._web_view.loadFinished.connect(self._on_page_loaded)

    def _on_page_loaded(self, ok):
        """Called when the web page finishes loading."""
        if ok:
            self._chart_ready = True
            print("[Chart] Lightweight-charts loaded successfully")
            self.refresh_chart()

    def _on_coin_clicked(self, coin: str):
        """Handle coin button click."""
        self._current_coin = coin
        self._coin_label.setText(coin)  # Update prominent coin label
        for c, btn in self._coin_buttons.items():
            btn.setChecked(c == coin)
        # Enable fast refresh for selected symbol (1 second updates)
        self._fast_refresh_mode = True
        self._last_coin_click_time = time.time()
        # Reset tracking for new coin
        self._last_candle_time = 0
        self._last_liq_hash = ""
        # Reset fit flag so chart fits when switching coins
        self._web_view.page().runJavaScript("window.hasInitialized = false;")
        self.refresh_chart(force_full=True)

    def _on_tf_clicked(self, tf: str):
        """Handle timeframe button click."""
        self._current_tf = tf
        for t, btn in self._tf_buttons.items():
            btn.setChecked(t == tf)
        # Reset tracking for new timeframe
        self._last_candle_time = 0
        # Reset fit flag so chart fits when changing timeframe
        self._web_view.page().runJavaScript("window.hasInitialized = false;")
        self.refresh_chart(force_full=True)

    def refresh_chart(self, force_full: bool = False):
        """Refresh chart with latest data.

        Args:
            force_full: Force full redraw (used when switching coins/timeframes)
        """
        if not self._chart_ready:
            return

        # Fetch candles
        candles = self._fetch_candles(self._current_coin, interval=self._current_tf)

        if not candles:
            return

        # Check if we have new data (compare last candle time)
        new_candle_time = candles[-1]['time'] if candles else 0
        has_new_candle = new_candle_time != self._last_candle_time

        if has_new_candle or force_full:
            print(f"[Chart] Updating {self._current_coin} ({self._current_tf}) - {len(candles)} candles")
            self._last_candle_time = new_candle_time

            # Update candles via JavaScript
            import json
            candles_json = json.dumps(candles)
            self._web_view.page().runJavaScript(f"updateCandles({candles_json});")

        # Always update current price (it changes even within same candle)
        current_price = candles[-1]['close']
        self._price_label.setText(f"${current_price:,.2f}")
        self._web_view.page().runJavaScript(f"setCurrentPrice({current_price});")

        # Update liquidation levels only if changed or forced
        self._update_liq_levels(current_price, force_redraw=force_full)

    def _fetch_candles(self, coin: str, interval: str = '1m', count: int = 100) -> list:
        """Fetch candles from Hyperliquid API."""
        try:
            # Calculate time range based on interval
            interval_mins = {'1m': 1, '5m': 5, '15m': 15, '1h': 60}.get(interval, 1)
            end_time = int(time.time() * 1000)
            start_time = end_time - (count * interval_mins * 60 * 1000)

            resp = requests.post(
                HYPERLIQUID_API,
                json={
                    'type': 'candleSnapshot',
                    'req': {
                        'coin': coin,
                        'interval': interval,
                        'startTime': start_time,
                        'endTime': end_time
                    }
                },
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                candles = []
                for c in data:
                    candles.append({
                        'time': c['t'],
                        'open': float(c['o']),
                        'high': float(c['h']),
                        'low': float(c['l']),
                        'close': float(c['c']),
                        'volume': float(c['v'])
                    })
                self._last_candles[coin] = candles
                return candles
        except Exception as e:
            print(f"[Chart] Error fetching candles: {e}")
        return self._last_candles.get(coin, [])

    def _update_liq_levels(self, current_price: float, force_redraw: bool = False):
        """Update liquidation level price lines only if changed."""
        try:
            conn = get_indexed_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT liquidation_price, position_value, side, distance_to_liq_pct
                FROM positions
                WHERE coin = ? AND distance_to_liq_pct > 0 AND distance_to_liq_pct < 10.0
                ORDER BY position_value DESC
                LIMIT 15
            """, (self._current_coin,))

            rows = cursor.fetchall()
            conn.close()

            # Create hash of current liq levels to detect changes
            liq_data = [(row['liquidation_price'], row['position_value'], row['side']) for row in rows]
            liq_hash = str(hash(tuple(liq_data)))

            # Skip redraw if nothing changed (unless forced)
            if liq_hash == self._last_liq_hash and not force_redraw:
                return

            self._last_liq_hash = liq_hash

            # Clear and redraw
            self._web_view.page().runJavaScript("clearLiqLevels();")
            print(f"[Chart] Redrawing {len(rows)} liq levels for {self._current_coin}")

            for i, row in enumerate(rows):
                liq_price = row['liquidation_price']
                value = row['position_value']
                side = row['side']
                distance = row['distance_to_liq_pct']

                if liq_price <= 0:
                    continue

                # Add price line via JavaScript
                self._web_view.page().runJavaScript(
                    f"addLiqLevel('liq_{i}', {liq_price}, {value}, '{side}', {distance});"
                )

        except Exception as e:
            print(f"[Chart] Error fetching liq levels: {e}")

    def show_our_position(self, entry_price: float, side: str, liq_price: float):
        """Show our current position on the chart."""
        # Add entry line (blue)
        self._web_view.page().runJavaScript(f"""
            addLiqLevel('our_entry', {entry_price}, 0, 'ENTRY', 0);
        """)
        # Add our liq line (orange)
        self._web_view.page().runJavaScript(f"""
            addLiqLevel('our_liq', {liq_price}, 0, 'OUR_LIQ', 0);
        """)

    def highlight_liq_price(self, liq_price: float, side: str):
        """Highlight a specific liquidation price with a prominent red line."""
        if not self._chart_ready or liq_price <= 0:
            return

        # Format price based on magnitude
        if liq_price >= 1000:
            price_str = f"${liq_price:,.0f}"
        elif liq_price >= 1:
            price_str = f"${liq_price:,.2f}"
        else:
            price_str = f"${liq_price:.6f}"

        # Add a prominent red price line for the clicked position's liquidation
        self._web_view.page().runJavaScript(f"""
            // Remove existing highlight if any
            if (window.highlightLine) {{
                candleSeries.removePriceLine(window.highlightLine);
            }}

            // Create prominent red line for liquidation price
            window.highlightLine = candleSeries.createPriceLine({{
                price: {liq_price},
                color: '#ff0000',
                lineWidth: 3,
                lineStyle: 0,
                axisLabelVisible: true,
                title: 'LIQ {side}'
            }});
        """)
        print(f"[Chart] Highlighted {side} liq @ {price_str}")


# ==============================================================================
# Quick Trade Panel Widget
# ==============================================================================

from PySide6.QtWidgets import QCheckBox, QSlider

class QuickTradePanel(QFrame):
    """Enhanced quick trade entry panel with full trading controls."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Row 1: Coin + Current Position
        row1 = QHBoxLayout()
        self.coin_label = QLabel("BTC")
        self.coin_label.setFont(QFont("Consolas", 12, QFont.Bold))
        self.coin_label.setStyleSheet(f"color: {COLORS['header']};")
        row1.addWidget(self.coin_label)

        self.position_label = QLabel("No Position")
        self.position_label.setFont(QFont("Consolas", 9))
        self.position_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        row1.addWidget(self.position_label)
        row1.addStretch()

        # Mode toggle
        self.ghost_check = QCheckBox("Ghost")
        self.ghost_check.setChecked(True)
        self.ghost_check.setStyleSheet(f"color: {COLORS['warning']};")
        row1.addWidget(self.ghost_check)
        layout.addLayout(row1)

        # Row 2: Size presets + custom
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        lbl = QLabel("Size:")
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        row2.addWidget(lbl)

        self._size_buttons = {}
        for size in ['$500', '$1K', '$2K', '$5K']:
            btn = QPushButton(size)
            btn.setFixedSize(40, 22)
            btn.setFont(QFont("Consolas", 8))
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['background']};
                    color: {COLORS['text_dim']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 2px;
                }}
                QPushButton:checked {{
                    background-color: {COLORS['header']};
                    color: {COLORS['background']};
                }}
            """)
            btn.clicked.connect(lambda checked, s=size: self._on_size_preset(s))
            row2.addWidget(btn)
            self._size_buttons[size] = btn
        self._size_buttons['$1K'].setChecked(True)

        self.size_input = QLineEdit("1000")
        self.size_input.setFixedWidth(55)
        self.size_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 2px;
                padding: 2px;
                font-size: 10px;
            }}
        """)
        row2.addWidget(self.size_input)
        row2.addStretch()
        layout.addLayout(row2)

        # Row 3: Leverage slider
        row3 = QHBoxLayout()
        row3.setSpacing(4)
        lbl = QLabel("Lev:")
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        row3.addWidget(lbl)

        self.lev_slider = QSlider(Qt.Horizontal)
        self.lev_slider.setRange(1, 50)
        self.lev_slider.setValue(5)
        self.lev_slider.setFixedWidth(120)
        self.lev_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {COLORS['border']};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['header']};
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
        """)
        self.lev_slider.valueChanged.connect(self._on_lev_changed)
        row3.addWidget(self.lev_slider)

        self.lev_label = QLabel("5x")
        self.lev_label.setFixedWidth(30)
        self.lev_label.setFont(QFont("Consolas", 10, QFont.Bold))
        self.lev_label.setStyleSheet(f"color: {COLORS['text']};")
        row3.addWidget(self.lev_label)

        # Lev presets
        for lev in [3, 5, 10, 20]:
            btn = QPushButton(f"{lev}x")
            btn.setFixedSize(28, 20)
            btn.setFont(QFont("Consolas", 8))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['background']};
                    color: {COLORS['text_dim']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 2px;
                }}
                QPushButton:hover {{ color: {COLORS['text']}; }}
            """)
            btn.clicked.connect(lambda _, l=lev: self._set_leverage(l))
            row3.addWidget(btn)
        row3.addStretch()
        layout.addLayout(row3)

        # Row 4: Entry options
        row4 = QHBoxLayout()
        row4.setSpacing(8)

        self.market_check = QCheckBox("Market")
        self.market_check.setChecked(True)
        self.market_check.setStyleSheet(f"color: {COLORS['text']}; font-size: 10px;")
        row4.addWidget(self.market_check)

        self.tick_check = QCheckBox("Enter on Tick")
        self.tick_check.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        row4.addWidget(self.tick_check)

        row4.addStretch()
        layout.addLayout(row4)

        # Row 5: Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.long_btn = QPushButton("LONG")
        self.long_btn.setFont(QFont("Consolas", 10, QFont.Bold))
        self.long_btn.setFixedHeight(32)
        self.long_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a3a1a;
                color: #4f4;
                border: 1px solid #4f4;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2a5a2a; }
            QPushButton:pressed { background-color: #3a7a3a; }
        """)
        self.long_btn.clicked.connect(self._on_long_clicked)
        btn_row.addWidget(self.long_btn)

        self.short_btn = QPushButton("SHORT")
        self.short_btn.setFont(QFont("Consolas", 10, QFont.Bold))
        self.short_btn.setFixedHeight(32)
        self.short_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a1a1a;
                color: #f44;
                border: 1px solid #f44;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a2a2a; }
            QPushButton:pressed { background-color: #7a3a3a; }
        """)
        self.short_btn.clicked.connect(self._on_short_clicked)
        btn_row.addWidget(self.short_btn)

        self.close_btn = QPushButton("CLOSE")
        self.close_btn.setFont(QFont("Consolas", 9))
        self.close_btn.setFixedHeight(32)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #aaa;
                border: 1px solid #555;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3a3a5a; }
        """)
        self.close_btn.clicked.connect(self._on_close_clicked)
        btn_row.addWidget(self.close_btn)

        layout.addLayout(btn_row)
        self.setLayout(layout)

        # State
        self._current_coin = "BTC"
        self._current_size = 1000.0

    def _on_size_preset(self, size_str: str):
        """Handle size preset button click."""
        sizes = {'$500': 500, '$1K': 1000, '$2K': 2000, '$5K': 5000}
        self._current_size = sizes.get(size_str, 1000)
        self.size_input.setText(str(int(self._current_size)))
        for s, btn in self._size_buttons.items():
            btn.setChecked(s == size_str)

    def _on_lev_changed(self, value: int):
        """Handle leverage slider change."""
        self.lev_label.setText(f"{value}x")

    def _set_leverage(self, lev: int):
        """Set leverage from preset button."""
        self.lev_slider.setValue(lev)

    def set_coin(self, coin: str):
        """Update the selected coin."""
        self._current_coin = coin
        self.coin_label.setText(coin)

    def update_position(self, position_info: dict):
        """Update current position display."""
        if position_info:
            side = position_info.get('side', '')
            size = position_info.get('size', 0)
            pnl = position_info.get('pnl', 0)
            color = COLORS['long'] if side == 'LONG' else COLORS['short']
            self.position_label.setText(f"{side} ${size:,.0f} ({pnl:+.1f}%)")
            self.position_label.setStyleSheet(f"color: {color};")
        else:
            self.position_label.setText("No Position")
            self.position_label.setStyleSheet(f"color: {COLORS['text_dim']};")

    def set_executor(self, executor):
        """Set the trade executor."""
        self._executor = executor

    def _get_params(self) -> tuple:
        """Get current trade parameters."""
        try:
            size = float(self.size_input.text())
            leverage = self.lev_slider.value()
            return size, leverage
        except ValueError:
            return 1000.0, 5

    def _on_long_clicked(self):
        """Handle LONG button click."""
        size, lev = self._get_params()
        symbol = f"{self._current_coin}USDT"
        ghost = self.ghost_check.isChecked()
        print(f"[QuickTrade] LONG {symbol} size=${size} lev={lev}x (ghost={ghost})")

        if hasattr(self, '_executor') and self._executor and hasattr(self._executor, 'enter_position'):
            self._executor.enter_position(symbol, "LONG", size, lev, ghost=ghost)

    def _on_short_clicked(self):
        """Handle SHORT button click."""
        size, lev = self._get_params()
        symbol = f"{self._current_coin}USDT"
        ghost = self.ghost_check.isChecked()
        print(f"[QuickTrade] SHORT {symbol} size=${size} lev={lev}x (ghost={ghost})")

        if hasattr(self, '_executor') and self._executor and hasattr(self._executor, 'enter_position'):
            self._executor.enter_position(symbol, "SHORT", size, lev, ghost=ghost)

    def _on_close_clicked(self):
        """Handle CLOSE button click."""
        symbol = f"{self._current_coin}USDT"
        ghost = self.ghost_check.isChecked()
        print(f"[QuickTrade] CLOSE {symbol} (ghost={ghost})")

        if hasattr(self, '_executor') and self._executor and hasattr(self._executor, 'close_position'):
            self._executor.close_position(symbol, ghost=ghost)


# ==============================================================================
# Main Window
# ==============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Liquidation Trading System")
        self.resize(1200, 800)
        self.start_time = time.time()

        # 1. Initialize Core Systems
        self.obs_system = ObservationSystem(TOP_10_SYMBOLS)
        self.collector = CollectorService(self.obs_system, warmup_duration_sec=0)

        # 1.5 Start background position refresher for Hyperliquid (REST polling)
        self.position_refresher = PositionRefresher(HL_INDEXED_DB_PATH)
        self.position_refresher.start()

        # 1.5.1 Start WebSocket position tracker for real-time updates (sub-50ms)
        self.ws_tracker = None
        self._ws_tracker_thread = None
        if HAS_WS_TRACKER:
            self._init_ws_tracker()

        # 1.6 Start background orderbook refresher for absorption analysis
        self.orderbook_refresher = OrderbookRefresher()
        self.orderbook_refresher.start()

        # 1.7 Initialize Liquidation Fade Executor (dry run by default)
        self._init_fade_executor()

        # 2. UI Setup
        self.stack = QStackedWidget()
        self.red_screen = RedScreenOfDeath()

        # Main Dashboard
        self.dashboard = QWidget()
        self.dashboard.setStyleSheet(f"background-color: {COLORS['background']}; color: {COLORS['text']};")
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ===== HEADER ROW =====
        header_layout = QHBoxLayout()

        title = QLabel("LIQUIDATION TRADING SYSTEM")
        title.setFont(QFont("Consolas", 14, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.status_indicator = QLabel("RUNNING")
        self.status_indicator.setFont(QFont("Consolas", 11, QFont.Bold))
        self.status_indicator.setStyleSheet(
            f"color: {COLORS['running']}; padding: 3px 10px; "
            f"background-color: #1a3a1a; border-radius: 4px;"
        )
        header_layout.addWidget(self.status_indicator)

        self.uptime_label = QLabel("0m 0s")
        self.uptime_label.setFont(QFont("Consolas", 10))
        self.uptime_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        header_layout.addWidget(self.uptime_label)

        self.intervals_label = QLabel("| 0 int")
        self.intervals_label.setFont(QFont("Consolas", 10))
        self.intervals_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        header_layout.addWidget(self.intervals_label)

        # Live tracker wallet count
        self.wallets_label = QLabel("| 🔴 0 wallets")
        self.wallets_label.setFont(QFont("Consolas", 10))
        self.wallets_label.setStyleSheet(f"color: {COLORS['short']};")  # Red for live indicator
        header_layout.addWidget(self.wallets_label)

        main_layout.addLayout(header_layout)

        # ===== PRICE TICKER =====
        self.price_ticker = PriceTickerWidget()
        main_layout.addWidget(self.price_ticker)

        # ===== TAB WIDGET =====
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border']};
                background-color: {COLORS['background']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text_dim']};
                padding: 8px 24px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS['background']};
                color: {COLORS['header']};
                font-weight: bold;
            }}
            QTabBar::tab:hover {{
                color: {COLORS['text']};
            }}
        """)

        # ===== TAB 1: MAIN (Chart + Positions) =====
        self.main_tab = QWidget()
        self._build_main_tab()
        self.tab_widget.addTab(self.main_tab, "MAIN")

        # ===== TAB 2: TRADES (Trade Management) =====
        self.trades_tab = QWidget()
        self._build_trades_tab()
        self.tab_widget.addTab(self.trades_tab, "TRADES")

        # ===== TAB 3: ANALYSIS (Cascade/Whale/Heatmap) =====
        self.analysis_tab = QWidget()
        self._build_analysis_tab()
        self.tab_widget.addTab(self.analysis_tab, "ANALYSIS")

        main_layout.addWidget(self.tab_widget)

        # ===== ACTIVITY LOG =====
        self.activity_log = ActivityLogRow()
        main_layout.addWidget(self.activity_log)

        self.dashboard.setLayout(main_layout)

        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.red_screen)
        self.setCentralWidget(self.stack)

        # Tracking
        self.last_trade_refresh = 0

        # 3. Start Update Loop
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(250)

        # 4. Start Collector Thread
        self.loop_thread = threading.Thread(target=self.run_async_loop, daemon=True)
        self.loop_thread.start()

    def run_async_loop(self):
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        import traceback
        error_log_file = open('THREAD_ERRORS.log', 'w', buffering=1)

        try:
            print("ASYNC THREAD: Starting collector", file=error_log_file)
            loop.run_until_complete(self.collector.start())
        except Exception as e:
            print(f"!!! EXCEPTION: {type(e).__name__} !!!", file=error_log_file)
            print(f"Error: {e}", file=error_log_file)
            traceback.print_exc(file=error_log_file)
            raise
        finally:
            error_log_file.close()

    def _build_main_tab(self):
        """Build the MAIN tab: Chart (60%) + Positions + QuickTrade (40%)."""
        layout = QHBoxLayout(self.main_tab)
        layout.setSpacing(8)
        layout.setContentsMargins(4, 4, 4, 4)

        # ----- LEFT: Chart (60%) -----
        chart_container = QVBoxLayout()
        chart_container.setSpacing(4)

        self.trading_chart = TradingChartWidget()
        chart_container.addWidget(self.trading_chart)

        layout.addLayout(chart_container, stretch=60)

        # ----- RIGHT: Positions + QuickTrade (40%) -----
        right_layout = QVBoxLayout()
        right_layout.setSpacing(6)

        # Positions near liquidation
        hl_group = QGroupBox("POSITIONS NEAR LIQUIDATION")
        hl_group.setFont(QFont("Consolas", 9, QFont.Bold))
        hl_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['critical']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        hl_layout = QVBoxLayout()

        # Sort toggle buttons
        sort_row = QHBoxLayout()
        sort_label = QLabel("Sort:")
        sort_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        sort_row.addWidget(sort_label)

        self.sort_impact_btn = QPushButton("Impact")
        self.sort_impact_btn.setCheckable(True)
        self.sort_impact_btn.setChecked(True)
        self.sort_impact_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['long']};
                color: white;
                border: none;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:!checked {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text_dim']};
            }}
        """)
        self.sort_impact_btn.clicked.connect(lambda: self._set_sort_mode("impact"))
        sort_row.addWidget(self.sort_impact_btn)

        self.sort_distance_btn = QPushButton("Distance")
        self.sort_distance_btn.setCheckable(True)
        self.sort_distance_btn.setChecked(False)
        self.sort_distance_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['short']};
                color: white;
                border: none;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:!checked {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text_dim']};
            }}
        """)
        self.sort_distance_btn.clicked.connect(lambda: self._set_sort_mode("distance"))
        sort_row.addWidget(self.sort_distance_btn)
        sort_row.addStretch()
        hl_layout.addLayout(sort_row)

        self.hl_sort_mode = "impact"
        self.hl_positions_table = HyperliquidPositionsTable()
        # Connect row click to chart sync
        self.hl_positions_table.cellClicked.connect(self._on_position_clicked)
        hl_layout.addWidget(self.hl_positions_table)
        hl_group.setLayout(hl_layout)
        right_layout.addWidget(hl_group, stretch=4)

        # Quick Trade Panel
        trade_group = QGroupBox("QUICK TRADE")
        trade_group.setFont(QFont("Consolas", 9, QFont.Bold))
        trade_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['header']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        trade_layout = QVBoxLayout()
        self.quick_trade_panel = QuickTradePanel()
        trade_layout.addWidget(self.quick_trade_panel)
        trade_group.setLayout(trade_layout)
        right_layout.addWidget(trade_group, stretch=1)

        layout.addLayout(right_layout, stretch=40)

    def _build_trades_tab(self):
        """Build the TRADES tab: Open positions, history, performance."""
        layout = QHBoxLayout(self.trades_tab)
        layout.setSpacing(8)
        layout.setContentsMargins(4, 4, 4, 4)

        # ----- LEFT: Open Positions -----
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)

        # Our positions with P&L
        pos_group = QGroupBox("OUR POSITIONS")
        pos_group.setFont(QFont("Consolas", 9, QFont.Bold))
        pos_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['header']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        pos_layout = QVBoxLayout()
        self.positions_table = PositionsPnLWidget()
        pos_layout.addWidget(self.positions_table)
        pos_group.setLayout(pos_layout)
        left_layout.addWidget(pos_group, stretch=2)

        # Primitives status (useful info)
        self.primitives_row = PrimitivesStatusRow()
        left_layout.addWidget(self.primitives_row)

        layout.addLayout(left_layout, stretch=50)

        # ----- RIGHT: Trade History -----
        right_layout = QVBoxLayout()
        right_layout.setSpacing(6)

        # Extended trade history
        history_group = QGroupBox("TRADE HISTORY")
        history_group.setFont(QFont("Consolas", 9, QFont.Bold))
        history_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['header']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        history_layout = QVBoxLayout()
        self.trade_history = TradeHistoryWidget()
        history_layout.addWidget(self.trade_history)
        history_group.setLayout(history_layout)
        right_layout.addWidget(history_group, stretch=1)

        layout.addLayout(right_layout, stretch=50)

    def _build_analysis_tab(self):
        """Build the ANALYSIS tab: Cascade, Whale Bias, Heatmap, Orderbook."""
        layout = QHBoxLayout(self.analysis_tab)
        layout.setSpacing(8)
        layout.setContentsMargins(4, 4, 4, 4)

        # ----- LEFT: Cascade + Whale -----
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)

        # Cascade State
        self.cascade_widget = CascadeStateWidget()
        left_layout.addWidget(self.cascade_widget, stretch=1)

        # Cascade Warning Panel
        self.cascade_warning = CascadeWarningWidget()
        left_layout.addWidget(self.cascade_warning, stretch=2)

        # Whale Bias Panel
        self.whale_bias = WhaleBiasWidget()
        left_layout.addWidget(self.whale_bias, stretch=2)

        layout.addLayout(left_layout, stretch=50)

        # ----- RIGHT: Heatmap + Orderbook -----
        right_layout = QVBoxLayout()
        right_layout.setSpacing(6)

        # Liquidation Heatmap
        heatmap_group = QGroupBox("LIQUIDATION HEATMAP")
        heatmap_group.setFont(QFont("Consolas", 9, QFont.Bold))
        heatmap_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['warning']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        heatmap_layout = QVBoxLayout()
        self.liquidation_heatmap = LiquidationHeatmapWidget()
        heatmap_layout.addWidget(self.liquidation_heatmap)
        heatmap_group.setLayout(heatmap_layout)
        right_layout.addWidget(heatmap_group, stretch=2)

        # Order Book Depth
        self.orderbook_widget = OrderBookDepthWidget()
        right_layout.addWidget(self.orderbook_widget, stretch=1)

        layout.addLayout(right_layout, stretch=50)

    def _on_position_clicked(self, row: int, column: int):
        """Handle click on a position row - sync chart to that coin and highlight liq price."""
        coin_item = self.hl_positions_table.item(row, 1)  # Coin column
        liq_item = self.hl_positions_table.item(row, 4)   # Liq Price column
        side_item = self.hl_positions_table.item(row, 2)  # Side column
        if coin_item:
            coin = coin_item.text()
            if coin:
                # Update chart
                self.trading_chart._on_coin_clicked(coin)
                # Update quick trade panel
                self.quick_trade_panel.set_coin(coin)

                # Highlight the specific liquidation price if available
                if liq_item:
                    try:
                        liq_price_text = liq_item.text().replace('$', '').replace(',', '')
                        liq_price = float(liq_price_text)
                        side = side_item.text() if side_item else "LONG"
                        self.trading_chart.highlight_liq_price(liq_price, side)
                        # Log the activity
                        self.activity_log.add_message(f"Viewing {coin} {side} liq @ ${liq_price:,.0f}")
                    except (ValueError, TypeError):
                        pass

    def _set_sort_mode(self, mode: str):
        """Set the sort mode for Hyperliquid positions."""
        self.hl_sort_mode = mode
        self.sort_impact_btn.setChecked(mode == "impact")
        self.sort_distance_btn.setChecked(mode == "distance")
        # Immediately refresh the positions table
        hl_positions = load_hyperliquid_positions(limit=25, sort_by=self.hl_sort_mode)
        self.hl_positions_table.update_data(hl_positions)

    @Slot()
    def update_ui(self):
        try:
            now = time.time()  # Define now at start of update cycle

            snapshot: ObservationSnapshot = self.obs_system.query({'type': 'snapshot'})

            if snapshot.status == ObservationStatus.FAILED:
                raise SystemHaltedException("Status reports FAILED")

            # Update uptime
            uptime = int(time.time() - self.start_time)
            mins, secs = divmod(uptime, 60)
            self.uptime_label.setText(f"{mins}m {secs}s")

            # Update intervals
            intervals = snapshot.counters.intervals_processed or 0
            self.intervals_label.setText(f"| {intervals} int")

            # Update live tracker wallet count
            wallet_count = get_live_wallet_count()
            self.wallets_label.setText(f"| 🔴 {wallet_count} wallets")

            # Update price ticker
            prices = aggregate_prices(snapshot)
            self.price_ticker.update_data(prices)

            # Update Hyperliquid positions - prioritize shared state (real-time WS data)
            # DECOUPLED: UI reads from shared state, detection writes to it
            ws_positions = []
            if HAS_WS_TRACKER and get_shared_state:
                shared = get_shared_state()
                # Get ALL positions from shared state
                all_snapshots = shared.get_all_positions()
                # Filter for positions CLOSE to liquidation:
                # - Recently updated (within 30s) - removes liquidated/stale positions
                # - Within 5% of liquidation (gives wider view)
                # - distance > 0 (positions at/past liq are removed by WS tracker)
                # - Meaningful notional ($10k+)
                stale_threshold = now - 30.0  # 30 seconds freshness
                valid_snapshots = [
                    s for s in all_snapshots
                    if s.updated_at > stale_threshold
                    and s.distance_pct > 0  # Must be above liq price (WS tracker removes at <=0)
                    and s.distance_pct <= 5.0  # Show positions within 5% of liq (wider view)
                    and s.notional >= 10000
                ]

                # STABILITY: Use stable sort with hysteresis to prevent flickering
                # Only re-sort if position order has changed significantly (>0.15% difference)
                if not hasattr(self, '_stable_position_order'):
                    self._stable_position_order = {}  # key -> last_distance

                # Build current distance map
                current_distances = {f"{s.wallet}:{s.coin}": s.distance_pct for s in valid_snapshots}

                # Check if we need to re-sort (new positions or significant changes)
                need_resort = False
                new_keys = set(current_distances.keys())
                old_keys = set(self._stable_position_order.keys())

                # Resort if positions added/removed
                if new_keys != old_keys:
                    need_resort = True
                else:
                    # Resort if any position changed by more than 0.15%
                    for key, new_dist in current_distances.items():
                        old_dist = self._stable_position_order.get(key, new_dist)
                        if abs(new_dist - old_dist) > 0.15:
                            need_resort = True
                            break

                if need_resort:
                    # Full resort
                    valid_snapshots.sort(key=lambda s: s.distance_pct)
                    self._stable_position_order = current_distances.copy()
                else:
                    # Keep previous order, just update distances
                    # Sort by stored order (using old distances as sort key)
                    valid_snapshots.sort(key=lambda s: self._stable_position_order.get(
                        f"{s.wallet}:{s.coin}", s.distance_pct
                    ))

                # Convert to UI format (match expected keys for HyperliquidPositionsTable)
                for snap in valid_snapshots[:25]:
                    ws_positions.append({
                        'wallet_address': snap.wallet,  # Table expects wallet_address
                        'coin': snap.coin,              # Table expects coin
                        'side': snap.side,
                        'size': snap.size,
                        'position_value': snap.notional,  # Table expects position_value
                        'entry_price': snap.entry_price,
                        'liquidation_price': snap.liq_price,  # Table expects liquidation_price
                        'current_price': snap.current_price,
                        'distance_to_liq_pct': snap.distance_pct,
                        'leverage': snap.leverage,
                        'danger_level': snap.danger_level,
                        'is_live': True,  # Mark as live WS data
                        'source': 'WS'
                    })

            # Fallback to REST-based data if WS has few positions
            live_positions = get_cached_live_positions()
            db_positions = load_hyperliquid_positions(limit=25, sort_by=self.hl_sort_mode)

            # Track position counts for stability - NEVER show empty
            if not hasattr(self, '_last_pos_count'):
                self._last_pos_count = 0
            if not hasattr(self, '_last_good_positions'):
                self._last_good_positions = []

            # Priority: WS > LIVE > DB > CACHED
            ws_count = len(ws_positions)
            live_count = len(live_positions) if live_positions else 0
            db_count = len(db_positions) if db_positions else 0
            cached_count = len(self._last_good_positions)

            min_acceptable = max(5, cached_count // 2)

            if ws_count >= min_acceptable:
                # Use WS real-time data (fastest, most accurate for danger)
                positions_to_show = ws_positions
                current_count = ws_count
                source = "WS"
                self._last_good_positions = ws_positions
            elif live_count >= min_acceptable:
                # Good live data
                positions_to_show = live_positions
                current_count = live_count
                source = "LIVE"
                self._last_good_positions = live_positions
            elif db_count >= min_acceptable:
                # Good DB data
                positions_to_show = db_positions
                current_count = db_count
                source = "DB"
                self._last_good_positions = db_positions
            elif self._last_good_positions:
                # Use cached good data to prevent flickering
                positions_to_show = self._last_good_positions
                current_count = cached_count
                source = "CACHED"
            else:
                # Fallback to whatever we have (only on first load)
                positions_to_show = ws_positions or live_positions or db_positions or []
                current_count = len(positions_to_show)
                source = "FALLBACK"
                if positions_to_show:
                    self._last_good_positions = positions_to_show

            # ALWAYS update the table - never leave it empty
            if positions_to_show:
                self.hl_positions_table.update_data(positions_to_show)

            # Log when position count changes significantly
            if abs(current_count - self._last_pos_count) >= 5:
                print(f"[UI] Position count: {self._last_pos_count} -> {current_count} ({source}, ws={ws_count}, live={live_count}, db={db_count})")
            self._last_pos_count = current_count

            # Update liquidation heatmap (every 5 seconds)
            if not hasattr(self, '_last_heatmap_refresh'):
                self._last_heatmap_refresh = 0
            if now - self._last_heatmap_refresh > 5.0:
                self.liquidation_heatmap.refresh_data()
                self._last_heatmap_refresh = now

            # Update trading chart
            # - 1 second when fast_refresh_mode enabled (user clicked a symbol)
            # - 3 seconds for normal background refresh
            if not hasattr(self, '_last_chart_refresh'):
                self._last_chart_refresh = 0
            chart_interval = 1.0 if getattr(self.trading_chart, '_fast_refresh_mode', False) else 3.0
            if now - self._last_chart_refresh > chart_interval:
                self.trading_chart.refresh_chart()
                self._last_chart_refresh = now

            # Update cascade state
            cascade_state = aggregate_cascade_state(snapshot)
            self.cascade_widget.update_data(cascade_state)

            # Update zoom mode status
            if hasattr(self, 'position_refresher'):
                zoom_status = self.position_refresher.get_zoom_status()
                self.cascade_widget.update_zoom_status(zoom_status)

            # Update cascade warning (every 30 seconds)
            if hasattr(self, 'cascade_warning') and time.time() - self.cascade_warning._last_refresh > 30:
                self.cascade_warning._refresh_cascade_data()

            # Update whale bias (every 30 seconds)
            if hasattr(self, 'whale_bias') and time.time() - self.whale_bias._last_refresh > 30:
                self.whale_bias._refresh_bias_data()

            # Update order book depth
            depth = get_orderbook_depth(snapshot)
            self.orderbook_widget.update_data(depth)

            # Update primitives status
            prim_counts = {}
            for symbol in TOP_10_SYMBOLS:
                bundle = snapshot.primitives.get(symbol)
                prim_counts[symbol] = count_primitives(bundle)
            self.primitives_row.update_data(prim_counts)

            # Refresh trade history periodically (every 2 seconds)
            now = time.time()
            if now - self.last_trade_refresh > 2.0:
                self.trade_history.refresh_trades()
                self.last_trade_refresh = now

        except SystemHaltedException as e:
            self.red_screen.set_error(str(e))
            self.stack.setCurrentWidget(self.red_screen)
        except Exception as e:
            print(f"UI Error: {e}")

    def _init_ws_tracker(self):
        """Initialize WebSocket-based position tracker for sub-50ms latency."""
        # Store reference to event loop for cross-thread scheduling
        self._ws_loop = None

        def run_ws_tracker():
            """Run the async WS tracker in a separate thread with its own event loop."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._ws_loop = loop  # Store reference for cross-thread access

            try:
                # Create tracker with callbacks
                self.ws_tracker = HybridPositionTracker(
                    on_signal=self._on_ws_danger_signal,
                    on_position_update=self._on_ws_position_update
                )

                # PRIORITY: Get wallets with positions close to liquidation FIRST
                danger_wallets = self._get_danger_wallets()
                print(f"[WSTracker] Found {len(danger_wallets)} wallets with positions <10% from liq")

                # Then add remaining tracked wallets
                all_wallets = list(self.position_refresher.TRACKED_WHALES)
                wallets = danger_wallets + [w for w in all_wallets if w not in danger_wallets]
                print(f"[WSTracker] Starting with {len(wallets)} wallets (danger wallets prioritized)")

                # Run the tracker
                loop.run_until_complete(self.ws_tracker.start(wallets))

                # Keep running until stopped
                loop.run_forever()

            except Exception as e:
                print(f"[WSTracker] Error: {e}")
            finally:
                loop.close()

        def on_wallet_discovered(wallet: str):
            """Callback for newly discovered wallets - subscribes them to WSTracker."""
            if self._ws_loop and self.ws_tracker:
                # Schedule async subscribe on the WS tracker's event loop
                future = asyncio.run_coroutine_threadsafe(
                    self.ws_tracker.ws_tracker.subscribe_wallet(wallet),
                    self._ws_loop
                )
                try:
                    # Wait briefly for result (non-blocking with timeout)
                    result = future.result(timeout=1.0)
                    if result:
                        print(f"[WSTracker] Dynamically subscribed to new wallet: {wallet[:10]}...")
                except Exception as e:
                    print(f"[WSTracker] Failed to subscribe {wallet[:10]}...: {e}")

        # Set the discovery callback
        self.position_refresher.set_wallet_discovery_callback(on_wallet_discovered)

        # Start in background thread
        self._ws_tracker_thread = threading.Thread(target=run_ws_tracker, daemon=True)
        self._ws_tracker_thread.start()
        print("[WSTracker] Background thread started for real-time position tracking")

    def _on_ws_danger_signal(self, signal):
        """Handle danger signal from WebSocket tracker (called from WS thread)."""
        # Filter out zombie positions (negative distance = already past liquidation)
        if signal.distance_pct <= 0:
            return

        # Log danger signals
        level_names = {1: 'WATCH', 2: 'WARNING', 3: 'CRITICAL'}
        level_name = level_names.get(signal.danger_level, 'UNKNOWN')
        print(
            f"[WS-SIGNAL] {level_name}: {signal.coin} {signal.side} "
            f"${signal.notional:,.0f} @ {signal.distance_pct:.2f}% from liq"
        )

        # If critical level (0.5%) and position is LONG, prepare fade opportunity
        # We fade AGAINST the liquidation - so when a LONG is about to liquidate,
        # the price will drop, then bounce back = we go LONG
        if signal.danger_level >= 3 and self.fade_executor:
            # Convert signal to fade event format
            fade_event = {
                'type': 'WS_DANGER_SIGNAL',
                'coin': signal.coin,
                'position_value': signal.notional,
                'wallet': signal.wallet,
                'side': signal.side,
                'distance_pct': signal.distance_pct,
                'liq_price': signal.liq_price,
                'current_price': signal.current_price,
                'danger_level': signal.danger_level
            }

            # Log the fade opportunity
            print(
                f"[FADE-TRIGGER] {signal.coin} {signal.side} ${signal.notional:,.0f} "
                f"@ {signal.distance_pct:.2f}% - preparing fade"
            )

            # Call fade executor - we're in the WS thread's async context
            # Use asyncio.get_event_loop() to schedule on the existing loop
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                # Schedule the coroutine to run in the existing event loop
                asyncio.ensure_future(self.fade_executor.on_liquidation(fade_event), loop=loop)
            except Exception as e:
                print(f"[FADE-ERROR] Failed to trigger fade: {e}")

    def _on_ws_position_update(self, wallet: str, clearinghouse: dict):
        """Handle position update from WebSocket (for debugging/logging)."""
        # This is called frequently - keep it minimal
        pass

    def _get_danger_wallets(self) -> list:
        """Get wallets with positions close to liquidation (within 10%)."""
        try:
            conn = sqlite3.connect(HL_INDEXED_DB_PATH, timeout=5)
            cursor = conn.cursor()
            # Expanded threshold (10%) and limit (100) for faster detection
            # This catches positions that might enter danger zone soon
            cursor.execute("""
                SELECT DISTINCT wallet_address
                FROM positions
                WHERE distance_to_liq_pct > 0 AND distance_to_liq_pct < 10
                ORDER BY distance_to_liq_pct ASC
                LIMIT 100
            """)
            wallets = [row[0] for row in cursor.fetchall()]
            conn.close()
            return wallets
        except Exception as e:
            print(f"[WSTracker] Error getting danger wallets: {e}")
            return []

    def _init_fade_executor(self):
        """Initialize the Liquidation Fade Executor (dry run mode by default)."""
        self.fade_executor = None

        if not HAS_FADE_EXECUTOR:
            print("[FADE] Executor not available (import failed)")
            return

        # Create executor in dry run mode (no real orders)
        config = FadeConfig(
            min_liquidation_value=30_000,  # $30k minimum to fade
            max_distance_pct=0.5,  # Only positions within 0.5% of liq
            position_size_usd=500,  # $500 position size
            take_profit_pct=0.4,  # 0.4% take profit
            stop_loss_pct=0.3,  # 0.3% stop loss (before breakeven)
            # Trailing TP / Breakeven protection
            breakeven_trigger_pct=0.15,  # Move SL to breakeven when +0.15%
            trailing_tp_enabled=True,  # Enable trailing take profit
            trailing_distance_pct=0.1,  # Trail 0.1% behind peak price
            max_concurrent_fades=2,  # Max 2 simultaneous fades
            cooldown_seconds=60,  # 1 minute cooldown per coin
            # CRITICAL: Impact filter to avoid traps
            max_impact_pct=5.0,  # Skip if position/volume > 5%
            min_orderbook_ratio=3.0,  # Skip if book depth < 3x position
        )

        self.fade_executor = LiquidationFadeExecutor(
            config=config,
            dry_run=True  # IMPORTANT: Start in dry run mode
        )

        # Connect to position refresher for liquidation detection
        if hasattr(self, 'position_refresher'):
            self.position_refresher.set_liquidation_callback(self._on_liquidation_detected)

        # Set up liquidator exit callback
        self.fade_executor.set_liquidator_exit_callback(self._on_liquidator_exit)

        # Track the whale liquidator wallet (NOT position holder)
        LIQUIDATOR_WALLET = '0x010461c14e146ac35fe42271bdc1134ee31c703a'
        self.fade_executor.track_liquidator(LIQUIDATOR_WALLET)

        # Start periodic check for liquidator exits (every 30 seconds)
        self._liquidator_check_timer = QTimer(self)
        self._liquidator_check_timer.timeout.connect(self._check_liquidator_exits)
        self._liquidator_check_timer.start(30_000)  # 30 seconds

        self.fade_executor.start()
        print("[FADE] Executor initialized in DRY RUN mode")
        print("[FADE] Config: $30k min, 0.4% TP, 0.3% SL")
        print("[FADE] Breakeven: +0.15% triggers, then trail 0.1%")
        print("[FADE] Impact filter: max 5% impact, min 3x book depth")
        print(f"[FADE] Tracking liquidator: {LIQUIDATOR_WALLET[:10]}...")

    def _on_liquidation_detected(self, event: Dict):
        """Callback when liquidation is detected by position refresher."""
        if not self.fade_executor:
            return

        coin = event.get('coin', '')
        wallet = event.get('wallet', '')
        value = event.get('value', 0)

        # Log the detection
        print(f"[FADE_SIGNAL] {coin} liquidation detected! Value: ${value:,.0f}")

        # Update mid prices cache in executor
        mid_prices = self.position_refresher._get_all_mids()
        self.fade_executor.update_mid_prices(mid_prices)

        # Trigger fade execution (async)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        asyncio.create_task(self.fade_executor.on_liquidation(event))

    def _on_liquidator_exit(self, exit_event: Dict):
        """Callback when tracked liquidator exits a position."""
        coin = exit_event.get('coin', '')
        reduction_pct = exit_event.get('reduction_pct', 0)
        is_full = exit_event.get('is_full_exit', False)
        side = exit_event.get('side', '')
        entry = exit_event.get('entry', 0)

        action = "CLOSED" if is_full else f"REDUCED {reduction_pct:.0f}%"
        print(f"\n{'='*60}")
        print(f"[LIQUIDATOR EXIT] {coin} {side} position {action}")
        print(f"[LIQUIDATOR EXIT] Entry was: ${entry:.6f}")
        print(f"{'='*60}\n")

        # If we have an active fade on this coin, consider exiting too
        if self.fade_executor and coin in self.fade_executor._active_fades:
            trade = self.fade_executor._active_fades[coin]
            current_price = self.fade_executor._mid_prices.get(coin, 0)
            if current_price > 0:
                profit_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
                print(f"[FADE] We have active {coin} position, profit: {profit_pct:+.2f}%")
                # If liquidator exits and we're in profit, consider following
                if profit_pct > 0:
                    print(f"[FADE] Consider following liquidator exit!")

    @Slot()
    def _check_liquidator_exits(self):
        """Periodic check for liquidator position changes."""
        if not self.fade_executor:
            return

        try:
            exits = self.fade_executor.check_liquidator_exits()
            if exits:
                print(f"[LIQUIDATOR] Detected {len(exits)} position change(s)")
        except Exception as e:
            print(f"[LIQUIDATOR] Check error: {e}")

    def closeEvent(self, event):
        """Clean up on window close."""
        print("Shutting down...")
        if hasattr(self, '_liquidator_check_timer'):
            self._liquidator_check_timer.stop()
        if hasattr(self, 'fade_executor') and self.fade_executor:
            self.fade_executor.stop()
        if hasattr(self, 'position_refresher'):
            self.position_refresher.stop()
        if hasattr(self, 'orderbook_refresher'):
            self.orderbook_refresher.stop()
        event.accept()


def kill_existing_instances():
    """Kill any existing instances of this app before starting."""
    import subprocess
    current_pid = os.getpid()
    try:
        # Find and kill other Python processes running main.py
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='python.exe'", 'get', 'processid,commandline'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'native_app' in line.lower() and 'main.py' in line.lower():
                parts = line.strip().split()
                for part in parts:
                    if part.isdigit():
                        pid = int(part)
                        if pid != current_pid:
                            print(f"[STARTUP] Killing existing instance PID {pid}")
                            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
    except Exception as e:
        print(f"[STARTUP] Could not check for existing instances: {e}")


def main():
    # Ensure single instance
    kill_existing_instances()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
