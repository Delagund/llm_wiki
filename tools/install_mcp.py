#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de instalación interactivo para registrar el servidor MCP de memoria semántica
(llm-wiki-memory) en varios entornos compatibles (Claude Desktop, Claude Code,
Antigravity global/local e IDEs externos).

Este script no tiene dependencias externas y se ejecuta de forma interactiva en la terminal.
"""

import os
import sys
import json
import urllib.request
import urllib.error

# Definición del directorio por defecto sugerido para la Wiki si no existe configuración previa.
# Se escoge esta ruta conforme a las especificaciones del usuario.
DEFAULT_WIKI_DIR = "/Users/cristian/Cerebro"

def read_existing_config(project_root):
    """
    Intenta leer el archivo .llm_wiki_config.json en la raíz del proyecto.
    Si existe, extrae la ruta base del directorio de la wiki.
    """
    config_path = os.path.join(project_root, ".llm_wiki_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            if "wiki_dir" in config_data:
                wiki_path = config_data["wiki_dir"]
                # Si la ruta termina en /wiki, asumimos que el directorio base de la wiki
                # (LLM_WIKI_DIR) es el directorio padre, para que coincida con la estructura
                # de inicialización del servidor.
                if os.path.basename(wiki_path) == "wiki":
                    return os.path.dirname(wiki_path)
                return wiki_path
        except Exception as e:
            # Imprimimos advertencia silenciosa pero no bloqueamos el flujo interactivo
            print(f"Nota: No se pudo leer el archivo de configuración existente: {e}")
    return None

def check_ollama_status():
    """
    Verifica si la instancia local de Ollama está activa y si el modelo
    de embeddings 'nomic-embed-text' se encuentra descargado.
    """
    print("\n=== 🔍 Verificación de Ollama ===")
    url = "http://localhost:11434/api/tags"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status == 200:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                models = res_json.get("models", [])
                model_names = [m.get("name") for m in models]
                
                print("✅ Ollama se está ejecutando correctamente en http://localhost:11434")
                print(f"🤖 Modelos instalados localmente: {', '.join(model_names) if model_names else 'Ninguno'}")
                
                # Buscamos si existe la variación de nomic-embed-text
                nomic_loaded = any("nomic-embed-text" in name for name in model_names)
                if nomic_loaded:
                    print("✅ El modelo de embedding 'nomic-embed-text' está disponible.")
                else:
                    print("❌ El modelo 'nomic-embed-text' no está descargado.")
                    print("   👉 Sugerencia: Ejecuta 'ollama pull nomic-embed-text' en otra terminal.")
                return True
            else:
                print(f"⚠️ Ollama respondió con código de estado inesperado: {response.status}")
                return False
    except urllib.error.URLError as e:
        print("❌ No se pudo conectar con Ollama en http://localhost:11434")
        print(f"   Detalle: {e.reason}")
        print("   👉 Asegúrate de iniciar Ollama corriendo 'ollama serve' o abriendo la aplicación.")
        return False
    except Exception as e:
        print(f"❌ Error al consultar el estado de Ollama: {e}")
        return False

def update_standard_mcp_config(config_path, python_path, server_path, wiki_dir):
    """
    Actualiza o crea un archivo de configuración MCP genérico en la ruta indicada,
    agregando o sobreescribiendo el bloque 'llm-wiki-memory'.
    """
    full_path = os.path.expanduser(config_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    config_data = {}
    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"⚠️ No se pudo leer {config_path} ({e}). Se creará de nuevo.")
            
    if "mcpServers" not in config_data:
        config_data["mcpServers"] = {}
        
    config_data["mcpServers"]["llm-wiki-memory"] = {
        "command": python_path,
        "args": [server_path],
        "env": {
            "LLM_WIKI_DIR": wiki_dir,
            "MCP_PROJECT_ID": "llm_wiki"
        }
    }
    
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        print(f"✅ Configuración actualizada con éxito en: {config_path}")
        return True
    except Exception as e:
        print(f"❌ Error al guardar la configuración en {config_path}: {e}")
        return False

def update_claude_code_config(project_root, python_path, server_path, wiki_dir):
    """
    Actualiza específicamente la configuración local de Claude Code (~/.claude.json)
    agregando el servidor MCP bajo la clave del proyecto actual de forma dinámica.
    """
    config_path = os.path.expanduser("~/.claude.json")
    
    config_data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"⚠️ No se pudo leer {config_path} ({e}). Se creará de nuevo.")
            
    if "projects" not in config_data:
        config_data["projects"] = {}
        
    project_key = os.path.abspath(project_root)
    if project_key not in config_data["projects"]:
        config_data["projects"][project_key] = {}
        
    if "mcpServers" not in config_data["projects"][project_key]:
        config_data["projects"][project_key]["mcpServers"] = {}
        
    config_data["projects"][project_key]["mcpServers"]["llm-wiki-memory"] = {
        "command": python_path,
        "args": [server_path],
        "env": {
            "LLM_WIKI_DIR": wiki_dir,
            "MCP_PROJECT_ID": "llm_wiki"
        }
    }
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        print(f"✅ Configuración de Claude Code actualizada con éxito en: ~/.claude.json")
        return True
    except Exception as e:
        print(f"❌ Error al guardar la configuración en ~/.claude.json: {e}")
        return False

def main():
    print("====================================================")
    print("🧠 Instalador del Servidor MCP - LLM Wiki Memory 🧠")
    print("====================================================\n")
    
    # Resolver la raíz del proyecto basándonos en la ubicación de este script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Determinar directorio sugerido de la wiki
    suggested_wiki_dir = read_existing_config(project_root)
    if not suggested_wiki_dir:
        suggested_wiki_dir = DEFAULT_WIKI_DIR
        
    # Solicitar interactivamente la ruta del directorio base de conocimientos
    print(f"Para continuar, especifique el directorio de la wiki (LLM_WIKI_DIR).")
    user_input = input(f"Ruta sugerida [{suggested_wiki_dir}]: ").strip()
    wiki_dir = os.path.abspath(user_input if user_input else suggested_wiki_dir)
    
    # Asegurar que el directorio base exista o preguntar si desea crearlo
    if not os.path.exists(wiki_dir):
        create_dir = input(f"El directorio '{wiki_dir}' no existe. ¿Desea crearlo? [y/N]: ").strip().lower()
        if create_dir in ("y", "yes", "s", "si"):
            try:
                # Se crean el directorio base y las subcarpetas obligatorias de wiki y sources
                os.makedirs(os.path.join(wiki_dir, "wiki"), exist_ok=True)
                os.makedirs(os.path.join(wiki_dir, "sources"), exist_ok=True)
                print(f"✅ Directorio creado con éxito: {wiki_dir} (con subcarpetas /wiki y /sources)")
            except Exception as e:
                print(f"❌ Error al crear el directorio '{wiki_dir}': {e}")
                sys.exit(1)
        else:
            print("❌ Operación abortada por el usuario. Saliendo sin cambios.")
            sys.exit(0)
    else:
        # Si el directorio ya existe, aseguramos que contenga las subcarpetas necesarias
        os.makedirs(os.path.join(wiki_dir, "wiki"), exist_ok=True)
        os.makedirs(os.path.join(wiki_dir, "sources"), exist_ok=True)
        print(f"✅ Directorio verificado: {wiki_dir}")
        
    # Resolver ruta absoluta al intérprete de Python y al script del servidor
    # Intentamos usar el entorno virtual local si existe, de lo contrario caemos en sys.executable
    venv_python = os.path.join(project_root, ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = sys.executable
    venv_python = os.path.abspath(venv_python)
    
    server_path = os.path.abspath(os.path.join(project_root, "server.py"))
    if not os.path.exists(server_path):
        print(f"❌ Error crítico: No se encontró 'server.py' en la ruta esperada: {server_path}")
        sys.exit(1)
        
    print(f"\n⚙️ Configurando bindings con:")
    print(f"  • Ejecutable Python: {venv_python}")
    print(f"  • Archivo Servidor:  {server_path}")
    print(f"  • Wiki base:         {wiki_dir}")
    
    print("\n=== 💾 Actualizando Archivos de Configuración ===")
    
    # 1. Claude Desktop
    update_standard_mcp_config(
        "~/Library/Application Support/Claude/claude_desktop_config.json",
        venv_python,
        server_path,
        wiki_dir
    )
    
    # 2. Claude Code
    update_claude_code_config(project_root, venv_python, server_path, wiki_dir)
    
    # 3. Antigravity Global
    update_standard_mcp_config(
        "~/.gemini/config/mcp_config.json",
        venv_python,
        server_path,
        wiki_dir
    )
    
    # 4. Antigravity Local
    update_standard_mcp_config(
        os.path.join(project_root, ".agents", "mcp_config.json"),
        venv_python,
        server_path,
        wiki_dir
    )
    
    # Validar estado del motor Ollama
    check_ollama_status()
    
    # Imprimir resumen final con la configuración copy-pasteable para clientes stdio tradicionales usando uvx
    print("\n====================================================")
    print("🎉 ¡Instalación Completada con Éxito! 🎉")
    print("====================================================")
    print("\nSi estás utilizando otros editores o clientes stdio genéricos")
    print("(como Cursor, Roo-Code o Cline), puedes configurar el servidor")
    print("usando el siguiente bloque JSON configurado con 'uvx':\n")
    
    uvx_config = {
        "mcpServers": {
            "llm-wiki-memory": {
                "command": "uvx",
                "args": [
                    "--from",
                    project_root,
                    "llm-wiki-mcp"
                ],
                "env": {
                    "LLM_WIKI_DIR": wiki_dir,
                    "MCP_PROJECT_ID": "llm_wiki"
                }
            }
        }
    }
    
    print(json.dumps(uvx_config, indent=2))
    print("\nNota: Recuerda que si modificas la dimensión o cambias de modelo")
    print("vectorial en Ollama, debes borrar la BD sqlite para evitar incompatibilidades:")
    print(f"rm -rf {os.path.expanduser('~/.config/mcp-wiki/mcp-wiki.db')}")
    print("====================================================\n")

if __name__ == "__main__":
    main()
