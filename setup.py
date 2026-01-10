"""
Quick setup script for liquidation trading system.

This script will:
1. Check if PostgreSQL is accessible
2. Create .env file if it doesn't exist
3. Test database connection
4. Create tables
"""

import os
import sys
from pathlib import Path

def create_env_file():
    """Create .env file from template if it doesn't exist."""
    env_file = Path('.env')
    env_example = Path('.env.example')
    
    if env_file.exists():
        print("✓ .env file already exists")
        
        # Ask if user wants to recreate it
        response = input("\nDo you want to recreate it? (y/n): ").strip().lower()
        if response != 'y':
            return True
        
        print("\nRecreating .env file...")
    
    if not env_example.exists():
        print("✗ .env.example not found")
        return False
    
    print("\n.env file setup")
    print("=" * 60)
    print("Please enter your PostgreSQL credentials.")
    print("Press Enter to use the default value shown in brackets.")
    print("=" * 60)
    
    db_host = input("\nDB_HOST [localhost]: ").strip() or "localhost"
    
    # Validate port is a number
    while True:
        db_port_input = input("DB_PORT [5432]: ").strip() or "5432"
        try:
            int(db_port_input)
            db_port = db_port_input
            break
        except ValueError:
            print("  ✗ Port must be a number. Please try again.")
    
    db_name = input("DB_NAME [liquidation_trading]: ").strip() or "liquidation_trading"
    db_user = input("DB_USER [postgres]: ").strip() or "postgres"
    db_password = input("DB_PASSWORD [postgres]: ").strip() or "postgres"
    
    env_content = f"""# PostgreSQL Database Configuration
DB_HOST={db_host}
DB_PORT={db_port}
DB_NAME={db_name}
DB_USER={db_user}
DB_PASSWORD={db_password}

# Optional: Binance API (for future trading execution)
BINANCE_API_KEY=
BINANCE_API_SECRET=

# Optional: Telegram Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("\n✓ .env file created successfully!")
    print(f"\nConfiguration:")
    print(f"  Host: {db_host}")
    print(f"  Port: {db_port}")
    print(f"  Database: {db_name}")
    print(f"  User: {db_user}")
    
    return True

def test_database():
    """Test database connection and create tables."""
    print("\nTesting database connection...")
    
    try:
        from database import DatabaseManager
        
        db = DatabaseManager()
        print("✓ Connected to PostgreSQL")
        
        db.create_tables()
        print("✓ Tables created/verified")
        
        # Test insert
        from datetime import datetime
        test_event = {
            'timestamp': datetime.now(),
            'trade_time': datetime.now(),
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'quantity': 0.001,
            'price': 50000,
            'avg_price': 50000,
            'value_usd': 50,
            'status': 'FILLED'
        }
        
        db.insert_liquidation(test_event)
        db.commit()
        print("✓ Test event inserted")
        
        stats = db.get_stats()
        print(f"✓ Database has {stats['total_events']} total events")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"\n✗ Database error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running:")
        print("   - Docker: docker ps (should show liquidation-postgres)")
        print("   - Local: pg_isready")
        print("2. Verify credentials in .env file")
        print("3. Create database if it doesn't exist:")
        print("   createdb liquidation_trading")
        print("4. See DATABASE_SETUP.md for detailed help")
        print("\nQuick Docker setup:")
        print("  docker run --name liquidation-postgres \\")
        print("    -e POSTGRES_PASSWORD=postgres \\")
        print("    -e POSTGRES_DB=liquidation_trading \\")
        print("    -p 5432:5432 -d postgres:14")
        return False

def main():
    """Run setup."""
    print("=" * 60)
    print("LIQUIDATION TRADING SYSTEM - SETUP")
    print("=" * 60)
    
    # Step 1: Create .env
    if not create_env_file():
        print("\n✗ Setup failed: Could not create .env file")
        return 1
    
    # Step 2: Test database
    if not test_database():
        print("\n✗ Setup failed: Database connection issue")
        print("\nYou can:")
        print("1. Fix the database connection and run 'python setup.py' again")
        print("2. Edit .env file manually with correct credentials")
        return 1
    
    # Success!
    print("\n" + "=" * 60)
    print("✅ SETUP COMPLETE!")
    print("=" * 60)
    print("\nYou can now run:")
    print("  python monitor.py")
    print("\nTo start collecting liquidation data!")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
