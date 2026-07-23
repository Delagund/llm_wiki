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

def test_migrate_v0_to_v1_preserves_data(tmp_path):
    import database
    db_path = tmp_path / "test_migrate_data.db"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 0;")
    conn.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, file_path TEXT UNIQUE, title TEXT, project_id TEXT, is_global INTEGER DEFAULT 0, content_hash TEXT, yaml_metadata TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);")
    conn.execute("INSERT INTO notes (id, file_path, title) VALUES ('test1', '/path/to/note.md', 'Test Note');")
    conn.commit()
    conn.close()

    database.ensure_schema(str(db_path))

    conn2 = sqlite3.connect(str(db_path))
    cursor = conn2.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes;")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT title FROM notes WHERE id = 'test1';")
    assert cursor.fetchone()[0] == 'Test Note'
    cursor.execute("PRAGMA user_version;")
    assert cursor.fetchone()[0] == 1
    conn2.close()

def test_ensure_schema_idempotent_preserves_data(tmp_path):
    import database
    db_path = tmp_path / "test_idempotent.db"

    database.ensure_schema(str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO notes (id, file_path, title) VALUES ('test1', '/path/note.md', 'Note');")
    conn.commit()
    conn.close()

    database.ensure_schema(str(db_path))

    conn2 = sqlite3.connect(str(db_path))
    cursor = conn2.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes;")
    assert cursor.fetchone()[0] == 1
    cursor.execute("PRAGMA user_version;")
    assert cursor.fetchone()[0] == 1
    conn2.close()

def test_ensure_schema_up_to_date_skips_migration(tmp_path):
    import database
    db_path = tmp_path / "test_current.db"

    database.ensure_schema(str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO notes (id, file_path, title) VALUES ('test1', '/path/n.md', 'A');")
    conn.commit()
    conn.close()

    database.ensure_schema(str(db_path))

    conn2 = sqlite3.connect(str(db_path))
    cursor = conn2.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes;")
    assert cursor.fetchone()[0] == 1
    conn2.close()

def test_corrupt_db_backup_and_recreate(tmp_path):
    import database
    db_path = tmp_path / "test_corrupt.db"

    with open(str(db_path), "w") as f:
        f.write("not a sqlite database")

    database.ensure_schema(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "notes" in tables
    cursor.execute("PRAGMA user_version;")
    assert cursor.fetchone()[0] == 1
    conn.close()

    backups = list(tmp_path.glob("test_corrupt.db.corrupted.*"))
    assert len(backups) >= 1
