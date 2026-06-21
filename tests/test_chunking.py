import pytest
from utils.chunking_strategy import chunk_text

def test_chunking_preserves_code_blocks():
    markdown = "```python\nprint('hola')\n```"
    chunks = chunk_text(markdown)
    assert len(chunks) == 1
    assert "```python" in chunks[0]
    assert "print('hola')" in chunks[0]

def test_chunking_splits_paragraphs():
    markdown = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
    # Even though it's below max_chars, it will group them together
    chunks = chunk_text(markdown, max_chars=20)
    # Paragraph 1 (11) + \n\n (2) + Paragraph 2 (11) = 24 > 20
    assert len(chunks) == 3
    assert "Paragraph 1" in chunks[0]
    assert "Paragraph 2" in chunks[1]
    assert "Paragraph 3" in chunks[2]

def test_chunking_large_paragraph():
    markdown = "A" * 3000
    chunks = chunk_text(markdown, max_chars=2000)
    assert len(chunks) == 1
    assert len(chunks[0]) == 3000
