"""
Event Sequencing Validator.

Tests HLP25 Part 9 hypothesis:
"The sequence of conditions matters, not just their presence."

Ideal Sequence (from HLP25):
1. OI SPIKE         → Market is positioned
2. FUNDING SKEW     → Imbalance confirmed
3. DEPTH ASYMMETRY  → Liquidity withdrawing
4. CASCADE TRIGGER  → Liquidations begin
5. WAVE 1-2         → Initial liquidations execute
6. ABSORPTION       → Entry point
7. EXHAUSTION       → Cascade complete
8. REVERSAL         → Price recovers

Validation criteria:
- Cascades following sequence have better outcomes
- Entry at step 6 (absorption) outperforms entry at step 4 (trigger)
"""

from typing import List, Any, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum, auto

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


class CascadePhase(Enum):
    """Phases of a liquidation cascade."""
    SETUP = auto()       # OI spike, funding skew building
    TRIGGER = auto()     # Cascade begins
    WAVE_1_2 = auto()    # Initial liquidations
    ABSORPTION = auto()  # Exhaustion signals appear
    RECOVERY = auto()    # Price reversal


@dataclass(frozen=True)
class SequenceEvent:
    """An event in the cascade sequence."""
    phase: CascadePhase
    timestamp: int
    description: str


@dataclass(frozen=True)
class CascadeSequence:
    """Complete sequence analysis for a cascade."""
    cascade_id: int
    coin: str
    events: tuple  # Tuple of SequenceEvent
    followed_ideal: bool  # Whether sequence matched ideal pattern
    entry_phase: Optional[CascadePhase]  # Phase when theoretical entry would occur
    outcome: Optional[str]


