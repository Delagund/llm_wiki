from fastmcp import FastMCP
import os
import json
import hashlib
import uuid
import struct
import time
import threading
from dataclasses import dataclass
from database import init_db, create_schema, VEC_AVAILABLE, VEC_AVAILABLE_LOCK, DB_LOCK, ensure_schema
from ollama_integration import get_ollama_embedding, OllamaTimeout, check_ollama_availability
from utils.chunking_strategy import chunk_text, segment_html, strip_markdown
from utils.frontmatter import parse_note_content
from utils.logger import logger
import re
from html.parser import HTMLParser

RRF_K = 60.0  # ponytail: RRF constant, tune per corpus if relevance metrics demand it

class StyleValidator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.has_style = False

    def handle_starttag(self, tag, attrs):
        if tag == 'style':
            self.has_style = True
        for attr, _ in attrs:
            if attr in ('style', 'class'):
                self.has_style = True


class RelationExtractor(HTMLParser):
    VALID_RELS = {"dependency", "concept-link", "source-summary", "comparison"}

    def __init__(self):
        super().__init__()
        self.relations: list[tuple[str, str, str]] = []  # (href, rel)

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href", "").strip()
        rel = attrs_dict.get("rel", "").strip().lower()
        if href and rel in self.VALID_RELS:
            self.relations.append((href, rel))


@dataclass
class ProjectConfig:
    """Configuración dinámica del proyecto. Resuelve rutas en runtime."""
    wiki_dir: str
    sources_dir: str
    db_path: str
    initialized: bool = True

# Configuración activa compartida por las herramientas MCP en runtime
active_config: ProjectConfig | None = None
_config_lock = threading.Lock()

mcp = FastMCP("llm-wiki-mcp")


