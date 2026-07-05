import requests
import json
import os
import time
from utils.logger import logger

TIMEOUT_OLLAMA_CHUNK = 5.0
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

_ollama_available = None
_last_check_time = 0.0

class OllamaTimeout(Exception):
    pass

def check_ollama_availability() -> bool:
    """
    Chequea una única vez si Ollama está disponible con un timeout de 1.0s.
    Guarda el resultado en una variable global.
    """
    global _ollama_available, _last_check_time
    
    if _ollama_available is False and time.time() - _last_check_time < 30.0:
        return False

    if _ollama_available is True:
        return True

    try:
        # Petición ligera a la raíz de Ollama
        response = requests.get("http://localhost:11434/", timeout=1.0)
        _ollama_available = response.status_code == 200
        if _ollama_available:
            logger.info("Ollama detectado y disponible.")
        else:
            logger.warning("Ollama no está disponible (código de respuesta inválido).")
            _last_check_time = time.time()
    except Exception as e:
        logger.warning({"error": str(e)}, "Ollama no detectado. Búsqueda semántica deshabilitada (fallback FTS5 inmediato).")
        _ollama_available = False
        _last_check_time = time.time()

    return _ollama_available

def get_ollama_embedding(text: str, timeout: float = TIMEOUT_OLLAMA_CHUNK) -> list[float]:
    """
    Obtiene el embedding con timeout estricto para mitigar congelamientos.
    Lanza OllamaTimeout si excede el límite.
    """
    global _ollama_available, _last_check_time
    # Si ya sabemos de antemano que no está disponible, no hacemos la petición HTTP
    if _ollama_available is False and time.time() - _last_check_time < 30.0:
        raise OllamaTimeout("Ollama está deshabilitado debido a falla de conexión inicial")

    try:
        response = requests.post(
            "http://localhost:11434/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except requests.exceptions.Timeout as e:
        logger.error({"error": str(e)}, "Ollama request timed out")
        raise OllamaTimeout("Ollama timeout exceeded") from e
    except requests.exceptions.RequestException as e:
        _ollama_available = False
        _last_check_time = time.time()
        logger.error({"error": str(e)}, "Ollama request failed")
        raise

