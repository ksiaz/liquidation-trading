"""
Data Integrity Validator

Read-only validation of stored market data.

SCOPE: Validation ONLY.
- No data modifications
- Report-only
- SELECT queries only

PRINCIPLE: Data correctness > completeness > performance
"""

import psycopg2
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class IntegrityIssue:
    """
    Report of data integrity issue.
    
    Fields:
        check_type: Type of check ("monotonicity", "gap", "duplicate", "schema")
        severity: Issue severity ("error", "warning")
        table: Table name where issue found
        message: Human-readable description
        timestamp: Related timestamp (optional)
        event_id: Related event ID (optional)
    """
    check_type: str
    severity: str
    table: str
    message: str
    timestamp: Optional[float] = None
    event_id: Optional[str] = None


class DataIntegrityValidator:
    """
    Read-only validation of stored data.
    
    RULE: No modifications.
    RULE: Report-only.
    RULE: SELECT queries only.
    """
    
    def __init__(self, connection_string: str):
        """
        Initialize validator.
        
        Args:
            connection_string: PostgreSQL connection string
        """
        self.conn_string = connection_string
        self.conn: Optional[psycopg2.extensions.connection] = None
    
    def connect(self) -> None:
        """Establish database connection."""
        self.conn = psycopg2.connect(self.conn_string)
    
    def check_timestamp_monotonicity(
        self,
        table: str,
        symbol: str
    ) -> List[IntegrityIssue]:
        """
        Check timestamps are monotonically increasing.
        
        RULE: Read-only check.
        
        Args:
            table: Table name to check
            symbol: Trading pair
            
        Returns:
            List of violations (empty if all OK)
        """
        issues = []
        
        sql = f"""
            SELECT 
                timestamp,
                event_id,
                LAG(timestamp) OVER (ORDER BY timestamp) as prev_ts
            FROM {table}
            WHERE symbol = %s
            ORDER BY timestamp
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (symbol,))
                
                for row in cur.fetchall():
                    timestamp, event_id, prev_ts = row
                    
                    if prev_ts is not None and timestamp < prev_ts:
                        issues.append(IntegrityIssue(
                            check_type="monotonicity",
                            severity="error",
                            table=table,
                            message=f"Backward time jump: {prev_ts} -> {timestamp}",
                            timestamp=timestamp,
                            event_id=event_id
                        ))
        except Exception as e:
            issues.append(IntegrityIssue(
                check_type="monotonicity",
                severity="error",
                table=table,
                message=f"Check failed: {e}"
            ))
        
        return issues
    
    def check_missing_intervals(
        self,
        table: str,
        symbol: str,
        max_gap_seconds: float
    ) -> List[IntegrityIssue]:
        """
        Detect gaps larger than expected.
        
        Args:
            table: Table name
            symbol: Trading pair
            max_gap_seconds: Maximum acceptable gap
            
        Returns:
            List of gap reports
        """
        issues = []
        
        sql = f"""
            SELECT 
                timestamp,
                LEAD(timestamp) OVER (ORDER BY timestamp) as next_ts
            FROM {table}
            WHERE symbol = %s
            ORDER BY timestamp
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (symbol,))
                
                for row in cur.fetchall():
                    timestamp, next_ts = row
                    
                    if next_ts is not None:
                        gap = next_ts - timestamp
                        if gap > max_gap_seconds:
                            issues.append(IntegrityIssue(
                                check_type="gap",
                                severity="warning",
                                table=table,
                                message=f"Gap of {gap:.1f}s detected ({timestamp} -> {next_ts})",
                                timestamp=timestamp
                            ))
        except Exception as e:
            issues.append(IntegrityIssue(
                check_type="gap",
                severity="error",
                table=table,
                message=f"Check failed: {e}"
            ))
        
        return issues
    
    def check_duplicates(
        self,
        table: str,
        symbol: str
    ) -> List[IntegrityIssue]:
        """
        Find duplicate events.
        
        Args:
            table: Table name
            symbol: Trading pair
            
        Returns:
            List of duplicate reports
        """
        issues = []
        
        # Check UUID duplicates
        sql_uuid = f"""
            SELECT event_id, COUNT(*) as cnt
            FROM {table}
            WHERE symbol = %s
            GROUP BY event_id
            HAVING COUNT(*) > 1
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql_uuid, (symbol,))
                
                for row in cur.fetchall():
                    event_id, count = row
                    issues.append(IntegrityIssue(
                        check_type="duplicate",
                        severity="error",
                        table=table,
                        message=f"Duplicate event_id: {event_id} ({count} occurrences)",
                        event_id=event_id
                    ))
        except Exception as e:
            issues.append(IntegrityIssue(
                check_type="duplicate",
                severity="error",
                table=table,
                message=f"UUID check failed: {e}"
            ))
        
        # Check timestamp duplicates (warning only - may be valid)
        sql_ts = f"""
            SELECT timestamp, COUNT(*) as cnt
            FROM {table}
            WHERE symbol = %s
            GROUP BY timestamp
            HAVING COUNT(*) > 1
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql_ts, (symbol,))
                
                for row in cur.fetchall():
                    timestamp, count = row
                    issues.append(IntegrityIssue(
                        check_type="duplicate",
                        severity="warning",
                        table=table,
                        message=f"Duplicate timestamp: {timestamp} ({count} events)",
                        timestamp=timestamp
                    ))
        except Exception as e:
            pass  # Already reported UUID check failure
        
        return issues
    
    def check_schema_consistency(
        self,
        table: str
    ) -> List[IntegrityIssue]:
        """
        Verify schema version consistency.
        
        Args:
            table: Table name
            
        Returns:
            List of schema violations
        """
        issues = []
        
        sql = f"""
            SELECT schema_version, COUNT(*) as cnt
            FROM {table}
            GROUP BY schema_version
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql)
                
                for row in cur.fetchall():
                    version, count = row
                    if version != 1:
                        issues.append(IntegrityIssue(
                            check_type="schema",
                            severity="error",
                            table=table,
                            message=f"Unexpected schema_version: {version} ({count} rows)"
                        ))
        except Exception as e:
            issues.append(IntegrityIssue(
                check_type="schema",
                severity="error",
                table=table,
                message=f"Schema check failed: {e}"
            ))
        
        return issues
    
    def run_full_validation(
        self,
        symbol: str = "BTCUSDT",
        max_gap_seconds: float = 60.0
    ) -> dict:
        """
        Run all validation checks.
        
        Args:
            symbol: Trading pair to validate
            max_gap_seconds: Maximum acceptable time gap
            
        Returns:
            Complete integrity report
        """
        report = {
            'symbol': symbol,
            'tables_checked': [],
            'total_issues': 0,
            'issues_by_severity': {'error': 0, 'warning': 0},
            'issues_by_type': {},
            'issues': []
        }
        
        tables = [
            'orderbook_events',
            'trade_events',
            'liquidation_events',
            'candle_events'
        ]
        
        for table in tables:
            report['tables_checked'].append(table)
            
            # Run all checks
            issues = []
            issues.extend(self.check_timestamp_monotonicity(table, symbol))
            issues.extend(self.check_missing_intervals(table, symbol, max_gap_seconds))
            issues.extend(self.check_duplicates(table, symbol))
            issues.extend(self.check_schema_consistency(table))
            
            # Add to report
            for issue in issues:
                report['issues'].append(issue)
                report['issues_by_severity'][issue.severity] += 1
                
                if issue.check_type not in report['issues_by_type']:
                    report['issues_by_type'][issue.check_type] = 0
                report['issues_by_type'][issue.check_type] += 1
        
        report['total_issues'] = len(report['issues'])
        
        return report
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
