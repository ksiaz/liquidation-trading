# Two-Tier Scout + Main Entry System

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split cascade entry into two independent positions — a fast "scout" (50% size, no fuel gate, tight stop, zone-health exit) that catches the wick peak/valley, and a slower "main" (50% size, fuel-gated, wide stop, DCA) that builds if the reversal develops.

**Architecture:** Scout positions are tracked in a lightweight in-memory dict (`_scout_positions`) separate from the ghost tracker (which is single-position-per-symbol). Both use the trailing stop manager (keyed by `entry_order_id`, already supports multiple per symbol). Scout exits are driven by L2 zone-health monitoring (dwell time + zone consumption) — research shows zone held + fast dwell = 98.9% reversal, zone eaten + slow dwell = 57% coin flip.

**Tech Stack:** Python, existing `LiquidityMap`, `TrailingStopManager`, `RollingVolumeTracker`, PostgreSQL for trade logging.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `runtime/liquidations/scout_tracker.py` | **Create** | ScoutPosition dataclass, ScoutTracker class (in-memory dict, entry/exit/PnL, zone health snapshot) |
| `external_policy/ep2_strategy_cascade_sniper.py` | **Modify** | Add `SCOUT_TRAIL_CONFIG`, reduce `ROLLING_FADE_TRAIL_CONFIG` notional comment |
| `runtime/collector/service.py` | **Modify** | Scout entry path (bypass fuel gate), scout zone-health exit loop, main entry at 50% size, scout PnL logging |
| `runtime/policy_adapter.py` | **Modify** | Accept `notional_override` param for 50% sizing |
| `runtime/tests/test_scout_tracker.py` | **Create** | Unit tests for ScoutTracker |
| `runtime/tests/test_scout_integration.py` | **Create** | Integration tests for scout+main coexistence |

---

## Chunk 1: ScoutTracker Core

### Task 1: ScoutPosition Data Model and ScoutTracker

**Files:**
- Create: `runtime/liquidations/scout_tracker.py`
- Test: `runtime/tests/test_scout_tracker.py`

- [ ] **Step 1: Write failing tests for ScoutTracker**

