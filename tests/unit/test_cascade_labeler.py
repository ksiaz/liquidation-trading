"""
Unit tests for Cascade Labeler.

Tests mechanical event detection and wave structure.
"""

import os
import tempfile
import pytest

from runtime.logging.execution_db import ResearchDatabase
from analysis.cascade_labeler import CascadeLabeler, LabeledCascade, WaveLabel
from analysis.wave_detector import WaveDetector, DetectedWave, WaveStructure


class TestWaveDetector:
    """Test wave detection logic."""

    @pytest.fixture
    def detector(self):
        """Create wave detector with default settings."""
        return WaveDetector()

    def test_empty_liquidations_returns_empty_structure(self, detector):
        """Empty input returns empty wave structure."""
        result = detector.detect_waves([])

        assert result.total_waves == 0
        assert result.waves == tuple()
        assert result.total_duration_ns == 0
        assert result.avg_inter_wave_gap_ns is None

    def test_single_liquidation_is_one_wave(self, detector):
        """Single liquidation is counted as one wave."""
        liqs = [{'detected_ts': 1000000000000}]
        result = detector.detect_waves(liqs)

        assert result.total_waves == 1
        assert len(result.waves) == 1
        assert result.waves[0].liquidation_count == 1

    def test_consecutive_liquidations_same_wave(self, detector):
        """Liquidations within gap threshold are same wave."""
        # 3 liquidations, 10 seconds apart each
        liqs = [
            {'detected_ts': 1000000000000},
            {'detected_ts': 1010000000000},  # +10s
            {'detected_ts': 1020000000000},  # +10s
        ]
        result = detector.detect_waves(liqs)

        assert result.total_waves == 1
        assert result.waves[0].liquidation_count == 3

    def test_gap_creates_new_wave(self, detector):
        """Gap > threshold creates new wave."""
        # 2 liquidations, 60 seconds apart (> 30s default)
        liqs = [
            {'detected_ts': 1000000000000},
            {'detected_ts': 1060000000000},  # +60s
        ]
        result = detector.detect_waves(liqs)

        assert result.total_waves == 2
        assert result.waves[0].liquidation_count == 1
        assert result.waves[1].liquidation_count == 1

    def test_mixed_waves_detected_correctly(self, detector):
        """Complex pattern with multiple waves detected."""
        # Pattern: 2 liqs, 40s gap, 3 liqs, 50s gap, 1 liq
        liqs = [
            {'detected_ts': 1000000000000},       # Wave 1
            {'detected_ts': 1005000000000},       # Wave 1 (+5s)
            {'detected_ts': 1045000000000},       # Wave 2 (+40s gap)
            {'detected_ts': 1050000000000},       # Wave 2 (+5s)
            {'detected_ts': 1055000000000},       # Wave 2 (+5s)
            {'detected_ts': 1105000000000},       # Wave 3 (+50s gap)
        ]
        result = detector.detect_waves(liqs)

        assert result.total_waves == 3
        assert result.waves[0].liquidation_count == 2
        assert result.waves[1].liquidation_count == 3
        assert result.waves[2].liquidation_count == 1

    def test_wave_numbers_are_sequential(self, detector):
        """Wave numbers start at 1 and are sequential."""
        liqs = [
            {'detected_ts': 1000000000000},
            {'detected_ts': 1060000000000},  # +60s
            {'detected_ts': 1120000000000},  # +60s
        ]
        result = detector.detect_waves(liqs)

        wave_nums = [w.wave_num for w in result.waves]
        assert wave_nums == [1, 2, 3]

    def test_largest_wave_detected(self, detector):
        """Largest wave number is correctly identified."""
        liqs = [
            {'detected_ts': 1000000000000},       # Wave 1: 1 liq
            {'detected_ts': 1060000000000},       # Wave 2: 5 liqs
            {'detected_ts': 1065000000000},
            {'detected_ts': 1070000000000},
            {'detected_ts': 1075000000000},
            {'detected_ts': 1080000000000},
            {'detected_ts': 1140000000000},       # Wave 3: 2 liqs
            {'detected_ts': 1145000000000},
        ]
        result = detector.detect_waves(liqs)

        assert result.largest_wave_num == 2

    def test_custom_wave_gap(self):
        """Custom wave gap threshold works."""
        detector = WaveDetector(wave_gap_ns=10_000_000_000)  # 10 seconds

        liqs = [
            {'detected_ts': 1000000000000},
            {'detected_ts': 1015000000000},  # +15s (> 10s gap)
        ]
        result = detector.detect_waves(liqs)

        assert result.total_waves == 2

    def test_exhaustion_check(self, detector):
        """Exhaustion detection works correctly."""
        liqs = [
            {'detected_ts': 1000000000000},
            {'detected_ts': 1005000000000},
        ]
        result = detector.detect_waves(liqs)

        # Current time far in future
        current_ts = 1200000000000  # +200s from last
        assert detector.is_exhausted(result, current_ts) is True

        # Current time close to last
        current_ts = 1010000000000  # +5s from last
        assert detector.is_exhausted(result, current_ts) is False


