"""
Batch Position Poller

Efficiently polls thousands of wallets for positions with tiered priority.

Polling tiers:
- Tier 1 (>$1M positions): Poll every 5 seconds
- Tier 2 (>$100k positions): Poll every 30 seconds
- Tier 3 (all others): Poll every 5 minutes

Rate limiting: Stays under 1000 requests/minute to avoid API throttling.

Constitutional compliance:
- Only polls for factual position data
- No interpretation or scoring
- Pure data retrieval
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set
from collections import defaultdict
import heapq

from ..client import HyperliquidClient
from ..types import WalletState
from .indexed_wallets import IndexedWalletStore


@dataclass
class PollerConfig:
    """Configuration for batch position poller."""
    # Rate limiting
    max_requests_per_minute: int = 1000  # Stay under API limit
    request_delay: float = 0.06  # ~1000/min (60/1000 = 0.06)

    # Tier thresholds (USD position value)
    tier1_threshold: float = 1_000_000  # $1M
    tier2_threshold: float = 100_000    # $100k

    # Polling intervals (seconds)
    tier0_interval: float = 3.0    # DANGER ZONE: every 3s (proximity-based)
    tier1_interval: float = 5.0    # High-value: every 5s
    tier2_interval: float = 30.0   # Medium-value: every 30s
    tier3_interval: float = 300.0  # Low-value: every 5 min

    # Proximity thresholds (% distance to liquidation)
    # Positions closer than these get upgraded to faster polling
    proximity_tier0: float = 5.0   # <5% from liq -> poll every 3s
    proximity_tier1: float = 10.0  # <10% from liq -> poll every 5s

    # Batch settings
    batch_size: int = 50  # Wallets per batch

    # Discovery polling
    discovery_interval: float = 600.0  # Check new wallets every 10 min


@dataclass(order=True)
class PollTask:
    """A scheduled poll task."""
    next_poll_time: float
    address: str = field(compare=False)
    tier: int = field(compare=False)
    last_position_value: float = field(default=0, compare=False)


class BatchPositionPoller:
    """
    Efficient position poller with tiered scheduling.

    Polls wallets based on their position value:
    - Large positions polled more frequently
    - Small/inactive positions polled less often
    - New wallets discovered and classified

    Usage:
        poller = BatchPositionPoller(client, store, config)
        await poller.start()

        # Poller runs continuously, updating positions
        # Access results via store or callbacks

        await poller.stop()
    """

    def __init__(
        self,
        client: HyperliquidClient,
        store: IndexedWalletStore,
        config: Optional[PollerConfig] = None
    ):
        self.config = config or PollerConfig()
        self._client = client
        self._store = store
        self._logger = logging.getLogger("BatchPositionPoller")

        # Scheduling
        self._poll_queue: List[PollTask] = []  # Min-heap by next_poll_time
        self._scheduled_addresses: Set[str] = set()

        # Stats
        self._total_polls = 0
        self._successful_polls = 0
        self._positions_found = 0
        self._last_poll_time: Dict[str, float] = {}

        # State
        self._running = False

        # Callbacks
        self._on_position_update: Optional[Callable] = None
        self._on_large_position: Optional[Callable] = None

    async def start(self):
        """Start the poller."""
        self._running = True

        # Initialize queue from store
        await self._initialize_queue()

        # Start polling tasks
        asyncio.create_task(self._poll_loop())
        asyncio.create_task(self._discovery_loop())

        self._logger.info(
            f"Batch poller started with {len(self._poll_queue)} wallets scheduled"
        )

    async def stop(self):
        """Stop the poller."""
        self._running = False
        self._logger.info("Batch poller stopped")

    # =========================================================================
    # Queue Management
    # =========================================================================

    async def _initialize_queue(self):
        """Initialize poll queue from store."""
        self._poll_queue.clear()
        self._scheduled_addresses.clear()

        now = time.time()

        # Get all wallets from store
        all_addresses = self._store.get_all_addresses()
        self._logger.info(f"Initializing queue with {len(all_addresses)} addresses")

        for address in all_addresses:
            wallet = self._store.get_wallet(address)
            if wallet:
                tier = self._classify_tier(wallet.position_value)
                interval = self._get_interval(tier)

                # Stagger initial polls to avoid burst
                stagger = len(self._poll_queue) * 0.01  # 10ms per wallet
                next_poll = now + stagger

                task = PollTask(
                    next_poll_time=next_poll,
                    address=address,
                    tier=tier,
                    last_position_value=wallet.position_value
                )
                heapq.heappush(self._poll_queue, task)
                self._scheduled_addresses.add(address)

    def add_wallet(self, address: str, tier: int = 3):
        """Add a wallet to the poll queue."""
        addr = address.lower()
        if addr in self._scheduled_addresses:
            return

        interval = self._get_interval(tier)
        task = PollTask(
            next_poll_time=time.time() + interval,
            address=addr,
            tier=tier
        )
        heapq.heappush(self._poll_queue, task)
        self._scheduled_addresses.add(addr)

    def remove_wallet(self, address: str):
        """Remove a wallet from the poll queue."""
        addr = address.lower()
        self._scheduled_addresses.discard(addr)
        # Note: Item stays in heap but will be skipped

    def _classify_tier(self, position_value: float, min_liq_distance: float = 100.0) -> int:
        """
        Classify wallet into polling tier based on position value AND liquidation proximity.

        Proximity overrides value-based tier:
        - Tier 0: <5% from liquidation (DANGER ZONE)
        - Tier 1: <10% from liq OR >$1M position
        - Tier 2: >$100k position
        - Tier 3: Everything else
        """
        # PRIORITY: Proximity-based classification (danger zone)
        if min_liq_distance <= self.config.proximity_tier0:
            return 0  # DANGER ZONE - poll very fast
        elif min_liq_distance <= self.config.proximity_tier1:
            return 1  # Approaching danger - poll fast

        # Fallback: Value-based classification
        if position_value >= self.config.tier1_threshold:
            return 1
        elif position_value >= self.config.tier2_threshold:
            return 2
        else:
            return 3

    def _get_interval(self, tier: int) -> float:
        """Get polling interval for tier."""
        if tier == 0:
            return self.config.tier0_interval  # DANGER ZONE
        elif tier == 1:
            return self.config.tier1_interval
        elif tier == 2:
            return self.config.tier2_interval
        else:
            return self.config.tier3_interval

    def _get_min_liq_distance(self, wallet_address: str) -> float:
        """Get minimum liquidation distance for any position in this wallet."""
        try:
            # Query the store for this wallet's positions
            positions = self._store.get_wallet_positions(wallet_address)
            if not positions:
                return 100.0  # No positions, assume safe

            min_dist = 100.0
            for pos in positions:
                dist = pos.get('distance_to_liq_pct', 100.0)
                if dist is not None and 0 < dist < min_dist:
                    min_dist = dist
            return min_dist
        except Exception:
            return 100.0  # On error, assume safe

    # =========================================================================
    # Polling Loop
    # =========================================================================

    async def _poll_loop(self):
        """Main polling loop with rate limiting."""
        self._logger.info("Poll loop started")

        while self._running:
            try:
                if not self._poll_queue:
                    await asyncio.sleep(1.0)
                    continue

                # Get next task due
                now = time.time()
                task = self._poll_queue[0]

                if task.next_poll_time > now:
                    # Wait until next task is due
                    wait_time = min(task.next_poll_time - now, 1.0)
                    await asyncio.sleep(wait_time)
                    continue

                # Pop task
                task = heapq.heappop(self._poll_queue)

                # Skip if wallet was removed
                if task.address not in self._scheduled_addresses:
                    continue

                # Poll wallet
                await self._poll_wallet(task)

                # Rate limiting delay
                await asyncio.sleep(self.config.request_delay)

            except Exception as e:
                self._logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(1.0)

    async def _poll_wallet(self, task: PollTask):
        """Poll a single wallet and reschedule."""
        try:
            self._total_polls += 1
            state = await self._client.get_clearinghouse_state(task.address)

            if state:
                self._successful_polls += 1

                # Calculate total position value
                total_value = sum(
                    pos.position_value for pos in state.positions.values()
                )

                # Update store
                self._store.update_position(task.address, total_value)

                # Save individual positions with liquidation data
                await self._save_individual_positions(state)

                # Get minimum liquidation distance for proximity-based tier
                min_liq_dist = self._get_min_liq_distance(task.address)

                # Check for tier change (now includes proximity)
                new_tier = self._classify_tier(total_value, min_liq_dist)
                if new_tier != task.tier:
                    tier_names = {0: 'DANGER', 1: 'HIGH', 2: 'MEDIUM', 3: 'LOW'}
                    self._logger.info(
                        f"Wallet {task.address[:10]}... tier change: "
                        f"{tier_names.get(task.tier, task.tier)} -> {tier_names.get(new_tier, new_tier)} "
                        f"(${total_value:,.0f}, {min_liq_dist:.1f}% from liq)"
                    )

                # Track positions
                if total_value > 0:
                    self._positions_found += 1

                    # Callback for large positions
                    if self._on_large_position and total_value >= self.config.tier1_threshold:
                        await self._on_large_position(state)

                # Callback for any update
                if self._on_position_update:
                    await self._on_position_update(state)

                # Reschedule with new tier
                interval = self._get_interval(new_tier)
                new_task = PollTask(
                    next_poll_time=time.time() + interval,
                    address=task.address,
                    tier=new_tier,
                    last_position_value=total_value
                )
                heapq.heappush(self._poll_queue, new_task)

            else:
                # Poll failed - reschedule with backoff
                backoff = min(task.tier * 60, 300)  # Up to 5 min backoff
                new_task = PollTask(
                    next_poll_time=time.time() + backoff,
                    address=task.address,
                    tier=task.tier,
                    last_position_value=task.last_position_value
                )
                heapq.heappush(self._poll_queue, new_task)

            self._last_poll_time[task.address] = time.time()

        except Exception as e:
            self._logger.debug(f"Failed to poll {task.address[:10]}...: {e}")
            # Reschedule with backoff
            backoff = 60.0
            new_task = PollTask(
                next_poll_time=time.time() + backoff,
                address=task.address,
                tier=task.tier,
                last_position_value=task.last_position_value
            )
            heapq.heappush(self._poll_queue, new_task)

    async def _save_individual_positions(self, state: WalletState):
        """Save individual positions with liquidation data and impact scores."""
        # Get current prices and volumes
        mid_prices = await self._client.get_all_mids()
        volumes = await self._client.get_asset_volumes()

        for coin, pos in state.positions.items():
            if pos.abs_size <= 0:
                # Position closed, remove from store
                self._store.remove_position(state.address, coin)
                continue

            # Get current price for distance calculation
            current_price = mid_prices.get(coin, 0)

            # Get 24h volume for impact calculation
            daily_volume = volumes.get(coin, 0)

            # Determine side from signed size
            side = "LONG" if pos.position_size > 0 else "SHORT"

            # If API returns no liq price, position is well-collateralized - skip it
            liq_price = pos.liquidation_price
            if liq_price is None or liq_price <= 0:
                continue

            self._store.save_position(
                wallet_address=state.address,
                coin=coin,
                side=side,
                entry_price=pos.entry_price,
                position_size=pos.abs_size,
                position_value=pos.position_value,
                leverage=pos.leverage,
                liquidation_price=liq_price,
                margin_used=pos.margin_used,
                unrealized_pnl=pos.unrealized_pnl,
                current_price=current_price,
                daily_volume=daily_volume
            )

    # =========================================================================
    # Discovery Loop
    # =========================================================================

    async def _discovery_loop(self):
        """
        Periodically check for new wallets that aren't in the queue.

        Handles wallets added to store after poller started.
        """
        while self._running:
            try:
                await asyncio.sleep(self.config.discovery_interval)

                # Get addresses from store not in queue
                all_addresses = set(self._store.get_all_addresses())
                new_addresses = all_addresses - self._scheduled_addresses

                if new_addresses:
                    self._logger.info(f"Discovered {len(new_addresses)} new wallets")
                    for addr in new_addresses:
                        self.add_wallet(addr)

            except Exception as e:
                self._logger.error(f"Discovery loop error: {e}")

    # =========================================================================
    # Batch Polling (for bulk operations)
    # =========================================================================

    async def poll_batch(self, addresses: List[str]) -> Dict[str, WalletState]:
        """
        Poll a batch of addresses.

        Used for initial discovery or bulk refresh.

        Returns dict of address -> WalletState
        """
        results = {}

        for i, addr in enumerate(addresses):
            try:
                state = await self._client.get_clearinghouse_state(addr)
                if state:
                    results[addr] = state

                    # Update store
                    total_value = sum(
                        pos.position_value for pos in state.positions.values()
                    )
                    self._store.update_position(addr, total_value)

                # Rate limiting
                await asyncio.sleep(self.config.request_delay)

                # Progress logging
                if (i + 1) % 100 == 0:
                    self._logger.info(f"Batch progress: {i + 1}/{len(addresses)}")

            except Exception as e:
                self._logger.debug(f"Batch poll error for {addr[:10]}...: {e}")

        return results

    async def poll_all_tier1(self) -> Dict[str, WalletState]:
        """Poll all Tier 1 wallets immediately."""
        tier1_addresses = self._store.get_tier1_addresses()
        return await self.poll_batch(tier1_addresses)

    # =========================================================================
    # Callbacks
    # =========================================================================

    def set_position_callback(self, callback: Callable):
        """Set callback for position updates."""
        self._on_position_update = callback

    def set_large_position_callback(self, callback: Callable):
        """Set callback for large position updates (>$1M)."""
        self._on_large_position = callback

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> Dict:
        """Get poller statistics."""
        tier_counts = defaultdict(int)
        for task in self._poll_queue:
            if task.address in self._scheduled_addresses:
                tier_counts[task.tier] += 1

        return {
            "running": self._running,
            "queued_wallets": len(self._scheduled_addresses),
            "total_polls": self._total_polls,
            "successful_polls": self._successful_polls,
            "positions_found": self._positions_found,
            "success_rate": (
                self._successful_polls / self._total_polls * 100
                if self._total_polls > 0 else 0
            ),
            "tier_counts": dict(tier_counts)
        }

    def get_queue_status(self) -> Dict:
        """Get detailed queue status."""
        now = time.time()

        # Count tasks by status
        overdue = 0
        due_soon = 0  # Within 10 seconds
        scheduled = 0

        for task in self._poll_queue:
            if task.address not in self._scheduled_addresses:
                continue
            if task.next_poll_time <= now:
                overdue += 1
            elif task.next_poll_time <= now + 10:
                due_soon += 1
            else:
                scheduled += 1

        return {
            "overdue": overdue,
            "due_soon": due_soon,
            "scheduled": scheduled,
            "total": len(self._scheduled_addresses)
        }
