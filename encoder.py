import json
import os
import re
import shlex
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from database import db_session


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

_settings_lock = threading.Lock()
_vaapi_device: str = "/dev/dri/renderD128"
_hw_encoder: str = "nvenc"          # nvenc | qsv | amf | vaapi | software
_output_video_codec: str = "hevc"   # hevc | av1 | h264 | vp9
_video_quality_cq: int = 24         # 0–51; lower = better quality
_audio_lossy_action: str = "opus"   # opus | aac | copy
_audio_languages: list = ["eng", "jpn"]  # empty list = keep all languages
_output_container: str = "mkv"      # mkv | mp4 | webm
_scale_height: Optional[int] = None # None = keep original; 2160, 1080, 720, 480
_pix_fmt: str = "auto"              # auto | yuv420p | yuv420p10le
_encoder_speed: str = "medium"      # fast | medium | slow | veryslow
_force_stereo: bool = False
_audio_normalize: bool = False
_force_encode_audio: bool = False
_subtitle_mode: str = "copy"        # copy | strip
_deinterlace: bool = False
_fps_cap: Optional[int] = None      # None = no cap; e.g. 60, 30, 24
_autocrop: bool = False
_denoise: bool = False

# Speed preset maps per encoder
_SPEED_NVENC    = {"fast": "p2",      "medium": "p4",       "slow": "p6",      "veryslow": "p7"}
_SPEED_QSV      = {"fast": "fast",    "medium": "medium",   "slow": "slow",    "veryslow": "slower"}
_SPEED_AMF      = {"fast": "speed",   "medium": "balanced", "slow": "quality", "veryslow": "quality"}
_SPEED_SW       = {"fast": "fast",    "medium": "medium",   "slow": "slow",    "veryslow": "veryslow"}
_SPEED_SVT      = {"fast": "8",       "medium": "6",        "slow": "4",       "veryslow": "2"}
_SPEED_VP9_CPU  = {"fast": "4",       "medium": "2",        "slow": "1",       "veryslow": "0"}
_SPEED_VP9_DL   = {"fast": "good",    "medium": "good",     "slow": "best",    "veryslow": "best"}


def set_vaapi_device(path: str):
    global _vaapi_device
    with _settings_lock:
        _vaapi_device = path


def set_hw_encoder(hw: str):
    global _hw_encoder
    with _settings_lock:
        if hw in ("nvenc", "qsv", "amf", "vaapi", "software"):
            _hw_encoder = hw


def set_encode_options(
    output_video_codec: str = None,
    video_quality_cq: int = None,
    audio_lossy_action: str = None,
    audio_languages: list = None,
    output_container: str = None,
    scale_height: int = None,
    pix_fmt: str = None,
    encoder_speed: str = None,
    force_stereo: bool = None,
    audio_normalize: bool = None,
    subtitle_mode: str = None,
    deinterlace: bool = None,
    fps_cap: int = None,
    autocrop: bool = None,
    denoise: bool = None,
    force_encode_audio: bool = None,
):
    global _output_video_codec, _video_quality_cq, _audio_lossy_action, _audio_languages
    global _output_container, _scale_height, _pix_fmt, _encoder_speed
    global _force_stereo, _audio_normalize, _subtitle_mode
    global _deinterlace, _fps_cap, _autocrop, _denoise, _force_encode_audio
    with _settings_lock:
        if output_video_codec in ("hevc", "av1", "h264", "vp9"):
            _output_video_codec = output_video_codec
        if video_quality_cq is not None and 0 <= video_quality_cq <= 51:
            _video_quality_cq = video_quality_cq
        if audio_lossy_action in ("opus", "aac", "copy"):
            _audio_lossy_action = audio_lossy_action
        if audio_languages is not None:
            _audio_languages = audio_languages
        if output_container in ("mkv", "mp4", "webm"):
            _output_container = output_container
        if scale_height is not None:
            _scale_height = scale_height if scale_height > 0 else None
        if pix_fmt in ("auto", "yuv420p", "yuv420p10le"):
            _pix_fmt = pix_fmt
        if encoder_speed in ("fast", "medium", "slow", "veryslow"):
            _encoder_speed = encoder_speed
        if force_stereo is not None:
            _force_stereo = bool(force_stereo)
        if audio_normalize is not None:
            _audio_normalize = bool(audio_normalize)
        if subtitle_mode in ("copy", "strip"):
            _subtitle_mode = subtitle_mode
        if deinterlace is not None:
            _deinterlace = bool(deinterlace)
        if fps_cap is not None:
            _fps_cap = int(fps_cap) if fps_cap > 0 else None
        if autocrop is not None:
            _autocrop = bool(autocrop)
        if denoise is not None:
            _denoise = bool(denoise)
        if force_encode_audio is not None:
            _force_encode_audio = bool(force_encode_audio)

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
    with db_session() as conn:
        rows = conn.execute("""
            SELECT j.id, j.file_id, j.status, j.job_type,
                   j.added_at, j.started_at, j.finished_at, j.error_msg,
                   j.extra_args,
                   f.filename, f.duration_s
            FROM jobs j
            JOIN files f ON f.id = j.file_id
            WHERE j.status IN ('queued','running','error','done')
            ORDER BY j.id ASC
        """).fetchall()
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


