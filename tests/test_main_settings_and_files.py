import json

import main


def test_update_settings_rejects_blank_ffmpeg_path(api_client):
    response = api_client.post("/api/settings", json={"ffmpeg_path": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "ffmpeg_path must not be empty"



def test_update_settings_rejects_missing_absolute_ffprobe_path(api_client, tmp_path):
    missing = tmp_path / "missing-ffprobe"

    response = api_client.post("/api/settings", json={"ffprobe_path": str(missing)})

    assert response.status_code == 400
    assert "ffprobe_path does not exist" in response.json()["detail"]



def test_update_settings_persists_and_propagates_encode_changes(api_client, monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    ffmpeg_bin = tmp_path / "ffmpeg"
    ffprobe_bin = tmp_path / "ffprobe"
    ffmpeg_bin.write_text("")
    ffprobe_bin.write_text("")

    monkeypatch.setattr(main, "_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(main, "load_config", lambda: {})

    encode_calls = []
    probe_calls = []
    watcher_calls = []
    hw_calls = []
    vaapi_calls = []

    monkeypatch.setattr(main, "set_encode_options", lambda *args: encode_calls.append(args))
    monkeypatch.setattr(main, "set_probe_refresh_settings", lambda *args: probe_calls.append(args))
    monkeypatch.setattr(main, "set_watcher_scan_settings", lambda *args: watcher_calls.append(args))
    monkeypatch.setattr(main, "set_hw_encoder", lambda hw: hw_calls.append(hw))
    monkeypatch.setattr(main, "set_vaapi_device", lambda path: vaapi_calls.append(path))

    response = api_client.post(
        "/api/settings",
        json={
            "ffmpeg_path": str(ffmpeg_bin),
            "ffprobe_path": str(ffprobe_bin),
            "needs_optimize_bitrate_threshold_kbps": 12345,
            "hw_encoder": "software",
            "output_video_codec": "hevc",
            "video_quality_cq": 21,
            "audio_lossy_action": "aac",
            "audio_languages": ["eng"],
            "output_container": "mkv",
            "scale_height": 720,
            "pix_fmt": "yuv420p",
            "encoder_speed": "slow",
            "force_stereo": True,
            "audio_normalize": True,
            "subtitle_mode": "strip",
            "deinterlace": True,
            "fps_cap": 30,
            "autocrop": True,
            "denoise": True,
            "force_encode_audio": True,
            "extra_args": "  -movflags +faststart  ",
            "vaapi_device": "/dev/dri/renderD129",
            "web_ui_enabled": True,
            "web_ui_host": "0.0.0.0",
            "web_ui_port": 9000,
            "web_ui_username": "user",
            "web_ui_password": "pass",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert hw_calls == ["software"]
    assert vaapi_calls == ["/dev/dri/renderD129"]
    assert encode_calls, "expected set_encode_options to be called"
    assert probe_calls[-1] == (str(ffprobe_bin), 12345, main.FLAG_AV1)
    assert watcher_calls[-1] == (str(ffprobe_bin), 12345, main.FLAG_AV1)

    settings = api_client.get("/api/settings", auth=("user", "pass")).json()
    assert settings["ffmpeg_path"] == str(ffmpeg_bin)
    assert settings["ffprobe_path"] == str(ffprobe_bin)
    assert settings["video_quality_cq"] == 21
    assert settings["audio_languages"] == ["eng"]
    assert settings["extra_args"] == "-movflags +faststart"
    assert settings["web_ui_port"] == 9000

    saved = json.loads(config_path.read_text())
    assert saved["ffmpeg_path"] == str(ffmpeg_bin)
    assert saved["web_ui_password"] == "pass"
    assert saved["extra_args"] == "-movflags +faststart"



def test_update_settings_rejects_webm_with_hevc(api_client, monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    monkeypatch.setattr(main, "_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(main, "load_config", lambda: {})

    response = api_client.post(
        "/api/settings",
        json={
            "output_video_codec": "hevc",
            "output_container": "webm",
        },
    )

    assert response.status_code == 400
    assert "WebM only supports VP9 and AV1" in response.json()["detail"]



def test_list_files_filters_and_sorts_results(api_client, test_db_path):
    with main.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute(
            """
            INSERT INTO files (
                folder_id, path, filename, width, video_codec, hdr_type,
                audio_tracks, needs_optimize, scanned_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "/library/a.mkv", "Movie A.mkv", 3840, "hevc", "hdr10", '[{"language": "eng", "codec_name": "aac"}]', 1, "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO files (
                folder_id, path, filename, width, video_codec, hdr_type,
                audio_tracks, needs_optimize, scanned_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "/library/b.mkv", "Movie B.mkv", 1920, "h264", None, '[{"language": "jpn", "codec_name": "opus"}]', 0, "2026-01-02T00:00:00+00:00"),
        )
        conn.commit()

    response = api_client.get(
        "/api/files",
        params={
            "resolution": "4k",
            "codec": "hevc",
            "hdr": "hdr10",
            "audio_lang": "eng",
            "audio_codec": "aac",
            "needs_optimize": 1,
            "search": "Movie",
            "sort": "scanned_at",
            "dir": "desc",
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["files"]) == 1
    assert body["files"][0]["filename"] == "Movie A.mkv"
    assert body["files"][0]["folder_path"] == "/library"



def test_list_files_uses_safe_default_sort_and_supports_audio_codec_sort(api_client, test_db_path):
    with main.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, audio_tracks) VALUES (1, ?, ?, ?)",
            ("/library/c.mkv", "C.mkv", '[{"codec_name": "opus"}]'),
        )
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, audio_tracks) VALUES (1, ?, ?, ?)",
            ("/library/a.mkv", "A.mkv", '[{"codec_name": "aac"}]'),
        )
        conn.commit()

    bad_sort = api_client.get("/api/files", params={"sort": "not_real", "dir": "asc"})
    assert bad_sort.status_code == 200
    assert [f["filename"] for f in bad_sort.json()["files"]] == ["A.mkv", "C.mkv"]

    audio_sort = api_client.get("/api/files", params={"sort": "audio_codec", "dir": "asc"})
    assert audio_sort.status_code == 200
    assert [f["filename"] for f in audio_sort.json()["files"]] == ["A.mkv", "C.mkv"]



def test_get_file_returns_row_and_404_for_missing(api_client, test_db_path):
    with main.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (1, '/library/a.mkv', 'A.mkv')"
        )
        conn.commit()

    ok = api_client.get("/api/files/1")
    assert ok.status_code == 200
    assert ok.json()["filename"] == "A.mkv"
    assert ok.json()["folder_path"] == "/library"

    missing = api_client.get("/api/files/999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "File not found"
