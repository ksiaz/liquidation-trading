"""
Create Signals Table in PostgreSQL

Run this script to add the signals table to your existing PostgreSQL database.
"""

import logging
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_signals_table():
    """Create signals table and indexes in PostgreSQL."""
    
    logger.info("Creating signals table in PostgreSQL...")
    
    db = DatabaseManager()
    
    # Read schema file
    try:
        with open('database_signals_schema_postgres.sql', 'r') as f:
            schema = f.read()
        
        # Execute schema
        db.cursor.execute(schema)
        db.commit()
        
        logger.info("✅ Signals table created successfully!")
        
        # Verify table exists
        db.cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_name = 'signals'
        """)
        
        count = db.cursor.fetchone()[0]
        if count > 0:
            logger.info("✅ Verified: signals table exists")
        else:
            logger.error("❌ Table creation failed")
        
        db.close()
        
    except Exception as e:
        logger.error(f"❌ Error creating signals table: {e}")
        db.rollback()
        db.close()
        raise


if __name__ == "__main__":
    print("=" * 60)
    print("PostgreSQL Signals Table Setup")
    print("=" * 60)
    print()
    
    try:
        create_signals_table()
        print()
        print("=" * 60)
        print("✅ Setup Complete!")
        print("=" * 60)
        print()
        print("The signals table has been added to your PostgreSQL database.")
        print("Signal persistence will now use PostgreSQL instead of SQLite.")
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Setup Failed!")
        print("=" * 60)
        print(f"Error: {e}")
        print()
        print("Please check your database connection and try again.")
