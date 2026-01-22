ADVANCED CASCADE MECHANICS & CROSS-MARKET SIGNALS
Hypotheses Requiring Validation

---

CRITICAL NOTICE

Every claim in this document is a HYPOTHESIS.

None of these patterns have been validated against Hyperliquid historical data.
Numbers (timeframes, thresholds, percentages) are estimates, not measurements.

Before using any of this:
1. Collect 30-60 days of raw data
2. Test each hypothesis against your data
3. If it doesn't hold, discard it

Do NOT trade based on unvalidated hypotheses.

---

PART 1: CROSS-EXCHANGE FUNDING LEAD

HYPOTHESIS: Binance funding leads Hyperliquid by 5-30 minutes.

Reasoning:
- Binance has more volume, price discovery happens there first
- HL funding calculation lags due to lower liquidity
- Arbitrageurs don't instantly equalize

Potential Edge:
- When Binance funding spikes to extreme (>0.1%), HL will follow
- Window to position before HL funding catches up
- Fade direction of extreme funding

Implementation:

def check_funding_divergence(symbol: str) -> Optional[dict]:
    binance_funding = get_binance_funding(symbol)
    hl_funding = get_hl_funding(symbol)

    divergence = binance_funding - hl_funding

    if abs(divergence) > 0.0005:  # 0.05% divergence threshold
        return {
            'binance': binance_funding,
            'hl': hl_funding,
            'divergence': divergence,
            'expected_hl_direction': 'UP' if divergence > 0 else 'DOWN'
        }
    return None

Validation Required:
- Measure actual lead time over 100+ funding changes
- Check if divergence reliably predicts HL funding direction
- Measure how quickly divergence closes
- Calculate if edge exceeds transaction costs

STATUS: HYPOTHESIS - UNVALIDATED

---

PART 2: CASCADE WAVE STRUCTURE

HYPOTHESIS: Liquidation cascades occur in 3-5 discrete waves, not continuous flow.

Wave Structure (Estimated):

Wave 1 (0-30s):     High-leverage positions liquidated first
                    Typically 3-10x leverage longs/shorts

Wave 2 (30-90s):    Margin calls trigger forced closes
                    Lower leverage positions hit maintenance margin

Wave 3 (60-180s):   Stop losses execute
                    Retail stops clustered at obvious levels

Wave 4 (120-300s):  Panic selling/buying
                    Discretionary traders exit

Wave 5 (optional):  Second liquidation round
                    Wave 1-4 price move triggers new liquidations

Timing Estimates: UNVALIDATED - derived from other markets, not HL data.

Potential Edge:
- Enter after Wave 2-3 exhaustion, not during Wave 1
- Wave 1 entries get stopped out by Wave 2
- Absorption signals appear between waves

Detection:

def detect_wave_structure(liquidations: List[Liquidation], window_sec: int = 300):
    """Group liquidations into waves based on clustering."""
    if not liquidations:
        return []

    waves = []
    current_wave = [liquidations[0]]

    for liq in liquidations[1:]:
        time_gap = liq.ts - current_wave[-1].ts

        if time_gap > 30_000_000_000:  # 30 second gap = new wave
            waves.append(current_wave)
            current_wave = [liq]
        else:
            current_wave.append(liq)

    waves.append(current_wave)
    return waves

def is_wave_exhausted(wave: List[Liquidation], current_ts: int) -> bool:
    """Check if wave has likely completed."""
    if not wave:
        return True

    time_since_last = current_ts - wave[-1].ts
    wave_volume = sum(l.size for l in wave)

    # HYPOTHESIS: Wave exhausted if 30s+ since last liquidation
    # and volume declining
    return time_since_last > 30_000_000_000

Validation Required:
- Analyze 100+ cascade events for wave structure
- Measure actual inter-wave timing
- Check if wave count is consistent (3-5) or varies
- Determine if wave structure predicts exhaustion

STATUS: HYPOTHESIS - UNVALIDATED

---

PART 3: ABSORPTION DETECTION

FACT: Absorption occurs when passive buyers absorb aggressive selling.

Observable Signature:
- Bid depth INCREASES while price DECREASES
- Someone is placing bids into the selling
- Indicates buyer willing to accumulate at lower prices

Implementation:

