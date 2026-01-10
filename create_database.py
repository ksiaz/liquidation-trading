"""
Create the liquidation_trading database.

This script connects to PostgreSQL and creates the database if it doesn't exist.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_database():
    """Create the liquidation_trading database."""
    
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'liquidation_trading')
    db_user = os.getenv('DB_USER', 'postgres')
    db_password = os.getenv('DB_PASSWORD', '')
    
    print(f"Connecting to PostgreSQL at {db_host}:{db_port}...")
    
    try:
        # Connect to default 'postgres' database to create our database
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database='postgres',  # Connect to default database
            user=db_user,
            password=db_password
        )
        
        # Set isolation level to autocommit to create database
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print(f"✓ Connected to PostgreSQL")
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,)
        )
        
        if cursor.fetchone():
            print(f"✓ Database '{db_name}' already exists")
        else:
            # Create database
            cursor.execute(f'CREATE DATABASE {db_name}')
            print(f"✓ Created database '{db_name}'")
        
        cursor.close()
        conn.close()
        
        print("\n✅ Database setup complete!")
        print(f"\nYou can now run: python setup.py")
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"\n✗ Connection error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running")
        print("2. Check credentials in .env file")
        print("3. Verify PostgreSQL is accepting connections on port", db_port)
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("CREATE LIQUIDATION_TRADING DATABASE")
    print("=" * 60)
    print()
    
    success = create_database()
    sys.exit(0 if success else 1)
