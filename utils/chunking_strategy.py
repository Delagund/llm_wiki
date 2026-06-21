import re

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
