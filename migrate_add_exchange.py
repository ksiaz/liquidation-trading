"""
Add exchange column to liquidations table for multi-exchange support
"""
from database import DatabaseManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add exchange column to liquidations table."""
    db = DatabaseManager()
    
    try:
        # Check if column already exists
        db.cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='liquidations' AND column_name='exchange'
        """)
        
        if db.cursor.fetchone():
            logger.info("Exchange column already exists")
            return
        
        logger.info("Adding exchange column to liquidations table...")
        
        # Add exchange column
        db.cursor.execute("""
            ALTER TABLE liquidations 
            ADD COLUMN exchange VARCHAR(20) DEFAULT 'BINANCE'
        """)
        
        # Add index for better performance
        db.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_liquidations_exchange 
            ON liquidations(exchange)
        """)
        
        # Add composite index for exchange + symbol queries
        db.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_liquidations_exchange_symbol 
            ON liquidations(exchange, symbol)
        """)
        
        db.conn.commit()
        logger.info("✅ Migration complete! Exchange column added successfully")
        
        # Show current schema
        db.cursor.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns 
            WHERE table_name='liquidations'
            ORDER BY ordinal_position
        """)
        
        logger.info("\nUpdated liquidations table schema:")
        for row in db.cursor.fetchall():
            logger.info(f"  {row[0]}: {row[1]} (default: {row[2]})")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.conn.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("="*60)
    print("DATABASE MIGRATION: Add Exchange Support")
    print("="*60)
    print()
    migrate()
    print()
    print("="*60)
    print("Migration complete! You can now run hyperliquid_monitor.py")
    print("="*60)
