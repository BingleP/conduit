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


def test_parse_progress_line_handles_valid_and_invalid_input():
    assert encoder._parse_progress_line("out_time_ms=123456", 100.0) == {"key": "out_time_ms", "val": "123456"}
    assert encoder._parse_progress_line("progress=end", 100.0) == {"key": "progress", "val": "end"}
    assert encoder._parse_progress_line("not-a-progress-line", 100.0) is None
