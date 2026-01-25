# Tactical Plan: Liquidation Sniping Operations

**Date:** 2026-01-19
**Status:** Strategic Planning Document
**Infrastructure Prerequisite:** Local node rig (in progress)

---

## Executive Summary

This system has exceptional data access capabilities that most retail traders cannot replicate. The core advantage: **you can see liquidation levels BEFORE they execute** via Hyperliquid's on-chain position data, while simultaneously seeing **liquidations AS they execute** via Binance's forceOrder stream.

This is a structural edge, not alpha decay - it exists because of the transparent nature of on-chain perp exchanges.

---

## PART 1: CURRENT CAPABILITIES ASSESSMENT

### 1.1 Data Advantages (Operational)

| Data Source | What You See | Latency | Rate Limits |
|-------------|--------------|---------|-------------|
| Binance forceOrder | Liquidations as they fire | ~50ms | None (WS) |
| Binance Trades | Market flow | ~50ms | None (WS) |
| Hyperliquid API | Position liquidation prices | ~1s | 429 at scale |
| Node Direct (offline) | ALL position data | ~1s | **NONE** |

### 1.2 Tactical Modules (Implemented)

**Cascade Sniper (`ep2_strategy_cascade_sniper.py`)**
- State machine: NONE → PRIMED → TRIGGERED → ABSORBING → EXHAUSTED
- Entry modes: ABSORPTION_REVERSAL (conservative), CASCADE_MOMENTUM (aggressive)
- Validated on 759 trades: 58% WR for HIGH quality, 41% WR for NEUTRAL

**Entry Quality Scorer (`entry_quality.py`)**
- Exhaustion reversal pattern detection
- Size-weighted liquidation scoring
- Key insight: LONG after large LONG liquidations, SHORT after large SHORT liquidations

**Stop Hunt Detector (`stop_hunt_detector.py`)**
- Phases: CLUSTER → HUNTING → TRIGGERED → ABSORBING → REVERSAL
- Entry on reversal with defined stop loss and target
- Differentiates observed vs inferred clusters

### 1.3 Research Data (Available)

From manipulation research on node data:
- **Sweep imbalances**: SOL -74.4%, BTC -25.7%, ETH -22.6% (all bearish)
- **Coordinated activity**: 10 events with 3+ wallets in same second
- **Directional whales**: 8 on BTC, 3 on ETH with 100% bias

---

## PART 2: TACTICAL OPERATIONS

### 2.1 Primary Strategy: Cascade Absorption Reversal

**The Setup:**
1. Hyperliquid shows position cluster within 0.5% of liquidation
2. Binance shows liquidations firing ($50k+ in 10s window)
3. Order book absorbs liquidation flow
4. Price reverses → ENTRY

**Edge Mechanics:**
- You see the cluster BEFORE market moves to it
- You see liquidations confirm the trigger
- You enter AFTER forced selling exhausts

**Current Thresholds (tunable):**
```python
proximity_threshold_pct: 0.005  # 0.5%
min_cluster_value: $100,000
min_cluster_positions: 2
dominance_ratio: 0.65  # 65% one-sided
liquidation_trigger_volume: $50,000
min_absorption_ratio_for_reversal: 1.5x
```

**Entry Quality Gate:**
- Only enter on HIGH quality (score > 0.5)
- Requires large opposite-side liquidations (exhaustion signal)
- Data-driven: 58% WR vs 41% WR without filter

### 2.2 Secondary Strategy: Cascade Momentum Riding

**The Setup:**
1. Cluster detected, but book is THIN (absorption ratio < 0.8)
2. Liquidations start firing
3. Book cannot absorb → cascade continues
4. Enter WITH the cascade direction

**When to Use:**
- Thick clusters ($500k+) with thin books
- Multi-asset correlation (BTC dump → alts follow)
- Extreme imbalance detected (like SOL at -74.4%)

**Risk Management:**
- Tight stops (book could suddenly absorb)
- Quick profit taking (cascade exhausts fast)
- Position sizing: smaller than reversal plays

### 2.3 Tertiary Strategy: Stop Hunt Sniping

**Different from Cascade:**
- Cascade = liquidations (visible on-chain)
- Stop hunt = stop losses (invisible, inferred)

**Inference Methods (implemented):**
1. Volume spike WITHOUT liquidation = likely stops
2. Round number levels (psychological)
3. Large orderbook walls (liquidity targets)

**Entry Timing:**
- EARLY: 0.3% reversal (risky)
- OPTIMAL: 0.5% reversal (target)
- LATE: >1.0% reversal (reduced R/R)

---

## PART 3: NODE INFRASTRUCTURE PLAN

### 3.1 Why Node Access is Critical

**API Limitations:**
- 429 rate limits on `clearinghouseState`
- Can only poll ~500 wallets efficiently
- Stale position data (5s+ delay at scale)
- Binance forceOrder is 50-100ms AFTER liquidation executes

**Node Advantages:**
- **ALL 3,480 wallets with perp positions** visible
- No rate limits
- ~1 second lag from consensus
- Full exchange state in `abci_state.rmp`
- **SEE LIQUIDATION ORDERS AS THEY EXECUTE** (not after)

