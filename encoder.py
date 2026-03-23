import json
import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from database import get_db


# ---------------------------------------------------------------------------
# Progress state
# ---------------------------------------------------------------------------

@dataclass
class EncodeProgress:
    job_id: int = 0
    file_id: int = 0
    filename: str = ""
    job_type: str = "encode"
    frame: int = 0
    fps: float = 0.0
    speed: str = "0x"
    out_time_ms: int = 0
    duration_s: float = 0.0
    percent: float = 0.0
    status: str = "idle"   # idle | running | done | error
    error_msg: str = ""
    started_at: Optional[float] = None

    def eta_s(self) -> Optional[float]:
        if self.percent > 0 and self.fps > 0 and self.started_at:
            elapsed = time.time() - self.started_at
            total_est = elapsed / (self.percent / 100.0)
            return max(0.0, total_est - elapsed)
        return None

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "file_id": self.file_id,
            "filename": self.filename,
            "job_type": self.job_type,
            "frame": self.frame,
            "fps": round(self.fps, 1),
            "speed": self.speed,
            "out_time_ms": self.out_time_ms,
            "percent": round(self.percent, 2),
            "status": self.status,
            "error_msg": self.error_msg,
            "eta_s": round(self.eta_s(), 0) if self.eta_s() is not None else None,
        }


_progress = EncodeProgress()
_progress_lock = threading.Lock()
_queue_changed = threading.Event()

_hw_encoder: str = "nvenc"          # nvenc | qsv | amf
_output_video_codec: str = "hevc"   # hevc | av1 | h264
_video_quality_cq: int = 24         # 0–51; lower = better quality
_audio_lossy_action: str = "opus"   # opus | aac | copy
_audio_languages: list = ["eng", "jpn"]  # empty list = keep all languages


def set_hw_encoder(hw: str):
    global _hw_encoder
    if hw in ("nvenc", "qsv", "amf"):
        _hw_encoder = hw


def set_encode_options(
    output_video_codec: str = None,
    video_quality_cq: int = None,
    audio_lossy_action: str = None,
    audio_languages: list = None,
):
    global _output_video_codec, _video_quality_cq, _audio_lossy_action, _audio_languages
    if output_video_codec in ("hevc", "av1", "h264"):
        _output_video_codec = output_video_codec
    if video_quality_cq is not None and 0 <= video_quality_cq <= 51:
        _video_quality_cq = video_quality_cq
    if audio_lossy_action in ("opus", "aac", "copy"):
        _audio_lossy_action = audio_lossy_action
    if audio_languages is not None:
        _audio_languages = audio_languages

_log_lines: deque = deque(maxlen=2000)
_log_lock = threading.Lock()


def get_log() -> list:
    with _log_lock:
        return list(_log_lines)


def _clear_log():
    with _log_lock:
        _log_lines.clear()


def get_progress() -> dict:
    with _progress_lock:
        return _progress.to_dict()


def get_queue() -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT j.id, j.file_id, j.status, j.job_type,
               j.added_at, j.started_at, j.finished_at, j.error_msg,
               f.filename, f.duration_s
        FROM jobs j
        JOIN files f ON f.id = j.file_id
        WHERE j.status IN ('queued','running','error','done')
        ORDER BY j.id ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

LOSSLESS_CODECS = {
    "flac", "mlp", "truehd",
    "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_s16be", "pcm_s24be", "pcm_s32be",
    "pcm_bluray", "pcm_dvd",
}

LOSSY_CODECS = {"eac3", "ac3", "aac", "dts", "opus", "mp3", "vorbis", "wmav1", "wmav2"}

DROP_SUBTITLE_CODECS = {"dvb_subtitle", "dvb_teletext"}


def _is_lossless(codec_name: str, profile: str) -> bool:
    if codec_name in LOSSLESS_CODECS:
        return True
    # DTS-HD MA: codec_name == 'dts' with profile containing 'MA'
    if codec_name == "dts" and profile and "MA" in profile.upper():
        return True
    # dts-hd / dtshd aliases
    if "dts-hd" in codec_name or "dtshd" in codec_name:
        return True
    return False


