# Implementation Roadmap: Node-Enabled Tactics

**Status:** Implementation Guide
**Prerequisite:** Local Hyperliquid node operational

---

## PHASE 1: State File Parsing (Critical Path)

### 1.1 The Prize: Full Position Visibility

The `abci_state.rmp` file (927MB) contains the ENTIRE exchange state:
- 1,455,522 user accounts
- 3,480 wallets with perp positions
- Real-time position sizes, basis prices
- Updated every block (~1.2 seconds)

**This is the key differentiator.** API gives you 500 wallets at best. Node gives you ALL 3,480.

### 1.2 State File Structure

From session research, the structure is:
```
exchange/
├── user_states: list[1,455,522]     # All registered users
├── blp/                              # Perp clearinghouse
│   ├── u: list[3,480]               # Users with positions
│   │   └── [wallet, {o: {}, t: [[asset_id, [{b, s}, ...]]]}]
│   ├── p: float                      # Price factor
│   ├── r: dict                       # Rates/funding
│   └── b: dict                       # Book data
└── context/
    └── height, time, etc.
```

Position data within `blp/u`:
```json
{
  "b": 9999673699,    // Basis (entry price × 1e8)
  "s": 9999624005     // Size (position size × 1e8)
}
```

### 1.3 Implementation: State Parser

Add to `scripts/node_proxy.py`:

```python
import msgpack
import os

STATE_FILE = os.path.expanduser("~/hl/hyperliquid_data/abci_state.rmp")

def parse_abci_state():
    """Parse the full exchange state from msgpack file."""
    with open(STATE_FILE, 'rb') as f:
        state = msgpack.unpack(f, raw=False)
    return state

def extract_all_positions():
    """Extract all perp positions from state.

    Returns:
        Dict[wallet, Dict[asset_id, {side, size, basis}]]
    """
    state = parse_abci_state()
    positions = {}

    # Navigate to perp clearinghouse user data
    blp_users = state.get('exchange', {}).get('blp', {}).get('u', [])

    for user_entry in blp_users:
        if len(user_entry) < 2:
            continue

        wallet = user_entry[0]
        user_data = user_entry[1]

        # t = list of [asset_id, position_data]
        position_list = user_data.get('t', [])

        wallet_positions = {}
        for pos_entry in position_list:
            if len(pos_entry) < 2:
                continue

            asset_id = pos_entry[0]
            pos_data = pos_entry[1]

            # Position data may be list or dict
            if isinstance(pos_data, list) and len(pos_data) > 0:
                pos_data = pos_data[0]

            basis = pos_data.get('b', 0) / 1e8
            size = pos_data.get('s', 0) / 1e8

            if size != 0:
                wallet_positions[asset_id] = {
                    'side': 'LONG' if size > 0 else 'SHORT',
                    'size': abs(size),
                    'basis': basis,
                    'entry_price': basis / abs(size) if size != 0 else 0
                }

        if wallet_positions:
            positions[wallet] = wallet_positions

    return positions

def get_positions_by_proximity(current_prices: Dict[int, float], threshold_pct: float = 0.5):
    """Get positions sorted by proximity to liquidation.

    Args:
        current_prices: Dict of asset_id -> current price
        threshold_pct: Max distance to consider (default 0.5%)

    Returns:
        List of positions within threshold, sorted by distance
    """
    all_positions = extract_all_positions()
    at_risk = []

    for wallet, positions in all_positions.items():
        for asset_id, pos in positions.items():
            current_price = current_prices.get(asset_id)
            if not current_price:
                continue

            # Estimate liquidation price (simplified)
            # Full calculation requires margin data
            leverage = 10  # Assume 10x average
            if pos['side'] == 'LONG':
                liq_price = pos['entry_price'] * (1 - 1/leverage * 0.9)
                distance_pct = (current_price - liq_price) / current_price * 100
            else:
                liq_price = pos['entry_price'] * (1 + 1/leverage * 0.9)
                distance_pct = (liq_price - current_price) / current_price * 100

            if 0 < distance_pct < threshold_pct:
                at_risk.append({
                    'wallet': wallet,
                    'asset_id': asset_id,
                    'side': pos['side'],
                    'size': pos['size'],
                    'entry_price': pos['entry_price'],
                    'liq_price': liq_price,
                    'distance_pct': distance_pct,
                    'notional': pos['size'] * current_price
                })

    # Sort by distance (closest first)
    return sorted(at_risk, key=lambda x: x['distance_pct'])
```

