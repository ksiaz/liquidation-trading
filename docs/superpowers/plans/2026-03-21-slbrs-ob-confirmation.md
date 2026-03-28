# SLBRS Order Block Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add gravity zone order block confirmation to SLBRS entries with structural bracket exits (TP at next OB, SL 30bp, 60min max hold).

**Architecture:** The gravity observer gets a new `WallTracker` that aggregates individual zone events into macro walls in real-time, tracking consecutive reversals and absorption. SLBRS strategy consumes wall status as an additional confidence signal during retest entry. A new `BracketExitManager` handles OB-target exits independently from the trailing stop manager.

**Tech Stack:** Python, PostgreSQL (gravity_zone_events, ghost_trades), existing gravity observer + liquidity map infrastructure.

**Research:** Full findings in `memory/gravity_wall_research.md`. Key numbers: OB + prior held + last3=3 → 100% reversal (N=88). OB target exit → 89% WR, +42bp avg, 14.1x profit factor. SL=30bp optimal.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `runtime/liquidations/wall_tracker.py` | Create | Macro wall detection, OB classification, consecutive reversal tracking |
| `runtime/liquidations/gravity_observer.py` | Modify | Feed finalized zone events into WallTracker |
| `runtime/liquidations/bracket_exit.py` | Create | OB-target bracket exit manager (TP/SL/time, no trailing) |
| `external_policy/ep2_slbrs_strategy.py` | Modify | Consume wall_status as confirmation signal |
| `runtime/collector/service.py` | Modify | Wire WallTracker + BracketExitManager, shadow log |
| `runtime/logging/pg_schema.py` | Modify | Add wall_status columns to ghost_trades entry_context |
| `runtime/tests/test_wall_tracker.py` | Create | Unit tests for wall detection + OB classification |
| `runtime/tests/test_bracket_exit.py` | Create | Unit tests for bracket exit logic |

---

### Task 1: WallTracker — Macro Wall Detection

**Files:**
- Create: `runtime/liquidations/wall_tracker.py`
- Test: `runtime/tests/test_wall_tracker.py`

The WallTracker aggregates individual zone reversal/breach events into macro walls in real-time. A "macro wall" = cluster of zones within 100bp price band hit within 15 minutes. It tracks:
- Consecutive zone reversals at the wall (the "last 3 held" signal)
- Whether zones absorbed resting orders (OB detection)
- Prior visits to the same price level (within 4h)

- [ ] **Step 1: Write failing tests for WallTracker**

```python
# runtime/tests/test_wall_tracker.py
import pytest
import time
from runtime.liquidations.wall_tracker import WallTracker, WallStatus

class TestWallTracker:
    def test_no_events_returns_none(self):
        wt = WallTracker()
        status = wt.get_wall_status("BTC")
        assert status is None

    def test_single_reversal_tracked(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.4,
                             gravity=100000, timestamp=1000)
        status = wt.get_wall_status("BTC")
        assert status is not None
        assert status.consecutive_reversals == 1
        assert status.is_ob is True  # min_size_ratio 0.4 = 60% absorbed

    def test_three_consecutive_reversals(self):
        wt = WallTracker()
        for i in range(3):
            wt.on_zone_finalized("BTC", zone_center=70000 + i * 5,
                                 zone_side="bid", reversal=True, breached=False,
                                 min_size_ratio=0.8, gravity=50000,
                                 timestamp=1000 + i * 30)
        status = wt.get_wall_status("BTC")
        assert status.consecutive_reversals == 3
        assert status.gold_signal is True  # 3 consecutive + prior visits tracked

    def test_breach_resets_consecutive(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        wt.on_zone_finalized("BTC", zone_center=70005, zone_side="bid",
                             reversal=False, breached=True, min_size_ratio=0.9,
                             gravity=50000, timestamp=1030)
        status = wt.get_wall_status("BTC")
        assert status.consecutive_reversals == 0

    def test_different_price_band_new_wall(self):
        wt = WallTracker()
        # Zone at 70000 (100bp band = 70000 ± 70)
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        # Zone at 70200 — outside 100bp band, new wall
        wt.on_zone_finalized("BTC", zone_center=70200, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1010)
        status = wt.get_wall_status("BTC")
        # Should track the latest wall only
        assert status.consecutive_reversals == 1

    def test_ob_detection_deep_absorption(self):
        wt = WallTracker()
        # 40% absorbed = min_size_ratio 0.6 → NOT deep OB (threshold: 50%)
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.6,
                             gravity=50000, timestamp=1000)
        status = wt.get_wall_status("BTC")
        assert status.is_ob is False
        assert status.absorbed_zones == 1  # ≥30% absorbed

        # 60% absorbed = min_size_ratio 0.4 → deep OB
        wt.on_zone_finalized("BTC", zone_center=70003, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.4,
                             gravity=50000, timestamp=1030)
        status = wt.get_wall_status("BTC")
        assert status.is_ob is True  # has deep absorption

    def test_prior_visit_tracking(self):
        wt = WallTracker()
        # First visit at level 70000
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        # Wall expires (>15min gap)
        # Second visit at same level
        wt.on_zone_finalized("BTC", zone_center=70002, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=2000)
        status = wt.get_wall_status("BTC")
        assert status.prior_reversals >= 1

    def test_stale_wall_expires(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        # 20 minutes later, no new events — wall should be stale
        status = wt.get_wall_status("BTC", now=1000 + 1200)
        assert status is None or status.consecutive_reversals == 0

    def test_gold_signal_requires_ob_prior_last3(self):
        wt = WallTracker()
        # Build a wall: prior visit + OB + 3 consecutive reversals
        # Prior visit (different wall instance, same price level)
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.3,
                             gravity=100000, timestamp=1000)
        # Gap > 15min (new wall at same level)
        for i in range(3):
            wt.on_zone_finalized("BTC", zone_center=70000 + i * 3,
                                 zone_side="bid", reversal=True, breached=False,
                                 min_size_ratio=0.3, gravity=100000,
                                 timestamp=2000 + i * 30)
        status = wt.get_wall_status("BTC")
        assert status.gold_signal is True
        assert status.prior_reversals >= 1
        assert status.consecutive_reversals >= 3
        assert status.is_ob is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest runtime/tests/test_wall_tracker.py -v`