def _opus_bitrate(channels: int) -> str:
    if channels >= 6: return "320k"
    if channels >= 2: return "192k"
    return "96k"


def _aac_bitrate(channels: int) -> str:
    if channels >= 6: return "256k"
    if channels >= 2: return "160k"
    return "96k"


def _build_audio_args(audio_tracks: list, languages: list = None, lossy_action: str = "opus"):
    """
    Select tracks based on configured languages, then encode according to lossy_action.
    Returns (args_list, has_jpn_in_selection).
    """
    if languages is None:
        languages = ["eng", "jpn"]

    keep_all = len(languages) == 0

    if keep_all:
        selected = audio_tracks
    else:
        # Keep tracks matching any configured language, preserving order they appear
        selected = [t for t in audio_tracks if t.get("language") in languages]
        if not selected and audio_tracks:
            selected = [audio_tracks[0]]  # fallback: keep first track

    jpn_codes = {"jpn", "ja", "japanese"}
    has_jpn = any(t.get("language") in jpn_codes for t in selected)

    args = []
    for idx, track in enumerate(selected):
        stream_index = track.get("stream_index", -1)
        codec = track.get("codec_name", "")
        profile = track.get("profile", "")
        channels = track.get("channels", 2)
        sample_rate = track.get("sample_rate", "")

        args += ["-map", f"0:{stream_index}"]

        if lossy_action == "copy" or _is_lossless(codec, profile):
            args += [f"-c:a:{idx}", "copy"]
        elif lossy_action == "aac":
            br = _aac_bitrate(channels)
            args += [f"-c:a:{idx}", "aac", f"-b:a:{idx}", br]
            if sample_rate:
                args += [f"-ar:{idx}", str(sample_rate)]
        else:  # opus (default)
            br = _opus_bitrate(channels)
            args += [f"-c:a:{idx}", "libopus", f"-b:a:{idx}", br]
            if sample_rate:
                args += [f"-ar:{idx}", str(sample_rate)]

    return args, has_jpn


# ---------------------------------------------------------------------------
# ffmpeg command builder
# ---------------------------------------------------------------------------

def _build_video_encode_args(hw: str, codec: str, cq: int) -> list:
    """Build ffmpeg video encoding arguments for the given hardware/codec/quality."""
    cq_s = str(cq)
    if hw == "nvenc":
        enc = {"hevc": "hevc_nvenc", "av1": "av1_nvenc", "h264": "h264_nvenc"}.get(codec, "hevc_nvenc")
        profile = (["-profile:v", "main10"] if codec == "hevc"
                   else ["-profile:v", "high"] if codec == "h264" else [])
        return ["-c:v", enc] + profile + ["-preset", "p4", "-rc", "vbr", "-cq", cq_s, "-b:v", "0"]
    if hw == "qsv":
        enc = {"hevc": "hevc_qsv", "av1": "av1_qsv", "h264": "h264_qsv"}.get(codec, "hevc_qsv")
        profile = (["-profile:v", "main10"] if codec == "hevc"
                   else ["-profile:v", "high"] if codec == "h264" else [])
        look = ["-look_ahead", "1"] if codec != "av1" else []
        return ["-c:v", enc] + profile + ["-preset", "medium", "-global_quality", cq_s] + look
    if hw == "amf":
        enc = {"hevc": "hevc_amf", "av1": "av1_amf", "h264": "h264_amf"}.get(codec, "hevc_amf")
        profile = (["-profile:v", "main"] if codec == "hevc"
                   else ["-profile:v", "high"] if codec == "h264" else [])
        return ["-c:v", enc] + profile + ["-quality", "balanced", "-rc", "cqp", "-qp_i", cq_s, "-qp_p", cq_s]
    # fallback: nvenc hevc
    return ["-c:v", "hevc_nvenc", "-profile:v", "main10", "-preset", "p4", "-rc", "vbr", "-cq", cq_s, "-b:v", "0"]