### 1.4 New Proxy Endpoints

Add to `NodeProxyHandler`:

```python
def handle_all_positions(self):
    """Return all positions on the exchange."""
    now = time.time()
    if now - cache.get('positions_time', 0) > 5.0:  # 5s cache
        cache['positions'] = extract_all_positions()
        cache['positions_time'] = now

    self.send_response(200)
    self.send_header('Content-Type', 'application/json')
    self.send_header('Access-Control-Allow-Origin', '*')
    self.end_headers()
    # Compress for large payloads
    import gzip
    data = json.dumps(cache['positions']).encode()
    self.wfile.write(gzip.compress(data))

def handle_liquidation_levels(self):
    """Return positions sorted by liquidation proximity."""
    # Get current prices from cache
    prices = cache.get('mids', {})
    threshold = float(self.params.get('threshold', [0.5])[0])

    at_risk = get_positions_by_proximity(prices, threshold)

    self.send_response(200)
    self.send_header('Content-Type', 'application/json')
    self.send_header('Access-Control-Allow-Origin', '*')
    self.end_headers()
    self.wfile.write(json.dumps(at_risk).encode())

def handle_position_aggregates(self):
    """Return aggregated position data by asset."""
    positions = extract_all_positions()
    prices = cache.get('mids', {})

    aggregates = {}
    for wallet, wallet_pos in positions.items():
        for asset_id, pos in wallet_pos.items():
            if asset_id not in aggregates:
                aggregates[asset_id] = {
                    'long_count': 0, 'long_value': 0,
                    'short_count': 0, 'short_value': 0
                }

            price = prices.get(asset_id, 1)
            notional = pos['size'] * price

            if pos['side'] == 'LONG':
                aggregates[asset_id]['long_count'] += 1
                aggregates[asset_id]['long_value'] += notional
            else:
                aggregates[asset_id]['short_count'] += 1
                aggregates[asset_id]['short_value'] += notional

    self.send_response(200)
    self.send_header('Content-Type', 'application/json')
    self.end_headers()
    self.wfile.write(json.dumps(aggregates).encode())
```

---

## PHASE 2: Sweep Detection (Order Flow Analysis)

### 2.1 What Sweeps Tell Us

A sweep = aggressive market order consuming multiple levels.

**Key insight from research:**
- SOL: 43 DOWN sweeps vs 7 UP sweeps (-74.4% imbalance)
- This means large actors are NET SELLING aggressively
- Sweep imbalances often precede directional moves

### 2.2 Implementation: Sweep Detector

Add to `scripts/node_proxy.py`:

