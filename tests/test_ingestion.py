import pytest
import sqlite3
import hashlib
import json
import os
from server import save_note, determine_scope, init_db, DB_PATH
from ollama_integration import OllamaTimeout

def test_determine_scope():
    file_path = "/wiki/project-alpha/note.md"
    yaml_meta = {"scope": "local"}
    project_id, is_global = determine_scope(file_path, yaml_meta)
    assert project_id == "project-alpha"
    assert is_global == 0

    yaml_meta_global = {"scope": "global"}
    project_id, is_global = determine_scope(file_path, yaml_meta_global)
    assert project_id == "project-alpha"
    assert is_global == 1

def test_save_note_happy_path(monkeypatch, tmp_path):
    # Mock embedding
    monkeypatch.setattr("server.get_ollama_embedding", lambda x: [0.1] * 768)
    
    # Override DB path for test
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    # Init DB
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    content = "---\ntitle: Test Note\nscope: local\n---\n# Header\nThis is a test."
    file_path = "/test/project-beta/test_note.md"
    
    result = save_note(file_path, content)
    assert result["status"] == "SUCCESS"
    
    # Verify in DB
    conn = init_db(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT project_id, content_hash FROM notes WHERE file_path = ?", (file_path,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "project-beta"
    
    cursor.execute("SELECT COUNT(*) FROM document_chunks")
    chunks_count = cursor.fetchone()[0]
    assert chunks_count > 0
    
    cursor.execute("SELECT COUNT(*) FROM vec_chunks")
    vec_count = cursor.fetchone()[0]
    assert vec_count == chunks_count
    
    cursor.execute("SELECT COUNT(*) FROM fts_chunks")
    fts_count = cursor.fetchone()[0]
    assert fts_count == chunks_count
    conn.close()

def test_save_note_skip_on_same_hash(monkeypatch, tmp_path):
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    content = "Hello world"
    file_path = "/test/project-beta/test_note.md"
    
    # Track how many times embedding is called
    call_count = 0
    def mock_embed(x):
        nonlocal call_count
        call_count += 1
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    
    # First save
    save_note(file_path, content)
    assert call_count > 0
    
    # Second save with same content
    call_count_before = call_count
    result = save_note(file_path, content)
    assert result["status"] == "SKIPPED"
    assert call_count == call_count_before # No new embedding calls

def test_save_note_timeout_rollback(monkeypatch, tmp_path):
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    content = "Some text"
    file_path = "/test/project-beta/timeout_note.md"
    
    def mock_embed(x):
        raise OllamaTimeout("Timeout!")
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    
    result = save_note(file_path, content)
    assert result["status"] == "SKIPPED"
    assert "timeout" in result.get("message", "").lower()
    
    # Check that note is NOT in notes table, but IS in ingestion_logs as SKIPPED
    conn = init_db(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes WHERE file_path = ?", (file_path,))
    assert cursor.fetchone()[0] == 0
    
    cursor.execute("SELECT status FROM ingestion_logs WHERE note_id = ?", (file_path,))
    log = cursor.fetchone()
    assert log is not None
    assert log[0] == "SKIPPED"
    conn.close()
