    def _load_active_signals_from_db(self):
        """Load active signals from database on startup."""
        if not self.db:
            return
        
        try:
            active_signals = self.db.load_active_signals()
            
            for signal in active_signals:
                signal_id = signal['id']
                self.active_signals[signal_id] = signal
                self.stats['total_signals'] += 1
                self.stats['open'] += 1
            
            logger.info(f"✅ Recovered {len(active_signals)} active signals from database")
            
        except Exception as e:
            logger.error(f"Failed to load active signals from database: {e}")
