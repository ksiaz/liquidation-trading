# PostgreSQL Installation Steps

## Step 1: Download Installer

Download from: **https://www.enterprisedb.com/downloads/postgres-postgresql-downloads**

Choose the latest version for Windows (e.g., PostgreSQL 16.x or 15.x)

## Step 2: Run Installer

1. Double-click the downloaded `.exe` file
2. Click "Next" through the wizard

## Step 3: Configuration

**Installation Directory:** (default is fine)  
`C:\Program Files\PostgreSQL\16`

**Components to Install:**
- ✅ PostgreSQL Server
- ✅ pgAdmin 4 (optional GUI)
- ✅ Command Line Tools

**Data Directory:** (default is fine)

**Password:**
```
Username: postgres
Password: postgres
```
**IMPORTANT:** Remember this password!

**Port:** `5432` (default)

**Locale:** Default locale

## Step 4: Complete Installation

- Click "Next" and "Finish"
- Uncheck "Launch Stack Builder" (not needed)

## Step 5: Add to PATH (if needed)

Open PowerShell as Administrator and run:
```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\PostgreSQL\16\bin", "Machine")
```

## Step 6: Verify Installation

Open a **NEW** PowerShell window and run:
```powershell
psql --version
# Should show: psql (PostgreSQL) 16.x
```

## Step 7: Create Database

```powershell
# Connect to PostgreSQL
psql -U postgres

# Enter password: postgres

# Create database
CREATE DATABASE trading;

# Exit
\q
```

## Next Steps

After installation is complete, I will:
1. Apply the schema from P3
2. Run the ingestion script
3. Proceed with P8 simulation tests

**Estimated time:** 10-15 minutes
