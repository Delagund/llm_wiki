# LLM Wiki MCP Server

Un Servidor MCP (Model Context Protocol) diseñado para dotar a Asistentes de IA de **Memoria Semántica de Largo Plazo** utilizando una base de conocimientos híbrida (Markdown estilo Obsidian + HTML Estructurado Minimalista) bajo los principios del estándar **OKF (Open Knowledge Format)** y una arquitectura de recuperación (RAG) Híbrida.

---

## 🚀 Características Principales y Enfoque OKF

Este servidor de memoria semántica ha evolucionado para alinearse con los principios de interoperabilidad y estructuración formal del conocimiento.

* **Búsqueda Híbrida (Vectorial + Léxica):** Realiza búsquedas vectoriales avanzadas con KNN a través de `sqlite-vec` y modelos locales (Ollama), con una degradación elegante (fallback) hacia Full-Text Search (FTS5) en caso de fallas o timeouts de Ollama.
* **Soporte Híbrido Markdown + HTML Semántico:** Además de notas clásicas en Markdown, el sistema es compatible con notas escritas en **HTML Puro y Minimalista**.
* **Enfoque OKF (Open Knowledge Format):** Las notas estructuradas permiten mapear relaciones y clasificar el conocimiento mediante etiquetas y propiedades semánticas tipadas, optimizando el consumo de tokens y la consistencia.
* **Syntax-Aware Chunking:** Almacena notas fragmentadas (~2000 caracteres) respetando la sintaxis del lenguaje, evitando truncar bloques lógicos de código Markdown o etiquetas de bloque HTML, y favoreciendo un overlap controlado (200 caracteres).
* **Control de Idempotencia Estricto:** Evita indexar el mismo contenido varias veces usando un hash por fragmento, solucionando las brechas fantasmas y la degradación del rendimiento por acumulación excesiva de información duplicada.
* **Aislamiento de Proyectos:** Búsqueda contextualmente aislada pero con capacidad de heredar "Conocimiento Global" transversal a múltiples repositorios.
* **Linter de Integridad Cero-Latencia:** Linter nativo 100% Python (`tools/lint.py`) que audita reglas restrictivas sobre la estructura de la wiki (etiquetas balanceadas, enlaces tipados, etc.) y levanta auto-sincronizaciones en el propio servidor MCP (`--ingest`) de inmediato tras detectar cambios.

---

## 💡 Ventajas del Enfoque HTML Minimalista (OKF-Aligned)

El uso de HTML minimalista (cero CSS, sin clases ni estilos inline) presenta múltiples ventajas críticas para el procesamiento por parte de modelos de lenguaje en comparación con el Markdown plano:

1. **Estructura Semántica de Alta Precisión:** El uso de etiquetas de bloque `<section id="...">` y `<article>` permite realizar lecturas selectivas. Un agente puede recuperar secciones específicas mediante su ID (`scoping_id`), reduciendo significativamente la ventana de contexto y el consumo de tokens.
2. **Enlaces con Semántica Explícita:** Los hipervínculos estructurados `<a href="nota.html" rel="dependency">` definen explícitamente el tipo de conexión entre entidades (ej. relaciones tipadas como `dependency`, `concept-link`, `source-summary`, `comparison`), facilitando la construcción y recorrido automatizado del grafo de conocimiento.
3. **Validación Rigurosa y Estricta:** Las reglas de la sintaxis HTML permiten al linter (`tools/lint.py`) verificar en tiempo de compilación y disco que no existan etiquetas mal cerradas, que los enlaces sean válidos y que no se usen atributos prohibidos (`class` o `style` que añaden ruido de tokens innecesarios).
4. **Metadatos Ultraligeros:** El Frontmatter YAML de las notas HTML se define de manera compacta dentro de comentarios HTML (`<!--yaml ... -->`), manteniendo la interoperabilidad y legibilidad de metadatos tipo OKF.

---

## 📈 Estado Actual del Proyecto (Hitos de Desarrollo)

El proyecto ha completado de forma exitosa sus **7 Fases del Plan de Trabajo Escalonado**:

