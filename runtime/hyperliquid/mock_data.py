"""
Mock Data Generator for Hyperliquid

Generates realistic test data for offline development.
All generated data follows the same schema as real API responses.

Use cases:
- Unit testing without API access
- Development without static IP/node
- Replay from stored snapshots
"""

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

from runtime.hyperliquid.hl_data_store import HLDataStore


@dataclass
class MockConfig:
    """Configuration for mock data generation."""

    # Wallet configuration
    num_wallets: int = 50
    wallet_prefix: str = "0xmock"

    # Coins to simulate
    coins: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])

    # Position parameters
    position_value_range: tuple = (10_000, 10_000_000)  # USD
    leverage_range: tuple = (1.0, 50.0)
    position_probability: float = 0.7  # Probability wallet has position in a coin

    # Price parameters
    btc_price: float = 95000.0
    eth_price: float = 3500.0
    sol_price: float = 200.0

    # Liquidation proximity
    liquidation_distance_range: tuple = (0.01, 0.20)  # 1% to 20%

    # Trade discovery
    trades_per_coin: int = 20
    large_trade_probability: float = 0.1


class MockHyperliquidClient:
    """
    Mock client that generates realistic position data.

    Simulates Hyperliquid API responses for offline testing.
    Generated data follows exact API response schema.

    Usage:
        client = MockHyperliquidClient()
        state = await client.get_clearinghouse_state("0x...")
        mids = await client.get_all_mids()
    """

    def __init__(self, config: Optional[MockConfig] = None, seed: int = None):
        """Initialize mock client.

        Args:
            config: Mock data configuration
            seed: Random seed for reproducibility
        """
        self._config = config or MockConfig()
        if seed is not None:
            random.seed(seed)

        # Price lookup - must be initialized BEFORE generating positions
        self._prices = {
            'BTC': self._config.btc_price,
            'ETH': self._config.eth_price,
            'SOL': self._config.sol_price,
        }

        # Generate stable wallet addresses
        self._wallets = [
            f"{self._config.wallet_prefix}{i:040d}"
            for i in range(self._config.num_wallets)
        ]

        # Generate stable position data per wallet
        self._wallet_positions = self._generate_initial_positions()

    def _generate_initial_positions(self) -> Dict[str, Dict[str, Dict]]:
        """Generate initial position state for all wallets.

        Returns:
            Dict of wallet -> coin -> position data
        """
        positions = {}

        for wallet in self._wallets:
            positions[wallet] = {}

            for coin in self._config.coins:
                if random.random() < self._config.position_probability:
                    positions[wallet][coin] = self._generate_position(coin)

        return positions

    def _generate_position(self, coin: str) -> Dict[str, Any]:
        """Generate a single position with realistic data.

        Args:
            coin: Asset symbol

        Returns:
            Position dict matching Hyperliquid API schema
        """
        # Random side
        is_long = random.random() > 0.5
        side_multiplier = 1 if is_long else -1

        # Position value and size
        value = random.uniform(*self._config.position_value_range)
        price = self._prices.get(coin, 1000.0)
        size = value / price

        # Leverage
        leverage = random.uniform(*self._config.leverage_range)

        # Entry price (slightly different from current)
        price_diff = random.uniform(-0.05, 0.05)  # ±5%
        entry_price = price * (1 + price_diff)

        # Liquidation price
        liq_distance = random.uniform(*self._config.liquidation_distance_range)
        if is_long:
            liquidation_price = entry_price * (1 - liq_distance)
        else:
            liquidation_price = entry_price * (1 + liq_distance)

        # PnL
        unrealized_pnl = (price - entry_price) * size * side_multiplier

        # Margin
        margin_used = value / leverage

        return {
            'coin': coin,
            'szi': str(size * side_multiplier),
            'entryPx': str(entry_price),
            'liquidationPx': str(liquidation_price),
            'positionValue': str(value),
            'unrealizedPnl': str(unrealized_pnl),
            'marginUsed': str(margin_used),
            'leverage': {
                'type': 'cross',
                'value': leverage
            },
            'returnOnEquity': str(unrealized_pnl / margin_used if margin_used else 0),
            'maxTradeSzs': [str(size * 2), str(size * 2)]
        }

    async def get_clearinghouse_state(self, wallet: str) -> Optional['MockWalletState']:
        """Return mock position data for wallet.

        Args:
            wallet: Wallet address

        Returns:
            MockWalletState or None if wallet not tracked
        """
        wallet = wallet.lower()

        if wallet not in self._wallet_positions:
            return None

        positions = list(self._wallet_positions[wallet].values())

        # Calculate account totals
        total_value = sum(float(p.get('positionValue', 0)) for p in positions)
        total_margin = sum(float(p.get('marginUsed', 0)) for p in positions)
        total_pnl = sum(float(p.get('unrealizedPnl', 0)) for p in positions)

        return MockWalletState(
            positions=positions,
            cross_margin_summary={
                'accountValue': str(total_value + total_pnl),
                'totalMarginUsed': str(total_margin),
                'withdrawable': str(max(0, total_value - total_margin))
            }
        )

    async def get_all_mids(self) -> Dict[str, float]:
        """Return mock mid prices.

        Returns:
            Dict of coin -> mid price
        """
        return self._prices.copy()

    async def get_recent_trades(self, coin: str) -> List[Dict]:
        """Return mock trades with wallet addresses for discovery.

        Args:
            coin: Asset symbol

        Returns:
            List of trade dicts
        """
        trades = []
        price = self._prices.get(coin, 1000.0)

        for _ in range(self._config.trades_per_coin):
            # Determine if large trade
            is_large = random.random() < self._config.large_trade_probability

            if is_large:
                size = random.uniform(10, 100)
                wallet = random.choice(self._wallets)
            else:
                size = random.uniform(0.01, 1.0)
                wallet = f"0xrandom{random.randint(0, 999999):06d}"

            trades.append({
                'coin': coin,
                'px': str(price * random.uniform(0.999, 1.001)),
                'sz': str(size),
                'side': random.choice(['B', 'S']),
                'user': wallet,
                'time': int(time.time() * 1000)
            })

        return trades

    def simulate_liquidation(self, wallet: str, coin: str):
        """Simulate a liquidation by removing a position.

        Args:
            wallet: Wallet address
            coin: Asset to liquidate
        """
        wallet = wallet.lower()
        if wallet in self._wallet_positions:
            self._wallet_positions[wallet].pop(coin, None)

    def simulate_new_position(self, wallet: str, coin: str):
        """Simulate opening a new position.

        Args:
            wallet: Wallet address
            coin: Asset symbol
        """
        wallet = wallet.lower()
        if wallet not in self._wallet_positions:
            self._wallet_positions[wallet] = {}

        self._wallet_positions[wallet][coin] = self._generate_position(coin)

    def get_tracked_wallets(self) -> List[str]:
        """Get list of all mock wallets.

        Returns:
            List of wallet addresses
        """
        return self._wallets.copy()


