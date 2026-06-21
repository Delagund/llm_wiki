import sqlite3
import sqlite_vec
import os

def init_db(db_path: str, timeout: float = 10.0) -> sqlite3.Connection:
    """
    Initializes a SQLite database connection with connection-per-request pattern.
    Enables WAL mode and loads sqlite-vec extension.
    """
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    return conn

def create_schema(conn: sqlite3.Connection):
    """
    Creates the required schema for semantic memory.
    """
    cursor = conn.cursor()
    
    # 1. Tabla relacional central de notas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        file_path TEXT UNIQUE,
        title TEXT,
        project_id TEXT,
        is_global INTEGER DEFAULT 0,
        content_hash TEXT,
        yaml_metadata TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Tabla relacional de fragmentos de texto (Chunks)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id TEXT,
        chunk_index INTEGER,
        content TEXT,
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
    );
    """)

    # 3. Tabla Virtual Vectorial (Provista por sqlite-vec)
    embed_dims = int(os.getenv("OLLAMA_EMBED_DIMS", "768"))
    cursor.execute(f"""
    CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
        chunk_id INTEGER PRIMARY KEY,
        embedding float[{embed_dims}]
    );
    """)

    # 4. Tabla de Búsqueda de Texto Completo (Provista por FTS5)
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
        chunk_id UNINDEXED,
        content
    );
    """)

    # 5. Tabla de Auditoría e Ingesta
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ingestion_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id TEXT,
        status TEXT,
        error_message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
