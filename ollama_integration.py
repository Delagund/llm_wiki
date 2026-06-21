import requests
import json
import os
from utils.logger import logger

TIMEOUT_OLLAMA_CHUNK = 5.0
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

class OllamaTimeout(Exception):
    pass

def get_ollama_embedding(text: str) -> list[float]:
    """
    Obtiene el embedding con timeout estricto para mitigar congelamientos.
    Lanza OllamaTimeout si excede el límite.
    """
    try:
        response = requests.post(
            "http://localhost:11434/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=TIMEOUT_OLLAMA_CHUNK
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except requests.exceptions.Timeout as e:
        logger.error({"error": str(e)}, "Ollama request timed out")
        raise OllamaTimeout("Ollama timeout exceeded") from e
    except requests.exceptions.RequestException as e:
        logger.error({"error": str(e)}, "Ollama request failed")
        raise
