# -*- coding: utf-8 -*-

"""
Pruebas unitarias para el script de instalación de MCP `tools/install_mcp.py`.
Estas pruebas aseguran que las utilidades de configuración lean y actualicen correctamente
las configuraciones locales y globales sin interferir con los datos del usuario real.
"""

import os
import json
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock
import pytest


def test_read_existing_config_no_file(tmp_path):
    # Explicación: Comprobamos que si el archivo de configuración no existe en la raíz,
    # la función retorna None de manera segura y sin lanzar excepciones.
    from tools.install_mcp import read_existing_config
    result = read_existing_config(str(tmp_path))
    assert result is None


def test_read_existing_config_valid(tmp_path):
    # Explicación: Verificamos que si existe un archivo .llm_wiki_config.json válido con la
    # clave wiki_dir, la función extraiga correctamente la ruta configurada y la retorne.
    from tools.install_mcp import read_existing_config
    
    config_file = tmp_path / ".llm_wiki_config.json"
    wiki_path = "/some/wiki/path"
    config_file.write_text(json.dumps({"wiki_dir": wiki_path}), encoding="utf-8")
    
    result = read_existing_config(str(tmp_path))
    assert result == wiki_path


def test_read_existing_config_ends_with_wiki(tmp_path):
    # Explicación: Si la ruta configurada en wiki_dir termina en "/wiki", la función debe retornar
    # el directorio base padre (resolviendo la raíz del espacio de trabajo) para alinearse con
    # la estructura de inicialización esperada del servidor MCP de memoria.
    from tools.install_mcp import read_existing_config
    
    config_file = tmp_path / ".llm_wiki_config.json"
    wiki_path = "/some/project/wiki"
    config_file.write_text(json.dumps({"wiki_dir": wiki_path}), encoding="utf-8")
    
    result = read_existing_config(str(tmp_path))
    assert result == "/some/project"


def test_read_existing_config_malformed_json(tmp_path):
    # Explicación: Verificamos la resiliencia del lector de configuración asegurando que si el JSON
    # está corrupto o mal formado, no lance excepciones fatales sino que retorne None de forma segura.
    from tools.install_mcp import read_existing_config
    
    config_file = tmp_path / ".llm_wiki_config.json"
    config_file.write_text("{invalid json", encoding="utf-8")
    
    result = read_existing_config(str(tmp_path))
    assert result is None


def test_update_standard_mcp_config_creates_new(tmp_path):
    # Explicación: Probamos que si el archivo de configuración destino de MCP no existe,
    # la función crea los directorios padres necesarios, crea el archivo JSON nuevo e
    # inyecta la estructura correcta bajo el identificador 'llm-wiki-memory'.
    from tools.install_mcp import update_standard_mcp_config
    
    config_file = tmp_path / "subdir" / "mcp_config.json"
    python_path = "/usr/bin/python3"
    server_path = "/path/to/server.py"
    wiki_dir = "/path/to/wiki"
    
    result = update_standard_mcp_config(
        str(config_file), python_path, server_path, wiki_dir
    )
    
    assert result is True
    assert config_file.exists()
    
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "mcpServers" in data
    assert "llm-wiki-memory" in data["mcpServers"]
    server_info = data["mcpServers"]["llm-wiki-memory"]
    assert server_info["command"] == python_path
    assert server_info["args"] == [server_path]
    assert server_info["env"]["LLM_WIKI_DIR"] == wiki_dir
    assert server_info["env"]["MCP_PROJECT_ID"] == "llm_wiki"


def test_update_standard_mcp_config_updates_existing(tmp_path):
    # Explicación: Si el archivo ya contiene otros servidores de MCP configurados, validamos que la
    # función no borre la configuración existente sino que preserve los otros servidores y añada/actualice
    # solamente el servidor 'llm-wiki-memory'.
    from tools.install_mcp import update_standard_mcp_config
    
    config_file = tmp_path / "mcp_config.json"
    existing_data = {
        "mcpServers": {
            "other-server": {
                "command": "node",
                "args": ["other.js"]
            }
        }
    }
    config_file.write_text(json.dumps(existing_data), encoding="utf-8")
    
    python_path = "/usr/bin/python3"
    server_path = "/path/to/server.py"
    wiki_dir = "/path/to/wiki"
    
    result = update_standard_mcp_config(
        str(config_file), python_path, server_path, wiki_dir
    )
    
    assert result is True
    
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "mcpServers" in data
    assert "other-server" in data["mcpServers"]
    assert "llm-wiki-memory" in data["mcpServers"]
    
    assert data["mcpServers"]["other-server"]["command"] == "node"
    assert data["mcpServers"]["llm-wiki-memory"]["command"] == python_path


