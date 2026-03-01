"""Whale Fill Tracker — per-wallet fill aggregator for whale manipulation detection.

Detects coordinated whale accumulation followed by sudden dump.
Follows RollingVolumeTracker lifecycle: on_fill / check_for_signal / confirm_signal / trim_windows.

Thread safety:
- on_fill() called from gRPC daemon thread (deque append is GIL-safe)
- check_for_signal() / confirm_signal() / trim_windows() called from asyncio loop
- All reads take list() snapshots before iteration
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Deque


# ── Data Structures ──────────────────────────────────────────────────

@dataclass
class _WalletFill:
    timestamp: float        # Wall clock at ingestion (for expiry/freshness)
    block_timestamp: float  # Original block timestamp (for sequence/duration analysis)
    symbol: str
    side: str       # "B" (buy) or "A" (sell)
    price: float
    size: float
    value_usd: float
    dir_type: str   # "Open Long", "Close Long", "Open Short", "Close Short", etc.
    closed_pnl: float
    is_liquidation: bool


@dataclass(frozen=True)
class WhaleAccumulation:
    wallet: str
    symbol: str
    direction: str          # "LONG" or "SHORT"
    total_volume_usd: float
    fill_count: int
    duration_sec: float
    price_start: float
    price_end: float
    price_impact_bps: float


@dataclass(frozen=True)
class WhaleDumpSignal:
    symbol: str
    dump_wallet: str
    dump_volume_usd: float
    dump_duration_sec: float
    dump_closed_pnl: float
    accumulation: WhaleAccumulation
    fade_direction: str     # "LONG" or "SHORT" — direction we trade
    confidence: float       # 0.0–1.0


# ── Constants ────────────────────────────────────────────────────────

MIN_FILL_VALUE_USD = 10_000          # Pre-filter: only track fills >= $10k
MAX_TRACKED_WALLETS = 500            # LRU eviction when exceeded
WALLET_INACTIVE_SEC = 1800           # Prune wallets with no fills in 30 min
ACCUMULATION_WINDOW = 600            # 10 min accumulation window
MIN_ACCUMULATION_FILLS = 3           # Minimum fills for accumulation
MIN_ACCUMULATION_VOLUME = 500_000    # $500k minimum volume
MIN_SAME_DIRECTION_PCT = 0.80        # 80% same direction
DUMP_WINDOW = 30                     # 30s dump window
MIN_DUMP_VOLUME = 1_000_000          # $1M minimum dump volume
DUMP_FILL_SIZE_MULTIPLIER = 2.0      # Dump fill ≥ 2× avg accumulation fill
SIGNAL_COOLDOWN = 900                # 15 min cooldown per coin
MIN_CONFIDENCE = 0.5                 # Minimum confidence for signal


# ── Direction Helpers (matches HL dir format, same logic as capitulation.py) ──

def _is_opening_fill(dir_type: str) -> bool:
    """True if fill explicitly opens a new position.

    Flips ('Long > Short', 'Short > Long') are NOT accumulation — they
    close old + open new in one trade. We detect them separately as dumps
    via _closes_long/_closes_short.
    """
    return dir_type.startswith("Open ")


def _opens_long(dir_type: str) -> bool:
    """True if fill explicitly opens a new LONG position."""
    return dir_type == "Open Long"


def _opens_short(dir_type: str) -> bool:
    """True if fill explicitly opens a new SHORT position."""
    return dir_type == "Open Short"


def _closes_long(dir_type: str) -> bool:
    """True if fill reduces/closes a LONG position.

    Matches capitulation.py pattern: startswith('Close') or '>' in dir_type,
    narrowed to long-closing variants.
    """
    return dir_type.startswith("Close Long") or "Long >" in dir_type


def _closes_short(dir_type: str) -> bool:
    """True if fill reduces/closes a SHORT position.

    Matches capitulation.py pattern: startswith('Close') or '>' in dir_type,
    narrowed to short-closing variants.
    """
    return dir_type.startswith("Close Short") or "Short >" in dir_type


# ── Tracker ──────────────────────────────────────────────────────────

class WhaleFillTracker:
    """Per-wallet fill aggregator detecting whale accumulation + dump patterns."""

    def __init__(self):
        # Per-wallet, per-symbol rolling fills
        self._wallet_fills: Dict[str, Dict[str, Deque[_WalletFill]]] = {}
        # Detected accumulation patterns: symbol → {wallet → WhaleAccumulation}
        self._active_accumulations: Dict[str, Dict[str, WhaleAccumulation]] = {}
        # Signal cooldown per coin
        self._last_signal_ts: Dict[str, float] = {}
        # LRU eviction tracking
        self._wallet_last_seen: Dict[str, float] = {}
        # Per-symbol wallet index: symbol → set(wallet) — avoids full wallet scan
        self._symbol_wallets: Dict[str, set] = {}

    def on_fill(self, event) -> None:
        """Ingest a FillEvent. Called from gRPC daemon thread.

        Pre-filters on value >= MIN_FILL_VALUE_USD.
        Only tracks fills with dir metadata (position direction info).
        """
        try:
            value_usd = float(event.value_usd) if event.value_usd else 0.0
            if value_usd < MIN_FILL_VALUE_USD:
                return

            if not event.dir:
                return  # No direction metadata — can't classify

            wallet = event.wallet
            if not wallet:
                return

            symbol = f"{event.symbol}USDT" if not event.symbol.endswith("USDT") else event.symbol
            price = float(event.price) if event.price else 0.0
            size = float(event.size) if event.size else 0.0
            closed_pnl = float(event.closed_pnl) if event.closed_pnl else 0.0
            # Wall clock for expiry/freshness (matches check_for_signal's time.time()).
            # Block timestamp for sequence/duration analysis within accumulations.
            # During node lag, block timestamps may be minutes old but ordering is correct.
            wall_ts = time.time()
            block_ts = event.timestamp_ms / 1000.0

            fill = _WalletFill(
                timestamp=wall_ts,
                block_timestamp=block_ts,
                symbol=symbol,
                side=event.side,
                price=price,
                size=size,
                value_usd=value_usd,
                dir_type=event.dir,
                closed_pnl=closed_pnl,
                is_liquidation=event.is_liquidation,
            )

            # Append to per-wallet per-symbol deque (GIL-safe)
            if wallet not in self._wallet_fills:
                self._wallet_fills[wallet] = {}
            if symbol not in self._wallet_fills[wallet]:
                self._wallet_fills[wallet][symbol] = deque(maxlen=200)
            self._wallet_fills[wallet][symbol].append(fill)
            self._wallet_last_seen[wallet] = time.time()

            # Maintain per-symbol index for O(wallets_per_symbol) check_for_signal
            if symbol not in self._symbol_wallets:
                self._symbol_wallets[symbol] = set()
            self._symbol_wallets[symbol].add(wallet)

            # LRU eviction when too many wallets
            if len(self._wallet_fills) > MAX_TRACKED_WALLETS:
                self._evict_oldest_wallet()

        except Exception:
            pass  # Fail silently — daemon thread

    def check_for_signal(self, symbol: str, timestamp: float) -> Optional[WhaleDumpSignal]:
        """Check for whale dump signal on this symbol. Called from asyncio loop.

        Scans all tracked wallets for accumulation patterns, then checks
        for dump reversal from wallets with active accumulation.

        Returns WhaleDumpSignal if detected, None otherwise.
        """
        # Cooldown check
        last_ts = self._last_signal_ts.get(symbol, 0)
        if timestamp - last_ts < SIGNAL_COOLDOWN:
            return None

        # Scan only wallets with fills for this symbol (via index)
        best_signal: Optional[WhaleDumpSignal] = None
        candidate_wallets = list(self._symbol_wallets.get(symbol, set()))

        for wallet in candidate_wallets:
            if wallet not in self._wallet_fills:
                continue
            symbols_dict = self._wallet_fills[wallet]
            if symbol not in symbols_dict:
                continue

            fills = list(symbols_dict[symbol])  # Thread-safe snapshot
            if len(fills) < MIN_ACCUMULATION_FILLS:
                continue

            # Detect accumulation
            accumulation = self._detect_accumulation(wallet, symbol, fills, timestamp)
            if accumulation:
                # Store active accumulation
                if symbol not in self._active_accumulations:
                    self._active_accumulations[symbol] = {}
                self._active_accumulations[symbol][wallet] = accumulation

            # Check for dump from wallets with active accumulation
            if symbol in self._active_accumulations:
                for acc_wallet, acc in list(self._active_accumulations[symbol].items()):
                    if acc_wallet not in self._wallet_fills:
                        continue
                    if symbol not in self._wallet_fills[acc_wallet]:
                        continue

                    acc_fills = list(self._wallet_fills[acc_wallet][symbol])
                    dump = self._detect_dump(acc_wallet, symbol, acc_fills, acc, timestamp)
                    if dump and (best_signal is None or dump.confidence > best_signal.confidence):
                        best_signal = dump

        return best_signal

    def confirm_signal(self, symbol: str, timestamp: float) -> None:
        """Confirm signal was evaluated — starts cooldown.

        Called when strategy accepts signal OR hard gate consumes it.
        """
        self._last_signal_ts[symbol] = timestamp
        # Clear active accumulations for this symbol (consumed)
        self._active_accumulations.pop(symbol, None)

    def trim_windows(self, timestamp: float) -> None:
        """Periodic maintenance. Prune inactive wallets, old fills, stale accumulations."""
        cutoff = timestamp - WALLET_INACTIVE_SEC
        # Prune inactive wallets + clean index
        stale = [w for w, ts in self._wallet_last_seen.items() if ts < cutoff]
        for w in stale:
            # Remove from symbol index before deleting fills
            for sym in list(self._wallet_fills.get(w, {})):
                if sym in self._symbol_wallets:
                    self._symbol_wallets[sym].discard(w)
            self._wallet_fills.pop(w, None)
            self._wallet_last_seen.pop(w, None)

        # Prune old fills per wallet per symbol
        fill_cutoff = timestamp - ACCUMULATION_WINDOW - DUMP_WINDOW
        for wallet in list(self._wallet_fills):
            for sym in list(self._wallet_fills[wallet]):
                dq = self._wallet_fills[wallet][sym]
                while dq and dq[0].timestamp < fill_cutoff:
                    dq.popleft()
                if not dq:
                    del self._wallet_fills[wallet][sym]
                    if sym in self._symbol_wallets:
                        self._symbol_wallets[sym].discard(wallet)
            if not self._wallet_fills[wallet]:
                del self._wallet_fills[wallet]

        # Prune stale accumulations: remove if the accumulating wallet has no
        # recent fills left (fills were pruned above) or wallet was evicted entirely.
        # An accumulation without backing fills can never produce a valid dump signal.
        for sym in list(self._active_accumulations):
            for w in list(self._active_accumulations[sym]):
                if w not in self._wallet_fills or sym not in self._wallet_fills.get(w, {}):
                    del self._active_accumulations[sym][w]
            if not self._active_accumulations.get(sym):
                self._active_accumulations.pop(sym, None)

    # ── Internal Detection ───────────────────────────────────────────

    def _detect_accumulation(
        self, wallet: str, symbol: str, fills: list, timestamp: float
    ) -> Optional[WhaleAccumulation]:
        """Detect accumulation pattern in recent fills for a wallet+symbol.

        Requirements:
        - ≥3 fills within ACCUMULATION_WINDOW (10 min)
        - ≥$500k total volume
        - ≥80% same direction (Open Long or Open Short)
        """
        cutoff = timestamp - ACCUMULATION_WINDOW
        recent = [f for f in fills if f.timestamp >= cutoff]

        # Only consider explicit position-opening fills ("Open Long", "Open Short").
        # Flips ("Long > Short") are excluded — they close+open in one trade and
        # represent a position change, not deliberate accumulation.
        # Close/reversal fills are handled separately by _detect_dump.
        open_fills = [f for f in recent if _is_opening_fill(f.dir_type)]
        if len(open_fills) < MIN_ACCUMULATION_FILLS:
            return None

        total_volume = sum(f.value_usd for f in open_fills)
        if total_volume < MIN_ACCUMULATION_VOLUME:
            return None

        # Count direction from explicit opens only
        # "Open Long" → LONG accumulation, "Open Short" → SHORT accumulation
        long_volume = sum(f.value_usd for f in open_fills if _opens_long(f.dir_type))
        short_volume = sum(f.value_usd for f in open_fills if _opens_short(f.dir_type))

        if long_volume >= total_volume * MIN_SAME_DIRECTION_PCT:
            direction = "LONG"
        elif short_volume >= total_volume * MIN_SAME_DIRECTION_PCT:
            direction = "SHORT"
        else:
            return None  # Mixed — not clear accumulation

        # Price impact (from opening fills only)
        price_start = open_fills[0].price
        price_end = open_fills[-1].price
        if price_start > 0:
            impact_bps = abs(price_end - price_start) / price_start * 10000
        else:
            impact_bps = 0.0

        # Use block_timestamp for duration (preserves real sequence during node lag)
        duration = open_fills[-1].block_timestamp - open_fills[0].block_timestamp

        return WhaleAccumulation(
            wallet=wallet,
            symbol=symbol,
            direction=direction,
            total_volume_usd=total_volume,
            fill_count=len(open_fills),
            duration_sec=duration,
            price_start=price_start,
            price_end=price_end,
            price_impact_bps=impact_bps,
        )

    def _detect_dump(
        self, wallet: str, symbol: str, fills: list, accumulation: WhaleAccumulation,
        timestamp: float
    ) -> Optional[WhaleDumpSignal]:
        """Detect dump reversal from a wallet with active accumulation.

        Requirements:
        - Within DUMP_WINDOW (30s)
        - ≥$1M dump volume
        - Fill size ≥ 2× avg accumulation fill
        - Direction reversal: Close*/flip that reduces accumulated position
        - closed_pnl is a confidence factor (not hard gate)
        """
        cutoff = timestamp - DUMP_WINDOW
        recent = [f for f in fills if f.timestamp >= cutoff]
        if not recent:
            return None

        # Identify dump fills (reversal direction).
        # Uses startswith('Close')/contains('>') pattern from capitulation.py,
        # narrowed to the side being closed.
        if accumulation.direction == "LONG":
            # Dump = closing/flipping longs (selling)
            dump_fills = [f for f in recent if _closes_long(f.dir_type)]
        else:
            # Dump = closing/flipping shorts (buying back)
            dump_fills = [f for f in recent if _closes_short(f.dir_type)]

        if not dump_fills:
            return None

        dump_volume = sum(f.value_usd for f in dump_fills)
        if dump_volume < MIN_DUMP_VOLUME:
            return None

        # Check fill size multiplier
        avg_acc_fill = accumulation.total_volume_usd / max(accumulation.fill_count, 1)
        max_dump_fill = max(f.value_usd for f in dump_fills)
        if max_dump_fill < avg_acc_fill * DUMP_FILL_SIZE_MULTIPLIER:
            return None

        total_pnl = sum(f.closed_pnl for f in dump_fills)

        # Use block_timestamp for duration (preserves real timing)
        dump_duration = dump_fills[-1].block_timestamp - dump_fills[0].block_timestamp

        # Fade direction: opposite of dump
        # Whale dumps LONG (sells) → we go LONG (buy the dip)
        # Whale dumps SHORT (covers) → we go SHORT
        if accumulation.direction == "LONG":
            fade_direction = "LONG"
        else:
            fade_direction = "SHORT"

        # Confidence scoring
        confidence = self._score_confidence(
            dump_volume, accumulation, total_pnl, dump_duration
        )
        if confidence < MIN_CONFIDENCE:
            return None

        return WhaleDumpSignal(
            symbol=symbol,
            dump_wallet=wallet,
            dump_volume_usd=dump_volume,
            dump_duration_sec=dump_duration,
            dump_closed_pnl=total_pnl,
            accumulation=accumulation,
            fade_direction=fade_direction,
            confidence=confidence,
        )

    def _score_confidence(
        self, dump_volume: float, accumulation: WhaleAccumulation,
        closed_pnl: float, dump_duration: float
    ) -> float:
        """Score confidence 0.0–1.0 for whale dump signal."""
        score = 0.0

        # Dump volume tiers
        if dump_volume >= 5_000_000:
            score += 0.3
        elif dump_volume >= 2_000_000:
            score += 0.2
        elif dump_volume >= 1_000_000:
            score += 0.1

        # Accumulation duration (longer = more deliberate)
        if accumulation.duration_sec >= 300:
            score += 0.2

        # Closed PnL magnitude — graduated boost (not hard gate).
        # Near-breakeven closes are still valid dumps, just less confident.
        if abs(closed_pnl) >= 50_000:
            score += 0.2
        elif abs(closed_pnl) >= 10_000:
            score += 0.1
        elif closed_pnl != 0:
            score += 0.05

        # Price impact of accumulation
        if accumulation.price_impact_bps >= 20:
            score += 0.2

        # Dump speed (faster = more aggressive)
        if dump_duration <= 5:
            score += 0.1

        return min(score, 1.0)

    def _evict_oldest_wallet(self) -> None:
        """Remove least recently seen wallet to stay under MAX_TRACKED_WALLETS."""
        if not self._wallet_last_seen:
            return
        oldest = min(self._wallet_last_seen, key=self._wallet_last_seen.get)
        # Clean symbol index before deleting
        for sym in list(self._wallet_fills.get(oldest, {})):
            if sym in self._symbol_wallets:
                self._symbol_wallets[sym].discard(oldest)
        self._wallet_fills.pop(oldest, None)
        self._wallet_last_seen.pop(oldest, None)