* **Fase 1: Motor SQLite & RAG Híbrido:** Persistencia en SQLite, embeddings a través de Ollama (`nomic-embed-text`) y búsqueda híbrida KNN/FTS5 con fallback automático.
* **Fase 2: Estrategia de Chunking Sintáctico:** Segmentación inteligente de archivos basada en semántica y sintaxis Markdown.
* **Fase 3: Idempotencia de Datos:** Deduplicación física mediante hashing a nivel de fragmentos.
* **Fase 4: Soporte de Notas Híbridas (HTML):** Ingestión completa de HTML minimalista compatible con linter local.
* **Fase 5: Linter de Integridad & Grafo:** Implementación de `tools/lint.py` para control estricto de rutas de archivos, kebab-case, etiquetas balanceadas, enlaces en cascada y referencias circulares.
* **Fase 6: Mecánica de Ingesta Asíncrona (Lazy Sync):** Detección en segundo plano de cambios en archivos durante el arranque (`startup_lazy_check`) para evitar bloqueos en el hilo principal del servidor MCP.
* **Fase 7: Directrices de Skill de Agente:** Configuración de instrucciones arquitectónicas integradas en `.agents/skills/manage-memory/SKILL.md` para guiar de manera autónoma a los agentes en el uso del grafo híbrido y sus convenciones.

---

## 📂 Estructura del Repositorio

- `server.py`: Servidor primario FastMCP. Contiene las herramientas expuestas a los agentes (`save_note`, `search_wiki`, `list_notes`, `get_ingestion_status`).
- `database.py`: Esquema de persistencia con transacciones SQLite, `vec0` y `fts5`.
- `ollama_integration.py`: Cliente y adaptador de embeddings para Ollama con thresholds estrictos de timeout.
- `tools/lint.py`: Herramienta de chequeo de integridad que mantiene el conocimiento sano y dispara actualizaciones al vuelo.
- `wiki/`: Base de conocimientos final estructurada en notas formato Markdown o HTML e indexada por el servidor.
- `sources/`: Recursos originales en estado crudo (ej. archivos PDF o código fuente nativo) referenciados desde la Wiki.

---

## 🛠 Instalación y Configuración

El proyecto está diseñado para funcionar como un ejecutable global del sistema a través de `pyproject.toml`.

```bash
# Recomendado: Instalación como ejecutable usando pip
pip install -e .
```

- Asegurarse de que Ollama esté corriendo o ejecutar `ollama serve` en terminal para iniciar el servidor.
- Si no está cargado el modelo predeterminado, ejecutar `ollama pull nomic-embed-text` para descargarlo.

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

### Configuración Portátil vía `uvx` (Recomendado)

Si deseas usar este MCP en clientes `stdio` sin instalar dependencias globales, puedes usar `uvx` definiendo la variable de entorno `LLM_WIKI_DIR` para indicarle dónde ubicar la carpeta de conocimientos física:

```json
{
  "mcpServers": {
    "llm-wiki-memory": {
      "command": "uvx",
      "args": ["--from", "/ruta/a/tu/clon/de/llm_wiki", "llm-wiki-mcp"],
      "env": {
        "LLM_WIKI_DIR": "/Users/tu_usuario/Documentos/Mi_Wiki/wiki",
        "MCP_PROJECT_ID": "mi_proyecto_principal"
      }
    }
  }
}
```

> **⚠️ Atención sobre los Embeddings:** Si decides cambiar el modelo vectorial (por ejemplo, a `mxbai-embed-large` de 1024 dimensiones), **DEBES borrar físicamente la base de datos** (`rm ~/.config/mcp-wiki/mcp-wiki.db`) antes de arrancar. `sqlite-vec` construye su esquema basándose en esa dimensión y arrojará un error si intentas mezclar vectores de distintos tamaños.

---

## 🤖 Configuración para Agentes (Agent Skills)

Para que cualquier modelo de lenguaje o agente IA (Cursor, Claude Code) entienda perfectamente los protocolos y flujos del servidor MCP sin intervención manual, debes indicarle que cree su propia habilidad o _Skill_.

**Instrucción requerida para el agente:**

> "Por favor, crea un archivo en `.agents/skills/manage-memory/SKILL.md` con el siguiente contenido exacto para gestionar tu forma de procesar la memoria en este proyecto:"