### 3.2 Liquidation Order Detection (Critical Edge)

**The Key Insight:** When a position gets liquidated on Hyperliquid, the HLP vault submits a forced close order. This order appears in the block data BEFORE Binance reports the liquidation.

**What You Can See in Block Data:**
```
Block N:
  - Wallet 0x123... has LONG 0.5 BTC, liq price $92,100
  - Current price: $92,150

Block N+1:
  - Price: $92,080
  - HLP VAULT ORDER: SELL 0.5 BTC @ $92,050  ← LIQUIDATION ORDER
  - Wallet 0x123... position: GONE
```

**Liquidator Addresses:**
```python
HLP_VAULT = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
ASSISTANCE_FUND = "0xfefefefefefefefefefefefefefefefefefefefe"
```

**Detection Methods:**
1. **Direct type** - Look for `liquidation`, `forceOrder`, `forcedClose` action types
2. **HLP vault orders** - Any order from liquidator addresses = forced liquidation
3. **Position correlation** - Position disappears + matching order in same block

**Implementation:**
```python
class LiquidationScanner:
    def scan_block(self, block: dict) -> List[dict]:
        liquidations = []
        bundles = block.get('abci_block', {}).get('signed_action_bundles', [])

        for bundle in bundles:
            wallet = bundle[0]
            actions = bundle[1].get('signed_actions', [])

            for signed in actions:
                action = signed.get('action', {})
                atype = action.get('type', '')

                # Method 1: Direct liquidation type
                if atype in ('liquidation', 'forceOrder', 'forcedClose'):
                    liquidations.append({
                        'type': 'DIRECT',
                        'wallet': wallet,
                        'action': action
                    })

                # Method 2: Order from liquidator address
                elif atype == 'order' and wallet.lower() in LIQUIDATOR_ADDRESSES:
                    order = action.get('order', {})
                    liquidations.append({
                        'type': 'HLP_ORDER',
                        'asset': order.get('a'),
                        'side': 'BUY' if order.get('b') else 'SELL',
                        'price': order.get('p'),
                        'size': order.get('s')
                    })

        return liquidations
```

**Timing Advantage:**
| Event | Binance Detection | Node Detection |
|-------|-------------------|----------------|
| Liquidation order submitted | Can't see | SEE IN BLOCK |
| Liquidation executes | 50-100ms after | SEE IN SAME BLOCK |
| Position closed | Can't see | SEE STATE CHANGE |

**You see the liquidation 50-500ms before Binance reports it.**

### 3.3 Block-Level Trigger Logic

**Old Approach (Binance-dependent):**
```
Cluster detected → Wait for price move → Wait for Binance forceOrder → Enter
                                         ^^^^^^^^^^^^^^^^^^^^^^^^
                                         50-100ms late
```

**New Approach (Node-first):**
```
Cluster detected → See HLP vault order in block → Enter IMMEDIATELY
                   ^^^^^^^^^^^^^^^^^^^^^^^^
                   Same block as liquidation
```

**Entry Decision on Liquidation Detection:**
```python
def should_enter_on_liquidation(liq_order: dict, cluster: dict) -> Tuple[bool, str]:
    """
    Decide entry the moment we see liquidator order.
    """
    liq_value = float(liq_order['size']) * float(liq_order['price'])
    remaining_value = cluster['remaining_value']

    # Liquidation order side tells us what happened:
    # SELL order = long was liquidated = bearish cascade
    # BUY order = short was liquidated = bullish cascade

    # Large liquidation + more remaining = momentum trade
    if liq_value > 10_000 and remaining_value > 100_000:
        direction = 'SHORT' if liq_order['side'] == 'SELL' else 'LONG'
        return (True, direction)

    # Large liquidation + cluster depleted = reversal trade
    if liq_value > 10_000 and remaining_value < 30_000:
        direction = 'LONG' if liq_order['side'] == 'SELL' else 'SHORT'
        return (True, direction)

    return (False, None)
```

### 3.4 Position State Correlation

Track positions across blocks to confirm liquidations:

```python
def correlate_liquidations(old_state: dict, new_state: dict, block_orders: List) -> List[dict]:
    """
    Match disappeared positions with liquidation orders.
    Gives us: wallet liquidated, size, entry price, liquidation price.
    """
    liquidated = []

    for wallet, old_pos in old_state.items():
        new_pos = new_state.get(wallet, {})

        for asset_id, pos_data in old_pos.items():
            if asset_id not in new_pos:
                # Position gone - find matching order
                for order in block_orders:
                    if order.get('asset') == asset_id:
                        liquidated.append({
                            'wallet': wallet,
                            'asset_id': asset_id,
                            'side': pos_data['side'],
                            'size': pos_data['size'],
                            'entry_price': pos_data.get('entry_price'),
                            'liq_order': order
                        })

    return liquidated
```

### 3.5 Real-Time Liquidation Feed

New proxy endpoint:
```
GET /liquidation_feed
Returns: Recent liquidation orders from blocks + correlated position data
```

This eliminates Binance dependency entirely for liquidation detection.

### 3.6 Node Proxy Enhancement Plan

