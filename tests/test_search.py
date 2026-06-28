import pytest
import os
from server import save_note, search_wiki, init_db, DB_PATH
from ollama_integration import OllamaTimeout

def test_search_wiki_vector(monkeypatch, tmp_path):
    # Mock embedding y disponibilidad
    def mock_embed(x, *args, **kwargs):
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)
    
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    # Save a note
    save_note("/test/project-alpha/note.md", "This is some semantic context about apples.")
    
    # Search
    result = search_wiki("apples", current_project="project-alpha")
    assert "semantic context about apples" in result
    assert "[project-alpha]" in result
    assert "Distancia:" in result

def test_search_wiki_fts5_fallback(monkeypatch, tmp_path):
    # Mock embedding to fail
    def mock_embed_fail(x, *args, **kwargs):
        if x == "apples":
            raise OllamaTimeout("Timeout!")
        return [0.1] * 768
        
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed_fail)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)
    
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    # Save a note (we need to bypass timeout to save it, so we embed normally, but search fails)
    # Wait, save_note calls embedding too.
    # We can mock it inside save_note, or just manually insert.
    # Let's adjust mock
    call_count = 0
    def mock_conditional_embed(x, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # 1st is save, 2nd is search
            raise OllamaTimeout("Timeout!")
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_conditional_embed)

    save_note("/test/project-alpha/note.md", "apples context")
    
    result = search_wiki("apples", current_project="project-alpha")
    assert "apples context" in result
    assert "Fallback FTS5" in result

def test_search_wiki_global_knowledge(monkeypatch, tmp_path):
    def mock_embed(x, *args, **kwargs):
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)
    
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    # Global note
    save_note("/test/global/pattern.md", "---\nscope: global\n---\nSingleton pattern is great.")
    
    # Local note
    save_note("/test/project-beta/local.md", "Local config for beta.")

    result = search_wiki("pattern", current_project="project-beta")
    assert "Singleton pattern is great." in result
    assert "[GLOBAL]" in result
    
    # Ensure it doesn't leak project-beta to project-alpha
    result_alpha = search_wiki("beta", current_project="project-alpha")
    assert "Local config for beta" not in result_alpha

def test_search_wiki_fts5_special_characters(monkeypatch, tmp_path):
    # Forzar fallback de FTS5 rompiendo Ollama
    def mock_embed_fail(x):
        raise OllamaTimeout("Forced fail")
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed_fail)
    monkeypatch.setattr("server.check_ollama_availability", lambda: False)
    
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    # Guardar nota con contenido
    save_note("/test/project-gamma/note.md", "This is special text code-123 context.")

    # Buscar con caracteres que romperían FTS5 no sanitizado (paréntesis desbalanceado)
    result = search_wiki('NEAR( ""', current_project="project-gamma")
    assert "special text" in result or "No se encontró" in result

def test_search_wiki_hybrid_rrf(monkeypatch, tmp_path):
    # Mock embedding
    def mock_embed(x):
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)
    
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("server.DB_PATH", test_db)
    
    conn = init_db(test_db)
    from database import create_schema
    create_schema(conn)
    conn.close()

    # Guardar dos notas en project-delta: una que match semántico y otra léxico
    save_note("/test/project-delta/semantic.md", "El patrón Singleton es un patrón de diseño creacional.")
    save_note("/test/project-delta/lexical.md", "Definición del patrón Singleton en la arquitectura local.")

    # Realizar búsqueda
    result = search_wiki("Singleton arquitectura", current_project="project-delta")
    assert "Singleton" in result
    assert "semantic" in result or "lexical" in result

