"""
Web Dashboard Server

Serves a real-time dashboard that displays:
1. Live liquidation events (from monitor.py)
2. Liquidation predictions (from prediction_monitor.py)
3. Market statistics and risk analysis

Uses Flask for the web server and Server-Sent Events (SSE) for real-time updates.
"""

from flask import Flask, render_template, jsonify, Response, request
from flask_cors import CORS
import json
import time
from datetime import datetime
from threading import Thread
import queue
from liquidation_predictor import LiquidationPredictor
from database import DatabaseManager
# OLD SignalGenerator removed - now using EarlyReversalDetector-based version
from market_impact import MarketImpactCalculator
from institutional_monitor import InstitutionalMonitor
from alpha_engine.engine import AlphaEngine
from config import SYMBOLS, DASHBOARD_ZONES_TO_SHOW, DASHBOARD_MIN_VALUE_USD
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Event queues for SSE
liquidation_queue = queue.Queue()
prediction_queue = queue.Queue()

# Initialize components
predictor = LiquidationPredictor(SYMBOLS)
impact_calc = MarketImpactCalculator()
db = DatabaseManager()
institutional_mon = InstitutionalMonitor(db)

# Initialize Orderbook Storage (stores 20-level orderbook to PostgreSQL)
# NOTE: Signal generators will be connected AFTER they are initialized (see line ~295)
try:
    from orderbook_storage import OrderbookStorageManager
    orderbook_storage = OrderbookStorageManager(SYMBOLS, db)
    
    orderbook_storage.start()
    logger.info("Orderbook storage started - capturing 1s snapshots to database")
except Exception as e:
    logger.warning(f"Orderbook storage not available: {e}")
    orderbook_storage = None

# Initialize Combined Heatmap Generators (liquidation density + order walls)
try:
    from combined_heatmap import CombinedHeatmapGenerator
    heatmap_generators = {s: CombinedHeatmapGenerator(s, predictor) for s in SYMBOLS}
    logger.info("Heatmap generators initialized - tracking liquidation density and order walls")
    
    # Connect orderbook stream to heatmap generators
    if orderbook_storage and orderbook_storage.stream:
        def on_orderbook_for_heatmap(symbol, orderbook):
            """Feed orderbook data to heatmap generators."""
            if symbol in heatmap_generators:
                heatmap_generators[symbol].on_orderbook_update(orderbook)
        
        orderbook_storage.stream.add_callback(on_orderbook_for_heatmap)
        logger.info("Heatmap generators connected to orderbook stream")
except Exception as e:
    logger.warning(f"Heatmap generators not available: {e}")
    heatmap_generators = None

# Initialize Advanced Orderbook Analyzers (OFI, weighted imbalance, etc.)
try:
    from orderbook_analyzer import OrderBookAnalyzer
    from mm_inventory_tracker import MarketMakerInventoryTracker
    from order_wall_detector import OrderWallDetector
    from v_bottom_tracker import VBottomTracker

    orderbook_analyzers = {s: OrderBookAnalyzer() for s in SYMBOLS}
    logger.info("Orderbook analyzers initialized - OFI, weighted imbalance, liquidity voids")
    
    mm_trackers = {s: MarketMakerInventoryTracker(s) for s in SYMBOLS}
    logger.info("MM inventory trackers initialized - tracking market maker positions")
    
    wall_detectors = {s: OrderWallDetector(s) for s in SYMBOLS}
    logger.info("Order wall detectors initialized - identifying significant order walls")
    
    v_bottom_trackers = {s: VBottomTracker(s) for s in SYMBOLS}
    logger.info("V-bottom trackers initialized - detecting sharp selloff reversals")
    
    # Store V-bottom signals (will be populated by tracker updates)
    v_bottom_signals = {s: None for s in SYMBOLS}
    
    # Connect orderbook stream to analyzers, MM trackers, wall detectors, and V-bottom trackers
    if orderbook_storage and orderbook_storage.stream:
        def on_orderbook_update_for_analysis(symbol, orderbook):
            """Feed orderbook data to advanced analyzers, MM trackers, wall detectors, and V-bottom trackers."""
            try:
                if symbol in orderbook_analyzers:
                    # Calculate OFI and other metrics
                    orderbook_analyzers[symbol].calculate_order_flow_imbalance(orderbook)
                    orderbook_analyzers[symbol].calculate_weighted_imbalance(orderbook)
                
                if symbol in mm_trackers:
                    mm_trackers[symbol].update(orderbook)
                
                if symbol in wall_detectors:
                    wall_detectors[symbol].on_orderbook_update(orderbook)
                
                # Update V-bottom tracker (NEW!)
                if symbol in v_bottom_trackers:
                    # Get current price from orderbook
                    if orderbook.get('bids'):
                        price = float(orderbook['bids'][0][0])
                        signal = v_bottom_trackers[symbol].update(orderbook, price)
                        
                        # Store signal if generated
                        if signal:
                            v_bottom_signals[symbol] = signal
                            logger.info(f"V-bottom signal generated for {symbol}: {signal['strategy']} @ {signal['confidence']:.0%}")
                    
            except Exception as e:
                logger.error(f"Error in orderbook update callback for analysis: {e}", exc_info=True)
        
        orderbook_storage.stream.add_callback(on_orderbook_update_for_analysis)
        logger.info("Orderbook analyzers, MM trackers, wall detectors, and V-bottom trackers connected to orderbook stream")