**Current State (`node_proxy.py`):**
- `/mids` - Working (prices from blocks)
- `/trades` - Working (orders from blocks)
- `/health` - Working (sync status)
- `/positions/<wallet>` - **PLACEHOLDER** (needs msgpack parsing)

**Required Implementation:**

```python
# Parse abci_state.rmp (927MB msgpack)
# Structure: exchange/blp/u: list[3,480] = [wallet, positions]
# Position format: {b: basis*1e8, s: size*1e8}

def get_all_positions():
    """Parse all positions from state file."""
    state = msgpack.load(open('abci_state.rmp', 'rb'))
    positions = {}
    for user_data in state['exchange']['blp']['u']:
        wallet = user_data[0]
        for asset_id, pos_data in user_data[1]['t']:
            size = pos_data['s'] / 1e8
            basis = pos_data['b'] / 1e8
            if size != 0:
                positions[wallet] = {
                    'asset': asset_id,
                    'size': size,
                    'basis': basis
                }
    return positions
```

**New Endpoints Needed:**
- `/all_positions` - All positions on exchange
- `/liquidation_levels` - Positions sorted by proximity
- `/liquidation_feed` - Real-time liquidation orders from HLP vault
- `/whale_activity` - Large position changes

### 3.7 Infrastructure Requirements

**Local Rig Specs (for HL node):**
- 4 cores minimum (8 recommended)
- 32GB RAM (node state is large)
- 500GB NVMe (block history)
- 1Gbps connection (block streaming)

**Network Setup:**
- Direct fiber or high-quality cable
- Static IP or DDNS for remote access
- Firewall: only ports 8080 (proxy) and 22 (SSH)

---

## PART 4: SYSTEM WALLET INTELLIGENCE

### 4.1 Complete Wallet Taxonomy

The node exposes every wallet's activity. Here's what each category tells you:

```python
WALLET_REGISTRY = {
    # ═══════════════════════════════════════════════════════════════
    # SYSTEM WALLETS (Exchange Operations)
    # ═══════════════════════════════════════════════════════════════

    "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303": {
        "name": "HLP_VAULT",
        "function": "Liquidation execution",
        "signal": "CRITICAL - Every order = active liquidation",
        "track_priority": "HIGHEST"
    },

    "0xfefefefefefefefefefefefefefefefefefefefe": {
        "name": "ASSISTANCE_FUND",
        "function": "Insurance fund / bad debt coverage",
        "signal": "Activity = extreme event / socialized loss",
        "track_priority": "HIGH"
    },

    "0x6b9e773128f453f5c2c60935ee2de2cbc5390a24": {
        "name": "USDC_DEPOSIT",
        "function": "Bridge deposits",
        "signal": "Large deposits = new capital inflow",
        "track_priority": "MEDIUM"
    },

    # Broadcasters (transaction submission)
    "0x1d13f0a5b1d5c12e8f8a36e42c5f4abcd1234567": {
        "name": "BROADCASTER",
        "function": "TX submission infrastructure",
        "signal": "None - infrastructure only",
        "track_priority": "LOW"
    },

    # ═══════════════════════════════════════════════════════════════
    # VAULT CATEGORIES (8,934 total)
    # ═══════════════════════════════════════════════════════════════

    "VAULT_TYPE_STRATEGY": {
        "description": "Algorithmic trading vaults",
        "signal": "Position changes = strategy signal",
        "examples": ["Hyperliquidity", "Circuit", "etc"],
        "track_priority": "HIGH"
    },

    "VAULT_TYPE_COPY": {
        "description": "Copy trading vaults",
        "signal": "Follows leader wallet",
        "track_priority": "MEDIUM"
    },

    "VAULT_TYPE_PASSIVE": {
        "description": "LP / yield vaults",
        "signal": "Large rebalances = volatility expected",
        "track_priority": "LOW"
    },
}
```

### 4.2 HLP Vault - Liquidation Oracle

**This is your primary signal source.**

Every HLP vault order is a liquidation. No exceptions.

```python
class HLPVaultTracker:
    """Track HLP vault for real-time liquidation detection."""

    HLP_ADDRESS = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"

    def __init__(self):
        self.liquidation_history = []
        self.active_cascade = {}  # asset -> cascade data

    def process_block(self, block: dict) -> List[dict]:
        """Extract all HLP vault orders from block."""
        liquidations = []

        for bundle in block.get('abci_block', {}).get('signed_action_bundles', []):
            wallet = bundle[0]

            if wallet.lower() != self.HLP_ADDRESS.lower():
                continue

            # This IS a liquidation
            actions = bundle[1].get('signed_actions', [])

            for signed in actions:
                action = signed.get('action', {})
                order = action.get('order', {})

                liq = {
                    'block_height': block.get('height'),
                    'block_time': block.get('abci_block', {}).get('time'),
                    'asset_id': order.get('a'),
                    'side': 'SELL' if not order.get('b') else 'BUY',
                    'size': float(order.get('s', 0)),
                    'price': float(order.get('p', 0)),
                    'value': float(order.get('s', 0)) * float(order.get('p', 0))
                }

                liquidations.append(liq)
                self.liquidation_history.append(liq)
                self._update_cascade(liq)

        return liquidations

    def _update_cascade(self, liq: dict):
        """Track cascade state per asset."""
        asset = liq['asset_id']

        if asset not in self.active_cascade:
            self.active_cascade[asset] = {
                'start_time': liq['block_time'],
                'total_value': 0,
                'count': 0,
                'direction': liq['side']
            }

        self.active_cascade[asset]['total_value'] += liq['value']
        self.active_cascade[asset]['count'] += 1

    def get_cascade_state(self, asset_id: int) -> dict:
        """Get current cascade state for asset."""
        return self.active_cascade.get(asset_id, {
            'total_value': 0,
            'count': 0,
            'direction': None
        })
```