def test_update_standard_mcp_config_malformed_json_fallback(tmp_path):
    # Explicación: Validamos el comportamiento de recuperación (fallback) cuando el archivo MCP actual
    # está corrupto. La función debe emitir una advertencia en consola y reconstruir el archivo
    # desde cero con el nuevo servidor.
    from tools.install_mcp import update_standard_mcp_config
    
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text("{bad json", encoding="utf-8")
    
    python_path = "/usr/bin/python3"
    server_path = "/path/to/server.py"
    wiki_dir = "/path/to/wiki"
    
    result = update_standard_mcp_config(
        str(config_file), python_path, server_path, wiki_dir
    )
    
    assert result is True
    
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "mcpServers" in data
    assert "llm-wiki-memory" in data["mcpServers"]


def test_update_standard_mcp_config_write_error(tmp_path):
    # Explicación: Verificamos la tolerancia a errores de escritura (por ejemplo, por problemas de
    # permisos de disco). En tal escenario, la función debe atrapar el error devolviendo False.
    from tools.install_mcp import update_standard_mcp_config
    
    # Creamos un directorio con el mismo nombre para causar un error de escritura (IsADirectoryError)
    invalid_path = tmp_path / "invalid_dir"
    invalid_path.mkdir()
    
    result = update_standard_mcp_config(
        str(invalid_path), "/usr/bin/python3", "/path/to/server.py", "/path/to/wiki"
    )
    
    assert result is False


