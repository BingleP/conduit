import json

import encoder


def test_build_audio_args_filters_languages_and_falls_back_to_first_track():
    audio_tracks = [
        {"stream_index": 1, "codec_name": "aac", "profile": "", "channels": 2, "sample_rate": "48000", "language": "eng"},
        {"stream_index": 2, "codec_name": "aac", "profile": "", "channels": 6, "sample_rate": "48000", "language": "jpn"},
    ]

    args, has_jpn = encoder._build_audio_args(audio_tracks, languages=["fra"], lossy_action="copy")

    assert args == ["-map", "0:1", "-c:a:0", "copy"]
    assert has_jpn is False


def test_build_audio_args_reencodes_with_normalization_and_forced_stereo():
    audio_tracks = [
        {"stream_index": 3, "codec_name": "aac", "profile": "LC", "channels": 6, "sample_rate": "48000", "language": "jpn"},
    ]

    args, has_jpn = encoder._build_audio_args(
        audio_tracks,
        languages=["jpn"],
        lossy_action="opus",
        force_stereo=True,
        normalize=True,
    )

    assert args == [
        "-map", "0:3",
        "-c:a:0", "libopus",
        "-b:a:0", "192k",
        "-ac:a:0", "2",
        "-ar:0", "48000",
        "-filter:a:0", "loudnorm",
    ]
    assert has_jpn is True


def test_build_vf_args_for_vaapi_adds_hwupload_and_no_pix_fmt_flag():
    args = encoder._build_vf_args(
        "vaapi",
        scale_height=720,
        pix_fmt="yuv420p10le",
        deinterlace=True,
        denoise=True,
        crop_str="1920:800:0:140",
    )

    assert args == [
        "-vf",
        "crop=1920:800:0:140,yadif,scale=-2:720:flags=lanczos,hqdn3d,format=nv12,hwupload",
    ]


def test_build_video_encode_args_covers_hardware_and_software_fallbacks():
    assert encoder._build_video_encode_args("nvenc", "vp9", 30, "slow") == [
        "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-deadline", "best", "-cpu-used", "1"
    ]
    assert encoder._build_video_encode_args("qsv", "h264", 22, "fast") == [
        "-c:v", "h264_qsv", "-profile:v", "high", "-preset", "fast", "-global_quality", "22", "-look_ahead", "1"
    ]
    assert encoder._build_video_encode_args("software", "av1", 28, "veryslow") == [
        "-c:v", "libsvtav1", "-crf", "28", "-preset", "2"
    ]


def test_build_ffmpeg_cmd_applies_container_audio_and_subtitle_rules(monkeypatch):
    encoder.set_vaapi_device("/dev/dri/renderD129")
    encoder.set_hw_encoder("nvenc")
    encoder.set_encode_options(
        output_video_codec="hevc",
        video_quality_cq=24,
        audio_lossy_action="copy",
        audio_languages=["eng", "jpn"],
        output_container="mkv",
        scale_height=1080,
        pix_fmt="yuv420p10le",
        encoder_speed="medium",
        force_stereo=False,
        audio_normalize=False,
        subtitle_mode="copy",
        deinterlace=False,
        fps_cap=30,
        autocrop=False,
        denoise=False,
        force_encode_audio=False,
    )

    file_row = {
        "audio_tracks": json.dumps([
            {"stream_index": 1, "codec_name": "aac", "profile": "", "channels": 2, "sample_rate": "48000", "language": "eng"},
            {"stream_index": 2, "codec_name": "flac", "profile": "", "channels": 2, "sample_rate": "48000", "language": "jpn"},
        ]),
        "subtitle_tracks": json.dumps([
            {"stream_index": 3, "codec_name": "subrip", "language": "eng"},
            {"stream_index": 4, "codec_name": "dvb_subtitle", "language": "eng"},
            {"stream_index": 5, "codec_name": "ass", "language": "jpn"},
        ]),
    }

    cmd = encoder.build_ffmpeg_cmd(
        file_row,
        job_type="encode",
        input_path="/tmp/input.mkv",
        output_path="/tmp/output.mp4",
        ffmpeg_path="ffmpeg-test",
        output_container_override="mp4",
        audio_lossy_action_override="opus",
        force_stereo_override=True,
        audio_normalize_override=True,
        subtitle_mode_override="copy",
        fps_cap_override=24,
        extra_args='-movflags +faststart -metadata title="Example"',
    )

    assert cmd[:6] == ["ffmpeg-test", "-y", "-progress", "pipe:1", "-nostats", "-i"]
    assert "/tmp/input.mkv" in cmd
    assert ["-c:a:0", "aac"] == cmd[cmd.index("-c:a:0"):cmd.index("-c:a:0") + 2]
    assert ["-c:a:1", "copy"] == cmd[cmd.index("-c:a:1"):cmd.index("-c:a:1") + 2]
    assert "-c:s" not in cmd
    assert "-map" in cmd and "0:t?" not in cmd
    assert ["-r", "24"] == cmd[cmd.index("-r"):cmd.index("-r") + 2]
    assert cmd[-5:] == ["-movflags", "+faststart", "-metadata", "title=Example", "/tmp/output.mp4"]


def test_run_cropdetect_returns_last_detected_crop(monkeypatch):
    class Result:
        stderr = "... crop=1920:800:0:140\n... crop=1918:798:2:141\n"

    captured = {}

    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        return Result()

    monkeypatch.setattr(encoder.subprocess, "run", fake_run)

    crop = encoder._run_cropdetect("/tmp/input.mkv", "ffmpeg-test", 500.0)

    assert crop == "1918:798:2:141"
    assert captured["cmd"][:6] == ["ffmpeg-test", "-ss", "30", "-i", "/tmp/input.mkv", "-vf"]
    assert captured["timeout"] == 60


