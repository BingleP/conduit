import json
import threading

import database
import scanner


def test_detect_hdr_identifies_dolby_vision_hdr10plus_hdr10_hlg_and_sdr():
    assert scanner._detect_hdr({"codec_tag_string": "dvhe"}, []) == "dolby_vision"
    assert scanner._detect_hdr({}, [{"side_data_list": [{"side_data_type": "HDR Dynamic Metadata SMPTE2094-40"}]}]) == "hdr10plus"
    assert scanner._detect_hdr({"color_transfer": "smpte2084"}, []) == "hdr10"
    assert scanner._detect_hdr({"color_transfer": "arib-std-b67"}, []) == "hlg"
    assert scanner._detect_hdr({}, []) is None



def test_needs_optimize_flags_hi10p_av1_and_high_bitrate():
    assert scanner._needs_optimize("h264", "yuv420p10le", 1000, 25000, flag_av1=False) is True
    assert scanner._needs_optimize("av1", "yuv420p", 1000, 25000, flag_av1=True) is True
    assert scanner._needs_optimize("hevc", "yuv420p", 30000, 25000, flag_av1=False) is True
    assert scanner._needs_optimize("hevc", "yuv420p", 1000, 25000, flag_av1=False) is False



def test_probe_file_returns_none_on_nonzero_exit_and_bad_json(monkeypatch, tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"x")

    class Result:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout

    monkeypatch.setattr(scanner.subprocess, "run", lambda *args, **kwargs: Result(1, "{}"))
    assert scanner.probe_file("ffprobe", str(video)) is None

    monkeypatch.setattr(scanner.subprocess, "run", lambda *args, **kwargs: Result(0, "not json"))
    assert scanner.probe_file("ffprobe", str(video)) is None



def test_scan_folder_inserts_updates_and_prunes_missing_rows(monkeypatch, test_db_path, tmp_path):
    kept = tmp_path / "kept.mkv"
    kept.write_bytes(b"kept")
    updated = tmp_path / "updated.mkv"
    updated.write_bytes(b"updated")

    with database.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", (str(tmp_path),))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, mtime, needs_optimize) VALUES (1, ?, 'updated.mkv', ?, 1)",
            (str(updated), 1.0),
        )
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, mtime, needs_optimize) VALUES (1, ?, 'missing.mkv', ?, 1)",
            (str(tmp_path / 'missing.mkv'), 1.0),
        )
        conn.commit()

    monkeypatch.setattr(scanner, "_find_video_files", lambda folder_path: [str(kept), str(updated)])
    monkeypatch.setattr(
        scanner.os.path,
        "getmtime",
        lambda path: {str(kept): 10.0, str(updated): 20.0}[str(path)],
    )
    monkeypatch.setattr(scanner, "probe_file", lambda *args, **kwargs: {"streams": [], "format": {}})

    def fake_parse_probe(probe, file_path, threshold_kbps, flag_av1):
        return {
            "size_bytes": 123,
            "duration_s": 4.5,
            "bitrate_kbps": 678,
            "video_codec": "hevc",
            "video_profile": "Main",
            "pix_fmt": "yuv420p",
            "width": 1920,
            "height": 1080,
            "hdr_type": None,
            "color_transfer": None,
            "color_space": None,
            "audio_tracks": json.dumps([{"language": "eng"}]),
            "subtitle_tracks": json.dumps([]),
            "has_attachments": 0,
            "needs_optimize": 0,
        }

    monkeypatch.setattr(scanner, "parse_probe", fake_parse_probe)
    monkeypatch.setattr(scanner, "_start_next_scan", lambda: None)

    with scanner._scan_lock:
        scanner._scan_status = scanner.ScanStatus(scanning=True, folder_id=1)

    scanner.scan_folder(1, str(tmp_path), "ffprobe", 25000, True, force_refresh=False)

    with database.db_session() as conn:
        rows = conn.execute("SELECT path, filename, mtime, needs_optimize FROM files ORDER BY path").fetchall()

    paths = [row["path"] for row in rows]
    assert str(kept) in paths
    assert str(updated) in paths
    assert str(tmp_path / "missing.mkv") not in paths
    updated_row = next(row for row in rows if row["path"] == str(updated))
    assert updated_row["mtime"] == 20.0
    assert updated_row["needs_optimize"] == 0



def test_scan_folder_skips_unchanged_files_unless_force_refresh(monkeypatch, test_db_path, tmp_path):
    video = tmp_path / "same.mkv"
    video.write_bytes(b"same")

    with database.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", (str(tmp_path),))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, mtime) VALUES (1, ?, 'same.mkv', 12.0)",
            (str(video),),
        )
        conn.commit()

    monkeypatch.setattr(scanner, "_find_video_files", lambda folder_path: [str(video)])
    monkeypatch.setattr(scanner.os.path, "getmtime", lambda path: 12.0)
    calls = []
    monkeypatch.setattr(scanner, "probe_file", lambda *args, **kwargs: calls.append("probe") or {"streams": [], "format": {}})
    monkeypatch.setattr(scanner, "parse_probe", lambda *args, **kwargs: {
        "size_bytes": 1,
        "duration_s": 1,
        "bitrate_kbps": 1,
        "video_codec": "hevc",
        "video_profile": "Main",
        "pix_fmt": "yuv420p",
        "width": 1,
        "height": 1,
        "hdr_type": None,
        "color_transfer": None,
        "color_space": None,
        "audio_tracks": "[]",
        "subtitle_tracks": "[]",
        "has_attachments": 0,
        "needs_optimize": 0,
    })
    monkeypatch.setattr(scanner, "_start_next_scan", lambda: None)

    with scanner._scan_lock:
        scanner._scan_status = scanner.ScanStatus(scanning=True, folder_id=1)
    scanner.scan_folder(1, str(tmp_path), "ffprobe", 25000, True, force_refresh=False)
    assert calls == []

    with scanner._scan_lock:
        scanner._scan_status = scanner.ScanStatus(scanning=True, folder_id=1)
    scanner.scan_folder(1, str(tmp_path), "ffprobe", 25000, True, force_refresh=True)
    assert calls == ["probe"]



def test_start_scan_deduplicates_and_upgrades_force_refresh(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            self.args = args
        def start(self):
            started.append(self.args)

    monkeypatch.setattr(scanner.threading, "Thread", FakeThread)

    with scanner._scan_lock:
        scanner._scan_queue.clear()
        scanner._scan_status = scanner.ScanStatus(scanning=True, folder_id=99)

    scanner.start_scan(1, "/library", "ffprobe", 25000, True, force_refresh=False)
    scanner.start_scan(1, "/library", "ffprobe", 25000, True, force_refresh=True)

    with scanner._scan_lock:
        queued = list(scanner._scan_queue)
    assert queued == [(1, "/library", "ffprobe", 25000, True, True)]
    assert started == []

    with scanner._scan_lock:
        scanner._scan_queue.clear()
        scanner._scan_status = scanner.ScanStatus(scanning=False)

    scanner.start_scan(2, "/library2", "ffprobe", 123, False, force_refresh=True)
    assert started == [(2, "/library2", "ffprobe", 123, False, True)]



def test_debounce_handler_schedules_rescan_with_latest_settings(monkeypatch):
    handler = scanner._DebounceHandler(7, "/library")
    triggered = []
    monkeypatch.setattr(scanner, "start_scan", lambda *args: triggered.append(args))
    scanner.set_watcher_scan_settings("ffprobe-custom", 7777, False)

    handler._trigger()

    assert triggered == [(7, "/library", "ffprobe-custom", 7777, False)]
