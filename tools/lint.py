#!/usr/bin/env python3
import os
import sys
import re
import yaml
import unicodedata
import subprocess
from datetime import datetime

def normalize_link(link: str) -> str:
    """Normalize diacritics, lowercase, replace spaces/underscores with hyphens."""
    normalized = unicodedata.normalize('NFKD', link).encode('ASCII', 'ignore').decode('ASCII')
    return re.sub(r'[\s_]+', '-', normalized.lower())

def extract_wikilinks(content: str) -> list[str]:
    """Extract [[wikilinks]] from content."""
    links = []
    # Pattern: [[link]] or [[link|alias]]
    pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    for match in pattern.finditer(content):
        raw_link = match.group(1).strip()
        links.append(normalize_link(raw_link))
    return links

def scan_markdown_files(directory: str) -> list[str]:
    """Return list of absolute paths to .md files."""
    md_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith('.md'):
                md_files.append(os.path.join(root, f))
    return md_files

def validate_kebab_case(name: str) -> bool:
    return bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', name))

def parse_frontmatter(content: str):
    """Parse YAML frontmatter and validate strictly."""
    if not content.startswith('---'):
        return False, ["Falta el bloque de inicio de YAML (---) en la primera línea."], None

    parts = content.split('---', 2)
    if len(parts) < 3:
        return False, ["Falta el bloque de cierre de YAML (---)."], None

    yaml_text = parts[1]
    try:
        data = yaml.safe_load(yaml_text)
    except Exception as e:
        return False, [f"Error de parseo YAML: {e}"], None

    if not isinstance(data, dict):
        return False, ["El frontmatter no es un diccionario válido."], None

    errors = []
    required_fields = ["title", "type", "sources", "related", "created", "updated"]
    for req in required_fields:
        if req not in data:
            errors.append(f"Campo obligatorio faltante: '{req}'.")

    if errors:
        return False, errors, None

    # Validate type
    valid_types = ["concept", "entity", "source-summary", "comparison"]
    if data.get("type") not in valid_types:
        errors.append(f"Tipo de nota inválido: '{data.get('type')}'. Valores permitidos: {valid_types}")

    # Validate confidence
    if "confidence" in data:
        valid_confidences = ["high", "medium", "low"]
        if data["confidence"] not in valid_confidences:
            errors.append(f"Nivel de confianza inválido: '{data['confidence']}'. Valores permitidos: {valid_confidences}")

    # Validate dates
    date_regex = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if "created" in data and not date_regex.match(str(data["created"])):
        errors.append(f"Formato de fecha 'created' inválido: '{data['created']}'. Debe ser YYYY-MM-DD.")
    if "updated" in data and not date_regex.match(str(data["updated"])):
        errors.append(f"Formato de fecha 'updated' inválido: '{data['updated']}'. Debe ser YYYY-MM-DD.")

    # Normalize list fields
    if isinstance(data.get("sources"), str):
        data["sources"] = [data["sources"]]
    elif not data.get("sources"):
        data["sources"] = []

    if isinstance(data.get("related"), str):
        data["related"] = [data["related"]]
    elif not data.get("related"):
        data["related"] = []

    return len(errors) == 0, errors, data

def main():
    args = sys.argv
    current_dir = os.getcwd()
    wiki_dir = os.path.join(current_dir, "wiki")
    

    print(f"Iniciando auditoría estricta (lint) del Wiki en: {wiki_dir}...")
    
    md_files = scan_markdown_files(wiki_dir)
    if not md_files:
        print("⚠️ No se encontraron archivos Markdown (.md) en el directorio 'wiki/'.")
        return
        
    errors = []
    all_file_names = set()
    all_inbound_links = set()
    titles_map = {}
    
    for file_path in md_files:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        all_file_names.add(base_name.lower())
        
    for file_path in md_files:
        relative_path = os.path.relpath(file_path, current_dir)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        base_name_lower = base_name.lower()
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except:
            errors.append({"file": relative_path, "msg": "No se pudo leer el archivo."})
            continue
            
        if True:
            if not validate_kebab_case(base_name):
                errors.append({"file": relative_path, "msg": f"Nombre de archivo inválido: '{base_name}.md'. Debe estar en kebab-case estricto."})
                
            is_valid, validation_errors, parsed_data = parse_frontmatter(content)
            if not is_valid:
                for err in validation_errors:
                    errors.append({"file": relative_path, "msg": f"YAML Frontmatter inválido: {err}"})
            elif parsed_data:
                title = parsed_data.get("title")
                if title:
                    norm_title = normalize_link(title)
                    if norm_title in titles_map:
                        errors.append({"file": relative_path, "msg": f"Título duplicado: '{title}' ya existe en '{titles_map[norm_title]}'."})
                    else:
                        titles_map[norm_title] = relative_path
                        
                for source in parsed_data.get("sources", []):
                    if not os.path.exists(os.path.join(current_dir, source)):
                        errors.append({"file": relative_path, "msg": f"Archivo de origen no encontrado en disco: '{source}'."})
                        
                for relation in parsed_data.get("related", []):
                    if not os.path.exists(os.path.join(current_dir, relation)):
                        errors.append({"file": relative_path, "msg": f"Archivo relacionado no encontrado en disco: '{relation}'."})
                        
                type_ = parsed_data.get("type")
                if type_ not in ["concept", "entity"]:
                    all_inbound_links.add(base_name_lower)
        else:
            all_inbound_links.add(base_name_lower)
            
        links = extract_wikilinks(content)
        for link in links:
            all_inbound_links.add(link)
            if link not in ["index", "log", "overview"] and link not in all_file_names:
                errors.append({"file": relative_path, "msg": f"Enlace roto detectado: [[{link}]] no coincide con ningún archivo."})
                
    for file_path in md_files:
        relative_path = os.path.relpath(file_path, current_dir)
        base_name_lower = os.path.splitext(os.path.basename(file_path))[0].lower()
        if base_name_lower not in all_inbound_links:
            errors.append({"file": relative_path, "msg": "Nota huérfana detectada: Ninguna otra nota la enlaza."})
            
    print("\n---------------- REPORTE DE AUDITORÍA (LINT) ----------------")
    print(f"Total de archivos verificados: {len(md_files)}")
    
    if not errors:
        print("✅ ¡El Wiki está completamente sano! No se encontraron problemas.")
    else:
        print(f"⚠️  Se encontraron {len(errors)} anomalía(s):")
        print("-" * 61)
        for e in errors:
            print(f"❌ {e['file']}: {e['msg']}")
        print("-" * 61)
        sys.exit(1)

if __name__ == "__main__":
    main()