class SequencingValidator:
    """Validates event sequencing hypothesis from HLP25 Part 9.

    Tests whether following the ideal sequence produces better outcomes.
    """

    def __init__(
        self,
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            min_sample_size: Minimum cascades for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "Event Sequencing (HLP25 Part 9)"

    def validate(self, cascades: List[Any]) -> ValidationResult:
        """Validate sequencing hypothesis.

        Uses wave structure as proxy for sequence phase:
        - Wave 1-2 = TRIGGER/WAVE_1_2 phase
        - Wave 3+ = ABSORPTION phase (later entry)

        Compares outcomes for early-wave vs late-wave cascades.

        Args:
            cascades: List of LabeledCascade objects

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        if len(cascades) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(cascades),
                reason=f"Need {self._min_sample_size} cascades, have {len(cascades)}"
            )

        # Categorize cascades by sequence characteristics
        # Using wave count as proxy for where in sequence we are
        early_entry = []  # 1-2 waves (entered at trigger)
        late_entry = []   # 3+ waves (entered after absorption)

        for cascade in cascades:
            if cascade.outcome is None:
                continue

            if cascade.wave_count <= 2:
                early_entry.append(cascade)
            else:
                late_entry.append(cascade)

        total = len(early_entry) + len(late_entry)

        if total < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total,
                reason="Insufficient cascades with outcomes"
            )

        # Calculate reversal rates (good outcome for counter-trend entry)
        early_reversal = sum(1 for c in early_entry if c.outcome == "REVERSAL")
        late_reversal = sum(1 for c in late_entry if c.outcome == "REVERSAL")

        early_rate = early_reversal / len(early_entry) if early_entry else 0
        late_rate = late_reversal / len(late_entry) if late_entry else 0

        # Calculate continuation rates (bad outcome for counter-trend entry)
        early_continuation = sum(1 for c in early_entry if c.outcome == "CONTINUATION")
        late_continuation = sum(1 for c in late_entry if c.outcome == "CONTINUATION")

        early_cont_rate = early_continuation / len(early_entry) if early_entry else 0
        late_cont_rate = late_continuation / len(late_entry) if late_entry else 0

        details = {
            'early_entry_count': len(early_entry),
            'late_entry_count': len(late_entry),
            'early_reversal_rate': round(early_rate, 3),
            'late_reversal_rate': round(late_rate, 3),
            'early_continuation_rate': round(early_cont_rate, 3),
            'late_continuation_rate': round(late_cont_rate, 3),
            'note': "Proxy validation using wave count - early=1-2 waves, late=3+ waves"
        }

        # Hypothesis validated if:
        # Late entry (after absorption) has higher reversal rate AND
        # Late entry has lower continuation rate
        reversal_improvement = late_rate - early_rate
        continuation_reduction = early_cont_rate - late_cont_rate

        details['reversal_improvement'] = round(reversal_improvement, 3)
        details['continuation_reduction'] = round(continuation_reduction, 3)

        # Need meaningful improvement in at least one metric
        if reversal_improvement > 0.1 or continuation_reduction > 0.1:
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=len(late_entry),
                threshold=3,  # Wave count threshold for "late" entry
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=len(late_entry),
                details=details
            )

    def analyze_sequence(
        self,
        cascade: Any,
        oi_data: Optional[List[Dict]] = None,
        funding_data: Optional[List[Dict]] = None,
        depth_data: Optional[List[Dict]] = None
    ) -> CascadeSequence:
        """Analyze sequence of events for a cascade.

        Full analysis requires OI, funding, and depth data.
        Falls back to wave-based analysis if data not available.

        Args:
            cascade: LabeledCascade object
            oi_data: Optional OI snapshots before/during cascade
            funding_data: Optional funding snapshots
            depth_data: Optional orderbook depth snapshots

        Returns:
            CascadeSequence with detected events
        """
        events = []

        # Use wave structure to infer sequence phases
        if cascade.wave_count >= 1:
            events.append(SequenceEvent(
                phase=CascadePhase.TRIGGER,
                timestamp=cascade.start_ts,
                description="Cascade triggered"
            ))

        if cascade.wave_count >= 2:
            events.append(SequenceEvent(
                phase=CascadePhase.WAVE_1_2,
                timestamp=cascade.start_ts,
                description="Initial waves executed"
            ))

        if cascade.wave_count >= 3:
            events.append(SequenceEvent(
                phase=CascadePhase.ABSORPTION,
                timestamp=cascade.end_ts,
                description="Absorption phase (wave 3+)"
            ))

        if cascade.outcome == "REVERSAL":
            events.append(SequenceEvent(
                phase=CascadePhase.RECOVERY,
                timestamp=cascade.end_ts,
                description="Price reversal"
            ))

        # Determine theoretical entry phase
        if cascade.wave_count >= 3:
            entry_phase = CascadePhase.ABSORPTION
        elif cascade.wave_count >= 1:
            entry_phase = CascadePhase.TRIGGER
        else:
            entry_phase = None

        # Check if sequence follows ideal pattern
        followed_ideal = (
            cascade.wave_count >= 3 and
            cascade.outcome == "REVERSAL"
        )

        return CascadeSequence(
            cascade_id=cascade.cascade_id,
            coin=cascade.coin,
            events=tuple(events),
            followed_ideal=followed_ideal,
            entry_phase=entry_phase,
            outcome=cascade.outcome
        )

    def get_ideal_entry_timing(
        self,
        cascade: Any
    ) -> Dict[str, Any]:
        """Determine ideal entry timing for a cascade.

        Based on HLP25: Enter at step 6 (absorption), not step 4 (trigger).

        Args:
            cascade: LabeledCascade object

        Returns:
            Dict with entry timing analysis
        """
        # Ideal: Enter after wave 2, before exhaustion
        if cascade.wave_count < 2:
            return {
                'ready': False,
                'reason': 'Insufficient waves - still in trigger phase',
                'recommended_action': 'WAIT'
            }

        if cascade.wave_count == 2:
            return {
                'ready': True,
                'reason': 'Wave 1-2 complete, absorption may begin',
                'recommended_action': 'PREPARE',
                'confidence': 'LOW'
            }

        if cascade.wave_count >= 3:
            if cascade.outcome == "REVERSAL":
                return {
                    'ready': True,
                    'reason': 'Absorption confirmed, reversal occurred',
                    'recommended_action': 'ENTRY_OPTIMAL',
                    'confidence': 'HIGH'
                }
            elif cascade.outcome == "CONTINUATION":
                return {
                    'ready': False,
                    'reason': 'Absorption failed, cascade continued',
                    'recommended_action': 'AVOID',
                    'confidence': 'HIGH'
                }
            else:
                return {
                    'ready': True,
                    'reason': 'Wave 3+ reached, absorption phase',
                    'recommended_action': 'ENTRY_POSSIBLE',
                    'confidence': 'MEDIUM'
                }

        return {
            'ready': False,
            'reason': 'Unknown state',
            'recommended_action': 'WAIT'
        }

    def calculate_sequence_statistics(
        self,
        cascades: List[Any]
    ) -> Dict[str, Any]:
        """Calculate statistics about cascade sequences.

        Args:
            cascades: List of LabeledCascade objects

        Returns:
            Dict with sequence statistics
        """
        if not cascades:
            return {
                'total_cascades': 0,
                'followed_ideal_count': 0,
                'followed_ideal_rate': 0.0
            }

        sequences = [self.analyze_sequence(c) for c in cascades]

        followed_ideal = sum(1 for s in sequences if s.followed_ideal)

        by_entry_phase = {}
        for seq in sequences:
            if seq.entry_phase:
                phase = seq.entry_phase.name
                by_entry_phase[phase] = by_entry_phase.get(phase, 0) + 1

        by_outcome_and_phase = {}
        for seq in sequences:
            if seq.entry_phase and seq.outcome:
                key = f"{seq.entry_phase.name}_{seq.outcome}"
                by_outcome_and_phase[key] = by_outcome_and_phase.get(key, 0) + 1

        return {
            'total_cascades': len(cascades),
            'followed_ideal_count': followed_ideal,
            'followed_ideal_rate': round(followed_ideal / len(cascades), 3),
            'by_entry_phase': by_entry_phase,
            'by_outcome_and_phase': by_outcome_and_phase
        }
