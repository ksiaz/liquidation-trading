# XRPUSDT MARKET CHARACTERIZATION

**Phase:** D1 Measurement-Only Analytics  
**Symbol:** XRPUSDT  
**Purpose:** Statistical characterization of market structure  

## 1. Volatility Structure

### ATR (1-minute candles)

| Percentile | Value |
|:-----------|:------|
| p10 | $0.000800 |
| p25 | $0.001100 |
| p50 | $0.001700 |
| p75 | $0.002600 |
| p90 | $0.003700 |
| p95 | $0.004400 |
| mean | $0.002014 |
| stddev | $0.001294 |

### Volatility Regime Durations

- **min:** 1.0 minutes
- **max:** 83.0 minutes
- **mean:** 3.6 minutes
- **median:** 2.0 minutes

## 2. Orderbook Structure

### Zone Persistence (CDF)

- **1s:** 79.3% of zones survive
- **5s:** 43.8% of zones survive
- **10s:** 26.7% of zones survive
- **30s:** 6.2% of zones survive
- **60s:** 1.7% of zones survive

### Half-Life Statistics

- **halflife_sec:** 3.86s
- **mean_lifetime:** 14.04s
- **median_lifetime:** 3.85s

### Spread Distribution (bps)

- **p10:** 0.50 bps
- **p50:** 0.50 bps
- **p90:** 0.50 bps
- **mean:** 0.50 bps

## 3. Trade Flow

### Arrival Rate

- **p10:** 0.003
- **p50:** 0.152
- **p90:** 0.630
- **mean:** 0.264
- **rate_per_sec:** 3.789

### Buy/Sell Imbalance

- **Entropy:** 0.9972

### Trade Bursts

- **num_bursts:** 26738
- **mean_duration:** 0.7986719641923388
- **max_duration:** 0.999000072479248

## 4. Liquidation Structure (Global)

### Inter-Arrival Times

- **p10:** 0.00s
- **p50:** 0.90s
- **p90:** 7.24s
- **mean:** 3.63s

### Burst Frequency

- **total_bursts:** 1457.00
- **bursts_per_hour:** 73.37

### Rolling Variance

- **10s_stddev:** 49.78
- **30s_stddev:** 81.04
- **60s_stddev:** 91.80
- **60s_mean:** 57.65

### Self-Excitation Proxy

- **pct_within_5s:** 84.421779063277
- **absolute_count:** 16637
