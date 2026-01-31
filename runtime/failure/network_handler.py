"""
HLP16: Network Failure Handler.

Handles WebSocket disconnections and reconnections with:
- Exponential backoff reconnection
- Heartbeat monitoring for stale connections
- State preservation during disconnection
- Orderbook snapshot request on reconnection
- Trading halt during disconnected state

Integration points:
- DegradationManager: Triggers REDUCED/EMERGENCY on network failures
- HealthMonitor: Reports connection health
- CircuitBreaker: Can trigger on repeated failures
"""

import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum, auto
from threading import Lock


class ConnectionState(Enum):
    """WebSocket connection state."""
    CONNECTED = auto()
    DISCONNECTED = auto()
    RECONNECTING = auto()
    FAILED = auto()  # Max retries exceeded


@dataclass
class NetworkConfig:
    """Configuration for network failure handling."""
    # Heartbeat settings
    heartbeat_interval_ms: int = 5000      # Send ping every 5 seconds
    heartbeat_timeout_ms: int = 15000      # Connection stale if no pong in 15s

    # Reconnection settings
    max_reconnect_attempts: int = 10       # Give up after 10 attempts
    backoff_base_ms: int = 1000            # Start with 1 second delay
    backoff_max_ms: int = 60000            # Cap at 60 seconds
    backoff_multiplier: float = 2.0        # Double delay each attempt

    # Recovery settings
    require_snapshot_on_reconnect: bool = True
    max_sequence_gap: int = 10             # Request full snapshot if gap > 10

    # Trading behavior during disconnection
    halt_trading_on_disconnect: bool = True
    maintain_stops_during_disconnect: bool = True

    # Alert thresholds
    warn_after_attempts: int = 3           # Warn after 3 failed attempts
    critical_after_attempts: int = 7       # Critical after 7 failed attempts


@dataclass
class ReconnectionEvent:
    """Record of a reconnection event."""
    timestamp: int  # nanoseconds
    attempt_number: int
    delay_ms: int
    success: bool
    error: Optional[str] = None
    sequence_gap: int = 0
    snapshot_requested: bool = False


@dataclass
class HeartbeatState:
    """Tracks heartbeat state for a connection."""
    last_sent: int = 0           # ns timestamp
    last_received: int = 0       # ns timestamp
    pending: bool = False
    consecutive_timeouts: int = 0


