"""
Hyperliquid Raw Data Store

HLP24-compliant storage layer: Raw facts only, no computed fields.
All derived values computed at query time.

Constitutional compliance:
- Stores only raw API responses
- No computed or derived fields
- Append-only (immutable after write)
- Full provenance tracking for wallet discovery
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from runtime.logging.execution_db import ResearchDatabase


@dataclass
class PollCycleStats:
    """Statistics for a completed poll cycle."""
    wallets_polled: int = 0
    positions_found: int = 0
    liquidations_detected: int = 0
    api_errors: int = 0
    duration_ms: int = 0


class HLDataStore:
    """
    Append-only raw data storage for Hyperliquid data.

    Follows HLP24 principles:
    - Store raw facts, derive labels later
    - All API responses stored as strings (as received)
    - No computed columns in storage
    - Timestamps in nanoseconds for precision

    Usage:
        db = ResearchDatabase("logs/execution.db")
        store = HLDataStore(db)

        # Start a poll cycle
        cycle_id = store.start_poll_cycle("tier1")

        # Store raw position data
        snapshot_id = store.store_position_snapshot(
            snapshot_ts=now_ns,
            poll_cycle_id=cycle_id,
            wallet="0x...",
            coin="BTC",
            raw_position=api_response
        )

        # End the cycle with stats
        store.end_poll_cycle(cycle_id, stats)
    """

    def __init__(self, db: ResearchDatabase):
        """Initialize data store with database connection.

        Args:
            db: ResearchDatabase instance with HLP24 tables
        """
        self._db = db
        self._current_cycle_id: Optional[int] = None

    # =========================================================================
    # Poll Cycle Management
    # =========================================================================

    def start_poll_cycle(self, cycle_type: str) -> int:
        """Start a new poll cycle for batch tracking.

        Args:
            cycle_type: Type of cycle ('tier1', 'tier2', 'tier3', 'discovery')

        Returns:
            poll_cycle_id for linking snapshots
        """
        cycle_id = self._db.start_hl_poll_cycle(cycle_type)
        self._current_cycle_id = cycle_id
        return cycle_id

    def end_poll_cycle(self, cycle_id: int, stats: PollCycleStats):
        """Complete a poll cycle with statistics.

        Args:
            cycle_id: The poll cycle ID from start_poll_cycle
            stats: Statistics collected during the cycle
        """
        self._db.end_hl_poll_cycle(
            cycle_id=cycle_id,
            wallets_polled=stats.wallets_polled,
            positions_found=stats.positions_found,
            liquidations_detected=stats.liquidations_detected,
            api_errors=stats.api_errors,
            duration_ms=stats.duration_ms
        )
        if self._current_cycle_id == cycle_id:
            self._current_cycle_id = None

    @property
    def current_cycle_id(self) -> Optional[int]:
        """Get current active poll cycle ID."""
        return self._current_cycle_id

    # =========================================================================
    # Position Snapshot Storage
    # =========================================================================

    def store_position_snapshot(
        self,
        snapshot_ts: int,
        poll_cycle_id: int,
        wallet: str,
        coin: str,
        raw_position: Dict[str, Any]
    ) -> int:
        """Store raw position snapshot from API response.

        Extracts fields from raw API response and stores as strings.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            poll_cycle_id: ID of the poll cycle
            wallet: Wallet address
            coin: Asset symbol
            raw_position: Raw position dict from Hyperliquid API

        Returns:
            Row ID of inserted snapshot
        """
        # Extract fields from raw position
        # Hyperliquid returns: szi, entryPx, liquidationPx, marginUsed, positionValue,
        # unrealizedPnl, leverage (type + value in some responses)
        return self._db.log_hl_position_snapshot_raw(
            snapshot_ts=snapshot_ts,
            poll_cycle_id=poll_cycle_id,
            wallet_address=wallet,
            coin=coin,
            szi=str(raw_position.get('szi', '')),
            entry_px=str(raw_position.get('entryPx', '')),
            liquidation_px=str(raw_position.get('liquidationPx')) if raw_position.get('liquidationPx') else None,
            leverage_type=raw_position.get('leverage', {}).get('type') if isinstance(raw_position.get('leverage'), dict) else None,
            leverage_value=raw_position.get('leverage', {}).get('value') if isinstance(raw_position.get('leverage'), dict) else raw_position.get('leverage'),
            margin_used=str(raw_position.get('marginUsed')) if raw_position.get('marginUsed') else None,
            position_value=str(raw_position.get('positionValue')) if raw_position.get('positionValue') else None,
            unrealized_pnl=str(raw_position.get('unrealizedPnl')) if raw_position.get('unrealizedPnl') else None
        )

    def store_wallet_snapshot(
        self,
        snapshot_ts: int,
        poll_cycle_id: int,
        wallet: str,
        raw_summary: Dict[str, Any]
    ) -> int:
        """Store raw wallet account snapshot.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            poll_cycle_id: ID of the poll cycle
            wallet: Wallet address
            raw_summary: Raw crossMarginSummary dict from API

        Returns:
            Row ID of inserted snapshot
        """
        return self._db.log_hl_wallet_snapshot_raw(
            snapshot_ts=snapshot_ts,
            poll_cycle_id=poll_cycle_id,
            wallet_address=wallet,
            account_value=str(raw_summary.get('accountValue')) if raw_summary.get('accountValue') else None,
            total_margin_used=str(raw_summary.get('totalMarginUsed')) if raw_summary.get('totalMarginUsed') else None,
            withdrawable=str(raw_summary.get('withdrawable')) if raw_summary.get('withdrawable') else None
        )

    # =========================================================================
    # Liquidation Detection Storage
    # =========================================================================

    def store_liquidation_event(
        self,
        detected_ts: int,
        wallet: str,
        coin: str,
        last_known_snapshot: Dict[str, Any],
        prev_snapshot_id: Optional[int] = None
    ) -> int:
        """Store liquidation event detected from position disappearance.

        A position disappearing IS the liquidation event.

        Args:
            detected_ts: Detection timestamp in nanoseconds
            wallet: Wallet that was liquidated
            coin: Asset that was liquidated
            last_known_snapshot: Last known position data before disappearance
            prev_snapshot_id: Reference to last position snapshot row

        Returns:
            Row ID of inserted event
        """
        return self._db.log_hl_liquidation_event_raw(
            detected_ts=detected_ts,
            wallet_address=wallet,
            coin=coin,
            last_known_szi=str(last_known_snapshot.get('szi', '')),
            last_known_entry_px=str(last_known_snapshot.get('entryPx', '')),
            last_known_liquidation_px=str(last_known_snapshot.get('liquidationPx')) if last_known_snapshot.get('liquidationPx') else None,
            last_known_position_value=str(last_known_snapshot.get('positionValue')) if last_known_snapshot.get('positionValue') else None,
            last_known_unrealized_pnl=str(last_known_snapshot.get('unrealizedPnl')) if last_known_snapshot.get('unrealizedPnl') else None,
            prev_snapshot_id=prev_snapshot_id
        )

    # =========================================================================
    # OI/Funding/Mark Price Storage
    # =========================================================================

    def store_oi_snapshot(
        self,
        snapshot_ts: int,
        coin: str,
        raw_context: Dict[str, Any]
    ) -> int:
        """Store OI/funding snapshot from activeAssetCtx response.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            coin: Asset symbol
            raw_context: Raw activeAssetCtx dict from API

        Returns:
            Row ID of inserted snapshot
        """
        return self._db.log_hl_oi_snapshot_raw(
            snapshot_ts=snapshot_ts,
            coin=coin,
            open_interest=str(raw_context.get('openInterest', '')),
            funding_rate=str(raw_context.get('funding')) if raw_context.get('funding') else None,
            premium=str(raw_context.get('premium')) if raw_context.get('premium') else None,
            day_ntl_vlm=str(raw_context.get('dayNtlVlm')) if raw_context.get('dayNtlVlm') else None
        )

    def store_mark_price(
        self,
        snapshot_ts: int,
        coin: str,
        mark_px: str,
        oracle_px: Optional[str] = None
    ) -> int:
        """Store mark price snapshot.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            coin: Asset symbol
            mark_px: Mark price string from API
            oracle_px: Oracle price string (optional)

        Returns:
            Row ID of inserted snapshot
        """
        return self._db.log_hl_mark_price_raw(
            snapshot_ts=snapshot_ts,
            coin=coin,
            mark_px=mark_px,
            oracle_px=oracle_px
        )

    def store_funding_snapshot(
        self,
        snapshot_ts: int,
        coin: str,
        funding_rate: str,
        next_funding_ts: Optional[int] = None
    ) -> int:
        """Store funding rate snapshot.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            coin: Asset symbol
            funding_rate: Funding rate string
            next_funding_ts: Next funding timestamp

        Returns:
            Row ID of inserted snapshot
        """
        return self._db.log_hl_funding_snapshot(
            snapshot_ts=snapshot_ts,
            coin=coin,
            funding_rate=funding_rate,
            next_funding_ts=next_funding_ts
        )

    # =========================================================================
    # Wallet Discovery
    # =========================================================================

    def store_wallet_discovery(
        self,
        wallet: str,
        source_type: str,
        source_coin: Optional[str] = None,
        source_value: Optional[float] = None,
        source_metadata: Optional[str] = None
    ) -> int:
        """Record wallet discovery provenance.

        Args:
            wallet: Discovered wallet address
            source_type: How discovered ('trade', 'liquidation', 'manual', 'hyperdash')
            source_coin: Coin if discovered from trade
            source_value: Trade value that triggered discovery
            source_metadata: JSON string with additional context

        Returns:
            Row ID of inserted record
        """
        discovery_ts = int(time.time() * 1_000_000_000)
        return self._db.log_hl_wallet_discovery(
            wallet_address=wallet,
            discovery_ts=discovery_ts,
            source_type=source_type,
            source_coin=source_coin,
            source_value=source_value,
            source_metadata=source_metadata
        )

    # =========================================================================
    # Wallet Tier Management
    # =========================================================================

    def set_wallet_tier(self, wallet: str, tier: int, next_poll_ts: Optional[int] = None):
        """Set or update wallet polling tier.

        Args:
            wallet: Wallet address
            tier: Polling tier (1=5s, 2=30s, 3=300s)
            next_poll_ts: Next scheduled poll timestamp (nanoseconds)
        """
        self._db.set_hl_wallet_tier(wallet, tier, next_poll_ts)

    def get_wallets_due_for_poll(self, tier: int) -> List[str]:
        """Get wallets due for polling in a tier.

        Args:
            tier: Polling tier to check

        Returns:
            List of wallet addresses due for polling
        """
        current_ts = int(time.time() * 1_000_000_000)
        return self._db.get_hl_wallets_due_for_poll(tier, current_ts)

    def update_wallet_poll_stats(
        self,
        wallet: str,
        next_poll_ts: int,
        had_positions: bool
    ):
        """Update wallet polling stats after a poll.

        Args:
            wallet: Wallet that was polled
            next_poll_ts: Scheduled next poll timestamp
            had_positions: Whether wallet had any positions
        """
        last_poll_ts = int(time.time() * 1_000_000_000)
        self._db.update_hl_wallet_poll_stats(wallet, last_poll_ts, next_poll_ts, had_positions)

    # =========================================================================
    # Query Methods (for replay/analysis)
    # =========================================================================

    def get_position_history(
        self,
        wallet: str,
        coin: str,
        start_ts: int,
        end_ts: int
    ) -> List[Dict]:
        """Get position snapshot history for a wallet/coin.

        Args:
            wallet: Wallet address
            coin: Asset symbol
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)

        Returns:
            List of position snapshots in chronological order
        """
        return self._db.get_hl_position_history(wallet, coin, start_ts, end_ts)

    def get_liquidations_in_window(
        self,
        start_ts: int,
        end_ts: int,
        coin: Optional[str] = None
    ) -> List[Dict]:
        """Get liquidation events in a time window.

        Args:
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            coin: Optional filter by coin

        Returns:
            List of liquidation events
        """
        return self._db.get_hl_liquidations_in_window(start_ts, end_ts, coin)

    def get_oi_history(
        self,
        coin: str,
        start_ts: int,
        end_ts: int
    ) -> List[Dict]:
        """Get OI snapshot history for a coin.

        Args:
            coin: Asset symbol
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)

        Returns:
            List of OI snapshots in chronological order
        """
        return self._db.get_hl_oi_history(coin, start_ts, end_ts)


def now_ns() -> int:
    """Get current time in nanoseconds."""
    return int(time.time() * 1_000_000_000)
