# Runbook: System Won't Start

## Symptoms
- Trading script fails to start
- Error messages on startup
- Process exits immediately

## Severity
**Medium** - No active trading, but no risk exposure

## Immediate Actions

### 1. Check Python Environment
```bash
# Verify Python version
python3 --version  # Should be 3.10+

# Check if virtual environment is activated
which python3  # Should point to venv

# Activate if needed
source venv/bin/activate
```

### 2. Check Dependencies
```bash
# Install missing dependencies
pip install -r requirements.txt

# Verify key packages
python3 -c "import hyperliquid; print('OK')"
python3 -c "import aiohttp; print('OK')"
python3 -c "import numpy; print('OK')"
```

### 3. Check Configuration
```bash
# Verify config file exists
ls -la config/trading_config.yaml

# Validate config syntax
python3 -c "import yaml; yaml.safe_load(open('config/trading_config.yaml'))"
```

### 4. Check API Credentials
```bash
# Verify environment variables
echo $HL_API_KEY
echo $HL_API_SECRET

# Or check .env file
cat .env | grep -E "^HL_"
```

### 5. Check Network Connectivity
```bash
# Test Hyperliquid API
curl -s https://api.hyperliquid.xyz/info -d '{"type":"meta"}' | head -c 100

# Test WebSocket (should connect then timeout)
timeout 5 wscat -c wss://api.hyperliquid.xyz/ws || echo "Connection test complete"
```

## Common Errors and Solutions

### "ModuleNotFoundError: No module named 'xyz'"
```bash
pip install xyz
# Or reinstall all
pip install -r requirements.txt
```

### "Config file not found"
```bash
# Copy example config
cp config/trading_config.example.yaml config/trading_config.yaml
# Edit with your settings
nano config/trading_config.yaml
```

### "Invalid API credentials"
1. Regenerate API keys in Hyperliquid dashboard
2. Update `.env` file with new keys
3. Verify keys are loaded: `python3 -c "import os; print(os.getenv('HL_API_KEY')[:8])"`

### "Address already in use"
```bash
# Find process using the port
lsof -i :8080

# Kill it
kill -9 <PID>
```

### "Database locked"
```bash
# Find processes using the database
fuser data/trading.db

# Kill them or wait for completion
```

## Verification
After fixing, verify startup:
```bash
python3 scripts/run_paper_trade.py --dry-run
```

The system should:
1. Initialize without errors
2. Connect to exchange
3. Show "System ready" message

## Escalation
If issue persists after all steps:
1. Check `logs/` directory for detailed error logs
2. Review recent changes in git history
3. Run in debug mode: `python3 scripts/run_paper_trade.py --debug`
