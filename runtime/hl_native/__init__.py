"""
HL-Native Module

Contains decision logic that uses ONLY Hyperliquid node data.
No Binance. No regime. No approximations.
"""

from .decision_loop import (
    HLNativeDecisionLoop,
    Decision,
    LiquidationEvent,
    SideImbalanceMetric,
    DecisionRecord,
    get_hl_native_loop,
    reset_hl_native_loop,
)

from .adapter import (
    HLNativeAdapter,
    run_hl_native_loop,
)

__all__ = [
    'HLNativeDecisionLoop',
    'Decision',
    'LiquidationEvent',
    'SideImbalanceMetric',
    'DecisionRecord',
    'get_hl_native_loop',
    'reset_hl_native_loop',
    'HLNativeAdapter',
    'run_hl_native_loop',
]