```python
class SweepDetector:
    """Detect aggressive sweep orders from block data."""

    # Sweep thresholds
    MIN_LEVELS_FOR_SWEEP = 5      # Must hit 5+ price levels
    MIN_VALUE_FOR_SWEEP = 10000   # $10k minimum
    SWEEP_WINDOW_MS = 1000        # Within 1 second

    def __init__(self):
        self.recent_orders = {}  # asset_id -> list of orders
        self.detected_sweeps = []

    def process_order(self, order: dict, timestamp: float):
        """Process an order and check for sweep pattern."""
        asset_id = order.get('a')
        price = float(order.get('p', 0))
        size = float(order.get('s', 0))
        is_buy = order.get('b', False)
        wallet = order.get('wallet', '')

        if asset_id not in self.recent_orders:
            self.recent_orders[asset_id] = []

        # Add order
        self.recent_orders[asset_id].append({
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'is_buy': is_buy,
            'wallet': wallet,
            'value': price * size
        })

        # Clean old orders
        cutoff = timestamp - self.SWEEP_WINDOW_MS / 1000
        self.recent_orders[asset_id] = [
            o for o in self.recent_orders[asset_id]
            if o['timestamp'] > cutoff
        ]

        # Check for sweep
        self._check_sweep(asset_id)

    def _check_sweep(self, asset_id: int):
        """Check if recent orders form a sweep."""
        orders = self.recent_orders.get(asset_id, [])
        if len(orders) < self.MIN_LEVELS_FOR_SWEEP:
            return

        # Group by direction
        buys = [o for o in orders if o['is_buy']]
        sells = [o for o in orders if not o['is_buy']]

        for side, side_orders in [('UP', buys), ('DOWN', sells)]:
            if len(side_orders) < self.MIN_LEVELS_FOR_SWEEP:
                continue

            # Check unique price levels
            prices = set(o['price'] for o in side_orders)
            if len(prices) < self.MIN_LEVELS_FOR_SWEEP:
                continue

            # Check total value
            total_value = sum(o['value'] for o in side_orders)
            if total_value < self.MIN_VALUE_FOR_SWEEP:
                continue

            # Sweep detected
            sweep = {
                'asset_id': asset_id,
                'direction': side,
                'levels': len(prices),
                'total_value': total_value,
                'orders': len(side_orders),
                'wallets': list(set(o['wallet'] for o in side_orders)),
                'timestamp': max(o['timestamp'] for o in side_orders),
                'price_range': (min(prices), max(prices))
            }

            self.detected_sweeps.append(sweep)

            # Log for monitoring
            print(f"[SWEEP] {ASSET_ID_TO_COIN.get(asset_id, asset_id)}: "
                  f"{side} sweep ${total_value:,.0f} across {len(prices)} levels")

    def get_imbalance(self, asset_id: int, window_min: int = 60) -> dict:
        """Get sweep imbalance for an asset over time window."""
        cutoff = time.time() - window_min * 60
        recent = [s for s in self.detected_sweeps
                  if s['asset_id'] == asset_id and s['timestamp'] > cutoff]

        up_value = sum(s['total_value'] for s in recent if s['direction'] == 'UP')
        down_value = sum(s['total_value'] for s in recent if s['direction'] == 'DOWN')
        total = up_value + down_value

        imbalance = 0
        if total > 0:
            imbalance = (up_value - down_value) / total * 100

        return {
            'asset_id': asset_id,
            'up_sweeps': len([s for s in recent if s['direction'] == 'UP']),
            'down_sweeps': len([s for s in recent if s['direction'] == 'DOWN']),
            'up_value': up_value,
            'down_value': down_value,
            'imbalance_pct': imbalance,
            'bias': 'BULLISH' if imbalance > 20 else 'BEARISH' if imbalance < -20 else 'NEUTRAL'
        }
```

### 2.3 Integration with Entry Quality

Modify `runtime/validation/entry_quality.py`:

```python
class EntryQualityScorer:
    # ... existing code ...

    def set_sweep_data(self, sweep_imbalance: dict):
        """Add sweep imbalance data to scoring."""
        self._sweep_data = sweep_imbalance

    def score_entry(self, symbol: str, intended_side: str = None, ...):
        # ... existing scoring ...

        # Add sweep imbalance component
        if hasattr(self, '_sweep_data') and self._sweep_data:
            imbalance = self._sweep_data.get('imbalance_pct', 0)

            # Adjust score based on alignment with sweep direction
            if intended_side == 'LONG' and imbalance > 20:
                # Bullish sweeps support long entries
                sweep_bonus = 0.2
            elif intended_side == 'SHORT' and imbalance < -20:
                # Bearish sweeps support short entries
                sweep_bonus = 0.2
            elif intended_side == 'LONG' and imbalance < -40:
                # Strong bearish sweeps penalize longs
                sweep_bonus = -0.3
            elif intended_side == 'SHORT' and imbalance > 40:
                # Strong bullish sweeps penalize shorts
                sweep_bonus = -0.3
            else:
                sweep_bonus = 0

            score += sweep_bonus

        # ... rest of scoring ...
```

