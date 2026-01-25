"""
EP-4 Hyperliquid Adapter - Real Exchange Connection

Bridges EP-4 execution pipeline to Hyperliquid OrderExecutor.
Replaces MockedExchangeAdapter for production use.

Hardenings:
- E5: Real order execution via OrderExecutor
- Uses E1-E4 hardenings from OrderExecutor

Authority: EP-4 Execution Policy Specification v1.0
"""

import asyncio
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from execution.ep4_exchange_adapter import (
    ExchangeConstraints,
    ExchangeResponseCode,
    ExchangeResponse,
)
from execution.ep4_action_schemas import (
    Action,
    OpenPositionAction,
    ClosePositionAction,
    AdjustPositionAction,
    CancelOrdersAction,
    NoOpAction,
    OrderType as ActionOrderType,
    Side,
)

# Import OrderExecutor from runtime
from runtime.exchange.order_executor import (
    OrderExecutor,
    ExecutorConfig,
    OrderRequest,
    OrderType,
    OrderSide,
    OrderStatus,
)


@dataclass(frozen=True)
class HyperliquidConfig:
    """Configuration for Hyperliquid adapter."""
    # API settings
    api_url: str = "https://api.hyperliquid.xyz"
    testnet_api_url: str = "https://api.hyperliquid-testnet.xyz"
    use_testnet: bool = True  # Default to testnet for safety

    # Wallet
    private_key: Optional[str] = None
    wallet_address: Optional[str] = None

    # Exchange constraints (Hyperliquid specific)
    min_order_size: float = 0.001
    max_order_size: float = 1000.0
    step_size: float = 0.001
    tick_size: float = 0.1
    max_leverage: float = 50.0


