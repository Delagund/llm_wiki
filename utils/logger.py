import logging
import json
import os

DB_DIR = os.path.expanduser("~/.config/mcp-wiki")
os.makedirs(DB_DIR, exist_ok=True)
LOG_FILE = os.path.join(DB_DIR, "mcp-wiki.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

class AppLogger:
    def _format_msg(self, context_or_msg, msg=None):
        if msg is None:
            return str(context_or_msg)
        if isinstance(context_or_msg, dict):
            # Formatea como "Mensaje estable | {"clave": "valor"}"
            return f"{msg} | {json.dumps(context_or_msg)}"
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
