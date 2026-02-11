"""
DATA SOURCE CONTRACT - CONSTITUTIONAL AUTHORITY

This file defines what each data source CAN and CANNOT provide.
These rules are NON-NEGOTIABLE and must not be bypassed.

Any component that violates these contracts is architecturally broken.
"""

from enum import Enum, auto
from typing import Set, FrozenSet


class DataSource(Enum):
    """Available data sources."""
    HL_NODE = auto()      # Hyperliquid protocol-native data
    BINANCE = auto()      # Binance exchange-surface data


class DataCapability(Enum):
    """What a data source can provide."""
    # HL Node capabilities
    ORACLE_PRICE = auto()           # Authoritative liquidation trigger price
    LIQUIDATION_GROUND_TRUTH = auto()  # Protocol-native liquidation events
    WALLET_IDENTITY = auto()        # Who was liquidated / liquidator
    POSITION_SIDE = auto()          # LONG/SHORT (not inferred)
    LIQUIDATION_METHOD = auto()     # market vs backstop
    BLOCK_ORDERING = auto()         # Deterministic event ordering

    # Binance capabilities
    TRADE_PRICE = auto()            # Individual trade prices
    TRADE_VOLUME = auto()           # Individual trade volumes
    TRADE_DIRECTION = auto()        # is_buyer_maker (taker side)
    ORDER_BOOK_DEPTH = auto()       # L2 order book
    OHLC_AGGREGATION = auto()       # Candles from trades
    MARK_PRICE = auto()             # Exchange mark price
    FUNDING_RATE = auto()           # Perpetual funding


# ============================================================================
# SOURCE AUTHORITY MAP (CONSTITUTIONAL - DO NOT MODIFY)
# ============================================================================

HL_NODE_PROVIDES: FrozenSet[DataCapability] = frozenset({
    DataCapability.ORACLE_PRICE,
    DataCapability.LIQUIDATION_GROUND_TRUTH,
    DataCapability.WALLET_IDENTITY,
    DataCapability.POSITION_SIDE,
    DataCapability.LIQUIDATION_METHOD,
    DataCapability.BLOCK_ORDERING,
})

HL_NODE_CANNOT_PROVIDE: FrozenSet[DataCapability] = frozenset({
    DataCapability.TRADE_PRICE,         # No trade events emitted
    DataCapability.TRADE_VOLUME,        # No volume data
    DataCapability.TRADE_DIRECTION,     # No taker/maker info
    DataCapability.ORDER_BOOK_DEPTH,    # No order book
    DataCapability.OHLC_AGGREGATION,    # Cannot build candles
})

BINANCE_PROVIDES: FrozenSet[DataCapability] = frozenset({
    DataCapability.TRADE_PRICE,
    DataCapability.TRADE_VOLUME,
    DataCapability.TRADE_DIRECTION,
    DataCapability.ORDER_BOOK_DEPTH,
    DataCapability.OHLC_AGGREGATION,
    DataCapability.MARK_PRICE,
    DataCapability.FUNDING_RATE,
})

BINANCE_CANNOT_PROVIDE: FrozenSet[DataCapability] = frozenset({
    DataCapability.WALLET_IDENTITY,     # Privacy protected
    DataCapability.POSITION_SIDE,       # Must infer from order side
    DataCapability.LIQUIDATION_METHOD,  # Internal detail
    DataCapability.ORACLE_PRICE,        # Exchange internal
    DataCapability.BLOCK_ORDERING,      # No blockchain
})


# ============================================================================
# CALCULATOR SOURCE REQUIREMENTS (ENFORCED)
# ============================================================================

class CalculatorContract:
    """Defines what a calculator requires and from which source."""

    def __init__(
        self,
        name: str,
        required_capabilities: FrozenSet[DataCapability],
        required_source: DataSource,
        fallback_source: DataSource = None,
        description: str = "",
    ):
        self.name = name
        self.required_capabilities = required_capabilities
        self.required_source = required_source
        self.fallback_source = fallback_source
        self.description = description

    def is_satisfied_by(self, source: DataSource) -> bool:
        """Check if source can satisfy requirements."""
        if source == DataSource.HL_NODE:
            available = HL_NODE_PROVIDES
        elif source == DataSource.BINANCE:
            available = BINANCE_PROVIDES
        else:
            return False

        return self.required_capabilities.issubset(available)


