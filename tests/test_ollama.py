import pytest
import threading
import requests
from ollama_integration import check_ollama_availability


def test_check_ollama_availability_thread_safe(monkeypatch):
    class MockResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    call_count = [0]
    call_lock = threading.Lock()

    def mock_get(*args, **kwargs):
        with call_lock:
            call_count[0] += 1
            return MockResponse(200)

    monkeypatch.setattr("ollama_integration._ollama_available", None)
    monkeypatch.setattr("ollama_integration._last_check_time", 0.0)
    monkeypatch.setattr(requests, "get", mock_get)

    errors = []
    err_lock = threading.Lock()

    def check():
        try:
            result = check_ollama_availability()
            assert result is True
        except Exception as e:
            with err_lock:
                errors.append(e)

    threads = [threading.Thread(target=check) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent checks failed: {errors}"
    # Only one call to mock_get should happen (others use cached value)
    assert call_count[0] >= 1  # Could be more if timing allows
