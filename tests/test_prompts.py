import pytest
from server import ingest_note, search_and_synthesize, reflexion

def test_ingest_note_default_type():
    raw_text = "Some random text"
    result = ingest_note(raw_text)
    assert "<!--yaml" in result
    assert "type: concept" in result
    assert raw_text in result
    assert "<a href=" in result
    assert "rel=" in result

def test_ingest_note_custom_type():
    raw_text = "Another text"
    result = ingest_note(raw_text, note_type="entity")
    assert "<!--yaml" in result
    assert "type: entity" in result
    assert raw_text in result

def test_search_and_synthesize_no_project():
    query = "What is MCP?"
    result = search_and_synthesize(query)
    assert query in result
    assert "Enfócate específicamente en el proyecto" not in result
    assert "herramienta de búsqueda" in result

def test_search_and_synthesize_with_project():
    query = "How to test?"
    project = "llm-wiki"
    result = search_and_synthesize(query, project=project)
    assert query in result
    assert f"Enfócate específicamente en el proyecto '{project}'" in result

def test_reflexion():
    topic = "The meaning of life"
    result = reflexion(topic)
    assert topic in result
    assert "1. Resumen del tema" in result
    assert "2. Puntos clave y posibles conexiones" in result
    assert "3. Preguntas abiertas o siguientes pasos" in result