---

## PHASE 3: Coordination Detection

### 3.1 What Coordination Tells Us

From research: 9 wallets coordinating $76M in UP sweeps in 1 second.

This is either:
1. Market maker hedging (neutral for us)
2. Coordinated manipulation (actionable)

### 3.2 Implementation: Coordination Detector

```python
from collections import deque
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class CoordinationEvent:
    timestamp: float
    wallet_count: int
    total_value: float
    direction: str  # 'UP' or 'DOWN'
    alignment: float  # 0-1, how aligned the direction is
    wallets: List[str]
    asset_id: int

class CoordinationDetector:
    """Detect coordinated multi-wallet activity."""

    COORDINATION_WINDOW_MS = 1000  # 1 second window
    MIN_WALLETS = 3               # At least 3 wallets
    MIN_VALUE = 100_000           # $100k minimum

    def __init__(self):
        self.recent_activity = {}  # asset_id -> deque of actions
        self.detected_events = deque(maxlen=1000)

    def record_action(
        self,
        asset_id: int,
        wallet: str,
        direction: str,  # 'UP' or 'DOWN'
        value: float,
        timestamp: float
    ):
        """Record a wallet action and check for coordination."""
        if asset_id not in self.recent_activity:
            self.recent_activity[asset_id] = deque(maxlen=500)

        self.recent_activity[asset_id].append({
            'wallet': wallet,
            'direction': direction,
            'value': value,
            'timestamp': timestamp
        })

        # Check for coordination
        self._check_coordination(asset_id, timestamp)

    def _check_coordination(self, asset_id: int, current_time: float):
        """Check for coordination pattern."""
        cutoff = current_time - self.COORDINATION_WINDOW_MS / 1000
        recent = [a for a in self.recent_activity[asset_id]
                  if a['timestamp'] > cutoff]

        # Need minimum wallets
        wallets = set(a['wallet'] for a in recent)
        if len(wallets) < self.MIN_WALLETS:
            return

        # Check total value
        total_value = sum(a['value'] for a in recent)
        if total_value < self.MIN_VALUE:
            return

        # Check directional alignment
        up_count = len([a for a in recent if a['direction'] == 'UP'])
        total_count = len(recent)
        up_pct = up_count / total_count

        # High alignment = coordinated
        alignment = max(up_pct, 1 - up_pct)
        if alignment < 0.7:  # Less than 70% aligned = not coordinated
            return

        event = CoordinationEvent(
            timestamp=current_time,
            wallet_count=len(wallets),
            total_value=total_value,
            direction='UP' if up_pct > 0.5 else 'DOWN',
            alignment=alignment,
            wallets=list(wallets),
            asset_id=asset_id
        )

        self.detected_events.append(event)

        print(f"[COORDINATION] {ASSET_ID_TO_COIN.get(asset_id, asset_id)}: "
              f"{len(wallets)} wallets, ${total_value:,.0f}, "
              f"{event.direction} ({alignment*100:.0f}% aligned)")

    def get_recent_coordination(
        self,
        asset_id: int = None,
        limit: int = 10
    ) -> List[CoordinationEvent]:
        """Get recent coordination events."""
        events = list(self.detected_events)
        if asset_id is not None:
            events = [e for e in events if e.asset_id == asset_id]
        return events[-limit:]

    def get_coordination_signal(self, asset_id: int) -> Optional[str]:
        """Get current coordination signal for trading."""
        recent = self.get_recent_coordination(asset_id, limit=5)
        if not recent:
            return None

        # Check last 5 minutes
        cutoff = time.time() - 300
        recent = [e for e in recent if e.timestamp > cutoff]

        if not recent:
            return None

        # If multiple coordinated events in same direction
        directions = [e.direction for e in recent]
        up_count = directions.count('UP')
        down_count = directions.count('DOWN')

        if up_count >= 2 and up_count > down_count:
            return 'BULLISH_COORDINATION'
        elif down_count >= 2 and down_count > up_count:
            return 'BEARISH_COORDINATION'

        return None
```