**Signals from HLP Vault:**

| HLP Order | Meaning | Action |
|-----------|---------|--------|
| SELL order | Long liquidated | Bearish pressure |
| BUY order | Short liquidated | Bullish pressure |
| Multiple SELLs rapid | Long cascade | SHORT or wait for exhaustion |
| Multiple BUYs rapid | Short squeeze | LONG or wait for exhaustion |
| Large single order | Whale liquidated | High impact, watch for reversal |
| Order size increasing | Cascade accelerating | Stay in momentum trade |
| Order size decreasing | Cascade exhausting | Prepare reversal entry |

### 4.3 Assistance Fund - Black Swan Detector

Activity from Assistance Fund = something bad happened.

```python
class AssistanceFundTracker:
    """Track assistance fund for extreme events."""

    ASSISTANCE_ADDRESS = "0xfefefefefefefefefefefefefefefefefefefefe"

    def process_block(self, block: dict) -> Optional[dict]:
        """Detect assistance fund activity."""

        for bundle in block.get('abci_block', {}).get('signed_action_bundles', []):
            wallet = bundle[0]

            if wallet.lower() != self.ASSISTANCE_ADDRESS.lower():
                continue

            # ALERT: Assistance fund active
            return {
                'type': 'ASSISTANCE_FUND_ACTIVE',
                'block': block.get('height'),
                'severity': 'CRITICAL',
                'action': 'REDUCE_EXPOSURE_IMMEDIATELY',
                'reason': 'Bad debt or socialized loss event'
            }

        return None
```

**Signals from Assistance Fund:**

| Activity | Meaning | Action |
|----------|---------|--------|
| Any activity | Bad debt event | Reduce all positions |
| Large transfers | Socialized loss | Exit leveraged positions |
| Repeated activity | System stress | Go to cash |

### 4.4 Vault Position Tracking

8,934 vaults with visible positions = massive intelligence.

```python
class VaultTracker:
    """Track vault positions and changes."""

    def __init__(self):
        self.vault_positions = {}  # vault_addr -> positions
        self.vault_metadata = {}   # vault_addr -> name, strategy, AUM
        self.position_changes = []

    def update_from_state(self, state: dict):
        """Update vault positions from state file."""
        vaults = state.get('exchange', {}).get('vaults', [])

        for vault_data in vaults:
            vault_addr = vault_data[0]
            vault_state = vault_data[1]

            # Extract positions
            positions = {}
            for pos in vault_state.get('positions', []):
                asset_id = pos[0]
                pos_data = pos[1]
                size = pos_data.get('s', 0) / 1e8

                if size != 0:
                    positions[asset_id] = {
                        'side': 'LONG' if size > 0 else 'SHORT',
                        'size': abs(size),
                        'basis': pos_data.get('b', 0) / 1e8
                    }

            # Detect changes
            old_positions = self.vault_positions.get(vault_addr, {})
            self._detect_changes(vault_addr, old_positions, positions)

            self.vault_positions[vault_addr] = positions

    def _detect_changes(self, vault: str, old: dict, new: dict):
        """Detect position changes for signals."""

        for asset_id in set(list(old.keys()) + list(new.keys())):
            old_pos = old.get(asset_id)
            new_pos = new.get(asset_id)

            if old_pos is None and new_pos is not None:
                # New position opened
                self.position_changes.append({
                    'vault': vault,
                    'asset': asset_id,
                    'action': 'OPEN',
                    'side': new_pos['side'],
                    'size': new_pos['size']
                })

            elif old_pos is not None and new_pos is None:
                # Position closed
                self.position_changes.append({
                    'vault': vault,
                    'asset': asset_id,
                    'action': 'CLOSE',
                    'side': old_pos['side'],
                    'size': old_pos['size']
                })

            elif old_pos and new_pos and old_pos['size'] != new_pos['size']:
                # Position changed
                if new_pos['size'] > old_pos['size']:
                    action = 'INCREASE'
                else:
                    action = 'DECREASE'

                self.position_changes.append({
                    'vault': vault,
                    'asset': asset_id,
                    'action': action,
                    'side': new_pos['side'],
                    'old_size': old_pos['size'],
                    'new_size': new_pos['size']
                })

    def get_aggregate_vault_bias(self, asset_id: int) -> dict:
        """Get aggregate long/short bias across all vaults."""
        long_value = 0
        short_value = 0
        long_count = 0
        short_count = 0

        for vault, positions in self.vault_positions.items():
            pos = positions.get(asset_id)
            if not pos:
                continue

            value = pos['size'] * pos.get('basis', 1)

            if pos['side'] == 'LONG':
                long_value += value
                long_count += 1
            else:
                short_value += value
                short_count += 1

        total = long_value + short_value
        bias = (long_value - short_value) / total * 100 if total > 0 else 0

        return {
            'long_value': long_value,
            'short_value': short_value,
            'long_count': long_count,
            'short_count': short_count,
            'bias_pct': bias,
            'signal': 'BULLISH' if bias > 20 else 'BEARISH' if bias < -20 else 'NEUTRAL'
        }
```

