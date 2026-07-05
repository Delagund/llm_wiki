import pytest
import os


@pytest.fixture
def initialized_server(monkeypatch, tmp_path):
    """Configura active_config con paths temporales para tests aislados."""
    import server
    from database import init_db, create_schema

    # Crear directorios base del sandbox de pruebas
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    db_path = str(tmp_path / "wiki.db")

    # Configurar ProjectConfig temporal con paths aislados
    config = server.ProjectConfig(
        wiki_dir=str(wiki_dir),
        sources_dir=str(sources_dir),
        db_path=db_path
    )
    monkeypatch.setattr(server, "active_config", config)

    # Inicializar esquema de la base de datos de pruebas
    conn = init_db(db_path)
    create_schema(conn)
    conn.close()

    return config
