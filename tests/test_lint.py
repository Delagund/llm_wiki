import os
import sys
import pytest
from tools.lint import (
    LintHTMLParser,
    validate_kebab_case,
    validate_metadata,
    main
)

def test_linter_html_integrity():
    # 1. Etiqueta no cerrada
    parser = LintHTMLParser()
    parser.feed("<div><p>Hola</p>")
    parser.check_final_balance()
    assert any("abierta pero no cerrada" in err for err in parser.errors)
    
    # 2. Etiqueta prohibida <style>
    parser2 = LintHTMLParser()
    parser2.feed("<style>body { color: red; }</style>")
    parser2.check_final_balance()
    assert any("Etiqueta prohibida: <style>" in err for err in parser2.errors)
    
    # 3. Atributo class prohibido
    parser3 = LintHTMLParser()
    parser3.feed('<div class="algo"></div>')
    parser3.check_final_balance()
    assert any("Atributos prohibidos" in err for err in parser3.errors)
    
    # 4. HTML Sano
    parser4 = LintHTMLParser()
    parser4.feed("<section id='main'><a href='http://test.com'>Link</a></section>")
    parser4.check_final_balance()
    assert len(parser4.errors) == 0

def test_linter_kebab_case_and_accent_validation(tmp_path, monkeypatch, capsys):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    
    bad_file = wiki_dir / "Nota_inválida.html"
    bad_file.write_text("<!--yaml\ntype: concept\ntitle: bad\n-->\n<section id='a'><p>Hola</p></section>")
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["lint.py"])
    
    with pytest.raises(SystemExit) as excinfo:
        main()
    
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "kebab-case" in captured.out or "kebab-case" in captured.err

def test_linter_broken_hyperlinks(tmp_path, monkeypatch, capsys):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    
    note_a = wiki_dir / "nota-a.html"
    note_a.write_text("""<!--yaml
type: concept
title: Nota A
-->
<section id="a">
    <a href="nota-b.html">Enlace roto</a>
    <a href="nota-c.html" rel="invalid-rel">Rel invalido</a>
</section>
""")
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["lint.py"])
    
    with pytest.raises(SystemExit) as excinfo:
        main()
        
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "Enlace roto detectado" in captured.out
    assert "Atributo rel='invalid-rel' inválido" in captured.out

def test_linter_frontmatter_flexibility():
    # .html con solo type debe pasar
    data_html = {"type": "concept"}
    errors, warnings, _ = validate_metadata(data_html, extension=".html")
    assert not errors
    
    # .md con solo type debe fallar
    data_md = {"type": "concept"}
    errors_md, warnings_md, _ = validate_metadata(data_md, extension=".md")
    assert any("Campo obligatorio faltante" in err for err in errors_md)
    assert len(errors_md) > 0

def test_e2e_linter_validation(initialized_server, monkeypatch, tmp_path):
    wiki_dir = tmp_path / "wiki"
    if not wiki_dir.exists():
        wiki_dir.mkdir()
        
    # Necesario para que `sources` no de error si está relacionado a la raíz
    sources_dir = tmp_path / "sources"
    if not sources_dir.exists():
        sources_dir.mkdir()
    
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir()
    
    nota_html = concepts_dir / "nota-sana.html"
    nota_html.write_text("""<!--yaml
type: concept
title: Nota Sana
-->
<section id="sana">
    <p>Hola</p>
    <a href="http://example.com">Ext</a>
</section>
""")

    nota_md = wiki_dir / "nota-dos.md"
    nota_md.write_text("""---
type: concept
title: Nota Dos
sources: []
related: []
created: 2023-01-01
updated: 2023-01-01
---
[[nota-sana]]
[[index]]
""")

    index_md = wiki_dir / "index.md"
    index_md.write_text("""---
type: concept
title: Index
sources: []
related: []
created: 2023-01-01
updated: 2023-01-01
---
[[nota-dos]]
""")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["lint.py"])
    
    try:
        main()
    except SystemExit as e:
        if e.code != 0:
            pytest.fail(f"Linter devolvió código de error: {e.code}")