class TestCascadeLabeler:
    """Test cascade labeling logic."""

    @pytest.fixture
    def db(self):
        """Create temporary database."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        yield db
        db.close()
        os.unlink(path)

    @pytest.fixture
    def labeler(self, db):
        """Create labeler with database."""
        return CascadeLabeler(db)

    def test_no_data_returns_empty(self, labeler):
        """Empty database returns no cascades."""
        result = labeler.label_all(
            start_ts=1000000000000,
            end_ts=2000000000000
        )
        assert result == []

    def test_outcome_classification_reversal(self, labeler):
        """Reversal outcome correctly classified."""
        outcome = labeler._calculate_outcome(
            price_start="100.0",
            price_end="90.0",    # Dropped
            price_5min="95.0"    # Recovered (reversal)
        )
        assert outcome == "REVERSAL"

    def test_outcome_classification_continuation(self, labeler):
        """Continuation outcome correctly classified."""
        outcome = labeler._calculate_outcome(
            price_start="100.0",
            price_end="90.0",    # Dropped
            price_5min="85.0"    # Continued down
        )
        assert outcome == "CONTINUATION"

    def test_outcome_classification_neutral(self, labeler):
        """Neutral outcome correctly classified."""
        outcome = labeler._calculate_outcome(
            price_start="100.0",
            price_end="90.0",    # Dropped
            price_5min="90.1"    # Barely moved
        )
        assert outcome == "NEUTRAL"

    def test_outcome_missing_price_returns_none(self, labeler):
        """Missing price returns None outcome."""
        outcome = labeler._calculate_outcome(
            price_start="100.0",
            price_end="90.0",
            price_5min=None
        )
        assert outcome is None

    def test_statistics_empty_cascades(self, labeler):
        """Statistics for empty cascade list."""
        stats = labeler.get_statistics([])

        assert stats['total_cascades'] == 0
        assert stats['by_coin'] == {}
        assert stats['by_outcome'] == {}


class TestLabeledCascadeDataclass:
    """Test LabeledCascade immutability."""

    def test_cascade_is_frozen(self):
        """LabeledCascade is immutable."""
        cascade = LabeledCascade(
            cascade_id=1,
            coin="BTC",
            start_ts=1000000000000,
            end_ts=1060000000000,
            oi_drop_pct="15.0",
            liquidation_count=5,
            price_at_start="95000",
            price_at_end="90000",
            price_5min_after="92000",
            wave_count=3,
            waves=tuple(),
            outcome="REVERSAL"
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            cascade.coin = "ETH"

    def test_wave_label_is_frozen(self):
        """WaveLabel is immutable."""
        wave = WaveLabel(
            wave_num=1,
            start_ts=1000000000000,
            end_ts=1030000000000,
            liquidation_count=3,
            oi_drop_pct=None
        )

        with pytest.raises(Exception):
            wave.wave_num = 2


class TestWaveStructureDataclass:
    """Test WaveStructure immutability."""

    def test_wave_structure_is_frozen(self):
        """WaveStructure is immutable."""
        wave = DetectedWave(
            wave_num=1,
            start_ts=1000000000000,
            end_ts=1030000000000,
            liquidation_count=3,
            total_value=100000.0
        )
        structure = WaveStructure(
            total_waves=1,
            waves=(wave,),
            total_duration_ns=30000000000,
            avg_inter_wave_gap_ns=None,
            largest_wave_num=1
        )

        with pytest.raises(Exception):
            structure.total_waves = 5