Expected: FAIL — module `wall_tracker` doesn't exist yet

- [ ] **Step 3: Implement WallTracker**

```python
# runtime/liquidations/wall_tracker.py
"""
Real-time macro wall tracker.

Aggregates individual zone reversal/breach events into macro walls.
Tracks consecutive reversals, OB absorption, and prior visits
to detect high-confidence structural levels.

Research: memory/gravity_wall_research.md
Gold filter: OB + prior held + last3=3 → 100% reversal (N=88, 11 days)
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class WallStatus:
    """Current state of macro wall at a price level."""
    coin: str
    center: float                   # Gravity-weighted center of wall
    side: str                       # "bid" or "ask"
    consecutive_reversals: int      # Last N zones that ALL reversed
    total_zones: int                # Zones in current wall
    total_gravity: float            # Sum of zone gravity in wall
    is_ob: bool                     # Has deep absorption (≥50%) or ≥2 absorbed zones
    absorbed_zones: int             # Zones with ≥30% absorption
    prior_reversals: int            # Times this level reversed in last 4h
    gold_signal: bool               # OB + prior held + last3=3
    last_event_ts: float            # Timestamp of most recent zone event
    wall_band_low: float = 0.0     # Lowest zone center in wall
    wall_band_high: float = 0.0    # Highest zone center in wall

    # For bracket exit: next wall in bounce direction
    next_wall_center: Optional[float] = None
    next_wall_distance_bp: Optional[float] = None


_WALL_BAND_BP = 100         # Zones within 100bp = same wall
_WALL_TIME_WINDOW = 900     # 15min max between zone events in same wall
_PRIOR_VISIT_WINDOW = 14400 # 4h lookback for prior visits
_PRIOR_VISIT_BAND_BP = 50   # Prior visit = within 50bp of current wall
_WALL_STALE_SEC = 900       # Wall expires after 15min of no events
_OB_DEEP_THRESHOLD = 0.50   # min_size_ratio ≤ 0.50 = deep absorption
_OB_ABSORBED_THRESHOLD = 0.30  # min_size_ratio ≤ 0.70 = absorbed


@dataclass
class _ZoneEvent:
    """Internal: single zone event within a wall."""
    center: float
    gravity: float
    reversal: bool
    breached: bool
    absorbed: bool           # ≥30% consumed
    deep_absorbed: bool      # ≥50% consumed
    timestamp: float


@dataclass
class _WallState:
    """Internal: accumulating wall state."""
    coin: str
    side: str
    events: List[_ZoneEvent] = field(default_factory=list)
    first_ts: float = 0.0
    last_ts: float = 0.0


class WallTracker:
    """Tracks macro walls from individual zone events in real-time."""

    def __init__(self):
        self._current_wall: Dict[str, _WallState] = {}  # coin → active wall
        self._wall_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=200)
        )  # coin → recent completed walls (for prior visit tracking)

    def on_zone_finalized(
        self,
        coin: str,
        zone_center: float,
        zone_side: str,
        reversal: bool,
        breached: bool,
        min_size_ratio: float,
        gravity: float,
        timestamp: float,
    ):
        """Called when gravity observer finalizes a zone event."""
        absorbed = (1 - min_size_ratio) >= _OB_ABSORBED_THRESHOLD
        deep_absorbed = (1 - min_size_ratio) >= _OB_DEEP_THRESHOLD

        event = _ZoneEvent(
            center=zone_center, gravity=gravity,
            reversal=reversal, breached=breached,
            absorbed=absorbed, deep_absorbed=deep_absorbed,
            timestamp=timestamp,
        )

        wall = self._current_wall.get(coin)

        # Check if event belongs to current wall
        if wall and wall.events:
            last = wall.events[-1]
            price_gap = abs(zone_center - last.center) / last.center * 10000 if last.center > 0 else 999
            time_gap = timestamp - wall.last_ts

            if price_gap <= _WALL_BAND_BP and time_gap <= _WALL_TIME_WINDOW:
                # Same wall — append
                wall.events.append(event)
                wall.last_ts = timestamp
                return

            # Different wall — archive current, start new
            self._archive_wall(wall)

        # Start new wall
        self._current_wall[coin] = _WallState(
            coin=coin, side=zone_side,
            events=[event],
            first_ts=timestamp, last_ts=timestamp,
        )

    def get_wall_status(self, coin: str, now: float = None) -> Optional[WallStatus]:
        """Get current macro wall status for a coin.

        Returns None if no active wall or wall is stale.
        """
        if now is None:
            now = time.time()

        wall = self._current_wall.get(coin)
        if not wall or not wall.events:
            return None

        # Stale check
        if now - wall.last_ts > _WALL_STALE_SEC:
            self._archive_wall(wall)
            self._current_wall.pop(coin, None)
            return None

        events = wall.events
        total_gravity = sum(e.gravity for e in events)
        centers = [e.center for e in events]
        grav_center = sum(e.center * e.gravity for e in events) / max(total_gravity, 1)

        # Consecutive reversals from tail
        consec = 0
        for e in reversed(events):
            if e.reversal:
                consec += 1
            else:
                break

        # OB detection
        absorbed_count = sum(1 for e in events if e.absorbed)
        has_deep = any(e.deep_absorbed for e in events)
        is_ob = has_deep or absorbed_count >= 2

        # Prior visit tracking
        prior_rev = self._count_prior_reversals(coin, grav_center, wall.first_ts)

        # Gold signal
        gold = is_ob and prior_rev >= 1 and consec >= 3

        return WallStatus(
            coin=coin,
            center=grav_center,
            side=wall.side,
            consecutive_reversals=consec,
            total_zones=len(events),
            total_gravity=total_gravity,
            is_ob=is_ob,
            absorbed_zones=absorbed_count,
            prior_reversals=prior_rev,
            gold_signal=gold,
            last_event_ts=wall.last_ts,
            wall_band_low=min(centers),
            wall_band_high=max(centers),
        )

    def _count_prior_reversals(self, coin: str, center: float, before_ts: float) -> int:
        """Count reversals at this price level in the last 4 hours."""
        count = 0
        cutoff = before_ts - _PRIOR_VISIT_WINDOW
        for hist_wall in self._wall_history.get(coin, []):
            if hist_wall['ts'] < cutoff:
                continue
            if hist_wall['ts'] >= before_ts:
                continue
            price_gap = abs(hist_wall['center'] - center) / center * 10000 if center > 0 else 999
            if price_gap <= _PRIOR_VISIT_BAND_BP:
                count += hist_wall['reversals']
        return count

    def _archive_wall(self, wall: _WallState):
        """Move completed wall to history for prior-visit tracking."""
        if not wall.events:
            return
        total_grav = sum(e.gravity for e in wall.events)
        center = sum(e.center * e.gravity for e in wall.events) / max(total_grav, 1)
        reversals = sum(1 for e in wall.events if e.reversal)
        self._wall_history[wall.coin].append({
            'center': center,
            'ts': wall.last_ts,
            'reversals': reversals,
            'gravity': total_grav,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest runtime/tests/test_wall_tracker.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/liquidations/wall_tracker.py runtime/tests/test_wall_tracker.py
git commit -m "feat: add WallTracker for macro wall detection and OB classification"
```

