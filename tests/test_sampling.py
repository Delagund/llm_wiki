import pytest
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock
from server import enrich_note

def test_enrich_note_success(initialized_server):
    # Setup test file
    file_path = os.path.join(initialized_server.wiki_dir, "test_note.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Contenido de prueba")
        
    mock_ctx = MagicMock()
    mock_ctx.sample = AsyncMock(return_value={"type": "concept", "keywords": ["test"]})
    
    result = asyncio.run(enrich_note(file_path, mock_ctx))
    
    assert result.get("status") == "SUCCESS"
    assert "proposed_enrichment" in result
    assert result["proposed_enrichment"] == {"type": "concept", "keywords": ["test"]}
    mock_ctx.sample.assert_called_once()

def test_enrich_note_fallback(initialized_server):
    # Setup test file
    file_path = os.path.join(initialized_server.wiki_dir, "test_note2.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Contenido de prueba 2")
        
    mock_ctx = MagicMock()
    mock_ctx.sample = AsyncMock(side_effect=Exception("Sampling not supported"))
    
    result = asyncio.run(enrich_note(file_path, mock_ctx))
    
    assert "warning" in result
    assert "error_detail" in result
    assert result["error_detail"] == "Sampling not supported"
    mock_ctx.sample.assert_called_once()
    
def test_enrich_note_invalid_path(initialized_server):
    # Path outside sandbox
    invalid_path = "/tmp/outside.md"
    mock_ctx = MagicMock()
    
    result = asyncio.run(enrich_note(invalid_path, mock_ctx))
    
    assert "error" in result
    assert "fuera del sandbox" in result["error"]
    mock_ctx.sample.assert_not_called()

def test_enrich_note_file_not_found(initialized_server):
    # File inside sandbox but doesn't exist
    not_found_path = os.path.join(initialized_server.wiki_dir, "doesnt_exist.md")
    mock_ctx = MagicMock()
    
    result = asyncio.run(enrich_note(not_found_path, mock_ctx))
    
    assert "error" in result
    assert "Error leyendo archivo" in result["error"]
    mock_ctx.sample.assert_not_called()
