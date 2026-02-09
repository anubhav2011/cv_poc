#!/usr/bin/env python3
"""
Database initialization and migration script.
Run this to ensure database schema is up-to-date with latest changes.
"""

import sys
import sqlite3
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "workers.db"

def migrate_database():
    """Run database migrations to ensure schema is up-to-date."""
    
    # Create data directory if it doesn't exist
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        logger.info(f"Connected to database: {DB_PATH}")
        
        # Create workers table
        logger.info("Ensuring workers table exists...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            worker_id TEXT PRIMARY KEY,
            mobile_number TEXT UNIQUE NOT NULL,
            name TEXT,
            dob TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Add columns to workers table safely
        workers_columns = [
            ("personal_document_path", "TEXT"),
            ("educational_document_paths", "TEXT"),
            ("video_url", "TEXT"),
            ("personal_ocr_raw_text", "TEXT")
        ]
        
        for col_name, col_type in workers_columns:
            try:
                cursor.execute(f"ALTER TABLE workers ADD COLUMN {col_name} {col_type}")
                logger.info(f"✓ Added column '{col_name}' to workers table")
            except sqlite3.OperationalError as e:
                if "already exists" in str(e).lower():
                    logger.info(f"✓ Column '{col_name}' already exists in workers table")
                else:
                    raise
        
        # Create educational_documents table (WITHOUT institution field)
        logger.info("Ensuring educational_documents table exists...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS educational_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT NOT NULL,
            document_type TEXT,
            qualification TEXT,
            board TEXT,
            stream TEXT,
            year_of_passing TEXT,
            school_name TEXT,
            marks_type TEXT,
            marks TEXT,
            percentage REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
        """)
        
        # Add raw_ocr_text column to educational_documents
        try:
            cursor.execute("ALTER TABLE educational_documents ADD COLUMN raw_ocr_text TEXT")
            logger.info("✓ Added column 'raw_ocr_text' to educational_documents table")
        except sqlite3.OperationalError as e:
            if "already exists" in str(e).lower():
                logger.info("✓ Column 'raw_ocr_text' already exists in educational_documents table")
            else:
                raise
        
        # Drop institution column if it exists (cleanup from old schema)
        try:
            # SQLite doesn't support DROP COLUMN easily, so we'd need to recreate the table
            # For now, just log a note
            cursor.execute("PRAGMA table_info(educational_documents)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'institution' in column_names:
                logger.warning("⚠ Column 'institution' exists in educational_documents table - this should not be used")
                # Note: Removing institution column from SQLite requires table recreation
                # For now, just ensure it's not being inserted into
        except Exception as e:
            logger.error(f"Error checking columns: {e}")
        
        conn.commit()
        conn.close()
        
        logger.info("=" * 80)
        logger.info("✓ Database migration completed successfully!")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Database migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
