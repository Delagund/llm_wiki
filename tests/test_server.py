import pytest
from server import save_note, search_wiki, get_ingestion_status, list_notes
from ollama_integration import get_ollama_embedding, OllamaTimeout
import requests

# Test signatures and basic happy paths
def test_mcp_tool_contracts():
    assert callable(save_note)
    assert callable(search_wiki)
    assert callable(get_ingestion_status)
    assert callable(list_notes)

# Test edge cases using mocks

def test_ollama_timeout_handling(monkeypatch):
    """
    Verifica que se lance la excepción correcta cuando Ollama excede el timeout de 5 segundos.
    """
    def mock_post(*args, **kwargs):
        raise requests.exceptions.Timeout("Read timeout")
        
    monkeypatch.setattr(requests, "post", mock_post)
    
    with pytest.raises(OllamaTimeout) as exc:
        get_ollama_embedding("test query")
    assert "timeout" in str(exc.value).lower()

def test_ollama_connection_error(monkeypatch):
    """
    Verifica que se levanten excepciones de RequestException si Ollama no está corriendo.
    """
    def mock_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")
        
    monkeypatch.setattr(requests, "post", mock_post)
    
    with pytest.raises(requests.exceptions.RequestException):
        get_ollama_embedding("test query")
