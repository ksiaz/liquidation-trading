"""Mandate Arbitrator.

Implements deterministic mandate resolution per MANDATE_ARBITRATION_PROOFS.md.

Enforces:
- 13 proven theorems
- EXIT supremacy (Theorem 2.2)
- BLOCK prevents ENTRY (Theorem 2.3)
- Deterministic resolution (Theorem 3.1)
- Symbol-local independence (Theorem 5.1)
"""

from typing import Set, Dict, List
from .types import Mandate, Action, MandateType, ActionType


class MandateArbitrator:
    """Arbitrates mandates to produce single action per symbol.
    
    Properties:
    - Deterministic (Theorem 3.1)
    - Symbol-local (Theorem 5.1)
    - Always completes (Theorem 8.1)
    """
    
    def arbitrate(self, mandates: Set[Mandate]) -> Action:
        """Arbitrate mandates for a symbol (deterministic - Theorem 3.1).
        
        Args:
            mandates: Set of mandates for ONE symbol
            
        Returns:
            Exactly one action (Theorem 4.1)
            
        Raises:
            ValueError: If mandates from multiple symbols
        """
        if not mandates:
            # Empty set → NO_ACTION (completeness - Theorem 6.1)
            return Action(type=ActionType.NO_ACTION, symbol="")
        
        # Validate all mandates for same symbol (symbol-local - Theorem 5.1)
        symbols = {m.symbol for m in mandates}
        if len(symbols) > 1:
            raise ValueError(f"Mandates must be for single symbol, got: {symbols}")
        
        symbol = next(iter(symbols))
        
        # Step 1: EXIT supremacy (Theorem 2.2)
        exit_mandates = [m for m in mandates if m.type == MandateType.EXIT]
        if exit_mandates:
            # Use first EXIT mandate's strategy_id for tracing
            strategy_id = exit_mandates[0].strategy_id if hasattr(exit_mandates[0], 'strategy_id') else None
            return Action(type=ActionType.EXIT, symbol=symbol, strategy_id=strategy_id)
        
        # Step 2: Filter ENTRY and DCA_ADD if BLOCK present (Theorem 2.3)
        if any(m.type == MandateType.BLOCK for m in mandates):
            mandates = {m for m in mandates if m.type not in (MandateType.ENTRY, MandateType.DCA_ADD)}
        
        # Step 3: Group by type, select highest authority (Theorem 3.2)
        by_type: Dict[MandateType, Mandate] = {}
        for mandate in mandates:
            if mandate.type not in by_type:
                by_type[mandate.type] = mandate
            elif mandate.authority > by_type[mandate.type].authority:
                # Higher authority wins (deterministic tiebreaker)
                by_type[mandate.type] = mandate
        
        # Step 4: Apply hierarchy (Theorem 2.2)
        # Check in priority order: EXIT > REDUCE > ENTRY > DCA_ADD > HOLD
        # DCA_ADD and ENTRY are state-exclusive (DCA_ADD only valid when OPEN, ENTRY only when FLAT)
        for mandate_type in [
            MandateType.EXIT,    # Priority 5
            MandateType.REDUCE,  # Priority 3 (skip BLOCK=4, not actionable)
            MandateType.ENTRY,   # Priority 2
            MandateType.DCA_ADD, # DCA add (only valid when OPEN)
            MandateType.HOLD,    # Priority 1
        ]:
            if mandate_type in by_type:
                mandate = by_type[mandate_type]
                # Use from_mandate to preserve direction for ENTRY actions
                return Action.from_mandate(mandate)
        
        # If only BLOCK remains, it's not actionable
        if MandateType.BLOCK in by_type:
            return Action(type=ActionType.NO_ACTION, symbol=symbol)
        
        # No actionable mandates
        return Action(type=ActionType.NO_ACTION, symbol=symbol)
    
    def arbitrate_all(self, mandates: List[Mandate]) -> Dict[str, Action]:
        """Arbitrate mandates for all symbols (symbol-independent - Theorem 5.1).
        
        Args:
            mandates: List of all mandates
            
        Returns:
            Dict mapping symbol → action
        """
        # Group by symbol (symbol-local - Theorem 5.1)
        by_symbol: Dict[str, Set[Mandate]] = {}
        global_mandates: List[Mandate] = []  # symbol="*" applies to all
        for mandate in mandates:
            if mandate.symbol == "*":
                global_mandates.append(mandate)
            else:
                if mandate.symbol not in by_symbol:
                    by_symbol[mandate.symbol] = set()
                by_symbol[mandate.symbol].add(mandate)

        # Expand global mandates (e.g. BLOCK on "*") into every symbol group
        if global_mandates:
            for symbol in by_symbol:
                for gm in global_mandates:
                    # Create symbol-specific copy to satisfy single-symbol validation
                    by_symbol[symbol].add(Mandate(
                        symbol=symbol,
                        type=gm.type,
                        authority=gm.authority,
                        timestamp=gm.timestamp,
                    ))

        # Arbitrate each symbol independently (Theorem 5.1, 5.2)
        actions = {}
        for symbol, symbol_mandates in by_symbol.items():
            actions[symbol] = self.arbitrate(symbol_mandates)

        return actions