```python
# runtime/tests/test_scout_tracker.py
import time
import pytest
from runtime.liquidations.scout_tracker import ScoutPosition, ScoutTracker, ZoneSnapshot


def test_open_scout_position():
    tracker = ScoutTracker()
    pos = tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=time.time(),
        zone=ZoneSnapshot(
            center_price=94950.0, band_low=94900.0, band_high=95000.0,
            initial_size_usd=500000.0, gravity=300000.0, side="bid",
        ),
    )
    assert pos is not None
    assert pos.symbol == "BTCUSDT"
    assert pos.side == "LONG"
    assert tracker.has_open("BTCUSDT")


def test_one_scout_per_symbol():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=time.time(),
        zone=ZoneSnapshot(
            center_price=94950.0, band_low=94900.0, band_high=95000.0,
            initial_size_usd=500000.0, gravity=300000.0, side="bid",
        ),
    )
    # Second open returns None — one scout per symbol
    pos2 = tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95100.0, timestamp=time.time(),
        zone=ZoneSnapshot(
            center_price=94950.0, band_low=94900.0, band_high=95000.0,
            initial_size_usd=500000.0, gravity=300000.0, side="bid",
        ),
    )
    assert pos2 is None


def test_close_scout_position():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="ETHUSDT", side="SHORT", quantity=0.05,
        entry_price=2100.0, timestamp=time.time(),
        zone=ZoneSnapshot(
            center_price=2110.0, band_low=2105.0, band_high=2115.0,
            initial_size_usd=200000.0, gravity=150000.0, side="ask",
        ),
    )
    pnl = tracker.close_position("ETHUSDT", exit_price=2090.0, exit_reason="ZONE_HEALTH")
    assert pnl is not None
    assert pnl > 0  # SHORT at 2100, exit at 2090 = profit
    assert not tracker.has_open("ETHUSDT")


def test_zone_health_check_healthy():
    """Zone held = healthy."""
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts,
        zone=ZoneSnapshot(
            center_price=94950.0, band_low=94900.0, band_high=95000.0,
            initial_size_usd=500000.0, gravity=300000.0, side="bid",
        ),
    )
    # Zone still has 80% of initial size, dwell only 5s — healthy
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=400000.0,
        current_price=95050.0, timestamp=ts + 5,
    )
    assert not should_exit


def test_zone_health_eaten_and_lingering():
    """Zone consumed + dwell > 10s = exit."""
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts,
        zone=ZoneSnapshot(
            center_price=94950.0, band_low=94900.0, band_high=95000.0,
            initial_size_usd=500000.0, gravity=300000.0, side="bid",
        ),
    )
    # Zone down to 30% of initial, 15s dwell
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=150000.0,
        current_price=94960.0, timestamp=ts + 15,
    )
    assert should_exit
    assert "eaten" in reason.lower()


def test_zone_health_max_dwell():
    """Dwell > 30s = exit regardless of zone health."""
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts,
        zone=ZoneSnapshot(
            center_price=94950.0, band_low=94900.0, band_high=95000.0,
            initial_size_usd=500000.0, gravity=300000.0, side="bid",
        ),
    )
    # Zone fully held but 35s dwell
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=500000.0,
        current_price=94960.0, timestamp=ts + 35,
    )
    assert should_exit
    assert "dwell" in reason.lower()


def test_zone_health_breach():
    """Price breached zone boundary = exit."""
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts,
        zone=ZoneSnapshot(
            center_price=94950.0, band_low=94900.0, band_high=95000.0,
            initial_size_usd=500000.0, gravity=300000.0, side="bid",
        ),
    )
    # Price fell below zone low (94900)
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=500000.0,
        current_price=94850.0, timestamp=ts + 3,
    )
    assert should_exit
    assert "breach" in reason.lower()


def test_pnl_long():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="SOLUSDT", side="LONG", quantity=1.0,
        entry_price=100.0, timestamp=time.time(),
        zone=ZoneSnapshot(
            center_price=99.5, band_low=99.0, band_high=100.0,
            initial_size_usd=50000.0, gravity=30000.0, side="bid",
        ),
    )
    pnl = tracker.close_position("SOLUSDT", exit_price=100.5, exit_reason="TRAILING_STOP")
    assert abs(pnl - 0.50) < 0.01  # 1.0 qty * $0.50 move


def test_pnl_short():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="SOLUSDT", side="SHORT", quantity=1.0,
        entry_price=100.0, timestamp=time.time(),
        zone=ZoneSnapshot(
            center_price=100.5, band_low=100.0, band_high=101.0,
            initial_size_usd=50000.0, gravity=30000.0, side="ask",
        ),
    )
    pnl = tracker.close_position("SOLUSDT", exit_price=99.5, exit_reason="TRAILING_STOP")
    assert abs(pnl - 0.50) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ksiaz/liquidation-trading && python -m pytest runtime/tests/test_scout_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'runtime.liquidations.scout_tracker'`

- [ ] **Step 3: Implement ScoutTracker**