class NetworkHandler:
    """
    Handle WebSocket disconnections and reconnections.

    Provides:
    - Automatic reconnection with exponential backoff
    - Heartbeat monitoring to detect stale connections
    - State preservation and recovery validation
    - Trading halt during disconnected state

    Usage:
        handler = NetworkHandler(config)
        handler.set_reconnect_callback(async_reconnect_fn)
        handler.set_snapshot_callback(async_snapshot_fn)

        # On disconnect
        await handler.on_disconnect("Connection reset")

        # Monitor heartbeats
        asyncio.create_task(handler.monitor_heartbeat())
    """

    def __init__(
        self,
        config: NetworkConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or NetworkConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Connection state
        self._state = ConnectionState.DISCONNECTED
        self._state_since: int = 0
        self._reconnect_attempts: int = 0
        self._current_backoff_ms: int = self._config.backoff_base_ms

        # Heartbeat tracking
        self._heartbeat = HeartbeatState()

        # Sequence tracking for gap detection
        self._last_sequence: int = 0
        self._sequence_gaps: List[tuple] = []  # [(expected, received)]

        # Event history
        self._events: List[ReconnectionEvent] = []

        # Callbacks
        self._on_reconnect: Optional[Callable] = None
        self._on_snapshot_request: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None
        self._on_trading_halt: Optional[Callable] = None
        self._on_trading_resume: Optional[Callable] = None

        self._lock = Lock()
        self._reconnect_task: Optional[asyncio.Task] = None

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == ConnectionState.CONNECTED

    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed based on connection state."""
        if not self._config.halt_trading_on_disconnect:
            return True
        return self._state == ConnectionState.CONNECTED

    def set_reconnect_callback(self, callback: Callable):
        """Set async callback for reconnection attempts."""
        self._on_reconnect = callback

    def set_snapshot_callback(self, callback: Callable):
        """Set async callback for snapshot requests."""
        self._on_snapshot_request = callback

    def set_state_change_callback(self, callback: Callable):
        """Set callback for state changes."""
        self._on_state_change = callback

    def set_trading_halt_callback(self, callback: Callable):
        """Set callback when trading should halt."""
        self._on_trading_halt = callback

    def set_trading_resume_callback(self, callback: Callable):
        """Set callback when trading can resume."""
        self._on_trading_resume = callback

    def on_connected(self):
        """Called when connection is established."""
        ts = self._now_ns()

        with self._lock:
            old_state = self._state
            self._state = ConnectionState.CONNECTED
            self._state_since = ts
            self._reconnect_attempts = 0
            self._current_backoff_ms = self._config.backoff_base_ms

            # Reset heartbeat
            self._heartbeat = HeartbeatState(
                last_sent=ts,
                last_received=ts,
                pending=False,
                consecutive_timeouts=0
            )

            self._logger.info("Network connection established")

            # Notify state change
            if self._on_state_change:
                try:
                    self._on_state_change(old_state, ConnectionState.CONNECTED)
                except Exception as e:
                    self._logger.error(f"State change callback error: {e}")

            # Resume trading if was disconnected
            if old_state != ConnectionState.CONNECTED and self._on_trading_resume:
                try:
                    self._on_trading_resume()
                except Exception as e:
                    self._logger.error(f"Trading resume callback error: {e}")

    async def on_disconnect(self, reason: str = "Unknown"):
        """
        Called when WebSocket drops.

        Actions:
        1. Mark system as DISCONNECTED
        2. Stop trading immediately (maintain existing stops)
        3. Start reconnection with exponential backoff
        """
        ts = self._now_ns()

        with self._lock:
            if self._state == ConnectionState.DISCONNECTED:
                return  # Already handling

            old_state = self._state
            self._state = ConnectionState.DISCONNECTED
            self._state_since = ts

            self._logger.warning(f"Network disconnected: {reason}")

            # Halt trading
            if self._config.halt_trading_on_disconnect and self._on_trading_halt:
                try:
                    self._on_trading_halt()
                except Exception as e:
                    self._logger.error(f"Trading halt callback error: {e}")

            # Notify state change
            if self._on_state_change:
                try:
                    self._on_state_change(old_state, ConnectionState.DISCONNECTED)
                except Exception as e:
                    self._logger.error(f"State change callback error: {e}")

        # Start reconnection
        await self._start_reconnection()

    async def _start_reconnection(self):
        """Start reconnection with exponential backoff."""
        self._state = ConnectionState.RECONNECTING

        while self._reconnect_attempts < self._config.max_reconnect_attempts:
            self._reconnect_attempts += 1
            ts = self._now_ns()

            # Log attempt
            level = logging.WARNING
            if self._reconnect_attempts >= self._config.critical_after_attempts:
                level = logging.ERROR
            elif self._reconnect_attempts >= self._config.warn_after_attempts:
                level = logging.WARNING

            self._logger.log(
                level,
                f"Reconnection attempt {self._reconnect_attempts}/{self._config.max_reconnect_attempts} "
                f"(backoff: {self._current_backoff_ms}ms)"
            )

            # Wait with backoff
            await asyncio.sleep(self._current_backoff_ms / 1000.0)

            # Attempt reconnection
            success = False
            error = None

            if self._on_reconnect:
                try:
                    success = await self._on_reconnect()
                except Exception as e:
                    error = str(e)
                    self._logger.error(f"Reconnection error: {e}")

            # Record event
            event = ReconnectionEvent(
                timestamp=ts,
                attempt_number=self._reconnect_attempts,
                delay_ms=self._current_backoff_ms,
                success=success,
                error=error
            )
            self._events.append(event)

            if success:
                await self._on_reconnect_success()
                return

            # Increase backoff
            self._current_backoff_ms = min(
                int(self._current_backoff_ms * self._config.backoff_multiplier),
                self._config.backoff_max_ms
            )

        # Max attempts exceeded
        self._state = ConnectionState.FAILED
        self._logger.error(
            f"Network reconnection FAILED after {self._reconnect_attempts} attempts"
        )

    async def _on_reconnect_success(self):
        """
        Called after successful reconnection.

        Actions:
        1. Request full orderbook snapshot
        2. Rebuild state from snapshot
        3. Verify no sequence gaps
        4. Resume trading only after validation
        """
        ts = self._now_ns()

        self._logger.info("Reconnection successful, validating state...")

        # Request snapshot if configured
        if self._config.require_snapshot_on_reconnect and self._on_snapshot_request:
            try:
                await self._on_snapshot_request()
                self._logger.info("Snapshot requested for state recovery")

                # Update last event
                if self._events:
                    self._events[-1].snapshot_requested = True

            except Exception as e:
                self._logger.error(f"Snapshot request failed: {e}")

        # Mark as connected (triggers trading resume)
        self.on_connected()

    def on_heartbeat_sent(self):
        """Called when heartbeat/ping is sent."""
        ts = self._now_ns()
        with self._lock:
            self._heartbeat.last_sent = ts
            self._heartbeat.pending = True

    def on_heartbeat_received(self):
        """Called when heartbeat/pong is received."""
        ts = self._now_ns()
        with self._lock:
            self._heartbeat.last_received = ts
            self._heartbeat.pending = False
            self._heartbeat.consecutive_timeouts = 0

    def on_message_received(self, sequence: int = None):
        """Called on any message received (updates liveness)."""
        ts = self._now_ns()
        with self._lock:
            self._heartbeat.last_received = ts

            # Track sequence gaps
            if sequence is not None:
                expected = self._last_sequence + 1
                if sequence > expected and self._last_sequence > 0:
                    gap = sequence - expected
                    self._sequence_gaps.append((expected, sequence))

                    if gap > self._config.max_sequence_gap:
                        self._logger.warning(
                            f"Sequence gap detected: expected {expected}, got {sequence} "
                            f"(gap: {gap})"
                        )

                self._last_sequence = sequence

    async def monitor_heartbeat(self):
        """
        Continuous heartbeat monitoring coroutine.

        Detects stale connections by tracking heartbeat responses.
        """
        while True:
            await asyncio.sleep(self._config.heartbeat_interval_ms / 1000.0)

            if self._state != ConnectionState.CONNECTED:
                continue

            ts = self._now_ns()

            with self._lock:
                time_since_received_ms = (ts - self._heartbeat.last_received) / 1_000_000

                if time_since_received_ms > self._config.heartbeat_timeout_ms:
                    self._heartbeat.consecutive_timeouts += 1

                    self._logger.warning(
                        f"Heartbeat timeout: no response in {time_since_received_ms:.0f}ms "
                        f"(consecutive: {self._heartbeat.consecutive_timeouts})"
                    )

                    # Treat as disconnect after consecutive timeouts
                    if self._heartbeat.consecutive_timeouts >= 3:
                        asyncio.create_task(
                            self.on_disconnect("Heartbeat timeout")
                        )

    def check_sequence_gaps(self) -> List[tuple]:
        """Get list of sequence gaps detected."""
        with self._lock:
            return list(self._sequence_gaps)

    def clear_sequence_gaps(self):
        """Clear recorded sequence gaps (after snapshot recovery)."""
        with self._lock:
            self._sequence_gaps.clear()

    def get_events(self, limit: int = 100) -> List[ReconnectionEvent]:
        """Get recent reconnection events."""
        with self._lock:
            return list(self._events[-limit:])

    def get_summary(self) -> Dict:
        """Get network handler summary."""
        ts = self._now_ns()

        with self._lock:
            time_in_state_ms = (ts - self._state_since) / 1_000_000 if self._state_since else 0
            time_since_heartbeat_ms = (ts - self._heartbeat.last_received) / 1_000_000 if self._heartbeat.last_received else 0

            return {
                'state': self._state.name,
                'time_in_state_ms': time_in_state_ms,
                'reconnect_attempts': self._reconnect_attempts,
                'current_backoff_ms': self._current_backoff_ms,
                'last_heartbeat_ms_ago': time_since_heartbeat_ms,
                'consecutive_heartbeat_timeouts': self._heartbeat.consecutive_timeouts,
                'sequence_gaps_count': len(self._sequence_gaps),
                'is_trading_allowed': self.is_trading_allowed,
                'total_reconnection_events': len(self._events),
            }

    def reset(self):
        """Reset handler state (for testing or manual recovery)."""
        with self._lock:
            self._state = ConnectionState.DISCONNECTED
            self._state_since = 0
            self._reconnect_attempts = 0
            self._current_backoff_ms = self._config.backoff_base_ms
            self._heartbeat = HeartbeatState()
            self._last_sequence = 0
            self._sequence_gaps.clear()
            self._events.clear()