---

### Task 2: Wire WallTracker into Gravity Observer

**Files:**
- Modify: `runtime/liquidations/gravity_observer.py` (lines 309-323, `_finalize` method)
- Modify: `runtime/collector/service.py` (line 348, init + line 1425 area)

The gravity observer already finalizes zone events with reversal/breached. We feed those into the WallTracker.

- [ ] **Step 1: Add WallTracker to GravityObserver**

In `runtime/liquidations/gravity_observer.py`, add to `__init__`:

```python
from runtime.liquidations.wall_tracker import WallTracker

class GravityObserver:
    def __init__(self, min_obs_gravity: float = 5000):
        self._min_gravity = min_obs_gravity
        self._active: Dict[str, Optional[ZoneArrivalEvent]] = {}
        self._last_price: Dict[str, float] = {}
        self._last_zone: Dict[str, Optional[tuple]] = {}
        self._recent: deque = deque(maxlen=500)
        self._pending_persist: List[ZoneArrivalEvent] = []
        self.wall_tracker = WallTracker()  # NEW
```

- [ ] **Step 2: Feed finalized events into WallTracker**

In `_finalize()` method (around line 316-323), after computing reversal and before appending to `_recent`:

```python
    def _finalize(self, coin: str, event: ZoneArrivalEvent):
        # ... existing reversal computation ...
        event.reversal = (event.approach_direction != event.exit_direction)

        # Feed into wall tracker
        self.wall_tracker.on_zone_finalized(
            coin=coin,
            zone_center=event.zone_center,
            zone_side=event.zone_side,
            reversal=event.reversal,
            breached=event.breached,
            min_size_ratio=event.min_size_ratio,
            gravity=event.zone_gravity,
            timestamp=event.arrival_ts,
        )

        self._recent.append(event)
        self._pending_persist.append(event)
        self._active[coin] = None
```

