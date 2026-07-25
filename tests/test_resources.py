import pytest
import json
import os
from server import get_projects, get_project_notes, get_note_content, get_project_graph
from database import init_db

def test_get_projects_uninitialized(monkeypatch):
    import server
    monkeypatch.setattr(server, "active_config", None)
    result = get_projects()
    data = json.loads(result)
    assert "error" in data
    assert "Servidor no inicializado" in data["error"]

def test_get_project_notes_uninitialized(monkeypatch):
    import server
    monkeypatch.setattr(server, "active_config", None)
    result = get_project_notes("proj1")
    data = json.loads(result)
    assert "error" in data
    assert "Servidor no inicializado" in data["error"]

def test_get_projects(initialized_server):
    db_path = initialized_server.db_path
    
    with init_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       ("1", "/wiki/proj1/note1.md", "Note 1", "proj1", 0, "hash1"))
        cursor.execute("INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       ("2", "/wiki/proj2/note2.md", "Note 2", "proj2", 0, "hash2"))
        conn.commit()
    
    result = get_projects()
    data = json.loads(result)
    assert "projects" in data
    assert set(data["projects"]) == {"proj1", "proj2"}

def test_get_project_notes(initialized_server):
    db_path = initialized_server.db_path
    
    with init_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       ("1", "/wiki/proj1/note1.md", "Note 1", "proj1", 0, "hash1"))
        cursor.execute("INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       ("2", "/wiki/proj1/note2.md", "Note 2", "proj1", 1, "hash2"))
        cursor.execute("INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       ("3", "/wiki/proj2/note3.md", "Note 3", "proj2", 0, "hash3"))
        conn.commit()
        
    result = get_project_notes("proj1")
    data = json.loads(result)
    assert "project_id" in data
    assert data["project_id"] == "proj1"
    assert "notes" in data
    assert len(data["notes"]) == 2
    
    titles = set(note["title"] for note in data["notes"])
    assert titles == {"Note 1", "Note 2"}
    
    # Check is_global parsing
    for note in data["notes"]:
        if note["title"] == "Note 1":
            assert note["is_global"] is False
        elif note["title"] == "Note 2":
            assert note["is_global"] is True

def test_get_note_content_valid(initialized_server):
    wiki_dir = initialized_server.wiki_dir
    note_path = "proj1/note1.md"
    full_path = os.path.join(wiki_dir, note_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write("# Hola Mundo")
        
    result = get_note_content(note_path)
    assert result == "# Hola Mundo"

def test_get_note_content_path_traversal(initialized_server):
    result = get_note_content("../../../etc/passwd")
    data = json.loads(result)
    assert "error" in data
    # The exact error message depends on `validate_path_sandbox`, but usually it raises a ValueError.
    # From server.py we saw: `except ValueError as e: return json.dumps({"error": str(e)})`
    assert isinstance(data["error"], str)

def test_get_project_graph(initialized_server):
    wiki_dir = initialized_server.wiki_dir
    db_path = initialized_server.db_path
    project_id = "proj_graph"
    
    note1_path = os.path.join(wiki_dir, "proj_graph", "note1.html")
    note2_path = os.path.join(wiki_dir, "proj_graph", "note2.html")
    os.makedirs(os.path.dirname(note1_path), exist_ok=True)
    
    with open(note1_path, "w", encoding="utf-8") as f:
        # Valid relation
        f.write('<a href="note2.html" rel="dependency">Dep</a>')
        # Invalid relation
        f.write('<a href="note3.html" rel="invalid-rel">Inv</a>')
        # No relation
        f.write('<a href="note4.html">None</a>')
        
    with open(note2_path, "w", encoding="utf-8") as f:
        f.write('<a href="note1.html" rel="concept-link">Link</a>')
        
    with init_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       ("n1", note1_path, "Note 1", project_id, 0, "hash1"))
        cursor.execute("INSERT INTO notes (id, file_path, title, project_id, is_global, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       ("n2", note2_path, "Note 2", project_id, 0, "hash2"))
        conn.commit()

    result = get_project_graph(project_id)
    data = json.loads(result)
    assert "project_id" in data
    assert data["project_id"] == project_id
    assert "graph" in data
    
    graph = data["graph"]
    assert len(graph) == 2
    
    # Sort or check content
    for node in graph:
        if "note1.html" in node["source"]:
            assert len(node["relations"]) == 1
            assert node["relations"][0]["target"] == "note2.html"
            assert node["relations"][0]["type"] == "dependency"
        elif "note2.html" in node["source"]:
            assert len(node["relations"]) == 1
            assert node["relations"][0]["target"] == "note1.html"
            assert node["relations"][0]["type"] == "concept-link"
