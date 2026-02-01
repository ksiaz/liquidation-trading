"""
HL-Native Adapter

Wires HLNativeDecisionLoop to NodeSubscriber events.
Converts node_client events to hl_native events.
"""

import time
from typing import Optional, List, Callable

from ..node_client.types import (
    LiquidationEvent as NodeLiquidationEvent,
    PriceEvent as NodePriceEvent,
)
from ..node_client.subscriber import NodeSubscriber
from .decision_loop import (
    HLNativeDecisionLoop,
    LiquidationEvent,
    DecisionRecord,
    Decision,
)


class HLNativeAdapter:
    """
    Adapter that connects NodeSubscriber to HLNativeDecisionLoop.

    Flow:
        NodeSubscriber → HLNativeAdapter → HLNativeDecisionLoop → DecisionRecords
    """

    def __init__(
        self,
        symbols: List[str] = None,
        address: str = 'localhost:50051',
        on_decision: Optional[Callable[[DecisionRecord], None]] = None,
        on_non_skip_decision: Optional[Callable[[DecisionRecord], None]] = None,
    ):
        """
        Initialize adapter.

        Args:
            symbols: HL symbols to track (BTC, ETH, SOL)
            address: gRPC adapter address
            on_decision: Callback for every decision
            on_non_skip_decision: Callback for non-SKIP decisions only
        """
        self._symbols = symbols or ['BTC', 'ETH', 'SOL']
        self._address = address
        self._on_decision = on_decision
        self._on_non_skip_decision = on_non_skip_decision

        # Create decision loop
        self._loop = HLNativeDecisionLoop(symbols=self._symbols)

        # Create subscriber (will be started in start())
        self._subscriber: Optional[NodeSubscriber] = None
        self._running = False

    def _create_subscriber(self) -> NodeSubscriber:
        """Create and wire the subscriber."""
        subscriber = NodeSubscriber(
            address=self._address,
            client_id='hl-native-loop',
            symbols=self._symbols,
        )

        # Wire callbacks
        subscriber.on_price(self._handle_price)
        subscriber.on_liquidation(self._handle_liquidation)

        return subscriber

    def _handle_price(self, event: NodePriceEvent):
        """Handle price event from node."""
        # Feed to decision loop (for oracle price reference)
        self._loop.on_hl_price(
            symbol=event.symbol,
            oracle_price=event.oracle_float,
            timestamp=event.timestamp_ns / 1_000_000_000,
        )

    def _handle_liquidation(self, event: NodeLiquidationEvent):
        """Handle liquidation event from node."""
        # Convert to hl_native format
        liq_event = LiquidationEvent(
            symbol=event.symbol,
            side=event.side,  # LONG or SHORT
            size_usd=event.value_usd_float,
            price=event.price_float,
            timestamp=event.timestamp_ms / 1000.0,
            wallet=event.liquidated_wallet,
        )

        # Feed to decision loop
        record = self._loop.on_liquidation(liq_event)

        # Notify callbacks
        if self._on_decision:
            self._on_decision(record)

        if self._on_non_skip_decision and record.decision != Decision.SKIP.value:
            self._on_non_skip_decision(record)

    def start(self) -> bool:
        """
        Start receiving events.

        Returns:
            True if connected successfully
        """
        if self._running:
            return True

        self._subscriber = self._create_subscriber()
        if not self._subscriber.start():
            print("[HLNativeAdapter] Failed to connect to adapter")
            return False

        self._running = True
        print(f"[HLNativeAdapter] Started, tracking: {self._symbols}")
        return True

    def stop(self):
        """Stop receiving events."""
        if self._subscriber:
            self._subscriber.stop()
        self._running = False
        print("[HLNativeAdapter] Stopped")

    def get_loop(self) -> HLNativeDecisionLoop:
        """Get the decision loop instance."""
        return self._loop

    def get_metrics(self) -> dict:
        """Get combined metrics."""
        loop_metrics = self._loop.get_metrics()
        subscriber_metrics = {}
        if self._subscriber:
            subscriber_metrics = self._subscriber.get_metrics()
        return {
            **loop_metrics,
            'subscriber': subscriber_metrics,
        }

    @property
    def is_connected(self) -> bool:
        """True if connected to adapter."""
        return self._subscriber.is_connected if self._subscriber else False


def run_hl_native_loop(
    symbols: List[str] = None,
    address: str = 'localhost:50051',
    duration_seconds: float = 60.0,
    output_file: str = None,
) -> HLNativeDecisionLoop:
    """
    Run the HL-native decision loop for a specified duration.

    Args:
        symbols: Symbols to track
        address: gRPC adapter address
        duration_seconds: How long to run
        output_file: Optional file to export decisions

    Returns:
        The decision loop with collected decisions
    """
    import time

    symbols = symbols or ['BTC', 'ETH', 'SOL']

    # Track non-skip decisions for logging
    non_skip_decisions = []

    def on_non_skip(record: DecisionRecord):
        print(f"[SIGNAL] {record.symbol}: {record.decision} - {record.reason}")
        print(f"         Value: ${record.total_value_usd:,.0f} | "
              f"Long: ${record.long_value_usd:,.0f} | Short: ${record.short_value_usd:,.0f}")
        non_skip_decisions.append(record)

    # Create adapter
    adapter = HLNativeAdapter(
        symbols=symbols,
        address=address,
        on_non_skip_decision=on_non_skip,
    )

    # Start
    if not adapter.start():
        print("Failed to start adapter. Is the HL node adapter running?")
        return adapter.get_loop()

    print(f"Running for {duration_seconds}s...")
    start_time = time.time()

    try:
        while time.time() - start_time < duration_seconds:
            time.sleep(1.0)

            # Print periodic status
            elapsed = time.time() - start_time
            metrics = adapter.get_loop().get_metrics()
            if int(elapsed) % 10 == 0 and elapsed > 0:
                print(f"[{int(elapsed)}s] Events: {metrics['events_processed']}, "
                      f"Signals: {metrics['non_skip_decisions']}")

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    # Stop
    adapter.stop()

    # Summary
    loop = adapter.get_loop()
    metrics = loop.get_metrics()

    print("\n" + "="*60)
    print("HL-Native Decision Loop Summary")
    print("="*60)
    print(f"Duration: {time.time() - start_time:.1f}s")
    print(f"Events processed: {metrics['events_processed']}")
    print(f"Decisions made: {metrics['decisions_made']}")
    print(f"Non-SKIP signals: {metrics['non_skip_decisions']}")
    print(f"Skip rate: {metrics['skip_rate']:.1%}")

    # Export if requested
    if output_file:
        loop.export_decisions_json(output_file)
        print(f"\nDecisions exported to: {output_file}")

    return loop
