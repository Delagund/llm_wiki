#!/usr/bin/env python3
import os
import sys
import re
import yaml
import unicodedata
import subprocess
from datetime import datetime
from html.parser import HTMLParser

class LintHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.errors = []
        self.open_tags = []
        self.local_links = []
        self.void_tags = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        
        if tag == 'style':
            self.errors.append("Etiqueta prohibida: <style>")
            return
            
        if 'style' in attr_dict or 'class' in attr_dict:
            self.errors.append(f"Atributos prohibidos ('style' o 'class') en etiqueta <{tag}>")
            
        if tag == 'section':
            if 'id' not in attr_dict:
                self.errors.append("Etiqueta <section> requiere el atributo 'id'")
                
        if tag == 'a':
            if 'href' not in attr_dict:
                self.errors.append("Etiqueta <a> requiere el atributo 'href'")
            else:
                href = attr_dict['href']
                if not href.startswith('http') and not href.startswith('#'):
                    rel = attr_dict.get('rel')
                    self.local_links.append((href, rel))
                    valid_rels = ['dependency', 'concept-link', 'source-summary', 'comparison']
                    if rel and rel not in valid_rels:
                        self.errors.append(f"Atributo rel='{rel}' inválido en enlace a '{href}'. Valores permitidos: {valid_rels}")
        
        if tag not in self.void_tags:
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if tag == 'style':
            return
            
        if tag not in self.void_tags:
            if not self.open_tags:
                self.errors.append(f"Cierre de etiqueta </{tag}> sin etiqueta de apertura correspondiente.")
            elif self.open_tags[-1] == tag:
                self.open_tags.pop()
            else:
                self.errors.append(f"Etiqueta mal balanceada: se esperaba </{self.open_tags[-1]}> pero se encontró </{tag}>")

    def check_final_balance(self):
        for tag in self.open_tags:
            self.errors.append(f"Etiqueta <{tag}> abierta pero no cerrada.")

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

def scan_note_files(directory: str) -> list[str]:
    """Return list of absolute paths to .md and .html files."""
    note_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith('.md') or f.endswith('.html'):
                note_files.append(os.path.join(root, f))
    return note_files

def validate_kebab_case(name: str) -> bool:
    return bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', name))

def parse_note_content(content: str, extension: str = ".md"):
    """Parse YAML frontmatter or HTML comment YAML."""
    content_stripped = content.lstrip()

    def parse_md():
        if content_stripped.startswith("---"):
            parts = content_stripped.split("---", 2)
            if len(parts) >= 3:
                try:
                    data = yaml.safe_load(parts[1]) or {}
                    return data, parts[2].lstrip(), None
                except Exception as e:
                    return None, None, [f"Error de parseo YAML: {e}"]
        return None, None, ["Falta el bloque de YAML."]
        
    def parse_html():
        match = re.match(r'^<!--yaml\s+(.*?)\s+-->', content_stripped, re.DOTALL)
        if match:
            try:
                data = yaml.safe_load(match.group(1)) or {}
                return data, content_stripped[match.end():].lstrip(), None
            except Exception as e:
                return None, None, [f"Error de parseo YAML: {e}"]
        return None, None, ["Falta el bloque YAML en HTML."]

    if extension == ".html":
        data, remaining, err = parse_html()
        if data is not None: return data, remaining, err
        data, remaining, err = parse_md()
        if data is not None: return data, remaining, err
    else:
        data, remaining, err = parse_md()
        if data is not None: return data, remaining, err
        data, remaining, err = parse_html()
        if data is not None: return data, remaining, err

    return None, None, ["No se encontró un bloque de metadatos válido."]

def validate_metadata(data, extension=".md"):
    errors = []
    warnings = []
    if not isinstance(data, dict):
        return ["El frontmatter no es un diccionario válido."], [], None
    
    if extension == '.md':
        required_fields = ["title", "type", "sources", "related", "created", "updated"]
    else:
        required_fields = ["type"]
        
    for req in required_fields:
        if req not in data:
            errors.append(f"Campo obligatorio faltante: '{req}'.")

    # Validate type
    valid_types = ["concept", "entity", "source-summary", "comparison"]
    if data.get("type") not in valid_types:
        warnings.append(f"Tipo de nota desconocido: '{data.get('type')}'. Valores permitidos originales: {valid_types}")

    # Validate confidence
    if "confidence" in data:
        valid_confidences = ["high", "medium", "low"]
        if data["confidence"] not in valid_confidences:
            warnings.append(f"Nivel de confianza desconocido: '{data['confidence']}'. Valores permitidos originales: {valid_confidences}")

    # Validate dates
    date_regex = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if "created" in data and not date_regex.match(str(data.get("created", ""))):
        errors.append(f"Formato de fecha 'created' inválido: '{data.get('created', '')}'. Debe ser YYYY-MM-DD.")
    if "updated" in data and not date_regex.match(str(data.get("updated", ""))):
        errors.append(f"Formato de fecha 'updated' inválido: '{data.get('updated', '')}'. Debe ser YYYY-MM-DD.")

    # Normalize list fields
    if "sources" in data:
        if isinstance(data["sources"], str):
            data["sources"] = [data["sources"]]
        elif not data["sources"]:
            data["sources"] = []
            
    if "related" in data:
        if isinstance(data["related"], str):
            data["related"] = [data["related"]]
        elif not data["related"]:
            data["related"] = []

    return errors, warnings, data

