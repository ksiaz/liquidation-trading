"""
C2: Database Write Verification Primitive

RULE: Verify data is actually being written to PostgreSQL
RULE: Stop if any expected table has 0 rows
"""
import psycopg2
from typing import Dict


class DatabaseVerifier:
    """
    Verify database writes during capture.
    
    RULE: Execute SELECT COUNT queries
    RULE: Report failures immediately
    RULE: Stop if expected data is missing
    """
    
    def __init__(self, conn_string: str, symbol: str):
        """
        Initialize verifier.
        
        Args:
            conn_string: PostgreSQL connection string
            symbol: Trading pair being captured
        """
        self.conn_string = conn_string
        self.symbol = symbol
    
    def verify_writes(self, expected_tables: list = None) -> Dict[str, int]:
        """
        Verify data exists in database.
        
        Args:
            expected_tables: List of tables that MUST have data
                           (e.g., ['orderbook_events', 'trade_events'])
        
        Returns:
            Dictionary of table_name -> count
            
        Raises:
            RuntimeError if expected table has 0 rows
        """
        if expected_tables is None:
            expected_tables = []
        
        try:
            conn = psycopg2.connect(self.conn_string)
            cur = conn.cursor()
            
            # Count all event tables
            counts = {}
            
            tables = [
                'orderbook_events',
                'trade_events',
                'candle_events',
                'liquidation_events'
            ]
            
            print(f"\n{'='*60}")
            print(f"DATABASE VERIFICATION - {self.symbol}")
            print(f"{'='*60}")
            
            for table in tables:
                # Total count
                cur.execute(f"SELECT COUNT(*) FROM {table};")
                total = cur.fetchone()[0]
                
                # Special handling for global tables
                if table == 'liquidation_events':
                    cur.execute(f"SELECT COUNT(*) FROM {table};")
                else:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE symbol = %s;", (self.symbol,))
                
                symbol_count = cur.fetchone()[0]
                
                counts[table] = symbol_count
                
                # Print result
                label = f"{self.symbol}" if table != 'liquidation_events' else "GLOBAL"
                status = "✓" if symbol_count > 0 else "✗"
                print(f"{status} {table}: {symbol_count:,} ({label})")
                
                # Check if this table was expected to have data
                if table in expected_tables and symbol_count == 0:
                    cur.close()
                    conn.close()
                    raise RuntimeError(
                        f"VERIFICATION FAILED: {table} has 0 rows for {self.symbol}. "
                        f"Expected data but none found. STOPPING."
                    )
            
            print(f"{'='*60}\n")
            
            cur.close()
            conn.close()
            
            return counts
            
        except psycopg2.Error as e:
            raise RuntimeError(f"Database verification failed: {e}")
    
    def verify_recent_writes(self, max_age_seconds: int = 60) -> Dict[str, int]:
        """
        Verify recent writes (within last N seconds).
        
        Args:
            max_age_seconds: Maximum age of events to count
            
        Returns:
            Dictionary of table_name -> recent count
        """
        try:
            conn = psycopg2.connect(self.conn_string)
            cur = conn.cursor()
            
            counts = {}
            
            tables = [
                'orderbook_events',
                'trade_events',
                'candle_events',
                'liquidation_events'
            ]
            
            print(f"\n{'='*60}")
            print(f"RECENT WRITES VERIFICATION (last {max_age_seconds}s)")
            print(f"{'='*60}")
            
            for table in tables:
                if table == 'liquidation_events':
                    # Global check
                    cur.execute(f"""
                        SELECT COUNT(*) FROM {table} 
                        WHERE timestamp > extract(epoch from now()) - %s;
                    """, (max_age_seconds,))
                else:
                    # Symbol specific check
                    cur.execute(f"""
                        SELECT COUNT(*) FROM {table} 
                        WHERE symbol = %s 
                        AND timestamp > extract(epoch from now()) - %s;
                    """, (self.symbol, max_age_seconds))
                
                count = cur.fetchone()[0]
                counts[table] = count
                
                status = "✓" if count > 0 else "-"
                print(f"{status} {table}: {count:,} recent writes")
            
            print(f"{'='*60}\n")
            
            cur.close()
            conn.close()
            
            return counts
            
        except psycopg2.Error as e:
            raise RuntimeError(f"Recent writes verification failed: {e}")


def main():
    """Test verification function."""
    conn_string = "postgresql://postgres:postgres@localhost:5436/trading"
    
    verifier = DatabaseVerifier(conn_string, 'BTCUSDT')
    
    # Verify all data
    print("=== FULL DATABASE VERIFICATION ===")
    counts = verifier.verify_writes()
    
    # Verify recent writes
    print("\n=== RECENT WRITES (60s) ===")
    recent = verifier.verify_recent_writes(max_age_seconds=60)
    
    # Test expected tables check
    print("\n=== TESTING EXPECTED TABLES ===")
    try:
        # This should fail if orderbook_events is empty
        verifier.verify_writes(expected_tables=['orderbook_events'])
    except RuntimeError as e:
        print(f"Expected failure caught: {e}")


if __name__ == "__main__":
    main()
