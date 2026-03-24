import json
import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from database import db_session


# ---------------------------------------------------------------------------
# Scan state (shared across threads)
# ---------------------------------------------------------------------------

@dataclass
class ScanStatus:
    scanning: bool = False
    folder_id: int = 0
    current_file: str = ""
    scanned: int = 0
    total: int = 0
    errors: int = 0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self):
        elapsed = None
        if self.started_at:
            end = self.finished_at or time.time()
            elapsed = round(end - self.started_at, 1)
        return {
            "scanning": self.scanning,
            "current_file": self.current_file,
            "scanned": self.scanned,
            "total": self.total,
            "errors": self.errors,
            "elapsed_s": elapsed,
        }


# Each entry: (folder_id, folder_path, ffprobe_path, threshold_kbps, flag_av1)
_scan_queue: deque = deque()
_scan_status = ScanStatus()
_scan_lock = threading.Lock()


def get_scan_status() -> dict:
    with _scan_lock:
        d = _scan_status.to_dict()
        d["queued"] = len(_scan_queue)
    return d


# ---------------------------------------------------------------------------
# HDR detection helpers
# ---------------------------------------------------------------------------

def _detect_hdr(video_stream: dict, frames: list) -> Optional[str]:
    color_transfer = video_stream.get("color_transfer", "")

    # Check side data from first frame for HDR10+ / Dolby Vision
    for frame in frames:
        side_data_list = frame.get("side_data_list", [])
        for sd in side_data_list:
            sd_type = sd.get("side_data_type", "")
            if "DOVI" in sd_type or "dovi" in sd_type or "Dolby Vision" in sd_type:
                return "dolby_vision"
            if "SMPTE2094-40" in sd_type or "HDR Dynamic Metadata" in sd_type:
                return "hdr10plus"

    # Check codec tag for Dolby Vision
    codec_tag = video_stream.get("codec_tag_string", "")
    if codec_tag in ("dvh1", "dvhe"):
        return "dolby_vision"

    if color_transfer == "smpte2084":
        return "hdr10"
    if color_transfer == "arib-std-b67":
        return "hlg"

    return None


# ---------------------------------------------------------------------------
# needs_optimize logic
# ---------------------------------------------------------------------------

def _needs_optimize(video_codec: str, pix_fmt: str, bitrate_kbps: int, threshold: int,
                    flag_av1: bool = True) -> bool:
    # H264 Hi10P — no hardware decoder anywhere
    if video_codec == "h264" and pix_fmt and "10" in pix_fmt:
        return True
    # AV1 — only flag if the option is enabled
    if flag_av1 and video_codec == "av1":
        return True
    # Very high bitrate
    if bitrate_kbps and bitrate_kbps > threshold:
        return True
    return False


# ---------------------------------------------------------------------------
# ffprobe parsing
# ---------------------------------------------------------------------------

def probe_file(ffprobe_path: str, file_path: str) -> Optional[dict]:
    """Run ffprobe on a file and return parsed JSON, or None on error."""
    cmd = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        "-show_frames",
        "-read_intervals", "%+#1",
        file_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