---

## PHASE 4: Whale Position Tracking

### 4.1 Whale Registry

Create `runtime/hyperliquid/whale_registry.py`:

```python
"""Whale wallet registry and tracking."""

from dataclasses import dataclass
from typing import Dict, List, Optional
import time
import sqlite3

@dataclass
class WhaleProfile:
    address: str
    bias: str  # 'LONG_BIAS', 'SHORT_BIAS', 'NEUTRAL'
    total_volume: float
    win_rate: Optional[float]
    avg_size: float
    last_seen: float
    notes: str = ""

# Known directional whales from research
KNOWN_WHALES = {
    # BTC Long bias
    "0xd4cb1c88d37e47...": WhaleProfile(
        address="0xd4cb1c88d37e47...",
        bias="LONG_BIAS",
        total_volume=15_199_100,
        win_rate=None,
        avg_size=0,
        last_seen=0
    ),
    # BTC Short bias
    "0xf3f64e8eaaf7f0...": WhaleProfile(
        address="0xf3f64e8eaaf7f0...",
        bias="SHORT_BIAS",
        total_volume=13_888_643,
        win_rate=None,
        avg_size=0,
        last_seen=0
    ),
    # Add more from research...
}

class WhaleTracker:
    """Track whale wallet positions and activity."""

    def __init__(self, db_path: str = "whale_tracking.db"):
        self.db_path = db_path
        self._init_db()
        self._whale_positions = {}  # wallet -> current positions

    def _init_db(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet TEXT,
                coin TEXT,
                side TEXT,
                size REAL,
                entry_price REAL,
                timestamp REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet TEXT,
                coin TEXT,
                action TEXT,  -- OPEN, CLOSE, INCREASE, DECREASE
                side TEXT,
                size_change REAL,
                price REAL,
                timestamp REAL
            )
        """)
        conn.commit()
        conn.close()

    def update_position(
        self,
        wallet: str,
        coin: str,
        side: str,
        size: float,
        entry_price: float,
        timestamp: float
    ):
        """Update whale position and detect changes."""
        key = (wallet, coin)
        old_pos = self._whale_positions.get(key)

        # Detect change type
        if old_pos is None and size > 0:
            action = 'OPEN'
            size_change = size
        elif old_pos is not None and size == 0:
            action = 'CLOSE'
            size_change = -old_pos['size']
        elif old_pos is not None:
            if size > old_pos['size']:
                action = 'INCREASE'
                size_change = size - old_pos['size']
            elif size < old_pos['size']:
                action = 'DECREASE'
                size_change = old_pos['size'] - size
            else:
                return  # No change

        # Update current position
        if size > 0:
            self._whale_positions[key] = {
                'side': side,
                'size': size,
                'entry_price': entry_price,
                'timestamp': timestamp
            }
        elif key in self._whale_positions:
            del self._whale_positions[key]

        # Log to database
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO whale_trades
            (wallet, coin, action, side, size_change, price, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (wallet, coin, action, side, size_change, entry_price, timestamp))
        conn.commit()
        conn.close()

        # Print alert for monitoring
        whale = KNOWN_WHALES.get(wallet[:20])
        bias_str = f" ({whale.bias})" if whale else ""
        print(f"[WHALE] {wallet[:16]}...{bias_str}: {action} {coin} {side} {size_change:.4f}")

    def get_whale_bias(self, coin: str) -> Dict[str, float]:
        """Get aggregate whale bias for a coin."""
        long_bias_value = 0
        short_bias_value = 0
        neutral_value = 0

        for (wallet, c), pos in self._whale_positions.items():
            if c != coin:
                continue

            whale = KNOWN_WHALES.get(wallet[:20])
            value = pos['size'] * pos['entry_price']

            if whale:
                if whale.bias == 'LONG_BIAS':
                    long_bias_value += value
                elif whale.bias == 'SHORT_BIAS':
                    short_bias_value += value
                else:
                    neutral_value += value
            else:
                neutral_value += value

        total = long_bias_value + short_bias_value + neutral_value
        return {
            'long_bias_value': long_bias_value,
            'short_bias_value': short_bias_value,
            'neutral_value': neutral_value,
            'bias': 'BULLISH' if long_bias_value > short_bias_value * 1.5
                    else 'BEARISH' if short_bias_value > long_bias_value * 1.5
                    else 'NEUTRAL'
        }

    def get_recent_whale_activity(self, coin: str = None, hours: int = 24) -> List[dict]:
        """Get recent whale trading activity."""
        cutoff = time.time() - hours * 3600
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT wallet, coin, action, side, size_change, price, timestamp
            FROM whale_trades
            WHERE timestamp > ?
            """ + (f" AND coin = '{coin}'" if coin else "") + """
            ORDER BY timestamp DESC
            LIMIT 100
        """, (cutoff,))
        results = cursor.fetchall()
        conn.close()

        return [
            {
                'wallet': r[0],
                'coin': r[1],
                'action': r[2],
                'side': r[3],
                'size_change': r[4],
                'price': r[5],
                'timestamp': r[6]
            }
            for r in results
        ]
```

