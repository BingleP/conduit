from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database
import main


@pytest.fixture
def test_db_path(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    database.init_db()
    return db_path


@pytest.fixture
def api_client(monkeypatch, test_db_path):
    monkeypatch.setattr(main, "start_encoder_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "startup_cleanup", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "start_watcher", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "set_watcher_scan_settings", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "watch_folder", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "set_probe_refresh_settings", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "set_encode_options", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "set_hw_encoder", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "set_vaapi_device", lambda *args, **kwargs: None)

    frontend_dir = Path(main.__file__).resolve().parent / "frontend"
    if not any(getattr(route, "path", None) == "/" for route in main.app.routes):
        main.app.mount("/", main.StaticFiles(directory=str(frontend_dir), html=True), name="frontend-test")

    with TestClient(main.app) as client:
        yield client
