import sqlite3
import os
import shutil
import threading
from datetime import datetime

try:
    import sqlite_vec
    VEC_AVAILABLE = True
except ImportError:
    VEC_AVAILABLE = False

DB_LOCK = threading.RLock()
VEC_AVAILABLE_LOCK = threading.Lock()
SCHEMA_VERSION = 1

def init_db(db_path: str, timeout: float = 10.0) -> sqlite3.Connection:
    """
    Initializes a SQLite database connection with connection-per-request pattern.
    Enables WAL mode and loads sqlite-vec extension.
    """
    global VEC_AVAILABLE
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    
    with VEC_AVAILABLE_LOCK:
        vec_ok = VEC_AVAILABLE
    if vec_ok:
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        except Exception:
            with VEC_AVAILABLE_LOCK:
                VEC_AVAILABLE = False
            
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
        section_id TEXT,
        content TEXT,
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS note_relations (
        source_note_id TEXT,
        target_file_path TEXT,
        relation_type TEXT,
        PRIMARY KEY (source_note_id, target_file_path, relation_type),
        FOREIGN KEY(source_note_id) REFERENCES notes(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_section ON document_chunks(section_id);")

    # 3. Tabla Virtual Vectorial (Provista por sqlite-vec)
    with VEC_AVAILABLE_LOCK:
        vec_ok = VEC_AVAILABLE
    if vec_ok:
        embed_dims = int(os.getenv("OLLAMA_EMBED_DIMS", "768"))
        cursor.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            embedding float[{embed_dims}]
        );
        """)

    # 4. Tabla de Búsqueda de Texto Completo (Provista por FTS5)
    # ponytail: standalone FTS5 (not external content) for simplicity.
    # External content avoids JOIN but needs rebuild post-insert and a v2 migration.
    # Upgrade path (A-04): CREATE VIRTUAL TABLE ... USING fts5(content, content=document_chunks, content_rowid=id)
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
    
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
    conn.commit()

_MIGRATIONS = [
    None,
    create_schema,
]

def ensure_schema(db_path: str):
    version = 0
    corrupt = False
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            if row[0] != "ok":
                corrupt = True
            else:
                cursor.execute("PRAGMA user_version;")
                row = cursor.fetchone()
                version = row[0] if row else 0
            conn.close()
        except Exception:
            corrupt = True

    if corrupt:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if os.path.exists(db_path):
            shutil.copy2(db_path, f"{db_path}.corrupted.{timestamp}")
        for ext in ["", "-wal", "-shm"]:
            try:
                os.remove(db_path + ext)
            except FileNotFoundError:
                pass
        with init_db(db_path) as conn:
            create_schema(conn)
        return

    if version >= SCHEMA_VERSION:
        return

    with init_db(db_path) as conn:
        for target_version in range(version + 1, SCHEMA_VERSION + 1):
            migration = _MIGRATIONS[target_version]
            if migration:
                migration(conn)
            conn.execute(f"PRAGMA user_version = {target_version};")
            conn.commit()
