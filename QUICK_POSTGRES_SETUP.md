# FASTEST PostgreSQL Setup - Portable Version (5 minutes)

## Download Portable PostgreSQL

**Direct Download (~50MB, not 220MB):**
https://get.enterprisedb.com/postgresql/postgresql-16.1-1-windows-x64-binaries.zip

This is the binaries-only version - no installer needed!

## Quick Setup

1. **Extract** the zip to `C:\pgsql` (or anywhere you want)

2. **Initialize database:**
```powershell
cd C:\pgsql\bin
.\initdb.exe -D C:\pgsql\data -U postgres -W
# Enter password when prompted: postgres
```

3. **Start PostgreSQL:**
```powershell
.\pg_ctl.exe -D C:\pgsql\data start
```

4. **Create database:**
```powershell
.\psql.exe -U postgres
# Enter password: postgres
# Then run:
CREATE DATABASE trading;
\q
```

## Add to PATH (for convenience)
```powershell
$env:PATH += ";C:\pgsql\bin"
```

## Done!

That's it - PostgreSQL is running. No hours of installation, just 5 minutes!

**Next:** Let me know when this is done and I'll apply the schema and ingest the data.