# Define calculator contracts
VWAP_CONTRACT = CalculatorContract(
    name="VWAP",
    required_capabilities=frozenset({
        DataCapability.TRADE_PRICE,
        DataCapability.TRADE_VOLUME,
    }),
    required_source=DataSource.BINANCE,
    fallback_source=None,  # NO FALLBACK - Binance required
    description="Volume-weighted average price requires trade volume data. "
                "HL node does not emit trades. IMPOSSIBLE to compute from HL."
)

ATR_CONTRACT = CalculatorContract(
    name="ATR",
    required_capabilities=frozenset({
        DataCapability.TRADE_PRICE,
        DataCapability.OHLC_AGGREGATION,
    }),
    required_source=DataSource.BINANCE,
    fallback_source=None,  # NO FALLBACK - Binance required
    description="Average True Range requires OHLC from trade aggregation. "
                "HL oracle prices lack intra-block volatility. IMPOSSIBLE from HL."
)

ORDERFLOW_CONTRACT = CalculatorContract(
    name="Orderflow",
    required_capabilities=frozenset({
        DataCapability.TRADE_DIRECTION,
        DataCapability.TRADE_VOLUME,
    }),
    required_source=DataSource.BINANCE,
    fallback_source=None,  # NO FALLBACK - Binance required
    description="Orderflow imbalance requires taker direction (is_buyer_maker). "
                "HL node does not emit trade direction. IMPOSSIBLE from HL."
)

LIQUIDATION_ZSCORE_CONTRACT = CalculatorContract(
    name="Liquidation Z-Score",
    required_capabilities=frozenset({
        DataCapability.LIQUIDATION_GROUND_TRUTH,
    }),
    required_source=DataSource.HL_NODE,  # HL preferred
    fallback_source=DataSource.BINANCE,   # Binance acceptable fallback
    description="Liquidation intensity from event stream. "
                "HL provides ground truth; Binance provides exchange-reported events."
)

PROXIMITY_CONTRACT = CalculatorContract(
    name="Position Proximity",
    required_capabilities=frozenset({
        DataCapability.WALLET_IDENTITY,
        DataCapability.POSITION_SIDE,
    }),
    required_source=DataSource.HL_NODE,
    fallback_source=None,  # NO FALLBACK - HL required
    description="Position-at-risk detection requires wallet identity and position data. "
                "Binance cannot provide account-level information. IMPOSSIBLE from Binance."
)

ABSORPTION_CONTRACT = CalculatorContract(
    name="Absorption Analysis",
    required_capabilities=frozenset({
        DataCapability.ORDER_BOOK_DEPTH,
    }),
    required_source=DataSource.BINANCE,
    fallback_source=None,  # NO FALLBACK - Binance required
    description="Absorption analysis requires order book depth. "
                "HL node does not provide order book data. IMPOSSIBLE from HL."
)


# All calculator contracts for iteration
ALL_CONTRACTS = [
    VWAP_CONTRACT,
    ATR_CONTRACT,
    ORDERFLOW_CONTRACT,
    LIQUIDATION_ZSCORE_CONTRACT,
    PROXIMITY_CONTRACT,
    ABSORPTION_CONTRACT,
]


# ============================================================================
# SYMBOL NAMESPACE RULES (DO NOT MERGE)
# ============================================================================

"""
SYMBOL NAMESPACE CONTRACT:

HL symbols:      BTC, ETH, SOL, DOGE, XRP, HYPE, etc.
Binance symbols: BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, etc.

RULES:
1. Do NOT auto-merge or alias these namespaces
2. Do NOT normalize symbols to force calculator reuse
3. It is VALID and CORRECT for:
   - BTCUSDT → full regime classification (has Binance calculators)
   - BTC → HL-only logic (price + liquidations, NO regime)

RATIONALE:
- HL symbol "BTC" has HL price and HL liquidation data
- Binance symbol "BTCUSDT" has Binance trades and calculators
- These are DIFFERENT information contexts, not the same asset in different formats
"""

