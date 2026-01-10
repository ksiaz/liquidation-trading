"""
Regime Classifier

Implements regime classification logic with exact conditions.

RULES:
- Check SIDEWAYS first, then EXPANSION
- ALL conditions must be met for regime activation
- If neither qualifies → DISABLED
- NULL metrics → DISABLED
- Regime is a GATE, not a signal
"""

from typing import List, Tuple, Dict, Optional, Any
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.metrics.types import DerivedMetrics
from .types import RegimeType, RegimeState, RegimeTransition


class RegimeClassifier:
    """
    Global regime classifier.
    
    INVARIANT: Regime is a GATE, not a signal.
    INVARIANT: ALL conditions must be met for regime activation.
    INVARIANT: DISABLED if neither SIDEWAYS nor EXPANSION qualify.
    """
    
    # SIDEWAYS thresholds
    SIDEWAYS_PRICE_VWAP_MULTIPLIER = 1.25
    SIDEWAYS_ATR_RATIO_MAX = 0.80
    SIDEWAYS_VOLUME_IMBALANCE_MAX = 0.18
    SIDEWAYS_LIQ_ZSCORE_MAX = 2.0
    
    # EXPANSION thresholds
    EXPANSION_PRICE_VWAP_MULTIPLIER = 1.5
    EXPANSION_ATR_RATIO_MIN = 1.0
    EXPANSION_VOLUME_IMBALANCE_MIN = 0.35
    EXPANSION_LIQ_ZSCORE_MIN = 2.5
    EXPANSION_OI_DELTA_MIN = 1000.0  # Contracts - can be tuned
    
    def __init__(self):
        """Initialize regime classifier."""
        self.current_regime: RegimeType = RegimeType.DISABLED
        self.transition_history: List[RegimeTransition] = []
    
    def classify(
        self,
        current_price: float,
        metrics: DerivedMetrics,
        current_time: float
    ) -> RegimeState:
        """
        Classify current regime based on metrics.
        
        Args:
            current_price: Current mid-price
            metrics: Derived metrics
            current_time: Current timestamp
        
        Returns:
            RegimeState with classification result
        
        RULE: Check SIDEWAYS first, then EXPANSION, else DISABLED.
        RULE: ALL conditions must be met.
        RULE: If any required metric is None, regime is DISABLED.
        """
        # Check SIDEWAYS first
        sideways_met, sideways_details = self._check_sideways(current_price, metrics)
        
        if sideways_met:
            regime = RegimeType.SIDEWAYS
            condition_details = sideways_details
        else:
            # Check EXPANSION
            expansion_met, expansion_details = self._check_expansion(current_price, metrics)
            
            if expansion_met:
                regime = RegimeType.EXPANSION
                condition_details = expansion_details
            else:
                # Neither qualifies → DISABLED
                regime = RegimeType.DISABLED
                condition_details = {
                    'price_vwap_distance': None,
                    'atr_ratio': None,
                    'volume_imbalance': None,
                    'liquidation_zscore': metrics.liquidation_zscore,
                    'oi_delta': metrics.oi_delta,
                    'condition_1_met': False,
                    'condition_2_met': False,
                    'condition_3_met': False,
                    'condition_4_met': False,
                }
        
        # Create regime state
        regime_state = RegimeState(
            regime=regime,
            timestamp=current_time,
            price_vwap_distance=condition_details.get('price_vwap_distance'),
            atr_ratio=condition_details.get('atr_ratio'),
            volume_imbalance=condition_details.get('volume_imbalance'),
            liquidation_zscore=condition_details.get('liquidation_zscore'),
            oi_delta=condition_details.get('oi_delta'),
            condition_1_met=condition_details['condition_1_met'],
            condition_2_met=condition_details['condition_2_met'],
            condition_3_met=condition_details['condition_3_met'],
            condition_4_met=condition_details['condition_4_met'],
        )
        
        # Log transition if regime changed
        if regime != self.current_regime:
            reason = self._determine_transition_reason(regime, condition_details)
            self._log_transition(self.current_regime, regime, current_time, reason)
            self.current_regime = regime
        
        return regime_state
    
    def _check_sideways(
        self,
        price: float,
        metrics: DerivedMetrics
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if SIDEWAYS conditions met.
        
        Returns:
            (all_met, condition_details)
        
        RULE: ALL 4 conditions must be True.
        
        Conditions:
        1. abs(price - VWAP) ≤ 1.25 × ATR(5m)
        2. ATR(5m) / ATR(30m) < 0.80
        3. abs(buy_30s - sell_30s) / total_30s < 0.18
        4. liquidation_zscore < 2.0
        """
        # Check required metrics available
        if (metrics.vwap is None or
            metrics.atr_5m is None or
            metrics.atr_30m is None or
            metrics.taker_buy_volume_30s is None or
            metrics.taker_sell_volume_30s is None or
            metrics.liquidation_zscore is None):
            return False, {
                'price_vwap_distance': None,
                'atr_ratio': None,
                'volume_imbalance': None,
                'liquidation_zscore': metrics.liquidation_zscore,
                'oi_delta': metrics.oi_delta,
                'condition_1_met': False,
                'condition_2_met': False,
                'condition_3_met': False,
                'condition_4_met': False,
            }
        
        # Calculate condition values
        price_vwap_distance = abs(price - metrics.vwap)
        atr_ratio = metrics.atr_5m / metrics.atr_30m if metrics.atr_30m > 0 else 999.0
        
        total_volume_30s = metrics.taker_buy_volume_30s + metrics.taker_sell_volume_30s
        if total_volume_30s > 0:
            volume_imbalance = abs(metrics.taker_buy_volume_30s - metrics.taker_sell_volume_30s) / total_volume_30s
        else:
            volume_imbalance = 0.0
        
        # Check each condition
        condition_1 = price_vwap_distance <= (self.SIDEWAYS_PRICE_VWAP_MULTIPLIER * metrics.atr_5m)
        condition_2 = atr_ratio < self.SIDEWAYS_ATR_RATIO_MAX
        condition_3 = volume_imbalance < self.SIDEWAYS_VOLUME_IMBALANCE_MAX
        condition_4 = metrics.liquidation_zscore < self.SIDEWAYS_LIQ_ZSCORE_MAX
        
        all_met = condition_1 and condition_2 and condition_3 and condition_4
        
        return all_met, {
            'price_vwap_distance': price_vwap_distance,
            'atr_ratio': atr_ratio,
            'volume_imbalance': volume_imbalance,
            'liquidation_zscore': metrics.liquidation_zscore,
            'oi_delta': metrics.oi_delta,
            'condition_1_met': condition_1,
            'condition_2_met': condition_2,
            'condition_3_met': condition_3,
            'condition_4_met': condition_4,
        }
    
    def _check_expansion(
        self,
        price: float,
        metrics: DerivedMetrics
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if EXPANSION conditions met.
        
        Returns:
            (all_met, condition_details)
        
        RULE: ALL 4 conditions must be True.
        RULE: Condition 4 is (liq_zscore >= 2.5 OR oi_delta > threshold).
        
        Conditions:
        1. abs(price - VWAP) ≥ 1.5 × ATR(5m)
        2. ATR(5m) / ATR(30m) ≥ 1.0
        3. abs(buy_30s - sell_30s) / total_30s ≥ 0.35
        4. liquidation_zscore ≥ 2.5 OR oi_delta > threshold
        """
        # Check required metrics available
        if (metrics.vwap is None or
            metrics.atr_5m is None or
            metrics.atr_30m is None or
            metrics.taker_buy_volume_30s is None or
            metrics.taker_sell_volume_30s is None):
            return False, {
                'price_vwap_distance': None,
                'atr_ratio': None,
                'volume_imbalance': None,
                'liquidation_zscore': metrics.liquidation_zscore,
                'oi_delta': metrics.oi_delta,
                'condition_1_met': False,
                'condition_2_met': False,
                'condition_3_met': False,
                'condition_4_met': False,
            }
        
        # Calculate condition values
        price_vwap_distance = abs(price - metrics.vwap)
        atr_ratio = metrics.atr_5m / metrics.atr_30m if metrics.atr_30m > 0 else 999.0
        
        total_volume_30s = metrics.taker_buy_volume_30s + metrics.taker_sell_volume_30s
        if total_volume_30s > 0:
            volume_imbalance = abs(metrics.taker_buy_volume_30s - metrics.taker_sell_volume_30s) / total_volume_30s
        else:
            volume_imbalance = 0.0
        
        # Check each condition
        condition_1 = price_vwap_distance >= (self.EXPANSION_PRICE_VWAP_MULTIPLIER * metrics.atr_5m)
        condition_2 = atr_ratio >= self.EXPANSION_ATR_RATIO_MIN
        condition_3 = volume_imbalance >= self.EXPANSION_VOLUME_IMBALANCE_MIN
        
        # Condition 4: liq_zscore >= 2.5 OR oi_delta > threshold
        # Allow None for either, but at least one must satisfy
        liq_condition = metrics.liquidation_zscore is not None and metrics.liquidation_zscore >= self.EXPANSION_LIQ_ZSCORE_MIN
        oi_condition = metrics.oi_delta is not None and metrics.oi_delta > self.EXPANSION_OI_DELTA_MIN
        condition_4 = liq_condition or oi_condition
        
        all_met = condition_1 and condition_2 and condition_3 and condition_4
        
        return all_met, {
            'price_vwap_distance': price_vwap_distance,
            'atr_ratio': atr_ratio,
            'volume_imbalance': volume_imbalance,
            'liquidation_zscore': metrics.liquidation_zscore,
            'oi_delta': metrics.oi_delta,
            'condition_1_met': condition_1,
            'condition_2_met': condition_2,
            'condition_3_met': condition_3,
            'condition_4_met': condition_4,
        }
    
    def _determine_transition_reason(
        self,
        new_regime: RegimeType,
        condition_details: Dict[str, Any]
    ) -> str:
        """
        Determine human-readable reason for regime transition.
        
        Args:
            new_regime: New regime type
            condition_details: Condition evaluation details
        
        Returns:
            Human-readable reason string
        """
        if new_regime == RegimeType.SIDEWAYS:
            return "All SIDEWAYS conditions met"
        elif new_regime == RegimeType.EXPANSION:
            return "All EXPANSION conditions met"
        else:  # DISABLED
            # Determine which conditions failed
            failed = []
            if not condition_details['condition_1_met']:
                failed.append("price-VWAP distance")
            if not condition_details['condition_2_met']:
                failed.append("ATR ratio")
            if not condition_details['condition_3_met']:
                failed.append("volume imbalance")
            if not condition_details['condition_4_met']:
                failed.append("liquidation/OI")
            
            if failed:
                return f"Conditions failed: {', '.join(failed)}"
            else:
                return "Insufficient metrics"
    
    def _log_transition(
        self,
        from_regime: RegimeType,
        to_regime: RegimeType,
        timestamp: float,
        reason: str
    ) -> None:
        """
        Log regime transition.
        
        Args:
            from_regime: Previous regime
            to_regime: New regime
            timestamp: Timestamp of transition
            reason: Reason for transition
        """
        transition = RegimeTransition(
            timestamp=timestamp,
            from_regime=from_regime,
            to_regime=to_regime,
            reason=reason
        )
        self.transition_history.append(transition)
    
    def get_current_regime(self) -> RegimeType:
        """Get current regime type."""
        return self.current_regime
    
    def get_transition_history(self) -> List[RegimeTransition]:
        """Get regime transition history."""
        return self.transition_history
    
    def reset(self) -> None:
        """Reset classifier to initial state."""
        self.current_regime = RegimeType.DISABLED
        self.transition_history.clear()
