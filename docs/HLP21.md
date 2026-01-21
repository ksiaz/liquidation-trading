DEPLOYMENT & OPERATIONS
Safe Deployment and Operational Procedures

Code that works locally may fail in production.
Deployment is where theory meets operational reality.

This document defines:
  - How to deploy updates safely
  - Rollback procedures
  - Emergency protocols
  - Operational runbooks

Goal: Deploy with confidence, recover from failures quickly.

---

PART 1: DEPLOYMENT PRINCIPLES

Principle 1: Zero-Downtime Deployments

Trading must continue during updates.

Use blue-green deployment or rolling updates.
Never hard-stop production to deploy.

---

Principle 2: Rollback Readiness

Every deployment must be reversible.

Before deploying:
  - Can you roll back in < 5 minutes?
  - Are database migrations reversible?
  - Do you have previous version ready?

If answer is "no" to any: Fix before deploying.

---

Principle 3: Deploy Small Changes

Small changes = low risk.

Prefer:
  - Single feature per deployment
  - Small code diffs
  - Incremental improvements

Avoid:
  - Massive refactors in one deploy
  - Multiple unrelated changes
  - "Big bang" releases

---

Principle 4: Validate Before Production

Deployment checklist (mandatory):

[ ] All tests pass
[ ] Code reviewed
[ ] Tested on staging/testnet
[ ] Performance benchmarks acceptable
[ ] Rollback plan documented

---

PART 2: DEPLOYMENT STRATEGIES

Strategy 1: Blue-Green Deployment

Architecture:

BLUE environment (currently live)
GREEN environment (new version)

Load balancer routes to BLUE.

Deployment Process:

1. Deploy new version to GREEN
2. Run smoke tests on GREEN
3. Switch load balancer to GREEN
4. Monitor for 5 minutes
5. If issues: Switch back to BLUE (instant rollback)
6. If stable: Keep GREEN, decommission BLUE

Benefits:
  - Zero downtime
  - Instant rollback
  - Validate before switching

Limitations:
  - Requires 2x infrastructure
  - Database migrations tricky

---

Strategy 2: Rolling Update

For multi-instance deployments:

1. Update instance 1
2. Wait for health check
3. If healthy: Update instance 2
4. Repeat for all instances

Benefits:
  - Minimal infrastructure overhead
  - Gradual rollout
  - Can pause/abort mid-deployment

Limitations:
  - Longer deployment time
  - Multiple versions running simultaneously

---

Strategy 3: Canary Deployment

Gradual traffic shift:

1. Deploy new version to 10% of instances
2. Monitor metrics (errors, latency, PnL)
3. If stable: Increase to 50%
4. If still stable: Increase to 100%
5. If issues at any point: Rollback immediately

Benefits:
  - Limits blast radius
  - Early issue detection
  - Data-driven rollout

---

Recommended for Trading System:

Blue-Green for simplicity and instant rollback.

Canary if you have multiple parallel trading instances.

---

PART 3: DEPLOYMENT PROCESS

Pre-Deployment:

1. Merge code to main branch
2. Run full test suite
3. Build deployment artifact:
   - Docker image, or
   - Binary package
   - Tag with version (e.g., v1.2.3)
4. Deploy to staging environment
5. Run smoke tests on staging
6. Get approval (if manual gate)

---

Deployment Execution:

Using Blue-Green:

# Deploy to GREEN environment
docker-compose -f docker-compose.green.yml up -d

# Wait for startup
sleep 10

# Run health checks
./scripts/health_check.sh green

# If healthy: Switch traffic
./scripts/switch_to_green.sh

# Monitor for 5 minutes
watch -n 5 "./scripts/monitor_health.sh"

# If stable: Celebrate
# If issues: Rollback (see Part 4)

---

Post-Deployment:

1. Monitor key metrics:
   - Error rate
   - Latency (p99)
   - Win rate
   - Position reconciliation
2. Watch for alerts
3. Check logs for anomalies
4. Verify trades executing correctly
5. After 1 hour stable:
   - Mark deployment as successful
   - Update BLUE to new version (for redundancy)

---

PART 4: ROLLBACK PROCEDURES

When to Rollback:

Immediate rollback if:
  - Errors spike > 10x baseline
  - Position mismatches detected
  - Trading halted unexpectedly
  - Crashes or restarts

Cautious rollback if:
  - Win rate drops > 20%
  - Latency increases > 5x
  - Unusual behavior observed

---

Rollback Execution:

Blue-Green:

# Switch back to BLUE
./scripts/switch_to_blue.sh

# Verify BLUE healthy
./scripts/health_check.sh blue

# Stop GREEN
docker-compose -f docker-compose.green.yml down

Time to rollback: < 30 seconds

---

Rolling Update:

# Stop rollout immediately
kubectl rollout pause deployment/trading-system

# Roll back to previous version
kubectl rollout undo deployment/trading-system

# Monitor rollback
kubectl rollout status deployment/trading-system

Time to rollback: 1-2 minutes

---

Database Rollback:

If schema changed:

