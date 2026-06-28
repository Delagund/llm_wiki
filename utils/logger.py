import logging
import json
import os
import sys

DB_DIR = os.path.expanduser("~/.config/mcp-wiki")
os.makedirs(DB_DIR, exist_ok=True)
LOG_FILE = os.path.join(DB_DIR, "mcp-wiki.log")

# Configurar logger raíz para registrar en archivo y stderr
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Evitar duplicar handlers al recargar
if not root_logger.handlers:
    # Handler para el archivo físico de logs
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(file_handler)

    # Handler para sys.stderr para que el cliente MCP capture los logs en tiempo real
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(stderr_handler)

class AppLogger:
    def _format_msg(self, context_or_msg, msg=None):
        """
        Formatea el mensaje. Si recibe un diccionario de contexto, lo expone estructuradamente
        para que los desarrolladores y clientes MCP lo lean con sus metadatos asociados.
        Explicación: Esto reemplaza logs ambiguos con una salida estructurada "Mensaje | metadata: {JSON}".
        """
        if msg is None:
            if isinstance(context_or_msg, dict):
                return json.dumps(context_or_msg, ensure_ascii=False)
            return str(context_or_msg)
            
        if isinstance(context_or_msg, dict):
            meta_json = json.dumps(context_or_msg, ensure_ascii=False)
            return f"{msg} | metadata: {meta_json}"
            
        return f"{context_or_msg} {msg}"

    def info(self, context_or_msg, msg=None):
        logging.info(self._format_msg(context_or_msg, msg))
        
    def error(self, context_or_msg, msg=None):
        logging.error(self._format_msg(context_or_msg, msg))
        
    def warning(self, context_or_msg, msg=None):
        logging.warning(self._format_msg(context_or_msg, msg))
        
    def debug(self, context_or_msg, msg=None):
        logging.debug(self._format_msg(context_or_msg, msg))

logger = AppLogger()