```python
# runtime/liquidations/scout_tracker.py
"""
Scout Position Tracker — lightweight in-memory tracker for fast wick-catching entries.

Scout positions are the first half of a two-tier cascade fade:
- Enters immediately when spike detected (no fuel gate)
- Tight trailing stop (30bp SL, 15bp activation, 10bp trail)
- Exits on L2 zone health degradation (zone consumed, dwell timeout, breach)
- No DCA, no gravity TP, no restart recovery

Zone health exit rules (from gravity_zone_events data analysis, 33k events):
- Zone held (size_ratio > 0.5) + dwell < 15s = 98.9% reversal — let it run
- Zone eaten (size_ratio < 0.5) + dwell > 10s = 57% coin flip — exit
- Dwell > 30s regardless = zone being absorbed — exit
- Price breaches zone boundary = zone failed — exit
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class ZoneSnapshot:
    """L2 zone state at scout entry time."""
    center_price: float
    band_low: float
    band_high: float
    initial_size_usd: float
    gravity: float
    side: str  # "bid" or "ask"


@dataclass
class ScoutPosition:
    """Lightweight position for wick-catching."""
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    entry_ts: float
    zone: ZoneSnapshot
    trade_id: str = ""
    # Zone health tracking
    zone_arrival_ts: float = 0.0  # When price first entered zone

    def pnl(self, exit_price: float) -> float:
        if self.side == "LONG":
            return (exit_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - exit_price) * self.quantity


# Zone health thresholds (calibrated from 33k gravity_zone_events)
ZONE_EATEN_RATIO = 0.5       # Zone consumed if current_size < 50% of initial
ZONE_EATEN_MIN_DWELL = 10.0  # Only exit if eaten AND dwell > 10s
ZONE_MAX_DWELL = 30.0        # Exit regardless after 30s at zone


class ScoutTracker:
    """In-memory tracker for scout positions.

    One scout per symbol. No persistence (scouts are short-lived).
    """

    def __init__(self):
        self._positions: Dict[str, ScoutPosition] = {}
        self._trade_counter: int = 0

    def open_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        timestamp: float,
        zone: ZoneSnapshot,
    ) -> Optional[ScoutPosition]:
        """Open a scout position. Returns None if one already exists for symbol."""
        if symbol in self._positions:
            return None

        self._trade_counter += 1
        pos = ScoutPosition(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_ts=timestamp,
            zone=zone,
            trade_id=f"SCOUT_{self._trade_counter:06d}",
            zone_arrival_ts=timestamp,
        )
        self._positions[symbol] = pos
        return pos

    def has_open(self, symbol: str) -> bool:
        return symbol in self._positions

    def get_position(self, symbol: str) -> Optional[ScoutPosition]:
        return self._positions.get(symbol)

    def get_all_open(self) -> Dict[str, ScoutPosition]:
        return dict(self._positions)

    def close_position(
        self, symbol: str, exit_price: float, exit_reason: str
    ) -> Optional[float]:
        """Close scout position. Returns PnL in USD or None if no position."""
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return None
        pnl = pos.pnl(exit_price)
        hold_s = time.time() - pos.entry_ts
        print(f"SCOUT_EXIT: {symbol} {pos.side} {exit_reason} "
              f"entry=${pos.entry_price:,.2f} exit=${exit_price:,.2f} "
              f"PnL=${pnl:+.4f} hold={hold_s:.1f}s")
        return pnl

    def check_zone_health(
        self,
        symbol: str,
        current_zone_size_usd: float,
        current_price: float,
        timestamp: float,
    ) -> Tuple[bool, str]:
        """Check if scout should exit based on zone health.

        Returns (should_exit, reason).

        Rules (from gravity_zone_events analysis):
        1. Zone breach: price outside zone boundary → exit immediately
        2. Zone eaten + dwell > 10s: size_ratio < 0.5 → exit (57% reversal = coin flip)
        3. Max dwell > 30s: zone being absorbed → exit regardless
        """
        pos = self._positions.get(symbol)
        if pos is None:
            return False, ""

        zone = pos.zone
        dwell = timestamp - pos.zone_arrival_ts

        # Rule 1: zone breach — price outside zone boundary
        if pos.side == "LONG" and current_price < zone.band_low:
            return True, f"ZONE_BREACH: price ${current_price:,.2f} < zone low ${zone.band_low:,.2f}"
        if pos.side == "SHORT" and current_price > zone.band_high:
            return True, f"ZONE_BREACH: price ${current_price:,.2f} > zone high ${zone.band_high:,.2f}"

        # Rule 3: max dwell (check before eaten — dwell alone is sufficient)
        if dwell > ZONE_MAX_DWELL:
            size_ratio = current_zone_size_usd / zone.initial_size_usd if zone.initial_size_usd > 0 else 0
            return True, f"MAX_DWELL: {dwell:.0f}s at zone (size_ratio={size_ratio:.0%})"

        # Rule 2: zone eaten + lingering
        if zone.initial_size_usd > 0:
            size_ratio = current_zone_size_usd / zone.initial_size_usd
            if size_ratio < ZONE_EATEN_RATIO and dwell > ZONE_EATEN_MIN_DWELL:
                return True, f"ZONE_EATEN: size_ratio={size_ratio:.0%} dwell={dwell:.0f}s"

        return False, ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ksiaz/liquidation-trading && python -m pytest runtime/tests/test_scout_tracker.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/liquidations/scout_tracker.py runtime/tests/test_scout_tracker.py
git commit -m "feat(scout): add ScoutTracker with zone-health exit logic

Lightweight in-memory tracker for fast wick-catching entries.
Zone health thresholds calibrated from 33k gravity_zone_events.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Scout Trail Config and 50% Sizing

### Task 2: Add SCOUT_TRAIL_CONFIG

**Files:**
- Modify: `external_policy/ep2_strategy_cascade_sniper.py:230-236`

- [ ] **Step 1: Add SCOUT_TRAIL_CONFIG after ROLLING_FADE_TRAIL_CONFIG**

Add at line 237 in `ep2_strategy_cascade_sniper.py`:

```python
# SCOUT trailing stop config — tight stops for wick-catching.
# Scout enters immediately (no fuel gate), catches the peak/valley.
# If the wick doesn't bounce within 30bp, cut it fast.
# Zone-health exit handles most exits; this is the hard backstop.
SCOUT_TRAIL_CONFIG = {
    "activation_pct": 0.0015,          # 0.15% = 15 bps (activate quickly)
    "trail_pct": 0.0010,               # 0.10% = 10 bps (tight trail)
    "sl_pct": 0.003,                   # 0.30% = 30 bps (hard stop — fast cut)
    "break_even_trigger_pct": 0.0010,  # 0.10% = 10 bps (protect gains early)
    "break_even_offset_pct": 0.0,      # exact entry price
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add external_policy/ep2_strategy_cascade_sniper.py
git commit -m "feat(scout): add SCOUT_TRAIL_CONFIG (15bp activation, 10bp trail, 30bp SL)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 3: Add _get_scout_stop_config to service.py

**Files:**
- Modify: `runtime/collector/service.py:3403` (after `_get_rolling_fade_stop_config`)

- [ ] **Step 1: Add scout stop config method**

Insert after the `_get_rolling_fade_stop_config` method (line 3403):

```python
    def _get_scout_stop_config(self, symbol: str, entry_px: float, side: str):
        """Get trailing stop config for SCOUT entries.

        Returns (TrailingStopConfig, initial_stop_price).
        Tight stops: 15bp activation, 10bp trail, 30bp hard SL.
        Zone-health exit handles most exits — this is the backstop.
        """
        from external_policy.ep2_strategy_cascade_sniper import SCOUT_TRAIL_CONFIG
        cfg = SCOUT_TRAIL_CONFIG
        sl_pct = cfg['sl_pct']
        trail_pct = cfg['trail_pct']
        activation_pct = cfg['activation_pct']

        if side == "LONG":
            initial_stop = entry_px * (1 - sl_pct)
        else:
            initial_stop = entry_px * (1 + sl_pct)

        be_trigger = cfg.get('break_even_trigger_pct', 1.0)
        be_offset = cfg.get('break_even_offset_pct', 0.0)

        config = TrailingStopConfig(
            mode=TrailingMode.FIXED_DISTANCE,
            trail_distance_pct=trail_pct,
            trail_activation_pct=activation_pct,
            break_even_trigger_pct=be_trigger,
            break_even_offset_pct=be_offset,
            min_move_to_update_pct=0.0002,
            min_move_atr_fraction=0.05,
        )

        print(f"SCOUT STOP: {symbol} {side} @ ${entry_px:,.2f} "
              f"SL={sl_pct*100:.2f}% trail={trail_pct*100:.2f}% "
              f"act={activation_pct*100:.2f}% initial_stop=${initial_stop:,.2f}")

        return config, initial_stop
```

- [ ] **Step 2: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/collector/service.py
git commit -m "feat(scout): add _get_scout_stop_config (30bp SL, 15bp activation, 10bp trail)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 4: 50% Sizing via notional_override

**Files:**
- Modify: `runtime/policy_adapter.py:643-660` (entry quantity calculation)

- [ ] **Step 1: Read the mandate generation code to confirm exact location**

The mandate generation in `policy_adapter.py` uses `self.config.default_notional_usd` ($100). We need to accept an override for scout (50%) and main (50%).

In `policy_adapter.py`, the `generate_mandates()` method computes quantity as `notional / price`. Add `notional_override` parameter:

Find in `policy_adapter.py` the quantity calculation block (~line 643):
```python
quantity = Decimal(str(self.config.default_notional_usd)) / entry_price
```

Change to:
```python
_notional = Decimal(str(notional_override or self.config.default_notional_usd))
quantity = _notional / entry_price
```

Also add `notional_override: float = None` to `generate_mandates()` signature, and thread it through.

**Alternative (simpler):** Don't change policy_adapter at all. Instead, in service.py, after receiving the ENTRY mandate, halve the quantity before passing to ghost_tracker. This is simpler and keeps the change localized.

- [ ] **Step 2: Implement 50% sizing in service.py entry handler**

In service.py, where the ENTRY mandate is processed (~line 2194), after `qty = float(pos.quantity)`:

```python
# Two-tier sizing: scout already took 50%, main gets 50%
if is_rolling_fade and self._scout_tracker.has_open(result.symbol):
    # Main entry with scout already active — both get 50%
    qty = qty * 0.5
elif is_rolling_fade:
    # Main entry without scout (scout stopped out or expired) — still 50%
    qty = qty * 0.5
```

Note: Scout sizing is handled separately in the scout entry path (Task 5). The policy_adapter still generates $100 notional; we halve at execution.

- [ ] **Step 3: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/collector/service.py
git commit -m "feat(scout): 50/50 sizing — main entry uses half notional

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: Scout Entry Path

### Task 5: Scout Entry — Bypass Fuel Gate

This is the core change. When a rolling_fade signal is detected, BEFORE the fuel gate, fire the scout entry immediately.

**Files:**
- Modify: `runtime/collector/service.py` — init section (~line 324), regime loop (~line 1708-1900)

- [ ] **Step 1: Add scout tracker initialization**

In service.py `__init__`, after `self._rolling_volume_tracker = RollingVolumeTracker()` (line 324):

```python
# Scout tracker: fast wick-catching entries (no fuel gate, tight stops)
from runtime.liquidations.scout_tracker import ScoutTracker
self._scout_tracker = ScoutTracker()
```

- [ ] **Step 2: Add scout entry logic BEFORE fuel gate**

In service.py, after the rolling_fade_signal is obtained and passes the regime/counter-trend/volume gates (~line 1794, after the volume gate block), but BEFORE the fuel gate (line 1796), insert scout entry:

```python
                    # ── SCOUT ENTRY: immediate, no fuel gate ──
                    # Fires on first signal detection. Catches the wick peak/valley.
                    # 50% of notional, tight stop, zone-health exit.
                    if rolling_fade_signal and not self._scout_tracker.has_open(symbol):
                        # Don't scout if main position already open
                        if not self.ghost_tracker.has_open_position(symbol):
                            # Check stop cooldown (scouts share the 5-min cooldown)
                            _last_stop = self._stop_exit_timestamps.get(symbol, 0)
                            if timestamp - _last_stop >= _STOP_LOSS_COOLDOWN_SEC:
                                # Snapshot the L2 zone for zone-health monitoring
                                _hl_sym = symbol.replace("USDT", "")
                                if _hl_sym == "kPEPE":
                                    _hl_sym = "PEPE"
                                _scout_side = rolling_fade_signal.fade_direction
                                _scout_zone_side = "bid" if _scout_side == "LONG" else "ask"
                                _scout_price = current_price or self._get_live_price(symbol)

                                # Find nearest gravity zone on the supporting side
                                _zone = None
                                if _scout_price:
                                    if _scout_side == "LONG":
                                        _lz = self._liquidity_map.get_heaviest_zone_below(
                                            _hl_sym, _scout_price, min_gravity=5000)
                                    else:
                                        _lz = self._liquidity_map.get_heaviest_zone_above(
                                            _hl_sym, _scout_price, min_gravity=5000)

                                    if _lz:
                                        from runtime.liquidations.scout_tracker import ZoneSnapshot
                                        _zone = ZoneSnapshot(
                                            center_price=_lz.center_price,
                                            band_low=_lz.band_low,
                                            band_high=_lz.band_high,
                                            initial_size_usd=_lz.current_size_usd,
                                            gravity=_lz.gravity,
                                            side=_lz.side,
                                        )

                                if _scout_price and _zone:
                                    # 50% notional
                                    _scout_notional = self.policy_adapter.config.default_notional_usd * 0.5
                                    _scout_qty = _scout_notional / _scout_price

                                    _scout_pos = self._scout_tracker.open_position(
                                        symbol=symbol, side=_scout_side,
                                        quantity=_scout_qty, entry_price=_scout_price,
                                        timestamp=timestamp, zone=_zone,
                                    )
                                    if _scout_pos:
                                        # Register tight trailing stop
                                        _s_config, _s_stop = self._get_scout_stop_config(
                                            symbol, _scout_price, _scout_side)
                                        self._trailing_stop_manager.register_trailing_stop(
                                            entry_order_id=_scout_pos.trade_id,
                                            symbol=symbol, direction=_scout_side,
                                            entry_price=_scout_price,
                                            initial_stop_price=_s_stop,
                                            config=_s_config,
                                            entry_timestamp=timestamp,
                                        )
                                        print(f"SCOUT_ENTRY: {symbol} {_scout_side} "
                                              f"qty={_scout_qty:.6f} @ ${_scout_price:,.2f} "
                                              f"zone={_zone.center_price:,.2f} "
                                              f"(gravity={_zone.gravity:,.0f} "
                                              f"size=${_zone.initial_size_usd:,.0f})")
                                        # Log to ghost_trades for analysis
                                        self.ghost_tracker.open_position(
                                            symbol=f"SCOUT_{symbol}",
                                            side=_scout_side,
                                            quantity=_scout_qty,
                                            entry_price=_scout_price,
                                            timestamp=timestamp,
                                            policy_name="EP2-SCOUT-V1",
                                        )
```

**IMPORTANT NOTE about ghost_trades logging:** We use `SCOUT_{symbol}` as the ghost tracker symbol to avoid collision with the main position on the same symbol. This is a logging-only entry — the real position tracking is in `_scout_tracker`.

- [ ] **Step 3: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/collector/service.py
git commit -m "feat(scout): immediate entry on signal, bypass fuel gate

Scout enters at 50% notional with tight stop when spike detected.
Snapshots nearest L2 gravity zone for zone-health monitoring.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: Scout Zone-Health Exit Loop

### Task 6: Monitor scout positions in regime loop and exit on zone degradation

**Files:**
- Modify: `runtime/collector/service.py` — regime loop, after trailing stop update (~line 1455)

- [ ] **Step 1: Add scout zone-health check in regime loop**

After the `_update_trailing_stops()` call for each symbol (line 1455), add the scout monitoring block:

```python
                    # ── SCOUT zone-health exit ──
                    # Check if scout position should exit based on L2 zone health.
                    # Runs every regime cycle (~200ms) for fast response.
                    if self._scout_tracker.has_open(symbol):
                        _scout_pos = self._scout_tracker.get_position(symbol)
                        if _scout_pos:
                            _hl_sym_scout = symbol.replace("USDT", "")
                            if _hl_sym_scout == "kPEPEUSDT":
                                _hl_sym_scout = "PEPE"
                            # Get current zone size from liquidity map
                            _cur_zone_size = 0.0
                            _sz = _scout_pos.zone
                            _all_zones = self._liquidity_map.get_zones(_hl_sym_scout, side=_sz.side)
                            for _z in _all_zones:
                                # Match by price band overlap
                                if _z.band_low <= _sz.center_price <= _z.band_high:
                                    _cur_zone_size = _z.current_size_usd
                                    break

                            _scout_price = current_price or self._get_live_price(symbol)
                            if _scout_price:
                                _should_exit, _exit_reason = self._scout_tracker.check_zone_health(
                                    symbol, _cur_zone_size, _scout_price, timestamp)
                                if _should_exit:
                                    _pnl = self._scout_tracker.close_position(
                                        symbol, exit_price=_scout_price,
                                        exit_reason=f"ZONE_HEALTH:{_exit_reason}")
                                    # Deregister trailing stop
                                    self._trailing_stop_manager.deregister(
                                        _scout_pos.trade_id)
                                    # Close ghost_trades logging entry
                                    if self.ghost_tracker.has_open_position(f"SCOUT_{symbol}"):
                                        self.ghost_tracker.close_position(
                                            symbol=f"SCOUT_{symbol}",
                                            exit_reason=f"ZONE_HEALTH:{_exit_reason}",
                                            exit_price=_scout_price,
                                            timestamp=time.time())
                                    # Set stop cooldown if loss
                                    if _pnl is not None and _pnl < 0:
                                        self._stop_exit_timestamps[symbol] = time.time()
```

- [ ] **Step 2: Handle scout trailing stop exits**

The trailing stop manager fires exits via `_update_trailing_stops()`. Currently it closes the ghost position. We need to also handle scout stop exits. In the trailing stop exit handler (search for `TRAILING_STOP_LOSS` or `TRAILING_STOP_PROFIT` in the trailing stop update method), add a check:

Find in `_update_trailing_stops` where stop exit is triggered. If the `entry_order_id` starts with `SCOUT_`, close the scout position instead of the ghost position:

```python
# In _update_trailing_stops, when a stop is triggered:
if _stop_entry_id.startswith("SCOUT_"):
    # Scout trailing stop exit
    _scout_symbol = _stop_state.symbol
    _exit_px = current_price
    _pnl = self._scout_tracker.close_position(
        _scout_symbol, exit_price=_exit_px,
        exit_reason=_stop_reason)
    # Close ghost_trades logging entry
    if self.ghost_tracker.has_open_position(f"SCOUT_{_scout_symbol}"):
        self.ghost_tracker.close_position(
            symbol=f"SCOUT_{_scout_symbol}",
            exit_reason=_stop_reason,
            exit_price=_exit_px,
            timestamp=time.time())
    if _pnl is not None and _pnl < 0:
        self._stop_exit_timestamps[_scout_symbol] = time.time()
else:
    # Normal ghost position trailing stop exit (existing code)
    ...
```

- [ ] **Step 3: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/collector/service.py
git commit -m "feat(scout): zone-health exit loop + trailing stop integration

Checks L2 zone health every 200ms. Exits on zone consumed+dwell,
max dwell timeout, or zone breach. Trailing stop acts as hard backstop.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 5: Main Entry 50% Sizing and Position Guard Update

### Task 7: Main entry uses 50% and coexists with scout

**Files:**
- Modify: `runtime/collector/service.py` — entry handler (~line 2194), position guard (~line 1899)

- [ ] **Step 1: Update position guard to allow main entry when scout is open**

At line 1899, the current position guard blocks ENTRY when ghost position exists. Scout uses `SCOUT_{symbol}` in ghost tracker, so the main position guard is unaffected — no change needed here. The guard correctly blocks when a MAIN ghost position exists.

However, we need to ensure the main entry halves the quantity. In the entry handler (~line 2194):

```python
# After qty = float(pos.quantity)
# Two-tier: main entry always uses 50% regardless of scout state
if is_rolling_fade:
    qty = qty * 0.5
```

- [ ] **Step 2: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/collector/service.py
git commit -m "feat(scout): main entry at 50% notional for rolling_fade

Two-tier sizing: scout=$50 immediate, main=$50 fuel-gated.
Both can coexist on same symbol via separate tracking.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 6: End-to-End Wiring and Guard Rails

### Task 8: Edge cases and guard rails

**Files:**
- Modify: `runtime/collector/service.py`

- [ ] **Step 1: Scout cleanup on main position exit**

When a main position exits (any reason), if a scout is still open on the same symbol, close the scout too. This prevents orphaned scouts.

In the exit handling code (MANDATE_EXIT, TRAILING_STOP exits), after closing the ghost position, add:

```python
# Clean up scout if main position closed
if self._scout_tracker.has_open(result.symbol):
    _scout_px = self._get_live_price(result.symbol) or exit_price
    self._scout_tracker.close_position(
        result.symbol, exit_price=_scout_px,
        exit_reason="MAIN_EXIT_CLEANUP")
    _scout_pos = self._scout_tracker.get_position(result.symbol)
    if _scout_pos:
        self._trailing_stop_manager.deregister(_scout_pos.trade_id)
```

- [ ] **Step 2: Scout blocked during stop cooldown**

Already handled in Task 5 — scout entry checks `_stop_exit_timestamps`. Both scout and main share the same 5-min cooldown.

- [ ] **Step 3: Scout not recovered on restart**

Scouts are in-memory only. On restart, any scout is naturally lost. The scout's ghost_trades entry (`SCOUT_{symbol}`) will be status=OPEN but the reconciler skips it (symbol doesn't match any real trading pair). Add explicit cleanup:

