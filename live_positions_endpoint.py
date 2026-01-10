@app.route('/api/live-positions')
def get_live_positions():
    """Get live positions with real-time P&L."""
    try:
        if not performance_tracker:
            return jsonify({'error': 'Performance tracker not available'}), 503
        
        # Get active signals with live metrics
        active_positions = []
        for signal_id, signal in performance_tracker.active_signals.items():
            position = {
                'id': signal_id,
                'symbol': signal['symbol'],
                'direction': signal['direction'],
                'type': signal.get('type', 'UNKNOWN'),
                'confidence': signal.get('confidence', 0),
                'entry': signal['entry'],
                'current': signal.get('current_price', signal['entry']),
                'target': signal['target'],
                'stop': signal['stop'],
                'unrealized_pnl': signal.get('unrealized_pnl_pct', 0),
                'distance_to_target': signal.get('distance_to_target_pct', 0),
                'distance_to_stop': signal.get('distance_to_stop_pct', 0),
                'duration': signal.get('duration_seconds', 0),
                'timestamp': signal['timestamp']
            }
            active_positions.append(position)
        
        return jsonify({
            'positions': active_positions,
            'count': len(active_positions),
            'timestamp': time.time()
        })
    
    except Exception as e:
        logger.error(f"Error fetching live positions: {e}")
        return jsonify({'error': str(e)}), 500
