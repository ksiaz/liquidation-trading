"""
Orderbook Feature Extractor - Phase 2
Extracts orderbook characteristics from labeled data to discover predictive patterns.

Features extracted:
1. Imbalance metrics (bid/ask ratio, weighted imbalance, trend)
2. Depth metrics (total liquidity, concentration, asymmetry)
3. Spread metrics (absolute, percentile)
4. Volume metrics (recent volume vs average)
5. Price metrics (volatility, momentum)
"""

import pandas as pd
import numpy as np
from datetime import timedelta

class OrderbookFeatureExtractor:
    def __init__(self, labeled_data_file):
        """
        Args:
            labeled_data_file: Path to CSV from Phase 1 (direction labels)
        """
        print(f"Loading labeled data from {labeled_data_file}...")
        self.df = pd.read_csv(labeled_data_file)
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        
        print(f"Loaded {len(self.df)} labeled snapshots")
        print(f"  - Bullish: {len(self.df[self.df['future_label'] == 'BULLISH'])}")
        print(f"  - Bearish: {len(self.df[self.df['future_label'] == 'BEARISH'])}")
        print(f"  - Flat: {len(self.df[self.df['future_label'] == 'FLAT'])}")
    
    def extract_features(self):
        """Extract all orderbook and market features."""
        print("\nExtracting features...")
        
        # Initialize feature columns
        features = pd.DataFrame(index=self.df.index)
        
        # === BASIC IMBALANCE ===
        print("  - Imbalance metrics...")
        total_vol = self.df['bid_volume_10'] + self.df['ask_volume_10']
        features['imbalance'] = (self.df['bid_volume_10'] - self.df['ask_volume_10']) / total_vol
        features['imbalance'].fillna(0, inplace=True)
        
        # Imbalance trend (rolling 30s)
        features['imbalance_ma_30'] = features['imbalance'].rolling(30, min_periods=1).mean()
        features['imbalance_slope_30'] = features['imbalance'] - features['imbalance_ma_30']
        
        # === DEPTH METRICS ===
        print("  - Depth metrics...")
        features['total_depth'] = total_vol
        features['depth_ratio'] = self.df['bid_volume_10'] / self.df['ask_volume_10']
        features['depth_ratio'].replace([np.inf, -np.inf], 0, inplace=True)
        features['depth_ratio'].fillna(0, inplace=True)
        
        # Depth trend
        features['depth_change_30'] = features['total_depth'].pct_change(30)
        features['depth_change_30'].fillna(0, inplace=True)
        
        # === SPREAD METRICS ===
        print("  - Spread metrics...")
        features['spread_pct'] = self.df['spread_pct']
        features['spread_ma_60'] = features['spread_pct'].rolling(60, min_periods=1).mean()
        features['spread_percentile'] = features['spread_pct'] / features['spread_ma_60']
        features['spread_percentile'].replace([np.inf, -np.inf], 1, inplace=True)
        features['spread_percentile'].fillna(1, inplace=True)
        
        # === PRICE METRICS ===
        print("  - Price metrics...")
        features['mid_price'] = self.df['mid_price']
        
        # Price momentum (% change over different windows)
        features['price_mom_10'] = features['mid_price'].pct_change(10)
        features['price_mom_30'] = features['mid_price'].pct_change(30)
        features['price_mom_60'] = features['mid_price'].pct_change(60)
        
        # Price volatility (rolling std)
        features['price_vol_30'] = features['mid_price'].rolling(30, min_periods=1).std()
        features['price_vol_60'] = features['mid_price'].rolling(60, min_periods=1).std()
        
        # Fill NaN for momentum/volatility
        for col in ['price_mom_10', 'price_mom_30', 'price_mom_60', 'price_vol_30', 'price_vol_60']:
            features[col].fillna(0, inplace=True)
        
        # === VOLUME METRICS ===
        print("  - Volume metrics...")
        features['volume_ma_60'] = features['total_depth'].rolling(60, min_periods=1).mean()
        features['volume_ratio'] = features['total_depth'] / features['volume_ma_60']
        features['volume_ratio'].replace([np.inf, -np.inf], 1, inplace=True)
        features['volume_ratio'].fillna(1, inplace=True)
        
        # Volume trend
        features['volume_slope'] = features['total_depth'] - features['volume_ma_60']
        
        # === MICROSTRUCTURE ===
        print("  - Microstructure metrics...")
        
        # Price direction changes (tick direction)
        features['price_up_tick'] = (features['mid_price'].diff() > 0).astype(int)
        features['price_down_tick'] = (features['mid_price'].diff() < 0).astype(int)
        
        # Count tick direction in rolling window
        features['up_ticks_30'] = features['price_up_tick'].rolling(30, min_periods=1).sum()
        features['down_ticks_30'] = features['price_down_tick'].rolling(30, min_periods=1).sum()
        features['tick_imbalance'] = (features['up_ticks_30'] - features['down_ticks_30']) / 30
        
        # === COMBINED FEATURES ===
        print("  - Combined indicators...")
        
        # Strong imbalance + low volatility = potential breakout
        features['breakout_signal'] = (
            (features['imbalance'].abs() > 0.3) & 
            (features['price_vol_30'] < features['price_vol_60'])
        ).astype(int)
        
        # Imbalance divergence from price
        features['imbalance_price_div'] = np.where(
            (features['price_mom_30'] > 0) & (features['imbalance'] < -0.1), 1,  # Price up, imbalance bearish
            np.where(
                (features['price_mom_30'] < 0) & (features['imbalance'] > 0.1), -1,  # Price down, imbalance bullish
                0
            )
        )
        
        # Add labels
        features['future_label'] = self.df['future_label']
        features['future_move_pct'] = self.df['future_move_pct']
        features['timestamp'] = self.df['timestamp']
        
        print(f"\nExtracted {len(features.columns)} features")
        return features
    
    def analyze_feature_importance(self, features):
        """
        Analyze which features correlate with direction changes.
        """
        print("\n" + "="*80)
        print("FEATURE IMPORTANCE ANALYSIS")
        print("="*80)
        
        # Separate by label
        bullish = features[features['future_label'] == 'BULLISH']
        bearish = features[features['future_label'] == 'BEARISH']
        flat = features[features['future_label'] == 'FLAT']
        
        # Feature columns (exclude labels and timestamp)
        feature_cols = [col for col in features.columns 
                       if col not in ['future_label', 'future_move_pct', 'timestamp']]
        
        print(f"\nAnalyzing {len(feature_cols)} features...\n")
        
        # Calculate mean for each group
        results = []
        
        for col in feature_cols:
            bull_mean = bullish[col].mean()
            bear_mean = bearish[col].mean()
            flat_mean = flat[col].mean()
            
            # Calculate separation (how different are bull/bear from flat)
            bull_sep = abs(bull_mean - flat_mean)
            bear_sep = abs(bear_mean - flat_mean)
            total_sep = bull_sep + bear_sep
            
            # Direction (do bull and bear diverge?)
            divergence = abs(bull_mean - bear_mean)
            
            results.append({
                'feature': col,
                'bull_mean': bull_mean,
                'bear_mean': bear_mean,
                'flat_mean': flat_mean,
                'separation': total_sep,
                'divergence': divergence,
                'score': total_sep + divergence  # Combined importance score
            })
        
        # Sort by importance
        results_df = pd.DataFrame(results).sort_values('score', ascending=False)
        
        # Print top features
        print("TOP 15 MOST IMPORTANT FEATURES:")
        print("-"*80)
        print(f"{'Feature':<30} {'Bullish':<12} {'Bearish':<12} {'Flat':<12} {'Score':<10}")
        print("-"*80)
        
        for idx, row in results_df.head(15).iterrows():
            print(f"{row['feature']:<30} {row['bull_mean']:>11.4f} {row['bear_mean']:>11.4f} "
                  f"{row['flat_mean']:>11.4f} {row['score']:>9.4f}")
        
        print("="*80)
        
        # Save full results
        results_df.to_csv('feature_importance.csv', index=False)
        print(f"\n💾 Full feature importance saved to: feature_importance.csv")
        
        return results_df
    
    def save_features(self, features, output_file='features_with_labels.csv'):
        """Save feature matrix with labels."""
        features.to_csv(output_file, index=False)
        print(f"\n💾 Feature matrix saved to: {output_file}")
        print(f"   Shape: {features.shape[0]} rows × {features.shape[1]} columns")

if __name__ == "__main__":
    # Load labeled data from Phase 1
    extractor = OrderbookFeatureExtractor('labeled_data_SOLUSDT_20251231.csv')
    
    # Extract features
    features = extractor.extract_features()
    
    # Analyze feature importance
    importance = extractor.analyze_feature_importance(features)
    
    # Save feature matrix
    extractor.save_features(features)
    
    print("\n✅ Phase 2 Complete - Feature extraction done!")
    print("   Next: Use feature_importance.csv to build new detector")
