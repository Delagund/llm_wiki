import requests
import json
import os
from utils.logger import logger

TIMEOUT_OLLAMA_CHUNK = 5.0
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

_OLLAMA_AVAILABLE = None

class OllamaTimeout(Exception):
    pass

def check_ollama_availability() -> bool:
    """
    Chequea una única vez si Ollama está disponible con un timeout de 1.0s.
    Guarda el resultado en una variable global.
    """
    global _OLLAMA_AVAILABLE
    if _OLLAMA_AVAILABLE is not None:
        return _OLLAMA_AVAILABLE

    try:
        # Petición ligera a la raíz de Ollama
        response = requests.get("http://localhost:11434/", timeout=1.0)
        _OLLAMA_AVAILABLE = response.status_code == 200
        if _OLLAMA_AVAILABLE:
            logger.info("Ollama detectado y disponible.")
        else:
            logger.warning("Ollama no está disponible (código de respuesta inválido).")
    except Exception as e:
        logger.warning({"error": str(e)}, "Ollama no detectado. Búsqueda semántica deshabilitada (fallback FTS5 inmediato).")
        _OLLAMA_AVAILABLE = False

    return _OLLAMA_AVAILABLE

def get_ollama_embedding(text: str, timeout: float = TIMEOUT_OLLAMA_CHUNK) -> list[float]:
    """
    Obtiene el embedding con timeout estricto para mitigar congelamientos.
    Lanza OllamaTimeout si excede el límite.
    """
    # Si ya sabemos de antemano que no está disponible, no hacemos la petición HTTP
    if _OLLAMA_AVAILABLE is False:
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
        logger.error({"error": str(e)}, "Ollama request failed")
        raise

