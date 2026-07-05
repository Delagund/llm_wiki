import pytest
from utils.chunking_strategy import chunk_text, segment_html

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

def test_html_segmentation_by_sections():
    html = '<html><body><article id="main"><section id="s1">Hola</section><section id="s2">Mundo</section></article></body></html>'
    res = segment_html(html)
    assert res == [("Hola", "main;s1"), ("Mundo", "main;s2")]

def test_html_segmentation_no_sections():
    html = '<div>Solo soy texto plano</div>'
    res = segment_html(html)
    assert res == [("Solo soy texto plano", "article")]

def test_token_efficiency():
    html = """
    <article>
        <section>
            <p>Este es un parrafo de texto largo que contiene mucha informacion que vamos a extraer de las etiquetas html.</p>
            <p>Este texto se tiene que limpiar correctamente y mantener una longitud muy parecida al original.</p>
        </section>
    </article>
    """
    clean_text = "Este es un parrafo de texto largo que contiene mucha informacion que vamos a extraer de las etiquetas html.\nEste texto se tiene que limpiar correctamente y mantener una longitud muy parecida al original."
    
    # Simulate how segment_html output will be tokenized/chunked
    # Wait, the requirement says "Comprueba que len(texto_html) <= len(texto_limpio) * 1.15. (Tolerancia 15% RNF-02)."
    # texto_html is the output of the parser? Wait, the return is `[(extracted_text, sec_id)]`.
    # Let's concatenate the extracted text to see if its length is close to clean_text.
    # Actually, the test says: `len(texto_html) <= len(texto_limpio) * 1.15`.
    # Where texto_html is the returned segmented text (which strips tags!).
    
    # Wait, the return is exactly the text without tags. The length should be very similar.
    res = segment_html(html)
    extracted = " ".join([t for t, _ in res])
    assert len(extracted) <= len(clean_text) * 1.15
    assert len(extracted) >= len(clean_text) * 0.85