def detect_absorption(
    current_bid_depth: float,
    previous_bid_depth: float,
    current_price: float,
    previous_price: float,
    threshold_depth_increase: float = 0.05,  # 5% depth increase
    threshold_price_decrease: float = 0.001  # 0.1% price decrease
) -> bool:
    """
    Detect absorption: bid depth up while price down.

    This is MECHANICAL DEFINITION, not hypothesis.
    Whether absorption predicts reversal IS hypothesis.
    """
    depth_change = (current_bid_depth - previous_bid_depth) / previous_bid_depth
    price_change = (current_price - previous_price) / previous_price

    return (
        depth_change > threshold_depth_increase and
        price_change < -threshold_price_decrease
    )

HYPOTHESIS: Absorption during cascade predicts exhaustion.

Reasoning:
- Passive buyer absorbing liquidation flow
- Liquidation supply being consumed
- Once absorbed, selling pressure exhausted

Validation Required:
- Track absorption events during cascades
- Measure price action 1-5 minutes after absorption
- Calculate win rate of entering on absorption signal
- Compare to random entry during cascade

STATUS: Definition is FACT. Predictive value is HYPOTHESIS - UNVALIDATED.

---

PART 4: OI CONCENTRATION RISK

HYPOTHESIS: When top N wallets hold >X% of OI, liquidation risk is concentrated.

Reasoning:
- Single whale liquidation can cascade entire market
- Concentrated OI = fragile market structure
- Distributed OI = more stable

Implementation:

def calculate_oi_concentration(positions: List[Position], top_n: int = 10) -> float:
    """
    Calculate what percentage of OI is held by top N wallets.

    Higher concentration = higher cascade risk from single liquidation.
    """
    sizes = sorted([abs(p.size) for p in positions], reverse=True)
    total_oi = sum(sizes)
    top_n_oi = sum(sizes[:top_n])

    return top_n_oi / total_oi if total_oi > 0 else 0

def assess_concentration_risk(concentration: float) -> str:
    """
    HYPOTHESIS: These thresholds indicate risk levels.
    Thresholds are GUESSES, require validation.
    """
    if concentration > 0.5:
        return "EXTREME"  # Top 10 hold >50%
    elif concentration > 0.4:
        return "HIGH"     # Top 10 hold >40%
    elif concentration > 0.3:
        return "MODERATE" # Top 10 hold >30%
    else:
        return "LOW"

Validation Required:
- Calculate concentration before historical cascades
- Compare concentration levels: cascade days vs normal days
- Find actual threshold that separates high-risk from normal
- Current thresholds (30/40/50%) are arbitrary

STATUS: HYPOTHESIS - THRESHOLDS UNVALIDATED

---

PART 5: FUNDING SETTLEMENT TIMING

FACT: Hyperliquid settles funding every 8 hours.

Settlement Times (UTC): 00:00, 08:00, 16:00

HYPOTHESIS: 15-30 minutes before settlement, positions adjust.

Reasoning:
- Traders close positions to avoid paying funding
- If funding is negative for longs, longs close
- Creates directional pressure before settlement

Implementation:

def time_to_next_funding() -> int:
    """Seconds until next funding settlement."""
    now = datetime.utcnow()

    settlement_hours = [0, 8, 16]
    current_hour = now.hour

    next_settlement = None
    for h in settlement_hours:
        if h > current_hour:
            next_settlement = h
            break

    if next_settlement is None:
        next_settlement = settlement_hours[0]  # Tomorrow's first

    # Calculate seconds to next settlement
    target = now.replace(hour=next_settlement, minute=0, second=0, microsecond=0)
    if target < now:
        target += timedelta(days=1)

    return int((target - now).total_seconds())

def is_pre_settlement_window(window_minutes: int = 30) -> bool:
    """Check if we're in pre-settlement adjustment window."""
    return time_to_next_funding() < window_minutes * 60

def predict_settlement_pressure(funding_rate: float) -> str:
    """
    HYPOTHESIS: Extreme funding creates directional pressure before settlement.
    """
    if funding_rate > 0.0005:  # Longs paying
        return "SELL_PRESSURE"  # Longs close to avoid paying
    elif funding_rate < -0.0005:  # Shorts paying
        return "BUY_PRESSURE"   # Shorts close to avoid paying
    else:
        return "NEUTRAL"

