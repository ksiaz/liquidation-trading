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
                    logger.info(f"{self.symbol}: STRONG CASCADE detected ({len(recent_liqs)} liquidations, ${sum(sizes):,.0f})")
                    return {
                        'score': 0.25,
                        'pattern': 'STRONG_CASCADE',
                        'cascade_size': len(recent_liqs),
                        'total_value': sum(sizes)
                    }
                elif size_increasing >= 1 or rapid_succession >= 1:
                    logger.info(f"{self.symbol}: Moderate cascade detected")
                    return {
                        'score': 0.15,
                        'pattern': 'MODERATE_CASCADE',
                        'cascade_size': len(recent_liqs)
                    }
            
            return {'score': 0.0}
            
        except Exception as e:
            logger.debug(f"Error detecting liquidation cascade: {e}")
            return {'score': 0.0}
