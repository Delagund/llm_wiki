import pytest
import os
from server import save_note, determine_scope
from database import init_db
from ollama_integration import OllamaTimeout


def test_determine_scope():
    """Verifica que project_id se calcule correctamente relativo a wiki_dir."""
    file_path = "/base/wiki/project-alpha/note.md"
    wiki_dir = "/base/wiki"
    yaml_meta = {"scope": "local"}
    project_id, is_global = determine_scope(file_path, yaml_meta, wiki_dir)
    assert project_id == "project-alpha"
    assert is_global == 0

    yaml_meta_global = {"scope": "global"}
    project_id, is_global = determine_scope(file_path, yaml_meta_global, wiki_dir)
    assert project_id == "project-alpha"
    assert is_global == 1


def test_save_note_happy_path(monkeypatch, initialized_server):
    """Verifica la ingesta exitosa de una nota dentro del sandbox."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x: [0.1] * 768)

    # Crear subdirectorio de proyecto dentro del wiki_dir del sandbox
    project_dir = os.path.join(initialized_server.wiki_dir, "project-beta")
    os.makedirs(project_dir, exist_ok=True)

    content = "---\ntitle: Test Note\nscope: local\n---\n# Header\nThis is a test."
    file_path = os.path.join(project_dir, "test_note.md")

    result = save_note(file_path, content)
    assert result["status"] == "SUCCESS"

    # Verificar persistencia en BD
    conn = init_db(initialized_server.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT project_id, content_hash FROM notes WHERE file_path = ?", (file_path,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "project-beta"

    cursor.execute("SELECT COUNT(*) FROM document_chunks")
    chunks_count = cursor.fetchone()[0]
    assert chunks_count > 0

    cursor.execute("SELECT COUNT(*) FROM vec_chunks")
    assert cursor.fetchone()[0] == chunks_count

    cursor.execute("SELECT COUNT(*) FROM fts_chunks")
    assert cursor.fetchone()[0] == chunks_count
    conn.close()


def test_save_note_skip_on_same_hash(monkeypatch, initialized_server):
    """Verifica que notas con el mismo hash se omitan sin re-procesar embeddings."""
    project_dir = os.path.join(initialized_server.wiki_dir, "project-beta")
    os.makedirs(project_dir, exist_ok=True)

    content = "Hello world"
    file_path = os.path.join(project_dir, "test_note.md")

    call_count = 0
    def mock_embed(x):
        nonlocal call_count
        call_count += 1
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)

    save_note(file_path, content)
    assert call_count > 0

    call_count_before = call_count
    result = save_note(file_path, content)
    assert result["status"] == "SKIPPED"
    assert call_count == call_count_before


def test_save_note_timeout_rollback(monkeypatch, initialized_server):
    """Verifica rollback correcto cuando Ollama hace timeout durante ingesta."""
    project_dir = os.path.join(initialized_server.wiki_dir, "project-beta")
    os.makedirs(project_dir, exist_ok=True)

    content = "Some text"
    file_path = os.path.join(project_dir, "timeout_note.md")

    def mock_embed(x):
        raise OllamaTimeout("Timeout!")
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)

    result = save_note(file_path, content)
    assert result["status"] == "SKIPPED"
    assert "timeout" in result.get("message", "").lower()

    conn = init_db(initialized_server.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes WHERE file_path = ?", (file_path,))
    assert cursor.fetchone()[0] == 0

    cursor.execute("SELECT status FROM ingestion_logs WHERE note_id = ?", (file_path,))
    log = cursor.fetchone()
    assert log is not None
    assert log[0] == "SKIPPED"
    conn.close()