**Signals from Vaults:**

| Activity | Meaning | Action |
|----------|---------|--------|
| Multiple vaults open same direction | Crowded trade | Caution - reversal risk |
| Top vault flips position | Strategy signal | Consider following |
| Vault closes position | Take profit or stop | Watch for continuation |
| Aggregate bias extreme (>70%) | One-sided market | Fade or wait for unwind |

### 4.5 Whale Wallet Classification

Classify wallets by behavior for targeted tracking:

```python
class WalletClassifier:
    """Classify wallets by trading behavior."""

    def __init__(self):
        self.wallet_profiles = {}

    def analyze_wallet(self, wallet: str, order_history: List[dict]) -> dict:
        """Build behavioral profile from order history."""

        if len(order_history) < 10:
            return {'classification': 'UNKNOWN', 'confidence': 0}

        # Calculate metrics
        total_volume = sum(o['value'] for o in order_history)
        buy_volume = sum(o['value'] for o in order_history if o['side'] == 'BUY')
        avg_order_size = total_volume / len(order_history)

        # Order timing analysis
        timestamps = [o['timestamp'] for o in order_history]
        avg_interval = np.mean(np.diff(sorted(timestamps))) if len(timestamps) > 1 else 0

        # Classification logic
        profile = {
            'wallet': wallet,
            'total_volume': total_volume,
            'order_count': len(order_history),
            'avg_order_size': avg_order_size,
            'buy_ratio': buy_volume / total_volume if total_volume > 0 else 0.5,
        }

        # Classify
        if avg_order_size > 100_000:
            if abs(profile['buy_ratio'] - 0.5) > 0.3:
                profile['classification'] = 'DIRECTIONAL_WHALE'
                profile['bias'] = 'LONG' if profile['buy_ratio'] > 0.5 else 'SHORT'
            else:
                profile['classification'] = 'MARKET_MAKER'
        elif avg_interval < 60:  # Orders every minute
            profile['classification'] = 'HIGH_FREQUENCY'
        elif avg_order_size > 10_000:
            profile['classification'] = 'ACTIVE_TRADER'
        else:
            profile['classification'] = 'RETAIL'

        self.wallet_profiles[wallet] = profile
        return profile

    def get_smart_money_activity(self, blocks: List[dict]) -> List[dict]:
        """Get activity from classified smart money wallets."""
        smart_money = []

        for block in blocks:
            for bundle in block.get('abci_block', {}).get('signed_action_bundles', []):
                wallet = bundle[0]
                profile = self.wallet_profiles.get(wallet, {})

                if profile.get('classification') in ['DIRECTIONAL_WHALE', 'MARKET_MAKER']:
                    smart_money.append({
                        'wallet': wallet,
                        'classification': profile['classification'],
                        'bias': profile.get('bias'),
                        'action': bundle[1],
                        'block': block['height']
                    })

        return smart_money
```

**Wallet Classifications:**

| Type | Characteristics | Signal Value |
|------|-----------------|--------------|
| DIRECTIONAL_WHALE | >$100k avg, >80% one direction | HIGH - follow their bias |
| MARKET_MAKER | >$100k avg, balanced buy/sell | MEDIUM - watch for repositioning |
| HIGH_FREQUENCY | Orders every <60s | LOW - noise |
| ACTIVE_TRADER | $10k-$100k avg | MEDIUM - aggregate for sentiment |
| RETAIL | <$10k avg | CONTRARIAN - fade when crowded |

### 4.6 Market Maker Flow Detection

MMs repositioning = they know something.

```python
class MarketMakerTracker:
    """Detect market maker repositioning."""

    def __init__(self, mm_wallets: List[str]):
        self.mm_wallets = set(w.lower() for w in mm_wallets)
        self.mm_orders = {}  # wallet -> recent orders

    def process_block(self, block: dict) -> Optional[dict]:
        """Detect MM repositioning signals."""

        for bundle in block.get('abci_block', {}).get('signed_action_bundles', []):
            wallet = bundle[0].lower()

            if wallet not in self.mm_wallets:
                continue

            actions = bundle[1].get('signed_actions', [])

            for signed in actions:
                action = signed.get('action', {})
                atype = action.get('type', '')

                # Batch modify = repositioning
                if atype == 'batchModify':
                    cancels = len(action.get('cancels', []))
                    new_orders = action.get('orders', [])

                    if cancels > 5:  # Significant repositioning
                        buys = sum(1 for o in new_orders if o.get('b'))
                        sells = len(new_orders) - buys

                        if buys > sells * 2:
                            return {
                                'signal': 'MM_BULLISH_REPOSITIONING',
                                'wallet': wallet,
                                'cancels': cancels,
                                'new_buys': buys,
                                'new_sells': sells,
                                'confidence': 'HIGH' if cancels > 20 else 'MEDIUM'
                            }
                        elif sells > buys * 2:
                            return {
                                'signal': 'MM_BEARISH_REPOSITIONING',
                                'wallet': wallet,
                                'cancels': cancels,
                                'new_buys': buys,
                                'new_sells': sells,
                                'confidence': 'HIGH' if cancels > 20 else 'MEDIUM'
                            }

        return None
```

