# Hyperliquid GitHub Resources

Curated from Discord channels: #node-operators, #api-traders, #builders

---

## Liquidation & Trading Bots

| Repo | Description |
|------|-------------|
| [dwellir-public/gRPC-code-examples/hyperliquid-liquidation-bot](https://github.com/dwellir-public/gRPC-code-examples/tree/main/hyperliquid-liquidation-bot) | **Liquidation bot via gRPC** - real-time liquidation monitoring |
| [botsonblock/hyperliquidation-bot](https://github.com/botsonblock/hyperliquidation-bot) | Liquidation tracking bot |
| [chainstacklabs/hyperliquid-trading-bot](https://github.com/chainstacklabs/hyperliquid-trading-bot) | Full trading bot with learning examples (copy trading, TWAP, etc.) |
| [Quantweb3-com/NexusTrader](https://github.com/Quantweb3-com/NexusTrader) | Multi-exchange trading framework (Binance, OKX, Bybit, Hyperliquid) |
| [davassi/hypertrade](https://github.com/davassi/hypertrade) | TradingView → Hyperliquid automated trading bridge |
| [duckdegen/apebot](https://github.com/duckdegen/apebot) | Binance news sniping bot (viral open source) |
| [hyperliquid-dex/hyperliquid-rust-sdk/bin/market_maker.rs](https://github.com/hyperliquid-dex/hyperliquid-rust-sdk/blob/master/src/bin/market_maker.rs) | Official market maker example |

---

## Official SDKs

| Repo | Language | Notes |
|------|----------|-------|
| [hyperliquid-dex/hyperliquid-python-sdk](https://github.com/hyperliquid-dex/hyperliquid-python-sdk) | Python | Official, most examples |
| [hyperliquid-dex/hyperliquid-rust-sdk](https://github.com/hyperliquid-dex/hyperliquid-rust-sdk) | Rust | Official, includes market maker |
| [hyperliquid-dex/ts-examples](https://github.com/hyperliquid-dex/ts-examples) | TypeScript | Official examples |
| [hyperliquid-dex/contracts](https://github.com/hyperliquid-dex/contracts) | Solidity | Bridge contracts |

---

## Community SDKs

| Repo | Language | Notes |
|------|----------|-------|
| [nktkas/hyperliquid](https://github.com/nktkas/hyperliquid) | TypeScript | Valibot schemas, well-maintained |
| [nomeida/hyperliquid](https://github.com/nomeida/hyperliquid) | TypeScript | Alternative TS SDK |
| [majinbot/hl-sdk](https://github.com/majinbot/hl-sdk) | TypeScript | Bun-compatible, handles symbol duplicates |
| [elevatordown/hyperliquid-ts-sdk](https://github.com/elevatordown/hyperliquid-ts-sdk) | TypeScript | Alternative implementation |
| [Logarithm-Labs/go-hyperliquid](https://github.com/Logarithm-Labs/go-hyperliquid) | Go | Go SDK |
| [0xBoji/hyperliquid-swift-sdk](https://github.com/0xBoji/hyperliquid-swift-sdk) | Swift | iOS development |
| [infinitefield/hypersdk](https://github.com/infinitefield/hypersdk) | Rust | Alternative Rust SDK |
| [skedzior/hyperliquid](https://github.com/skedzior/hyperliquid) | - | Community SDK |

---

## Node Setup & Docker

| Repo | Description |
|------|-------------|
| [hyperliquid-dex/node](https://github.com/hyperliquid-dex/node) | **Official node repo** |
| [zilayo/hyperliquid-node-dockerized](https://github.com/zilayo/hyperliquid-node-dockerized) | Simplified Docker setup |
| [BriungRi/hl-docker](https://github.com/BriungRi/hl-docker) | Docker + ValiDAO Grafana metrics |
| [zeulart/hl-node](https://github.com/zeulart/hl-node) | Fork with updated Dockerfile + gossip config |

---

## Monitoring & Alerting

| Repo | Description |
|------|-------------|
| [validaoxyz/hyperliquid-exporter](https://github.com/validaoxyz/hyperliquid-exporter) | Prometheus exporter for validators |
| [Luganodes/hypermon](https://github.com/Luganodes/hypermon) | Monitoring tool |
| [nodebreaker0-0/hlmon](https://github.com/nodebreaker0-0/hlmon) | Validator alert tool (liveness, signatures) |
| [nodebreaker0-0/hlmon/updatemon](https://github.com/nodebreaker0-0/hlmon/tree/main/updatemon) | Binary update alerts |
| [janklimo/hl-node-monitor](https://github.com/janklimo/hl-node-monitor) | Node monitoring |
| [Firstset/hl-node/watchtower](https://github.com/Firstset/hl-node/tree/main/watchtower) | Telegram alerts for jailing |
| [l0ix/hyperliquid-testnet-performance-exporter](https://github.com/l0ix/hyperliquid-testnet-performance-exporter) | Historical validator performance |
| [b-harvest/hl-exporter](https://github.com/b-harvest/hl-exporter) | Exporter (validator & non-validator branches) |
| [NodeOps-app/Hyperliquid-validator-monitoring](https://github.com/NodeOps-app/Hyperliquid-validator-monitoring) | Validator monitoring |
| [nodebreaker0-0/hy_vote_count](https://github.com/nodebreaker0-0/hy_vote_count) | Vote counting tool |

---

## Archive Node & EVM

| Repo | Description |
|------|-------------|
| [hl-archive-node/nanoreth](https://github.com/hl-archive-node/nanoreth) | Reth-based HyperEVM archive node |
| [sprites0/nanoreth](https://github.com/sprites0/nanoreth) | Nanoreth fork |
| [sprites0/evm-init](https://github.com/sprites0/evm-init) | EVM initialization |
| [sprites0/block-importer](https://github.com/sprites0/block-importer) | Block importer |
| [sprites0/hl-testnet-genesis](https://github.com/sprites0/hl-testnet-genesis) | Testnet genesis files |
| [hyperliquid-dex/hyper-evm-sync](https://github.com/hyperliquid-dex/hyper-evm-sync) | EVM sync tool |
| [hyperliquid-dex/order_book_server](https://github.com/hyperliquid-dex/order_book_server) | Order book server from node data |

---

## HyperEVM Development

| Repo | Description |
|------|-------------|
| [hyperliquid-dev/hyper-evm-lib](https://github.com/hyperliquid-dev/hyper-evm-lib) | Precompile library with tests |
| [HypurrStudio/illusio-sdk](https://github.com/HypurrStudio/illusio-sdk) | Precompile/CoreWriter testing & tracing |
| [raul0ligma/hyperqit](https://github.com/raul0ligma/hyperqit) | Multi-sig examples |

---

## Utilities & Tools

| Repo | Description |
|------|-------------|
| [hyperliquid-dex/ts-examples/LiquidationPx.tsx](https://github.com/hyperliquid-dex/ts-examples/blob/main/examples/LiquidationPx.tsx) | **Liquidation price calculation code** |
| [DiamondHandsQuant/HLTradingViewTest](https://github.com/DiamondHandsQuant/HLTradingViewTest) | TradingView Advanced charts integration |
| [Firstset/hl-dune-exporter](https://github.com/Firstset/hl-dune-exporter) | Dune Analytics exporter |
| [Pier-Two/hyperliquid-utility-scripts](https://github.com/Pier-Two/hyperliquid-utility-scripts) | Auto unjail, peer discovery (Docker) |
| [chainstacklabs/compare-dashboard-functions](https://github.com/chainstacklabs/compare-dashboard-functions) | Response time comparison dashboard |
| [b-harvest/awesome-hyperliquid-validators](https://github.com/b-harvest/awesome-hyperliquid-validators) | Validator resources list |
| [chaifeng/ufw-docker](https://github.com/chaifeng/ufw-docker) | UFW + Docker firewall fix |

---

## Copy Trading & Frontends

| Repo | Description |
|------|-------------|
| [xxkhanxx77/padtai-copytrading-frontend](https://github.com/xxkhanxx77/padtai-copytrading-frontend) | Copy trading frontend |
| [xxkhanxx77/padtai-copytrading-be](https://github.com/xxkhanxx77/padtai-copytrading-be) | Copy trading backend |
| [xxkhanxx77/padtai-copytrading-tradingbot](https://github.com/xxkhanxx77/padtai-copytrading-tradingbot) | Copy trading bot |
| [Aayushgoyal00/Hyperliquid-Trading-Dashboard](https://github.com/Aayushgoyal00/Hyperliquid-Trading-Dashboard) | Trading dashboard with Privy wallet |
| [chainstacklabs/hyperliquid-trading-bot/.../copy_trading](https://github.com/chainstacklabs/hyperliquid-trading-bot/blob/main/learning_examples/06_copy_trading/track_all_orders.py) | Copy trading examples |

---

## Third-Party Integrations

| Repo | Description |
|------|-------------|
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | Multi-exchange library (includes Hyperliquid) |
| [paradigmxyz/reth](https://github.com/paradigmxyz/reth) | Reth client (base for nanoreth) |
| [ethereum-lists/chains](https://github.com/ethereum-lists/chains) | Chain registry |
| [mds1/multicall3](https://github.com/mds1/multicall3) | Multicall contract (deployed on HyperEVM) |

---

## Key Code References

### Liquidation Price Calculation
```
https://github.com/hyperliquid-dex/ts-examples/blob/main/examples/LiquidationPx.tsx
```

### Signing Implementation
```
https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/hyperliquid/utils/signing.py
https://github.com/nktkas/hyperliquid/blob/main/src/api/exchange/_base/_execute.ts
```

### Market Maker Example
```
https://github.com/hyperliquid-dex/hyperliquid-rust-sdk/blob/master/src/bin/market_maker.rs
https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_adding.py
```

### Vault/Subaccount Trading
```
https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_vault.py
```

### Agent Wallet Setup
```
https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_agent.py
```

### Precompile Testing
```
https://github.com/hyperliquid-dev/hyper-evm-lib/blob/main/test/simulation/PrecompileSim.sol
```

---

## Articles & Docs

- Precompiles & CoreWriter explained: `medium.com/@ambitlabs/demystifying-the-hyperliquid-precompiles-and-corewriter`
- Official docs: `hyperliquid.gitbook.io/hyperliquid-docs`

---

*Last updated: 2026-01-24*
*Source: Hyperliquid Discord exports*