def build_ffmpeg_cmd(file_row, job_type: str, input_path: str, output_path: str,
                     ffmpeg_path: str = "ffmpeg") -> list:
    cmd = [ffmpeg_path, "-y", "-progress", "pipe:1", "-nostats", "-i", input_path]

    # --- Video ---
    cmd += ["-map", "0:v:0"]
    if job_type == "remux":
        cmd += ["-c:v", "copy"]
    else:
        cmd += _build_video_encode_args(_hw_encoder, _output_video_codec, _video_quality_cq)

    # --- Audio ---
    audio_tracks = json.loads(file_row["audio_tracks"] or "[]")
    audio_args, has_jpn = _build_audio_args(audio_tracks, _audio_languages, _audio_lossy_action)
    cmd += audio_args

    # --- Subtitles ---
    subtitle_tracks = json.loads(file_row["subtitle_tracks"] or "[]")
    valid_subs = [
        s for s in subtitle_tracks
        if s.get("codec_name", "") not in DROP_SUBTITLE_CODECS
    ]

    mapped_sub_indices = set()
    keep_all_langs = len(_audio_languages) == 0

    if keep_all_langs:
        for s in valid_subs:
            if s["stream_index"] not in mapped_sub_indices:
                cmd += ["-map", f"0:{s['stream_index']}"]
                mapped_sub_indices.add(s["stream_index"])
    else:
        for lang in _audio_languages:
            for s in [x for x in valid_subs if x.get("language") == lang]:
                if s["stream_index"] not in mapped_sub_indices:
                    cmd += ["-map", f"0:{s['stream_index']}"]
                    mapped_sub_indices.add(s["stream_index"])

    if mapped_sub_indices:
        cmd += ["-c:s", "copy"]

    # --- Attachments (fonts etc) ---
    cmd += ["-map", "0:t?"]

    # --- Chapters ---
    cmd += ["-map_chapters", "0"]

    cmd += [output_path]
    return cmd


# ---------------------------------------------------------------------------
# Encoder thread
# ---------------------------------------------------------------------------

def _parse_progress_line(line: str, duration_s: float) -> Optional[dict]:
    """Parse a single key=value progress line from ffmpeg -progress pipe:1."""
    line = line.strip()
    if "=" not in line:
        return None
    key, _, val = line.partition("=")
    key = key.strip()
    val = val.strip()
    result = {"key": key, "val": val}
    return result