def load_config() -> ProjectConfig | None:
    """
    Carga la configuración del proyecto con prioridad:
    1. Variable de entorno LLM_WIKI_DIR
    2. Archivo .llm_wiki_config.json en el directorio de ejecución
    Si ninguno existe, retorna None (servidor no inicializado).
    """
    env_dir = os.environ.get("LLM_WIKI_DIR")
    if env_dir:
        base_path = os.path.abspath(env_dir)
        return ProjectConfig(
            wiki_dir=os.path.join(base_path, "wiki"),
            sources_dir=os.path.join(base_path, "sources"),
            db_path=os.path.join(base_path, "wiki.db")
        )

    config_path = os.path.join(os.getcwd(), ".llm_wiki_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            return ProjectConfig(
                wiki_dir=config_data["wiki_dir"],
                sources_dir=config_data["sources_dir"],
                db_path=os.path.join(os.path.dirname(config_data["wiki_dir"]), "wiki.db")
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error({"error": str(e), "config_path": config_path}, "Error al leer configuracion local")

    return None


def validate_path_sandbox(file_path: str, allowed_base: str) -> str:
    """
    Valida que la ruta resuelta esté dentro del directorio base permitido.
    Previene ataques de Path Traversal usando os.path.abspath.
    """
    if not os.path.isabs(file_path):
        normalized = os.path.normpath(file_path)
        parts = normalized.split(os.sep)
        first_component = parts[0] if parts else ""

        allowed_base_normalized = os.path.normpath(allowed_base)
        allowed_base_name = os.path.basename(allowed_base_normalized)

        if first_component == allowed_base_name:
            parent_base = os.path.dirname(allowed_base_normalized)
            resolved = os.path.abspath(os.path.join(parent_base, normalized))
        else:
            resolved = os.path.abspath(os.path.join(allowed_base, normalized))
    else:
        resolved = os.path.abspath(file_path)

    base = os.path.abspath(allowed_base)
    if not resolved.startswith(base + os.sep) and resolved != base:
        raise ValueError(
            f"Acceso denegado: la ruta '{file_path}' esta fuera del sandbox '{allowed_base}'"
        )
    return resolved


def require_initialized() -> ProjectConfig:
    with _config_lock:
        config = active_config
    if config is None:
        raise ValueError(
            "Servidor no inicializado. Use initialize_project(base_path) para configurar."
        )
    return config


def determine_scope(file_path: str, yaml_metadata: dict, wiki_dir: str = None) -> tuple[str, int]:
    """
    Determina el project_id y visibilidad global de una nota.
    El project_id se extrae como el primer subdirectorio relativo a wiki_dir.
    """
    project_id = "default"
    if wiki_dir:
        try:
            rel_path = os.path.relpath(file_path, wiki_dir)
            parts = rel_path.split(os.sep)
            if len(parts) > 1 and parts[0] != '..':
                project_id = parts[0]
        except ValueError:
            pass
    else:
        parts = file_path.split(os.sep)
        project_id = parts[-2] if len(parts) > 1 else "default"

    is_global = 1 if yaml_metadata.get("scope") == "global" else 0
    return project_id, is_global

def serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


@mcp.tool()
def initialize_project(base_path: str) -> dict:
    """
    Inicializa un proyecto LLM-Wiki: crea estructura de carpetas, base de datos y configuracion.
    Es la unica herramienta que funciona sin que el servidor este previamente inicializado.
    """
    global active_config

    base_path = os.path.abspath(base_path)

    is_test_mode = os.environ.get("LLM_WIKI_TEST_MODE") == "true"
    if not is_test_mode and base_path == os.sep:
        raise ValueError("No se permite inicializar en la raiz del sistema de archivos")

    dirs_to_create = [
        os.path.join(base_path, "wiki", "concepts"),
        os.path.join(base_path, "wiki", "entities"),
        os.path.join(base_path, "wiki", "sources"),
        os.path.join(base_path, "wiki", "comparisons"),
        os.path.join(base_path, "sources"),
    ]
    for d in dirs_to_create:
        os.makedirs(d, exist_ok=True)

    db_path = os.path.join(base_path, "wiki.db")
    ensure_schema(db_path)

    config_data = {
        "wiki_dir": os.path.join(base_path, "wiki"),
        "sources_dir": os.path.join(base_path, "sources")
    }
    config_path = os.path.join(base_path, ".llm_wiki_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    with _config_lock:
        active_config = ProjectConfig(
            wiki_dir=config_data["wiki_dir"],
            sources_dir=config_data["sources_dir"],
            db_path=db_path
        )

    logger.info({"base_path": base_path, "db_path": db_path}, "Proyecto inicializado exitosamente")

    return {
        "status": "SUCCESS",
        "message": f"Proyecto inicializado en {base_path}",
        "wiki_dir": config_data["wiki_dir"],
        "sources_dir": config_data["sources_dir"],
        "db_path": db_path
    }


@mcp.tool()
def get_wiki_config() -> dict:
    """
    Devuelve la configuración actual del servidor: wiki_dir, sources_dir y db_path.
    El agente debe usar esta información para construir rutas absolutas al llamar a save_note.
    """
    config = require_initialized()
    return {
        "wiki_dir": config.wiki_dir,
        "sources_dir": config.sources_dir,
        "db_path": config.db_path
    }


@mcp.tool()
def save_note(file_path: str, content: str) -> dict:
    """
    Ingesta una nota con embeddings. Extrae metadata YAML, asigna project_id e is_global,
    segmenta el texto, genera embeddings (con timeout) y persiste atómicamente.
    # ponytail: ~140 lines, 16 sub-steps. SRP refactor (A-02) deferred — no operational bug.
    """
    config = require_initialized()
    file_path = validate_path_sandbox(file_path, config.wiki_dir)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    tmp_path = file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, file_path)

    t0 = time.perf_counter()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    
    with DB_LOCK:
        with init_db(config.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT content_hash FROM notes WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row and row[0] == content_hash:
                return {"status": "SKIPPED", "message": "Content hash matches existing note. Skipped."}
                
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()
            
            yaml_meta, plain_text, _ = parse_note_content(content, ext)
            if yaml_meta is None:
                yaml_meta, plain_text = {}, content.lstrip()

            # Strip markdown syntax for cleaner indexing (only affects chunking, not file on disk)
            if ext == '.md':
                plain_text = strip_markdown(plain_text)
            
            if ext == '.md':
                required = ["title", "type", "sources", "related", "created", "updated"]
                if not all(r in yaml_meta for r in required):
                    return {"status": "FAILED", "message": "Faltan campos obligatorios en MD"}
            elif ext == '.html':
                if "type" not in yaml_meta:
                    return {"status": "FAILED", "message": "Falta campo obligatorio 'type' en HTML"}
                
                validator = StyleValidator()
                validator.feed(content)
                if validator.has_style:
                    return {"status": "FAILED", "message": "Rechazado: HTML contiene etiquetas style o atributos style/class"}
                    
            project_id, is_global = determine_scope(file_path, yaml_meta, config.wiki_dir)
            note_id = str(uuid.uuid4())
            
            try:
                t1 = time.perf_counter()
                cursor.execute("BEGIN TRANSACTION")
                
                cursor.execute("SELECT id FROM notes WHERE file_path = ?", (file_path,))
                old_row = cursor.fetchone()
                if old_row:
                    old_id = old_row[0]
                    cursor.execute("DELETE FROM vec_chunks WHERE chunk_id IN (SELECT id FROM document_chunks WHERE note_id = ?)", (old_id,))
                    cursor.execute("DELETE FROM fts_chunks WHERE chunk_id IN (SELECT id FROM document_chunks WHERE note_id = ?)", (old_id,))
                    cursor.execute("DELETE FROM notes WHERE id = ?", (old_id,))
                    
                title = yaml_meta.get("title", os.path.basename(file_path))
                cursor.execute(
                    "INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash, yaml_metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (note_id, file_path, title, project_id, is_global, content_hash, json.dumps(yaml_meta, default=str))
                )
                
                if ext == '.html':
                    segments = segment_html(plain_text)
                    chunks = []
                    for text_seg, sec_id in segments:
                        for c in chunk_text(text_seg):
                            chunks.append((c, sec_id))
                else:
                    md_chunks = chunk_text(plain_text)
                    chunks = [(c, None) for c in md_chunks]
                    
                t2 = time.perf_counter()
                for idx, (chunk, sec_id) in enumerate(chunks):
                    vector = get_ollama_embedding(chunk)
                    cursor.execute(
                        "INSERT INTO document_chunks (note_id, chunk_index, content, section_id) VALUES (?, ?, ?, ?)",
                        (note_id, idx, chunk, sec_id)
                    )
                    chunk_id = cursor.lastrowid
                    
                    with VEC_AVAILABLE_LOCK:
                        vec_ok = VEC_AVAILABLE
                    if vec_ok:
                        cursor.execute(
                            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                            (chunk_id, serialize_f32(vector))
                        )
                    cursor.execute(
                        "INSERT INTO fts_chunks (chunk_id, content) VALUES (?, ?)",
                        (chunk_id, chunk)
                    )
                    
                # Extract graph relations from HTML content
                if ext == '.html':
                    extractor = RelationExtractor()
                    extractor.feed(content)
                    for href, rel in extractor.relations:
                        cursor.execute(
                            "INSERT OR IGNORE INTO note_relations (source_note_id, target_file_path, relation_type) VALUES (?, ?, ?)",
                            (note_id, href, rel)
                        )
                    
                t3 = time.perf_counter()
                cursor.execute("INSERT INTO ingestion_logs (note_id, status) VALUES (?, ?)", (file_path, "SUCCESS"))
                conn.commit()
                t4 = time.perf_counter()
                
                logger.info({
                    "action": "profiling",
                    "file": file_path,
                    "project_id": project_id,
                    "is_global": is_global,
                    "char_count": len(content),
                    "chunks": len(chunks),
                    "parse_ms": round((t1 - t0) * 1000, 2),
                    "chunking_ms": round((t2 - t1) * 1000, 2),
                    "embedding_ms": round((t3 - t2) * 1000, 2),
                    "db_commit_ms": round((t4 - t3) * 1000, 2),
                    "total_ms": round((t4 - t0) * 1000, 2)
                }, "Ingestion profiling")
                
                return {"status": "SUCCESS", "message": f"Ingested {len(chunks)} chunks."}
                
            except OllamaTimeout as e:
                conn.rollback()
                cursor.execute("INSERT INTO ingestion_logs (note_id, status, error_message) VALUES (?, ?, ?)", (file_path, "SKIPPED", str(e)))
                conn.commit()
                logger.warning({"file": file_path, "error": str(e)}, "Timeout during ingestion")
                return {"status": "SKIPPED", "message": f"Ollama timeout: {str(e)}"}
            except Exception as e:
                conn.rollback()
                cursor.execute("INSERT INTO ingestion_logs (note_id, status, error_message) VALUES (?, ?, ?)", (file_path, "FAILED", str(e)))
                conn.commit()
                logger.error({"file": file_path, "error": str(e)}, "Failed to save note")
                return {"status": "FAILED", "message": f"Error: {str(e)}"}


def sanitize_fts_query(query: str) -> str:
    """
    Sanitiza la query de FTS5 eliminando caracteres especiales que puedan
    romper la sintaxis de SQLite FTS (manteniendo alfanuméricos, espacios, guiones y guiones bajos).
    Explicación: Esto previene excepciones operacionales si la consulta contiene comillas impares o comodines mal ubicados.
    """
    if not query:
        return ""
    cleaned = "".join(c for c in query if c.isalnum() or c.isspace() or c in ("-", "_", "*", '"'))
    return " ".join(cleaned.split())


@mcp.tool()
def search_wiki(query: str, current_project: str = None, limit: int = 5, scoping_id: str = None) -> str:
    """
    Busca contexto usando búsqueda semántica híbrida (KNN Vec0 + FTS5) fusionada mediante RRF.
    Explicación: Si Ollama está disponible, ejecuta tanto búsqueda semántica como léxica,
    filtrando por proyecto y fusionando resultados usando Reciprocal Rank Fusion (RRF).
    Si Ollama no está disponible o falla, degrada a búsqueda léxica únicamente.
    # ponytail: returns str for now (A-03). Switch to list[dict] when an MCP client needs structured data.
    """
    t0 = time.perf_counter()
    config = require_initialized()

    if not current_project:
        current_project = os.getenv("MCP_PROJECT_ID", hashlib.md5(os.getcwd().encode()).hexdigest()[:8])

    use_vector = False
    query_vector = None

    # Explicación: Se chequea la disponibilidad de Ollama una única vez para evitar timeouts repetitivos
    with VEC_AVAILABLE_LOCK:
        vec_ok = VEC_AVAILABLE
    if vec_ok and check_ollama_availability():
        try:
            # Explicación: Timeout ajustado a 2s para búsquedas interactivas ágiles
            query_vector = get_ollama_embedding(query, timeout=2.0)
            use_vector = True
        except Exception:
            use_vector = False

    t1 = time.perf_counter()
    
    with init_db(config.db_path) as conn:
        cursor = conn.cursor()
        
        rrf_scores = {}
        chunks_metadata = {}
        vector_results = []
        fts_results = []

        # 1. Recuperación Semántica (KNN)
        if use_vector and query_vector:
            # Explicación: Buscamos un k mayor (50) globalmente para evitar descartar coincidencias de proyecto antes del filtro
            cursor.execute("""
                SELECT c.content, n.title, n.is_global, v.distance, c.id, c.section_id
                FROM vec_chunks v
                JOIN document_chunks c ON v.chunk_id = c.id
                JOIN notes n ON c.note_id = n.id
                WHERE v.embedding MATCH ?
                  AND (n.project_id = ? OR n.is_global = 1)
                  AND v.k = 50
                ORDER BY v.distance ASC
            """, (serialize_f32(query_vector), current_project))
            vector_results = cursor.fetchall()
            
            for rank, row in enumerate(vector_results):
                if scoping_id and row[5] != scoping_id:
                    continue
                chunk_id = row[4]
                # row: (content, title, is_global, distance, id, section_id)
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (RRF_K + rank + 1))
                chunks_metadata[chunk_id] = (row[0], row[1], row[2], f"Distancia: {row[3]:.4f}", row[5])

        # 2. Recuperación Léxica (FTS5)
        sanitized = sanitize_fts_query(query)
        if sanitized:
            fts_query_str = """
                SELECT c.content, n.title, n.is_global, c.id, c.section_id
                FROM fts_chunks f
                JOIN document_chunks c ON f.chunk_id = c.id
                JOIN notes n ON c.note_id = n.id
                WHERE fts_chunks MATCH ?
                  AND (n.project_id = ? OR n.is_global = 1)
            """
            fts_params = [sanitized, current_project]
            if scoping_id:
                fts_query_str += " AND c.section_id = ?"
                fts_params.append(scoping_id)
            fts_query_str += " LIMIT 50"
            
            cursor.execute(fts_query_str, tuple(fts_params))
            fts_results = cursor.fetchall()
            
            for rank, row in enumerate(fts_results):
                chunk_id = row[3]
                # row: (content, title, is_global, id, section_id)
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (RRF_K + rank + 1))
                if chunk_id not in chunks_metadata:
                    chunks_metadata[chunk_id] = (row[0], row[1], row[2], "FTS5 Léxico", row[4])

        # Explicación: Consolidamos y ordenamos los fragmentos fusionando ambos rankings
        sorted_chunks = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)[:limit]
        results = [chunks_metadata[cid] for cid in sorted_chunks]
        
        t2 = time.perf_counter()
        
        time_embedding = (t1 - t0) * 1000
        time_db = (t2 - t1) * 1000
        time_total = (t2 - t0) * 1000
        
        logger.info({
            "action": "profiling",
            "search_query": query,
            "sanitized_query": sanitized,
            "project_id": current_project,
            "limit": limit,
            "hybrid": use_vector,
            "vector_candidates": len(vector_results),
            "fts5_candidates": len(fts_results),
            "results_returned": len(results),
            "embedding_ms": round(time_embedding, 2),
            "db_search_ms": round(time_db, 2),
            "total_ms": round(time_total, 2)
        }, "Search profiling")
        
        logger.info({"action": "search", "query": query, "scoping_id": scoping_id, "time_total_ms": time_total, "fallback_fts5": not use_vector})
        
        if not results:
            return f"No se encontró contexto semántico o léxico para el proyecto '{current_project}'."

        output_str = (
            "[DIAGNÓSTICO]\n"
            f"- Fallback FTS5 (Ollama fuera de línea): {not use_vector}\n"
            f"- Tiempo Embedding: {time_embedding:.1f} ms\n"
            f"- Tiempo DB: {time_db:.1f} ms\n"
            f"- Tiempo Total: {time_total:.1f} ms\n\n"
        )

        chunks_str = []
        for row in results:
            scope_tag = "[GLOBAL]" if row[2] == 1 else f"[{current_project}]"
            section_id = row[4]
            section_tag = f" [Sección: {section_id}]" if section_id else ""
            chunks_str.append(f"### {scope_tag} Nota: {row[1]} ({row[3]}){section_tag}\n\n{row[0]}\n\n")

        return output_str + "".join(chunks_str)