except Exception as e:
    logger.warning(f"Orderbook analytics components not available: {e}")
    orderbook_analyzers = None
    mm_trackers = None
    wall_detectors = None
    v_bottom_trackers = None

# Initialize Dynamic Confidence Calculators (percentage-based scoring)
try:
    from dynamic_confidence import DynamicConfidenceCalculator
    confidence_calculators = {s: DynamicConfidenceCalculator(s) for s in SYMBOLS}
    logger.info("Confidence calculators initialized - dynamic percentage-based scoring")
except Exception as e:
    logger.warning(f"Confidence calculators not available: {e}")
    confidence_calculators = None

# Initialize Binance Liquidation Stream (for live liquidation feed)
try:
    from liquidation_stream import BinanceLiquidationStream
    binance_liq_queue = queue.Queue()
    binance_stream = BinanceLiquidationStream(symbols=SYMBOLS, data_queue=binance_liq_queue)
    logger.info("Binance liquidation stream initialized")
except Exception as e:
    logger.warning(f"Binance liquidation stream not available: {e}")
    binance_stream = None
    binance_liq_queue = None

# Initialize Trade Stream and Volume Flow Analyzers (for reversal detection)
try:
    from trade_stream import BinanceTradeStream
    from volume_flow_detector import MultiWindowVolumeAnalyzer
    
    # Create volume analyzers for each symbol
    volume_flow_analyzers = {s: MultiWindowVolumeAnalyzer(s) for s in SYMBOLS}
    logger.info("Volume flow analyzers initialized - tracking 1m, 5m, 15m windows")
    
    # Create trade stream
    trade_stream = BinanceTradeStream(SYMBOLS)
    
    # Connect trade stream to volume analyzers AND live price tracking
    def on_trade_for_volume_flow(symbol, trade):
        """Feed trades to volume flow analyzers and update live prices."""
        if symbol in volume_flow_analyzers:
            volume_flow_analyzers[symbol].on_trade(trade)
        
        # Update live price for performance tracking
        if 'update_live_price' in globals() and 'price' in trade:
            update_live_price(symbol, trade['price'])
    
    trade_stream.add_callback(on_trade_for_volume_flow)
    trade_stream.start()
    
    logger.info("Trade stream started - feeding volume flow analyzers")
except Exception as e:
    logger.warning(f"Trade stream / volume flow not available: {e}")
    trade_stream = None
    volume_flow_analyzers = None

# Initialize Order Toxicity Calculators (detect informed vs uninformed flow)
try:
    from order_toxicity import OrderToxicityCalculator
    
    # Create toxicity calculators for each symbol
    toxicity_calculators = {s: OrderToxicityCalculator(s) for s in SYMBOLS}
    logger.info("Order toxicity calculators initialized - detecting informed trading")
    
    # Connect trade stream to toxicity calculators
    if trade_stream:
        def on_trade_for_toxicity(symbol, trade):
            """Feed trades to toxicity calculators."""
            if symbol in toxicity_calculators:
                toxicity_calculators[symbol].calculate_toxicity(trade)
        
        trade_stream.add_callback(on_trade_for_toxicity)
        logger.info("Toxicity calculators connected to trade stream")
    
    # Connect orderbook stream to toxicity calculators
    if orderbook_storage and orderbook_storage.stream:
        def on_orderbook_for_toxicity(symbol, orderbook):
            """Feed orderbook to toxicity calculators."""
            if symbol in toxicity_calculators:
                toxicity_calculators[symbol].update_orderbook(orderbook)
        
        orderbook_storage.stream.add_callback(on_orderbook_for_toxicity)
        logger.info("Toxicity calculators connected to orderbook stream")
        
