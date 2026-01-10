# PostgreSQL Installation Guide (Windows)

## Option 1: Install PostgreSQL Locally

### Download
1. Go to: https://www.postgresql.org/download/windows/
2. Download the installer (latest version, e.g., PostgreSQL 15 or 16)
3. Run the installer

### During Installation
- Username: `postgres`
- Password: `postgres`
- Port: `5432`
- Install pgAdmin (optional GUI)

### After Installation
```powershell
# Add to PATH (if not auto-added)
$env:PATH += ";C:\Program Files\PostgreSQL\15\bin"

# Verify installation
psql --version

# Create database
psql -U postgres
# Enter password: postgres
# Then run:
CREATE DATABASE trading;
\q
```

## Option 2: Use Docker (Simpler)

```powershell
# Install Docker Desktop first: https://www.docker.com/products/docker-desktop/

# Run PostgreSQL container
docker run -d --name trading-db `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=trading `
  -p 5432:5432 postgres:15

# Verify
docker ps
```

## Option 3: Use SQLite (No Install Required)

If you want to proceed immediately without PostgreSQL setup, I can modify the ingestion script to use SQLite instead. This would allow us to proceed with P8b/P8 testing immediately.

**Pros:** No installation, immediate execution  
**Cons:** Different SQL syntax (but our schema will work)

Let me know which option you prefer!
