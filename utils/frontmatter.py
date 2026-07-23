import re
import yaml


def parse_note_content(content: str, extension: str = ".md") -> tuple[dict | None, str | None, list[str] | None]:
    content_stripped = content.lstrip()

    def try_md():
        if not content_stripped.startswith("---"):
            return None, None, ["Falta el bloque de YAML (---)."]
        parts = content_stripped.split("---", 2)
        if len(parts) < 3:
            return None, None, ["Bloque YAML mal formado."]
        try:
            data = yaml.safe_load(parts[1]) or {}
            return data, parts[2].lstrip(), None
        except Exception as e:
            return None, None, [f"Error de parseo YAML: {e}"]

    def try_html():
        match = re.match(r'^<!--yaml\s+(.*?)\s+-->', content_stripped, re.DOTALL)
        if not match:
            return None, None, ["Falta el bloque YAML en HTML."]
        try:
            data = yaml.safe_load(match.group(1)) or {}
            return data, content_stripped[match.end():].lstrip(), None
        except Exception as e:
            return None, None, [f"Error de parseo YAML: {e}"]

    if extension == ".html":
        data, remaining, err = try_html()
        if data is not None:
            return data, remaining, err
        data, remaining, err = try_md()
        if data is not None:
            return data, remaining, err
    else:
        data, remaining, err = try_md()
        if data is not None:
            return data, remaining, err
        data, remaining, err = try_html()
        if data is not None:
            return data, remaining, err

    return None, None, ["No se encontró un bloque de metadatos válido."]