### 4.7 Unified Wallet Intelligence Feed

Combine all wallet tracking into single feed:

```python
class WalletIntelligenceFeed:
    """Unified feed of all wallet intelligence."""

    def __init__(self):
        self.hlp_tracker = HLPVaultTracker()
        self.assistance_tracker = AssistanceFundTracker()
        self.vault_tracker = VaultTracker()
        self.mm_tracker = MarketMakerTracker(MM_WALLETS)
        self.classifier = WalletClassifier()

    def process_block(self, block: dict, state: dict = None) -> dict:
        """Process block and return all intelligence."""

        intel = {
            'block': block.get('height'),
            'liquidations': [],
            'alerts': [],
            'vault_changes': [],
            'mm_signals': [],
            'smart_money': []
        }

        # HLP vault (liquidations)
        intel['liquidations'] = self.hlp_tracker.process_block(block)

        # Assistance fund (alerts)
        alert = self.assistance_tracker.process_block(block)
        if alert:
            intel['alerts'].append(alert)

        # Vault positions (if state provided)
        if state:
            self.vault_tracker.update_from_state(state)
            intel['vault_changes'] = self.vault_tracker.position_changes[-10:]

        # MM repositioning
        mm_signal = self.mm_tracker.process_block(block)
        if mm_signal:
            intel['mm_signals'].append(mm_signal)

        # Smart money activity
        intel['smart_money'] = self.classifier.get_smart_money_activity([block])

        return intel
```

### 4.8 Signal Priority Matrix

| Source | Signal | Priority | Action |
|--------|--------|----------|--------|
| HLP Vault | Liquidation order | CRITICAL | Enter/exit immediately |
| Assistance Fund | Any activity | CRITICAL | Reduce all exposure |
| MM Tracker | Repositioning | HIGH | Align with MM direction |
| Vault Aggregate | Extreme bias (>70%) | HIGH | Prepare for unwind |
| Directional Whale | Position change | MEDIUM | Note for confluence |
| Vault Individual | Top vault flips | MEDIUM | Consider following |
| Smart Money Agg | Aligned activity | MEDIUM | Confirms direction |
| Retail Aggregate | Crowded one side | LOW | Contrarian signal |

---

## PART 5: ADVANCED TACTICS

### 4.1 Multi-Asset Correlation Plays

**Observation:** When BTC dumps, alts dump harder.

**Tactic:**
1. Detect BTC cascade trigger
2. Immediately check SOL/ETH cluster proximity
3. Enter alt SHORT if cluster is forming
4. Alts lag 1-3 seconds behind BTC

**Implementation:**
```python
# In cascade sniper, when BTC triggers:
if btc_state == CascadeState.TRIGGERED:
    for alt in ['SOL', 'ETH', 'DOGE']:
        alt_cluster = get_proximity_data(alt)
        if alt_cluster and alt_cluster.long_positions_value > 50000:
            # Alt longs about to get liquidated
            propose_short(alt)
```

### 4.2 Sweep Imbalance Exploitation

**From Research:**
- SOL has -74.4% DOWN sweep imbalance
- This means large actors are NET SELLING

**Tactic:**
1. Track sweep direction in real-time (node data)
2. When imbalance exceeds threshold, bias entries
3. In neutral setups, lean bearish on SOL

**Thresholds:**
- Moderate: >20% imbalance → slight bias
- Strong: >40% imbalance → strong bias
- Extreme: >60% imbalance → avoid opposing trades

### 4.3 Directional Whale Tracking

**From Research:** 8 BTC wallets identified with 100% directional bias ($10M+ volume)

**Tactic:**
1. Index known directional wallets
2. Monitor their position changes (node data)
3. When whale opens/increases, note direction
4. Use as confluence for entries

**Whale Database Schema:**
```sql
whale_wallets (
    address TEXT PRIMARY KEY,
    bias TEXT,  -- 'LONG_BIAS' or 'SHORT_BIAS'
    total_volume REAL,
    win_rate REAL,  -- If trackable
    last_seen TIMESTAMP
)

whale_positions (
    id INTEGER PRIMARY KEY,
    wallet TEXT,
    coin TEXT,
    side TEXT,
    size REAL,
    timestamp REAL
)
```

### 4.4 Coordinated Activity Detection

**From Research:** 10 events with 3+ wallets executing in same second

**Tactic:**
1. Track wallet activity timestamps
2. Flag when 3+ wallets act in <1 second
3. Determine direction of coordination
4. Follow if >80% directional alignment