except Exception as e:
    logger.warning(f"Order toxicity calculators not available: {e}")
    toxicity_calculators = None

# Initialize Enhanced Signal Generator (combines all analytics)
# DISABLED: Using new EarlyReversalDetector-based SignalGenerator instead
# try:
#     from enhanced_signal_generator import EnhancedSignalGenerator
#     
#     enhanced_signal_gen = EnhancedSignalGenerator(SYMBOLS)
#     logger.info("Enhanced signal generator initialized - combining all analytics")
#     
#     # Signal generation will be triggered periodically
#     signal_history = []  # Store recent signals for dashboard
#     
# except Exception as e:
#     logger.warning(f"Enhanced signal generator not available: {e}")
#     enhanced_signal_gen = None
#     signal_history = []

# OLD signal generator disabled - using EarlyReversalDetector-based version
enhanced_signal_gen = None
signal_history = []
logger.info("✅ Using NEW EarlyReversalDetector-based signal generator only")

# Initialize Funding Rate Monitor
try:
    from funding_rate_monitor import FundingRateMonitor
    
    funding_monitor = FundingRateMonitor(SYMBOLS)
    funding_monitor.update()  # Initial fetch
    logger.info("Funding rate monitor initialized - tracking overcrowded positions")
    
except Exception as e:
    logger.warning(f"Funding rate monitor not available: {e}")
    funding_monitor = None

# Initialize Signal Performance Tracker
try:
    from signal_performance_tracker import SignalPerformanceTracker
    
    performance_tracker = SignalPerformanceTracker()
    logger.info("Signal performance tracker initialized")
    
except Exception as e:
    logger.warning(f"Performance tracker not available: {e}")
    performance_tracker = None

# Initialize NEW Signal Generators (AFTER performance_tracker exists!)
signal_generators = {}
signal_queue = queue.Queue()  # Shared queue for broadcasting signals to dashboard

for symbol in SYMBOLS:
    try:
        from signal_generator import SignalGenerator as NewSignalGenerator
        signal_generators[symbol] = NewSignalGenerator(
            db, 
            signal_queue, 
            symbol=symbol,
            performance_tracker=performance_tracker
        )
        logger.info(f"✅ Signal Generator initialized for {symbol}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize signal generator for {symbol}: {e}", exc_info=True)
        signal_generators[symbol] = None

# CRITICAL: Connect signal generators to orderbook storage NOW
if orderbook_storage:
    orderbook_storage.signal_generators = signal_generators
    active_count = len([g for g in signal_generators.values() if g])
    logger.info(f"✅ {active_count} signal generators connected to orderbook storage")
else:
    logger.error("❌ Orderbook storage not available - signals will NOT be generated!")

# Live price tracking (from trade streams, not DB)
live_prices = {symbol: 0.0 for symbol in SYMBOLS}

def update_live_price(symbol: str, price: float):
    """Update live price from trade stream."""
    live_prices[symbol] = price
    
    # Update performance tracker
    if performance_tracker:
        performance_tracker.update_prices(live_prices)

# Note: dYdX stream removed - using Binance only for reliability