Validation Required:
- Analyze price action in 30 minutes before settlements
- Compare days with extreme funding vs neutral funding
- Measure actual window length (is it 15 min? 30 min? 60 min?)
- Calculate if pre-settlement bias is tradeable after costs

STATUS: Settlement times are FACT. Adjustment window is HYPOTHESIS - UNVALIDATED.

---

PART 6: CROSS-ASSET CASCADE CORRELATION

HYPOTHESIS: BTC cascades lead ETH, ETH leads alts.

Estimated Lead Times:
- BTC → ETH: 30-120 seconds
- ETH → Alts: 60-180 seconds

Reasoning:
- BTC is most liquid, moves first
- ETH traders react to BTC
- Alt traders react to both
- Margin calls cascade down the liquidity ladder

Implementation:

def check_cascade_correlation(
    btc_cascade_end: int,
    current_ts: int,
    btc_lead_window: int = 120_000_000_000  # 120 seconds in nanoseconds
) -> bool:
    """
    Check if BTC cascade recently completed, implying ETH cascade imminent.
    """
    time_since_btc = current_ts - btc_cascade_end
    return time_since_btc < btc_lead_window

def get_cascade_priority():
    """
    Watch assets in priority order during cascade conditions.

    HYPOTHESIS: Cascades propagate in this order.
    """
    return ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP', 'OTHERS']

Validation Required:
- Identify 50+ cascade events across BTC, ETH, alts
- Measure actual lead/lag times
- Check if correlation is consistent or varies
- Determine if lead time is tradeable (enough time to position?)

STATUS: HYPOTHESIS - TIMING UNVALIDATED

---

PART 7: MANIPULATOR DETECTION

HYPOTHESIS: Manipulated cascades show OI pause/reversal mid-event.

Pattern:
- Real cascade: OI drops smoothly
- Manipulated: OI drops, pauses or increases, drops again

Reasoning:
- Manipulator triggers cascade with initial selling
- Pauses to let liquidations run
- OI increases = manipulator re-entering (accumulating)
- Second leg down to trigger more liquidations

Implementation:

def detect_manipulation_pattern(
    oi_values: List[int],
    timestamps: List[int],
    window_start: int = 5,   # Skip first 5 readings
    window_end: int = 20     # Check readings 5-20
) -> bool:
    """
    HYPOTHESIS: OI increasing mid-cascade indicates manipulation.

    Real cascade: monotonic OI decrease
    Manipulation: OI decrease, increase, decrease
    """
    for i in range(window_start, min(window_end, len(oi_values) - 1)):
        oi_change = oi_values[i + 1] - oi_values[i]

        if oi_change > 0:
            # OI increased during cascade
            return True

    return False

def cascade_leg_count(oi_values: List[int]) -> int:
    """
    Count number of distinct down-legs in cascade.

    HYPOTHESIS: >2 legs suggests manipulation (artificial extension).
    """
    legs = 0
    in_down_leg = False

    for i in range(1, len(oi_values)):
        change = oi_values[i] - oi_values[i-1]

        if change < 0 and not in_down_leg:
            legs += 1
            in_down_leg = True
        elif change >= 0:
            in_down_leg = False

    return legs

Validation Required:
- Identify cascade events with manipulation pattern
- Compare outcomes: manipulated vs organic cascades
- Check if manipulation detection improves entry timing
- Validate that OI pause actually indicates re-accumulation

STATUS: HYPOTHESIS - UNVALIDATED

---

PART 8: SPOT-PERP BASIS AS LEADING INDICATOR

HYPOTHESIS: Perp trading at significant discount to spot indicates liquidation pressure.

Basis Calculation:

def calculate_basis(perp_price: float, spot_price: float) -> float:
    """
    Basis = (perp - spot) / spot

    Positive: Perp premium (bullish positioning)
    Negative: Perp discount (bearish positioning / liquidations)
    """
    return (perp_price - spot_price) / spot_price

def interpret_basis(basis: float) -> str:
    """
    HYPOTHESIS: These thresholds indicate market state.
    Thresholds are GUESSES.
    """
    if basis < -0.005:  # >0.5% discount
        return "LIQUIDATION_PRESSURE"
    elif basis < -0.002:
        return "MILD_SELLING"
    elif basis > 0.005:
        return "FOMO_PREMIUM"
    elif basis > 0.002:
        return "MILD_BUYING"
    else:
        return "NEUTRAL"

