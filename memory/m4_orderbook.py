"""
M4 Order Book Primitives

Constitutional order book primitives as defined in RAW-DATA PRIMITIVES.md Section 7.

ALLOWED: Resting Size, Order Consumption, Absorption Event, Refill Event
FORBIDDEN: Support, Resistance, Strength, Weakness, "Important" levels

Authority: RAW-DATA PRIMITIVES.md, EPISTEMIC_CONSTITUTION.md
"""

from dataclasses import dataclass
from typing import Optional
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


@dataclass(frozen=True)
class RestingSizeAtPrice:
    """7.1: Resting Size at Price

    Total resting quantity at a price level.
    Constitutional: Factual observation, not interpretation.
    """
    price: float
    size_bid: float
    size_ask: float
    timestamp: float


@dataclass(frozen=True)
class OrderConsumption:
    """7.2: Order Consumption

    Reduction in resting size due to trades.
    Constitutional: Factual size reduction, not directional prediction.
    """
    price: float
    initial_size: float
    consumed_size: float
    remaining_size: float
    duration: float


@dataclass(frozen=True)
class AbsorptionEvent:
    """7.3: Absorption Event

    Trades occur without price movement while size decreases.
    Constitutional: NOT "support" - purely factual consumption.
    """
    price: float
    consumed_size: float
    duration: float
    trade_count: int


@dataclass(frozen=True)
class RefillEvent:
    """7.4: Refill Event

    Resting size replenishes after consumption.
    Constitutional: Factual size increase, not directional signal.
    """
    price: float
    refill_size: float
    duration: float


def compute_resting_size(node: EnrichedLiquidityMemoryNode) -> Optional[RestingSizeAtPrice]:
    """Compute current resting size at node price.

    Returns None if no order book data available.
    """
    if node.last_orderbook_update_ts is None:
        return None

    return RestingSizeAtPrice(
        price=node.price_center,
        size_bid=node.resting_size_bid,
        size_ask=node.resting_size_ask,
        timestamp=node.last_orderbook_update_ts
    )


def detect_order_consumption(
    node: EnrichedLiquidityMemoryNode,
    previous_size: float,
    current_size: float,
    duration: float
) -> Optional[OrderConsumption]:
    """Detect consumption of resting orders.

    Returns None if no consumption detected (size unchanged or increased).
    """
    if previous_size <= 0 or current_size >= previous_size:
        return None

    consumed = previous_size - current_size

    return OrderConsumption(
        price=node.price_center,
        initial_size=previous_size,
        consumed_size=consumed,
        remaining_size=current_size,
        duration=duration
    )


def detect_absorption_event(
    node: EnrichedLiquidityMemoryNode,
    price_start: float,
    price_end: float,
    consumed_size: float,
    duration: float,
    trade_count: int,
    price_tolerance: float = 0.01
) -> Optional[AbsorptionEvent]:
    """Detect absorption event (trades without price movement).

    Constitutional: Detects factual price stability during consumption.
    NOT "support/resistance" interpretation.

    Args:
        price_tolerance: Maximum price movement (percentage) to qualify as absorption

    Returns None if price moved beyond tolerance.
    """
    price_movement_pct = abs(price_end - price_start) / price_start

    if price_movement_pct > price_tolerance:
        return None

    if consumed_size <= 0:
        return None

    return AbsorptionEvent(
        price=node.price_center,
        consumed_size=consumed_size,
        duration=duration,
        trade_count=trade_count
    )


def detect_refill_event(
    node: EnrichedLiquidityMemoryNode,
    previous_size: float,
    current_size: float,
    duration: float
) -> Optional[RefillEvent]:
    """Detect refill event (resting size replenishes).

    Constitutional: Factual size increase after depletion.

    Returns None if no refill detected (size decreased or unchanged).
    """
    if current_size <= previous_size:
        return None

    refill = current_size - previous_size

    return RefillEvent(
        price=node.price_center,
        refill_size=refill,
        duration=duration
    )