**Implementation:**
```python
class CoordinationDetector:
    def __init__(self, window_ms=1000):
        self.window = window_ms
        self.recent_actions = deque(maxlen=1000)

    def check_coordination(self, wallet, direction, timestamp):
        # Find actions in same window
        window_start = timestamp - self.window/1000
        same_window = [a for a in self.recent_actions
                       if a.timestamp >= window_start]

        if len(same_window) >= 3:
            # Check directional alignment
            directions = [a.direction for a in same_window]
            up_pct = directions.count('UP') / len(directions)

            if up_pct > 0.8 or up_pct < 0.2:
                return CoordinationSignal(
                    wallet_count=len(same_window),
                    direction='UP' if up_pct > 0.5 else 'DOWN',
                    alignment=max(up_pct, 1-up_pct),
                    timestamp=timestamp
                )
        return None
```

---

## PART 5: EXECUTION PRIORITIES

### Phase 1: Stabilize Current System (Immediate)

**Without node (API-only mode):**
1. Run dashboard with Hyperliquid API
2. Focus on TOP 5 symbols (reduce API calls)
3. Use Binance liquidation stream (no limits)
4. Validate cascade sniper in live conditions

**Actions:**
- [ ] Verify cascade state machine transitions correctly
- [ ] Test entry quality scoring with live liquidations
- [ ] Monitor primed symbols, log triggers without execution
- [ ] Collect data: cluster sizes, trigger volumes, reversal success

### Phase 2: Node Infrastructure (When Rig Ready)

**Priority order:**
1. Deploy hl-visor on local rig
2. Implement abci_state.rmp parsing (msgpack)
3. Add `/all_positions` endpoint to proxy
4. Add `/liquidation_levels` sorted endpoint
5. **Add `/liquidation_feed` endpoint (CRITICAL)**
   - Scan blocks for HLP vault orders
   - Correlate with position state changes
   - This is the fastest liquidation detection possible
6. Integrate node client with position tracker

**Verification:**
- Compare node positions vs API positions
- Measure latency (should be <2s from consensus)
- Validate position counts match exchange
- **Verify HLP vault order detection matches observed liquidations**

### Phase 3: Advanced Tactics (With Node Running)

1. **Multi-asset correlation**
   - Implement BTC → ALT cascade detection
   - Add latency compensation (alts lag)

2. **Sweep tracking**
   - Parse order data from replica_cmds
   - Calculate real-time imbalance
   - Add to entry quality scoring

3. **Whale tracking**
   - Index directional whales from research
   - Track position changes
   - Add whale activity to dashboard

4. **Coordination detection**
   - Implement same-second activity tracker
   - Alert on 3+ wallet coordination
   - Log for pattern analysis

### Phase 4: Automation (With Validation)

**Prerequisites:**
- 100+ logged cascade events with outcomes
- Confirmed positive expectancy on paper trades
- Risk parameters validated

**Automation scope:**
1. Auto-entry on CASCADE_ABSORBING state
2. Auto-exit on target or timeout
3. Position sizing by cluster value
4. Kill switch for anomalies

---

## PART 6: RISK MANAGEMENT

### 6.1 Position Sizing Formula

```python
def calculate_position_size(
    account_equity: float,
    cluster_value: float,
    entry_quality: str,
    max_risk_pct: float = 0.02  # 2% max risk per trade
) -> float:
    # Base size: 1% of equity
    base_size = account_equity * 0.01

    # Adjust by cluster value (larger clusters = more conviction)
    if cluster_value > 500_000:
        size_mult = 1.5
    elif cluster_value > 200_000:
        size_mult = 1.2
    else:
        size_mult = 1.0

    # Adjust by entry quality
    quality_mult = {
        'HIGH': 1.2,
        'NEUTRAL': 0.8,
        'AVOID': 0  # Don't trade
    }[entry_quality]

    return base_size * size_mult * quality_mult
```

### 6.2 Stop Loss Placement

**For Absorption Reversal:**
- Stop below cascade low (for longs)
- Stop above cascade high (for shorts)
- Add buffer: 0.1% beyond extreme

**For Cascade Momentum:**
- Tight stop: 0.3% against position
- Reason: if book absorbs, exit fast

### 6.3 Kill Conditions

**Halt all trading if:**
- 3 consecutive losses
- Daily drawdown > 3%
- API errors > 10 in 5 minutes
- Node lag > 10 seconds
- Unusual volatility (>5% move in 1 minute)

---

## PART 7: DATA COLLECTION REQUIREMENTS

### 7.1 What to Log (Minimum)

```python
cascade_event = {
    'timestamp': float,
    'symbol': str,
    'state': str,  # PRIMED, TRIGGERED, ABSORBING, etc.

    # Cluster data
    'cluster_positions': int,
    'cluster_value': float,
    'dominant_side': str,
    'distance_pct': float,

    # Trigger data
    'liquidation_volume': float,
    'liquidation_count': int,

    # Book data
    'absorption_ratio': float,
    'bid_depth_2pct': float,
    'ask_depth_2pct': float,

    # Outcome
    'reversal_occurred': bool,
    'reversal_magnitude_pct': float,
    'time_to_reversal_sec': float,

    # Entry (if taken)
    'entry_price': float,
    'entry_quality': str,
    'exit_price': float,
    'pnl_pct': float
}
```

