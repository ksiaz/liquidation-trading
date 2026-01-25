# Manipulation Research Findings

**Date:** 2026-01-19
**Data Source:** Hyperliquid Node (64.176.65.252)
**Scope:** BTC, ETH, SOL order flow and sweep analysis

---

## Executive Summary

Analysis of node-level order data reveals significant directional bias and coordinated activity patterns that may indicate market manipulation ahead of liquidation cascades.

### Key Findings

| Metric | BTC | ETH | SOL |
|--------|-----|-----|-----|
| Sweep Imbalance | -25.7% BEARISH | -22.6% BEARISH | -74.4% BEARISH |
| UP Sweep Volume | $491M | $294M | $28M |
| DOWN Sweep Volume | $831M | $465M | $192M |
| Directional Whales | 8 detected | 3 detected | 0 detected |

**All three major assets show strong BEARISH sweep imbalance**, with SOL showing extreme -74.4% bias toward DOWN sweeps.

---

## 1. Sweep Direction Analysis

### Definition
A "sweep" is an aggressive market order that consumes multiple price levels in the order book in rapid succession.

### Findings

#### BTC (Bitcoin)
- **UP sweeps:** 19 events, $491,456,685 total
- **DOWN sweeps:** 31 events, $831,418,070 total
- **Imbalance:** -25.7% (BEARISH)

**Largest DOWN sweeps (potential long liquidation triggers):**
| Wallet | Amount |
|--------|--------|
| 0x12653c414ab3fc... | $45,975,542 |
| 0xedc712f5395737... | $39,768,703 |
| 0x87edc697bf9343... | $31,551,237 |
| 0xb5f7bd5cb13eec... | $31,135,442 |

#### ETH (Ethereum)
- **UP sweeps:** 20 events, $293,758,046 total
- **DOWN sweeps:** 30 events, $465,442,091 total
- **Imbalance:** -22.6% (BEARISH)

**Largest DOWN sweeps:**
| Wallet | Amount |
|--------|--------|
| 0x9f33f565f0ed31... | $21,547,804 |
| 0x4df968ddd85ba6... | $19,560,090 |
| 0xf37eb0e589dc11... | $19,068,660 |
| 0x46b6ff58757266... | $18,958,675 |

#### SOL (Solana)
- **UP sweeps:** 7 events, $28,136,729 total
- **DOWN sweeps:** 43 events, $191,763,574 total
- **Imbalance:** -74.4% (BEARISH) **EXTREME**

**Largest DOWN sweeps:**
| Wallet | Amount |
|--------|--------|
| 0x1701d22c19bc28... | $9,426,918 |
| 0x2269e4ce158828... | $7,382,606 |
| 0x60a3e0c6b7d8c9... | $6,736,948 |

---

## 2. Wallet Coordination Analysis

### Methodology
Identified instances where 3+ different wallets executed sweeps within the same second - a strong indicator of coordinated activity.

### Findings

**10 coordinated sweep events detected**

| Wallets | Total Volume | Direction | Coordination |
|---------|--------------|-----------|--------------|
| 5 | $97,389,008 | MIXED (56% up) | High |
| 9 | $75,993,077 | UP (100% up) | **Very High** |
| 5 | $41,487,190 | DOWN (0% up) | **Very High** |
| 3 | $39,130,952 | UP (100% up) | **Very High** |
| 4 | $35,882,381 | UP (100% up) | **Very High** |
| 3 | $27,429,499 | UP (67% up) | Moderate |
| 3 | $25,808,273 | DOWN (0% up) | **Very High** |
| 3 | $23,540,370 | DOWN (0% up) | **Very High** |
| 3 | $23,503,606 | DOWN (0% up) | **Very High** |
| 3 | $20,311,692 | UP (100% up) | **Very High** |

### Interpretation
- 9 wallets coordinating $76M in UP sweeps in a single second is statistically improbable without coordination
- Multiple events show 100% directional alignment (all UP or all DOWN)
- This pattern is consistent with either:
  - Market maker hedging activity
  - Coordinated manipulation to trigger liquidations

---

## 3. Price Impact Analysis

### Sweep Characteristics by Asset

