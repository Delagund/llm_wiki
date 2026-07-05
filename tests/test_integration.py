import pytest
import os
import server
from server import save_note, search_wiki, initialize_project, startup_lazy_check
from tests.test_search import make_md

def test_e2e_uninitialized_state(monkeypatch, tmp_path):
    monkeypatch.setattr("server.active_config", None)
    with pytest.raises(ValueError, match="Servidor no inicializado"):
        save_note(str(tmp_path / "test.md"), "test")

def test_e2e_initialization_and_ingestion(tmp_path):
    # Initialize
    res = initialize_project(str(tmp_path))
    assert res["status"] == "SUCCESS"
    assert os.path.exists(res["wiki_dir"])
    assert os.path.exists(res["db_path"])

    # Create raw text file in sources/
    sources_dir = os.path.join(str(tmp_path), "sources")
    raw_path = os.path.join(sources_dir, "un_raw.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("Texto libre crudo")

    # Call startup_lazy_check
    startup_lazy_check()

    # Verify that wiki/sources/un_raw.html was created
    wiki_sources_dir = os.path.join(str(tmp_path), "wiki", "sources")
    assert os.path.exists(os.path.join(wiki_sources_dir, "un_raw.html"))

def test_e2e_search_and_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr("server.get_ollama_embedding", lambda x, *args, **kwargs: [0.1] * 768)
    monkeypatch.setattr("server.check_ollama_availability", lambda: False)
    
    initialize_project(str(tmp_path))
    
    wiki_dir = os.path.join(str(tmp_path), "wiki")
    proj_dir = os.path.join(wiki_dir, "testproj")
    os.makedirs(proj_dir, exist_ok=True)
    
    md_path = os.path.join(proj_dir, "note1.md")
    save_note(md_path, make_md("This is markdown note.", title="md note"))

    html_path = os.path.join(proj_dir, "note2.html")
    html_content = (
        '<!--yaml\n'
        'title: html note\n'
        'type: doc\n'
        'scope: global\n'
        '-->\n'
        '<article>'
        'This is html note.'
        '</article>'
    )
    save_note(html_path, html_content)
    
    # Search and verify scope tags and diagnostics
    result = search_wiki("note", current_project="testproj")
    assert "[DIAGNÓSTICO]" in result
    assert "[testproj]" in result
    assert "[GLOBAL]" in result