- [ ] **Step 3: Expose wall status API**

Add method to GravityObserver:

```python
    def get_wall_status(self, coin: str):
        """Get current macro wall status. Returns WallStatus or None."""
        return self.wall_tracker.get_wall_status(coin)
```

- [ ] **Step 4: Run existing tests + new tests**

Run: `pytest runtime/tests/ -v -k "wall or gravity"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/liquidations/gravity_observer.py
git commit -m "feat: wire WallTracker into GravityObserver finalization"
```

---

### Task 3: Shadow-Log Wall Status with Entries

**Files:**
- Modify: `runtime/collector/service.py` (entry context building, ~line 1700 area and ~line 2275 area)

Before making wall status gate entries, shadow-log it alongside every trade for data collection. Uses the existing `entry_context` JSONB column added earlier today.

- [ ] **Step 1: Add wall status to entry context**

In service.py, where `self._trade_entry_context[symbol]` is built (after decel phase classification, ~line 1708):

```python
                                # Persist context for PG (survives log rotation)
                                _rz = self._rolling_volume_tracker.get_current_z(symbol, timestamp)
                                _wall = self._gravity_observer.get_wall_status(
                                    symbol.replace("USDT", ""))
                                self._trade_entry_context[symbol] = {
                                    "decel_phase": _phase,
                                    "decel_ratio": round(_d_ratio, 3),
                                    "v_recent_bp": round(_d_recent, 2),
                                    "v_prior_bp": round(_d_prior, 2),
                                    "cd_recent": round(_cd_recent, 2),
                                    "cd_prior": round(_cd_prior, 2),
                                    "rolling_z": round(_rz, 2) if _rz else None,
                                    "fade_dir": rolling_fade_signal.fade_direction,
                                    # Wall status (shadow)
                                    "wall_consec_rev": _wall.consecutive_reversals if _wall else None,
                                    "wall_is_ob": _wall.is_ob if _wall else None,
                                    "wall_prior_rev": _wall.prior_reversals if _wall else None,
                                    "wall_gold": _wall.gold_signal if _wall else None,
                                    "wall_gravity": round(_wall.total_gravity, 0) if _wall else None,
                                }
```

- [ ] **Step 2: Add wall shadow log to SLBRS entries**

Find where SLBRS entries are processed in service.py (search for `EP2-SLBRS-V1` or `slbrs`). Add wall status to the entry context for SLBRS trades too. The exact location depends on where SLBRS proposals become trades — find it and add:

