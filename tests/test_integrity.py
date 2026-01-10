"""
Unit Tests for Data Integrity Validator

Tests verify validation logic without actual database.

RULE: Mock database queries.
RULE: Test all check types.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock
sys.path.append('d:/liquidation-trading')

from data_pipeline.validation import DataIntegrityValidator, IntegrityIssue


class TestDataIntegrityValidator:
    """Test integrity validator."""
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_connection(self, mock_connect):
        """Validator connects to database."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        assert validator.conn == mock_conn
        mock_connect.assert_called_once()
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_check_monotonicity_no_issues(self, mock_connect):
        """Monotonicity check passes with ascending timestamps."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock ascending timestamps
        mock_cursor.fetchall.return_value = [
            (100.0, 'id1', None),     # First
            (200.0, 'id2', 100.0),    # OK
            (300.0, 'id3', 200.0),    # OK
        ]
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        issues = validator.check_timestamp_monotonicity('trade_events', 'BTCUSDT')
        
        # No issues
        assert len(issues) == 0
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_check_monotonicity_backward_jump(self, mock_connect):
        """Monotonicity check detects backward time jump."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock backward jump
        mock_cursor.fetchall.return_value = [
            (100.0, 'id1', None),
            (200.0, 'id2', 100.0),
            (150.0, 'id3', 200.0),  # BACKWARD!
        ]
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        issues = validator.check_timestamp_monotonicity('trade_events', 'BTCUSDT')
        
        # Should detect 1 issue
        assert len(issues) == 1
        assert issues[0].check_type == "monotonicity"
        assert issues[0].severity == "error"
        assert "Backward time jump" in issues[0].message
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_check_gaps_no_issues(self, mock_connect):
        """Gap check passes with small gaps."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Small gaps (< 60s)
        mock_cursor.fetchall.return_value = [
            (100.0, 110.0),   # 10s gap
            (110.0, 120.0),   # 10s gap
        ]
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        issues = validator.check_missing_intervals('trade_events', 'BTCUSDT', 60.0)
        
        assert len(issues) == 0
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_check_gaps_large_gap(self, mock_connect):
        """Gap check detects large gap."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Large gap (> 60s)
        mock_cursor.fetchall.return_value = [
            (100.0, 110.0),   # 10s gap
            (110.0, 300.0),   # 190s gap!
        ]
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        issues = validator.check_missing_intervals('trade_events', 'BTCUSDT', 60.0)
        
        assert len(issues) == 1
        assert issues[0].check_type == "gap"
        assert issues[0].severity == "warning"
        assert "190" in issues[0].message
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_check_duplicates_uuid(self, mock_connect):
        """Duplicate check detects UUID collisions."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # UUID duplicates
        mock_cursor.fetchall.side_effect = [
            [('duplicate-id', 3)],  # UUID check
            []                       # Timestamp check
        ]
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        issues = validator.check_duplicates('trade_events', 'BTCUSDT')
        
        assert len(issues) >= 1
        uuid_issues = [i for i in issues if 'event_id' in i.message]
        assert len(uuid_issues) == 1
        assert uuid_issues[0].check_type == "duplicate"
        assert uuid_issues[0].severity == "error"
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_check_schema_consistency_valid(self, mock_connect):
        """Schema check passes with version 1."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # All schema_version = 1
        mock_cursor.fetchall.return_value = [
            (1, 1000)
        ]
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        issues = validator.check_schema_consistency('trade_events')
        
        assert len(issues) == 0
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_check_schema_consistency_invalid(self, mock_connect):
        """Schema check detects unexpected version."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # schema_version = 2 (unexpected)
        mock_cursor.fetchall.return_value = [
            (1, 500),
            (2, 100)  # Unexpected!
        ]
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        issues = validator.check_schema_consistency('trade_events')
        
        assert len(issues) == 1
        assert issues[0].check_type == "schema"
        assert issues[0].severity == "error"
        assert "Unexpected schema_version: 2" in issues[0].message
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_full_validation_report(self, mock_connect):
        """Full validation generates complete report."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock empty results (no issues)
        mock_cursor.fetchall.return_value = []
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        validator = DataIntegrityValidator("postgresql://test")
        validator.connect()
        
        report = validator.run_full_validation("BTCUSDT")
        
        # Verify report structure
        assert report['symbol'] == "BTCUSDT"
        assert len(report['tables_checked']) == 4
        assert 'total_issues' in report
        assert 'issues_by_severity' in report
        assert 'issues' in report
    
    @patch('data_pipeline.validation.integrity.psycopg2.connect')
    def test_context_manager(self, mock_connect):
        """Validator works as context manager."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        
        with DataIntegrityValidator("postgresql://test") as validator:
            assert validator.conn == mock_conn
        
        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
