import pytest
import os
from server import save_note, search_wiki
from database import init_db
from ollama_integration import OllamaTimeout

def make_md(content, scope="local", title="x"):
    return f"---\ntitle: {title}\ntype: doc\nsources: []\nrelated: []\ncreated: x\nupdated: x\nscope: {scope}\n---\n{content}"

def test_search_wiki_vector(monkeypatch, initialized_server):
    """Verifica búsqueda vectorial semántica con Ollama disponible."""
    def mock_embed(x, *args, **kwargs):
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)

    project_dir = os.path.join(initialized_server.wiki_dir, "project-alpha")
    os.makedirs(project_dir, exist_ok=True)

    file_path = os.path.join(project_dir, "note.md")
    save_note(file_path, make_md("This is some semantic context about apples.", title="note"))

    result = search_wiki("apples", current_project="project-alpha")
    assert "semantic context about apples" in result
    assert "[project-alpha]" in result
    assert "Distancia:" in result


def test_search_wiki_fts5_fallback(monkeypatch, initialized_server):
    """Verifica degradación a FTS5 cuando Ollama falla en la búsqueda."""
    project_dir = os.path.join(initialized_server.wiki_dir, "project-alpha")
    os.makedirs(project_dir, exist_ok=True)

    call_count = 0
    def mock_conditional_embed(x, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # La primera llamada es para save_note, la segunda para search
        if call_count == 2:
            raise OllamaTimeout("Timeout!")
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_conditional_embed)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)

    file_path = os.path.join(project_dir, "note.md")
    save_note(file_path, make_md("apples context", title="note"))

    result = search_wiki("apples", current_project="project-alpha")
    assert "apples context" in result
    assert "Fallback FTS5" in result


def test_search_wiki_global_knowledge(monkeypatch, initialized_server):
    """Verifica que las notas globales son visibles desde cualquier proyecto."""
    def mock_embed(x, *args, **kwargs):
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    # Desactivar vector search para isolación determinista con FTS5
    monkeypatch.setattr("server.check_ollama_availability", lambda: False)

    # Usar directorio sin 'global' en el nombre
    shared_dir = os.path.join(initialized_server.wiki_dir, "shared-knowledge")
    os.makedirs(shared_dir, exist_ok=True)

    beta_dir = os.path.join(initialized_server.wiki_dir, "project-beta")
    os.makedirs(beta_dir, exist_ok=True)

    # Nota global marcada por frontmatter scope: global
    save_note(os.path.join(shared_dir, "pattern.md"), make_md("Singleton pattern is great.", scope="global", title="pattern"))

    # Nota local con scope local (ya no hay heurístico de path)
    local_path = os.path.join(beta_dir, "local.md")
    save_note(local_path, make_md("Local config for beta.", scope="local", title="local"))

    result = search_wiki("pattern", current_project="project-beta")
    assert "Singleton pattern is great." in result
    assert "[GLOBAL]" in result

    # La nota local de project-beta NO debe ser visible desde project-alpha
    result_alpha = search_wiki("beta", current_project="project-alpha")
    assert "Local config for beta" not in result_alpha


def test_search_wiki_fts5_special_characters(monkeypatch, initialized_server):
    """Verifica que los caracteres especiales no rompen la búsqueda FTS5."""
    def mock_embed_fail(x, *args, **kwargs):
        raise OllamaTimeout("Forced fail")
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed_fail)
    monkeypatch.setattr("server.check_ollama_availability", lambda: False)

    project_dir = os.path.join(initialized_server.wiki_dir, "project-gamma")
    os.makedirs(project_dir, exist_ok=True)

    file_path = os.path.join(project_dir, "note.md")
    save_note(file_path, make_md("This is special text code-123 context.", title="note"))

    result = search_wiki('NEAR( ""', current_project="project-gamma")
    assert "special text" in result or "No se encontr" in result


def test_search_wiki_hybrid_rrf(monkeypatch, initialized_server):
    """Verifica la fusión RRF entre resultados vectoriales y léxicos."""
    def mock_embed(x, *args, **kwargs):
        return [0.1] * 768
    monkeypatch.setattr("server.get_ollama_embedding", mock_embed)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)

    project_dir = os.path.join(initialized_server.wiki_dir, "project-delta")
    os.makedirs(project_dir, exist_ok=True)

    save_note(os.path.join(project_dir, "semantic.md"), make_md("El patron Singleton es un patron de diseno creacional.", title="semantic"))
    save_note(os.path.join(project_dir, "lexical.md"), make_md("Definicion del patron Singleton en la arquitectura local.", title="lexical"))

    result = search_wiki("Singleton arquitectura", current_project="project-delta")
    assert "Singleton" in result
    assert "semantic" in result or "lexical" in result


def test_search_degradation_diagnostics(monkeypatch, initialized_server):
    """Verifica el diagnostico y la degradacion cuando Ollama falla."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x, *args, **kwargs: [0.1] * 768)
    project_dir = os.path.join(initialized_server.wiki_dir, "project-degrad")
    os.makedirs(project_dir, exist_ok=True)
    file_path = os.path.join(project_dir, "note.md")
    save_note(file_path, make_md("This is degradation test context.", title="note"))

    monkeypatch.setattr("server.check_ollama_availability", lambda: False)
    
    result = search_wiki("degradation", current_project="project-degrad")
    assert "[DIAGNÓSTICO]" in result
    assert "Fallback FTS5 (Ollama fuera de línea): True" in result


def test_search_speed_performance(monkeypatch, initialized_server):
    """Verifica que la busqueda retorne rapido (< 200 ms)."""
    import time
    monkeypatch.setattr("server.get_ollama_embedding", lambda x, *args, **kwargs: [0.1] * 768)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)
    project_dir = os.path.join(initialized_server.wiki_dir, "project-speed")
    os.makedirs(project_dir, exist_ok=True)
    file_path = os.path.join(project_dir, "note.md")
    save_note(file_path, make_md("Fast context data.", title="note"))

    t0 = time.perf_counter()
    result = search_wiki("Fast", current_project="project-speed")
    t1 = time.perf_counter()

    assert t1 - t0 < 0.2
    assert "Tiempo DB:" in result


def test_search_scoping(monkeypatch, initialized_server):
    """Verifica el scoping por seccion html."""
    monkeypatch.setattr("server.get_ollama_embedding", lambda x, *args, **kwargs: [0.1] * 768)
    monkeypatch.setattr("server.check_ollama_availability", lambda: True)
    project_dir = os.path.join(initialized_server.wiki_dir, "project-scope")
    os.makedirs(project_dir, exist_ok=True)
    file_path = os.path.join(project_dir, "note.html")
    
    html_content = (
        '<!--yaml\n'
        'title: scope_test\n'
        'type: doc\n'
        'scope: local\n'
        '-->\n'
        '<article id="main">'
        '<section id="a">Soy de la seccion a</section>'
        '<section id="b">Soy de la seccion b</section>'
        '</article>'
    )
    save_note(file_path, html_content)

    result_a = search_wiki("Soy de la", current_project="project-scope", scoping_id="main;a")
    assert "seccion a" in result_a
    assert "seccion b" not in result_a

    result_none = search_wiki("Soy de la", current_project="project-scope", scoping_id="inexistente")
    assert "seccion a" not in result_none
    assert "seccion b" not in result_none
