from fastmcp import FastMCP
import os
import json
import hashlib
import yaml
import uuid
import struct
import time
import threading
from database import init_db, create_schema
from ollama_integration import get_ollama_embedding, OllamaTimeout
from utils.chunking_strategy import chunk_text
from utils.logger import logger

DB_DIR = os.path.expanduser("~/.config/mcp-wiki")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "central_memory.db")

mcp = FastMCP("llm-wiki-central-memory")

def parse_frontmatter(content: str) -> tuple[dict, str]:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                metadata = yaml.safe_load(parts[1]) or {}
                return metadata, parts[2].strip()
            except yaml.YAMLError:
                pass
    return {}, content.strip()

def determine_scope(file_path: str, yaml_metadata: dict) -> tuple[str, int]:
    parts = file_path.split(os.sep)
    project_id = parts[-2] if len(parts) > 1 else "default"
    is_global = 1 if yaml_metadata.get("scope") == "global" or "global" in file_path.lower() else 0
    return project_id, is_global

def serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


@mcp.tool()
def save_note(file_path: str, content: str) -> dict:
    """
    Ingesta una nota con embeddings. Extrae metadata YAML, asigna project_id e is_global,
    segmenta el texto, genera embeddings (con timeout) y persiste atómicamente.
    """
    t0 = time.perf_counter()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    
    with init_db(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT content_hash FROM notes WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        if row and row[0] == content_hash:
            return {"status": "SKIPPED", "message": "Content hash matches existing note. Skipped."}
            
        yaml_meta, plain_text = parse_frontmatter(content)
        project_id, is_global = determine_scope(file_path, yaml_meta)
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
            
            chunks = chunk_text(plain_text)
            t2 = time.perf_counter()
            for idx, chunk in enumerate(chunks):
                vector = get_ollama_embedding(chunk)
                cursor.execute(
                    "INSERT INTO document_chunks (note_id, chunk_index, content) VALUES (?, ?, ?)",
                    (note_id, idx, chunk)
                )
                chunk_id = cursor.lastrowid
                
                cursor.execute(
                    "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                    (chunk_id, serialize_f32(vector))
                )
                cursor.execute(
                    "INSERT INTO fts_chunks (chunk_id, content) VALUES (?, ?)",
                    (chunk_id, chunk)
                )
                
            t3 = time.perf_counter()
            cursor.execute("INSERT INTO ingestion_logs (note_id, status) VALUES (?, ?)", (file_path, "SUCCESS"))
            conn.commit()
            t4 = time.perf_counter()
            
            logger.info({
                "action": "profiling",
                "file": file_path,
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


@mcp.tool()
def search_wiki(query: str, current_project: str = None, limit: int = 5) -> str:
    """
    Busca contexto usando búsqueda semántica híbrida (KNN Vec0) con fallback a FTS5 léxico.
    Filtra por project_id o contenido is_global=1.
    """
    t0 = time.perf_counter()
    if not current_project:
        current_project = os.getenv("MCP_PROJECT_ID", hashlib.md5(os.getcwd().encode()).hexdigest()[:8])

    try:
        query_vector = get_ollama_embedding(query)
        use_vector = True
    except Exception:
        use_vector = False

    t1 = time.perf_counter()
    with init_db(DB_PATH) as conn:
        cursor = conn.cursor()
        
        if use_vector:
            cursor.execute("""
                SELECT c.content, n.title, n.is_global, v.distance
                FROM vec_chunks v
                JOIN document_chunks c ON v.chunk_id = c.id
                JOIN notes n ON c.note_id = n.id
                WHERE v.embedding MATCH ?
                  AND (n.project_id = ? OR n.is_global = 1)
                  AND v.k = ?
                ORDER BY v.distance ASC
            """, (serialize_f32(query_vector), current_project, limit))
        else:
            cursor.execute("""
                SELECT c.content, n.title, n.is_global, 1.0 AS distance
                FROM fts_chunks f
                JOIN document_chunks c ON f.chunk_id = c.id
                JOIN notes n ON c.note_id = n.id
                WHERE fts_chunks MATCH ?
                  AND (n.project_id = ? OR n.is_global = 1)
                LIMIT ?
            """, (query, current_project, limit))
            
        results = cursor.fetchall()
        t2 = time.perf_counter()
        
        logger.info({
            "action": "profiling",
            "search_query": query,
            "fallback": not use_vector,
            "embedding_ms": round((t1 - t0) * 1000, 2),
            "db_search_ms": round((t2 - t1) * 1000, 2),
            "total_ms": round((t2 - t0) * 1000, 2)
        }, "Search profiling")
        
        if not results:
            return f"No se encontró contexto semántico o léxico para el proyecto '{current_project}'."

        output = []
        for row in results:
            scope_tag = "[GLOBAL]" if row[2] == 1 else f"[{current_project}]"
            meta_dist = f" (Distancia: {row[3]:.4f})" if use_vector else " (Fallback FTS5)"
            output.append(f"### {scope_tag} Nota: {row[1]}{meta_dist}\n{row[0]}\n---")

        return "\n".join(output)


@mcp.tool()
def get_ingestion_status(status: str = None) -> list[dict]:
    """
    Reporta notas que hayan fallado o hayan sido omitidas (SKIPPED).
    Opcionalmente filtra por status.
    """
    with init_db(DB_PATH) as conn:
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
    with init_db(DB_PATH) as conn:
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
    Sincronización Extraordinaria: Escanea el directorio wiki/
    y actualiza los archivos que hayan sido modificados desde la última indexación.
    """
    default_wiki_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wiki")
    wiki_dir = os.environ.get("LLM_WIKI_DIR", default_wiki_dir)
    if not os.path.exists(wiki_dir):
        return

    with init_db(DB_PATH) as conn:
        cursor = conn.cursor()
        
        for root, _, files in os.walk(wiki_dir):
            for file in files:
                if file.endswith(".md"):
                    file_path = os.path.join(root, file)
                    
                    # Verificar la última modificación en DB
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

def main_run():
    """Punto de entrada para el script de consola llm-wiki-mcp."""
    with init_db(DB_PATH) as conn:
        create_schema(conn)
        
    # Ejecutamos la validación lazy en segundo plano para no bloquear el 'initialize' del cliente MCP
    threading.Thread(target=startup_lazy_check, daemon=True).start()
    
    mcp.run()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--ingest":
        for file_path in sys.argv[2:]:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    logger.info({"file": file_path}, "Manual CLI ingestion triggered")
                    print(f"Ingesting {file_path}...")
                    print(save_note(file_path, content))
                except Exception as e:
                    logger.error({"file": file_path, "error": str(e)}, "Manual ingestion failed")
                    print(f"Failed to ingest {file_path}: {e}")
            else:
                logger.error({"file": file_path}, "File not found for CLI ingest")
                print(f"File not found: {file_path}")
        sys.exit(0)

    main_run()