def _build_audio_args(audio_tracks: list, languages: list = None, lossy_action: str = "opus",
                      force_stereo: bool = False, normalize: bool = False,
                      force_encode_audio: bool = False):
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

        copying = lossy_action == "copy" or (_is_lossless(codec, profile) and not force_encode_audio)

        if copying:
            args += [f"-c:a:{idx}", "copy"]
        elif lossy_action == "aac":
            out_channels = 2 if (force_stereo and channels > 2) else channels
            br = _aac_bitrate(out_channels)
            args += [f"-c:a:{idx}", "aac", f"-b:a:{idx}", br, f"-ac:a:{idx}", str(out_channels)]
            if sample_rate:
                args += [f"-ar:{idx}", str(sample_rate)]
        else:  # opus (default)
            out_channels = 2 if (force_stereo and channels > 2) else channels
            br = _opus_bitrate(out_channels)
            args += [f"-c:a:{idx}", "libopus", f"-b:a:{idx}", br, f"-ac:a:{idx}", str(out_channels)]
            if sample_rate:
                args += [f"-ar:{idx}", str(sample_rate)]

        # Audio normalization only for re-encoded tracks (can't filter stream-copy)
        if normalize and not copying:
            args += [f"-filter:a:{idx}", "loudnorm"]

    return args, has_jpn


# ---------------------------------------------------------------------------
# ffmpeg command builder
# ---------------------------------------------------------------------------

def _build_vf_args(hw: str, scale_height: int = None, pix_fmt: str = None,
                   deinterlace: bool = False, denoise: bool = False,
                   crop_str: str = None) -> list:
    """Build -vf filter chain and -pix_fmt args for the video stream.

    Filter order: crop → yadif (deinterlace) → scale → hqdn3d (denoise)
    → format/hwupload (VA-API only).  All are software filters that run
    before hwupload, so VA-API stays compatible.
    """
    filters = []
    if crop_str:
        filters.append(f"crop={crop_str}")
    if deinterlace:
        filters.append("yadif")
    if scale_height:
        filters.append(f"scale=-2:{scale_height}:flags=lanczos")
    if denoise:
        filters.append("hqdn3d")
    if hw == "vaapi":
        if filters:
            filters += ["format=nv12", "hwupload"]
        else:
            filters += ["format=nv12|vaapi", "hwupload"]
    result = (["-vf", ",".join(filters)] if filters else [])
    # Pixel format only meaningful for non-VAAPI software-side encoders
    if pix_fmt and pix_fmt != "auto" and hw != "vaapi":
        result += ["-pix_fmt", pix_fmt]
    return result