In `_reconcile_positions_on_startup()`, add early cleanup:

```python
# Clean up orphaned scout ghost_trades from previous run
# Scouts are in-memory only, never recovered on restart
for symbol in list(self.ghost_tracker._state.open_positions.keys()):
    if symbol.startswith("SCOUT_"):
        self.ghost_tracker.close_position(
            symbol=symbol,
            exit_reason="RESTART_CLEANUP",
            exit_price=0,
            timestamp=time.time())
        print(f"RECONCILE: Cleaned up orphaned scout {symbol}")
```

- [ ] **Step 4: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/collector/service.py
git commit -m "feat(scout): guard rails — cleanup on main exit, restart, cooldown

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 9: Integration test

**Files:**
- Create: `runtime/tests/test_scout_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# runtime/tests/test_scout_integration.py
"""Integration tests for scout + main two-tier entry."""
import time
import pytest
from runtime.liquidations.scout_tracker import ScoutTracker, ZoneSnapshot


def test_scout_and_main_coexist():
    """Scout and main can both be open on same symbol."""
    scout = ScoutTracker()
    zone = ZoneSnapshot(
        center_price=94950, band_low=94900, band_high=95000,
        initial_size_usd=500000, gravity=300000, side="bid",
    )
    # Scout opens
    pos = scout.open_position("BTCUSDT", "LONG", 0.0005, 95000.0, time.time(), zone)
    assert pos is not None
    assert scout.has_open("BTCUSDT")
    # Main would go to ghost_tracker (separate system)
    # Scout doesn't block main, main doesn't block scout


def test_scout_exit_does_not_affect_main():
    """Closing scout leaves main unaffected."""
    scout = ScoutTracker()
    zone = ZoneSnapshot(
        center_price=94950, band_low=94900, band_high=95000,
        initial_size_usd=500000, gravity=300000, side="bid",
    )
    scout.open_position("BTCUSDT", "LONG", 0.0005, 95000.0, time.time(), zone)
    pnl = scout.close_position("BTCUSDT", 95050.0, "TRAILING_STOP_PROFIT")
    assert pnl > 0
    assert not scout.has_open("BTCUSDT")
    # Main ghost position would still be open (separate tracker)


def test_scout_multiple_symbols():
    """Multiple scouts on different symbols."""
    scout = ScoutTracker()
    ts = time.time()
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        zone = ZoneSnapshot(
            center_price=100, band_low=99, band_high=101,
            initial_size_usd=100000, gravity=50000, side="bid",
        )
        scout.open_position(sym, "LONG", 1.0, 100.0, ts, zone)
    assert len(scout.get_all_open()) == 3
    scout.close_position("ETHUSDT", 100.5, "ZONE_HEALTH")
    assert len(scout.get_all_open()) == 2


def test_zone_health_not_triggered_when_bouncing():
    """Price bounced above zone — no exit signal."""
    scout = ScoutTracker()
    ts = time.time()
    zone = ZoneSnapshot(
        center_price=94950, band_low=94900, band_high=95000,
        initial_size_usd=500000, gravity=300000, side="bid",
    )
    scout.open_position("BTCUSDT", "LONG", 0.001, 95000.0, ts, zone)

    # Price bounced up to 95200, zone still held
    should_exit, _ = scout.check_zone_health(
        "BTCUSDT", current_zone_size_usd=480000,
        current_price=95200.0, timestamp=ts + 8)
    assert not should_exit
```

