# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed (2026-01-06) - Database Decontamination + Symbol Scope Lockdown
- **[CRITICAL]** Enforced strict TOP_10 symbol allowlist to prevent data contamination
- **[CRITICAL]** Added ingestion DROP filters at all entry points (collector, detector, API)
- **[CRITICAL]** Purged contaminated historical data from parquet files
- **[CRITICAL]** Reset all runtime detectors and baselines (strict per-symbol isolation)
- **[FIX]** Pre-initialize exactly 10 detectors (no dynamic expansion)
- **[FIX]** Updated WebSocket subscriptions to TOP_10 symbols only
- **[DOCS]** Added `docs/system_scope.md`: Symbol scope policy
- **[DOCS]** Added `docs/data_integrity.md`: Decontamination protocol
- **[TOOL]** Created `scripts/decontaminate_db.py`: One-time migration script

### Fixed (2026-01-06) - Architectural Corrections
- **[FIX]** Parquet writes now fire-and-forget (persistence never blocks ingestion)
- **[FIX]** Per-symbol detector isolation with assertion guards (prevents symbol mixing)
- **[FIX]** Separated raw feed buffers from window state (liquidations no longer disappear)
- **[FIX]** Store both `base_qty` and `quote_qty` (fixes 0.000 quantity bug)
- **[IMPROVE]** Added retry logic for Windows file locking on parquet save
- **[IMPROVE]** Load existing parquet data on collector startup (preserves history)

## [1.0.0] - 2026-01-05

### Added
- Peak Pressure detection system (4-condition promotion logic)
- Per-symbol baseline calculation (P90, P95 thresholds)
- Liquidation retention buffer (60s window)
- Market event collector (trades, liquidations, klines, OI)
- Two-panel UI (Peak Pressure events + raw market feed)
- API endpoints for events and statistics

[Unreleased]: https://github.com/username/repo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/username/repo/releases/tag/v1.0.0