def parse_probe(probe: dict, file_path: str, threshold_kbps: int, flag_av1: bool = True) -> dict:
    """Extract all relevant info from a ffprobe JSON result."""
    streams = probe.get("streams", [])
    fmt = probe.get("format", {})
    frames = probe.get("frames", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    attachment_streams = [s for s in streams if s.get("codec_type") == "attachment"]

    # --- File-level ---
    size_bytes = int(fmt.get("size", 0)) or os.path.getsize(file_path)
    duration_s = float(fmt.get("duration", 0) or 0)
    bitrate_bps = int(fmt.get("bit_rate", 0) or 0)
    bitrate_kbps = bitrate_bps // 1000 if bitrate_bps else 0

    # --- Video ---
    video_codec = None
    video_profile = None
    pix_fmt = None
    width = None
    height = None
    color_transfer = None
    color_space = None
    hdr_type = None

    if video_stream:
        video_codec = video_stream.get("codec_name")
        video_profile = video_stream.get("profile")
        pix_fmt = video_stream.get("pix_fmt")
        width = video_stream.get("width")
        height = video_stream.get("height")
        color_transfer = video_stream.get("color_transfer")
        color_space = video_stream.get("color_space")
        hdr_type = _detect_hdr(video_stream, frames)

    # --- Audio ---
    audio_tracks = []
    for s in audio_streams:
        tags = s.get("tags", {})
        lang = (tags.get("language") or tags.get("LANGUAGE") or "").lower().strip()
        codec = s.get("codec_name", "")
        profile = s.get("profile", "")
        channels = s.get("channels", 0)
        sample_rate = s.get("sample_rate", "")
        stream_index = s.get("index", -1)
        audio_tracks.append({
            "stream_index": stream_index,
            "codec_name": codec,
            "profile": profile,
            "channels": int(channels) if channels else 0,
            "sample_rate": sample_rate,
            "language": lang,
        })

    # --- Subtitles ---
    subtitle_tracks = []
    for s in subtitle_streams:
        tags = s.get("tags", {})
        lang = (tags.get("language") or tags.get("LANGUAGE") or "").lower().strip()
        codec = s.get("codec_name", "")
        stream_index = s.get("index", -1)
        subtitle_tracks.append({
            "stream_index": stream_index,
            "codec_name": codec,
            "language": lang,
        })

    has_attachments = 1 if attachment_streams else 0

    needs_opt = _needs_optimize(video_codec or "", pix_fmt or "", bitrate_kbps, threshold_kbps, flag_av1)

    return {
        "size_bytes": size_bytes,
        "duration_s": duration_s,
        "bitrate_kbps": bitrate_kbps,
        "video_codec": video_codec,
        "video_profile": video_profile,
        "pix_fmt": pix_fmt,
        "width": width,
        "height": height,
        "hdr_type": hdr_type,
        "color_transfer": color_transfer,
        "color_space": color_space,
        "audio_tracks": json.dumps(audio_tracks),
        "subtitle_tracks": json.dumps(subtitle_tracks),
        "has_attachments": has_attachments,
        "needs_optimize": 1 if needs_opt else 0,
    }


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".wmv", ".flv", ".webm", ".m4v"}


def _find_video_files(folder_path: str) -> list:
    result = []
    for root, dirs, files in os.walk(folder_path):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS:
                result.append(os.path.join(root, f))
    return result


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------

