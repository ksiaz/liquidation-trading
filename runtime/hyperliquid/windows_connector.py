"""
Windows Node Connector

TCP client that connects to the WSL-based node adapter and feeds
events to the observation system.

Handles:
- TCP connection to adapter
- Automatic reconnection with backoff
- Event parsing and routing to M1
- Order activity tracking for position refresh
"""

import asyncio
import json
import time
from typing import Callable, Awaitable, Dict, List, Optional, Set
from dataclasses import dataclass, field

from .node_adapter.config import WindowsConnectorConfig


@dataclass
class ConnectorMetrics:
    """Metrics for the Windows connector."""
    # Connection
    connection_attempts: int = 0
    successful_connections: int = 0
    disconnections: int = 0
    is_connected: bool = False

    # Events
    events_received: int = 0
    price_events: int = 0
    liquidation_events: int = 0
    order_activity_events: int = 0
    parse_errors: int = 0

    # Bytes
    bytes_received: int = 0

    # Timing
    start_time: float = field(default_factory=time.time)
    last_event_time: float = 0.0
    last_reconnect_time: float = 0.0

    @property
    def events_per_second(self) -> float:
        elapsed = time.time() - self.start_time
        return self.events_received / elapsed if elapsed > 0 else 0.0


class WindowsNodeConnector:
    """
    Windows-side TCP client connecting to WSL node adapter.

    Receives normalized events and routes them to callbacks
    for integration with the observation system.

    Usage:
        connector = WindowsNodeConnector()

        # Set callbacks
        connector.on_price = async def(event): ...
        connector.on_liquidation = async def(event): ...
        connector.on_order_activity = async def(event): ...

        await connector.start()
        # ... runs until stopped
        await connector.stop()
    """

    def __init__(self, config: Optional[WindowsConnectorConfig] = None):
        """
        Initialize connector.

        Args:
            config: Connector configuration (uses defaults if None)
        """
        self._config = config or WindowsConnectorConfig()

        # State
        self._running = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._reconnect_delay = self._config.reconnect_delay

        # Metrics
        self.metrics = ConnectorMetrics()

        # Callbacks
        self.on_price: Optional[Callable[[Dict], Awaitable[None]]] = None
        self.on_liquidation: Optional[Callable[[Dict], Awaitable[None]]] = None
        self.on_order_activity: Optional[Callable[[Dict], Awaitable[None]]] = None
        self.on_connected: Optional[Callable[[Dict], Awaitable[None]]] = None
        self.on_disconnected: Optional[Callable[[], Awaitable[None]]] = None

        # Order activity tracking (for position refresh triggering)
        self._recent_order_activity: Dict[str, List[Dict]] = {}  # wallet -> events
        self._order_activity_window = 60.0  # Keep 60 seconds of history

        # Latest prices cache
        self._latest_prices: Dict[str, float] = {}

        # Tasks
        self._read_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the connector."""
        if self._running:
            return

        self._running = True
        self.metrics.start_time = time.time()

        # Start connection loop
        self._reconnect_task = asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        """Stop the connector."""
        self._running = False

        # Cancel tasks
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Close connection
        await self._disconnect()

    async def wait_connected(self, timeout: float = 30.0) -> bool:
        """
        Wait until connected to adapter.

        Returns True if connected, False if timeout.
        """
        start = time.time()
        while not self.metrics.is_connected:
            if time.time() - start > timeout:
                return False
            await asyncio.sleep(0.1)
        return True

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest oracle price for a symbol."""
        return self._latest_prices.get(symbol)

    def get_all_prices(self) -> Dict[str, float]:
        """Get all latest oracle prices."""
        return dict(self._latest_prices)

    def get_recent_order_activity(
        self,
        wallet: str,
        coin: Optional[str] = None,
        since: Optional[float] = None
    ) -> List[Dict]:
        """
        Get recent order activity for a wallet.

        Args:
            wallet: Wallet address
            coin: Filter by coin (optional)
            since: Only activity after this timestamp (optional)

        Returns:
            List of order activity events
        """
        activities = self._recent_order_activity.get(wallet, [])

        if since:
            activities = [a for a in activities if a.get('timestamp', 0) > since]

        if coin:
            activities = [a for a in activities if a.get('coin') == coin]

        return activities

    def has_recent_activity(
        self,
        wallet: str,
        coin: str,
        window_seconds: float = 5.0
    ) -> bool:
        """
        Check if wallet has recent order activity for a coin.

        Used to trigger position re-reads when activity detected.
        """
        cutoff = time.time() - window_seconds
        activities = self.get_recent_order_activity(wallet, coin, cutoff)
        return len(activities) > 0

    # ==================== Internal Methods ====================

    async def _connection_loop(self) -> None:
        """Main connection loop with reconnection logic."""
        while self._running:
            try:
                # Attempt connection
                await self._connect()

                if self.metrics.is_connected:
                    # Reset reconnect delay on success
                    self._reconnect_delay = self._config.reconnect_delay

                    # Start reading
                    self._read_task = asyncio.create_task(self._read_loop())
                    await self._read_task

            except asyncio.CancelledError:
                break
            except Exception as e:
                pass

            # Disconnected - wait before reconnecting
            if self._running:
                self.metrics.last_reconnect_time = time.time()
                await asyncio.sleep(self._reconnect_delay)

                # Exponential backoff
                self._reconnect_delay = min(
                    self._reconnect_delay * self._config.reconnect_backoff,
                    self._config.max_reconnect_delay
                )

    async def _connect(self) -> None:
        """Establish TCP connection to adapter."""
        self.metrics.connection_attempts += 1

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self._config.tcp_host,
                    self._config.tcp_port,
                ),
                timeout=self._config.connect_timeout,
            )

            self.metrics.successful_connections += 1
            self.metrics.is_connected = True

            print(f"[WindowsConnector] Connected to {self._config.tcp_host}:{self._config.tcp_port}")

        except asyncio.TimeoutError:
            self.metrics.is_connected = False
        except ConnectionRefusedError:
            self.metrics.is_connected = False
        except Exception:
            self.metrics.is_connected = False

    async def _disconnect(self) -> None:
        """Close TCP connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except:
                pass

        self._reader = None
        self._writer = None
        self.metrics.is_connected = False
        self.metrics.disconnections += 1

        if self.on_disconnected:
            try:
                await self.on_disconnected()
            except:
                pass

    async def _read_loop(self) -> None:
        """Read events from adapter."""
        buffer = b""

        while self._running and self._reader:
            try:
                # Read chunk
                chunk = await asyncio.wait_for(
                    self._reader.read(self._config.read_buffer_size),
                    timeout=self._config.read_timeout,
                )

                if not chunk:
                    # Connection closed
                    break

                self.metrics.bytes_received += len(chunk)
                buffer += chunk

                # Process complete lines
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)

                    if line:
                        await self._process_event(line.decode('utf-8'))

            except asyncio.TimeoutError:
                # No data for a while - check connection is alive
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                break

        # Disconnected
        await self._disconnect()

    async def _process_event(self, line: str) -> None:
        """Process a single event line."""
        try:
            event = json.loads(line)
            self.metrics.events_received += 1
            self.metrics.last_event_time = time.time()

            event_type = event.get('event_type', '')

            if event_type == 'HL_PRICE':
                self.metrics.price_events += 1

                # Update price cache
                symbol = event.get('symbol')
                oracle_price = event.get('oracle_price')
                if symbol and oracle_price:
                    self._latest_prices[symbol] = oracle_price

                # Call callback
                if self.on_price:
                    await self.on_price(event)

            elif event_type == 'HL_LIQUIDATION':
                self.metrics.liquidation_events += 1

                if self.on_liquidation:
                    await self.on_liquidation(event)

            elif event_type == 'HL_ORDER_ACTIVITY':
                self.metrics.order_activity_events += 1

                # Track activity
                self._track_order_activity(event)

                if self.on_order_activity:
                    await self.on_order_activity(event)

            elif event_type == 'CONNECTED':
                # Welcome message from adapter
                if self.on_connected:
                    await self.on_connected(event)

        except json.JSONDecodeError:
            self.metrics.parse_errors += 1
        except Exception:
            self.metrics.parse_errors += 1

    def _track_order_activity(self, event: Dict) -> None:
        """Track order activity for position refresh triggering."""
        wallet = event.get('wallet')
        if not wallet:
            return

        # Initialize wallet tracking
        if wallet not in self._recent_order_activity:
            self._recent_order_activity[wallet] = []

        # Add event
        self._recent_order_activity[wallet].append(event)

        # Cleanup old events
        cutoff = time.time() - self._order_activity_window
        self._recent_order_activity[wallet] = [
            e for e in self._recent_order_activity[wallet]
            if e.get('timestamp', 0) > cutoff
        ]

        # Cleanup empty wallets
        if not self._recent_order_activity[wallet]:
            del self._recent_order_activity[wallet]


class ObservationSystemConnector:
    """
    Higher-level connector that integrates with the observation system.

    Wraps WindowsNodeConnector and routes events to M1 ingestion.
    Optionally integrates with PositionStateManager for tiered refresh.
    """

    def __init__(
        self,
        observation_system,  # ObservationSystem instance
        config: Optional[WindowsConnectorConfig] = None,
        position_state_manager=None,  # Optional PositionStateManager
    ):
        """
        Initialize connector.

        Args:
            observation_system: ObservationSystem instance to feed events to
            config: Connector configuration
            position_state_manager: Optional PositionStateManager for position tracking
        """
        self._obs = observation_system
        self._connector = WindowsNodeConnector(config)
        self._position_manager = position_state_manager

        # Wire up callbacks
        self._connector.on_price = self._handle_price
        self._connector.on_liquidation = self._handle_liquidation
        self._connector.on_order_activity = self._handle_order_activity

        # Wire position manager callbacks if provided
        if self._position_manager:
            self._position_manager.on_position_update = self._handle_position_update
            self._position_manager.on_proximity_alert = self._handle_proximity_alert

    async def start(self) -> None:
        """Start the connector and position manager."""
        await self._connector.start()
        if self._position_manager:
            await self._position_manager.start()

    async def stop(self) -> None:
        """Stop the connector and position manager."""
        if self._position_manager:
            await self._position_manager.stop()
        await self._connector.stop()

    async def wait_connected(self, timeout: float = 30.0) -> bool:
        """Wait until connected."""
        return await self._connector.wait_connected(timeout)

    @property
    def metrics(self) -> ConnectorMetrics:
        """Get connector metrics."""
        return self._connector.metrics

    @property
    def position_manager(self):
        """Get position state manager."""
        return self._position_manager

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest oracle price."""
        return self._connector.get_latest_price(symbol)

    def has_recent_activity(self, wallet: str, coin: str) -> bool:
        """Check for recent order activity."""
        return self._connector.has_recent_activity(wallet, coin)

    # ==================== Event Handlers ====================

    async def _handle_price(self, event: Dict) -> None:
        """Handle price event - feed to M1 and position manager.

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        """
        try:
            symbol = event.get('symbol')

            if symbol:
                # Use wall clock for governance freshness check
                now = time.time()

                # Feed to M1
                self._obs.ingest_observation(
                    timestamp=now,  # Wall clock for governance validation
                    symbol=symbol,
                    event_type='HL_PRICE',
                    payload=event,  # Original timestamp preserved in payload
                )

                # Update position manager with new prices
                if self._position_manager:
                    oracle_price = event.get('oracle_price')
                    if oracle_price:
                        self._position_manager.update_prices({symbol: oracle_price})

        except Exception:
            pass

    async def _handle_liquidation(self, event: Dict) -> None:
        """Handle liquidation event - feed to M1.

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        """
        try:
            symbol = event.get('symbol')

            if symbol:
                # Use wall clock for governance freshness check
                now = time.time()

                self._obs.ingest_observation(
                    timestamp=now,  # Wall clock for governance validation
                    symbol=symbol,
                    event_type='HL_LIQUIDATION',
                    payload=event,  # Original timestamp preserved in payload
                )
        except Exception:
            pass

    async def _handle_order_activity(self, event: Dict) -> None:
        """
        Handle order activity event.

        Triggers position refresh for tracked wallets.
        """
        try:
            wallet = event.get('wallet')
            coin = event.get('coin')

            if wallet and coin and self._position_manager:
                # Trigger refresh for this wallet/coin if tracked
                await self._position_manager.on_order_activity(wallet, coin)

        except Exception:
            pass

    async def _handle_position_update(self, event: Dict) -> None:
        """Handle position update from position manager - feed to M1.

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        """
        try:
            symbol = event.get('symbol')

            if symbol:
                # Use wall clock for governance freshness check
                now = time.time()

                self._obs.ingest_observation(
                    timestamp=now,  # Wall clock for governance validation
                    symbol=symbol,
                    event_type='HL_POSITION',
                    payload=event,  # Original timestamp preserved in payload
                )
        except Exception:
            pass

    async def _handle_proximity_alert(self, alert) -> None:
        """
        Handle proximity alert from position manager.

        Alerts are logged and can trigger immediate action.
        """
        try:
            # Log critical alerts
            if alert.new_tier.value == 'CRITICAL':
                print(f"[ProximityAlert] CRITICAL: {alert.wallet[:10]}... {alert.coin} "
                      f"at {alert.proximity_pct:.2f}% to liquidation")
        except Exception:
            pass
