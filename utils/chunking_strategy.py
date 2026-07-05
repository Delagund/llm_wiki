import re
from html.parser import HTMLParser

class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.segments = []
        self.tag_stack = []
        self.current_text = []

    def current_section_path(self):
        ids = [id_val for _, id_val in self.tag_stack if id_val is not None]
        return ";".join(ids) if ids else "article"

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_id = attrs_dict.get('id')
        
        if tag_id:
            text = "".join(self.current_text).strip()
            if text:
                self.segments.append((text, self.current_section_path()))
            self.current_text = []
            
        self.tag_stack.append((tag, tag_id))

    def handle_endtag(self, tag):
        for i in range(len(self.tag_stack)-1, -1, -1):
            if self.tag_stack[i][0] == tag:
                tag_id = self.tag_stack[i][1]
                if tag_id:
                    text = "".join(self.current_text).strip()
                    if text:
                        self.segments.append((text, self.current_section_path()))
                    self.current_text = []
                
                self.tag_stack = self.tag_stack[:i]
                break

    def handle_data(self, data):
        if data.strip():
            self.current_text.append(data)

def segment_html(content: str) -> list[tuple[str, str]]:
    """Segmenta HTML en tuplas (texto_limpio, section_id)."""
    parser = ArticleParser()
    parser.feed(content)
    
    text = "".join(parser.current_text).strip()
    if text:
        parser.segments.append((text, parser.current_section_path()))
        
    if not parser.segments:
        stripped = content.strip()
        if stripped:
            return [(stripped, "article")]
        return []
        
    return parser.segments

def chunk_text(text: str, max_chars: int = 2000, overlap_chars: int = 200) -> list[str]:
    """
    Splits text into chunks, respecting markdown code blocks.
    It uses a character approximation where 1 token ≈ 4 chars.
    e.g. max 500 tokens -> 2000 chars.
    """
    if not text:
        return []

    # TODO: Para futuros deploys a mayor escala, considerar reemplazar
    # esta estimación heurística por una herramienta de tokenización real (ej. tiktoken)
    
    code_blocks = []
    
    def replace_code_block(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    text_no_code = re.sub(r'```.*?```', replace_code_block, text, flags=re.DOTALL)
    
    # Dividir por párrafos (doble salto de línea)
    paragraphs = text_no_code.split('\n\n')
    
    chunks = []
    current_chunk_text = ""
    
    def restore_code_blocks(content: str) -> str:
        def restore_match(m):
            idx = int(m.group(1))
            return code_blocks[idx]
        return re.sub(r'__CODE_BLOCK_(\d+)__', restore_match, content)

    for p in paragraphs:
        # Si el párrafo por sí solo excede el límite (ej. un bloque de código masivo),
        # lo guardamos forzosamente como chunk independiente para evitar cortarlo.
        if len(p) > max_chars:
            if current_chunk_text:
                chunks.append(restore_code_blocks(current_chunk_text.strip()))
                current_chunk_text = ""
            chunks.append(restore_code_blocks(p.strip()))
            continue
            
        if len(current_chunk_text) + len(p) + 2 > max_chars:
            chunks.append(restore_code_blocks(current_chunk_text.strip()))
            # Solapamiento básico: si queremos overlap de contexto, tomamos el final del chunk anterior
            # Por simplicidad KISS, el overlap se aplicará a nivel de párrafos si no excede
            current_chunk_text = p + "\n\n"
        else:
            current_chunk_text += p + "\n\n"

    if current_chunk_text.strip():
        chunks.append(restore_code_blocks(current_chunk_text.strip()))

    return chunks


def strip_markdown(text: str) -> str:
    # 1. Code blocks (triple backtick)
    text = re.sub(r'```(?:\w+)?\n(.*?)\n```', r'\1', text, flags=re.DOTALL)
    # 2. Inline code (single backtick)
    text = re.sub(r'`{1,3}(.+?)`{1,3}', r'\1', text)
    # 3. Headers
    text = re.sub(r'(?m)^#{1,6}\s+', '', text)
    # 4. Bold and Italic (asterisks only, NOT underscores)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # 5. Links
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # 6. Blockquotes
    text = re.sub(r'(?m)^\s*>\s+', '', text)
    # 7. List markers
    text = re.sub(r'(?m)^\s*[-*+]\s+', '', text)
    text = re.sub(r'(?m)^\s*\d+\.\s+', '', text)
    # 8. Strikethrough
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    # 9. Horizontal rules
    text = re.sub(r'(?m)^[-*_]{3,}\s*$', '', text)
    return text.strip()