```python
                        _wall = self._gravity_observer.get_wall_status(
                            result.symbol.replace("USDT", ""))
                        _wall_ctx = {
                            "wall_consec_rev": _wall.consecutive_reversals if _wall else None,
                            "wall_is_ob": _wall.is_ob if _wall else None,
                            "wall_prior_rev": _wall.prior_reversals if _wall else None,
                            "wall_gold": _wall.gold_signal if _wall else None,
                            "wall_gravity": round(_wall.total_gravity, 0) if _wall else None,
                        }
                        # Merge into entry_context or log separately
                        print(f"[WALL-SHADOW] {result.symbol}: {_wall_ctx}", flush=True)
```

- [ ] **Step 3: Verify shadow logging works**

Run: `systemctl --user restart paper-trade.service`
Wait for a trade, then check: `python scripts/analyze_trades.py --hours 1`
Verify `wall_*` fields appear in entry_context.

- [ ] **Step 4: Commit**

```bash
git add runtime/collector/service.py
git commit -m "feat: shadow-log wall status with every entry for data collection"
```

---

### Task 4: BracketExitManager — OB-Target Exits

**Files:**
- Create: `runtime/liquidations/bracket_exit.py`
- Test: `runtime/tests/test_bracket_exit.py`

Separate from trailing stop manager. Fixed bracket: TP at next wall, SL at 30bp, 60min max hold. No trailing.

- [ ] **Step 1: Write failing tests**

