# PostgreSQL PATH Setup

PostgreSQL is installed but not accessible in PowerShell yet.

## Option 1: Restart PowerShell (Easiest)

Close your current PowerShell window and open a new one. The installer should have added PostgreSQL to PATH.

Then test:
```powershell
psql --version
```

## Option 2: Add to PATH Manually (Current Session)

Run these commands in your current PowerShell:

```powershell
# Find PostgreSQL version
$pgDir = Get-ChildItem "C:\Program Files\PostgreSQL" -Directory | Select-Object -First 1
$env:PATH += ";$($pgDir.FullName)\bin"

# Verify
psql --version
```

## Next Steps

Once `psql --version` works, I will:
1. Create the trading database  
2. Apply the schema from P3
3. Ingest the 158MB of real Binance data
4. Run integrity validation
5. Execute P8 simulation tests

**Let me know when psql command is working!**
