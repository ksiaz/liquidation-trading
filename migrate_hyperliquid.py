"""
Database Migration for Hyperliquid Integration

Adds exchange column to liquidations table to support multi-exchange data.
"""

import psycopg2
from dotenv import load_dotenv
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def migrate_database():
    """Add exchange column to liquidations table."""
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'liquidation_trading'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', '')
        )
        
        cursor = conn.cursor()
        
        logger.info("Connected to database")
        
        # Add exchange column if it doesn't exist
        logger.info("Adding exchange column to liquidations table...")
        
        cursor.execute("""
            ALTER TABLE liquidations 
            ADD COLUMN IF NOT EXISTS exchange VARCHAR(20) DEFAULT 'BINANCE';
        """)
        
        # Create index on exchange column
        logger.info("Creating index on exchange column...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_liquidations_exchange 
            ON liquidations(exchange);
        """)
        
        # Create index for cross-exchange queries
        logger.info("Creating composite index for cross-exchange analysis...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_exchange_timestamp 
            ON liquidations(symbol, exchange, timestamp);
        """)
        
        conn.commit()
        
        logger.info("✅ Database migration completed successfully!")
        logger.info("")
        logger.info("Changes made:")
        logger.info("  - Added 'exchange' column to liquidations table")
        logger.info("  - Created index on exchange column")
        logger.info("  - Created composite index for cross-exchange queries")
        logger.info("")
        logger.info("Existing Binance data will have exchange = 'BINANCE'")
        logger.info("New Hyperliquid data will have exchange = 'HYPERLIQUID'")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    print("="*60)
    print("HYPERLIQUID INTEGRATION - DATABASE MIGRATION")
    print("="*60)
    print("")
    print("This will add support for multi-exchange liquidation data.")
    print("")
    
    response = input("Proceed with migration? (yes/no): ")
    
    if response.lower() == 'yes':
        migrate_database()
    else:
        print("Migration cancelled")