```python
# runtime/tests/test_bracket_exit.py
import pytest
from runtime.liquidations.bracket_exit import BracketExitManager, BracketConfig

class TestBracketExit:
    def test_no_brackets_no_exit(self):
        mgr = BracketExitManager()
        result = mgr.check_exits("BTC", 70000)
        assert result == []

    def test_long_tp_hit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        # Price at TP
        exits = mgr.check_exits("BTC", 70050, now=1100)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_TP'
        assert exits[0]['entry_id'] == 'trade1'

    def test_long_sl_hit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        # Price at SL (30bp below entry = 70000 * 0.003 = 21 points)
        exits = mgr.check_exits("BTC", 69979, now=1100)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_SL'

    def test_short_tp_hit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="SHORT",
                      entry_price=70000, tp_price=69950, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        exits = mgr.check_exits("BTC", 69950, now=1100)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_TP'

    def test_max_hold_exit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        # 61 minutes later, price neutral
        exits = mgr.check_exits("BTC", 70010, now=1000 + 3660)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_TIMEOUT'

    def test_unregister(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        mgr.unregister("trade1")
        exits = mgr.check_exits("BTC", 70050, now=1100)
        assert exits == []

    def test_no_exit_in_range(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        exits = mgr.check_exits("BTC", 70025, now=1100)
        assert exits == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest runtime/tests/test_bracket_exit.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement BracketExitManager**

```python
# runtime/liquidations/bracket_exit.py
"""
Bracket exit manager for OB-target trades.

Fixed TP/SL bracket with time cutoff. No trailing.
Research: OB target exit → 89% WR, +42bp avg, 14.1x PF at SL=30bp.
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class BracketConfig:
    sl_bps: float = 30.0         # Stop loss in basis points
    max_hold_sec: float = 3600   # 60 minute max hold


@dataclass
class _BracketState:
    entry_id: str
    symbol: str
    direction: str        # "LONG" or "SHORT"
    entry_price: float
    tp_price: float       # Take profit price (next OB wall)
    sl_price: float       # Stop loss price
    entry_ts: float
    max_hold_sec: float


class BracketExitManager:
    """Manages fixed TP/SL/timeout brackets for OB-confirmed trades."""

    def __init__(self):
        self._brackets: Dict[str, _BracketState] = {}  # entry_id → state

    def register(
        self,
        entry_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        tp_price: float,
        sl_bps: float = 30.0,
        max_hold_sec: float = 3600,
        entry_ts: float = None,
    ):
        """Register a new bracket exit."""
        if entry_ts is None:
            entry_ts = time.time()

        if direction == "LONG":
            sl_price = entry_price * (1 - sl_bps / 10000)
        else:
            sl_price = entry_price * (1 + sl_bps / 10000)

        self._brackets[entry_id] = _BracketState(
            entry_id=entry_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            entry_ts=entry_ts,
            max_hold_sec=max_hold_sec,
        )

    def unregister(self, entry_id: str):
        """Remove bracket (position closed externally)."""
        self._brackets.pop(entry_id, None)

    def check_exits(
        self, symbol: str, price: float, now: float = None
    ) -> List[dict]:
        """Check if any brackets triggered for this symbol.

        Returns list of {'entry_id', 'reason', 'price'} dicts.
        """
        if now is None:
            now = time.time()

        exits = []
        for entry_id, state in list(self._brackets.items()):
            if state.symbol != symbol:
                continue

            reason = None

            # TP check
            if state.direction == "LONG" and price >= state.tp_price:
                reason = "BRACKET_TP"
            elif state.direction == "SHORT" and price <= state.tp_price:
                reason = "BRACKET_TP"

            # SL check
            if reason is None:
                if state.direction == "LONG" and price <= state.sl_price:
                    reason = "BRACKET_SL"
                elif state.direction == "SHORT" and price >= state.sl_price:
                    reason = "BRACKET_SL"

            # Timeout check
            if reason is None:
                if now - state.entry_ts >= state.max_hold_sec:
                    reason = "BRACKET_TIMEOUT"

            if reason:
                exits.append({
                    'entry_id': entry_id,
                    'reason': reason,
                    'price': price,
                    'entry_price': state.entry_price,
                    'tp_price': state.tp_price,
                    'sl_price': state.sl_price,
                    'hold_sec': now - state.entry_ts,
                })
                self._brackets.pop(entry_id)

        return exits

    def get_bracket(self, entry_id: str) -> Optional[_BracketState]:
        return self._brackets.get(entry_id)

    def has_bracket(self, symbol: str) -> bool:
        return any(s.symbol == symbol for s in self._brackets.values())
```

- [ ] **Step 4: Run tests**

Run: `pytest runtime/tests/test_bracket_exit.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/liquidations/bracket_exit.py runtime/tests/test_bracket_exit.py
git commit -m "feat: add BracketExitManager for OB-target fixed TP/SL exits"
```

---

### Task 5: Inject Wall Confirmation into SLBRS Strategy

**Files:**
- Modify: `external_policy/ep2_slbrs_strategy.py` (lines 727-901, `_check_retest_entry`)

Add wall status as optional confidence boost. NOT a hard gate yet — shadow period first. When `gold_signal=True`, log it prominently. When we're ready to gate, uncomment the hard requirement.

- [ ] **Step 1: Add wall_status parameter to generate_proposal**

In `ep2_slbrs_strategy.py`, add `wall_status=None` parameter to `generate_proposal()` signature (line 243):

```python
    def generate_proposal(
        self,
        *,
        symbol: str,
        regime_state: Optional[RegimeState],
        # ... existing params ...
        capitulation_confidence: float = 0.0,
        wall_status=None  # NEW: WallStatus from gravity observer
    ) -> Optional[StrategyProposal]:
```

Pass it through to `_check_retest_entry()` — add `wall_status=None` parameter there too.

- [ ] **Step 2: Add wall status logging at entry decision point**

In `_check_retest_entry()`, right before the entry diagnostic (line 887), add:

```python
        # Wall status shadow logging
        _wall_info = "none"
        _wall_gold = False
        if wall_status:
            _wall_info = (f"consec={wall_status.consecutive_reversals} "
                         f"ob={wall_status.is_ob} prior={wall_status.prior_reversals} "
                         f"gold={wall_status.gold_signal} grav={wall_status.total_gravity:,.0f}")
            _wall_gold = wall_status.gold_signal

        print(f"[SLBRS-WALL] {symbol}: {_wall_info}", flush=True)

        # TODO: When ready to gate, uncomment:
        # if not _wall_gold:
        #     self._count_reject("wall_not_gold")
        #     return None
```

- [ ] **Step 3: Update `generate_slbrs_proposal()` wrapper**

In `external_policy/ep2_slbrs_strategy.py` line 996, update the wrapper function signature and passthrough:

```python
def generate_slbrs_proposal(
    *,
    symbol: str,
    regime_state: Optional[RegimeState],
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence,
    price: float,
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None,
    absorption_event=None,
    directional_continuity=None,
    orderflow_imbalance: Optional[float] = None,
    orderflow_fill_count: int = 0,
    capitulation_confidence: float = 0.0,
    wall_status=None  # NEW
) -> Optional[StrategyProposal]:
    return _slbrs_strategy.generate_proposal(
        symbol=symbol,
        regime_state=regime_state,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=price,
        context=context,
        permission=permission,
        position_state=position_state,
        absorption_event=absorption_event,
        directional_continuity=directional_continuity,
        orderflow_imbalance=orderflow_imbalance,
        orderflow_fill_count=orderflow_fill_count,
        capitulation_confidence=capitulation_confidence,
        wall_status=wall_status,  # NEW
    )
```

- [ ] **Step 4: Pass wall_status from service.py**

Find where `generate_slbrs_proposal()` is called in service.py (~line 1489-1520) and add:

```python
        _wall = self._gravity_observer.get_wall_status(
            hl_symbol, liquidity_map=self._liquidity_map,
            price=current_price)
        proposal = generate_slbrs_proposal(
            # ... existing params ...
            wall_status=_wall,
        )
```

- [ ] **Step 4: Run SLBRS tests**

Run: `pytest -v -k slbrs`
Expected: All PASS (wall_status defaults to None, no behavior change)

- [ ] **Step 5: Commit**

```bash
git add external_policy/ep2_slbrs_strategy.py runtime/collector/service.py
git commit -m "feat: inject wall status shadow logging into SLBRS retest entry"
```

---

### Task 6: Wire BracketExitManager into Service

**Files:**
- Modify: `runtime/collector/service.py`

Wire the bracket exit manager into the price update loop alongside trailing stops. For now, only register brackets when wall_gold=True on SLBRS entries.

- [ ] **Step 1: Initialize BracketExitManager**

In `CollectorService.__init__` (near other manager inits, ~line 350):

```python
        from runtime.liquidations.bracket_exit import BracketExitManager
        self._bracket_exit_manager = BracketExitManager()
```

- [ ] **Step 2: Register bracket on SLBRS entry with gold signal**

After SLBRS entry succeeds and ghost position is opened, check wall status and register bracket if gold:

```python
                        # Register bracket exit for gold-signal SLBRS entries
                        if result.strategy_id == "EP2-SLBRS-V1":
                            _wall = self._gravity_observer.get_wall_status(
                                result.symbol.replace("USDT", ""))
                            if _wall and _wall.gold_signal and _wall.next_wall_center:
                                self._bracket_exit_manager.register(
                                    entry_id=trade.trade_id,
                                    symbol=result.symbol,
                                    direction=side,
                                    entry_price=entry_px,
                                    tp_price=_wall.next_wall_center,
                                    sl_bps=30,
                                    max_hold_sec=3600,
                                )
                                print(f"BRACKET_REGISTERED: {result.symbol} {side} "
                                      f"entry=${entry_px:,.2f} tp=${_wall.next_wall_center:,.2f} "
                                      f"sl=30bp timeout=60m")
```

- [ ] **Step 3: Check bracket exits in price update loop**

In the trailing stop section of `_process_regime_data` (where `_trailing_stop_manager.update_price` is called, ~line 3800):

```python
                # Check bracket exits (OB-target trades)
                _bracket_exits = self._bracket_exit_manager.check_exits(symbol, price)
                for _bx in _bracket_exits:
                    if self.ghost_tracker.has_open_position(symbol):
                        ok, err, trade = self.ghost_tracker.close_position(
                            symbol=symbol,
                            exit_reason=_bx['reason'],
                            exit_price=price,
                            timestamp=time.time())
                        if ok and trade:
                            pnl_str = f"${trade.pnl:+.2f}" if trade.pnl else "$0.00"
                            hold_str = f"{_bx['hold_sec']:.0f}s"
                            print(f"BRACKET_EXIT: {symbol} {_bx['reason']} @ ${price:,.2f} "
                                  f"PNL={pnl_str} hold={hold_str} "
                                  f"tp=${_bx['tp_price']:,.2f} sl=${_bx['sl_price']:,.2f}")
                            self._force_position_flat(symbol)
                            # Unregister any trailing stop for this symbol
                            for eid in list(self._trailing_stop_manager.get_all_stops().keys()):
                                if self._trailing_stop_manager.get_all_stops()[eid].symbol == symbol:
                                    self._trailing_stop_manager.unregister_stop(eid)
```

- [ ] **Step 4: Add next_wall_center to WallStatus**

In `wall_tracker.py`, update `get_wall_status()` to populate `next_wall_center` using the liquidity map. This requires passing the liquidity map reference:

```python
    def get_wall_status(self, coin: str, now: float = None,
                        liquidity_map=None, current_price: float = None) -> Optional[WallStatus]:
        # ... existing logic ...

        # Find next wall in bounce direction for bracket TP
        if liquidity_map and current_price and status.consecutive_reversals >= 3:
            # Bounce direction: if wall is bid (from_above approach), bounce goes UP
            if wall.side == "bid":
                next_zones = liquidity_map.get_zones_above(coin, current_price, min_gravity=50000)
            else:
                next_zones = liquidity_map.get_zones_below(coin, current_price, min_gravity=50000)
            # Sort by distance (nearest first) — get_zones returns gravity-sorted
            next_zones_sorted = sorted(
                next_zones,
                key=lambda z: abs(z.center_price - current_price)
            )
            # Find nearest zone ≥10bp away (skip micro-adjacent zones)
            for z in next_zones_sorted:
                dist = abs(z.center_price - current_price) / current_price * 10000
                if dist >= 10:
                    status.next_wall_center = z.center_price
                    status.next_wall_distance_bp = dist
                    break

        return status
```

Update the gravity observer's `get_wall_status` to pass through liquidity_map and price:

```python
    def get_wall_status(self, coin: str, liquidity_map=None, price: float = None):
        return self.wall_tracker.get_wall_status(
            coin, liquidity_map=liquidity_map, current_price=price)
```

Update service.py calls to pass these through.

- [ ] **Step 5: Verify compilation and restart**

Run: `python -c "import runtime.collector.service; print('OK')"`
Then: `systemctl --user restart paper-trade.service`
Verify: `tail -20 paper_trade.log` — no errors

- [ ] **Step 6: Commit**

```bash
git add runtime/collector/service.py runtime/liquidations/wall_tracker.py runtime/liquidations/gravity_observer.py
git commit -m "feat: wire BracketExitManager into service for gold-signal SLBRS entries"
```

---

### Task 7: Update analyze_trades.py for Wall Data

**Files:**
- Modify: `scripts/analyze_trades.py`

Add wall status columns to the trade analysis output so we can evaluate the shadow data.

- [ ] **Step 1: Add wall columns to analysis output**

In `analyze_trades.py`, update the main query and display to show wall_status fields from entry_context:

```python
    # In the main loop, extract wall fields:
    wall_gold = ctx.get("wall_gold", None)
    wall_rev = ctx.get("wall_consec_rev", None)
    wall_ob = ctx.get("wall_is_ob", None)

    # Add to print:
    wall_str = "GOLD" if wall_gold else (f"w{wall_rev}" if wall_rev else "")
```

Add a "By Wall Status" aggregation section similar to the existing "By Decel Phase" section.

- [ ] **Step 2: Test**

Run: `python scripts/analyze_trades.py --hours 24`
Verify wall columns appear (will be empty until new trades fire with shadow data).

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_trades.py
git commit -m "feat: add wall status columns to trade analysis script"
```

---

## Execution Notes

**Task dependencies:**
- Tasks 1 and 4 are independent (WallTracker and BracketExitManager have no shared code).
- Task 2 depends on Task 1 (wires WallTracker into GravityObserver).
- Task 3 depends on Task 2 (calls `get_wall_status()` which requires Task 2).
- Task 5 depends on Task 2 (SLBRS consumes wall status from observer).
- Task 6 depends on Tasks 1-5 (wires everything together).
- Task 7 is independent (just reporting).

**SLBRS is currently DISABLED** (`enable_slbrs=False` in service.py:188, 26% WR). Task 5's SLBRS-specific shadow logging will only fire when SLBRS is re-enabled. However, Task 3's cascade entry shadow logging works regardless — wall status is logged for ALL entries (cascade sniper included). This is sufficient for the shadow period.

**Shadow period**: After deployment, collect 2-3 weeks of data with wall status logged on cascade entries. Analyze: do wall-confirmed cascade entries outperform non-confirmed? Separately, when ready to re-enable SLBRS with wall confirmation as a hard gate, change `enable_slbrs=True` and uncomment the gate in Task 5.

**Stale bracket cleanup**: When positions are closed by OTHER exit paths (trailing stop, CCK kill, reconcile), the bracket remains registered but harmless (ghost_tracker.has_open_position check prevents double-close). Add periodic cleanup: in the bracket check loop, unregister brackets for symbols with no open position.

**No trailing stop for bracket trades**: BracketExitManager handles exits independently. When a bracket is registered, the trailing stop manager should NOT also manage the same position. Task 6 handles this by unregistering trailing stops on bracket exit.
