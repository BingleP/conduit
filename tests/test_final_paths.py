import asyncio
import os

import encoder
import scanner
import main


def test_start_watcher_watch_folder_and_unwatch_folder(monkeypatch, tmp_path):
    class FakeObserver:
        def __init__(self):
            self.started = False
            self.scheduled = []
            self.unscheduled = []
        def start(self):
            self.started = True
        def schedule(self, handler, folder_path, recursive=True):
            token = (handler.folder_id, folder_path, recursive)
            self.scheduled.append(token)
            return token
        def unschedule(self, watch):
            self.unscheduled.append(watch)

    monkeypatch.setattr(scanner, "_WATCHDOG_AVAILABLE", True)
    monkeypatch.setattr(scanner, "_Observer", FakeObserver)

    folder = tmp_path / "library"
    folder.mkdir()

    with scanner._watcher_lock:
        scanner._watcher_observer = None
        scanner._watcher_handlers.clear()

    scanner.start_watcher()
    assert isinstance(scanner._watcher_observer, FakeObserver)
    assert scanner._watcher_observer.started is True

    scanner.watch_folder(5, str(folder))
    scanner.watch_folder(5, str(folder))
    assert len(scanner._watcher_observer.scheduled) == 1

    scanner.unwatch_folder(5)
    assert len(scanner._watcher_observer.unscheduled) == 1



def test_watch_folder_ignores_missing_dirs_and_schedule_failures(monkeypatch, tmp_path):
    class BrokenObserver:
        def schedule(self, handler, folder_path, recursive=True):
            raise RuntimeError("nope")

    monkeypatch.setattr(scanner, "_WATCHDOG_AVAILABLE", True)
    with scanner._watcher_lock:
        scanner._watcher_observer = BrokenObserver()
        scanner._watcher_handlers.clear()

    scanner.watch_folder(1, str(tmp_path / "missing"))
    assert scanner._watcher_handlers == {}

    folder = tmp_path / "real"
    folder.mkdir()
    scanner.watch_folder(2, str(folder))
    assert scanner._watcher_handlers == {}



def test_encoder_worker_processes_queued_job(monkeypatch):
    class FakeConn:
        def execute(self, query, params=()):
            class Result:
                def fetchone(self_inner):
                    return {
                        "job_id": 9,
                        "file_id": 2,
                        "job_type": "encode",
                        "keep_original": 0,
                        "hw_encoder": None,
                        "output_video_codec": None,
                        "video_quality_cq": None,
                        "audio_lossy_action": None,
                        "output_container": None,
                        "scale_height": None,
                        "pix_fmt": None,
                        "encoder_speed": None,
                        "force_stereo": None,
                        "audio_normalize": None,
                        "subtitle_mode": None,
                        "output_dir": None,
                        "deinterlace": None,
                        "fps_cap": None,
                        "autocrop": None,
                        "denoise": None,
                        "force_encode_audio": None,
                        "extra_args": None,
                        "path": "/tmp/input.mkv",
                        "filename": "input.mkv",
                        "duration_s": 1.0,
                        "audio_tracks": "[]",
                        "subtitle_tracks": "[]",
                    }
            return Result()
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    calls = []
    monkeypatch.setattr(encoder, "db_session", lambda: FakeConn())

    def fake_run_encode(job_id, row, ffmpeg_path):
        calls.append((job_id, row["filename"], ffmpeg_path))
        raise SystemExit("stop")

    monkeypatch.setattr(encoder, "_run_encode", fake_run_encode)

    try:
        encoder._encoder_worker("ffmpeg-test")
    except SystemExit:
        pass

    assert calls == [(9, "input.mkv", "ffmpeg-test")]



def test_encoder_worker_sleeps_when_no_jobs(monkeypatch):
    class FakeConn:
        def execute(self, query, params=()):
            class Result:
                def fetchone(self_inner):
                    return None
            return Result()
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    sleeps = []
    monkeypatch.setattr(encoder, "db_session", lambda: FakeConn())

    def fake_sleep(seconds):
        sleeps.append(seconds)
        raise SystemExit("stop")

    monkeypatch.setattr(encoder.time, "sleep", fake_sleep)

    try:
        encoder._encoder_worker("ffmpeg-test")
    except SystemExit:
        pass

    assert sleeps == [1]



def test_startup_cleanup_resets_running_jobs_and_restores_files(monkeypatch, test_db_path, tmp_path):
    tracked = tmp_path / "movie.mkv"
    bak = tmp_path / "movie.mkv.bak"
    bak.write_bytes(b"backup")
    new_file = tmp_path / "movie.new.mkv"
    new_file.write_bytes(b"partial")

    with encoder.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", (str(tmp_path),))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename) VALUES (1, ?, 'movie.mkv')",
            (str(tracked),),
        )
        conn.execute("INSERT INTO jobs (file_id, status) VALUES (1, 'running')")
        conn.commit()

    encoder.startup_cleanup()

    with encoder.db_session() as conn:
        job = conn.execute("SELECT status, error_msg FROM jobs WHERE id=1").fetchone()

    assert job["status"] == "error"
    assert "Server restarted during encode" in job["error_msg"]
    assert tracked.exists()
    assert not bak.exists()
    assert not new_file.exists()



def test_jobs_progress_stream_emits_progress_queue_and_done_events(monkeypatch):
    progress_states = iter([
        {"status": "running", "percent": 10},
        {"status": "done", "percent": 100},
    ])
    queue_states = iter([
        [{"id": 1, "file_id": 5, "status": "running", "filename": "movie.mkv"}],
        [{"id": 1, "file_id": 5, "status": "done", "filename": "movie.mkv"}],
    ])

    monkeypatch.setattr(main, "get_progress", lambda: next(progress_states))
    monkeypatch.setattr(main, "get_queue", lambda: next(queue_states))

    class FakeRequest:
        def __init__(self):
            self.calls = 0
        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 2

    async def collect_events():
        response = await main.jobs_progress(FakeRequest())
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunk if isinstance(chunk, bytes) else chunk.encode() for chunk in chunks).decode()

    text = asyncio.run(collect_events())

    assert "event: progress" in text
    assert "event: queue" in text
    assert "event: done" in text
    assert '"job_id": 1' in text
