import pytest
import os
import json
from server import save_note, search_wiki, get_ingestion_status, list_notes, initialize_project
from ollama_integration import get_ollama_embedding, OllamaTimeout
import requests


def test_mcp_tool_contracts():
    """Verifica que las herramientas MCP estén registradas y sean invocables."""
    assert callable(save_note)
    assert callable(search_wiki)
    assert callable(get_ingestion_status)
    assert callable(list_notes)
    assert callable(initialize_project)


def test_ollama_timeout_handling(monkeypatch):
    """
    Verifica que se lance la excepción correcta cuando Ollama excede el timeout de 5 segundos.
    """
    def mock_post(*args, **kwargs):
        raise requests.exceptions.Timeout("Read timeout")

    monkeypatch.setattr(requests, "post", mock_post)

    with pytest.raises(OllamaTimeout) as exc:
        get_ollama_embedding("test query")
    assert "timeout" in str(exc.value).lower()


def test_ollama_connection_error(monkeypatch):
    """
    Verifica que se levanten excepciones de RequestException si Ollama no está corriendo.
    """
    def mock_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")

    monkeypatch.setattr(requests, "post", mock_post)

    with pytest.raises(requests.exceptions.RequestException):
        get_ollama_embedding("test query")


# ============================================================================
# Tests TDD — Fase 1 (T1.6)
# ============================================================================


def test_config_priority(monkeypatch, tmp_path):
    """Verifica que LLM_WIKI_DIR tiene prioridad absoluta sobre .llm_wiki_config.json."""
    import server

    # Crear estructura para env var
    env_base = tmp_path / "env_project"
    env_base.mkdir()
    (env_base / "wiki").mkdir()
    (env_base / "sources").mkdir()

    # Crear estructura para JSON config con ruta diferente
    json_base = tmp_path / "json_project"
    json_base.mkdir()
    (json_base / "wiki").mkdir()
    (json_base / "sources").mkdir()

    # Escribir .llm_wiki_config.json en el cwd
    config_json = {
        "wiki_dir": str(json_base / "wiki"),
        "sources_dir": str(json_base / "sources")
    }
    config_path = tmp_path / ".llm_wiki_config.json"
    with open(config_path, "w") as f:
        json.dump(config_json, f)

    # Simular que cwd tiene el JSON
    monkeypatch.chdir(tmp_path)

    # Caso 1: Sin env var, debe usar JSON
    monkeypatch.delenv("LLM_WIKI_DIR", raising=False)
    config_json_result = server.load_config()
    assert config_json_result is not None
    assert str(json_base / "wiki") == config_json_result.wiki_dir

    # Caso 2: Con env var, debe ignorar JSON y usar env
    monkeypatch.setenv("LLM_WIKI_DIR", str(env_base))
    config_env_result = server.load_config()
    assert config_env_result is not None
    assert str(env_base / "wiki") == config_env_result.wiki_dir
    # Confirmar que NO usa la ruta del JSON
    assert str(json_base) not in config_env_result.wiki_dir


def test_sandbox_path_traversal():
    """Verifica que el sandbox rechaza rutas fuera del directorio permitido."""
    from server import validate_path_sandbox
    import tempfile

    with tempfile.TemporaryDirectory() as base:
        # Ruta válida dentro del sandbox
        valid_path = os.path.join(base, "wiki", "notes", "note.md")
        result = validate_path_sandbox(valid_path, base)
        assert result.startswith(base)

        # Path Traversal con ..
        traversal_path = os.path.join(base, "..", "etc", "passwd")
        with pytest.raises(ValueError, match="fuera del sandbox"):
            validate_path_sandbox(traversal_path, base)

        # Ruta completamente externa
        external_path = "/tmp/malicious/file.txt"
        with pytest.raises(ValueError, match="fuera del sandbox"):
            validate_path_sandbox(external_path, base)


def test_uninitialized_state(monkeypatch):
    """Verifica que las herramientas MCP fallan cuando el servidor no está inicializado."""
    import server

    # Forzar estado no inicializado
    monkeypatch.setattr(server, "active_config", None)

    # Todas las herramientas excepto initialize_project deben fallar
    with pytest.raises(ValueError, match="no inicializado"):
        server.save_note("/any/path.md", "content")

    with pytest.raises(ValueError, match="no inicializado"):
        server.search_wiki("query")

    with pytest.raises(ValueError, match="no inicializado"):
        server.list_notes()

    with pytest.raises(ValueError, match="no inicializado"):
        server.get_ingestion_status()

    # initialize_project NO debe fallar por estado no inicializado
    # (puede fallar por otras razones pero no por "no inicializado")
    assert callable(server.initialize_project)


def test_initialize_project_tool(monkeypatch, tmp_path):
    """Verifica que initialize_project crea estructura, BD, JSON y activa el servidor."""
    import server

    # Estado inicial: no inicializado
    monkeypatch.setattr(server, "active_config", None)
    monkeypatch.setenv("LLM_WIKI_TEST_MODE", "true")

    base = str(tmp_path / "test_project")

    result = server.initialize_project(base)

    # Verificar respuesta exitosa
    assert result["status"] == "SUCCESS"

    # Verificar que se crearon los directorios
    assert os.path.isdir(os.path.join(base, "wiki", "concepts"))
    assert os.path.isdir(os.path.join(base, "wiki", "entities"))
    assert os.path.isdir(os.path.join(base, "wiki", "sources"))
    assert os.path.isdir(os.path.join(base, "wiki", "comparisons"))
    assert os.path.isdir(os.path.join(base, "sources"))

    # Verificar que se creó la base de datos
    db_path = os.path.join(base, "wiki.db")
    assert os.path.isfile(db_path)

    # Verificar que se creó el JSON de configuración
    config_path = os.path.join(base, ".llm_wiki_config.json")
    assert os.path.isfile(config_path)
    with open(config_path) as f:
        config_data = json.load(f)
    assert config_data["wiki_dir"] == os.path.join(base, "wiki")
    assert config_data["sources_dir"] == os.path.join(base, "sources")

    # Verificar que active_config se activó en runtime
    assert server.active_config is not None
    assert server.active_config.wiki_dir == os.path.join(base, "wiki")
    assert server.active_config.db_path == db_path

    # Verificar que ahora las herramientas NO fallan por "no inicializado"
    # (pueden fallar por otras razones pero no por estado)
    try:
        server.list_notes()
    except ValueError as e:
        # No debe ser error de "no inicializado"
        assert "no inicializado" not in str(e).lower()

def test_atomic_write(tmp_path, monkeypatch, initialized_server):
    import os
    import server
    
    def mock_replace(src, dst):
        raise Exception("Fallo en atomicidad simulado")
        
    monkeypatch.setattr(os, "replace", mock_replace)
    
    test_note = os.path.join(initialized_server.wiki_dir, "atomic_note.md")
    content = "Atomic content"
    
    with pytest.raises(Exception, match="Fallo en atomicidad simulado"):
        server.save_note(test_note, content)
        
    # El archivo de destino no debió crearse (o modificarse)
    assert not os.path.exists(test_note)
    
    # El archivo temporal sí debería existir
    assert os.path.exists(test_note + ".tmp")