```yaml
---
name: manage-memory
description: Instrucciones arquitectónicas sobre cómo guardar, procesar o buscar conocimientos, PDFs, y reflexiones dentro del ecosistema LLM-Wiki MCP. Usa este skill cuando el usuario pida "memorizar", "guardar" o procesar nueva información.
---

# Flujo de Operación de la Memoria Semántica (LLM Wiki)

Actúas en un entorno respaldado por un servidor MCP de memoria semántica. Tu responsabilidad es procesar información cruda y transformarla en notas estructuradas en HTML minimalista. NO debes indexar vectores manualmente, el servidor MCP (`server.py`) hace esto automáticamente cuando usas las herramientas adecuadas.

## Escenario 1: Recibes un Archivo Crudo (PDF, Código, Doc) o un Link

Si el usuario te proporciona un documento o te pide guardar un archivo externo en la base de conocimientos:

1. **Persistencia Física:** Primero, usando tus herramientas de sistema de archivos, descarga o guarda el contenido original crudo dentro de un subdirectorio lógico en `sources/` (ej. `sources/papers/paper.pdf` o `sources/articles/blog.md`).
2. **Síntesis Analítica:** Lee y extrae las ideas principales, conceptos y conclusiones del archivo.
3. **Ingesta (save_note):** Utiliza la herramienta MCP `save_note` para guardar tu análisis en la carpeta `wiki/` en formato `.html`.
   _DEBES_ incluir un bloque YAML Frontmatter incrustado dentro de comentarios HTML que apunte físicamente al archivo guardado en `sources/`.
   **Pasa SIEMPRE la ruta absoluta** como `file_path` (ej. `/Users/.../wiki/sources/summary-paper.html`), nunca la relativa.

## Escenario 2: Reflexiones, Acuerdos de Diseño o Ideas

1. **Síntesis:** Dale forma de concepto estructurado.
2. **Ingesta Directa:** Llama a la herramienta `save_note` guardando el archivo en `wiki/` con extensión `.html`. Usa **ruta absoluta** en `file_path`.

## Especificaciones Estrictas del Formato HTML y YAML
CADA nota que envíes a `save_note` o guardes en `wiki/` debe estar en HTML puro, minimalista (sin atributos `style` ni `class`) y comenzar con este bloque YAML en comentarios HTML:

<!--yaml
title: "Título Descriptivo"
type: "concept" # Valores permitidos: concept, entity, source-summary, comparison
sources: ["sources/papers/tu_archivo.pdf"] # O rutas relativas a otros orígenes. Si no hay, pon []
related: [] # Rutas relativas a otros archivos .html o .md relacionados
created: YYYY-MM-DD # Reemplazar por la fecha ACTUAL
updated: YYYY-MM-DD # Reemplazar por la fecha ACTUAL
confidence: "high" # Valores permitidos: high, medium, low
-->

### Reglas de Estructuración y Enlaces:
- Agrupa y divide las secciones semánticas de la nota con `<section id="nombre_unico">`.
- Enlaza notas usando etiquetas de ancla HTML con el atributo de relación tipada: `<a href="conceptos-relacionados.html" rel="concept-link">Texto descriptivo</a>`.
- Todas las notas nuevas deben preferir extensión `.html`.
- Todos los nombres de archivos dentro de `wiki/` deben estar en estricto **kebab-case** sin acentos (ej. `flujo-de-trabajo-efectivo.html`).
- Ejecuta `python tools/lint.py` después de cada escritura para validar la integridad del grafo.
```

---

## 🔍 Auditoría y Comprobación de Integridad

El sistema provee 3 vías diferentes para comprobar la integridad de tu base de conocimientos:

### 1. Vía Herramientas MCP (Agentes e IA)

- Llama a `get_ingestion_status(status=None)` para revisar notas que fallaron (ej. timeouts de Ollama) o fueron omitidas (`SKIPPED`).
- Llama a `list_notes()` para asegurar qué archivos físicos están ya sincronizados en la base de datos.

### 2. Vía Logs del Servidor (Tracing)

El servidor mantiene un log persistente de baja cardinalidad donde registra sincronizaciones perezosas, ingestas CLI y errores de infraestructura en tiempo real en:
`~/.config/mcp-wiki/mcp-wiki.log`

### 3. Vía Base de Datos Cruda (SQLite de Bajo Nivel)

```bash
# Comprobar corrupción estructural nativa:
sqlite3 ~/.config/mcp-wiki/mcp-wiki.db "PRAGMA integrity_check;"

# Ver conteo de fragmentos y vectores procesados:
sqlite3 ~/.config/mcp-wiki/mcp-wiki.db "SELECT count(*) AS Notas FROM notes; SELECT count(*) AS Fragmentos FROM vec_chunks;"
```
