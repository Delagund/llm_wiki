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

def test_db_schema_relations_and_sections(tmp_path):
    db_path = tmp_path / "test2.db"
    conn = init_db(str(db_path))
    create_schema(conn)
    cursor = conn.cursor()

    # Check section_id in document_chunks
    cursor.execute("PRAGMA table_info(document_chunks);")
    columns = [row[1] for row in cursor.fetchall()]
    assert "section_id" in columns

    # Check note_relations table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='note_relations';")
    assert cursor.fetchone() is not None

    # Check user_version
    cursor.execute("PRAGMA user_version;")
    version = cursor.fetchone()[0]
    assert version == 1
    conn.close()

def test_sqlite_vec_load_fallback(monkeypatch, tmp_path):
    import database
    def mock_load(conn):
        raise Exception("Fallo binario")
    
    monkeypatch.setattr(sqlite_vec, "load", mock_load)
    monkeypatch.setattr(database, "VEC_AVAILABLE", True)
    
    db_path = tmp_path / "test_fallback.db"
    conn = database.init_db(str(db_path))
    
    assert database.VEC_AVAILABLE is False
    conn.close()

def test_schema_auto_rebuild(tmp_path):
    import sqlite3
    import database
    db_path = tmp_path / "test_rebuild.db"
    
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 0;")
    conn.commit()
    conn.close()
    
    database.ensure_schema(str(db_path))
    
    conn2 = sqlite3.connect(str(db_path))
    cursor = conn2.cursor()
    cursor.execute("PRAGMA user_version;")
    assert cursor.fetchone()[0] == 1
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    assert "notes" in tables
    conn2.close()