def test_run_cropdetect_returns_none_on_subprocess_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(encoder.subprocess, "run", fake_run)

    assert encoder._run_cropdetect("/tmp/input.mkv", "ffmpeg-test", 0) is None


def test_refresh_file_record_updates_database_row(monkeypatch, test_db_path, tmp_path):
    video_path = tmp_path / "encoded.mkv"
    video_path.write_bytes(b"encoded")

    with encoder.db_session() as conn:
        conn.execute("INSERT INTO folders (path) VALUES (?)", (str(tmp_path),))
        conn.execute(
            "INSERT INTO files (folder_id, path, filename, needs_optimize) VALUES (1, ?, 'old.mkv', 1)",
            (str(tmp_path / 'old.mkv'),),
        )
        conn.commit()

    encoder.set_probe_refresh_settings("ffprobe-custom", 9876, False)

    monkeypatch.setattr(encoder, "probe_file", lambda ffprobe_path, file_path: {"streams": [], "format": {}})

    def fake_parse_probe(probe, file_path, threshold_kbps, flag_av1):
        assert file_path == str(video_path)
        assert threshold_kbps == 9876
        assert flag_av1 is False
        return {
            "size_bytes": 7,
            "duration_s": 42.5,
            "bitrate_kbps": 1111,
            "video_codec": "hevc",
            "video_profile": "Main 10",
            "pix_fmt": "yuv420p10le",
            "width": 1920,
            "height": 1080,
            "hdr_type": "hdr10",
            "color_transfer": "smpte2084",
            "color_space": "bt2020nc",
            "audio_tracks": "[]",
            "subtitle_tracks": "[]",
            "has_attachments": 0,
            "needs_optimize": 0,
        }

    monkeypatch.setattr(encoder, "parse_probe", fake_parse_probe)

    encoder._refresh_file_record(1, str(video_path))

    with encoder.db_session() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=1").fetchone()

    assert row["path"] == str(video_path)
    assert row["filename"] == "encoded.mkv"
    assert row["size_bytes"] == 7
    assert row["duration_s"] == 42.5
    assert row["bitrate_kbps"] == 1111
    assert row["video_codec"] == "hevc"
    assert row["needs_optimize"] == 0
    assert row["scanned_at"] is not None


def test_refresh_file_record_raises_when_probe_fails(monkeypatch, test_db_path, tmp_path):
    video_path = tmp_path / "broken.mkv"
    video_path.write_bytes(b"broken")
    monkeypatch.setattr(encoder, "probe_file", lambda ffprobe_path, file_path: None)

    try:
        encoder._refresh_file_record(1, str(video_path))
    except RuntimeError as exc:
        assert str(video_path) in str(exc)
    else:
        raise AssertionError("Expected probe failure to raise RuntimeError")


def test_build_ffmpeg_cmd_for_webm_vaapi_remux_paths():
    encoder.set_vaapi_device("/dev/dri/renderD130")
    encoder.set_hw_encoder("vaapi")
    encoder.set_encode_options(
        output_video_codec="vp9",
        video_quality_cq=31,
        audio_lossy_action="aac",
        audio_languages=[],
        output_container="webm",
        scale_height=None,
        pix_fmt="auto",
        encoder_speed="fast",
        force_stereo=False,
        audio_normalize=False,
        subtitle_mode="copy",
        deinterlace=False,
        fps_cap=None,
        autocrop=False,
        denoise=False,
        force_encode_audio=False,
    )

    file_row = {
        "audio_tracks": json.dumps([
            {"stream_index": 1, "codec_name": "aac", "profile": "", "channels": 2, "sample_rate": "48000", "language": "eng"},
            {"stream_index": 2, "codec_name": "aac", "profile": "", "channels": 2, "sample_rate": "48000", "language": "spa"},
        ]),
        "subtitle_tracks": json.dumps([
            {"stream_index": 3, "codec_name": "subrip", "language": "eng"},
        ]),
    }

    cmd = encoder.build_ffmpeg_cmd(
        file_row,
        job_type="encode",
        input_path="/tmp/input.mkv",
        output_path="/tmp/output.webm",
        ffmpeg_path="ffmpeg-test",
    )

    assert cmd[:8] == ["ffmpeg-test", "-y", "-progress", "pipe:1", "-nostats", "-vaapi_device", "/dev/dri/renderD130", "-i"]
    assert "libopus" in cmd
    assert "-c:s" not in cmd
    assert "0:t?" not in cmd

    remux_cmd = encoder.build_ffmpeg_cmd(
        file_row,
        job_type="remux",
        input_path="/tmp/input.mkv",
        output_path="/tmp/output.mkv",
        ffmpeg_path="ffmpeg-test",
        output_container_override="mkv",
    )

    assert ["-c:v", "copy"] == remux_cmd[remux_cmd.index("-c:v"):remux_cmd.index("-c:v") + 2]
    assert "-vaapi_device" not in remux_cmd


def test_parse_progress_line_handles_valid_and_invalid_input():
    assert encoder._parse_progress_line("out_time_ms=123456", 100.0) == {"key": "out_time_ms", "val": "123456"}
    assert encoder._parse_progress_line("progress=end", 100.0) == {"key": "progress", "val": "end"}
    assert encoder._parse_progress_line("not-a-progress-line", 100.0) is None