- [ ] **Step 2: Run integration tests**

Run: `cd /home/ksiaz/liquidation-trading && python -m pytest runtime/tests/test_scout_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
cd /home/ksiaz/liquidation-trading
git add runtime/tests/test_scout_integration.py
git commit -m "test(scout): integration tests for scout+main coexistence

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Implementation Notes

### What changes vs. what stays the same

**Unchanged:**
- Rolling volume tracker signal detection (same burst logic)
- Fuel gate for main entry (same 3-phase gate)
- Main trailing stop config (80bp activation, 40bp trail, 200bp SL)
- DCA (main only, 8 levels)
- Gravity TP (main only)
- Counter-trend gate (applies to BOTH scout and main — same signal)
- Volume gate (applies to BOTH)
- Stop cooldown (shared between scout and main)

**Changed:**
- Signal now fires TWO entries: scout (immediate) + main (fuel-gated)
- Scout: 50% notional, 30bp SL, 15bp activation, 10bp trail
- Main: 50% notional (was 100%), same wide config
- Scout exits on L2 zone health degradation (new)
- Scout tracked separately from ghost tracker (new `ScoutTracker`)

### Risk assessment

- **Scout max loss per trade**: 50% × $100 × 30bp = $0.15. Acceptable.
- **Both scout and main stopped**: 50% × $100 × 30bp + 50% × $100 × 200bp = $1.15. Same as current $100 × 200bp = $2.00 but actually LESS.
- **Scout wins, main loses**: Net could still be positive. Scout captures wick bounce ($0.10-0.30), main takes full SL ($1.00). Net: -$0.70 to -$0.90. Worse per-trade but scout win rate should be higher.
- **Scout wins, main never enters**: Pure profit from wick catch. This is the new edge.

### Monitoring

After deployment, watch:
- `SCOUT_ENTRY:` and `SCOUT_EXIT:` log lines
- Scout win rate vs main win rate
- Zone health exit frequency vs trailing stop exit
- Whether scout PnL offsets main losses on bad days