def test_update_claude_code_config_creates_new(tmp_path):
    # Explicación: Verificamos que si el archivo de configuración de Claude Code (~/.claude.json)
    # no existe en el sistema local, la función crea el archivo estructurándolo bajo la clave 'projects'
    # usando la ruta del proyecto resuelta en absoluto de forma dinámica.
    from tools.install_mcp import update_claude_code_config
    
    mock_claude_json = tmp_path / ".claude.json"
    project_root = str(tmp_path / "llm_wiki")
    # Aseguramos que la carpeta simulada del proyecto exista para que abspath funcione
    os.makedirs(project_root, exist_ok=True)
    
    python_path = "/usr/bin/python3"
    server_path = "/path/to/server.py"
    wiki_dir = "/path/to/wiki"
    
    # Parcheamos os.path.expanduser para apuntar al archivo de prueba temporal
    with patch("os.path.expanduser", return_value=str(mock_claude_json)):
        result = update_claude_code_config(
            project_root, python_path, server_path, wiki_dir
        )
        
    assert result is True
    assert mock_claude_json.exists()
    
    with open(mock_claude_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "projects" in data
    project_key = os.path.abspath(project_root)
    assert project_key in data["projects"]
    project_config = data["projects"][project_key]
    assert "mcpServers" in project_config
    assert "llm-wiki-memory" in project_config["mcpServers"]
    
    server_info = project_config["mcpServers"]["llm-wiki-memory"]
    assert server_info["command"] == python_path
    assert server_info["args"] == [server_path]
    assert server_info["env"]["LLM_WIKI_DIR"] == wiki_dir


def test_update_claude_code_config_preserves_other_projects(tmp_path):
    # Explicación: Comprobamos que al actualizar la configuración de Claude Code para el proyecto actual,
    # no eliminemos información referente a otros proyectos que ya estuviesen configurados previamente,
    # asegurando que sólo se modifique la clave correspondiente al proyecto actual.
    from tools.install_mcp import update_claude_code_config
    
    mock_claude_json = tmp_path / ".claude.json"
    other_project = "/path/to/other/project"
    existing_data = {
        "projects": {
            other_project: {
                "mcpServers": {
                    "some-tool": {
                        "command": "node"
                    }
                }
            }
        }
    }
    mock_claude_json.write_text(json.dumps(existing_data), encoding="utf-8")
    
    project_root = str(tmp_path / "llm_wiki")
    os.makedirs(project_root, exist_ok=True)
    python_path = "/usr/bin/python3"
    server_path = "/path/to/server.py"
    wiki_dir = "/path/to/wiki"
    
    with patch("os.path.expanduser", return_value=str(mock_claude_json)):
        result = update_claude_code_config(
            project_root, python_path, server_path, wiki_dir
        )
        
    assert result is True
    
    with open(mock_claude_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Validamos que el otro proyecto siga intacto
    assert other_project in data["projects"]
    assert data["projects"][other_project]["mcpServers"]["some-tool"]["command"] == "node"
    
    # Validamos que el proyecto actual se haya registrado correctamente
    project_key = os.path.abspath(project_root)
    assert project_key in data["projects"]
    assert "llm-wiki-memory" in data["projects"][project_key]["mcpServers"]


def test_update_claude_code_config_malformed_json_fallback(tmp_path):
    # Explicación: Verificamos el comportamiento ante JSON dañado en el archivo ~/.claude.json.
    # El proceso debe sobreescribir el archivo corrupto y registrar de manera limpia el proyecto actual.
    from tools.install_mcp import update_claude_code_config
    
    mock_claude_json = tmp_path / ".claude.json"
    mock_claude_json.write_text("{corrupt json", encoding="utf-8")
    
    project_root = str(tmp_path / "llm_wiki")
    os.makedirs(project_root, exist_ok=True)
    python_path = "/usr/bin/python3"
    server_path = "/path/to/server.py"
    wiki_dir = "/path/to/wiki"
    
    with patch("os.path.expanduser", return_value=str(mock_claude_json)):
        result = update_claude_code_config(
            project_root, python_path, server_path, wiki_dir
        )
        
    assert result is True
    
    with open(mock_claude_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "projects" in data
    project_key = os.path.abspath(project_root)
    assert project_key in data["projects"]


def test_update_claude_code_config_write_error(tmp_path):
    # Explicación: Validamos el manejo seguro de errores de escritura al intentar actualizar la
    # configuración de Claude Code. En caso de fallo de E/S, la función debe devolver False.
    from tools.install_mcp import update_claude_code_config
    
    # Creamos un directorio en el lugar del archivo para provocar un error al escribir (IsADirectoryError)
    mock_claude_json = tmp_path / ".claude.json"
    mock_claude_json.mkdir()
    
    project_root = str(tmp_path / "llm_wiki")
    os.makedirs(project_root, exist_ok=True)
    python_path = "/usr/bin/python3"
    server_path = "/path/to/server.py"
    wiki_dir = "/path/to/wiki"
    
    with patch("os.path.expanduser", return_value=str(mock_claude_json)):
        result = update_claude_code_config(
            project_root, python_path, server_path, wiki_dir
        )
        
    assert result is False


def test_check_ollama_status_success_with_model():
    # Explicación: Simulamos que Ollama responde exitosamente (HTTP 200) y que en la lista de modelos
    # ya está instalado 'nomic-embed-text'. La función debe retornar True tras verificarlo positivamente.
    from tools.install_mcp import check_ollama_status
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"models": [{"name": "nomic-embed-text:latest"}]}'
    mock_response.__enter__.return_value = mock_response
    
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = check_ollama_status()
        
    assert result is True


def test_check_ollama_status_success_without_model():
    # Explicación: Probamos que si Ollama responde correctamente con HTTP 200 pero no tiene el modelo
    # 'nomic-embed-text' en su lista, la función imprima una sugerencia pero igualmente retorne True,
    # ya que la conectividad básica con Ollama ha sido verificada.
    from tools.install_mcp import check_ollama_status
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"models": [{"name": "llama3:latest"}]}'
    mock_response.__enter__.return_value = mock_response
    
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = check_ollama_status()
        
    assert result is True


def test_check_ollama_status_unexpected_status():
    # Explicación: Si Ollama devuelve un código HTTP no exitoso (por ejemplo, 500), comprobamos que
    # la función lo detecte correctamente como fallo del servidor y devuelva False.
    from tools.install_mcp import check_ollama_status
    
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.__enter__.return_value = mock_response
    
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = check_ollama_status()
        
    assert result is False


def test_check_ollama_status_url_error():
    # Explicación: Simulamos un error de conexión (URLError), que representa la situación en la que
    # Ollama no se está ejecutando en el sistema o hay un problema de red. Debe capturar el error y retornar False.
    from tools.install_mcp import check_ollama_status
    
    url_error = urllib.error.URLError("Connection refused")
    
    with patch("urllib.request.urlopen", side_effect=url_error):
        result = check_ollama_status()
        
    assert result is False


def test_check_ollama_status_general_exception():
    # Explicación: Comprobamos que cualquier otra excepción inesperada dentro del bloque try-except
    # al consultar a Ollama sea controlada limpiamente, retornando False en lugar de fallar la ejecución.
    from tools.install_mcp import check_ollama_status
    
    with patch("urllib.request.urlopen", side_effect=RuntimeError("Unexpected error")):
        result = check_ollama_status()
        
    assert result is False
