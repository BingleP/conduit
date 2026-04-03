import json

from scanner import _find_video_files, parse_probe


def test_parse_probe_extracts_stream_metadata_and_flags_high_bitrate(tmp_path):
    video_path = tmp_path / "movie.mkv"
    video_path.write_bytes(b"0" * 32)

    probe = {
        "format": {
            "size": "32",
            "duration": "120.5",
            "bit_rate": "30000000",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "profile": "High 10",
                "pix_fmt": "yuv420p10le",
                "width": 1920,
                "height": 1080,
                "color_transfer": "smpte2084",
                "color_space": "bt2020nc",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "sample_rate": "48000",
                "tags": {"language": "eng"},
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"LANGUAGE": "JPN"},
            },
            {
                "index": 3,
                "codec_type": "attachment",
                "codec_name": "ttf",
            },
        ],
        "frames": [],
    }

    result = parse_probe(probe, str(video_path), threshold_kbps=25_000, flag_av1=True)

    assert result["size_bytes"] == 32
    assert result["duration_s"] == 120.5
    assert result["bitrate_kbps"] == 30_000
    assert result["video_codec"] == "h264"
    assert result["video_profile"] == "High 10"
    assert result["pix_fmt"] == "yuv420p10le"
    assert result["width"] == 1920
    assert result["height"] == 1080
    assert result["color_transfer"] == "smpte2084"
    assert result["color_space"] == "bt2020nc"
    assert json.loads(result["audio_tracks"]) == [
        {
            "stream_index": 1,
            "codec_name": "aac",
            "profile": "",
            "channels": 2,
            "sample_rate": "48000",
            "language": "eng",
        }
    ]
    assert json.loads(result["subtitle_tracks"]) == [
        {
            "stream_index": 2,
            "codec_name": "subrip",
            "language": "jpn",
        }
    ]
    assert result["has_attachments"] == 1
    assert result["needs_optimize"] == 1


def test_find_video_files_skips_hidden_directories_and_non_video_files(tmp_path):
    visible_dir = tmp_path / "Movies"
    hidden_dir = tmp_path / ".cache"
    visible_dir.mkdir()
    hidden_dir.mkdir()

    keep = visible_dir / "clip.mp4"
    keep.write_text("video")
    (visible_dir / "notes.txt").write_text("not video")
    (hidden_dir / "secret.mkv").write_text("hidden")

    found = _find_video_files(str(tmp_path))

    assert found == [str(keep)]
