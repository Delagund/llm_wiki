# LLM Wiki MCP Server

Un Servidor MCP (Model Context Protocol) diseñado para dotar a Asistentes de IA de **Memoria Semántica de Largo Plazo** utilizando una base de conocimientos en formato Markdown (estilo Obsidian) respaldada por una arquitectura de recuperación (RAG) Híbrida.

## 🚀 Características Principales

- **Búsqueda Híbrida (Vectorial + Léxica):** Realiza búsquedas vectoriales avanzadas con KNN a través de `sqlite-vec` y modelos locales (Ollama), con una degradación elegante (fallback) hacia Full-Text Search (FTS5) en caso de fallas o timeouts.
- **Syntax-Aware Chunking:** Almacena notas fragmentadas (~2000 caracteres) respetando la sintaxis del lenguaje, evitando truncar bloques lógicos de código Markdown y favoreciendo el overlap (200 caracteres).
- **Control de Idempotencia Estricto:** Evita indexar el mismo contenido varias veces usando un hash por fragmento, solucionando las brechas fantasmas y la degradación del rendimiento por acumulación excesiva.
- **Aislamiento de Proyectos:** Búsqueda contextualmente aislada pero con capacidad de heredar "Conocimiento Global" transversal a múltiples repositorios.
- **Linter de Integridad Cero-Latencia:** Linter nativo 100% Python (`tools/lint.py`) que audita reglas restrictivas sobre la wiki y levanta auto-sincronizaciones en el propio servidor MCP (`--ingest`) de inmediato tras detectar cambios.

## 📂 Estructura del Repositorio

- `server.py`: Servidor primario FastMCP. Contiene las herramientas expuestas a los agentes (`save_note`, `search_wiki`, `list_notes`, `get_ingestion_status`).
- `database.py`: Esquema de persistencia con transacciones SQLite, `vec0` y `fts5`.
- `ollama_integration.py`: Cliente y adaptador de embeddings para Ollama con thresholds estrictos de timeout.
- `tools/lint.py`: Herramienta de chequeo de integridad que mantiene el conocimiento sano y dispara actualizaciones al vuelo.
- `wiki/`: Base de conocimientos final estructurada en notas formato Markdown e indexada por el servidor.
- `sources/`: Recursos originales en estado crudo (ej. archivos PDF o código fuente nativo) referenciados desde la Wiki.

## 🛠 Instalación y Configuración

El proyecto está diseñado para funcionar como un ejecutable global del sistema a través de `pyproject.toml`.

```bash
# Recomendado: Instalación como ejecutable usando pip
pip install -e .
```

Agrega la configuración a tu cliente MCP preferido (Claude Code, Cursor, etc.):

```json
{
  "mcpServers": {
    "llm-wiki-memory": {
      "command": "llm-wiki-mcp",
      "args": [],
      "env": {
        "MCP_PROJECT_ID": "mi_proyecto_principal",
        "OLLAMA_EMBED_MODEL": "nomic-embed-text",
        "OLLAMA_EMBED_DIMS": "768"
      }
    }
  }
}
```

### Configuración Portátil vía `uvx` (Recomendado para instalaciones nuevas)
Si deseas usar este MCP en clientes `stdio` (como Qwen Desktop, Claude o Cursor) sin instalar dependencias globales y descargando todo directamente al vuelo, puedes usar `uvx` de Astral. 

Para que esto funcione, debes definir la variable `LLM_WIKI_DIR` para indicarle al servidor efímero dónde guardar físicamente los archivos Markdown en tu computadora:

```json
{
  "mcpServers": {
    "llm-wiki-memory": {
      "command": "uvx",
      "args": [
        "--from", "/ruta/a/tu/clon/de/llm_wiki", 
        "llm-wiki-mcp"
      ],
      "env": {
        "LLM_WIKI_DIR": "/Users/tu_usuario/Documentos/Mi_Wiki/wiki",
        "MCP_PROJECT_ID": "mi_proyecto_principal"
      }
    }
  }
}
```
*(Nota: En lugar de una ruta local en `--from`, si el proyecto estuviera publicado, podrías usar directamente el nombre en PyPI u origen git).*

> **⚠️ Atención sobre los Embeddings:** Si decides cambiar el modelo vectorial (por ejemplo, a `mxbai-embed-large` de 1024 dimensiones), **DEBES borrar físicamente la base de datos** (`rm ~/.config/mcp-wiki/mcp-wiki.db`) antes de arrancar. `sqlite-vec` construye su esquema basándose en esa dimensión y arrojará un error si intentas mezclar vectores de distintos tamaños.

---

## 🤖 Configuración para Agentes (Agent Skills)

Para que cualquier modelo de lenguaje o agente IA (Cursor, Chatbots) entienda perfectamente los protocolos y flujos del servidor MCP sin intervención manual, debes indicarle que cree su propia habilidad o *Skill*.

**Instrucción requerida para el agente:**

> "Por favor, crea un archivo en `.agents/skills/manage-memory/SKILL.md` con el siguiente contenido exacto para gestionar tu forma de procesar la memoria en este proyecto:"

