import sqlite3
import pytest
import sqlite_vec
import os

from database import init_db, create_schema

def test_database_initialization_and_schema(tmp_path):
    db_path = tmp_path / "test.db"
    
    # Init DB should return a connection with vector extension and WAL mode
    conn = init_db(str(db_path))
    assert isinstance(conn, sqlite3.Connection)
    
    # Check WAL mode
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"
    
    # Apply schema
    create_schema(conn)
    
    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    
    expected_tables = {
        "notes",
        "document_chunks",
        "vec_chunks",
        "fts_chunks",
        "ingestion_logs"
    }
    
    # Verify expected tables are subset of actual tables
    for expected in expected_tables:
        assert expected in tables, f"Missing table: {expected}"
        
    conn.close()
