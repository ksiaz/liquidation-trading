WALLET TRACKING

STATUS: RESEARCH CONCEPT - NOT IMPLEMENTABLE WITH CURRENT DATA

---

CONCEPT OVERVIEW

The idea: Track specific wallet addresses to detect patterns in their trading behavior that correlate with subsequent market movements.

**CRITICAL LIMITATION:**
Node data provides a snapshot of current positions, not historical behavior.
To identify "interesting" wallets, you need historical data that doesn't exist in the node state.

---

WHAT NODE DATA PROVIDES

From user_to_state[address]:
- Current position size (s)
- Current entry price (e)
- Current leverage (l)
- Current margin (M)

From users_with_positions:
- Set of addresses with open positions (~66,000 wallets)

**What node data does NOT provide:**
- Historical trades by wallet
- Historical position changes
- Wallet behavior patterns over time
- Wallet profitability
- Wallet classification

---

IMPLEMENTATION REQUIREMENTS

To implement wallet tracking, you would need:

1. **Historical Position Tracking**
   - Record user_to_state snapshots over time
   - Build database of position changes per wallet
   - Requires running collector for extended period (weeks/months)

2. **Behavior Classification**
   - Define what "interesting" behavior means
   - Criteria must be precise and measurable
   - Must avoid overfitting to specific wallets

3. **Validation Framework**
   - Prove that identified wallets have predictive value
   - Out-of-sample testing required
   - Statistical significance required

---

POTENTIAL CLASSIFICATION CRITERIA (HYPOTHESES)

**HYPOTHESIS 1: Size-based classification**
Wallets with positions > X USD may have more market impact.
Problem: Large positions are visible to everyone.

**HYPOTHESIS 2: Timing-based classification**
Wallets that change positions before price moves may be informed.
Problem: Requires historical data and suffers survivorship bias.

**HYPOTHESIS 3: Behavior-based classification**
Wallets that show specific patterns (quick entry/exit, size scaling) may be identifiable.
Problem: Requires extensive historical data and clear pattern definitions.

---

HONEST ASSESSMENT

Current state:
- Wallet tracking is a concept, not a feature
- No implementation path exists without historical data collection
- No validated wallet classification criteria exist
- Claims of "manipulator wallet" identification are unsubstantiated

Future possibility:
- If historical data is collected for months, classification may become feasible
- Validation would still be required before use
- False positive rate would need to be measured

---

RECOMMENDATION

Do not implement wallet tracking until:
1. Historical position data has been collected for minimum 3 months
2. Classification criteria are precisely defined
3. Validation methodology is documented
4. Out-of-sample testing shows statistically significant predictive value

Until then, wallet tracking remains a research hypothesis, not a system feature.

---

WHAT CAN BE DONE NOW

Observable without historical data:
- Current aggregate position distribution (long vs short OI)
- Current leverage distribution
- Position concentration (are positions clustered in few wallets or distributed?)

These aggregate statistics may have value. Individual wallet tracking does not, without historical context.