# Start Binance Liquidation Stream
if binance_stream:
    binance_stream.start()
    logger.info("Binance liquidation stream started")
    
    # Background thread to process Binance liquidations
    def process_binance_liquidations():
        """Process liquidations from Binance stream and push to SSE queue."""
        logger.info("Binance liquidation processor thread started")
        while True:
            try:
                if binance_liq_queue:
                    liq = binance_liq_queue.get(timeout=1)
                    
                    logger.debug(f"Raw liquidation from queue: {liq}")
                    logger.debug(f"Liquidation types: {[(k, type(v).__name__) for k, v in liq.items()]}")
                    
                    # Convert ALL datetime objects to ISO strings
                    cleaned_liq = {}
                    for key, value in liq.items():
                        if hasattr(value, 'isoformat'):
                            cleaned_liq[key] = value.isoformat()
                            logger.debug(f"Converted {key} from datetime to string: {cleaned_liq[key]}")
                        else:
                            cleaned_liq[key] = value
                    
                    logger.debug(f"Cleaned liquidation: {cleaned_liq}")
                    logger.debug(f"Cleaned types: {[(k, type(v).__name__) for k, v in cleaned_liq.items()]}")
                    
                    # Push to SSE queue for dashboard
                    liquidation_queue.put(cleaned_liq)
                    logger.info(f"Pushed liquidation to SSE queue: {cleaned_liq['symbol']} ${cleaned_liq['value_usd']:.2f}")
                    
                    # Also update heatmap if available
                    symbol = cleaned_liq['symbol']
                    if heatmap_generators and symbol in heatmap_generators:
                        heatmap_generators[symbol].on_liquidation({
                            'price': cleaned_liq['price'],
                            'value_usd': cleaned_liq['value_usd'],
                            'side': cleaned_liq['side'],
                            'timestamp': time.time()
                        })
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error processing Binance liquidation: {e}", exc_info=True)
                time.sleep(1)
    
    binance_thread = threading.Thread(target=process_binance_liquidations, daemon=True)
    binance_thread.start()
    logger.info("Binance liquidation processor started")


@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('dashboard.html')


