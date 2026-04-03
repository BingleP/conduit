import sqlite3
from pathlib import Path

import database
import main


def _set_test_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    database.init_db()
    return db_path


def test_database_stats_reports_counts(monkeypatch, tmp_path):
    _set_test_db(monkeypatch, tmp_path)

    with database.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute("INSERT INTO folders (path) VALUES (?)", (main._DROPPED_FOLDER_PATH,))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, needs_optimize) VALUES (1, ?, 'movie.mkv', 1)",
            (str(tmp_path / "movie.mkv"),),
        )
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, needs_optimize) VALUES (2, ?, 'drop.mkv', 0)",
            (str(tmp_path / "drop.mkv"),),
        )
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'queued')")
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'done')")
        conn.commit()

    monkeypatch.setattr(main, "get_scan_status", lambda: {"scanning": False, "queued": 0, "current_file": None})

    stats = main.database_stats()

    assert stats["folders"] == 1
    assert stats["files"] == 2
    assert stats["dropped_files"] == 1
    assert stats["jobs"] == {"queued": 1, "running": 0, "done": 1, "error": 0}


def test_prune_missing_database_files_removes_missing_rows_and_empty_dropped_folder(monkeypatch, tmp_path):
    existing = tmp_path / "keep.mkv"
    existing.write_text("video")
    missing = tmp_path / "missing.mkv"
    dropped_missing = tmp_path / "dropped_missing.mkv"

    _set_test_db(monkeypatch, tmp_path)

    with database.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute("INSERT INTO folders (path) VALUES (?)", (main._DROPPED_FOLDER_PATH,))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (1, ?, 'keep.mkv')",
            (str(existing),),
        )
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (1, ?, 'missing.mkv')",
            (str(missing),),
        )
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (2, ?, 'dropped_missing.mkv')",
            (str(dropped_missing),),
        )
        conn.commit()

    result = main.prune_missing_database_files()

    assert result["deleted_files"] == 2
    with database.db_session() as conn:
        filenames = [row["filename"] for row in conn.execute("SELECT filename FROM files ORDER BY id").fetchall()]
        folders = [row["path"] for row in conn.execute("SELECT path FROM folders ORDER BY id").fetchall()]

    assert filenames == ["keep.mkv"]
    assert folders == ["/library"]


def test_refresh_database_queues_force_refresh_scan_for_real_folders(monkeypatch, tmp_path):
    _set_test_db(monkeypatch, tmp_path)

    with database.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library/a",))
        conn.execute("INSERT INTO folders (path) VALUES (?)", (main._DROPPED_FOLDER_PATH,))
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library/b",))
        conn.commit()

    queued = []

    def fake_start_scan(folder_id, folder_path, ffprobe_path, threshold_kbps, flag_av1, force_refresh=False):
        queued.append((folder_id, folder_path, ffprobe_path, threshold_kbps, flag_av1, force_refresh))

    monkeypatch.setattr(main, "start_scan", fake_start_scan)
    monkeypatch.setattr(main, "FFPROBE_PATH", "ffprobe-test")
    monkeypatch.setattr(main, "THRESHOLD_KBPS", 12345)
    monkeypatch.setattr(main, "FLAG_AV1", False)

    result = main.refresh_database()

    assert result["queued_folders"] == 2
    assert queued == [
        (1, "/library/a", "ffprobe-test", 12345, False, True),
        (3, "/library/b", "ffprobe-test", 12345, False, True),
    ]


def test_reset_database_rejects_when_active_jobs_exist(monkeypatch, tmp_path):
    _set_test_db(monkeypatch, tmp_path)

    with database.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute("INSERT INTO files (folder_id, path, filename) VALUES (1, ?, 'movie.mkv')", (str(tmp_path / 'movie.mkv'),))
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'queued')")
        conn.commit()

    monkeypatch.setattr(main, "get_scan_status", lambda: {"scanning": False})

    try:
        main.reset_database()
    except main.HTTPException as exc:
        assert exc.status_code == 409
        assert "Queued or running jobs exist" in exc.detail
    else:
        raise AssertionError("Expected reset_database to reject active jobs")


def test_reset_database_clears_records_and_unwatches_real_folders(monkeypatch, tmp_path):
    _set_test_db(monkeypatch, tmp_path)

    with database.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library/a",))
        conn.execute("INSERT INTO folders (path) VALUES (?)", (main._DROPPED_FOLDER_PATH,))
        conn.execute("INSERT INTO files (folder_id, path, filename) VALUES (1, ?, 'movie.mkv')", (str(tmp_path / 'movie.mkv'),))
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'done')")
        conn.commit()

    unwatched = []
    monkeypatch.setattr(main, "get_scan_status", lambda: {"scanning": False})
    monkeypatch.setattr(main, "unwatch_folder", lambda folder_id: unwatched.append(folder_id))

    result = main.reset_database()

    assert result == {
        "ok": True,
        "deleted_folders": 1,
        "deleted_files": 1,
        "deleted_jobs": 1,
        "message": "Database reset. All tracked folders and file records were removed.",
    }
    assert unwatched == [1]

    with database.db_session() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()["cnt"]
            for table in ("folders", "files", "jobs")
        }

    assert counts == {"folders": 0, "files": 0, "jobs": 0}