# Run reverse migration
./scripts/migrate_down.sh

# Verify data integrity
./scripts/verify_database.sh

Prevention:
  - Make migrations backward-compatible
  - Use additive changes (add columns, don't remove)
  - Test migrations on copy of production data

---

Post-Rollback:

1. Verify system stable
2. Investigate what went wrong
3. Fix issue in code
4. Retest thoroughly
5. Deploy fix (new version)

Document:
  - What failed
  - Why rollback was needed
  - How to prevent in future

---

PART 5: VERSIONING & RELEASES

Version Numbering:

Use Semantic Versioning: v{MAJOR}.{MINOR}.{PATCH}

MAJOR: Breaking changes (rare)
MINOR: New features
PATCH: Bug fixes

Examples:
  v1.2.3 → v1.2.4 (bug fix)
  v1.2.4 → v1.3.0 (new strategy added)
  v1.3.0 → v2.0.0 (major refactor)

---

Tagging Releases:

git tag -a v1.2.3 -m "Add kinematics strategy"
git push origin v1.2.3

Build from tag:
  - Ensures reproducibility
  - Easy to identify running version
  - Simple rollback (deploy previous tag)

---

Release Notes:

For each release, document:

## v1.2.3 - 2026-01-21

### Added
- Kinematics strategy for range expansion
- Wallet match scoring

### Changed
- Improved orderbook slippage estimation
- Updated stop placement logic

### Fixed
- Position reconciliation race condition
- Memory leak in event registry

### Deployment Notes
- Run database migration: `./scripts/migrate.sh`
- Update config: Add `kinematics_enabled: true`

---

PART 6: CONFIGURATION MANAGEMENT

Configuration Files:

config/
  production.yaml
  staging.yaml
  development.yaml

Never hard-code values.

---

Example Configuration:

# production.yaml
trading:
  enabled: true
  max_positions: 1
  risk_per_trade: 0.01

strategies:
  geometry:
    enabled: true
    oi_threshold: 1.20
    confidence_min: 0.70
  kinematics:
    enabled: true
    range_threshold: 0.015

risk:
  daily_loss_limit: 0.03
  weekly_loss_limit: 0.07
  max_drawdown: 0.25

---

Hot Reload:

Support configuration updates without restart:

def reload_config():
  new_config = load_config("config/production.yaml")
  
  # Validate config
  validate(new_config)
  
  # Atomically swap
  global current_config
  current_config = new_config
  
  log_info("Configuration reloaded")

Trigger via signal:
  kill -HUP <pid>

Or API endpoint:
  POST /admin/reload-config

---

Secrets Management:

Never commit secrets to git.

Use:
  - Environment variables
  - Secret management service (Vault, AWS Secrets Manager)
  - Encrypted config files

Example:

# .env (not in git)
HYPERLIQUID_API_KEY=abc123...
DATABASE_PASSWORD=secure_pass

Load at runtime:
  load_dotenv()
  api_key = os.getenv("HYPERLIQUID_API_KEY")

---

PART 7: MONITORING DEPLOYMENT HEALTH

Deployment Dashboard:

Track during deployment:

Current Version: v1.2.4 → v1.2.5
Deployment Status: IN_PROGRESS
Start Time: 18:45:00
Duration: 2m 15s

Health Checks:
  ✓ Node connection
  ✓ State builder
  ✓ All strategies
  ✓ Database connection

Metrics (vs baseline):
  Error rate: 0.1% (baseline: 0.1%) ✓
  Latency p99: 12ms (baseline: 10ms) ~
  Win rate: 58% (baseline: 57%) ✓
  
Trades Since Deploy: 3
  - All successful ✓

Alert: None

Action: Monitor for 3 more minutes

---

Rollback Trigger Criteria:

Auto-rollback if:
  - Error rate > 1% (10x baseline)
  - Any position mismatch detected
  - Critical component fails health check

Manual rollback if:
  - Win rate drops > 15%
  - Latency increases > 3x
  - Operator judges deployment unsafe

---

PART 8: EMERGENCY PROCEDURES

Emergency Kill Switch:

Purpose: Immediately halt all trading.

Trigger Conditions:
  - Severe bug discovered
  - Regulatory concerns
  - Exchange issues
  - Capital at risk

Execution:

# Via admin endpoint
curl -X POST https://trading-system/admin/emergency-stop \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"

# Via command line
./scripts/emergency_stop.sh

# Via manual intervention
docker-compose down

Effects:
  - Close all open positions at market
  - Cancel all open orders
  - Halt all strategies
  - Disconnect from exchange
  - Require manual restart

---

Manual Position Closure:

If automated closure fails:

# List positions
./scripts/list_positions.sh

# Close specific position
./scripts/close_position.sh BTC-PERP

# Or via exchange UI
# - Log into Hyperliquid
# - Manually close positions

---

Data Backup Emergency:

If database corruption detected:

# Immediate backup
./scripts/backup_database.sh emergency

# Stop writes
./scripts/halt_trading.sh

# Assess damage
./scripts/verify_database.sh

# Restore if needed
./scripts/restore_database.sh latest_backup.sql

---

PART 9: RUNBOOKS

Runbook: System Won't Start

Symptoms: System fails to start after deployment

Diagnostic Steps:

1. Check logs:
   docker logs trading-system
   
2. Common issues:
   - Config syntax error
   - Missing environment variables
   - Database migration failed
   - Port already in use

3. Fixes:
   - Validate config: `./scripts/validate_config.sh`
   - Check env vars: `env | grep TRADING`
   - Run migration manually: `./scripts/migrate.sh`
   - Kill conflicting process: `lsof -i :8080`

4. If still failing:
   - Rollback to previous version
   - Investigate offline

---

Runbook: High Latency Detected

Symptoms: Order execution latency > 50ms p99

Diagnostic Steps:

1. Check system resources:
   - CPU usage
   - Memory usage
   - Disk I/O

2. Check network:
   - Ping to exchange
   - Packet loss

3. Check for lock contention:
   - Review HLP15 lock-free design
   - Profile hot path

4. Common causes:
   - Background tasks (backtesting, optimization)
   - Memory pressure (GC pauses)
   - Network congestion

Fixes:
   - Throttle background tasks
   - Increase heap size
   - Optimize hot path
   - If persistent: Restart system

---

Runbook: Positions Not Reconciling

Symptoms: Internal positions don't match exchange

Diagnostic Steps:

1. Get both positions:
   internal = system.get_positions()
   exchange = exchange_api.get_positions()

2. Compare:
   diff = compare(internal, exchange)

3. Common causes:
   - Missed fill notification
   - Duplicate order submission
   - Exchange-side fill not recorded

Fixes:
   - Manual reconciliation:
     * Trust exchange as source of truth
     * Update internal state
   - Close position manually if needed
   - Investigation required for root cause

---

Runbook: Circuit Breaker Activated

Symptoms: System halted trading due to circuit breaker

Investigation:

1. Check why triggered:
   ./scripts/get_circuit_breaker_reason.sh

2. Possible reasons:
   - Daily loss limit hit
   - Consecutive losses
   - Rapid unexpected losses
   - System malfunction detected

3. Validation before restart:
   - Is issue fixed?
   - Were losses legitimate?
   - Is system healthy?

Restart:
   # Only after validation
   ./scripts/reset_circuit_breaker.sh
   ./scripts/resume_trading.sh

---

PART 10: OPERATIONAL CHECKLIST

Daily Operations:

[ ] Check system status (health dashboard)
[ ] Review yesterday's trades
[ ] Check error logs
[ ] Verify positions reconciled
[ ] Review capital utilization
[ ] Check for alerts

---

Weekly Operations:

[ ] Review performance metrics
[ ] Analyze win rate trends
[ ] Check for strategy degradation
[ ] Review capital management stats
[ ] Update documentation
[ ] Review recent deployments
[ ] Plan next week's changes

---

Monthly Operations:

[ ] Full system audit
[ ] Review and optimize parameters
[ ] Analyze counterfactual data
[ ] Review wallet classifications
[ ] Database maintenance
[ ] Log archival
[ ] Security review

---

PART 11: ACCESS CONTROL

Roles:

Admin:
  - Full access
  - Can deploy
  - Can halt trading
  - Can modify config

Operator:
  - Read-only access to system
  - Can view trades, logs
  - Can trigger emergency stop
  - Cannot deploy or modify

Developer:
  - Full access to staging
  - Read-only in production
  - Can deploy to staging
  - Cannot deploy to production without review

---

Authentication:

Use strong authentication:
  - SSH keys (no passwords)
  - 2FA for admin access
  - API keys rotated regularly
  - Audit logs for all access

---

PART 12: DOCUMENTATION

Maintain:

1. Architecture diagrams
   - System components
   - Data flow
   - Deployment architecture

2. API documentation
   - Internal APIs
   - Exchange API usage

3. Runbooks (this document)
   - Emergency procedures
   - Common issues
   - Troubleshooting guides

4. Change log
   - All deployments
   - Configuration changes
   - Incidents

Keep documentation up-to-date with every deployment.

---

IMPLEMENTATION CHECKLIST

[ ] Set up blue-green deployment infrastructure
[ ] Write deployment scripts
[ ] Write rollback scripts
[ ] Create configuration management system
[ ] Set up secrets management
[ ] Write emergency procedures
[ ] Create runbooks for common issues
[ ] Set up monitoring dashboards
[ ] Implement access controls
[ ] Document deployment process
[ ] Test rollback procedures
[ ] Create deployment checklist

---

BOTTOM LINE

Deployment is not "push to production and hope."

Deployment is:
  - Planned and tested
  - Reversible in minutes
  - Monitored continuously
  - Documented thoroughly

Good deployment practices:
  - Prevent outages
  - Enable fast recovery
  - Build operational confidence
  - Allow rapid iteration

Bad deployment practices:
  - Cause downtime
  - Lead to data loss
  - Create panic
  - Slow development

Invest in deployment infrastructure upfront.

Deploy early, deploy often, deploy safely.
