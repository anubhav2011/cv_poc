# Database Location Configuration

## Current Setup

The application is configured to store `workers.db` in the existing `data` folder:

**Database Location:** `/vercel/share/v0-project/data/workers.db`

## How It Works

### 1. Database Path Configuration (database.py)

```python
DB_PATH = (Path(__file__).resolve().parent.parent / "data" / "workers.db")
```

**Explanation:**
- `Path(__file__).resolve()` → Gets absolute path to database.py file (`/vercel/share/v0-project/db/database.py`)
- `.parent.parent` → Goes up 2 directories to project root (`/vercel/share/v0-project/`)
- `/ "data" / "workers.db"` → Navigates to data folder and creates workers.db file

**Result:** `/vercel/share/v0-project/data/workers.db`

### 2. Automatic Directory Creation

The `get_db_connection()` function automatically creates the data folder if it doesn't exist:

```python
def get_db_connection(timeout: float = 30.0):
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # Creates /data folder
        conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
        ...
```

**When it happens:** On the first database connection (typically during server startup)

### 3. Migration Script Path (scripts/migrate_db.py)

```python
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "workers.db"
```

**Explanation:**
- `Path(__file__).resolve()` → Gets absolute path to migrate_db.py (`/vercel/share/v0-project/scripts/migrate_db.py`)
- `.parent.parent` → Goes up 2 directories to project root (`/vercel/share/v0-project/`)
- `/ "data" / "workers.db"` → Same location as main database

**Result:** Same as main app - `/vercel/share/v0-project/data/workers.db`

## Verification

### Check That Database Will Be Created Correctly

When you start the server, you should see in the logs:

```
Database path: /vercel/share/v0-project/data/workers.db
Initializing database at /path/to/data/workers.db (attempt 1/3)
Database initialized successfully!
```

### Manual Verification After First Run

After running the application once, check if the database file exists:

```bash
ls -la /vercel/share/v0-project/data/workers.db
```

You should see:
```
-rw-r--r-- ... workers.db
```

### Using the Migration Script

You can also manually run the migration to ensure the database is properly initialized:

```bash
cd /vercel/share/v0-project
python scripts/migrate_db.py
```

This will output:
```
INFO - Database initialization and migration script.
INFO - Connected to database: /vercel/share/v0-project/data/workers.db
INFO - Ensuring workers table exists...
...
```

## Summary

✅ Database is already configured to be created in the `data` folder  
✅ Data folder will be automatically created on first server run  
✅ Same database location is used by main app and migration script  
✅ No additional configuration needed

The system is ready to go. Simply run your application and the database will be automatically initialized in the data folder.