def _run_encode(job_id: int, file_row, ffmpeg_path: str):
    global _progress

    input_path = file_row["path"]
    base, _ = os.path.splitext(input_path)
    output_path = base + ".new.mkv"
    duration_s = file_row["duration_s"] or 0
    job_type = file_row["job_type"]

    with _progress_lock:
        _progress = EncodeProgress(
            job_id=job_id,
            file_id=file_row["file_id"],
            filename=file_row["filename"],
            job_type=job_type,
            duration_s=duration_s,
            status="running",
            started_at=time.time(),
        )

    conn = get_db()
    conn.execute(
        "UPDATE jobs SET status='running', started_at=datetime('now') WHERE id=?",
        (job_id,),
    )
    conn.commit()

    cmd = build_ffmpeg_cmd(file_row, job_type, input_path, output_path, ffmpeg_path)

    _clear_log()

    proc = None
    error_msg = None
    success = False
    stderr_thread = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def _read_stderr():
            try:
                for line in proc.stderr:
                    with _log_lock:
                        _log_lines.append(line.rstrip('\n\r'))
            except Exception:
                pass

        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stderr_thread.start()

        # Collect progress key=value pairs; ffmpeg -progress pipe:1 ends each block with
        # "progress=continue" or "progress=end" (NOT empty lines)
        kv_block = {}
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            if "=" in line:
                k, _, v = line.partition("=")
                kv_block[k.strip()] = v.strip()

            if line.startswith("progress="):
                # End of a progress block — update state
                with _progress_lock:
                    if "frame" in kv_block:
                        try:
                            _progress.frame = int(kv_block["frame"])
                        except ValueError:
                            pass
                    if "fps" in kv_block:
                        try:
                            _progress.fps = float(kv_block["fps"])
                        except ValueError:
                            pass
                    if "speed" in kv_block:
                        _progress.speed = kv_block["speed"]
                    if "out_time_ms" in kv_block:
                        try:
                            otms = int(kv_block["out_time_ms"])
                            _progress.out_time_ms = otms
                            if duration_s > 0:
                                _progress.percent = min(100.0, otms / (duration_s * 1e6) * 100)
                        except ValueError:
                            pass
                    if kv_block.get("progress") == "end":
                        _progress.percent = 100.0
                kv_block = {}

        proc.wait()
        if stderr_thread:
            stderr_thread.join(timeout=3)

        if proc.returncode == 0:
            success = True
        else:
            with _log_lock:
                error_lines = [l for l in list(_log_lines) if l.strip()]
            tail = error_lines[-3:] if error_lines else []
            error_msg = f"ffmpeg exited {proc.returncode}" + (": " + " | ".join(tail) if tail else "")

    except Exception as e:
        error_msg = str(e)
        if proc:
            try:
                proc.kill()
            except Exception:
                pass

    now = datetime.utcnow().isoformat()

    if success:
        # In-place replacement: delete original, rename .new.mkv
        try:
            os.remove(input_path)
            os.rename(output_path, input_path)
            # Update file record mtime
            new_mtime = os.path.getmtime(input_path)
            conn.execute(
                "UPDATE files SET mtime=?, needs_optimize=0 WHERE id=?",
                (new_mtime, file_row["file_id"]),
            )
        except Exception as e:
            error_msg = f"Post-encode rename failed: {e}"
            success = False

    if success:
        conn.execute(
            "UPDATE jobs SET status='done', finished_at=? WHERE id=?",
            (now, job_id),
        )
        with _progress_lock:
            _progress.status = "done"
            _progress.percent = 100.0
    else:
        # Clean up partial output
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        conn.execute(
            "UPDATE jobs SET status='error', finished_at=?, error_msg=? WHERE id=?",
            (now, error_msg, job_id),
        )
        with _progress_lock:
            _progress.status = "error"
            _progress.error_msg = error_msg or "Unknown error"

    conn.commit()
    conn.close()
    _queue_changed.set()


def _encoder_worker(ffmpeg_path: str):
    """Main encoder loop — processes one job at a time."""
    while True:
        conn = get_db()
        row = conn.execute("""
            SELECT j.id as job_id, j.file_id, j.job_type,
                   f.path, f.filename, f.duration_s,
                   f.audio_tracks, f.subtitle_tracks
            FROM jobs j
            JOIN files f ON f.id = j.file_id
            WHERE j.status = 'queued'
            ORDER BY j.id ASC
            LIMIT 1
        """).fetchone()
        conn.close()

        if row is None:
            time.sleep(1)
            continue

        _run_encode(row["job_id"], row, ffmpeg_path)


# ---------------------------------------------------------------------------
# Startup cleanup
# ---------------------------------------------------------------------------

def startup_cleanup():
    """
    On startup: reset any 'running' jobs to 'error' (crash recovery),
    delete orphaned .new.mkv temp files.
    """
    conn = get_db()

    # Reset running jobs
    conn.execute(
        "UPDATE jobs SET status='error', error_msg='Server restarted during encode' "
        "WHERE status='running'"
    )
    conn.commit()

    # Find all file paths, look for orphaned .new.mkv
    rows = conn.execute("SELECT path FROM files").fetchall()
    for row in rows:
        base, _ = os.path.splitext(row["path"])
        orphan = base + ".new.mkv"
        if os.path.exists(orphan):
            try:
                os.remove(orphan)
            except Exception:
                pass

    conn.close()


def start_encoder_thread(ffmpeg_path: str):
    t = threading.Thread(target=_encoder_worker, args=(ffmpeg_path,), daemon=True)
    t.start()