@app.route('/api/stats')
def get_stats():
    """Get current statistics."""
    try:
        stats = {}
        
        for symbol in SYMBOLS:
            # Get database stats
            db_stats = db.get_stats(symbol=symbol)
            
            # Get prediction risk
            risk = predictor.analyze_liquidation_risk(symbol)
            
            stats[symbol] = {
                'db_stats': db_stats,
                'risk': risk
            }
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/recent_liquidations')
def get_recent_liquidations():
    """Get recent liquidation events."""
    try:
        limit = int(request.args.get('limit', 50))
        symbol = request.args.get('symbol', None)
        
        liquidations = db.get_recent_liquidations(limit=limit, symbol=symbol)
        
        # Convert datetime to string for JSON
        for liq in liquidations:
            liq['timestamp'] = liq['timestamp'].isoformat()
            liq['trade_time'] = liq['trade_time'].isoformat()
        
        return jsonify(liquidations)
    except Exception as e:
        logger.error(f"Error getting liquidations: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/trading_signals')
def get_trading_signals():
    """Get recent trading signals from EarlyReversalDetector."""
    try:
        limit = int(request.args.get('limit', 20))
        symbol = request.args.get('symbol', 'BTCUSDT')
        
        # Try to get from signal generator first
        if symbol in signal_generators and signal_generators[symbol]:
            signals = signal_generators[symbol].get_recent_signals(limit=limit)
            
            # Convert datetime to string for JSON
            for sig in signals:
                if 'timestamp' in sig and hasattr(sig['timestamp'], 'isoformat'):
                    sig['timestamp'] = sig['timestamp'].isoformat()
            
            return jsonify({
                'signals': signals,
                'stats': signal_generators[symbol].get_stats()
            })
        else:
            # Fallback: query database directly
            query = """
            SELECT timestamp, symbol, direction, entry_price, confidence, snr,
                   timeframe, signals_confirmed, signals_total,
                   imbalance_divergence, depth_building, volume_exhaustion,
                   funding_divergence, liquidity_confirmation,
                   wave_trend_bias
            FROM trading_signals
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """
            
            db.cursor.execute(query, (symbol, limit))
            
            signals = []
            for row in db.cursor.fetchall():
                signals.append({
                    'timestamp': row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                    'symbol': row[1],
                    'direction': row[2],
                    'entry_price': float(row[3]),
                    'confidence': row[4],
                    'snr': float(row[5]),
                    'timeframe': row[6],
                    'signals_confirmed': row[7],
                    'signals_total': row[8],
                    'signals': {
                        'imbalance_divergence': row[9],
                        'depth_building': row[10],
                        'volume_exhaustion': row[11],
                        'funding_divergence': row[12],
                        'liquidity_confirmation': row[13]
                    },
                    'wave_trend_bias': row[14]
                })
            
            return jsonify({'signals': signals, 'stats': {}})
            
    except Exception as e:
        logger.error(f"Error getting trading signals: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/predictions')
def get_predictions():
    try:
        predictions = {}
        
        for symbol in SYMBOLS:
            risk = predictor.analyze_liquidation_risk(symbol)
            zones = predictor.estimate_liquidation_zones(symbol)
            clusters = predictor.detect_liquidation_clusters(symbol)
            
            # Filter zones by minimum value
            # Calculate estimated value for each zone
            filtered_zones = []
            for zone in zones:
                # Estimate value: assume average position size based on leverage
                # Higher leverage = smaller positions typically
                estimated_value = zone['liquidation_price'] * (100 / zone['leverage'])
                
                if estimated_value >= DASHBOARD_MIN_VALUE_USD:
                    filtered_zones.append(zone)
            
            # Convert datetime to string
            if 'timestamp' in risk:
                risk['timestamp'] = risk['timestamp'].isoformat()
            
            for zone in filtered_zones:
                if 'timestamp' in zone:
                    zone['timestamp'] = zone['timestamp'].isoformat()
            
            # Get market impact (with timeout protection)
            try:
                impact = impact_calc.calculate_impact_for_move(symbol, 1.0)
            except Exception as e:
                logger.error(f"Error calculating impact for {symbol}: {e}")
                impact = {'error': 'timeout'}
            
            # Get recent order book snapshot
            try:
                ob_query = """
                SELECT imbalance, spread_pct, bid_volume_10, ask_volume_10
                FROM orderbook_snapshots
                WHERE symbol = %s
                ORDER BY timestamp DESC
                LIMIT 1
                """
                db.cursor.execute(ob_query, (symbol,))
                ob_row = db.cursor.fetchone()
                
                if ob_row:
                    orderbook_data = {
                        'imbalance': float(ob_row[0]) if ob_row[0] else 0,
                        'spread_pct': float(ob_row[1]) if ob_row[1] else 0,
                        'bid_volume': float(ob_row[2]) if ob_row[2] else 0,
                        'ask_volume': float(ob_row[3]) if ob_row[3] else 0
                    }
                else:
                    orderbook_data = None
            except Exception as e:
                logger.error(f"Error fetching order book for {symbol}: {e}")
                orderbook_data = None
            
            # Get institutional activity summary
            try:
                institutional = institutional_mon.get_institutional_summary(symbol)
            except Exception as e:
                logger.error(f"Error getting institutional data for {symbol}: {e}\")")
                institutional = None
            
            # Get signal from NEW EarlyReversalDetector-based generator
            signal = None
            if symbol in signal_generators and signal_generators[symbol]:
                try:
                    # Get most recent signal from database for this symbol
                    recent_signals = signal_generators[symbol].get_recent_signals(limit=1)
                    if recent_signals:
                        sig = recent_signals[0]
                        # Convert to old signal format for dashboard compatibility
                        signal = {
                            'type': 'EARLY_REVERSAL',
                            'direction': sig['direction'],
                            'confidence': 'HIGH' if sig['confidence'] >= 75 else 'MEDIUM',
                            'confidence_score': sig['confidence'],
                            'reason': f"SNR: {sig['snr']:.2f}, {sig['signals_confirmed']}/{sig['signals_total']} signals",
                            'entry': f"${sig['entry_price']:,.2f}",
                            'target': f"${sig['entry_price'] * 1.005:,.2f}" if sig['direction'] == 'LONG' else f"${sig['entry_price'] * 0.995:,.2f}",
                            'stop': f"${sig['entry_price'] * 0.9975:,.2f}" if sig['direction'] == 'LONG' else f"${sig['entry_price'] * 1.0025:,.2f}",
                            'setup': f"Timeframe: {sig['timeframe']}s, Wave: {sig.get('wave_trend_bias', 'N/A')}"
                        }
                except Exception as e:
                    logger.error(f"Error getting signal for {symbol}: {e}")
            
            # Add dynamic confidence if available
            if confidence_calculators and symbol in confidence_calculators:
                try:
                    # Get confidence percentage
                    conf_data = confidence_calculators[symbol].get_confidence(
                        signal['direction'] if signal else 'LONG'
                    )
                    
                    # Add to signal
                    if signal:
                        signal['confidence_pct'] = conf_data['confidence_pct']
                        signal['confidence_breakdown'] = conf_data['breakdown']
                        signal['market_regime'] = conf_data['regime']
                except Exception as e:
                    logger.error(f"Error calculating confidence for {symbol}: {e}")
            
            predictions[symbol] = {
                'zones': zones[:12],  # Top 12 zones
                'risk': risk,
                'signal': signal,
                'orderbook': orderbook_data or {}
            }
        
        return jsonify(predictions)
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/stream/liquidations')
def stream_liquidations():
    """Server-Sent Events stream for real-time liquidations."""
    def generate():
        while True:
            try:
                # Get liquidation from live queue (blocking with timeout)
                liq = liquidation_queue.get(timeout=1)
                
                logger.debug(f"SSE stream received: {liq}")
                logger.debug(f"SSE types: {[(k, type(v).__name__) for k, v in liq.items()]}")
                
                # Double-check: Ensure all values are JSON serializable
                for key, value in liq.items():
                    if hasattr(value, 'isoformat'):
                        liq[key] = value.isoformat()
                        logger.warning(f"SSE: Had to convert {key} from datetime!")
                
                # Send to dashboard
                json_str = json.dumps(liq)
                logger.debug(f"SSE JSON: {json_str}")
                yield f"data: {json_str}\n\n"
                
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"
            except Exception as e:
                logger.error(f"Error in liquidation stream: {e}", exc_info=True)
                time.sleep(1)
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/stream/predictions')
def stream_predictions():
    """Server-Sent Events stream for real-time predictions."""
    def generate():
        while True:
            try:
                predictions = {}
                
                for symbol in SYMBOLS:
                    risk = predictor.analyze_liquidation_risk(symbol)
                    
                    # Convert datetime to string
                    if 'timestamp' in risk:
                        risk['timestamp'] = risk['timestamp'].isoformat()
                    
                    predictions[symbol] = risk
                
                yield f"data: {json.dumps(predictions)}\n\n"
                
                time.sleep(10)  # Update every 10 seconds
            except Exception as e:
                logger.error(f"Error in prediction stream: {e}")
                time.sleep(5)
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/heatmap')
def get_heatmap():
    """Get heatmap data for all symbols."""
    try:
        heatmaps = {}
        
        if not heatmap_generators:
            return jsonify({'error': 'Heatmap generators not available'}), 503
        
        for symbol in SYMBOLS:
            if symbol in heatmap_generators:
                heatmap = heatmap_generators[symbol]
                
                # Get heatmap data and hot zones
                heatmap_data = heatmap.get_heatmap_data()
                hot_zones = heatmap.get_hot_zones(threshold_percentile=75)
                stats = heatmap.get_stats()
                
                heatmaps[symbol] = {
                    'heatmap': heatmap_data,
                    'hot_zones': hot_zones,
                    'stats': stats,
                    'current_price': heatmap.current_price
                }
            else:
                heatmaps[symbol] = {'error': 'No data'}
        
        return jsonify(heatmaps)
    except Exception as e:
        logger.error(f"Error getting heatmaps: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/orderbook-metrics')
def get_orderbook_metrics():
    """Get advanced orderbook analytics for all symbols."""
    try:
        metrics = {}
        
        if not orderbook_analyzers:
            return jsonify({'error': 'Orderbook analyzers not available'}), 503
        
        for symbol in SYMBOLS:
            if symbol in orderbook_analyzers:
                analyzer = orderbook_analyzers[symbol]
                
                # Get current OFI
                current_ofi = analyzer.ofi_history[-1] if analyzer.ofi_history else 0
                
                # Calculate OFI signal
                ofi_signal = 'NEUTRAL'
                if current_ofi > 1.0:
                    ofi_signal = 'STRONG_BULLISH'
                elif current_ofi > 0.3:
                    ofi_signal = 'BULLISH'
                elif current_ofi < -1.0:
                    ofi_signal = 'STRONG_BEARISH'
                elif current_ofi < -0.3:
                    ofi_signal = 'BEARISH'
                
                # Get OFI stats
                ofi_stats = {}
                if len(analyzer.ofi_history) > 0:
                    import numpy as np
                    ofi_stats = {
                        'current': current_ofi,
                        'avg': float(np.mean(analyzer.ofi_history)),
                        'std': float(np.std(analyzer.ofi_history)),
                        'min': float(np.min(analyzer.ofi_history)),
                        'max': float(np.max(analyzer.ofi_history))
                    }
                
                metrics[symbol] = {
                    'ofi': {
                        'value': current_ofi,
                        'signal': ofi_signal,
                        'stats': ofi_stats
                    },
                    'timestamp': time.time()
                }
            else:
                metrics[symbol] = {'error': 'No data'}
        
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error getting orderbook metrics: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/volume-flow')
def get_volume_flow():
    """
    Get volume flow analysis and reversal signals.
    
    Returns cumulative buy/sell volume, flow states, and reversal signals
    for all symbols across multiple time windows (1m, 5m, 15m).
    """
    try:
        results = {}
        
        if not volume_flow_analyzers:
            return jsonify({'error': 'Volume flow analyzers not available'}), 503
        
        for symbol in SYMBOLS:
            if symbol in volume_flow_analyzers:
                analyzer = volume_flow_analyzers[symbol]
                
                # Get all window states
                states = analyzer.get_all_states()
                
                # Get reversal signal (if multiple windows agree)
                reversal_signal = analyzer.get_reversal_signal()
                
                results[symbol] = {
                    'states': states,
                    'reversal_signal': reversal_signal,
                    'timestamp': time.time()
                }
            else:
                results[symbol] = {'error': 'No data'}
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error getting volume flow: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/order-toxicity')
def get_order_toxicity():
    """Get order toxicity analysis and signals."""
    try:
        results = {}
        
        if not toxicity_calculators:
            return jsonify({'error': 'Toxicity calculators not available'}), 503
        
        for symbol in SYMBOLS:
            if symbol in toxicity_calculators:
                calc = toxicity_calculators[symbol]
                signal = calc.get_toxicity_signal(window_seconds=30)
                stats = calc.get_stats()
                
                results[symbol] = {
                    'signal': signal,
                    'stats': stats,
                    'timestamp': time.time()
                }
            else:
                results[symbol] = {'error': 'No data'}
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error getting order toxicity: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/enhanced-signals')
def get_enhanced_signals():
    """Get enhanced trading signals combining all analytics."""
    try:
        if not enhanced_signal_gen:
            return jsonify({'error': 'Enhanced signal generator not available'}), 503
        
        signals = []
        
        for symbol in SYMBOLS:
            # Get current price (with fallback to Binance API)
            price = None
            try:
                price_data = db.get_latest_price(symbol)
                if price_data:
                    price = price_data['price']
            except Exception as e:
                logger.debug(f"Database price fetch failed for {symbol}: {e}")
            
            # Fallback: Fetch from Binance API directly
            if not price:
                try:
                    import requests
                    response = requests.get(
                        f'https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}',
                        timeout=5
                    )
                    if response.status_code == 200:
                        data = response.json()
                        price = float(data['price'])
                        logger.debug(f"Using Binance API price for {symbol}: {price}")
                except Exception as e:
                    logger.error(f"Failed to get price for {symbol} from both DB and API: {e}")
                    continue
            
            if not price:
                logger.warning(f"No price available for {symbol}, skipping signal generation")
                continue
            
            # Get OFI data
            ofi_data = None
            if symbol in orderbook_analyzers:
                analyzer = orderbook_analyzers[symbol]
                if analyzer.ofi_history:
                    ofi_val = analyzer.ofi_history[-1]
                    ofi_data = {
                        'ofi': {
                            'value': ofi_val,
                            'signal': 'STRONG_BULLISH' if ofi_val > 1.0 else 
                                     'BULLISH' if ofi_val > 0.3 else
                                     'BEARISH' if ofi_val < -0.3 else
                                     'STRONG_BEARISH' if ofi_val < -1.0 else 'NEUTRAL'
                        }
                    }
            
            # Get toxicity data
            toxicity_data = None
            if symbol in toxicity_calculators:
                calc = toxicity_calculators[symbol]
                toxicity_data = {
                    'signal': calc.get_toxicity_signal(window_seconds=30),
                    'stats': calc.get_stats()
                }
            
            # Get volume flow data
            volume_flow_data = None
            if symbol in volume_flow_analyzers:
                analyzer = volume_flow_analyzers[symbol]
                volume_flow_data = {
                    'reversal_signal': analyzer.get_reversal_signal()
                }
            
            # Get orderbook data with orderbook alpha metrics (NEW!)
            orderbook_data = None
            if symbol in orderbook_analyzers:
                analyzer = orderbook_analyzers[symbol]
                if analyzer.prev_orderbook:
                    orderbook_data = {
                        'weighted_imbalance': analyzer.calculate_weighted_imbalance(analyzer.prev_orderbook)
                    }
                    
                    # Add liquidity cliffs (NEW!)
                    try:
                        current_price = price
                        cliffs = analyzer.detect_liquidity_cliffs(analyzer.prev_orderbook, current_price)
                        orderbook_data['liquidity_cliffs'] = cliffs
                    except Exception as e:
                        logger.debug(f"Could not detect liquidity cliffs for {symbol}: {e}")
                    
                    # Add spoofing events (NEW!)
                    if symbol in wall_detectors:
                        try:
                            wall_detector = wall_detectors[symbol]
                            spoofing_events = wall_detector.get_spoofing_events(60)  # Last 60 seconds
                            wall_summary = wall_detector.get_wall_summary()
                            
                            orderbook_data['spoofing_events'] = len(spoofing_events)
                            orderbook_data['stats'] = {
                                'walls': {
                                    'bid_walls': wall_summary.get('bid_walls', 0),
                                    'ask_walls': wall_summary.get('ask_walls', 0)
                                }
                            }
                        except Exception as e:
                            logger.debug(f"Could not get spoofing data for {symbol}: {e}")
                    
                    # Add MM signal (NEW!)
                    if symbol in mm_trackers:
                        try:
                            mm_tracker = mm_trackers[symbol]
                            mm_signal = mm_tracker.get_signal()
                            if mm_signal:
                                orderbook_data['mm_signal'] = mm_signal
                        except Exception as e:
                            logger.debug(f"Could not get MM signal for {symbol}: {e}")
                    
                    # Add V-bottom signal (NEW!)
                    if symbol in v_bottom_trackers:
                        try:
                            v_tracker = v_bottom_trackers[symbol]
                            v_state = v_tracker.get_state()
                            
                            # Include state info for monitoring
                            orderbook_data['v_bottom_state'] = v_state['state']
                            
                            # Pass signal if available
                            if symbol in v_bottom_signals and v_bottom_signals[symbol]:
                                orderbook_data['v_bottom_signal'] = v_bottom_signals[symbol]
                                # Clear signal after passing (consume once)
                                v_bottom_signals[symbol] = None
                                # Reset tracker
                                v_tracker.reset()
                        except Exception as e:
                            logger.debug(f"Could not get V-bottom data for {symbol}: {e}")
            
            # Get zones
            zones = predictor.estimate_liquidation_zones(symbol)
            
            # Get funding signal
            funding_signal = None
            if funding_monitor:
                funding_monitor.update()  # Update rates
                funding_signal = funding_monitor.get_funding_signal(symbol)
                logger.info(f"💰 {symbol}: Funding signal returned: {funding_signal is not None}")
                if funding_signal:
                    logger.info(f"   Type: {funding_signal.get('type')}, Direction: {funding_signal.get('direction')}, Confidence: {funding_signal.get('confidence')}")

            
            # Generate signal
            signal = enhanced_signal_gen.generate_signal(
                symbol=symbol,
                price=price,
                ofi_data=ofi_data,
                toxicity_data=toxicity_data,
                volume_flow_data=volume_flow_data,
                orderbook_data=orderbook_data,
                zones=zones,
                funding_signal=funding_signal
            )
            
            if signal:
                signals.append(signal)
                signal_history.insert(0, signal)
                if len(signal_history) > 20:
                    signal_history.pop()
                
                # Persist signal to database via performance tracker
                if performance_tracker:
                    try:
                        performance_tracker.add_signal(signal)
                        logger.info(f"Signal persisted: {signal['symbol']} {signal['type']} {signal['direction']}")
                    except Exception as e:
                        logger.error(f"Error persisting signal: {e}")
        
        return jsonify({
            'signals': signals,
            'history': signal_history,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"Error generating enhanced signals: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/funding-rates')
def get_funding_rates():
    """Get current funding rates and signals."""
    try:
        if not funding_monitor:
            return jsonify({'error': 'Funding monitor not available'}), 503
        
        # Update rates
        funding_monitor.update()
        
        results = {}
        for symbol in SYMBOLS:
            stats = funding_monitor.get_stats(symbol)
            signal = funding_monitor.get_funding_signal(symbol)
            
            results[symbol] = {
                'stats': stats,
                'signal': signal,
                'timestamp': time.time()
            }
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error getting funding rates: {e}")
        return jsonify({'error': str(e)}), 500


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


def run_server(host='0.0.0.0', port=5000):
    """Run the Flask server."""
    logger.info(f"Starting dashboard server on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    print("=" * 60)
    print("LIQUIDATION DASHBOARD SERVER")
    print("=" * 60)
    print("\nStarting server...")
    print("Dashboard will be available at: http://localhost:5000")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)
    
    run_server()