```yaml
---
name: manage-memory
description: Instrucciones arquitectónicas sobre cómo guardar, procesar o buscar conocimientos, PDFs, y reflexiones dentro del ecosistema LLM-Wiki MCP. Usa este skill cuando el usuario pida "memorizar", "guardar" o procesar nueva información.
---

# Flujo de Operación de la Memoria Semántica (LLM Wiki)

Actúas en un entorno respaldado por un servidor MCP de memoria semántica. Tu responsabilidad es procesar información cruda y transformarla en notas altamente estructuradas. NO debes indexar vectores manualmente, el servidor MCP (`server.py`) hace esto automáticamente cuando usas las herramientas adecuadas.

## Escenario 1: Recibes un Archivo Crudo (PDF, Código, Doc) o un Link
Si el usuario te proporciona un documento o te pide guardar un archivo externo en la base de conocimientos:

1. **Persistencia Física:** Primero, usando tus herramientas de sistema de archivos, descarga o guarda el contenido original crudo dentro de un subdirectorio lógico en `sources/` (ej. `sources/papers/paper.pdf` o `sources/articles/blog.md`).
2. **Síntesis Analítica:** Lee y extrae las ideas principales, conceptos y conclusiones del archivo.
3. **Ingesta (save_note):** Utiliza la herramienta MCP `save_note` para guardar tu análisis en la carpeta `wiki/` (ej. `wiki/sources/summary-paper.md`). 
   *DEBES* incluir un bloque YAML Frontmatter estricto en el contenido de la nota que apunte físicamente al archivo guardado en `sources/`.

## Escenario 2: Reflexiones, Acuerdos de Diseño o Ideas Sueltas
Si el usuario te dice "recuerda esto", "guarda este bloque de código" o llegan a una conclusión arquitectónica conversando:

1. **Síntesis:** Dale forma de concepto estructurado.
2. **Ingesta Directa:** Llama a la herramienta `save_note` guardando el archivo en `wiki/concepts/` o `wiki/entities/`. 
   Dado que no hay un archivo físico externo, puedes referenciar la conversación en `sources` o dejarlo vacío si aplica.

## Especificaciones Estrictas del YAML Frontmatter
CADA nota que envíes a `save_note` o guardes en `wiki/` DEBE comenzar con este bloque YAML (el linter fallará si falta):

---
title: "Título Descriptivo"
type: "concept" # Valores permitidos: concept, entity, source-summary, comparison
sources: ["sources/papers/tu_archivo.pdf"] # O rutas relativas a otros orígenes. Si no hay, pon []
related: [] # Rutas relativas a otros archivos .md relacionados, ej: ["wiki/concepts/foo.md"]
created: YYYY-MM-DD # Reemplazar por la fecha ACTUAL
updated: YYYY-MM-DD # Reemplazar por la fecha ACTUAL
confidence: "high" # Valores permitidos: high, medium, low
---
[Contenido Markdown de la nota aquí...]

## Convenciones de Nomenclatura
- Todos los nombres de archivos dentro de `wiki/` deben estar en estricto **kebab-case** sin acentos (ej. `flujo-de-trabajo-efectivo.md`).

## Búsqueda de Conocimiento
Para consultar información pasada, SIEMPRE utiliza la herramienta MCP `search_wiki(query)`. Te devolverá bloques semánticamente relevantes usando búsqueda vectorial KNN y, en caso de fallo local, se degradará elegantemente a búsqueda léxica FTS5.
```

---

## 🔍 Auditoría y Comprobación de Integridad

El sistema provee 3 vías diferentes para comprobar la integridad de tu base de conocimientos:

### 1. Vía Herramientas MCP (Agentes e IA)
Los agentes pueden auto-diagnosticar la memoria usando las herramientas expuestas:
- Llama a `get_ingestion_status(status=None)` para revisar notas que fallaron (ej. timeouts de Ollama) o fueron omitidas (`SKIPPED`).
- Llama a `list_notes()` para asegurar qué archivos físicos están ya sincronizados en la base de datos.

### 2. Vía Logs del Servidor (Tracing)
El servidor mantiene un log persistente de baja cardinalidad donde registra sincronizaciones perezosas, ingestas CLI y errores de infraestructura. Puedes revisarlo en tiempo real:
```bash
tail -f ~/.config/mcp-wiki/mcp-wiki.log
```

### 3. Vía Base de Datos Cruda (SQLite de Bajo Nivel)
Dado que persistimos usando SQLite tradicional sin ofuscaciones, puedes auditar el archivo `.db` de forma nativa. 

**Comprobar corrupción estructural nativa:**
```bash
sqlite3 ~/.config/mcp-wiki/mcp-wiki.db "PRAGMA integrity_check;"
```

**Ver conteo de fragmentos y vectores procesados:**
```bash
sqlite3 ~/.config/mcp-wiki/mcp-wiki.db "SELECT count(*) AS Notas FROM notes; SELECT count(*) AS Fragmentos FROM vec_chunks;"
```
