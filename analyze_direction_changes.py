"""
Direction Change Analyzer - Phase 1
Identifies significant price moves in historical orderbook data and labels them.

This tool:
1. Scans through orderbook snapshots
2. Identifies direction changes (0.3-0.5%+ moves)
3. Labels each snapshot with what happened next (BULLISH/BEARISH/FLAT)
4. Saves labeled dataset for pattern discovery
"""

import psycopg2
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import os
from dotenv import load_dotenv

load_dotenv()

class DirectionChangeAnalyzer:
    def __init__(self, symbol='SOLUSDT', lookforward_minutes=5, min_move_pct=0.003):
        """
        Args:
            symbol: Trading pair to analyze
            lookforward_minutes: How far into future to check for moves
            min_move_pct: Minimum move to classify as direction change (0.3%)
        """
        self.symbol = symbol
        self.lookforward_seconds = lookforward_minutes * 60
        self.min_move_pct = min_move_pct
        
        self.conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'liquidation_trading'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )
    
    def analyze_period(self, start_time, end_time):
        """
        Analyze a time period for direction changes.
        
        Args:
            start_time: Start of analysis period
            end_time: End of analysis period
        """
        print(f"Analyzing {self.symbol} from {start_time} to {end_time}")
        print(f"Looking forward: {self.lookforward_seconds}s, Min move: {self.min_move_pct*100}%")
        print("="*80)
        
        # Load data (actual schema: best_bid/ask + volume aggregates)
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT timestamp, best_bid, best_ask,
                   bid_volume_10, ask_volume_10, spread_pct
            FROM orderbook_snapshots
            WHERE symbol = %s
              AND timestamp >= %s
              AND timestamp <= %s
            ORDER BY timestamp ASC
        """, (self.symbol, start_time, end_time))
        
        rows = cursor.fetchall()
        cursor.close()
        
        if len(rows) == 0:
            print("No data found!")
            return None
        
        print(f"Loaded {len(rows)} snapshots")
        
        # Convert to DataFrame for easier analysis
        columns = ['timestamp', 'best_bid', 'best_ask',
                   'bid_volume_10', 'ask_volume_10', 'spread_pct']
        
        df = pd.DataFrame(rows, columns=columns)
        df['mid_price'] = (df['best_bid'].astype(float) + df['best_ask'].astype(float)) / 2
        
        print(f"Analyzing all {len(df)} snapshots (no sampling)")
        
        # Label each snapshot
        print("\nLabeling snapshots...")
        labels = []
        
        for idx, row in df.iterrows():
            current_time = row['timestamp']
            current_price = row['mid_price']
            
            # Find price range in next N seconds
            future_end = current_time + timedelta(seconds=self.lookforward_seconds)
            future_prices = df[
                (df['timestamp'] > current_time) & 
                (df['timestamp'] <= future_end)
            ]['mid_price']
            
            if len(future_prices) == 0:
                labels.append({
                    'label': 'INSUFFICIENT_DATA',
                    'max_move_pct': 0,
                    'direction': 'NONE',
                    'time_to_move': 0
                })
                continue
            
            # Calculate high and low
            future_high = future_prices.max()
            future_low = future_prices.min()
            
            # Calculate moves
            up_move_pct = (future_high - current_price) / current_price
            down_move_pct = (current_price - future_low) / current_price
            
            # Determine label
            if up_move_pct >= self.min_move_pct and up_move_pct > down_move_pct:
                # Bullish move
                time_to_high = df[df['mid_price'] == future_high]['timestamp'].iloc[0]
                labels.append({
                    'label': 'BULLISH',
                    'max_move_pct': up_move_pct,
                    'direction': 'UP',
                    'time_to_move': (time_to_high - current_time).total_seconds()
                })
            elif down_move_pct >= self.min_move_pct and down_move_pct > up_move_pct:
                # Bearish move
                time_to_low = df[df['mid_price'] == future_low]['timestamp'].iloc[0]
                labels.append({
                    'label': 'BEARISH',
                    'max_move_pct': down_move_pct,
                    'direction': 'DOWN',
                    'time_to_move': (time_to_low - current_time).total_seconds()
                })
            else:
                # Flat / choppy
                labels.append({
                    'label': 'FLAT',
                    'max_move_pct': max(up_move_pct, down_move_pct),
                    'direction': 'NONE',
                    'time_to_move': 0
                })
        
        # Add labels to dataframe
        df['future_label'] = [l['label'] for l in labels]
        df['future_move_pct'] = [l['max_move_pct'] for l in labels]
        df['future_direction'] = [l['direction'] for l in labels]
        df['time_to_move'] = [l['time_to_move'] for l in labels]
        
        # Print statistics
        print("\n" + "="*80)
        print("DIRECTION CHANGE STATISTICS")
        print("="*80)
        
        label_counts = df['future_label'].value_counts()
        print("\nLabel Distribution:")
        for label, count in label_counts.items():
            pct = count / len(df) * 100
            print(f"  {label:<20} {count:>6} ({pct:>5.1f}%)")
        
        # Bullish moves
        bullish = df[df['future_label'] == 'BULLISH']
        if len(bullish) > 0:
            print(f"\nBullish Moves ({len(bullish)}):")
            print(f"  Avg magnitude: {bullish['future_move_pct'].mean()*100:.2f}%")
            print(f"  Max magnitude: {bullish['future_move_pct'].max()*100:.2f}%")
            print(f"  Avg time to move: {bullish['time_to_move'].mean():.0f}s")
        
        # Bearish moves
        bearish = df[df['future_label'] == 'BEARISH']
        if len(bearish) > 0:
            print(f"\nBearish Moves ({len(bearish)}):")
            print(f"  Avg magnitude: {bearish['future_move_pct'].mean()*100:.2f}%")
            print(f"  Max magnitude: {bearish['future_move_pct'].max()*100:.2f}%")
            print(f"  Avg time to move: {bearish['time_to_move'].mean():.0f}s")
        
        print("="*80)
        
        # Save labeled dataset
        output_file = f'labeled_data_{self.symbol}_{start_time.strftime("%Y%m%d")}.csv'
        df.to_csv(output_file, index=False)
        print(f"\n💾 Labeled dataset saved to: {output_file}")
        
        return df
    
    def close(self):
        self.conn.close()

if __name__ == "__main__":
    analyzer = DirectionChangeAnalyzer(
        symbol='SOLUSDT',
        lookforward_minutes=5,  # Look 5 minutes ahead (was 3)
        min_move_pct=0.002      # 0.2% minimum move (was 0.3%)
    )
    
    # Analyze last 24 hours (more data)
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    
    df_labeled = analyzer.analyze_period(
        start_time=start_time,
        end_time=end_time
    )
    
    analyzer.close()