def main():
    args = sys.argv
    current_dir = os.getcwd()
    wiki_dir = os.path.join(current_dir, "wiki")
    

    print(f"Iniciando auditoría estricta (lint) del Wiki en: {wiki_dir}...")
    
    md_files = scan_note_files(wiki_dir)
    if not md_files:
        print("⚠️ No se encontraron archivos (.md o .html) en el directorio 'wiki/'.")
        return
        
    errors = []
    warnings = []
    all_file_names = set()
    all_inbound_links = set()
    titles_map = {}
    
    for file_path in md_files:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        all_file_names.add(base_name.lower())
        
    for file_path in md_files:
        relative_path = os.path.relpath(file_path, current_dir)
        base_name, ext = os.path.splitext(os.path.basename(file_path))
        base_name_lower = base_name.lower()
        ext = ext.lower()
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except:
            errors.append({"file": relative_path, "msg": "No se pudo leer el archivo."})
            continue
            
        if not validate_kebab_case(base_name):
            errors.append({"file": relative_path, "msg": f"Nombre de archivo inválido: '{base_name}{ext}'. Debe estar en kebab-case estricto."})
            
        data, _, parse_err = parse_note_content(content, ext)
        if parse_err:
            for err in parse_err:
                errors.append({"file": relative_path, "msg": f"YAML Frontmatter inválido: {err}"})
        elif data is not None:
            validation_errors, validation_warnings, parsed_data = validate_metadata(data, ext)
            if validation_errors:
                for err in validation_errors:
                    errors.append({"file": relative_path, "msg": f"Metadata inválida: {err}"})
            if validation_warnings:
                for warn in validation_warnings:
                    warnings.append({"file": relative_path, "msg": f"Metadata Warning: {warn}"})
                    
            type_ = parsed_data.get("type")
            if ext == ".html" and type_:
                type_mapping = {
                    "concept": "concepts",
                    "entity": "entities",
                    "source-summary": "sources",
                    "comparison": "comparisons"
                }
                expected_dir = type_mapping.get(type_)
                if expected_dir:
                    path_parts = relative_path.split(os.sep)
                    if expected_dir not in path_parts:
                        errors.append({"file": relative_path, "msg": f"Ubicación física errónea: type '{type_}' debería estar en una carpeta '{expected_dir}'."})

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
                    
            if type_ not in ["concept", "entity"]:
                all_inbound_links.add(base_name_lower)
        else:
            all_inbound_links.add(base_name_lower)
            
        links = extract_wikilinks(content)
        for link in links:
            all_inbound_links.add(link)
            if link not in ["index", "log", "overview"] and link not in all_file_names:
                errors.append({"file": relative_path, "msg": f"Enlace roto detectado: [[{link}]] no coincide con ningún archivo."})

        if ext == ".html":
            parser = LintHTMLParser()
            parser.feed(content)
            parser.check_final_balance()
            for err in parser.errors:
                errors.append({"file": relative_path, "msg": f"Error HTML: {err}"})
            
            for href, rel in parser.local_links:
                link_base = normalize_link(os.path.splitext(os.path.basename(href))[0])
                all_inbound_links.add(link_base)
                
                if href.startswith('sources/'):
                    target_path = os.path.join(current_dir, href)
                else:
                    target_path = os.path.join(wiki_dir, href)
                    
                if not os.path.exists(target_path):
                    errors.append({"file": relative_path, "msg": f"Enlace roto detectado (href): {href}"})
                
    for file_path in md_files:
        relative_path = os.path.relpath(file_path, current_dir)
        base_name_lower = os.path.splitext(os.path.basename(file_path))[0].lower()
        if base_name_lower not in all_inbound_links:
            errors.append({"file": relative_path, "msg": "Nota huérfana detectada: Ninguna otra nota la enlaza."})
            
    print("\n---------------- REPORTE DE AUDITORÍA (LINT) ----------------")
    print(f"Total de archivos verificados: {len(md_files)}")
    
    if warnings:
        print(f"⚠️  Se encontraron {len(warnings)} advertencia(s):")
        for w in warnings:
            print(f"⚠️ {w['file']}: {w['msg']}")
        print("-" * 61)
    
    if not errors:
        print("✅ ¡El Wiki está completamente sano! No se encontraron errores críticos.")
    else:
        print(f"❌ Se encontraron {len(errors)} error(es) crítico(s):")
        print("-" * 61)
        for e in errors:
            print(f"❌ {e['file']}: {e['msg']}")
        print("-" * 61)
        sys.exit(1)

if __name__ == "__main__":
    main()
