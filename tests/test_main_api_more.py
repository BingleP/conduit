import json

import main


def test_create_jobs_rejects_invalid_container_combo(api_client):
    response = api_client.post(
        "/api/jobs",
        json={
            "file_ids": [1],
            "job_type": "encode",
            "output_video_codec": "vp9",
            "output_container": "mp4",
        },
    )

    assert response.status_code == 400
    assert "VP9 is not compatible" in response.json()["detail"]



def test_create_jobs_inserts_one_job_and_skips_duplicate_queued_job(api_client, test_db_path):
    with main.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (1, '/library/a.mkv', 'a.mkv')"
        )
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (1, '/library/b.mkv', 'b.mkv')"
        )
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'queued')")
        conn.commit()

    response = api_client.post(
        "/api/jobs",
        json={
            "file_ids": [1, 2],
            "job_type": "encode",
            "keep_original": True,
            "output_video_codec": "hevc",
            "output_container": "mkv",
            "force_stereo": True,
            "audio_normalize": True,
            "deinterlace": True,
            "autocrop": True,
            "denoise": True,
            "force_encode_audio": True,
            "extra_args": "-movflags +faststart",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 1
    assert len(body["job_ids"]) == 1

    with main.db_session() as conn:
        rows = conn.execute(
            "SELECT file_id, keep_original, force_stereo, audio_normalize, deinterlace, autocrop, denoise, force_encode_audio, extra_args FROM jobs ORDER BY id"
        ).fetchall()

    assert len(rows) == 2
    created = rows[1]
    assert created["file_id"] == 2
    assert created["keep_original"] == 1
    assert created["force_stereo"] == 1
    assert created["audio_normalize"] == 1
    assert created["deinterlace"] == 1
    assert created["autocrop"] == 1
    assert created["denoise"] == 1
    assert created["force_encode_audio"] == 1
    assert created["extra_args"] == "-movflags +faststart"



def test_cancel_job_rejects_non_queued_and_deletes_queued(api_client, test_db_path):
    with main.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (1, '/library/a.mkv', 'a.mkv')"
        )
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'running')")
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'queued')")
        conn.commit()

    bad = api_client.delete("/api/jobs/1")
    assert bad.status_code == 400
    assert "Only queued jobs can be cancelled" in bad.json()["detail"]

    ok = api_client.delete("/api/jobs/2")
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}

    with main.db_session() as conn:
        remaining = conn.execute("SELECT id FROM jobs ORDER BY id").fetchall()
    assert [row["id"] for row in remaining] == [1]



def test_user_preset_crud_round_trip(api_client, monkeypatch):
    saved = []
    monkeypatch.setattr(main, "USER_PRESETS", [])
    monkeypatch.setattr(main, "_save_config", lambda: saved.append("saved"))

    create = api_client.post(
        "/api/presets",
        json={
            "name": "My Preset",
            "hw_encoder": "software",
            "output_video_codec": "av1",
            "video_quality_cq": 30,
            "audio_lossy_action": "opus",
            "output_container": "webm",
            "scale_height": 720,
            "pix_fmt": "auto",
            "encoder_speed": "slow",
            "subtitle_mode": "strip",
            "force_stereo": True,
            "audio_normalize": True,
            "fps_cap": 30,
            "deinterlace": True,
            "autocrop": True,
            "denoise": True,
            "force_encode_audio": True,
            "extra_args": "-row-mt 1",
        },
    )
    assert create.status_code == 201
    preset = create.json()
    assert preset["name"] == "My Preset"
    assert preset["builtin"] is False

    update = api_client.put(
        f"/api/presets/{preset['id']}",
        json={
            "name": "Renamed Preset",
            "hw_encoder": "nvenc",
            "output_video_codec": "hevc",
            "video_quality_cq": 24,
            "audio_lossy_action": "aac",
            "output_container": "mkv",
            "scale_height": None,
            "pix_fmt": "yuv420p",
            "encoder_speed": "medium",
            "subtitle_mode": "copy",
            "force_stereo": False,
            "audio_normalize": False,
            "fps_cap": None,
            "deinterlace": False,
            "autocrop": False,
            "denoise": False,
            "force_encode_audio": False,
            "extra_args": "",
        },
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Renamed Preset"
    assert update.json()["extra_args"] is None

    listed = api_client.get("/api/presets")
    assert listed.status_code == 200
    assert any(p["id"] == preset["id"] for p in listed.json()["user"])

    delete = api_client.delete(f"/api/presets/{preset['id']}")
    assert delete.status_code == 200
    assert delete.json() == {"ok": True}
    assert len(saved) == 3



def test_set_builtin_accelerator_updates_override_and_rejects_unknown_preset(api_client, monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    monkeypatch.setattr(main, "_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(main, "BUILTIN_PRESET_HW_OVERRIDES", {})
    monkeypatch.setattr(main, "load_config", lambda: {})

    response = api_client.patch(
        "/api/presets/builtin-default/accelerator",
        json={"hw_encoder": "software"},
    )
    assert response.status_code == 200
    assert main.BUILTIN_PRESET_HW_OVERRIDES["builtin-default"] == "software"
    assert json.loads(config_path.read_text())["builtin_preset_hw_overrides"]["builtin-default"] == "software"

    missing = api_client.patch(
        "/api/presets/not-real/accelerator",
        json={"hw_encoder": "software"},
    )
    assert missing.status_code == 404



def test_resolve_drops_returns_existing_and_new_dropped_records(api_client, monkeypatch, test_db_path, tmp_path):
    tracked = tmp_path / "tracked.mkv"
    tracked.write_bytes(b"tracked")
    fresh = tmp_path / "fresh.mkv"
    fresh.write_bytes(b"fresh")

    with main.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", ("/library",))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, needs_optimize) VALUES (1, ?, 'tracked.mkv', 0)",
            (str(tracked),),
        )
        conn.commit()

    monkeypatch.setattr(main, "probe_file", lambda ffprobe_path, vp: {"streams": [], "format": {}})
    monkeypatch.setattr(
        main,
        "parse_probe",
        lambda probe, vp, threshold, flag_av1: {
            "size_bytes": 5,
            "duration_s": 1.5,
            "bitrate_kbps": 123,
            "video_codec": "hevc",
            "video_profile": "Main",
            "pix_fmt": "yuv420p",
            "width": 1280,
            "height": 720,
            "hdr_type": None,
            "color_transfer": None,
            "color_space": None,
            "audio_tracks": "[]",
            "subtitle_tracks": "[]",
            "has_attachments": 0,
            "needs_optimize": 1,
        },
    )

    response = api_client.post(
        "/api/resolve-drops",
        json={"paths": [str(tracked), str(fresh)]},
    )

    assert response.status_code == 200
    files = response.json()["files"]
    assert len(files) == 2
    assert any(f["path"] == str(tracked) for f in files)
    inserted = next(f for f in files if f["path"] == str(fresh))
    assert inserted["folder_path"] == main._DROPPED_FOLDER_PATH
    assert inserted["needs_optimize"] == 1

    with main.db_session() as conn:
        dropped_folder = conn.execute("SELECT id FROM folders WHERE path=?", (main._DROPPED_FOLDER_PATH,)).fetchone()
        fresh_row = conn.execute("SELECT filename FROM files WHERE path=?", (str(fresh),)).fetchone()

    assert dropped_folder is not None
    assert fresh_row["filename"] == "fresh.mkv"