---

## PHASE 5: Integration Architecture

### 5.1 Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NODE PROXY (VM/Local)                         │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  State      │  │  Sweep      │  │ Coordination│  │   Whale     │ │
│  │  Parser     │  │  Detector   │  │  Detector   │  │  Tracker    │ │
│  │             │  │             │  │             │  │             │ │
│  │ /positions  │  │ /sweeps     │  │ /coord      │  │ /whales     │ │
│  │ /liq_levels │  │ /imbalance  │  │ /signals    │  │ /activity   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
│         │                │                │                │        │
│         └────────────────┴────────────────┴────────────────┘        │
│                                  │                                   │
└──────────────────────────────────┼───────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │       NODE CLIENT            │
                    │   (runtime/hyperliquid/      │
                    │    node_client.py)           │
                    └──────────────┬───────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  Position       │   │  Entry Quality  │   │  Cascade        │
│  Tracker        │   │  Scorer         │   │  Sniper         │
│                 │   │                 │   │                 │
│ proximity_data  │   │ + sweep_data    │   │ + whale_bias    │
│ cluster_detect  │   │ + coord_signal  │   │ + coord_signal  │
│ liq_levels      │   │ + whale_bias    │   │ + sweep_imbal   │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                               │
                               ▼
                    ┌──────────────────────────────┐
                    │       EXECUTION              │
                    │   (runtime/executor/         │
                    │    controller.py)            │
                    └──────────────────────────────┘
```

### 5.2 Unified Signal Aggregation

Create `runtime/signals/aggregator.py`:

```python
"""Aggregate signals from all data sources."""

from dataclasses import dataclass
from typing import Optional

@dataclass
class AggregatedSignal:
    symbol: str
    timestamp: float

    # Core cascade data
    cascade_state: str
    cascade_value: float
    cluster_proximity_pct: float

    # Entry quality
    entry_quality: str
    entry_score: float

    # Node-enhanced signals
    sweep_imbalance_pct: float
    sweep_bias: str
    coordination_signal: Optional[str]
    whale_bias: str

    # Final recommendation
    recommended_action: str  # 'ENTER_LONG', 'ENTER_SHORT', 'WAIT', 'AVOID'
    confidence_factors: int  # Count of aligned signals