def is_hl_symbol(symbol: str) -> bool:
    """Check if symbol is in HL format (no suffix)."""
    return not symbol.endswith('USDT') and not symbol.endswith('USD')

def is_binance_symbol(symbol: str) -> bool:
    """Check if symbol is in Binance format (with USDT suffix)."""
    return symbol.endswith('USDT')

def get_hl_symbol(binance_symbol: str) -> str:
    """Convert Binance symbol to HL format. Use for HL data lookup only."""
    if binance_symbol.endswith('USDT'):
        return binance_symbol[:-4]
    return binance_symbol

def get_binance_symbol(hl_symbol: str) -> str:
    """Convert HL symbol to Binance format. Use for Binance data lookup only."""
    if not hl_symbol.endswith('USDT'):
        return f"{hl_symbol}USDT"
    return hl_symbol


# ============================================================================
# BLOCKING REASONS (EXPLICIT)
# ============================================================================

class BlockReason(Enum):
    """Why a component is blocked."""
    BINANCE_DISCONNECTED = "Binance WebSocket not connected"
    BINANCE_NO_TRADES = "No Binance trade data received for symbol"
    HL_DISCONNECTED = "HL Node gRPC not connected"
    HL_NO_LIQUIDATIONS = "No HL liquidation data received"
    PSM_NOT_ACTIVE = "PositionStateManager not parsing abci_state"
    WARM_UP_INCOMPLETE = "Calculator warm-up period not complete"
    SYMBOL_NOT_SUPPORTED = "Symbol not in configured whitelist"
    ARCHITECTURALLY_IMPOSSIBLE = "Required data cannot exist from available sources"


def get_regime_block_reason(
    has_vwap: bool,
    has_atr: bool,
    has_orderflow: bool,
    has_liquidation_z: bool,
    binance_connected: bool,
) -> str:
    """Get explicit reason why regime classification is blocked."""
    if not binance_connected:
        return BlockReason.BINANCE_DISCONNECTED.value

    missing = []
    if not has_vwap:
        missing.append("VWAP (requires Binance trades)")
    if not has_atr:
        missing.append("ATR (requires Binance OHLC)")
    if not has_orderflow:
        missing.append("Orderflow (requires Binance trade direction)")
    if not has_liquidation_z:
        missing.append("Liquidation Z-score")

    if missing:
        return f"Binance-required data missing: {', '.join(missing)}"

    return "Ready"


# ============================================================================
# COMPONENT STATUS (TRUTH TABLE)
# ============================================================================

"""
COMPONENT STATUS TRUTH TABLE

| Component          | Status   | Required Source | Reason if Blocked              |
|--------------------|----------|-----------------|--------------------------------|
| VWAP               | LIVE*    | Binance-only    | Binance WS disconnected        |
| ATR                | LIVE*    | Binance-only    | Binance WS or warm-up missing  |
| Orderflow          | LIVE*    | Binance-only    | Binance WS disconnected        |
| Liquidation Z      | LIVE     | HL (preferred)  | Both sources disconnected      |
| Regime Classifier  | LIVE*    | Binance-req     | Any Binance calculator missing |
| Proximity          | BLOCKED  | HL-only         | PSM not parsing abci_state     |
| Absorption         | LIVE*    | Binance-only    | Binance depth stream missing   |
| Liquidation Burst  | LIVE     | Multi-source    | Both sources disconnected      |

* = Requires Binance WebSocket connection

IMPOSSIBLE COMBINATIONS:
- VWAP from HL → Architecturally impossible (no trade volume)
- ATR from HL → Architecturally impossible (no OHLC)
- Orderflow from HL → Architecturally impossible (no trade direction)
- Proximity from Binance → Architecturally impossible (no wallet identity)
- Absorption from HL → Architecturally impossible (no order book)
"""
