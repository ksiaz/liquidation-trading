"""
Tiered Wallet Polling System

Polls wallets at different intervals based on position value:
- Tier 1 (>$10M): 5 second interval
- Tier 2 ($1M-$10M): 30 second interval
- Tier 3 ($100k-$1M): 5 minute interval
- Discovery: Trade-based discovery for new wallets

Constitutional compliance:
- No prediction or interpretation
- Only tracks observable facts (position values)
- Tier assignment is mechanical, not judgmental
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any

from runtime.hyperliquid.hl_data_store import HLDataStore, PollCycleStats, now_ns


logger = logging.getLogger(__name__)


@dataclass
class TierConfig:
    """Configuration for tiered polling."""

    # Value thresholds for tier assignment (USD)
    tier1_threshold: float = 10_000_000   # $10M+ → Tier 1
    tier2_threshold: float = 1_000_000    # $1M+ → Tier 2
    tier3_threshold: float = 100_000      # $100k+ → Tier 3

    # Polling intervals (seconds)
    tier1_interval: float = 5.0           # High-value: every 5s
    tier2_interval: float = 30.0          # Medium-value: every 30s
    tier3_interval: float = 300.0         # Low-value: every 5min

    # Discovery configuration
    discovery_interval: float = 300.0     # Trade scan every 5min
    discovery_min_value: float = 50_000   # Minimum trade value for discovery

    # Demotion rules
    empty_polls_before_demotion: int = 10  # Demote after 10 empty polls


@dataclass
class WalletState:
    """Internal tracking state for a wallet."""
    address: str
    tier: int
    last_poll_ts: int = 0
    next_poll_ts: int = 0
    last_total_value: float = 0.0
    consecutive_empty: int = 0
    last_snapshot_ids: Dict[str, int] = field(default_factory=dict)  # coin -> snapshot_id


class TieredPoller:
    """
    Tiered wallet polling with automatic tier promotion/demotion.

    Responsibilities:
    1. Assign wallets to tiers based on position value
    2. Schedule polls according to tier intervals
    3. Run trade-based discovery for new wallets
    4. Promote/demote wallets between tiers based on value changes

    Usage:
        poller = TieredPoller(client, data_store)

        # Add known wallets
        poller.add_wallet("0x...", tier=1)

        # Run polling loops (typically in separate tasks)
        await poller.run_tier1_poll()  # Call every 5s
        await poller.run_tier2_poll()  # Call every 30s
        await poller.run_tier3_poll()  # Call every 5min
        await poller.run_discovery()   # Call every 5min
    """

    def __init__(
        self,
        client,  # HyperliquidClient
        data_store: HLDataStore,
        config: Optional[TierConfig] = None,
        on_position_update: Optional[Callable[[str, str, Dict], None]] = None,
        on_liquidation_detected: Optional[Callable[[str, str, Dict], None]] = None
    ):
        """Initialize tiered poller.

        Args:
            client: HyperliquidClient instance for API calls
            data_store: HLDataStore for raw data storage
            config: Tier configuration (uses defaults if None)
            on_position_update: Callback for position updates (wallet, coin, position)
            on_liquidation_detected: Callback for liquidation detection (wallet, coin, last_known)
        """
        self._client = client
        self._store = data_store
        self._config = config or TierConfig()

        # Callbacks
        self._on_position_update = on_position_update
        self._on_liquidation_detected = on_liquidation_detected

        # Wallet tracking by tier
        self._wallets: Dict[str, WalletState] = {}
        self._tier1_wallets: Set[str] = set()
        self._tier2_wallets: Set[str] = set()
        self._tier3_wallets: Set[str] = set()

        # Discovery tracking
        self._discovered_wallets: Set[str] = set()

    # =========================================================================
    # Wallet Management
    # =========================================================================

    def add_wallet(self, wallet: str, tier: int = 3, source_type: str = 'manual'):
        """Add a wallet to tracking.

        Args:
            wallet: Wallet address
            tier: Initial tier (1, 2, or 3)
            source_type: How wallet was discovered
        """
        wallet = wallet.lower()
        if wallet in self._wallets:
            return

        state = WalletState(address=wallet, tier=tier)
        self._wallets[wallet] = state
        self._assign_to_tier_set(wallet, tier)

        # Record discovery provenance
        self._store.store_wallet_discovery(
            wallet=wallet,
            source_type=source_type
        )

        # Set tier in database
        self._store.set_wallet_tier(wallet, tier)

        logger.info(f"Added wallet {wallet[:10]}... to tier {tier}")

    def remove_wallet(self, wallet: str):
        """Remove a wallet from tracking.

        Args:
            wallet: Wallet address to remove
        """
        wallet = wallet.lower()
        if wallet not in self._wallets:
            return

        state = self._wallets[wallet]
        self._remove_from_tier_set(wallet, state.tier)
        del self._wallets[wallet]

        logger.info(f"Removed wallet {wallet[:10]}...")

    def _assign_to_tier_set(self, wallet: str, tier: int):
        """Add wallet to appropriate tier set."""
        if tier == 1:
            self._tier1_wallets.add(wallet)
        elif tier == 2:
            self._tier2_wallets.add(wallet)
        else:
            self._tier3_wallets.add(wallet)

    def _remove_from_tier_set(self, wallet: str, tier: int):
        """Remove wallet from tier set."""
        if tier == 1:
            self._tier1_wallets.discard(wallet)
        elif tier == 2:
            self._tier2_wallets.discard(wallet)
        else:
            self._tier3_wallets.discard(wallet)

    # =========================================================================
    # Tier Assignment
    # =========================================================================

    def assign_tier_by_value(self, total_value: float) -> int:
        """Determine tier based on total position value.

        Args:
            total_value: Total USD value of all positions

        Returns:
            Tier number (1, 2, or 3)
        """
        if total_value >= self._config.tier1_threshold:
            return 1
        elif total_value >= self._config.tier2_threshold:
            return 2
        elif total_value >= self._config.tier3_threshold:
            return 3
        else:
            return 3  # Minimum tier

    def promote_wallet(self, wallet: str, new_tier: int):
        """Promote wallet to a higher tier (lower number).

        Args:
            wallet: Wallet address
            new_tier: New tier (must be < current tier)
        """
        wallet = wallet.lower()
        if wallet not in self._wallets:
            return

        state = self._wallets[wallet]
        old_tier = state.tier

        if new_tier >= old_tier:
            return  # Not a promotion

        self._remove_from_tier_set(wallet, old_tier)
        state.tier = new_tier
        self._assign_to_tier_set(wallet, new_tier)
        self._store.set_wallet_tier(wallet, new_tier)

        logger.info(f"Promoted wallet {wallet[:10]}... from tier {old_tier} to {new_tier}")

    def demote_wallet(self, wallet: str, new_tier: int):
        """Demote wallet to a lower tier (higher number).

        Args:
            wallet: Wallet address
            new_tier: New tier (must be > current tier)
        """
        wallet = wallet.lower()
        if wallet not in self._wallets:
            return

        state = self._wallets[wallet]
        old_tier = state.tier

        if new_tier <= old_tier:
            return  # Not a demotion

        self._remove_from_tier_set(wallet, old_tier)
        state.tier = new_tier
        self._assign_to_tier_set(wallet, new_tier)
        self._store.set_wallet_tier(wallet, new_tier)

        logger.info(f"Demoted wallet {wallet[:10]}... from tier {old_tier} to {new_tier}")

    # =========================================================================
    # Polling Methods
    # =========================================================================

    async def run_tier1_poll(self) -> PollCycleStats:
        """Poll Tier 1 wallets (high-value, 5s interval).

        Returns:
            Statistics from the poll cycle
        """
        return await self._run_tier_poll(1, self._tier1_wallets)

    async def run_tier2_poll(self) -> PollCycleStats:
        """Poll Tier 2 wallets (medium-value, 30s interval).

        Returns:
            Statistics from the poll cycle
        """
        return await self._run_tier_poll(2, self._tier2_wallets)

    async def run_tier3_poll(self) -> PollCycleStats:
        """Poll Tier 3 wallets (low-value, 5min interval).

        Returns:
            Statistics from the poll cycle
        """
        return await self._run_tier_poll(3, self._tier3_wallets)

    async def _run_tier_poll(self, tier: int, wallets: Set[str]) -> PollCycleStats:
        """Execute a poll cycle for a specific tier.

        Args:
            tier: Tier number
            wallets: Set of wallet addresses to poll

        Returns:
            Statistics from the poll cycle
        """
        if not wallets:
            return PollCycleStats()

        start_time = time.time()
        cycle_id = self._store.start_poll_cycle(f"tier{tier}")

        stats = PollCycleStats()
        wallets_to_poll = list(wallets)  # Copy to avoid modification during iteration

        for wallet in wallets_to_poll:
            try:
                await self._poll_wallet(wallet, cycle_id, stats)
                stats.wallets_polled += 1
            except Exception as e:
                logger.warning(f"Error polling wallet {wallet[:10]}...: {e}")
                stats.api_errors += 1

        stats.duration_ms = int((time.time() - start_time) * 1000)
        self._store.end_poll_cycle(cycle_id, stats)

        logger.debug(f"Tier {tier} poll: {stats.wallets_polled} wallets, "
                    f"{stats.positions_found} positions, {stats.duration_ms}ms")

        return stats

    async def _poll_wallet(self, wallet: str, cycle_id: int, stats: PollCycleStats):
        """Poll a single wallet and store results.

        Args:
            wallet: Wallet address
            cycle_id: Current poll cycle ID
            stats: Stats object to update
        """
        snapshot_ts = now_ns()
        state = self._wallets.get(wallet)
        if not state:
            return

        # Fetch clearinghouse state from API
        wallet_state = await self._client.get_clearinghouse_state(wallet)

        if wallet_state is None:
            state.consecutive_empty += 1
            self._check_demotion(wallet, state)
            return

        # Store wallet summary
        if hasattr(wallet_state, 'cross_margin_summary') and wallet_state.cross_margin_summary:
            self._store.store_wallet_snapshot(
                snapshot_ts=snapshot_ts,
                poll_cycle_id=cycle_id,
                wallet=wallet,
                raw_summary=wallet_state.cross_margin_summary
            )

        # Process positions
        positions = wallet_state.positions if hasattr(wallet_state, 'positions') else []
        current_coins = set()
        total_value = 0.0

        for pos in positions:
            coin = pos.get('coin', pos.get('symbol', 'UNKNOWN'))
            current_coins.add(coin)

            # Store raw position snapshot
            snapshot_id = self._store.store_position_snapshot(
                snapshot_ts=snapshot_ts,
                poll_cycle_id=cycle_id,
                wallet=wallet,
                coin=coin,
                raw_position=pos
            )

            # Track for liquidation detection
            state.last_snapshot_ids[coin] = snapshot_id
            stats.positions_found += 1

            # Calculate value for tier adjustment
            pos_value = abs(float(pos.get('positionValue', 0)))
            total_value += pos_value

            # Callback
            if self._on_position_update:
                self._on_position_update(wallet, coin, pos)

        # Detect liquidations (position disappeared)
        previous_coins = set(state.last_snapshot_ids.keys())
        liquidated_coins = previous_coins - current_coins

        for coin in liquidated_coins:
            prev_snapshot_id = state.last_snapshot_ids.pop(coin, None)
            stats.liquidations_detected += 1

            # We don't have last_known here, would need to query or cache
            # For now, store minimal event
            self._store._db.log_hl_liquidation_event_raw(
                detected_ts=snapshot_ts,
                wallet_address=wallet,
                coin=coin,
                last_known_szi="unknown",  # Would need cache
                last_known_entry_px="unknown",
                prev_snapshot_id=prev_snapshot_id,
                detection_method='position_disappearance'
            )

            if self._on_liquidation_detected:
                self._on_liquidation_detected(wallet, coin, {})

            logger.info(f"Liquidation detected: {wallet[:10]}... {coin}")

        # Update state
        state.last_total_value = total_value
        state.consecutive_empty = 0 if positions else state.consecutive_empty + 1

        # Check for tier changes
        self._check_tier_change(wallet, state, total_value)
        self._check_demotion(wallet, state)

        # Schedule next poll
        interval = self._get_interval_for_tier(state.tier)
        next_poll_ts = snapshot_ts + int(interval * 1_000_000_000)
        self._store.update_wallet_poll_stats(wallet, next_poll_ts, len(positions) > 0)

    def _check_tier_change(self, wallet: str, state: WalletState, total_value: float):
        """Check if wallet should change tiers based on value.

        Args:
            wallet: Wallet address
            state: Current wallet state
            total_value: Current total position value
        """
        new_tier = self.assign_tier_by_value(total_value)

        if new_tier < state.tier:
            self.promote_wallet(wallet, new_tier)
        elif new_tier > state.tier and state.consecutive_empty == 0:
            # Only demote if value actually decreased, not just empty
            self.demote_wallet(wallet, new_tier)

    def _check_demotion(self, wallet: str, state: WalletState):
        """Check if wallet should be demoted due to inactivity.

        Args:
            wallet: Wallet address
            state: Current wallet state
        """
        if state.consecutive_empty >= self._config.empty_polls_before_demotion:
            if state.tier < 3:
                self.demote_wallet(wallet, state.tier + 1)
                state.consecutive_empty = 0  # Reset after demotion

    def _get_interval_for_tier(self, tier: int) -> float:
        """Get polling interval for a tier.

        Args:
            tier: Tier number

        Returns:
            Interval in seconds
        """
        if tier == 1:
            return self._config.tier1_interval
        elif tier == 2:
            return self._config.tier2_interval
        else:
            return self._config.tier3_interval

    # =========================================================================
    # Discovery
    # =========================================================================

    async def run_discovery(self) -> int:
        """Discover new wallets from recent trades.

        Returns:
            Number of new wallets discovered
        """
        discovered = 0

        try:
            # Get recent large trades
            for coin in await self._get_discovery_coins():
                trades = await self._client.get_recent_trades(coin)

                for trade in trades:
                    value = abs(float(trade.get('sz', 0)) * float(trade.get('px', 0)))

                    if value >= self._config.discovery_min_value:
                        wallet = trade.get('user', trade.get('wallet', ''))
                        if wallet and wallet.lower() not in self._wallets:
                            self.add_wallet(
                                wallet,
                                tier=3,
                                source_type='trade'
                            )
                            self._store.store_wallet_discovery(
                                wallet=wallet,
                                source_type='trade',
                                source_coin=coin,
                                source_value=value
                            )
                            discovered += 1

        except Exception as e:
            logger.warning(f"Discovery error: {e}")

        if discovered > 0:
            logger.info(f"Discovered {discovered} new wallets from trades")

        return discovered

    async def _get_discovery_coins(self) -> List[str]:
        """Get list of coins to scan for discovery.

        Returns:
            List of coin symbols
        """
        # Default to major coins
        return ['BTC', 'ETH', 'SOL']

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current poller status.

        Returns:
            Status dictionary with tier counts and wallet info
        """
        return {
            'total_wallets': len(self._wallets),
            'tier1_count': len(self._tier1_wallets),
            'tier2_count': len(self._tier2_wallets),
            'tier3_count': len(self._tier3_wallets),
            'tier1_wallets': list(self._tier1_wallets)[:5],  # Sample
            'config': {
                'tier1_interval': self._config.tier1_interval,
                'tier2_interval': self._config.tier2_interval,
                'tier3_interval': self._config.tier3_interval,
            }
        }
