#!/usr/bin/env python3
"""
Benchmark de Recuperacion de Indice (RNF-04).
Mide el tiempo de startup_lazy_check con 500 notas sinteticas.
Ejecutar solo localmente, no en CI.
Uso: python tools/benchmark_recovery.py
"""
import os
import sys
import time
import tempfile
import shutil

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    print("=" * 60)
    print("Benchmark de Recuperacion de Indice (RNF-04)")
    print("=" * 60)

    workdir = tempfile.mkdtemp(prefix="llm_wiki_bench_")
    try:
        import server
        from server import startup_lazy_check, save_note
        import threading

        # Mock Ollama to avoid real HTTP calls
        import server as srv_mod
        import ollama_integration
        monkeypatch_get_embedding = lambda x: [0.1] * 768

        # Initialize project
        print(f"\nCreando proyecto en: {workdir}")
        os.environ["LLM_WIKI_TEST_MODE"] = "true"
        result = server.initialize_project(workdir)
        print(f"Proyecto inicializado: {result['status']}")

        # Generate 500 synthetic notes
        print("\nGenerando 500 notas sinteticas...")
        notes_dir = os.path.join(workdir, "wiki", "benchmark")
        os.makedirs(notes_dir, exist_ok=True)

        for i in range(500):
            title = f"benchmark-note-{i:04d}"
            content = f"""---
title: "{title}"
type: concept
sources: []
related: []
created: 2026-07-04
updated: 2026-07-04
---

# {title}

This is synthetic benchmark note number {i}. It contains some text content
for testing the cold sync ingestion performance. The quick brown fox jumps
over the lazy dog. Python is a programming language. SQLite is a database.
Embeddings are vector representations of text data.

## Section {i % 10}

More content for chunking and indexing purposes.
"""
            file_path = os.path.join(notes_dir, f"{title}.md")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        # Generate 10 HTML notes with links
        html_dir = os.path.join(workdir, "wiki", "benchmark-html")
        os.makedirs(html_dir, exist_ok=True)
        for i in range(10):
            content = f"""<!--yaml
type: concept
title: "html-note-{i}"
-->
<article>
<section id="s{i}">
<p>HTML benchmark note {i} with <a href="../benchmark/benchmark-note-0000.md" rel="concept-link">related link</a></p>
</section>
</article>"""
            file_path = os.path.join(html_dir, f"html-note-{i}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        # Now run startup_lazy_check and measure time
        print("\nEjecutando startup_lazy_check...")
        t0 = time.perf_counter()

        # Temporarily set active_config and mock embedding
        real_embed = srv_mod.get_ollama_embedding
        real_embed_orig = ollama_integration.get_ollama_embedding
        srv_mod.get_ollama_embedding = monkeypatch_get_embedding
        ollama_integration.get_ollama_embedding = monkeypatch_get_embedding

        try:
            startup_lazy_check()
        finally:
            srv_mod.get_ollama_embedding = real_embed
            ollama_integration.get_ollama_embedding = real_embed_orig

        elapsed = time.perf_counter() - t0
        limit = 300.0  # 5 minutes

        print(f"\n{'=' * 60}")
        print(f"RESULTADOS DEL BENCHMARK")
        print(f"{'=' * 60}")
        print(f"Tiempo total:         {elapsed:.2f} segundos ({elapsed/60:.2f} minutos)")
        print(f"Limite (5 min):       {limit:.0f} segundos")
        print(f"Cumple RNF-04:        {'OK' if elapsed < limit else 'NO'}")
        print(f"{'=' * 60}")

        # Count notes in DB
        from database import init_db
        conn = init_db(os.path.join(workdir, "wiki.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM notes")
        notes_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM document_chunks")
        chunks_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM note_relations")
        rels_count = cursor.fetchone()[0]
        conn.close()

        print(f"\nResumen de BD:")
        print(f"  Notas:                {notes_count}")
        print(f"  Chunks:               {chunks_count}")
        print(f"  Relaciones del grafo: {rels_count}")

    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        print(f"\nDirectorio temporal eliminado: {workdir}")

    sys.exit(0 if elapsed < limit else 1)


if __name__ == "__main__":
    main()