def scan_folder(folder_id: int, folder_path: str, ffprobe_path: str, threshold_kbps: int,
                flag_av1: bool = True):
    """Scan a folder; called from a daemon thread. _scan_status.scanning is already True on entry."""
    try:
        files = _find_video_files(folder_path)

        with _scan_lock:
            _scan_status.total = len(files)

        with db_session() as conn:
            for i, file_path in enumerate(files):
                with _scan_lock:
                    _scan_status.current_file = os.path.basename(file_path)
                    _scan_status.scanned = i

                try:
                    mtime = os.path.getmtime(file_path)
                    filename = os.path.basename(file_path)

                    # Check if already in DB with same mtime
                    existing = conn.execute(
                        "SELECT id, mtime FROM files WHERE path = ?", (file_path,)
                    ).fetchone()

                    if existing and existing["mtime"] == mtime:
                        # Up to date, skip ffprobe
                        continue

                    probe = probe_file(ffprobe_path, file_path)
                    if probe is None:
                        with _scan_lock:
                            _scan_status.errors += 1
                        continue

                    info = parse_probe(probe, file_path, threshold_kbps, flag_av1)
                    now = datetime.now(timezone.utc).isoformat()

                    if existing:
                        conn.execute("""
                            UPDATE files SET
                                filename=?, size_bytes=?, duration_s=?, bitrate_kbps=?,
                                video_codec=?, video_profile=?, pix_fmt=?, width=?, height=?,
                                hdr_type=?, color_transfer=?, color_space=?,
                                audio_tracks=?, subtitle_tracks=?, has_attachments=?,
                                needs_optimize=?, scanned_at=?, mtime=?
                            WHERE path=?
                        """, (
                            filename, info["size_bytes"], info["duration_s"], info["bitrate_kbps"],
                            info["video_codec"], info["video_profile"], info["pix_fmt"],
                            info["width"], info["height"],
                            info["hdr_type"], info["color_transfer"], info["color_space"],
                            info["audio_tracks"], info["subtitle_tracks"], info["has_attachments"],
                            info["needs_optimize"], now, mtime,
                            file_path,
                        ))
                    else:
                        conn.execute("""
                            INSERT INTO files (
                                folder_id, path, filename, size_bytes, duration_s, bitrate_kbps,
                                video_codec, video_profile, pix_fmt, width, height,
                                hdr_type, color_transfer, color_space,
                                audio_tracks, subtitle_tracks, has_attachments,
                                needs_optimize, scanned_at, mtime
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            folder_id, file_path, filename,
                            info["size_bytes"], info["duration_s"], info["bitrate_kbps"],
                            info["video_codec"], info["video_profile"], info["pix_fmt"],
                            info["width"], info["height"],
                            info["hdr_type"], info["color_transfer"], info["color_space"],
                            info["audio_tracks"], info["subtitle_tracks"], info["has_attachments"],
                            info["needs_optimize"], now, mtime,
                        ))

                    conn.commit()

                except Exception:
                    with _scan_lock:
                        _scan_status.errors += 1

            # Remove DB entries for files that no longer exist on disk
            existing_paths = set(files)
            db_files = conn.execute(
                "SELECT id, path FROM files WHERE folder_id = ?", (folder_id,)
            ).fetchall()
            for row in db_files:
                if row["path"] not in existing_paths:
                    conn.execute("DELETE FROM files WHERE id = ?", (row["id"],))
            conn.commit()

    finally:
        with _scan_lock:
            _scan_status.scanning = False
            _scan_status.scanned = _scan_status.total
            _scan_status.current_file = ""
            _scan_status.finished_at = time.time()
        # Start the next queued scan, if any
        _start_next_scan()


def _start_next_scan():
    """Pop and start the next queued scan, if any. Must NOT be called while holding _scan_lock."""
    global _scan_status
    with _scan_lock:
        if not _scan_queue or _scan_status.scanning:
            return
        folder_id, folder_path, ffprobe_path, threshold_kbps, flag_av1 = _scan_queue.popleft()
        _scan_status = ScanStatus(
            scanning=True,
            folder_id=folder_id,
            started_at=time.time(),
        )
    t = threading.Thread(
        target=scan_folder,
        args=(folder_id, folder_path, ffprobe_path, threshold_kbps, flag_av1),
        daemon=True,
    )
    t.start()


def start_scan(folder_id: int, folder_path: str, ffprobe_path: str, threshold_kbps: int,
               flag_av1: bool = True):
    """Queue a folder scan. Starts immediately if idle, otherwise enqueues (deduplicates)."""
    global _scan_status
    with _scan_lock:
        # Deduplicate: skip if this folder is already the active scan
        if _scan_status.scanning and _scan_status.folder_id == folder_id:
            return
        # Deduplicate: skip if already waiting in the queue
        if any(item[0] == folder_id for item in _scan_queue):
            return

        if _scan_status.scanning:
            # Another scan is running — enqueue for later
            _scan_queue.append((folder_id, folder_path, ffprobe_path, threshold_kbps, flag_av1))
            return

        # Idle — start immediately
        _scan_status = ScanStatus(
            scanning=True,
            folder_id=folder_id,
            started_at=time.time(),
        )

    t = threading.Thread(
        target=scan_folder,
        args=(folder_id, folder_path, ffprobe_path, threshold_kbps, flag_av1),
        daemon=True,
    )
    t.start()