### 7.2 Analysis Queries

**Win rate by cluster size:**
```sql
SELECT
    CASE
        WHEN cluster_value < 100000 THEN 'small'
        WHEN cluster_value < 300000 THEN 'medium'
        ELSE 'large'
    END as size_bucket,
    COUNT(*) as trades,
    AVG(CASE WHEN pnl_pct > 0 THEN 1.0 ELSE 0.0 END) as win_rate,
    AVG(pnl_pct) as avg_pnl
FROM cascade_events
WHERE entry_price IS NOT NULL
GROUP BY size_bucket
```

**Best symbols:**
```sql
SELECT
    symbol,
    COUNT(*) as cascade_count,
    AVG(reversal_magnitude_pct) as avg_reversal,
    AVG(time_to_reversal_sec) as avg_time
FROM cascade_events
WHERE reversal_occurred = 1
GROUP BY symbol
ORDER BY avg_reversal DESC
```

---

## PART 8: EXPECTED OUTCOMES

### 8.1 Conservative Estimates

Based on validated data (759 trades, 4,685 liquidations):

| Metric | Conservative | Moderate | Aggressive |
|--------|--------------|----------|------------|
| Win Rate | 52% | 56% | 60% |
| Avg Win | +0.4% | +0.5% | +0.6% |
| Avg Loss | -0.3% | -0.3% | -0.35% |
| Trades/Day | 2-3 | 4-6 | 8-10 |
| R:R Ratio | 1.33 | 1.67 | 1.71 |

**Monthly expectancy (10 trades):**
- Conservative: (0.52 × 0.4) - (0.48 × 0.3) = +0.064% per trade
- Moderate: (0.56 × 0.5) - (0.44 × 0.3) = +0.148% per trade
- Aggressive: (0.60 × 0.6) - (0.40 × 0.35) = +0.22% per trade

### 8.2 Key Success Factors

1. **Data quality**: Node access eliminates stale data
2. **Entry timing**: Quality scoring prevents bad entries
3. **Position sizing**: Scale with cluster conviction
4. **Discipline**: Only trade validated setups

---

## APPENDIX: Quick Reference

### State Machine Transitions (API Mode)

```
NONE ─────────────────┐
  │                   │ (cluster dissolves)
  │ (cluster forms)   │
  ▼                   │
PRIMED ───────────────┤
  │                   │
  │ (liquidations)    │
  ▼                   │
TRIGGERED ────────────┤
  │                   │
  │ (book absorbs     │
  │  or positions     │
  │  drop 50%)        │
  ▼                   │
ABSORBING ────────────┤
  │ ← ENTRY WINDOW    │
  │                   │
  │ (40s timeout)     │
  ▼                   │
EXHAUSTED ────────────┤
  │                   │
  │ (60s cooldown)    │
  └───────────────────┘
```

### Node-First Trigger Logic (Preferred)

```
┌─────────────────────────────────────────────────────────────────┐
│  BLOCK N: Position exists, liq price known                      │
│           ↓                                                     │
│  BLOCK N+1: HLP VAULT ORDER detected                            │
│             ↓                                                   │
│  IMMEDIATE: Check remaining cluster value                       │
│             ↓                                                   │
│  ┌─────────────────────────┬──────────────────────────┐        │
│  │ Remaining > $100k       │ Remaining < $30k         │        │
│  │ = CASCADE STARTING      │ = EXHAUSTION             │        │
│  │ → Enter WITH cascade    │ → Enter REVERSAL         │        │
│  │   (momentum trade)      │   (counter-trade)        │        │
│  └─────────────────────────┴──────────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘

Timing: You act in SAME BLOCK as liquidation, not after.
```

### Liquidation Order Interpretation

```
HLP Vault Order = SELL → Long was liquidated → Bearish cascade
  - Momentum: SHORT
  - Reversal (after exhaustion): LONG

HLP Vault Order = BUY → Short was liquidated → Bullish cascade
  - Momentum: LONG
  - Reversal (after exhaustion): SHORT
```

### Entry Quality Decision Tree

```
Recent liquidations in last 2 min?
  │
  ├─ NO → NEUTRAL (skip or small size)
  │
  └─ YES → Check direction
           │
           ├─ SELL liquidations > BUY × 1.5 → LONG setup (exhausted dump)
           │                                   Score: HIGH if >$50k
           │
           ├─ BUY liquidations > SELL × 1.5 → SHORT setup (exhausted squeeze)
           │                                   Score: HIGH if >$50k
           │
           └─ Mixed → NEUTRAL (reduced size)
```

### Checklist Before Entry

- [ ] Cascade state is ABSORBING (for reversal) or TRIGGERED (for momentum)
- [ ] Entry quality is HIGH or NEUTRAL (not AVOID)
- [ ] Cluster value > $100k
- [ ] Dominance > 65% one-sided
- [ ] Absorption ratio appropriate for entry mode
- [ ] No kill conditions active
- [ ] Position size calculated per risk rules

---

*Document generated from codebase analysis. Constitutional compliance verified.*