@mcp.tool()
def get_ingestion_status(status: str = None) -> list[dict]:
    """
    Reporta notas que hayan fallado o hayan sido omitidas (SKIPPED).
    Opcionalmente filtra por status.
    """
    config = require_initialized()

    with init_db(config.db_path) as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT note_id, status, error_message, timestamp FROM ingestion_logs WHERE status = ?", (status,))
        else:
            cursor.execute("SELECT note_id, status, error_message, timestamp FROM ingestion_logs")
            
        return [{"file_path": r[0], "status": r[1], "error_message": r[2], "timestamp": r[3]} for r in cursor.fetchall()]

@mcp.tool()
def list_notes(project_id: str = None, is_global: bool = None) -> list[dict]:
    """
    Lista las notas almacenadas, con filtros opcionales.
    """
    config = require_initialized()

    with init_db(config.db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT file_path, title, project_id, is_global, updated_at FROM notes WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if is_global is not None:
            query += " AND is_global = ?"
            params.append(1 if is_global else 0)
            
        cursor.execute(query, tuple(params))
        return [{"file_path": r[0], "title": r[1], "project_id": r[2], "is_global": bool(r[3]), "updated_at": r[4]} for r in cursor.fetchall()]

def startup_lazy_check():
    """
    Sincronizacion en frio: escanea wiki/ y actualiza archivos modificados.
    """
    try:
        config = require_initialized()
    except ValueError:
        return

    wiki_dir = config.wiki_dir
    if not os.path.exists(wiki_dir):
        return

    with init_db(config.db_path) as conn:
        cursor = conn.cursor()

        for root, _, files in os.walk(wiki_dir):
            for file in files:
                if file.endswith((".md", ".html")):
                    file_path = os.path.join(root, file)

                    # Validar que el archivo esta dentro del sandbox
                    try:
                        validate_path_sandbox(file_path, wiki_dir)
                    except ValueError:
                        logger.warning({"file": file_path}, "Archivo fuera del sandbox, omitido")
                        continue

                    cursor.execute("SELECT strftime('%s', updated_at) FROM notes WHERE file_path = ?", (file_path,))
                    row = cursor.fetchone()

                    mtime = os.path.getmtime(file_path)

                    needs_update = False
                    if row is None:
                        needs_update = True
                    else:
                        db_epoch = float(row[0]) if row[0] else 0
                        if mtime > db_epoch:
                            needs_update = True

                    if needs_update:
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                            save_note(file_path, content)
                            logger.info({"file": file_path}, "Lazy sync completed")
                        except Exception as e:
                            logger.error({"file": file_path, "error": str(e)}, "Lazy sync failed")


    # T4.4: Ingesta de sources/ — autogenerar resúmenes para archivos crudos
    sources_dir = config.sources_dir
    wiki_sources_dir = os.path.join(config.wiki_dir, "sources")
    if sources_dir and os.path.exists(sources_dir):
        os.makedirs(wiki_sources_dir, exist_ok=True)
        for entry in os.listdir(sources_dir):
            src_path = os.path.join(sources_dir, entry)
            if not os.path.isfile(src_path):
                continue
            base_name, _ = os.path.splitext(entry)
            target_path = os.path.join(wiki_sources_dir, f"{base_name}.html")
            if os.path.exists(target_path):
                continue
            try:
                with open(src_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
            except UnicodeDecodeError:
                logger.warning({"file": entry}, "Source file no es UTF-8, omitido")
                continue
            html_content = f"<!--yaml\ntype: source-summary\nis_global: true\nsources: [\"sources/{entry}\"]\ntitle: {base_name}\n-->\n<article>\n{raw_content}\n</article>"
            try:
                save_note(target_path, html_content)
                logger.info({"file": target_path, "source": entry}, "Source auto-ingested")
            except Exception as e:
                logger.error({"file": target_path, "error": str(e)}, "Source ingestion failed")


def main_run():
    """Punto de entrada para el script de consola llm-wiki-mcp."""
    global active_config
    t0 = time.perf_counter()

    # Cargar configuracion con prioridad: env > JSON > None
    loaded_config = load_config()
    with _config_lock:
        active_config = loaded_config

    if active_config:
        ensure_schema(active_config.db_path)
        logger.info({
            "db_path": active_config.db_path,
            "wiki_dir": active_config.wiki_dir,
            "mcp_server": mcp.name,
            "event": "startup_init"
        }, "Iniciando servidor MCP con configuracion activa")

        try:
            with init_db(active_config.db_path) as conn:
                logger.info({
                    "db_path": active_config.db_path,
                    "status": "connected"
                }, "Base de datos inicializada y esquemas listos")
        except Exception as e:
            logger.error({"error": str(e)}, "Error al inicializar la base de datos")
            raise

        # Sincronizacion lazy en segundo plano para no bloquear el arranque
        threading.Thread(target=startup_lazy_check, daemon=True).start()
    else:
        logger.info({
            "mcp_server": mcp.name,
            "event": "startup_uninit"
        }, "Servidor MCP iniciado sin configuracion. Use initialize_project para configurar.")

    t1 = time.perf_counter()
    logger.info({
        "startup_ms": round((t1 - t0) * 1000, 2),
        "mcp_server": mcp.name,
        "status": "running"
    }, "Servidor MCP listo para recibir peticiones")

    mcp.run()


def cli_ingest(file_paths: list[str]) -> int:
    active_config = load_config()
    if active_config is None:
        print("Error: Servidor no inicializado. Configure LLM_WIKI_DIR o ejecute initialize_project.")
        return 1

    for file_path in file_paths:
        abs_path = os.path.abspath(file_path)
        if os.path.exists(abs_path):
            try:
                validate_path_sandbox(abs_path, active_config.wiki_dir)
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                logger.info({"file": abs_path}, "Manual CLI ingestion triggered")
                print(f"Ingesting {abs_path}...")
                print(save_note(abs_path, content))
            except ValueError as e:
                print(f"Security error: {e}")
            except Exception as e:
                logger.error({"file": abs_path, "error": str(e)}, "Manual ingestion failed")
                print(f"Failed to ingest {abs_path}: {e}")
        else:
            logger.error({"file": file_path}, "File not found for CLI ingest")
            print(f"File not found: {file_path}")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--ingest":
        sys.exit(cli_ingest(sys.argv[2:]))
    main_run()