class SignalAggregator:
    """Combine all signals into trading decision."""

    def aggregate(
        self,
        cascade_data: dict,
        entry_score: dict,
        sweep_data: dict = None,
        coordination_data: dict = None,
        whale_data: dict = None
    ) -> AggregatedSignal:
        """Aggregate all signals into final recommendation."""

        confidence_factors = 0
        recommended_action = 'WAIT'

        # Start with cascade state
        if cascade_data.get('state') == 'ABSORBING':
            # Potential reversal entry
            dominant = cascade_data.get('dominant_side')
            if dominant == 'LONG':
                base_direction = 'LONG'  # Reversal after long liquidation
            else:
                base_direction = 'SHORT'  # Reversal after short liquidation

            # Check entry quality alignment
            if entry_score.get('quality') == 'HIGH':
                confidence_factors += 2
            elif entry_score.get('quality') == 'NEUTRAL':
                confidence_factors += 1

            # Check sweep alignment
            if sweep_data:
                if base_direction == 'LONG' and sweep_data.get('bias') == 'BULLISH':
                    confidence_factors += 1
                elif base_direction == 'SHORT' and sweep_data.get('bias') == 'BEARISH':
                    confidence_factors += 1
                # Penalize counter-trend
                elif base_direction == 'LONG' and sweep_data.get('bias') == 'BEARISH':
                    confidence_factors -= 1
                elif base_direction == 'SHORT' and sweep_data.get('bias') == 'BULLISH':
                    confidence_factors -= 1

            # Check coordination alignment
            if coordination_data:
                coord_signal = coordination_data.get('signal')
                if base_direction == 'LONG' and coord_signal == 'BULLISH_COORDINATION':
                    confidence_factors += 1
                elif base_direction == 'SHORT' and coord_signal == 'BEARISH_COORDINATION':
                    confidence_factors += 1

            # Check whale alignment
            if whale_data:
                whale_bias = whale_data.get('bias')
                if base_direction == 'LONG' and whale_bias == 'BULLISH':
                    confidence_factors += 1
                elif base_direction == 'SHORT' and whale_bias == 'BEARISH':
                    confidence_factors += 1

            # Determine final action
            if confidence_factors >= 3:
                recommended_action = f'ENTER_{base_direction}'
            elif confidence_factors >= 1:
                recommended_action = 'WAIT'  # Need more confluence
            else:
                recommended_action = 'AVOID'  # Signals disagree

        return AggregatedSignal(
            symbol=cascade_data.get('symbol', ''),
            timestamp=cascade_data.get('timestamp', 0),
            cascade_state=cascade_data.get('state', 'NONE'),
            cascade_value=cascade_data.get('value', 0),
            cluster_proximity_pct=cascade_data.get('proximity', 0),
            entry_quality=entry_score.get('quality', 'NEUTRAL'),
            entry_score=entry_score.get('score', 0),
            sweep_imbalance_pct=sweep_data.get('imbalance_pct', 0) if sweep_data else 0,
            sweep_bias=sweep_data.get('bias', 'NEUTRAL') if sweep_data else 'NEUTRAL',
            coordination_signal=coordination_data.get('signal') if coordination_data else None,
            whale_bias=whale_data.get('bias', 'NEUTRAL') if whale_data else 'NEUTRAL',
            recommended_action=recommended_action,
            confidence_factors=confidence_factors
        )
```

---

## Verification Checklist

### Phase 1: State Parsing
- [ ] abci_state.rmp loads without error
- [ ] Position count matches expected (~3,480)
- [ ] Position sizes are reasonable (not obviously wrong)
- [ ] Liquidation levels calculate correctly

### Phase 2: Sweep Detection
- [ ] Sweeps detected from block data
- [ ] Imbalance matches research findings (~74% SOL)
- [ ] Integration with entry quality works

### Phase 3: Coordination Detection
- [ ] Multi-wallet activity detected
- [ ] Alignment calculation is correct
- [ ] Signals integrate with cascade strategy

### Phase 4: Whale Tracking
- [ ] Known whales indexed
- [ ] Position changes detected
- [ ] Bias calculation is correct

### Phase 5: Integration
- [ ] All signals flow to aggregator
- [ ] Confidence scoring is reasonable
- [ ] Dashboard shows all data sources

---

*Implementation guide complete. Execute phases in order.*