@dataclass
class MockWalletState:
    """Mock wallet state matching HyperliquidClient response."""
    positions: List[Dict[str, Any]]
    cross_margin_summary: Dict[str, str]


class SnapshotReplayer:
    """
    Replays stored snapshots for testing.

    Reads from hl_position_snapshots and replays in chronological order.
    Useful for testing processing logic without live data.

    Usage:
        replayer = SnapshotReplayer(data_store, start_ts, end_ts)

        async def process_snapshot(wallet, coin, position):
            print(f"Replaying: {wallet} {coin}")

        await replayer.replay(process_snapshot)
    """

    def __init__(
        self,
        data_store: HLDataStore,
        start_ts: int,
        end_ts: int,
        coins: Optional[List[str]] = None
    ):
        """Initialize replayer.

        Args:
            data_store: HLDataStore with historical data
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            coins: Optional filter for specific coins
        """
        self._store = data_store
        self._start_ts = start_ts
        self._end_ts = end_ts
        self._coins = coins

    async def replay(
        self,
        callback: Callable[[str, str, Dict], None],
        speed_multiplier: float = 1.0
    ):
        """Replay snapshots in chronological order.

        Args:
            callback: Function to call for each snapshot (wallet, coin, position)
            speed_multiplier: 1.0 = real-time, 2.0 = 2x speed, 0 = instant
        """
        # Query all snapshots in window
        # Note: This is a simplified implementation
        # In production, would need to query in batches

        # Get unique wallets that have data
        all_wallets = set()

        # For each wallet/coin, get history and replay
        # This is a simplified mock - real implementation would:
        # 1. Query snapshots ordered by timestamp
        # 2. Group by timestamp
        # 3. Replay in order with timing

        # Placeholder for actual replay logic
        pass

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of data available for replay.

        Returns:
            Summary dict with counts and time range
        """
        return {
            'start_ts': self._start_ts,
            'end_ts': self._end_ts,
            'duration_seconds': (self._end_ts - self._start_ts) / 1_000_000_000,
            'coins_filter': self._coins
        }


class MockDataGenerator:
    """
    Generates test data and stores it in the data store.

    Use to populate database with mock data for testing queries
    and analysis without live API access.
    """

    def __init__(
        self,
        data_store: HLDataStore,
        config: Optional[MockConfig] = None
    ):
        """Initialize generator.

        Args:
            data_store: HLDataStore to populate
            config: Mock data configuration
        """
        self._store = data_store
        self._config = config or MockConfig()
        self._client = MockHyperliquidClient(config)

    async def generate_history(
        self,
        duration_hours: float = 24,
        interval_seconds: float = 5.0
    ) -> int:
        """Generate historical data and store it.

        Args:
            duration_hours: How much history to generate
            interval_seconds: Snapshot interval

        Returns:
            Number of snapshots generated
        """
        import time

        end_ts = int(time.time() * 1_000_000_000)
        start_ts = end_ts - int(duration_hours * 3600 * 1_000_000_000)
        interval_ns = int(interval_seconds * 1_000_000_000)

        current_ts = start_ts
        snapshot_count = 0

        while current_ts < end_ts:
            # Start poll cycle
            cycle_id = self._store.start_poll_cycle('mock')

            # Poll each wallet
            for wallet in self._client.get_tracked_wallets()[:10]:  # Limit for speed
                state = await self._client.get_clearinghouse_state(wallet)

                if state and state.positions:
                    # Store wallet snapshot
                    self._store.store_wallet_snapshot(
                        snapshot_ts=current_ts,
                        poll_cycle_id=cycle_id,
                        wallet=wallet,
                        raw_summary=state.cross_margin_summary
                    )

                    # Store each position
                    for pos in state.positions:
                        coin = pos.get('coin', 'UNKNOWN')
                        self._store.store_position_snapshot(
                            snapshot_ts=current_ts,
                            poll_cycle_id=cycle_id,
                            wallet=wallet,
                            coin=coin,
                            raw_position=pos
                        )
                        snapshot_count += 1

            # End cycle
            from runtime.hyperliquid.hl_data_store import PollCycleStats
            self._store.end_poll_cycle(cycle_id, PollCycleStats(
                wallets_polled=10,
                positions_found=snapshot_count,
                duration_ms=int(interval_seconds * 1000)
            ))

            # Occasionally simulate liquidation
            if random.random() < 0.01:  # 1% chance per interval
                wallet = random.choice(self._client.get_tracked_wallets())
                coin = random.choice(self._config.coins)
                self._client.simulate_liquidation(wallet, coin)

            current_ts += interval_ns

        return snapshot_count
