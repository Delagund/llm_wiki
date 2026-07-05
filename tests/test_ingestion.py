import pytest
import os
from server import save_note, determine_scope
from database import init_db
from ollama_integration import OllamaTimeout

VALID_FRONTMATTER = """---
title: Test Note
type: doc
sources: []
related: []
created: 2026-07-04
updated: 2026-07-04
scope: local
---
"""

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

    content = VALID_FRONTMATTER + "# Header\nThis is a test."
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

    content = VALID_FRONTMATTER + "Hello world"
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

    content = VALID_FRONTMATTER + "Some text"
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

# =============================================================================
# T4.6 — Pruebas TDD de ingesta y sincronización
# =============================================================================


def test_clean_text_indexing_md(monkeypatch, initialized_server):
    """Verifica que las notas .md tengan sus chunks limpios de sintaxis Markdown."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x: [0.1] * 768)
    import server
    from database import init_db

    config = initialized_server
    project_dir = os.path.join(config.wiki_dir, "test_project")
    os.makedirs(project_dir, exist_ok=True)

    content = """---
title: MD Clean Test
type: concept
sources: []
related: []
created: 2026-07-04
updated: 2026-07-04
scope: local
---
# Header
Some **bold** text and *italic* text and `code` and [link text](https://example.com)
"""
    file_path = os.path.join(project_dir, "clean_test.md")
    result = server.save_note(file_path, content)
    assert result["status"] == "SUCCESS"

    conn = init_db(config.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT content FROM document_chunks")
    rows = cursor.fetchall()
    conn.close()

    assert rows, "No se encontraron chunks en document_chunks"
    stored_text = " ".join(r[0] for r in rows)

    # Verificar ausencia de sintaxis Markdown
    assert "#" not in stored_text, "Headers (#) aun presentes en el texto almacenado"
    assert "**" not in stored_text, "Bold (**) aun presente en el texto almacenado"
    assert "`" not in stored_text, "Backticks aun presentes en el texto almacenado"

    # Verificar que los links se convirtieron a texto plano (sin sintaxis [](url))
    assert "[" not in stored_text, "Corchetes de link aun presentes"
    assert "](https://" not in stored_text, "Sintaxis de URL aun presente"

    # Verificar que el texto limpio esta presente
    assert "Header" in stored_text
    assert "bold" in stored_text
    assert "italic" in stored_text
    assert "code" in stored_text
    assert "link text" in stored_text


def test_clean_text_indexing_html(monkeypatch, initialized_server):
    """Verifica que las notas .html tengan texto limpio (sin etiquetas HTML)."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x: [0.1] * 768)
    import server
    from database import init_db

    config = initialized_server
    project_dir = os.path.join(config.wiki_dir, "test_project")
    os.makedirs(project_dir, exist_ok=True)

    content = """<!--yaml
title: HTML Clean Test
type: doc
-->
<section><p>Hello <a href="test">world</a></p><p>Second paragraph</p></section>
"""
    file_path = os.path.join(project_dir, "clean_test.html")
    result = server.save_note(file_path, content)
    assert result["status"] == "SUCCESS"

    conn = init_db(config.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT content FROM document_chunks")
    rows = cursor.fetchall()
    conn.close()

    assert rows, "No se encontraron chunks en document_chunks"
    stored_text = " ".join(r[0] for r in rows)

    # Verificar ausencia de etiquetas HTML
    assert "<p>" not in stored_text
    assert "</p>" not in stored_text
    assert "<a" not in stored_text
    assert "</a>" not in stored_text
    assert "<section>" not in stored_text
    assert "</section>" not in stored_text

    # Verificar que el texto plano esta presente
    assert "Hello" in stored_text
    assert "world" in stored_text
    assert "Second paragraph" in stored_text


def test_graph_relation_extraction(monkeypatch, initialized_server):
    """Verifica que los enlaces HTML con rel valido generen registros en note_relations."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x: [0.1] * 768)
    import server
    from database import init_db

    config = initialized_server
    project_dir = os.path.join(config.wiki_dir, "test_project")
    os.makedirs(project_dir, exist_ok=True)

    content = """<!--yaml
title: Relation Test
type: doc
-->
<a href="dep.md" rel="dependency">Dependency</a>
<a href="concept.md" rel="concept-link">Concept Link</a>
<a href="ignored.md" rel="invalid">Ignored</a>
"""
    file_path = os.path.join(project_dir, "relation_test.html")
    result = server.save_note(file_path, content)
    assert result["status"] == "SUCCESS"

    conn = init_db(config.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT relation_type, target_file_path FROM note_relations")
    rows = cursor.fetchall()
    conn.close()

    # Solo 2 relaciones validas (la rel="invalid" debe ignorarse)
    assert len(rows) == 2, f"Se esperaban 2 relaciones, se obtuvieron {len(rows)}"

    rel_types = [r[0] for r in rows]
    assert "dependency" in rel_types
    assert "concept-link" in rel_types
    assert "invalid" not in rel_types


def test_source_ingestion(monkeypatch, initialized_server, tmp_path):
    """Verifica la auto-ingesta de archivos fuente en sources/."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x: [0.1] * 768)
    monkeypatch.setenv("LLM_WIKI_TEST_MODE", "true")
    import server
    from database import init_db
    import json

    # Inicializar un proyecto limpio via initialize_project
    base_path = str(tmp_path / "source_project")
    server.initialize_project(base_path)

    # Crear un archivo fuente en sources/
    src_dir = server.active_config.sources_dir
    source_file = os.path.join(src_dir, "test_source.py")
    with open(source_file, "w", encoding="utf-8") as f:
        f.write("print('hello world')")

    # Ejecutar sincronizacion lazy para auto-ingestar
    server.startup_lazy_check()

    # Verificar que se creo el resumen HTML
    target_path = os.path.join(server.active_config.wiki_dir, "sources", "test_source.html")
    assert os.path.exists(target_path), f"El archivo {target_path} no fue creado"

    with open(target_path, encoding="utf-8") as f:
        file_content = f.read()
    assert "<!--yaml" in file_content
    assert "type: source-summary" in file_content
    assert "is_global: true" in file_content

    # Verificar que la nota esta registrada en la BD
    conn = init_db(server.active_config.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT yaml_metadata FROM notes WHERE file_path = ?", (target_path,))
    row = cursor.fetchone()
    assert row is not None, "La nota no fue registrada en la base de datos"
    metadata = json.loads(row[0])
    assert metadata.get("is_global") is True, "El yaml_metadata debe contener is_global: true"
    conn.close()


def test_hybrid_sync(monkeypatch, initialized_server):
    """Verifica la sincronizacion hibrida de archivos .md y .html."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x: [0.1] * 768)
    import server
    from database import init_db

    config = initialized_server
    project_dir = os.path.join(config.wiki_dir, "test_project")
    os.makedirs(project_dir, exist_ok=True)

    # Crear archivo .md
    md_content = """---
title: Hybrid MD
type: concept
sources: []
related: []
created: 2026-07-04
updated: 2026-07-04
scope: local
---
# Hybrid
Markdown content.
"""
    md_path = os.path.join(project_dir, "hybrid.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Crear archivo .html
    html_content = """<!--yaml
title: Hybrid HTML
type: doc
-->
<p>HTML content here</p>
"""
    html_path = os.path.join(project_dir, "hybrid.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Ejecutar sincronizacion lazy
    server.startup_lazy_check()

    # Verificar en la base de datos
    conn = init_db(config.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM notes WHERE file_path = ?", (md_path,))
    assert cursor.fetchone()[0] == 1, "La nota .md no fue registrada"

    cursor.execute("SELECT COUNT(*) FROM notes WHERE file_path = ?", (html_path,))
    assert cursor.fetchone()[0] == 1, "La nota .html no fue registrada"

    cursor.execute("SELECT COUNT(*) FROM document_chunks")
    chunk_count = cursor.fetchone()[0]
    assert chunk_count >= 2, (
        f"Se esperaban al menos 2 chunks (uno por archivo), "
        f"se obtuvieron {chunk_count}"
    )

    conn.close()