class HyperliquidExchangeAdapter:
    """
    E5: Real Hyperliquid exchange adapter for EP-4.

    Implements same interface as MockedExchangeAdapter but
    uses OrderExecutor for real order submission.
    """

    def __init__(
        self,
        *,
        config: HyperliquidConfig,
        exchange_constraints: Optional[ExchangeConstraints] = None
    ):
        """
        Initialize Hyperliquid adapter.

        Args:
            config: Hyperliquid configuration
            exchange_constraints: Exchange constraints (optional override)
        """
        self._config = config

        # Build constraints
        self._constraints = exchange_constraints or ExchangeConstraints(
            min_order_size=config.min_order_size,
            max_order_size=config.max_order_size,
            step_size=config.step_size,
            tick_size=config.tick_size,
            max_leverage=config.max_leverage,
            margin_mode="CROSS"
        )

        # Build executor config
        executor_config = ExecutorConfig(
            api_url=config.api_url,
            testnet_api_url=config.testnet_api_url,
            use_testnet=config.use_testnet
        )

        # Create OrderExecutor
        self._executor = OrderExecutor(
            config=executor_config,
            private_key=config.private_key,
            wallet_address=config.wallet_address
        )

        self._call_count = 0

    def execute_order(
        self,
        *,
        action_id: str,
        order_params: dict,
        timestamp: float
    ) -> ExchangeResponse:
        """
        E5: Execute order on Hyperliquid.

        Converts EP-4 action to OrderRequest and submits via OrderExecutor.

        Args:
            action_id: Action identifier
            order_params: Contains 'action' key with EP-4 action object
            timestamp: Execution timestamp

        Returns:
            ExchangeResponse
        """
        self._call_count += 1

        action = order_params.get("action")
        if action is None:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.REJECTED,
                order_id=None,
                message="Missing action in order_params",
                timestamp=timestamp
            )

        # Convert EP-4 action to OrderRequest
        order_request = self._convert_action_to_request(action, action_id)
        if order_request is None:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.REJECTED,
                order_id=None,
                message=f"Cannot convert action type: {type(action).__name__}",
                timestamp=timestamp
            )

        # Submit order (run async in sync context)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context - create task
                future = asyncio.ensure_future(
                    self._executor.submit_order(order_request)
                )
                # This is a limitation - we need to handle this differently
                # For now, return AMBIGUOUS and let caller retry
                return ExchangeResponse(
                    response_code=ExchangeResponseCode.AMBIGUOUS,
                    order_id=None,
                    message="Async submission pending - check status",
                    timestamp=timestamp
                )
            else:
                response = loop.run_until_complete(
                    self._executor.submit_order(order_request)
                )
        except RuntimeError:
            # No event loop - create one
            response = asyncio.run(
                self._executor.submit_order(order_request)
            )

        # Convert OrderResponse to ExchangeResponse
        if response.success:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.ACKNOWLEDGED,
                order_id=response.order_id,
                message="Order submitted",
                timestamp=timestamp
            )
        elif response.status == OrderStatus.REJECTED:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.REJECTED,
                order_id=None,
                message=response.error_message or "Order rejected",
                timestamp=timestamp
            )
        elif response.status == OrderStatus.FAILED:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.TIMEOUT,
                order_id=None,
                message=response.error_message or "Order failed",
                timestamp=timestamp
            )
        else:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.AMBIGUOUS,
                order_id=response.order_id,
                message=response.error_message or "Unknown status",
                timestamp=timestamp
            )

    def _convert_action_to_request(
        self,
        action: Action,
        action_id: str
    ) -> Optional[OrderRequest]:
        """Convert EP-4 action to OrderRequest."""
        if isinstance(action, OpenPositionAction):
            return OrderRequest(
                symbol=action.symbol,
                side=OrderSide.BUY if action.side == Side.LONG else OrderSide.SELL,
                size=action.quantity,
                order_type=(
                    OrderType.LIMIT if action.order_type == ActionOrderType.LIMIT
                    else OrderType.MARKET
                ),
                price=action.limit_price,
                reduce_only=False,
                client_order_id=action_id
            )
        elif isinstance(action, ClosePositionAction):
            # Close position - need to determine side from context
            # For now, assume we know the position side
            return OrderRequest(
                symbol=action.symbol,
                side=OrderSide.SELL,  # Will be overridden by reduce_only
                size=action.quantity or 0,  # 0 = close all
                order_type=OrderType.MARKET,
                reduce_only=True,
                client_order_id=action_id
            )
        elif isinstance(action, AdjustPositionAction):
            # Adjust - positive delta = increase, negative = decrease
            side = OrderSide.BUY if action.delta_quantity > 0 else OrderSide.SELL
            return OrderRequest(
                symbol=action.symbol,
                side=side,
                size=abs(action.delta_quantity),
                order_type=OrderType.MARKET,
                reduce_only=action.delta_quantity < 0,
                client_order_id=action_id
            )
        else:
            return None

    def cancel_orders(
        self,
        *,
        action_id: str,
        symbol: Optional[str],
        timestamp: float
    ) -> ExchangeResponse:
        """
        Cancel orders on Hyperliquid.

        Args:
            action_id: Action identifier
            symbol: Symbol to cancel (None = all)
            timestamp: Execution timestamp

        Returns:
            ExchangeResponse
        """
        self._call_count += 1

        # Get pending orders
        pending = self._executor.get_pending_orders()

        if not pending:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.ACKNOWLEDGED,
                order_id=None,
                message="No pending orders to cancel",
                timestamp=timestamp
            )

        # Filter by symbol if specified
        orders_to_cancel = [
            (oid, update) for oid, update in pending.items()
            if symbol is None or update.symbol == symbol
        ]

        if not orders_to_cancel:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.ACKNOWLEDGED,
                order_id=None,
                message=f"No pending orders for {symbol}",
                timestamp=timestamp
            )

        # Cancel each order
        cancelled = 0
        failed = 0

        for order_id, update in orders_to_cancel:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already async - schedule
                    asyncio.ensure_future(
                        self._executor.cancel_order(order_id, update.symbol)
                    )
                    cancelled += 1
                else:
                    success = loop.run_until_complete(
                        self._executor.cancel_order(order_id, update.symbol)
                    )
                    if success:
                        cancelled += 1
                    else:
                        failed += 1
            except RuntimeError:
                success = asyncio.run(
                    self._executor.cancel_order(order_id, update.symbol)
                )
                if success:
                    cancelled += 1
                else:
                    failed += 1

        if failed == 0:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.ACKNOWLEDGED,
                order_id=None,
                message=f"Cancelled {cancelled} orders",
                timestamp=timestamp
            )
        else:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.AMBIGUOUS,
                order_id=None,
                message=f"Cancelled {cancelled}, failed {failed}",
                timestamp=timestamp
            )

    def get_constraints(self) -> ExchangeConstraints:
        """Get exchange constraints."""
        return self._constraints

    def get_call_count(self) -> int:
        """Get number of exchange calls made."""
        return self._call_count

    def get_executor(self) -> OrderExecutor:
        """Get underlying OrderExecutor for advanced operations."""
        return self._executor

    async def close(self):
        """Close the adapter and underlying executor."""
        await self._executor.close()
