import pytest
import asyncio
from unittest.mock import AsyncMock

import server
from database import init_db

@pytest.fixture
def mock_context():
    return AsyncMock()

def test_reindex_project_no_notes(initialized_server, mock_context):
    result = asyncio.run(server.reindex_project("proj1", ctx=mock_context))
    
    assert result == {"status": "SUCCESS", "message": "No hay notas para reindexar"}
    mock_context.info.assert_called_once_with("No hay notas en el proyecto proj1 para reindexar.")
    mock_context.report_progress.assert_not_called()

def test_reindex_project_with_notes(initialized_server, mock_context):
    config = initialized_server
    
    # Setup some dummy notes in the database
    with init_db(config.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notes (id, file_path, project_id, title, is_global, updated_at) 
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', ("note1", "/tmp/note1.md", "proj1", "Note 1", 0))
        cursor.execute('''
            INSERT INTO notes (id, file_path, project_id, title, is_global, updated_at) 
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', ("note2", "/tmp/note2.md", "proj1", "Note 2", 0))
        conn.commit()

    result = asyncio.run(server.reindex_project("proj1", ctx=mock_context))
    
    assert result == {"status": "SUCCESS", "reindexed_count": 2}
    
    # Check that report_progress was called sequentially
    assert mock_context.report_progress.call_count == 2
    mock_context.report_progress.assert_any_call(1, 2)
    mock_context.report_progress.assert_any_call(2, 2)
    
    # Check that info was emitted appropriately
    assert mock_context.info.call_count == 2
    mock_context.info.assert_any_call("Reindexando nota 1/2: /tmp/note1.md")
    mock_context.info.assert_any_call("Reindexando nota 2/2: /tmp/note2.md")
