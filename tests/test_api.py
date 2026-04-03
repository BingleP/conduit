def test_get_settings_returns_current_configuration(api_client):
    response = api_client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["ffmpeg_path"]
    assert body["ffprobe_path"]
    assert body["output_video_codec"]
    assert "platform" in body


def test_add_folder_endpoint_persists_folder_and_queues_scan(api_client, monkeypatch, tmp_path):
    queued = []
    watched = []
    folder = tmp_path / "library"
    folder.mkdir()

    monkeypatch.setattr("main.start_scan", lambda *args, **kwargs: queued.append((args, kwargs)))
    monkeypatch.setattr("main.watch_folder", lambda folder_id, path: watched.append((folder_id, path)))

    response = api_client.post("/api/folders", json={"path": str(folder)})

    assert response.status_code == 201
    body = response.json()
    assert body["path"] == str(folder)
    assert watched == [(body["id"], str(folder))]
    assert queued and queued[0][0][:2] == (body["id"], str(folder))


def test_database_reset_endpoint_rejects_while_scanning(api_client, monkeypatch):
    monkeypatch.setattr("main.get_scan_status", lambda: {"scanning": True})

    response = api_client.delete("/api/database/reset")

    assert response.status_code == 409
    assert "folder scan is currently running" in response.json()["detail"].lower()