def _run_cropdetect(input_path: str, ffmpeg_path: str, duration_s: float) -> Optional[str]:
    """Run cropdetect on the input file and return a crop string like '1920:800:0:140'.

    Seeks into the file (skipping intros/credits) and samples 200 frames.
    Returns None on any failure so callers can safely skip cropping.
    """
    seek = min(duration_s * 0.1, 30.0) if duration_s > 0 else 10.0
    cmd = [
        ffmpeg_path,
        "-ss", str(int(seek)),
        "-i", input_path,
        "-vf", "cropdetect=limit=24:round=2:skip=2",
        "-frames:v", "200",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        matches = re.findall(r"crop=(\d+:\d+:\d+:\d+)", result.stderr)
        if matches:
            return matches[-1]
    except Exception:
        pass
    return None


def _build_video_encode_args(hw: str, codec: str, cq: int, speed: str = "medium") -> list:
    """Build ffmpeg video codec arguments (no -vf; call _build_vf_args separately)."""
    cq_s = str(cq)

    def _sw_vp9():
        cpu = _SPEED_VP9_CPU.get(speed, "2")
        dl  = _SPEED_VP9_DL.get(speed, "good")
        return ["-c:v", "libvpx-vp9", "-crf", cq_s, "-b:v", "0", "-deadline", dl, "-cpu-used", cpu]

    if hw == "nvenc":
        if codec == "vp9":
            return _sw_vp9()  # NVENC has no VP9 encoder; fall back to software
        enc     = {"hevc": "hevc_nvenc", "av1": "av1_nvenc", "h264": "h264_nvenc"}.get(codec, "hevc_nvenc")
        profile = (["-profile:v", "main10"] if codec == "hevc"
                   else ["-profile:v", "high"] if codec == "h264" else [])
        preset  = _SPEED_NVENC.get(speed, "p4")
        return ["-c:v", enc] + profile + ["-preset", preset, "-rc", "vbr", "-cq", cq_s, "-b:v", "0"]
    if hw == "qsv":
        enc     = {"hevc": "hevc_qsv", "av1": "av1_qsv", "h264": "h264_qsv", "vp9": "vp9_qsv"}.get(codec, "hevc_qsv")
        profile = (["-profile:v", "main10"] if codec == "hevc"
                   else ["-profile:v", "high"] if codec == "h264" else [])
        # look_ahead is only supported for H.264 and HEVC on QSV
        look    = ["-look_ahead", "1"] if codec in ("hevc", "h264") else []
        preset  = _SPEED_QSV.get(speed, "medium")
        return ["-c:v", enc] + profile + ["-preset", preset, "-global_quality", cq_s] + look
    if hw == "amf":
        if codec == "vp9":
            return _sw_vp9()  # AMF has no VP9 encoder; fall back to software
        enc     = {"hevc": "hevc_amf", "av1": "av1_amf", "h264": "h264_amf"}.get(codec, "hevc_amf")
        profile = (["-profile:v", "main"] if codec == "hevc"
                   else ["-profile:v", "high"] if codec == "h264" else [])
        quality = _SPEED_AMF.get(speed, "balanced")
        return ["-c:v", enc] + profile + ["-quality", quality, "-rc", "cqp", "-qp_i", cq_s, "-qp_p", cq_s]
    if hw == "vaapi":
        enc = {"hevc": "hevc_vaapi", "av1": "av1_vaapi", "h264": "h264_vaapi", "vp9": "vp9_vaapi"}.get(codec, "hevc_vaapi")
        return ["-c:v", enc, "-rc_mode", "CQP", "-qp", cq_s]  # vf handled by _build_vf_args
    if hw == "software":
        if codec == "vp9":
            return _sw_vp9()
        sw = _SPEED_SW.get(speed, "medium")
        if codec == "av1":
            return ["-c:v", "libsvtav1", "-crf", cq_s, "-preset", _SPEED_SVT.get(speed, "6")]
        elif codec == "h264":
            return ["-c:v", "libx264", "-crf", cq_s, "-preset", sw]
        else:
            return ["-c:v", "libx265", "-crf", cq_s, "-preset", sw]
    # fallback: nvenc hevc
    return ["-c:v", "hevc_nvenc", "-profile:v", "main10", "-preset", "p4", "-rc", "vbr", "-cq", cq_s, "-b:v", "0"]


def build_ffmpeg_cmd(file_row, job_type: str, input_path: str, output_path: str,
                     ffmpeg_path: str = "ffmpeg",
                     hw_encoder_override: str = None,
                     output_video_codec_override: str = None,
                     video_quality_cq_override: int = None,
                     audio_lossy_action_override: str = None,
                     output_container_override: str = None,
                     scale_height_override: int = None,
                     pix_fmt_override: str = None,
                     encoder_speed_override: str = None,
                     force_stereo_override=None,
                     audio_normalize_override=None,
                     subtitle_mode_override: str = None,
                     deinterlace_override=None,
                     fps_cap_override=None,
                     crop_str: str = None,
                     denoise_override=None,
                     force_encode_audio_override=None,
                     extra_args: str = None) -> list:
    # Resolve effective settings: per-job override > global
    with _settings_lock:
        eff_hw                = hw_encoder_override                                     or _hw_encoder
        eff_codec             = output_video_codec_override                             or _output_video_codec
        eff_cq                = video_quality_cq_override if video_quality_cq_override is not None else _video_quality_cq
        eff_audio             = audio_lossy_action_override                             or _audio_lossy_action
        eff_container         = output_container_override                               or _output_container
        eff_scale             = scale_height_override if scale_height_override is not None else _scale_height
        eff_pix_fmt           = pix_fmt_override                                        or _pix_fmt
        eff_speed             = encoder_speed_override                                  or _encoder_speed
        eff_stereo            = force_stereo_override  if force_stereo_override  is not None else _force_stereo
        eff_normalize         = audio_normalize_override if audio_normalize_override is not None else _audio_normalize
        eff_sub_mode          = subtitle_mode_override                                  or _subtitle_mode
        eff_vaapi_dev         = _vaapi_device
        eff_deinterlace       = deinterlace_override if deinterlace_override is not None else _deinterlace
        eff_fps_cap           = fps_cap_override if fps_cap_override is not None else _fps_cap
        eff_denoise           = denoise_override if denoise_override is not None else _denoise
        eff_force_enc_audio   = force_encode_audio_override if force_encode_audio_override is not None else _force_encode_audio

    # Container-specific audio overrides
    if eff_container == "webm" and eff_audio != "opus":
        eff_audio = "opus"   # WebM requires Opus
    if eff_container == "mp4" and eff_audio == "opus":
        eff_audio = "aac"    # MP4 doesn't reliably support libopus

    # No subtitles/attachments for WebM or MP4 (incompatible formats)
    subs_supported = (eff_container == "mkv")

    cmd = [ffmpeg_path, "-y", "-progress", "pipe:1", "-nostats"]
    # VA-API device must be declared before -i
    if eff_hw == "vaapi" and job_type != "remux":
        cmd += ["-vaapi_device", eff_vaapi_dev]
    cmd += ["-i", input_path]

    # --- Video ---
    cmd += ["-map", "0:v:0"]
    if job_type == "remux":
        cmd += ["-c:v", "copy"]
    else:
        cmd += _build_vf_args(
            eff_hw,
            eff_scale if eff_scale else None,
            eff_pix_fmt,
            deinterlace=eff_deinterlace,
            denoise=eff_denoise,
            crop_str=crop_str,
        )
        cmd += _build_video_encode_args(eff_hw, eff_codec, eff_cq, eff_speed)

    # --- Audio ---
    audio_tracks = json.loads(file_row["audio_tracks"] or "[]")
    with _settings_lock:
        langs = _audio_languages
    audio_args, has_jpn = _build_audio_args(
        audio_tracks, langs, eff_audio,
        force_stereo=eff_stereo, normalize=eff_normalize,
        force_encode_audio=eff_force_enc_audio,
    )
    cmd += audio_args

    # --- Subtitles (MKV only, respecting subtitle_mode) ---
    if subs_supported and eff_sub_mode == "copy":
        subtitle_tracks = json.loads(file_row["subtitle_tracks"] or "[]")
        valid_subs = [s for s in subtitle_tracks if s.get("codec_name", "") not in DROP_SUBTITLE_CODECS]
        mapped_sub_indices = set()
        with _settings_lock:
            keep_all_langs = len(_audio_languages) == 0
            cur_langs = _audio_languages

        if keep_all_langs:
            for s in valid_subs:
                if s["stream_index"] not in mapped_sub_indices:
                    cmd += ["-map", f"0:{s['stream_index']}"]
                    mapped_sub_indices.add(s["stream_index"])
        else:
            for lang in cur_langs:
                for s in [x for x in valid_subs if x.get("language") == lang]:
                    if s["stream_index"] not in mapped_sub_indices:
                        cmd += ["-map", f"0:{s['stream_index']}"]
                        mapped_sub_indices.add(s["stream_index"])

        if mapped_sub_indices:
            cmd += ["-c:s", "copy"]

        # --- Attachments (fonts etc, MKV only) ---
        cmd += ["-map", "0:t?"]

    # --- Chapters ---
    cmd += ["-map_chapters", "0"]

    # --- Frame rate cap (encode only) ---
    if job_type != "remux" and eff_fps_cap:
        cmd += ["-r", str(int(eff_fps_cap))]

    # --- Extra user-supplied args (inserted before the output path) ---
    if extra_args and extra_args.strip():
        try:
            cmd += shlex.split(extra_args)
        except ValueError:
            cmd += extra_args.split()

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
    keep_original = bool(file_row["keep_original"])
    job_type = file_row["job_type"]
    duration_s = file_row["duration_s"] or 0
    output_dir = file_row["output_dir"]

    # Resolve effective container for output extension
    with _settings_lock:
        cur_container = _output_container
    eff_container = file_row["output_container"] or cur_container
    ext = {"webm": ".webm", "mp4": ".mp4"}.get(eff_container, ".mkv")

    if output_dir:
        # User chose a specific output directory — write directly there, original is untouched
        os.makedirs(output_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_dir, stem + ext)
    elif keep_original:
        output_path = base + ".optimized" + ext
    else:
        output_path = base + ".new" + ext

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

    with db_session() as conn:
        conn.execute(
            "UPDATE jobs SET status='running', started_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        conn.commit()

    # Auto-crop pre-pass: run cropdetect before building the main command
    crop_str = None
    if job_type != "remux":
        with _settings_lock:
            global_autocrop = _autocrop
        row_autocrop = file_row["autocrop"]
        eff_autocrop = bool(row_autocrop) if row_autocrop is not None else global_autocrop
        if eff_autocrop:
            crop_str = _run_cropdetect(input_path, ffmpeg_path, duration_s)

    cmd = build_ffmpeg_cmd(
        file_row, job_type, input_path, output_path, ffmpeg_path,
        hw_encoder_override=file_row["hw_encoder"],
        output_video_codec_override=file_row["output_video_codec"],
        video_quality_cq_override=file_row["video_quality_cq"],
        audio_lossy_action_override=file_row["audio_lossy_action"],
        output_container_override=file_row["output_container"],
        scale_height_override=file_row["scale_height"],
        pix_fmt_override=file_row["pix_fmt"],
        encoder_speed_override=file_row["encoder_speed"],
        force_stereo_override=bool(file_row["force_stereo"]) if file_row["force_stereo"] is not None else None,
        audio_normalize_override=bool(file_row["audio_normalize"]) if file_row["audio_normalize"] is not None else None,
        subtitle_mode_override=file_row["subtitle_mode"],
        deinterlace_override=bool(file_row["deinterlace"]) if file_row["deinterlace"] is not None else None,
        fps_cap_override=file_row["fps_cap"],
        crop_str=crop_str,
        denoise_override=bool(file_row["denoise"]) if file_row["denoise"] is not None else None,
        force_encode_audio_override=bool(file_row["force_encode_audio"]) if file_row["force_encode_audio"] is not None else None,
        extra_args=file_row["extra_args"],
    )

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
            tail = error_lines[-5:] if error_lines else []
            error_msg = f"ffmpeg exited {proc.returncode}" + (": " + " | ".join(tail) if tail else "")
            if file_row.get("extra_args"):
                error_msg = f"[Custom args were active — they may have caused this failure]\n{error_msg}"

    except Exception as e:
        error_msg = str(e)
        if proc:
            try:
                proc.kill()
            except Exception:
                pass

    now = datetime.now(timezone.utc).isoformat()

    if success:
        try:
            if output_dir:
                # Output was written to a separate directory — original is untouched
                new_mtime = os.path.getmtime(input_path)
                with db_session() as conn:
                    conn.execute(
                        "UPDATE files SET mtime=?, needs_optimize=0 WHERE id=?",
                        (new_mtime, file_row["file_id"]),
                    )
                    conn.commit()
            elif keep_original:
                # Leave the original untouched; mark it optimized so it leaves the flagged list
                new_mtime = os.path.getmtime(input_path)
                with db_session() as conn:
                    conn.execute(
                        "UPDATE files SET mtime=?, needs_optimize=0 WHERE id=?",
                        (new_mtime, file_row["file_id"]),
                    )
                    conn.commit()
            else:
                # Replace original: delete it, rename temp to final path
                # If container changed extension (e.g. mkv→webm), use new extension
                final_path = base + ext
                bak_path = input_path + ".bak"
                
                os.rename(input_path, bak_path)
                try:
                    os.rename(output_path, final_path)
                    if os.path.exists(bak_path):
                        os.remove(bak_path)
                except Exception as e:
                    if os.path.exists(bak_path):
                        os.rename(bak_path, input_path)
                    raise e

                new_mtime = os.path.getmtime(final_path)
                new_filename = os.path.basename(final_path)
                with db_session() as conn:
                    conn.execute(
                        "UPDATE files SET path=?, filename=?, mtime=?, needs_optimize=0 WHERE id=?",
                        (final_path, new_filename, new_mtime, file_row["file_id"]),
                    )
                    conn.commit()
        except Exception as e:
            error_msg = f"Post-encode file handling failed: {e}"
            success = False

    if success:
        with db_session() as conn:
            conn.execute(
                "UPDATE jobs SET status='done', finished_at=? WHERE id=?",
                (now, job_id),
            )
            conn.commit()
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
        with db_session() as conn:
            conn.execute(
                "UPDATE jobs SET status='error', finished_at=?, error_msg=? WHERE id=?",
                (now, error_msg, job_id),
            )
            conn.commit()
        with _progress_lock:
            _progress.status = "error"
            _progress.error_msg = error_msg or "Unknown error"

    _queue_changed.set()


def _encoder_worker(ffmpeg_path: str):
    """Main encoder loop — processes one job at a time."""
    while True:
        with db_session() as conn:
            row = conn.execute("""
                SELECT j.id as job_id, j.file_id, j.job_type, j.keep_original,
                       j.hw_encoder, j.output_video_codec, j.video_quality_cq,
                       j.audio_lossy_action, j.output_container,
                       j.scale_height, j.pix_fmt, j.encoder_speed,
                       j.force_stereo, j.audio_normalize, j.subtitle_mode,
                       j.output_dir,
                       j.deinterlace, j.fps_cap, j.autocrop, j.denoise, j.force_encode_audio, j.extra_args,
                       f.path, f.filename, f.duration_s,
                       f.audio_tracks, f.subtitle_tracks
                FROM jobs j
                JOIN files f ON f.id = j.file_id
                WHERE j.status = 'queued'
                ORDER BY j.id ASC
                LIMIT 1
            """).fetchone()

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
    restore original files from .bak if rename failed,
    delete orphaned .new.* and .bak files.
    """
    with db_session() as conn:
        # Reset running jobs
        conn.execute(
            "UPDATE jobs SET status='error', error_msg='Server restarted during encode' "
            "WHERE status='running'"
        )
        conn.commit()

        # Find all file paths
        rows = conn.execute("SELECT path FROM files").fetchall()
    
    for row in rows:
        path = row["path"]
        bak_path = path + ".bak"
        
        # Restore from .bak if original is missing
        if os.path.exists(bak_path) and not os.path.exists(path):
            try:
                os.rename(bak_path, path)
            except Exception:
                pass
        
        # Delete orphaned .new.* and .bak files
        base, _ = os.path.splitext(path)
        for suffix in (".new.mkv", ".new.webm", ".new.mp4", ".bak"):
            orphan = base + suffix if suffix != ".bak" else path + suffix
            if os.path.exists(orphan):
                try:
                    os.remove(orphan)
                except Exception:
                    pass


def start_encoder_thread(ffmpeg_path: str):
    t = threading.Thread(target=_encoder_worker, args=(ffmpeg_path,), daemon=True)
    t.start()