Validation Required:
- Track basis during confirmed cascades
- Measure if extreme negative basis precedes cascades
- Find actual threshold that signals cascade (is it -0.5%? -1%?)
- Check Hyperliquid-specific basis behavior

STATUS: HYPOTHESIS - THRESHOLDS UNVALIDATED

---

PART 9: THE MISSING PIECE - SEQUENCING

Your current system (from HLP docs):
- Detects conditions: OI spike, funding skew, depth asymmetry
- Treats them as simultaneous requirements

HYPOTHESIS: The sequence of conditions matters, not just presence.

Wrong Approach:

def should_enter_wrong(state):
    return (
        state.oi_spike and
        state.funding_skewed and
        state.depth_asymmetric
    )
    # Problem: Doesn't know WHERE in cascade you are

Better Approach:

def should_enter_better(state, event_history):
    # Check sequence
    if not event_history.oi_spike_occurred:
        return False  # Haven't seen spike yet

    if not event_history.funding_skew_occurred:
        return False  # Spike happened but funding hasn't reacted

    if not event_history.depth_asymmetry_occurred:
        return False  # Funding skewed but depth hasn't shifted

    if not event_history.absorption_detected:
        return False  # THE KEY: Haven't seen exhaustion signal

    # All stages complete, in correct order
    return True

Ideal Sequence:

1. OI SPIKE         → Market is positioned
2. FUNDING SKEW     → Imbalance confirmed
3. DEPTH ASYMMETRY  → Liquidity withdrawing from one side
4. CASCADE TRIGGER  → Liquidations begin
5. WAVE 1-2         → Initial liquidations execute
6. ABSORPTION       → ← ENTER HERE
7. EXHAUSTION       → Cascade complete
8. REVERSAL         → Price recovers

Most Systems Enter at Step 4.
Edge is Entering at Step 6.

Validation Required:
- Map historical cascades to this sequence
- Check if sequence is consistent
- Measure outcomes by entry point in sequence
- Validate absorption as reliable exhaustion signal

STATUS: HYPOTHESIS - SEQUENCE UNVALIDATED

---

PART 10: VALIDATION FRAMEWORK

For each hypothesis in this document:

Step 1: Collect Data

Run data collection for 30-60 days minimum:
- Raw OI, funding, depth, trades, liquidations
- Cross-exchange data (Binance funding)
- Spot prices for basis calculation

Step 2: Label Events

Identify cascade events mechanically:
- OI dropped >15% in <60 seconds (or your threshold)
- Tag wave structure, absorption points
- Record outcomes (price 1/5/15 min after)

Step 3: Test Hypothesis

For each hypothesis:
- Calculate metric (lead time, concentration, etc.)
- Correlate with cascade occurrence or outcome
- Measure statistical significance
- Calculate if edge exceeds costs

Step 4: Validate or Discard

If hypothesis holds:
- Document actual values (not estimates)
- Implement in trading system
- Continue monitoring for degradation

If hypothesis fails:
- Document why it failed
- Remove from consideration
- Don't revisit without new evidence

Step 5: Track Degradation

Markets change. What works today may fail tomorrow.
- Re-validate quarterly
- Monitor for regime changes
- Be willing to discard degraded signals

---

IMPLEMENTATION CHECKLIST

[ ] Set up Binance funding data collection
[ ] Calculate and log basis (perp vs spot)
[ ] Implement wave detection algorithm
[ ] Add absorption detection to hot state
[ ] Calculate OI concentration daily
[ ] Log pre-settlement price action
[ ] Track cross-asset cascade timing
[ ] Build validation pipeline for each hypothesis
[ ] Document which hypotheses validated/failed
[ ] Remove failed hypotheses from system

---

BOTTOM LINE

Everything in this document is a hypothesis.

Some hypotheses are:
- Mechanically sound (absorption definition)
- Logically derived (funding settlement pressure)
- Observed in other markets (cascade waves)

But NONE are validated on Hyperliquid data.

Your job:
1. Collect data
2. Test each hypothesis
3. Keep what works
4. Discard what doesn't

Don't trade based on this document.
Trade based on validated patterns in YOUR data.

The estimates and thresholds here are starting points for investigation,
not proven values. Treat them with appropriate skepticism.