| Asset | Current Price | Avg UP Sweep | Avg DOWN Sweep | Widest Sweep |
|-------|---------------|--------------|----------------|--------------|
| BTC | $92,605 | $11.4M (26 levels) | $10.5M (21 levels) | DOWN - 35 levels |
| ETH | $3,203 | $7.9M (17 levels) | $6.7M (20 levels) | DOWN - 25 levels |
| SOL | $133 | $1.5M (13 levels) | $1.7M (14 levels) | UP - 19 levels |

### Observations
- BTC DOWN sweeps hit up to 35 price levels - significant slippage potential
- ETH DOWN sweeps average more levels (20) than UP sweeps (17)
- SOL has most balanced level consumption, but volume heavily skewed DOWN

---

## 4. Directional Whale Detection

### Methodology
Identified wallets with $10M+ volume and 100% directional bias (all trades in one direction).

### BTC Directional Whales

**LONG bias (potential short squeeze actors):**
| Wallet | Volume |
|--------|--------|
| 0xd4cb1c88d37e47... | $15,199,100 |
| 0x09fb19b230d43c... | $13,272,342 |
| 0x1a4070a49a3e7f... | $12,802,492 |
| 0x5186e78f7dd1e2... | $11,505,373 |
| 0x54bd38bdd65fc4... | $11,359,372 |

**SHORT bias (potential long liquidation actors):**
| Wallet | Volume |
|--------|--------|
| 0xf3f64e8eaaf7f0... | $13,888,643 |
| 0x32770b06713b14... | $12,154,199 |
| 0x57a297211539cb... | $10,366,721 |

### ETH Directional Whales

**LONG bias only detected:**
| Wallet | Volume |
|--------|--------|
| 0x742234b8b816c1... | $17,454,265 |
| 0x5d86aa3338fc37... | $11,431,300 |
| 0x2e76bc4f429244... | $10,245,387 |

### SOL
No directional whales >$10M detected, but extreme -46.2% SELL imbalance in order flow.

---

## 5. Manipulation Signal Summary

### Active Signals

| Signal Type | Asset | Severity | Evidence |
|-------------|-------|----------|----------|
| Extreme Imbalance | SOL | HIGH | -46.2% sell pressure |
| Sweep Imbalance | SOL | HIGH | -74.4% bearish |
| Sweep Imbalance | BTC | MEDIUM | -25.7% bearish |
| Sweep Imbalance | ETH | MEDIUM | -22.6% bearish |
| Coordinated Sweeps | ALL | HIGH | 10 events with 3+ wallets |
| Directional Whales | BTC | HIGH | 8 wallets with 100% bias |
| Directional Whales | ETH | MEDIUM | 3 wallets with 100% bias |

---

## 6. Trading Implications

### Hypothesis: Sweep-Liquidation Correlation
Large DOWN sweeps may precede long liquidation cascades by:
1. Triggering stop losses at key levels
2. Moving price toward liquidation clusters
3. Creating cascade effect as liquidations add selling pressure

### Actionable Signals

1. **Extreme Order Imbalance (>30%)** - Often precedes price movement in that direction
2. **Multi-level Sweeps** - Aggressive actor willing to accept slippage = high conviction
3. **100% Directional Wallets** - May be positioning for manipulation or have inside information
4. **Coordinated Multi-wallet Activity** - Strong indicator of organized manipulation
5. **Thin Support/Resistance** - Vulnerability to moves through that zone

### Current Market Bias
All three major assets show **BEARISH** sweep imbalance, suggesting:
- Active selling pressure from large actors
- Potential setup for long liquidation cascade
- Higher probability of downside moves in near term

---

## 7. Methodology Notes

### Data Source
- Direct node access to Hyperliquid validator replica
- Order data from `replica_cmds/` directory
- State data from `abci_state.rmp`

### Definitions
- **Sweep:** Order that fills across 5+ price levels in <1 second
- **Coordination:** 3+ wallets executing in same 1-second window
- **Directional Whale:** Wallet with >$10M volume and 100% single-direction trades

### Limitations
- Historical order data only (no real-time streaming)
- Cannot prove causation, only correlation
- Wallet addresses may be controlled by same entity

---

## Appendix: Research API Endpoints

The following endpoints were used for this analysis:

```
GET /order_flow?coin={coin}&minutes={window}
GET /price_zones?coin={coin}&max_distance={pct}
GET /sweeps?coin={coin}
GET /wallet_profile?wallet={address}
```

Server: `http://64.176.65.252:8081` (accessed via SSH tunnel)

---

*Generated by manipulation research framework*
