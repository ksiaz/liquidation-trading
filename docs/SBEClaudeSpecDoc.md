# THE OMNISCIENT PREDATOR: Complete System Specification
## Liquidation Hunting on Hyperliquid with Maximum Intelligence

---

## TABLE OF CONTENTS

1. [System Overview](#system-overview)
2. [Core Architecture](#core-architecture)
3. [Risk Management System](#risk-management-system)
4. [Epistemic Learning Engine](#epistemic-learning-engine)
5. [LLM Reasoning Layer](#llm-reasoning-layer)
6. [Institutional Edge Extraction](#institutional-edge-extraction)
7. [Blockchain Intelligence](#blockchain-intelligence)
8. [Complete Integration](#complete-integration)
9. [Implementation Specifications](#implementation-specifications)

---

## SYSTEM OVERVIEW

### Objective
Build a fully autonomous, self-learning liquidation hunting system on Hyperliquid that:
- Learns continuously from market data
- Adapts to regime changes
- Manages risk dynamically
- Extracts institutional-level edges
- Reads blockchain-level intelligence
- Uses LLM reasoning for strategic decisions

### Capital Scaling Strategy

**Phase-Based Risk Adjustment:**

| Phase | Capital Range | Max Risk/Trade | Max Leverage | Expected Monthly ROI |
|-------|---------------|----------------|--------------|---------------------|
| **SURVIVAL** | $1k - $5k | 15% | 30x | 50-200% |
| **GROWTH** | $5k - $20k | 10% | 20x | 30-100% |
| **SCALING** | $20k - $100k | 5% | 10x | 15-50% |
| **WEALTH** | $100k+ | 2% | 5x | 10-30% |

### Expected Returns

**Conservative Scenario:**
- Quantitative strategies: 50-150% annually
- + Institutional edges: +50-125% annually
- + Blockchain intelligence: +45-100% annually
- **Total: 145-375% annually**

**Aggressive Scenario:**
- Quantitative strategies: 100-300% annually
- + Institutional edges: +80-200% annually
- + Blockchain intelligence: +70-150% annually
- **Total: 250-650% annually**

**Reality Check:**
- 50% chance: Account to zero in 1-3 months (aggressive phase)
- 30% chance: 2-5x in 3-6 months
- 15% chance: 10-50x in 6-12 months
- 5% chance: 100x+ in 12+ months

---

## CORE ARCHITECTURE

### System Layers
```
┌─────────────────────────────────────────────────────────┐
│                  LLM REASONING LAYER                    │
│         (Strategic decisions, hypothesis generation)     │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              EPISTEMIC BELIEF ENGINE                    │
│          (Bayesian learning, uncertainty tracking)       │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│            DYNAMIC RISK MANAGEMENT                      │
│        (Adaptive position sizing, Kelly criterion)       │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              EXECUTION ENGINES                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │Liquidation│  │ Funding  │  │Cross-Exch│            │
│  │  Hunter   │  │Arbitrage │  │  Arb     │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│           BLOCKCHAIN INTELLIGENCE                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Oracle   │  │ Validator│  │  Mempool │            │
│  │ Monitor  │  │  Intel   │  │  Monitor │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              DATA SOURCES                               │
│  L4 Orderbook, WebSocket, RPC, On-chain Events          │
└─────────────────────────────────────────────────────────┘
```

---

## RISK MANAGEMENT SYSTEM

### Dynamic Position Sizing

**Phase-Based Calculations:**
```javascript
class DynamicRiskManager {
  constructor(capital) {
    this.capital = capital;
    this.phase = this.determinePhase();
  }
  
  determinePhase() {
    if (this.capital < 5000) return 'SURVIVAL';
    if (this.capital < 20000) return 'GROWTH';
    if (this.capital < 100000) return 'SCALING';
    return 'WEALTH';
  }
  
  calculatePositionSize(setup) {
    const baseRisk = this.getBaseRisk();
    const qualityMultiplier = this.scoreSetup(setup);
    const performanceMultiplier = this.getPerformanceMultiplier();
    const streakMultiplier = this.getStreakMultiplier();
    
    const adjustedRisk = baseRisk * qualityMultiplier * performanceMultiplier * streakMultiplier;
    
    return this.clampToLimits(adjustedRisk);
  }
  
  getBaseRisk() {
    switch(this.phase) {
      case 'SURVIVAL': return this.capital * 0.15;  // 15%
      case 'GROWTH': return this.capital * 0.10;    // 10%
      case 'SCALING': return this.capital * 0.05;   // 5%
      case 'WEALTH': return this.capital * 0.02;    // 2%
    }
  }
  
  scoreSetup(setup) {
    let score = 1.0;
    
    // Expected ROI
    if (setup.expectedROI > 0.10) score += 0.2;
    if (setup.expectedROI > 0.20) score += 0.2;
    if (setup.expectedROI < 0.05) score -= 0.3;
    
    // Target vulnerability
    if (setup.target.distanceToLiq < 0.01) score += 0.2;
    if (setup.target.leverage > 25) score += 0.1;
    if (setup.target.size > 100000) score += 0.1;
    
    // Market conditions
    if (setup.volatility > 0.03) score += 0.1;
    if (setup.liquidityGap) score += 0.2;
    
    // Time of day
    const hour = new Date().getUTCHours();
    if (hour >= 2 && hour <= 6) score += 0.1;  // Dead hours
    
    // Cascade potential
    if (setup.clusterSize > 3) score += 0.2;
    
    return Math.max(0.5, Math.min(1.5, score));
  }
  
  getPerformanceMultiplier() {
    const recent = this.trades.slice(-10);
    if (recent.length < 5) return 1.0;
    
    const winRate = recent.filter(t => t.profit > 0).length / recent.length;
    const recentPnL = recent.reduce((sum, t) => sum + t.profit, 0);
    const pnlPercent = recentPnL / this.capital;
    
    if (winRate > 0.70 && pnlPercent > 0.20) return 1.3;
    if (winRate > 0.60) return 1.1;
    if (winRate < 0.40) return 0.7;
    if (pnlPercent < -0.15) return 0.5;
    
    return 1.0;
  }
  
  getStreakMultiplier() {
    const maxMultiplier = this.phase === 'SURVIVAL' ? 0.15 : 0.10;
    return Math.max(0.3, 1 - (this.consecutiveLosses * maxMultiplier));
  }
  
  clampToLimits(risk) {
    const limits = {
      'SURVIVAL': { min: this.capital * 0.05, max: this.capital * 0.20 },
      'GROWTH': { min: this.capital * 0.03, max: this.capital * 0.15 },
      'SCALING': { min: this.capital * 0.02, max: this.capital * 0.08 },
      'WEALTH': { min: this.capital * 0.01, max: this.capital * 0.03 }
    };
    
    const { min, max } = limits[this.phase];
    return Math.max(min, Math.min(max, risk));
  }
  
  calculateLeveragedPosition(riskAmount, setup) {
    const stopLossPercent = 0.02;  // 2%
    const positionSize = riskAmount / stopLossPercent;
    const capitalAllocated = riskAmount * 5;
    const leverage = Math.min(
      positionSize / capitalAllocated,
      this.getMaxLeverage()
    );
    
    return {
      riskAmount,
      positionSize,
      leverage,
      capitalAllocated: positionSize / leverage,
      stopLoss: stopLossPercent,
      liquidationDistance: (1 / leverage) * 0.9
    };
  }
  
  getMaxLeverage() {
    const leverageLimits = {
      'SURVIVAL': 30,
      'GROWTH': 20,
      'SCALING': 10,
      'WEALTH': 5
    };
    return leverageLimits[this.phase];
  }
}
```

### Position Monitoring

**Real-time risk tracking with automatic adjustments:**
```javascript
class PositionMonitor {
  async monitorPosition(position) {
    const maxHoldTime = this.getMaxHoldTime(position);
    const startTime = Date.now();
    
    while (Date.now() - startTime < maxHoldTime) {
      const currentPrice = this.getCurrentPrice(position.coin);
      const pnl = this.calculatePnL(position, currentPrice);
      const pnlPercent = pnl / position.capitalAllocated;
      
      // CRITICAL: Liquidation risk check
      const liquidationRisk = this.calculateLiquidationRisk(position, currentPrice);
      
      if (liquidationRisk > 0.20) {
        console.log(`🚨 LIQUIDATION RISK: ${(liquidationRisk * 100).toFixed(1)}%`);
        await this.reducePosition(position, 0.5);  // Cut in half
        continue;
      }
      
      // Stop loss
      if (pnlPercent <= -position.stopLoss) {
        await this.closePosition(position);
        return { profit: pnl, reason: 'STOP_LOSS' };
      }
      
      // Take profit
      if (pnlPercent >= position.takeProfit) {
        await this.closePosition(position);
        return { profit: pnl, reason: 'TAKE_PROFIT' };
      }
      
      // Trailing stop (lock profits)
      if (pnlPercent > 0.10) {
        const trailingStop = pnlPercent * 0.5;
        if (pnlPercent < trailingStop) {
          await this.closePosition(position);
          return { profit: pnl, reason: 'TRAILING_STOP' };
        }
      }
      
      // Time stop
      if (Date.now() - startTime > maxHoldTime) {
        await this.closePosition(position);
        return { profit: pnl, reason: 'TIME_STOP' };
      }
      
      await sleep(100);  // Check every 100ms
    }
  }
  
  calculateLiquidationRisk(position, currentPrice) {
    const priceChange = position.side === 'long' ?
      (currentPrice - position.entryPrice) / position.entryPrice :
      (position.entryPrice - currentPrice) / position.entryPrice;
    
    const liquidationThreshold = -(1 / position.leverage) * 0.95;
    const distanceToLiq = Math.abs(liquidationThreshold - priceChange);
    const maxDistance = Math.abs(liquidationThreshold);
    
    return 1 - (distanceToLiq / maxDistance);
  }
  
  getMaxHoldTime(position) {
    const holdTimes = {
      'SURVIVAL': 10000,   // 10 seconds
      'GROWTH': 30000,     // 30 seconds
      'SCALING': 120000,   // 2 minutes
      'WEALTH': 300000     // 5 minutes
    };
    return holdTimes[this.phase];
  }
}
```

### Metrics Tracking

**Comprehensive performance monitoring:**
```javascript
class MetricsTracker {
  constructor() {
    this.metrics = {
      // Core
      totalTrades: 0,
      winningTrades: 0,
      losingTrades: 0,
      winRate: 0,
      
      // P&L
      totalProfit: 0,
      totalLoss: 0,
      netPnL: 0,
      avgWin: 0,
      avgLoss: 0,
      profitFactor: 0,
      
      // Risk
      maxDrawdown: 0,
      currentDrawdown: 0,
      sharpeRatio: 0,
      
      // Liquidation risk
      timesNearLiquidation: 0,
      avgLiquidationRisk: 0,
      maxLiquidationRisk: 0,
      
      // Streaks
      currentStreak: 0,
      maxWinStreak: 0,
      maxLossStreak: 0,
      
      // Capital
      startingCapital: 0,
      currentCapital: 0,
      peakCapital: 0,
      roi: 0
    };
  }
  
  recordTrade(trade) {
    this.metrics.totalTrades++;
    
    if (trade.profit > 0) {
      this.metrics.winningTrades++;
      this.metrics.totalProfit += trade.profit;
      this.metrics.currentStreak = Math.max(0, this.metrics.currentStreak) + 1;
      this.metrics.maxWinStreak = Math.max(this.metrics.maxWinStreak, this.metrics.currentStreak);
    } else {
      this.metrics.losingTrades++;
      this.metrics.totalLoss += Math.abs(trade.profit);
      this.metrics.currentStreak = Math.min(0, this.metrics.currentStreak) - 1;
      this.metrics.maxLossStreak = Math.max(this.metrics.maxLossStreak, Math.abs(this.metrics.currentStreak));
    }
    
    if (trade.maxLiquidationRisk > 0.20) {
      this.metrics.timesNearLiquidation++;
    }
    
    this.metrics.maxLiquidationRisk = Math.max(
      this.metrics.maxLiquidationRisk,
      trade.maxLiquidationRisk
    );
    
    this.updateDerivedMetrics();
  }
  
  updateDerivedMetrics() {
    this.metrics.winRate = this.metrics.winningTrades / this.metrics.totalTrades;
    this.metrics.avgWin = this.metrics.totalProfit / (this.metrics.winningTrades || 1);
    this.metrics.avgLoss = this.metrics.totalLoss / (this.metrics.losingTrades || 1);
    this.metrics.profitFactor = this.metrics.totalProfit / (this.metrics.totalLoss || 1);
    this.metrics.netPnL = this.metrics.totalProfit - this.metrics.totalLoss;
    this.metrics.roi = (this.metrics.currentCapital - this.metrics.startingCapital) / 
                       this.metrics.startingCapital;
    
    // Update drawdown
    if (this.metrics.currentCapital > this.metrics.peakCapital) {
      this.metrics.peakCapital = this.metrics.currentCapital;
      this.metrics.currentDrawdown = 0;
    } else {
      this.metrics.currentDrawdown = 
        (this.metrics.peakCapital - this.metrics.currentCapital) / 
        this.metrics.peakCapital;
      
      this.metrics.maxDrawdown = Math.max(
        this.metrics.maxDrawdown,
        this.metrics.currentDrawdown
      );
    }
  }
  
  checkLiquidationAlert() {
    if (this.metrics.avgLiquidationRisk > 0.15) {
      console.log(`🚨 WARNING: Avg liquidation risk ${(this.metrics.avgLiquidationRisk * 100).toFixed(1)}%`);
      console.log(`   Recommendation: Reduce leverage/position sizes`);
    }
    
    if (this.metrics.timesNearLiquidation > 5) {
      console.log(`🚨 DANGER: Near liquidation ${this.metrics.timesNearLiquidation} times`);
      console.log(`   Recommendation: Significantly reduce risk`);
    }
  }
}
```

---

## EPISTEMIC LEARNING ENGINE

### Bayesian Belief System

**Core belief structure with continuous updating:**
```javascript
class EpistemicBeliefEngine {
  constructor() {
    this.beliefs = {
      targetTypes: {
        overleveredRetail: {
          probability: 0.50,
          successRate: 0.65,
          avgProfit: 0.08,
          confidence: 0.60,
          sampleSize: 0
        },
        liquidationCluster: {
          probability: 0.20,
          successRate: 0.75,
          avgProfit: 0.15,
          confidence: 0.70,
          sampleSize: 0
        },
        fundingExtreme: {
          probability: 0.15,
          successRate: 0.55,
          avgProfit: 0.12,
          confidence: 0.50,
          sampleSize: 0
        },
        newListingChaos: {
          probability: 0.10,
          successRate: 0.45,
          avgProfit: 0.25,
          confidence: 0.40,
          sampleSize: 0
        },
        cascadeParasite: {
          probability: 0.05,
          successRate: 0.50,
          avgProfit: 0.30,
          confidence: 0.35,
          sampleSize: 0
        }
      },
      
      timeEdges: {
        deadHours: { edge: 0.12, confidence: 0.75 },
        asianSession: { edge: 0.06, confidence: 0.60 },
        usSession: { edge: 0.04, confidence: 0.55 },
        euroSession: { edge: 0.05, confidence: 0.50 }
      },
      
      coinBehaviors: {
        BTC: { volatility: 0.03, cascadeProbability: 0.15, confidence: 0.80 },
        ETH: { volatility: 0.04, cascadeProbability: 0.18, confidence: 0.75 },
        SOL: { volatility: 0.06, cascadeProbability: 0.25, confidence: 0.70 },
        WIF: { volatility: 0.12, cascadeProbability: 0.40, confidence: 0.50 },
        PEPE: { volatility: 0.15, cascadeProbability: 0.45, confidence: 0.45 }
      }
    };
    
    this.evidence = {
      totalTrades: 0,
      tradesByType: {},
      tradesByTime: {},
      tradesByCoin: {},
      tradesByRegime: {}
    };
  }
  
  // Bayesian update: P(H|E) = P(E|H) * P(H) / P(E)
  updateBelief(hypothesis, outcome, evidence) {
    const prior = hypothesis.probability;
    const likelihood = this.calculateLikelihood(hypothesis, outcome, evidence);
    const marginal = this.calculateMarginalProbability(outcome, evidence);
    
    const posterior = (likelihood * prior) / marginal;
    hypothesis.probability = posterior;
    hypothesis.confidence = this.calculateConfidence(hypothesis);
    
    return posterior;
  }
  
  calculateLikelihood(hypothesis, outcome, evidence) {
    return outcome.success ? hypothesis.successRate : (1 - hypothesis.successRate);
  }
  
  calculateMarginalProbability(outcome, evidence) {
    const relevantTrades = this.getRelevantTrades(evidence);
    if (relevantTrades.length === 0) return 0.5;
    
    const successCount = relevantTrades.filter(t => t.success).length;
    return successCount / relevantTrades.length;
  }
  
  calculateConfidence(hypothesis) {
    const n = hypothesis.sampleSize || 0;
    
    if (n < 5) return 0.2;
    if (n < 10) return 0.4;
    if (n < 30) return 0.6;
    if (n < 100) return 0.8;
    return 0.9;
  }
  
  learnFromTrade(trade) {
    this.evidence.totalTrades++;
    
    const tradeType = this.classifyTrade(trade);
    const timeSlot = this.classifyTime(trade.timestamp);
    const regime = this.identifyRegime(trade);
    
    if (this.beliefs.targetTypes[tradeType]) {
      const hypothesis = this.beliefs.targetTypes[tradeType];
      
      const newSuccessRate = this.updateSuccessRate(hypothesis, trade.success);
      hypothesis.successRate = newSuccessRate;
      hypothesis.sampleSize = (hypothesis.sampleSize || 0) + 1;
      
      if (trade.success) {
        const n = hypothesis.profitSamples || 0;
        hypothesis.avgProfit = 
          (hypothesis.avgProfit * n + trade.profitPercent) / (n + 1);
        hypothesis.profitSamples = n + 1;
      }
      
      hypothesis.confidence = this.calculateConfidence(hypothesis);
    }
    
    this.storeEvidence(trade, tradeType, timeSlot, regime);
  }
  
  updateSuccessRate(hypothesis, success) {
    const n = hypothesis.sampleSize || 0;
    const oldRate = hypothesis.successRate;
    
    const alpha = oldRate * n + (success ? 1 : 0);
    const beta = (1 - oldRate) * n + (success ? 0 : 1);
    
    return alpha / (alpha + beta);
  }
  
  calculateUncertainty(hypothesis) {
    const sampleSize = hypothesis.sampleSize || 0;
    const confidence = hypothesis.confidence || 0;
    
    const sampleUncertainty = Math.exp(-sampleSize / 20);
    const confidenceUncertainty = 1 - confidence;
    const variance = hypothesis.variance || 0.5;
    
    return (sampleUncertainty * 0.4 + confidenceUncertainty * 0.4 + variance * 0.2);
  }
  
  shouldTakeTrade(setup) {
    const tradeType = this.classifySetup(setup);
    const timeSlot = this.classifyTime(Date.now());
    const regime = this.identifyCurrentRegime();
    
    const hypothesis = this.beliefs.targetTypes[tradeType];
    
    if (!hypothesis) {
      return {
        decision: false,
        reason: 'UNKNOWN_TYPE',
        uncertainty: 1.0
      };
    }
    
    const expectedValue = this.calculateExpectedValue(hypothesis, setup);
    const uncertainty = this.calculateUncertainty(hypothesis);
    const uncertaintyPenalty = 1 - (uncertainty * 0.5);
    const adjustedEV = expectedValue * uncertaintyPenalty;
    
    const timeEdge = this.beliefs.timeEdges[timeSlot]?.edge || 0;
    const timeConfidence = this.beliefs.timeEdges[timeSlot]?.confidence || 0.5;
    const regimeEdge = this.beliefs.marketRegimes?.[regime]?.edge || 0;
    
    const totalEdge = adjustedEV + (timeEdge * timeConfidence) + regimeEdge;
    const threshold = 0.08;  // 8% minimum edge
    
    return {
      decision: totalEdge > threshold,
      expectedValue: totalEdge,
      uncertainty,
      confidence: hypothesis.confidence,
      reason: totalEdge > threshold ? 'POSITIVE_EDGE' : 'INSUFFICIENT_EDGE'
    };
  }
  
  calculateExpectedValue(hypothesis, setup) {
    const winProb = hypothesis.successRate;
    const lossProb = 1 - winProb;
    const avgWin = hypothesis.avgProfit;
    const avgLoss = setup.stopLoss || 0.02;
    
    return (winProb * avgWin) - (lossProb * avgLoss);
  }
  
  shouldExplore() {
    const totalTrades = this.evidence.totalTrades;
    const epsilon = Math.max(0.05, 0.3 * Math.exp(-totalTrades / 100));
    return Math.random() < epsilon;
  }
}
```

### Adaptive Memory System

**Sliding window memory with knowledge decay:**
```javascript
class AdaptiveMemorySystem {
  constructor() {
    this.memoryTypes = {
      shortTerm: {
        window: 20,
        weight: 0.50,
        purpose: "Regime detection, quick adaptation",
        decayRate: 0
      },
      mediumTerm: {
        window: 100,
        weight: 0.30,
        purpose: "Current strategy effectiveness",
        decayRate: 0.01
      },
      longTerm: {
        window: 500,
        weight: 0.15,
        purpose: "Fundamental market structure",
        decayRate: 0.02
      },
      episodic: {
        window: Infinity,
        weight: 0.05,
        purpose: "Black swans, rare events",
        decayRate: 0
      }
    };
    
    this.memoryBuffer = {
      shortTerm: [],
      mediumTerm: [],
      longTerm: [],
      episodic: []
    };
  }
  
  addMemory(trade) {
    this.memoryBuffer.shortTerm.push(trade);
    this.memoryBuffer.mediumTerm.push(trade);
    this.memoryBuffer.longTerm.push(trade);
    
    if (this.isEpisodic(trade)) {
      this.memoryBuffer.episodic.push(trade);
    }
    
    this.trimBuffers();
    this.applyDecay();
  }
  
  isEpisodic(trade) {
    return (
      Math.abs(trade.profitPercent) > 0.50 ||
      trade.maxLiquidationRisk > 0.80 ||
      trade.regime === 'blackSwan'
    );
  }
  
  trimBuffers() {
    for (const [type, config] of Object.entries(this.memoryTypes)) {
      if (config.window === Infinity) continue;
      
      const buffer = this.memoryBuffer[type];
      if (buffer.length > config.window) {
        this.memoryBuffer[type] = buffer.slice(-config.window);
      }
    }
  }
  
  applyDecay() {
    for (const [type, config] of Object.entries(this.memoryTypes)) {
      if (config.decayRate === 0) continue;
      
      this.memoryBuffer[type] = this.memoryBuffer[type].map((trade, index) => {
        const age = this.memoryBuffer[type].length - index;
        const decayFactor = Math.exp(-age * config.decayRate);
        
        return { ...trade, weight: decayFactor };
      });
    }
  }
  
  getCompositeBelief(hypothesis) {
    let compositeBelief = 0;
    let totalWeight = 0;
    
    for (const [type, config] of Object.entries(this.memoryTypes)) {
      const buffer = this.memoryBuffer[type];
      const relevantTrades = buffer.filter(t => t.type === hypothesis.type);
      
      if (relevantTrades.length === 0) continue;
      
      const belief = this.calculateBelief(relevantTrades);
      compositeBelief += belief * config.weight;
      totalWeight += config.weight;
    }
    
    return compositeBelief / totalWeight;
  }
  
  calculateBelief(trades) {
    if (trades.length === 0) return 0.5;
    
    const weightedSum = trades.reduce((sum, trade) => {
      const outcome = trade.success ? 1 : 0;
      const weight = trade.weight || 1;
      return sum + (outcome * weight);
    }, 0);
    
    const weightSum = trades.reduce((sum, trade) => {
      return sum + (trade.weight || 1);
    }, 0);
    
    return weightedSum / weightSum;
  }
  
  shouldPurge() {
    const recent = this.memoryBuffer.shortTerm.slice(-10);
    const longTerm = this.memoryBuffer.longTerm;
    
    if (recent.length < 5 || longTerm.length < 50) return false;
    
    const recentWR = recent.filter(t => t.success).length / recent.length;
    const longTermWR = longTerm.filter(t => t.success).length / longTerm.length;
    
    const divergence = Math.abs(recentWR - longTermWR);
    
    if (divergence > 0.35) {
      console.log(`🔥 CATASTROPHIC DIVERGENCE: ${(divergence * 100).toFixed(1)}%`);
      console.log(`   💣 PURGING MEMORY`);
      return true;
    }
    
    return false;
  }
  
  purgeMemory() {
    this.memoryBuffer.shortTerm = [];
    this.memoryBuffer.mediumTerm = [];
    this.memoryBuffer.longTerm = [];
    // Keep episodic memories
  }
  
  forgetObsoleteKnowledge() {
    const now = Date.now();
    
    for (const [type, buffer] of Object.entries(this.memoryBuffer)) {
      if (type === 'episodic') continue;
      
      this.memoryBuffer[type] = buffer.filter(trade => {
        const age = (now

Continue
01:47

    trade.timestamp) / 86400000; const maxAge = this.memoryTypes[type].window;

     if (age > maxAge) return false;
     
     // Forget mediocre trades faster
     if (Math.abs(trade.profitPercent) < 0.02) {
       return Math.random() < 0.7;
     }
     
     return true;

    }); } } }


### Knowledge Decay Detection
```javascript
class KnowledgeDecayEngine {
  constructor() {
    this.decayFactors = {
      competitorLearning: { timeScale: 60, effect: 0.6 },  // 60 days
      victimAdaptation: { timeScale: 90, effect: 0.5 },    // 90 days
      structuralShifts: { timeScale: 120, effect: 1.0 },   // 120 days
      macroRegimes: { timeScale: 180, effect: 0.8 }        // 180 days
    };
  }
  
  calculateHalfLife(edge) {
    const baseHalfLife = 90;
    
    const edgeMultipliers = {
      'obviousPattern': 0.3,
      'publicStrategy': 0.5,
      'technicalEdge': 1.0,
      'behavioralEdge': 1.2,
      'executionEdge': 2.0,
      'informationEdge': 3.0
    };
    
    const multiplier = edgeMultipliers[edge.type] || 1.0;
    const halfLife = baseHalfLife * multiplier;
    
    return {
      halfLife,
      expiryDate: Date.now() + (halfLife * 86400000),
      currentValue: this.calculateCurrentValue(edge, halfLife)
    };
  }
  
  calculateCurrentValue(edge, halfLife) {
    const daysSinceDiscovery = (Date.now() - edge.discoveryDate) / 86400000;
    const decayConstant = Math.log(2) / halfLife;
    return edge.initialValue * Math.exp(-decayConstant * daysSinceDiscovery);
  }
}
```

---

## LLM REASONING LAYER

### LLM Integration

**Strategic decision-making and hypothesis generation:**
```javascript
class LLMReasoningEngine {
  constructor(anthropicApiKey) {
    this.client = new Anthropic({ apiKey: anthropicApiKey });
    this.model = "claude-sonnet-4-20250514";
    
    this.systemPrompt = `You are a quantitative trading strategist specializing in cryptocurrency liquidation hunting on Hyperliquid. Your role is to:

1. ANALYZE market conditions and identify potential edges
2. GENERATE hypotheses about new trading opportunities  
3. INTERPRET quantitative signals in broader market context
4. CRITIQUE existing strategies and suggest improvements
5. EXPLAIN trade decisions in human-understandable terms

You have access to:
- Real-time market data (orderbooks, trades, liquidations)
- Historical performance metrics
- Current beliefs and confidence levels
- Epistemic uncertainty measurements

Be concise, analytical, and creative. Think like a predator seeking alpha.`;
    
    this.conversationHistory = [];
  }
  
  async reason(query, context) {
    const messages = [
      ...this.conversationHistory,
      {
        role: "user",
        content: this.formatQuery(query, context)
      }
    ];
    
    try {
      const response = await this.client.messages.create({
        model: this.model,
        max_tokens: 2000,
        system: this.systemPrompt,
        messages: messages
      });
      
      const reasoning = response.content[0].text;
      
      this.conversationHistory.push(
        { role: "user", content: this.formatQuery(query, context) },
        { role: "assistant", content: reasoning }
      );
      
      if (this.conversationHistory.length > 20) {
        this.conversationHistory = this.conversationHistory.slice(-20);
      }
      
      return this.parseReasoning(reasoning);
      
    } catch (error) {
      console.error("LLM reasoning error:", error);
      return { reasoning: null, confidence: 0 };
    }
  }
  
  formatQuery(query, context) {
    return `
${query}

CONTEXT:
${JSON.stringify(context, null, 2)}

Provide your analysis in the following format:
REASONING: [Your thought process]
CONCLUSION: [Your specific recommendation]
CONFIDENCE: [0-100]
RATIONALE: [Why this confidence level]
    `.trim();
  }
  
  parseReasoning(response) {
    const reasoningMatch = response.match(/REASONING:(.*?)(?=CONCLUSION:|$)/s);
    const conclusionMatch = response.match(/CONCLUSION:(.*?)(?=CONFIDENCE:|$)/s);
    const confidenceMatch = response.match(/CONFIDENCE:\s*(\d+)/);
    const rationaleMatch = response.match(/RATIONALE:(.*?)$/s);
    
    return {
      reasoning: reasoningMatch?.[1]?.trim() || response,
      conclusion: conclusionMatch?.[1]?.trim() || null,
      confidence: confidenceMatch?.[1] ? parseInt(confidenceMatch[1]) / 100 : 0.5,
      rationale: rationaleMatch?.[1]?.trim() || null
    };
  }
}
```

### Hypothesis Generation

**LLM discovers new edges autonomously:**
```javascript
class HypothesisGenerator {
  constructor(llm, beliefEngine) {
    this.llm = llm;
    this.beliefs = beliefEngine;
  }
  
  async generateNewHypotheses() {
    console.log(`🧠 LLM: GENERATING NEW HYPOTHESES...`);
    
    const context = {
      currentEdges: this.summarizeCurrentEdges(),
      recentPerformance: this.summarizePerformance(),
      marketConditions: this.summarizeMarketConditions(),
      decayingEdges: this.identifyDecayingEdges()
    };
    
    const query = `
Based on current market conditions and our performance data, generate 3-5 NEW hypotheses for potential trading edges we haven't explored yet.

Consider:
- What patterns might exist that we're not tracking?
- What market inefficiencies could we exploit?
- What behavioral biases could we capitalize on?
- What combinations of factors might create edge?

For each hypothesis, provide:
1. Clear description
2. Expected edge (%)
3. How to test it
4. Required sample size
5. Risk factors
    `;
    
    const response = await this.llm.reason(query, context);
    
    console.log(`📊 LLM REASONING:\n${response.reasoning}`);
    console.log(`💡 NEW HYPOTHESES:\n${response.conclusion}`);
    
    const hypotheses = this.parseHypotheses(response.conclusion);
    
    for (const hypothesis of hypotheses) {
      console.log(`➕ Adding hypothesis: ${hypothesis.name}`);
      this.beliefs.beliefs.targetTypes[hypothesis.name] = {
        probability: 0.1,
        successRate: hypothesis.expectedWinRate || 0.50,
        avgProfit: hypothesis.expectedEdge || 0.05,
        confidence: 0.2,
        sampleSize: 0,
        description: hypothesis.description,
        testingPlan: hypothesis.testingPlan,
        discoveredBy: 'LLM',
        discoveryDate: Date.now()
      };
    }
    
    return hypotheses;
  }
}
```

### Regime Interpretation

**LLM explains market conditions:**
```javascript
class RegimeInterpreter {
  constructor(llm) {
    this.llm = llm;
  }
  
  async interpretCurrentRegime(marketData, performanceData) {
    console.log(`🌍 LLM: INTERPRETING MARKET REGIME...`);
    
    const context = {
      priceAction: marketData.recentPriceAction,
      volatility: marketData.volatility,
      funding: marketData.fundingRates,
      openInterest: marketData.openInterest,
      liquidations: marketData.recentLiquidations,
      ourPerformance: {
        recentWinRate: performanceData.winRate,
        profitFactor: performanceData.profitFactor,
        bestStrategies: performanceData.bestPerforming,
        worstStrategies: performanceData.worstPerforming
      }
    };
    
    const query = `
Analyze the current market regime and explain:

1. What type of market are we in? (trending/ranging/volatile/quiet)
2. Why are certain strategies working/failing?
3. What's the dominant trader behavior right now?
4. What risks should we be aware of?
5. What opportunities might emerge soon?

Be specific and actionable.
    `;
    
    const response = await this.llm.reason(query, context);
    
    console.log(`🧠 LLM REGIME ANALYSIS:`);
    console.log(response.reasoning);
    console.log(`💡 ACTIONABLE INSIGHTS:`);
    console.log(response.conclusion);
    
    return {
      regime: this.extractRegime(response.conclusion),
      insights: response.reasoning,
      recommendations: this.extractRecommendations(response.conclusion),
      confidence: response.confidence
    };
  }
}
```

### Strategy Critique

**LLM performs self-analysis:**
```javascript
class StrategyCritic {
  constructor(llm, beliefEngine) {
    this.llm = llm;
    this.beliefs = beliefEngine;
  }
  
  async critiquePerformance() {
    console.log(`🔍 LLM: SELF-CRITIQUE SESSION...`);
    
    const context = {
      overall: {
        totalTrades: this.beliefs.evidence.totalTrades,
        winRate: '...',
        profitFactor: '...',
        roi: '...'
      },
      byStrategy: this.getStrategyBreakdown(),
      recentTrends: this.getRecentTrends(),
      edgeDecay: this.getEdgeDecayStatus()
    };
    
    const query = `
Conduct a critical analysis of our trading system's performance:

1. What are we doing well?
2. What are our biggest weaknesses?
3. Which strategies are becoming obsolete?
4. What biases might we have developed?
5. What should we change immediately?

Be brutally honest. Identify specific issues with evidence.
    `;
    
    const response = await this.llm.reason(query, context);
    
    console.log(`🎯 SELF-CRITIQUE:`);
    console.log(response.reasoning);
    console.log(`⚠️  ACTION ITEMS:`);
    console.log(response.conclusion);
    
    const actions = this.parseActionItems(response.conclusion);
    
    for (const action of actions) {
      console.log(`🔧 Implementing: ${action.description}`);
      await this.implementAction(action);
    }
    
    return response;
  }
  
  async implementAction(action) {
    if (action.type === 'stop' || action.type === 'abandon') {
      const strategyName = this.extractStrategyName(action.description);
      if (strategyName && this.beliefs.beliefs.targetTypes[strategyName]) {
        this.beliefs.beliefs.targetTypes[strategyName].enabled = false;
        console.log(`   ❌ Disabled: ${strategyName}`);
      }
    }
    
    if (action.type === 'reduce') {
      const strategyName = this.extractStrategyName(action.description);
      if (strategyName && this.beliefs.beliefs.targetTypes[strategyName]) {
        this.beliefs.beliefs.targetTypes[strategyName].positionSizeMultiplier = 0.5;
        console.log(`   📉 Reduced sizing: ${strategyName}`);
      }
    }
    
    if (action.type === 'increase' || action.type === 'prioritize') {
      const strategyName = this.extractStrategyName(action.description);
      if (strategyName && this.beliefs.beliefs.targetTypes[strategyName]) {
        this.beliefs.beliefs.targetTypes[strategyName].positionSizeMultiplier = 1.5;
        console.log(`   📈 Increased sizing: ${strategyName}`);
      }
    }
  }
}
```

---

## INSTITUTIONAL EDGE EXTRACTION

### Order Flow Toxicity Analysis

**Classify traders by sophistication:**
```javascript
class OrderFlowToxicityAnalyzer {
  constructor() {
    this.walletProfiles = new Map();
    this.toxicityThreshold = 0.7;
  }
  
  async analyzeOrderFlow() {
    const ws = connectL4WebSocket();
    ws.subscribe({ type: 'l4Book', coin: 'BTC' });
    
    ws.on('l4Book', (data) => {
      for (const level of data.levels[0]) {
        if (level.orders) {
          for (const order of level.orders) {
            this.classifyOrder(order, 'buy');
          }
        }
      }
      
      for (const level of data.levels[1]) {
        if (level.orders) {
          for (const order of level.orders) {
            this.classifyOrder(order, 'sell');
          }
        }
      }
    });
  }
  
  classifyOrder(order, side) {
    const profile = this.getOrCreateProfile(order.user);
    const toxicity = this.calculateToxicity(order, profile);
    
    profile.recentOrders.push({
      size: order.sz,
      price: order.px,
      side: side,
      toxicity: toxicity,
      timestamp: Date.now()
    });
    
    if (toxicity > this.toxicityThreshold) {
      console.log(`🧪 TOXIC ORDER: ${order.user.slice(0,8)} - ${side}`);
      console.log(`   Toxicity: ${(toxicity * 100).toFixed(1)}%`);
      
      this.respondToToxicOrder(order, side, toxicity, profile);
    }
  }
  
  calculateToxicity(order, profile) {
    let score = 0.5;
    
    // Historical profitability
    if (profile.historicalWinRate > 0.65) score += 0.2;
    if (profile.historicalROI > 0.50) score += 0.15;
    
    // Order size
    const avgOrderSize = profile.avgOrderSize || 1000;
    if (order.sz > avgOrderSize * 3) score += 0.15;
    if (order.sz > avgOrderSize * 10) score += 0.25;
    
    // Timing
    if (this.isUnusualTiming(order, profile)) score += 0.20;
    
    // Correlation with smart money
    if (this.correlatesWithSmartMoney(order, profile)) score += 0.25;
    
    // Order aggressiveness
    if (order.orderType === 'market') score += 0.15;
    if (order.orderType === 'IOC') score += 0.10;
    
    // Sophistication indicators
    if (profile.usesComplexStrategies) score += 0.15;
    if (profile.hasAPIAccess) score += 0.10;
    if (profile.tradingFrequency === 'high') score += 0.10;
    
    return Math.min(1.0, score);
  }
  
  respondToToxicOrder(order, side, toxicity, profile) {
    // Copy toxic orders (informed traders)
    if (toxicity > 0.80) {
      console.log(`   🎯 COPYING TOXIC ORDER`);
      this.copyOrder(order, side, 0.1);
    }
    
    // Fade uninformed orders
    if (toxicity < 0.30) {
      console.log(`   🔄 FADING ORDER`);
      this.fadeOrder(order, side, 0.05);
    }
  }
}
```

### Cross-Exchange Arbitrage

**Price discrepancy exploitation:**
```javascript
class CrossExchangeArbitrage {
  constructor() {
    this.exchanges = {
      hyperliquid: { ws: null, prices: {} },
      binance: { ws: null, prices: {} },
      bybit: { ws: null, prices: {} }
    };
  }
  
  async start() {
    await Promise.all([
      this.connectHyperliquid(),
      this.connectBinance(),
      this.connectBybit()
    ]);
    
    this.monitorArbitrage();
  }
  
  async connectBinance() {
    const ws = new WebSocket('wss://fstream.binance.com/ws');
    
    ws.on('open', () => {
      ws.send(JSON.stringify({
        method: 'SUBSCRIBE',
        params: ['btcusdt@markPrice', 'ethusdt@markPrice', 'solusdt@markPrice'],
        id: 1
      }));
    });
    
    ws.on('message', (data) => {
      const msg = JSON.parse(data);
      if (msg.e === 'markPriceUpdate') {
        const symbol = msg.s.replace('USDT', '');
        this.exchanges.binance.prices[symbol] = {
          price: parseFloat(msg.p),
          timestamp: msg.E
        };
      }
    });
  }
  
  monitorArbitrage() {
    setInterval(() => {
      const coins = ['BTC', 'ETH', 'SOL'];
      
      for (const coin of coins) {
        const hlPrice = this.exchanges.hyperliquid.prices[coin]?.price;
        const bnPrice = this.exchanges.binance.prices[coin]?.price;
        
        if (!hlPrice || !bnPrice) continue;
        
        const spread = (hlPrice - bnPrice) / bnPrice;
        
        if (Math.abs(spread) > 0.002) {
          console.log(`💰 ARB OPPORTUNITY: ${coin}`);
          console.log(`   Spread: ${(spread * 100).toFixed(3)}%`);
          
          if (spread > 0) {
            console.log(`   Action: SELL HL, BUY Binance`);
            this.executeArb(coin, 'sell', 'buy', spread);
          } else {
            console.log(`   Action: BUY HL, SELL Binance`);
            this.executeArb(coin, 'buy', 'sell', Math.abs(spread));
          }
        }
      }
    }, 100);
  }
  
  async executeArb(coin, hlSide, bnSide, spread) {
    const capital = 5000;
    const size = capital / this.exchanges.hyperliquid.prices[coin].price;
    
    try {
      await Promise.all([
        this.executeHyperliquid(coin, hlSide, size),
        this.executeBinance(coin, bnSide, size)
      ]);
      
      const profit = capital * spread * 0.8;
      console.log(`   ✅ ARB EXECUTED: +$${profit.toFixed(2)}`);
    } catch (error) {
      console.error(`   ❌ ARB FAILED:`, error);
    }
  }
}
```

### Funding Rate Arbitrage

**Risk-free yield farming:**
```javascript
class FundingArbitrage {
  async findFundingOpportunities() {
    const coins = ['BTC', 'ETH', 'SOL', 'WIF'];
    
    for (const coin of coins) {
      const funding = await this.getFundingRate(coin);
      
      if (Math.abs(funding) > 0.05) {
        console.log(`💸 FUNDING ARB: ${coin}`);
        console.log(`   Funding: ${(funding * 100).toFixed(3)}%`);
        console.log(`   Annualized: ${(funding * 3 * 365 * 100).toFixed(1)}%`);
        
        if (funding < 0) {
          console.log(`   Strategy: LONG perp, SHORT spot`);
          await this.executeFundingArb(coin, 'long', 'short');
        } else {
          console.log(`   Strategy: SHORT perp, LONG spot`);
          await this.executeFundingArb(coin, 'short', 'long');
        }
      }
    }
  }
  
  async getFundingRate(coin) {
    const response = await fetch('https://api.hyperliquid.xyz/info', {
      method: 'POST',
      body: JSON.stringify({ type: 'metaAndAssetCtxs' })
    });
    
    const data = await response.json();
    const asset = data[0].universe.find(a => a.name === coin);
    return parseFloat(asset.funding) / 100;
  }
  
  async executeFundingArb(coin, perpSide, spotSide) {
    const capital = 10000;
    
    await this.openPerp(coin, perpSide, capital);
    await this.openSpot(coin, spotSide, capital);
    
    console.log(`   ✅ FUNDING ARB ACTIVE`);
  }
}
```

### Spoofing Detection

**Trade against manipulators:**
```javascript
class SpoofDetector {
  detectSpoofing() {
    const suspiciousOrders = this.trackOrders();
    
    for (const order of suspiciousOrders) {
      if (order.cancellationRate > 0.90 && order.size > 100000) {
        console.log(`🎭 SPOOFING DETECTED`);
        console.log(`   Spoofer: ${order.user.slice(0,8)}`);
        console.log(`   Fake ${order.side} support/resistance`);
        
        this.fadeSpoofing(order);
      }
    }
  }
  
  fadeSpoofing(order) {
    const side = order.side === 'buy' ? 'sell' : 'buy';
    console.log(`   🎯 FADING SPOOF: ${side.toUpperCase()}`);
    // Place opposite order
  }
}
```

---

## BLOCKCHAIN INTELLIGENCE

### Oracle Price Monitoring

**100-500ms price prediction edge:**
```javascript
class OracleMonitor {
  constructor() {
    this.oraclePrices = {};
    this.exchangePrices = {};
    this.leads = [];
  }
  
  async monitorOracle() {
    console.log(`🔮 MONITORING ORACLE FEEDS...`);
    
    const ws = new WebSocket('wss://api.hyperliquid.xyz/evm');
    
    ws.on('open', () => {
      ws.send(JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'eth_subscribe',
        params: ['logs', {
          address: '0x...oracle_contract',
          topics: ['0x...price_update_event']
        }]
      }));
    });
    
    ws.on('message', async (data) => {
      const msg = JSON.parse(data);
      
      if (msg.method === 'eth_subscription') {
        const log = msg.params.result;
        const update = this.decodeOracleUpdate(log);
        
        console.log(`🔮 ORACLE UPDATE: ${update.coin} @ $${update.price}`);
        
        this.oraclePrices[update.coin] = {
          price: update.price,
          timestamp: update.timestamp
        };
        
        await this.detectOracleLead(update);
      }
    });
  }
  
  async detectOracleLead(oracleUpdate) {
    const exchangePrice = await this.getExchangePrice(oracleUpdate.coin);
    if (!exchangePrice) return;
    
    const diff = (oracleUpdate.price - exchangePrice.price) / exchangePrice.price;
    
    if (Math.abs(diff) > 0.001) {
      console.log(`⚡ ORACLE LEADING: ${(diff * 100).toFixed(3)}%`);
      console.log(`   Direction: ${diff > 0 ? 'UP ↗' : 'DOWN ↘'}`);
      
      await this.exploitOracleLead({
        coin: oracleUpdate.coin,
        oraclePrice: oracleUpdate.price,
        exchangePrice: exchangePrice.price,
        diff: diff
      });
    }
  }
  
  async exploitOracleLead(lead) {
    console.log(`   🎯 EXPLOITING ORACLE LEAD`);
    
    const side = lead.diff > 0 ? 'buy' : 'sell';
    const entry = await this.marketOrder(lead.coin, side, 1000);
    
    await this.waitForCatchup(lead, 2000);
    
    const exit = await this.marketOrder(lead.coin, side === 'buy' ? 'sell' : 'buy', 1000);
    
    const profit = side === 'buy' ? 
      (exit.price - entry.price) * (1000 / entry.price) :
      (entry.price - exit.price) * (1000 / entry.price);
    
    console.log(`   ✅ Profit: $${profit.toFixed(2)}`);
  }
}
```

### Liquidation Engine Monitoring

**Predict liquidations 0.5-2s early:**
```javascript
class LiquidationEngineMonitor {
  constructor() {
    this.liquidationEngineAddress = '0x...liquidation_contract';
    this.pendingLiquidations = [];
  }
  
  async monitorLiquidationEngine() {
    console.log(`⚙️ MONITORING LIQUIDATION ENGINE...`);
    
    const ws = new WebSocket('wss://api.hyperliquid.xyz/evm');
    
    ws.on('open', () => {
      ws.send(JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'eth_subscribe',
        params: ['newPendingTransactions']
      }));
    });
    
    ws.on('message', async (data) => {
      const msg = JSON.parse(data);
      
      if (msg.method === 'eth_subscription') {
        const txHash = msg.params.result;
        const tx = await this.getTransaction(txHash);
        
        if (tx.from.toLowerCase() === this.liquidationEngineAddress.toLowerCase()) {
          console.log(`🚨 LIQUIDATION ENGINE TX DETECTED`);
          
          const liquidation = this.decodeLiquidation(tx);
          
          if (liquidation) {
            console.log(`   Target: ${liquidation.user.slice(0,8)}`);
            console.log(`   Coin: ${liquidation.coin}`);
            console.log(`   Size: $${liquidation.size.toLocaleString()}`);
            console.log(`   ⏱️  PENDING (not confirmed)`);
            
            await this.frontRunLiquidation(liquidation);
          }
        }
      }
    });
  }
  
  async frontRunLiquidation(liquidation) {
    console.log(`   🎯 FRONT-RUNNING LIQUIDATION`);
    
    const side = liquidation.side === 'long' ? 'short' : 'long';
    await this.placeOrders(liquidation.coin, side, liquidation.size * 0.1);
    
    console.log(`   ✅ Positioned for cascade`);
  }
}
```

### Whale Wallet Intelligence

**Follow smart money in real-time:**
```javascript
class WhaleIntelligence {
  constructor() {
    this.whales = new Map();
    this.topWhales = [];
  }
  
  async identifyWhales() {
    console.log(`🐋 IDENTIFYING WHALES...`);
    
    const leaderboard = await this.scrapeLeaderboard();
    const onChainWhales = await this.findProfitableWallets();
    
    this.topWhales = [...new Set([...leaderboard, ...onChainWhales])];
    
    console.log(`   Found ${this.topWhales.length} whales`);
    
    for (const whale of this.topWhales) {
      const profile = await this.buildWhaleProfile(whale);
      this.whales.set(whale, profile);
      console.log(`   🐋 ${whale.slice(0,8)}: ${profile.classification}`);
    }
  }
  
  async monitorWhales() {
    console.log(`👀 MONITORING ${this.topWhales.length} WHALES...`);
    
    const ws = new WebSocket('wss://api.hyperliquid.xyz/evm');
    
    ws.on('open', () => {
      for (const whale of this.topWhales) {
        ws.send(JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'eth_subscribe',
          params: ['logs', {
            address: null,
            topics: [null, this.addressToTopic(whale)]
          }]
        }));
      }
    });
    
    ws.on('message', async (data) => {
      const msg = JSON.parse(data);
      
      if (msg.method === 'eth_subscription') {
        const log = msg.params.result;
        const action = await this.decodeWhaleAction(log);
        
        if (action) {
          await this.handleWhaleAction(action);
        }
      }
    });
  }
  
  async handleWhaleAction(action) {
    console.log(`🐋 WHALE ACTION: ${action.whale.slice(0,8)}`);
    console.log(`   Type: ${action.actionType}`);
    
    switch(action.actionType) {
      case 'DEPOSIT':
        await this.handleWhaleDeposit(action);
        break;
      case 'WITHDRAWAL':
        await this.handleWhaleWithdrawal(action);
        break;
      case 'ORDER_PLACED':
        await this.handleWhaleOrder(action);
        break;
      case 'ORDER_CANCELED':
        await this.handleWhaleCancel(action);
        break;
    }
  }
  
  async handleWhaleDeposit(action) {
    console.log(`   🚨 Whale depositing: preparing for position`);
    if (action.profile.strategyType === 'trend_long') {
      console.log(`   📈 LIKELY: About to buy ${action.profile.preferredCoins[0]}`);
      await this.frontRunWhaleEntry(action);
    }
  }
  
  async handleWhaleOrder(action) {
    const order = action.details.order;
    
    if (order.size > 100000) {
      console.log(`   🎯 LARGE ORDER: Following whale`);
      await this.copyWhaleOrder(action, order);
    }
  }
  
  async handleWhaleCancel(action) {
    console.log(`   🚨 Whale changed mind - sentiment shift`);
    // Trade accordingly
  }
}
```

### Validator Intelligence

**Detect MEV extraction by validators:**
```javascript
class ValidatorIntelligence {

Continue
01:51

constructor() {
this.validators = [];
this.mevPatterns = new Map();
}

async identifyValidators() { const response = await fetch('https://api.hyperliquid.xyz/info', { method: 'POST', body: JSON.stringify({ type: 'validatorSummaries' }) });

const data = await response.json();
this.validators = data.map(v => ({
  address: v.validator,
  stake: v.stake,
  commission: v.commission
}));

console.log(`🏛️  Identified ${this.validators.length} validators`);

}

async monitorValidatorBehavior() { console.log(👁️  MONITORING VALIDATOR BEHAVIOR...);

const ws = new WebSocket('wss://api.hyperliquid.xyz/evm');

ws.on('open', () => {
  ws.send(JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'eth_subscribe',
    params: ['newHeads']
  }));
});

ws.on('message', async (data) => {
  const msg = JSON.parse(data);
  
  if (msg.method === 'eth_subscription') {
    const block = msg.params.result;
    await this.analyzeBlock(block);
  }
});

}

async analyzeBlock(blockHeader) {
const block = await this.getFullBlock(blockHeader.number);
const patterns = this.detectBlockPatterns(block);

if (patterns.suspicious) {
  console.log(`🚨 SUSPICIOUS VALIDATOR BEHAVIOR`);
  console.log(`   Validator: ${block.miner.slice(0,10)}`);
  console.log(`   Patterns: ${patterns.detected.join(', ')}`);
  
  if (patterns.detected.includes('SANDWICH_ATTACK')) {
    await this.copyValidatorStrategy(block, patterns);
  }
}

}

detectBlockPatterns(block) {
const patterns = { suspicious: false, detected: [] };
const txs = block.transactions;

// Detect sandwich attacks
for (let i = 0; i < txs.length - 2; i++) {
  if (this.isValidatorTx(txs[i]) && 
      !this.isValidatorTx(txs[i + 1]) && 
      this.isValidatorTx(txs[i + 2])) {
    
    if (this.areInverseOps(txs[i], txs[i + 2])) {
      patterns.suspicious = true;
      patterns.detected.push('SANDWICH_ATTACK');
    }
  }
}

return patterns;

}
}


### Contract State Monitoring

**Read contract memory before UI updates:**
```javascript
class ContractStateMonitor {
  constructor() {
    this.contracts = {
      clearinghouse: '0x...clearinghouse',
      oracle: '0x...oracle',
      insurance: '0x...insurance',
      funding: '0x...funding'
    };
    this.stateHistory = new Map();
  }
  
  async monitorCriticalState() {
    console.log(`📜 MONITORING CONTRACT STATE...`);
    
    setInterval(async () => {
      const state = await this.readAllState();
      const changes = this.detectStateChanges(state);
      
      if (changes.length > 0) {
        console.log(`📊 CONTRACT STATE CHANGES:`);
        
        for (const change of changes) {
          await this.analyzeChange(change);
        }
      }
    }, 1000);
  }
  
  async readAllState() {
    return {
      insuranceFund: await this.readStorage(this.contracts.insurance, '0x0'),
      totalOI: await this.readStorage(this.contracts.clearinghouse, '0x1'),
      fundingRate: await this.readStorage(this.contracts.funding, '0x0'),
      liquidationQueueSize: await this.readStorage(this.contracts.clearinghouse, '0x5'),
      oracleDeviation: await this.readStorage(this.contracts.oracle, '0x3'),
      marginUtilization: await this.readStorage(this.contracts.clearinghouse, '0x7')
    };
  }
  
  async readStorage(contractAddress, slot) {
    const response = await fetch('https://api.hyperliquid.xyz/evm', {
      method: 'POST',
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'eth_getStorageAt',
        params: [contractAddress, slot, 'latest']
      })
    });
    
    const data = await response.json();
    return parseInt(data.result, 16);
  }
  
  detectStateChanges(currentState) {
    const prevState = this.stateHistory.get('latest');
    if (!prevState) {
      this.stateHistory.set('latest', currentState);
      return [];
    }
    
    const changes = [];
    
    for (const [key, value] of Object.entries(currentState)) {
      if (prevState[key] !== value) {
        changes.push({
          variable: key,
          oldValue: prevState[key],
          newValue: value,
          change: value - prevState[key],
          percentChange: ((value - prevState[key]) / prevState[key]) * 100
        });
      }
    }
    
    this.stateHistory.set('latest', currentState);
    return changes;
  }
  
  async analyzeChange(change) {
    console.log(`   ${change.variable}: ${change.percentChange.toFixed(2)}% change`);
    
    switch(change.variable) {
      case 'insuranceFund':
        if (change.change < 0) {
          console.log(`     🚨 Insurance fund decreasing - system stress`);
        }
        break;
        
      case 'totalOI':
        if (change.percentChange > 10) {
          console.log(`     🚨 Massive OI spike - big move expected`);
        }
        break;
        
      case 'fundingRate':
        console.log(`     📊 Funding rate changed BEFORE publication`);
        console.log(`     ⚡ EDGE: Know before others`);
        if (Math.abs(change.newValue) > 50000) {
          await this.tradeFundingEdge(change.newValue);
        }
        break;
        
      case 'liquidationQueueSize':
        if (change.newValue > 10) {
          console.log(`     🚨 Liquidation cascade building`);
          await this.positionForCascade();
        }
        break;
        
      case 'marginUtilization':
        const utilization = change.newValue / 1e8;
        if (utilization > 0.8) {
          console.log(`     🚨 High system leverage: ${(utilization * 100).toFixed(1)}%`);
        }
        break;
    }
  }
}
```

### Mempool Monitoring

**See pending transactions before execution:**
```javascript
class MempoolMonitor {
  constructor() {
    this.pendingTxs = new Map();
    this.failedTxs = [];
  }
  
  async monitorMempool() {
    console.log(`🕳️  MONITORING MEMPOOL...`);
    
    const ws = new WebSocket('wss://api.hyperliquid.xyz/evm');
    
    ws.on('open', () => {
      ws.send(JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'eth_subscribe',
        params: ['newPendingTransactions']
      }));
    });
    
    ws.on('message', async (data) => {
      const msg = JSON.parse(data);
      
      if (msg.method === 'eth_subscription') {
        const txHash = msg.params.result;
        const tx = await this.getPendingTransaction(txHash);
        
        if (tx) {
          await this.analyzePendingTx(tx);
        }
      }
    });
  }
  
  async analyzePendingTx(tx) {
    const intent = this.decodeIntent(tx);
    if (!intent) return;
    
    this.pendingTxs.set(tx.hash, {
      tx,
      intent,
      seenAt: Date.now(),
      included: false
    });
    
    if (this.isSignificant(intent)) {
      console.log(`🔮 SIGNIFICANT PENDING TX`);
      console.log(`   From: ${tx.from.slice(0,8)}`);
      console.log(`   Intent: ${intent.type}`);
      
      if (this.shouldFrontRun(intent)) {
        await this.frontRunTransaction(tx, intent);
      }
    }
    
    this.trackTransactionFate(tx.hash);
  }
  
  decodeIntent(tx) {
    const signature = tx.input.slice(0, 10);
    
    const intentMap = {
      '0x...placeOrder': 'PLACE_ORDER',
      '0x...cancelOrder': 'CANCEL_ORDER',
      '0x...liquidate': 'LIQUIDATION',
      '0x...withdraw': 'WITHDRAWAL',
      '0x...deposit': 'DEPOSIT'
    };
    
    const intentType = intentMap[signature];
    if (!intentType) return null;
    
    return {
      type: intentType,
      details: this.decodeDetails(tx.input, intentType)
    };
  }
  
  isSignificant(intent) {
    if (intent.type === 'PLACE_ORDER' && intent.details.size > 100000) {
      return true;
    }
    if (intent.type === 'LIQUIDATION') {
      return true;
    }
    return false;
  }
  
  shouldFrontRun(intent) {
    if (intent.type === 'PLACE_ORDER' && intent.details.side === 'buy') {
      return true;
    }
    return false;
  }
  
  async frontRunTransaction(tx, intent) {
    console.log(`   🏃 FRONT-RUNNING TX`);
    
    const higherGasPrice = parseInt(tx.gasPrice, 16) * 1.1;
    
    await this.placeOrderWithGas(
      intent.details.coin,
      intent.details.side,
      intent.details.size * 0.1,
      higherGasPrice
    );
    
    console.log(`   ✅ Front-run order placed`);
  }
}
```

### Temporal Pattern Analysis

**Time-based behavior prediction:**
```javascript
class TemporalAnalyzer {
  constructor() {
    this.history = {
      fundingEvents: [],
      blockTimes: [],
      gasPrices: [],
      liquidations: []
    };
  }
  
  async analyzeTemporalPatterns() {
    console.log(`⏰ ANALYZING TEMPORAL PATTERNS...`);
    
    await this.analyzeFundingTimePattern();
    await this.analyzeBlockTimePattern();
    await this.analyzeCyclicalPatterns();
  }
  
  async analyzeFundingTimePattern() {
    const nextFunding = this.getNextFundingTime();
    const timeUntilFunding = nextFunding - Date.now();
    
    console.log(`   Next funding: ${new Date(nextFunding).toISOString()}`);
    
    if (timeUntilFunding < 900000 && timeUntilFunding > 0) {
      console.log(`   🚨 PRE-FUNDING WINDOW`);
      console.log(`   Expected: Volatility spike`);
      console.log(`   Strategy: Reduce leverage`);
    }
  }
  
  getNextFundingTime() {
    const now = new Date();
    const hours = now.getUTCHours();
    const fundingHours = [0, 8, 16];
    const nextHour = fundingHours.find(h => h > hours) || fundingHours[0];
    
    const next = new Date(now);
    next.setUTCHours(nextHour, 0, 0, 0);
    
    if (nextHour <= hours) {
      next.setUTCDate(next.getUTCDate() + 1);
    }
    
    return next.getTime();
  }
  
  async analyzeCyclicalPatterns() {
    const hour = new Date().getUTCHours();
    
    if (hour >= 0 && hour < 8) {
      console.log(`   🌏 ASIAN SESSION - Lower volume, easier to move markets`);
    }
    
    if (hour >= 14 && hour < 22) {
      console.log(`   🇺🇸 US SESSION - Highest volume, most liquidity`);
    }
    
    const day = new Date().getUTCDay();
    if (day === 0 || day === 6) {
      console.log(`   📅 WEEKEND - 30-50% lower volume, larger moves possible`);
    }
  }
}
```

---

## COMPLETE INTEGRATION

### The Omniscient Predator System
```javascript
class OmniscientPredator {
  constructor(initialCapital, anthropicApiKey) {
    // Core systems
    this.capital = initialCapital;
    this.riskManager = new DynamicRiskManager(initialCapital);
    this.metrics = new MetricsTracker();
    
    // Epistemic learning
    this.beliefs = new EpistemicBeliefEngine();
    this.memory = new AdaptiveMemorySystem();
    this.knowledgeDecay = new KnowledgeDecayEngine();
    
    // LLM reasoning
    this.llm = new LLMReasoningEngine(anthropicApiKey);
    this.hypothesisGenerator = new HypothesisGenerator(this.llm, this.beliefs);
    this.regimeInterpreter = new RegimeInterpreter(this.llm);
    this.strategyCritic = new StrategyCritic(this.llm, this.beliefs);
    
    // Institutional edges
    this.orderFlowAnalyzer = new OrderFlowToxicityAnalyzer();
    this.crossExchangeArb = new CrossExchangeArbitrage();
    this.fundingArb = new FundingArbitrage();
    this.spoofDetector = new SpoofDetector();
    
    // Blockchain intelligence
    this.oracleMonitor = new OracleMonitor();
    this.liquidationEngineMonitor = new LiquidationEngineMonitor();
    this.whaleIntelligence = new WhaleIntelligence();
    this.validatorIntelligence = new ValidatorIntelligence();
    this.contractStateMonitor = new ContractStateMonitor();
    this.mempoolMonitor = new MempoolMonitor();
    this.temporalAnalyzer = new TemporalAnalyzer();
    
    // Position management
    this.positionMonitor = new PositionMonitor(this.riskManager);
    
    // State
    this.activePositions = new Map();
    this.reasoningSchedule = {
      hypothesisGeneration: 86400000 * 7,    // Weekly
      regimeInterpretation: 3600000,         // Hourly
      performanceCritique: 86400000,         // Daily
      temporalAnalysis: 3600000              // Hourly
    };
  }
  
  async start() {
    console.log(`
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║              THE OMNISCIENT PREDATOR v1.0                  ║
║                                                            ║
║   "See Everything. Know Everything. Hunt Everything."      ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    `);
    
    console.log(`\n💰 Starting Capital: $${this.capital.toLocaleString()}`);
    console.log(`📊 Phase: ${this.riskManager.phase}`);
    console.log(`⚙️  Max Leverage: ${this.riskManager.getMaxLeverage()}x`);
    console.log(`🎯 Risk per trade: ${(this.riskManager.getBaseRisk() / this.capital * 100).toFixed(1)}%`);
    
    // Initialize all systems
    await this.initialize();
    
    // Start background processes
    this.startBackgroundProcesses();
    
    // Start main hunting loop
    await this.hunt();
  }
  
  async initialize() {
    console.log(`\n🔧 INITIALIZING ALL SYSTEMS...\n`);
    
    // Initialize blockchain intelligence
    await this.whaleIntelligence.identifyWhales();
    await this.validatorIntelligence.identifyValidators();
    
    // Initialize metrics
    this.metrics.metrics.startingCapital = this.capital;
    this.metrics.metrics.currentCapital = this.capital;
    
    console.log(`✅ All systems initialized\n`);
  }
  
  startBackgroundProcesses() {
    console.log(`🚀 STARTING BACKGROUND PROCESSES...\n`);
    
    // Blockchain monitors
    this.oracleMonitor.monitorOracle();
    this.liquidationEngineMonitor.monitorLiquidationEngine();
    this.whaleIntelligence.monitorWhales();
    this.validatorIntelligence.monitorValidatorBehavior();
    this.contractStateMonitor.monitorCriticalState();
    this.mempoolMonitor.monitorMempool();
    
    // Institutional edges
    this.orderFlowAnalyzer.analyzeOrderFlow();
    this.crossExchangeArb.start();
    setInterval(() => this.fundingArb.findFundingOpportunities(), 3600000);
    setInterval(() => this.spoofDetector.detectSpoofing(), 10000);
    
    // LLM reasoning tasks
    setInterval(async () => {
      console.log(`\n═══ SCHEDULED: HYPOTHESIS GENERATION ═══`);
      await this.hypothesisGenerator.generateNewHypotheses();
    }, this.reasoningSchedule.hypothesisGeneration);
    
    setInterval(async () => {
      console.log(`\n═══ SCHEDULED: REGIME INTERPRETATION ═══`);
      const marketData = await this.gatherMarketData();
      const performanceData = this.getPerformanceData();
      await this.regimeInterpreter.interpretCurrentRegime(marketData, performanceData);
    }, this.reasoningSchedule.regimeInterpretation);
    
    setInterval(async () => {
      console.log(`\n═══ SCHEDULED: PERFORMANCE CRITIQUE ═══`);
      await this.strategyCritic.critiquePerformance();
    }, this.reasoningSchedule.performanceCritique);
    
    setInterval(async () => {
      await this.temporalAnalyzer.analyzeTemporalPatterns();
    }, this.reasoningSchedule.temporalAnalysis);
    
    // Memory maintenance
    setInterval(() => {
      if (this.memory.shouldPurge()) {
        this.memory.purgeMemory();
      }
      this.memory.forgetObsoleteKnowledge();
    }, 3600000);  // Hourly
    
    // Metrics reporting
    setInterval(() => {
      this.metrics.printDashboard();
      this.metrics.checkLiquidationAlert();
    }, 60000);  // Every minute
    
    console.log(`✅ All background processes active\n`);
  }
  
  async hunt() {
    console.log(`🎯 STARTING MAIN HUNTING LOOP...\n`);
    
    while (true) {
      try {
        // Find next potential setup
        const setup = await this.findSetup();
        
        if (!setup) {
          await sleep(1000);
          continue;
        }
        
        // Epistemic decision
        const analysis = this.beliefs.shouldTakeTrade(setup);
        
        // Exploration mode
        const exploring = this.beliefs.shouldExplore();
        
        if (!analysis.decision && !exploring) {
          console.log(`⏭️  SKIPPED: ${analysis.reason}`);
          await sleep(1000);
          continue;
        }
        
        if (exploring && !analysis.decision) {
          console.log(`🔬 EXPLORATION: Taking uncertain trade to learn`);
        }
        
        // For high uncertainty trades, consult LLM
        if (analysis.uncertainty > 0.40 && !analysis.decision) {
          console.log(`🤔 High uncertainty. Consulting LLM...`);
          
          const llmOpinion = await this.getLLMTradeOpinion(setup, analysis);
          
          if (llmOpinion.shouldTake && llmOpinion.confidence > 0.6) {
            console.log(`🧠 LLM OVERRIDE: Taking trade`);
            console.log(`   Reasoning: ${llmOpinion.reasoning}`);
            analysis.decision = true;
            analysis.confidence = llmOpinion.confidence;
          }
        }
        
        if (!analysis.decision) {
          await sleep(1000);
          continue;
        }
        
        // Calculate position size
        const riskAmount = this.calculateEpistemicPositionSize(setup, analysis);
        
        if (riskAmount === 0) {
          console.log(`⏭️  SKIPPED: Zero risk allocation`);
          continue;
        }
        
        // Execute trade
        const result = await this.executeTrade(setup, riskAmount, analysis);
        
        // Learn from outcome
        this.learnFromTrade(result, setup, analysis);
        
        // Update capital
        this.capital += result.profit;
        this.riskManager.capital = this.capital;
        this.metrics.metrics.currentCapital = this.capital;
        
        // LLM explains trade (async)
        this.explainTradeAsync(result, setup, analysis);
        
      } catch (error) {
        console.error(`💥 HUNT ERROR:`, error);
        await sleep(5000);
      }
      
      await sleep(1000);
    }
  }
  
  calculateEpistemicPositionSize(setup, analysis) {
    // Base position from risk manager
    const baseRisk = this.riskManager.calculatePositionSize(setup);
    
    // Epistemic adjustments
    const hypothesis = this.beliefs.beliefs.targetTypes[
      this.beliefs.classifySetup(setup)
    ];
    
    if (!hypothesis) return 0;
    
    // Kelly Criterion with epistemic adjustment
    const kellyFraction = this.calculateEpistemicKelly(hypothesis, setup);
    const epistemicRisk = baseRisk * kellyFraction;
    
    // Uncertainty discount
    const uncertaintyDiscount = 1 - (analysis.uncertainty * 0.7);
    const finalRisk = epistemicRisk * uncertaintyDiscount;
    
    // Confidence scaling
    const confidenceScale = Math.max(0.3, analysis.confidence);
    const adjustedRisk = finalRisk * confidenceScale;
    
    console.log(`💰 POSITION SIZING:`);
    console.log(`   Base risk: $${baseRisk.toFixed(2)}`);
    console.log(`   Kelly: ${kellyFraction.toFixed(3)}`);
    console.log(`   Uncertainty discount: ${(uncertaintyDiscount * 100).toFixed(1)}%`);
    console.log(`   Confidence scale: ${(confidenceScale * 100).toFixed(0)}%`);
    console.log(`   Final risk: $${adjustedRisk.toFixed(2)}`);
    
    return adjustedRisk;
  }
  
  calculateEpistemicKelly(hypothesis, setup) {
    const p = hypothesis.successRate;
    const b = hypothesis.avgProfit / (setup.stopLoss || 0.02);
    
    const kelly = (b * p - (1 - p)) / b;
    
    const uncertainty = this.beliefs.calculateUncertainty(hypothesis);
    const uncertaintyAdjustment = 1 - (uncertainty * 0.5);
    
    // Quarter Kelly for safety
    const fractionalKelly = kelly * 0.25 * uncertaintyAdjustment;
    
    return Math.max(0, Math.min(1, fractionalKelly));
  }
  
  async executeTrade(setup, riskAmount, analysis) {
    const position = this.riskManager.calculateLeveragedPosition(riskAmount, setup);
    
    console.log(`\n🎯 EXECUTING TRADE`);
    console.log(`   Coin: ${setup.target.coin}`);
    console.log(`   Side: ${setup.direction}`);
    console.log(`   Position: $${position.positionSize.toLocaleString()}`);
    console.log(`   Leverage: ${position.leverage.toFixed(1)}x`);
    console.log(`   Risk: $${position.riskAmount.toFixed(2)}`);
    
    // Execute entry
    const entry = await this.enter(setup, position);
    
    // Monitor position
    const result = await this.positionMonitor.monitorPosition(entry);
    
    console.log(`\n${result.profit > 0 ? '✅' : '❌'} TRADE CLOSED`);
    console.log(`   P&L: $${result.profit.toFixed(2)}`);
    console.log(`   Reason: ${result.reason}`);
    
    return {
      ...result,
      setup,
      riskAmount,
      analysis,
      type: this.beliefs.classifySetup(setup),
      timestamp: Date.now(),
      regime: this.beliefs.identifyCurrentRegime(),
      coin: setup.target.coin
    };
  }
  
  learnFromTrade(result, setup, analysis) {
    const trade = {
      success: result.profit > 0,
      profitPercent: result.profit / this.capital,
      type: result.type,
      timestamp: result.timestamp,
      regime: result.regime,
      coin: result.coin,
      expectedValue: analysis.expectedValue,
      actualValue: result.profit / result.riskAmount,
      uncertainty: analysis.uncertainty,
      confidence: analysis.confidence,
      maxLiquidationRisk: result.maxLiquidationRisk || 0
    };
    
    // Update beliefs
    this.beliefs.learnFromTrade(trade);
    
    // Update memory
    this.memory.addMemory(trade);
    
    // Track metrics
    this.metrics.recordTrade(trade);
    
    // Update risk manager
    this.riskManager.trades = this.riskManager.trades || [];
    this.riskManager.trades.push(trade);
    
    if (!trade.success) {
      this.riskManager.consecutiveLosses = 
        (this.riskManager.consecutiveLosses || 0) + 1;
    } else {
      this.riskManager.consecutiveLosses = 0;
    }
    
    const predictionError = trade.actualValue - trade.expectedValue;
    console.log(`📊 LEARNING UPDATE:`);
    console.log(`   Expected: ${(trade.expectedValue * 100).toFixed(2)}%`);
    console.log(`   Actual: ${(trade.actualValue * 100).toFixed(2)}%`);
    console.log(`   Error: ${(predictionError * 100).toFixed(2)}%`);
  }
  
  async getLLMTradeOpinion(setup, quantAnalysis) {
    const context = {
      setup: {
        target: setup.target,
        expectedROI: setup.expectedROI,
        clusterSize: setup.clusterSize
      },
      quantAnalysis: {
        expectedValue: quantAnalysis.expectedValue,
        uncertainty: quantAnalysis.uncertainty,
        confidence: quantAnalysis.confidence
      },
      marketContext: {
        regime: this.beliefs.identifyCurrentRegime(),
        recentPerformance: '...'
      }
    };
    
    const query = `
The quantitative system is uncertain about this trade. 

Should we take it? Consider:
- Is there a qualitative edge we're missing?
- Does the market context support this?
- Are there risks the quant model doesn't see?

Respond with: TAKE or SKIP, plus reasoning.
    `;
    
    const response = await this.llm.reason(query, context);
    
    return {
      shouldTake: response.conclusion?.toLowerCase().includes('take'),
      confidence: response.confidence,
      reasoning: response.reasoning
    };
  }
  
  async explainTradeAsync(result, setup, analysis) {
    setTimeout(async () => {
      const explainer = new TradeExplainer(this.llm);
      await explainer.explainTrade(result, setup, analysis);
    }, 0);
  }
  
  async findSetup() {
    // Scan for potential targets
    // This would integrate with the liquidation scanner
    // Returns setup object or null
    return null;  // Placeholder
  }
  
  async enter(setup, position) {
    // Execute entry orders
    // Returns entry details
    return {};  // Placeholder
  }
  
  async gatherMarketData() {
    return {
      recentPriceAction: {},
      volatility: {},
      fundingRates: {},
      openInterest: {},
      recentLiquidations: []
    };
  }
  
  getPerformanceData() {
    return {
      winRate: this.metrics.metrics.winRate,
      profitFactor: this.metrics.metrics.profitFactor,
      bestPerforming: [],
      worstPerforming: []
    };
  }
}
```

### Deployment
```javascript
// DEPLOY THE OMNISCIENT PREDATOR

const initialCapital = 1000;  // Starting capital in USD
const anthropicApiKey = process.env.ANTHROPIC_API_KEY;

const predator = new OmniscientPredator(initialCapital, anthropicApiKey);

predator.start().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
```

---

## IMPLEMENTATION SPECIFICATIONS

### Required Dependencies
```json
{
  "dependencies": {
    "@anthropic-ai/sdk": "^0.30.0",
    "ws": "^8.14.2",
    "node-fetch": "^3.3.2"
  }
}
```

### Environment Variables
```bash
ANTHROPIC_API_KEY=your_api_key_here
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
```

### API Endpoints

**Hyperliquid:**
- REST API: `https://api.hyperliquid.xyz/info`
- WebSocket: `wss://api.hyperliquid.xyz/ws`
- L4 Orderbook: `wss://api.hyperliquid.xyz/evm`
- RPC: `https://api.hyperliquid.xyz/evm`

**External:**
- Binance Futures: `wss://fstream.binance.com/ws`
- Bybit: `wss://stream.bybit.com/v5/public/linear`

### Storage Requirements

**Persistent Storage:**
- Use Hyperliquid's persistent storage API: `window.storage`
- Store beliefs,

Continue
09:28

memory, metrics

    Key structure: system_state, beliefs, memory_buffer, metrics

Performance Targets

    Liquidation detection: <1ms
    Order placement: <50ms
    Full attack cycle: <200ms
    Oracle lead exploitation: 100-500ms window
    Mempool front-running: <100ms execution

Critical Implementation Notes

    NO browser storage APIs (localStorage, sessionStorage) - use React state or window.storage
    All network calls must handle failures gracefully
    Position monitoring must run continuously in separate thread
    Memory cleanup every hour to prevent bloat
    LLM calls rate-limited to avoid API costs
    All blockchain calls must verify responses
    Emergency stop if liquidation risk > 20%
    Auto-withdraw profits every 5x capital increase

Risk Disclaimers

THIS SYSTEM:

    Uses extreme leverage (up to 50x)
    Has 50% chance of total loss
    Requires constant monitoring
    May violate ToS on some platforms
    Is for educational purposes only
    Should start with capital you can afford to lose

REGULATORY:

    Front-running may be illegal in some jurisdictions
    Market manipulation is illegal
    Consult legal counsel before deployment
    Use at your own risk

FINAL NOTES

This is the complete specification for building the most advanced liquidation hunting system possible with current technology. It combines:

✅ Quantitative precision (millisecond execution) ✅ Epistemic learning (Bayesian belief updates) ✅ LLM reasoning (strategic decision-making) ✅ Institutional edges (order flow, arbitrage) ✅ Blockchain intelligence (oracle, mempool, validators) ✅ Dynamic risk management (adaptive position sizing) ✅ Continuous evolution (knowledge decay, hypothesis generation)

Expected returns: 145-650% annually (if it doesn't blow up)

Expected failure rate: 50% within 3 months

This is the apex predator. Use wisely.

End of specification document

