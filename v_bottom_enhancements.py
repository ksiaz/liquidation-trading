    # ============================================
    # ENHANCEMENT METHODS (New Precision Layers)
    # ============================================
    
    def _detect_liquidation_cascade(self) -> Dict:
        """
        Enhancement Layer 8: Liquidation cascade detection.
        
        Detects when liquidations trigger more liquidations (cascade effect).
        Strong capitulation signal.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.liquidation_history) < 3:
            return {'score': 0.0}
        
        recent_liqs = list(self.liquidation_history)[-5:]
        
        # Extract liquidation data
        try:
            sides = [liq.get('side') for liq in recent_liqs if 'side' in liq]
            sizes = [liq.get('value_usd', 0) for liq in recent_liqs if 'value_usd' in liq]
            timestamps = [liq.get('timestamp', 0) for liq in recent_liqs if 'timestamp' in liq]
            
            if len(sides) < 3 or len(sizes) < 3 or len(timestamps) < 3:
                return {'score': 0.0}
            
            # Check for cascade pattern
            # 1. All same side (panic in one direction)
            if len(set(sides)) == 1:
                # 2. Increasing size (snowball effect)
                size_increasing = sum(1 for i in range(len(sizes)-1) if sizes[i] < sizes[i+1])
                
                # 3. Rapid succession (< 5 seconds between)
                time_diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                rapid_succession = sum(1 for diff in time_diffs if diff < 5)
                
                # Strong cascade if both conditions met
                if size_increasing >= 2 and rapid_succession >= 2:
                    return {
                        'score': 0.25,
                        'pattern': 'STRONG_CASCADE',
                        'cascade_size': len(recent_liqs),
                        'total_value': sum(sizes)
                    }
                elif size_increasing >= 1 or rapid_succession >= 1:
                    return {
                        'score': 0.15,
                        'pattern': 'MODERATE_CASCADE',
                        'cascade_size': len(recent_liqs)
                    }
            
            return {'score': 0.0}
            
        except Exception as e:
            logger.debug(f"Error detecting liquidation cascade: {e}")
            return {'score': 0.0}
    
    def _track_orderbook_pressure_buildup(self) -> Dict:
        """
        Enhancement Layer 9: Orderbook pressure buildup tracking.
        
        Tracks acceleration of bid refills (not just refill).
        Detects institutional buying.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.bid_depth_history) < 10:
            return {'score': 0.0}
        
        # Calculate pressure gradient (rate of change)
        bid_changes = []
        for i in range(1, len(self.bid_depth_history)):
            change = self.bid_depth_history[i] - self.bid_depth_history[i-1]
            bid_changes.append(change)
        
        if len(bid_changes) < 5:
            return {'score': 0.0}
        
        # Check for acceleration (gradient of gradient)
        recent_changes = bid_changes[-5:]
        
        # Accelerating bid refill (each change larger than previous)
        accelerating = sum(1 for i in range(len(recent_changes)-1) 
                          if recent_changes[i] > 0 and recent_changes[i+1] > recent_changes[i])
        
        if accelerating >= 3:
            acceleration_strength = recent_changes[-1] / (recent_changes[0] + 1)
            return {
                'score': 0.20,
                'pattern': 'ACCELERATING_BID_REFILL',
                'strength': acceleration_strength
            }
        elif accelerating >= 2:
            return {
                'score': 0.10,
                'pattern': 'MODERATE_BID_ACCELERATION'
            }
        
        return {'score': 0.0}
    
    def _analyze_volume_profile_shape(self) -> Dict:
        """
        Enhancement Layer 10: Volume profile microstructure.
        
        Analyzes volume distribution during selloff.
        Perfect V-bottom has volume spike at exact low, then declining.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.volume_history) < 30:
            return {'score': 0.0}
        
        volumes = list(self.volume_history)[-30:]
        
        # Find volume peak
        max_vol = max(volumes)
        peak_idx = volumes.index(max_vol)
        
        # Check if peak is recent (within last 10 ticks)
        if peak_idx > len(volumes) - 10:
            # Volume declining after peak (exhaustion)
            post_peak = volumes[peak_idx:]
            
            if len(post_peak) >= 3:
                # Check if declining
                declining = sum(1 for i in range(len(post_peak)-1) 
                               if post_peak[i] > post_peak[i+1])
                
                if declining >= len(post_peak) - 1:  # All declining
                    decline_rate = (post_peak[0] - post_peak[-1]) / (post_peak[0] + 1)
                    return {
                        'score': 0.15,
                        'pattern': 'CAPITULATION_EXHAUSTION',
                        'peak_volume': max_vol,
                        'decline_rate': decline_rate
                    }
                elif declining >= (len(post_peak) - 1) // 2:  # Mostly declining
                    return {
                        'score': 0.08,
                        'pattern': 'MODERATE_EXHAUSTION'
                    }
        
        return {'score': 0.0}
    
    def _detect_toxicity_flip(self) -> Dict:
        """
        Enhancement Layer 11: Toxicity flip detection.
        
        Detects when toxic (informed) flow reverses direction.
        Informed traders reversing = strong signal.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.toxicity_history) < 2:
            return {'score': 0.0}
        
        try:
            current_tox = self.toxicity_history[-1]
            
            if not current_tox or 'signal' not in current_tox:
                return {'score': 0.0}
            
            signal = current_tox.get('signal', {})
            
            # During CAPITULATION state, look for toxic buying
            if self.state == 'CAPITULATION':
                toxic_signal = signal.get('signal', '')
                
                if 'TOXIC_BUYING' in toxic_signal:
                    # Strong toxic buying during capitulation
                    avg_toxicity = signal.get('avg_toxicity', 0)
                    
                    if avg_toxicity > 0.7:
                        return {
                            'score': 0.20,
                            'pattern': 'STRONG_TOXIC_BUYING',
                            'toxicity': avg_toxicity
                        }
                    elif avg_toxicity > 0.5:
                        return {
                            'score': 0.10,
                            'pattern': 'MODERATE_TOXIC_BUYING',
                            'toxicity': avg_toxicity
                        }
            
            return {'score': 0.0}
            
        except Exception as e:
            logger.debug(f"Error detecting toxicity flip: {e}")
            return {'score': 0.0}
    
    def _check_btc_correlation(self) -> Dict:
        """
        Enhancement Layer 12: BTC correlation.
        
        Uses BTC as leading indicator for ETH/SOL.
        If BTC reversed first, ETH/SOL likely to follow.
        
        Returns:
            Dict with score and pattern info
        """
        # Only applies to ETH/SOL
        if self.symbol not in ['ETHUSDT', 'SOLUSDT']:
            return {'score': 0.0}
        
        # Check if BTC is in REVERSAL state
        if self.btc_state == 'REVERSAL' and self.state == 'CAPITULATION':
            return {
                'score': 0.15,
                'pattern': 'BTC_LEADING_REVERSAL'
            }
        elif self.btc_state == 'CAPITULATION' and self.state == 'CAPITULATION':
            return {
                'score': 0.08,
                'pattern': 'BTC_CORRELATED_CAPITULATION'
            }
        
        return {'score': 0.0}
    
    def set_btc_state(self, btc_state: str):
        """Set BTC state for correlation analysis."""
        self.btc_state = btc_state
