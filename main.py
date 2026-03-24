import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import db_session, init_db
from encoder import (
    get_log,
    get_progress,
    get_queue,
    set_encode_options,
    set_hw_encoder,
    set_vaapi_device,
    start_encoder_thread,
    startup_cleanup,
)
from scanner import (
    get_scan_status, start_scan,
    start_watcher, watch_folder, unwatch_folder, set_watcher_scan_settings,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
_settings_lock = threading.Lock()

def load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)

CONFIG = load_config()
FFMPEG_PATH = CONFIG.get("ffmpeg_path", "ffmpeg")
FFPROBE_PATH = CONFIG.get("ffprobe_path", "ffprobe")
PORT = CONFIG.get("port", 8000)
THRESHOLD_KBPS = CONFIG.get("needs_optimize_bitrate_threshold_kbps", 25000)
HW_ENCODER          = CONFIG.get("hw_encoder", "nvenc")
FLAG_AV1            = CONFIG.get("flag_av1", True)
OUTPUT_VIDEO_CODEC  = CONFIG.get("output_video_codec", "hevc")
VIDEO_QUALITY_CQ    = CONFIG.get("video_quality_cq", 24)
AUDIO_LOSSY_ACTION  = CONFIG.get("audio_lossy_action", "opus")
AUDIO_LANGUAGES     = CONFIG.get("audio_languages", ["eng", "jpn"])
OUTPUT_CONTAINER    = CONFIG.get("output_container", "mkv")
SCALE_HEIGHT: Optional[int] = CONFIG.get("scale_height", None)
PIX_FMT: str        = CONFIG.get("pix_fmt", "auto")
ENCODER_SPEED: str  = CONFIG.get("encoder_speed", "medium")
FORCE_STEREO: bool  = CONFIG.get("force_stereo", False)
AUDIO_NORMALIZE: bool = CONFIG.get("audio_normalize", False)
SUBTITLE_MODE: str  = CONFIG.get("subtitle_mode", "copy")
VAAPI_DEVICE        = CONFIG.get("vaapi_device", "/dev/dri/renderD128")
WEB_UI_ENABLED      = CONFIG.get("web_ui_enabled", False)
WEB_UI_HOST         = CONFIG.get("web_ui_host", "0.0.0.0")
WEB_UI_PORT         = CONFIG.get("web_ui_port", 8000)
WEB_UI_USERNAME     = CONFIG.get("web_ui_username", "")
WEB_UI_PASSWORD     = CONFIG.get("web_ui_password", "")
USER_PRESETS: list  = CONFIG.get("user_presets", [])

# Built-in presets (read-only)
BUILTIN_PRESETS = [
    {
        "id": "builtin-tower-unite",
        "name": "Tower Unite",
        "hw_encoder": "software",
        "output_video_codec": "vp9",
        "video_quality_cq": 31,
        "audio_lossy_action": "opus",
        "output_container": "webm",
        "builtin": True,
        "description": "VP9 + Opus in WebM. Required for synced playback in Tower Unite condos without CEFCodecFix.",
    },
]


def _save_config():
    config = load_config()
    config["user_presets"] = USER_PRESETS
    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def verify_credentials(request: Request, credentials: Optional[HTTPBasicCredentials] = Depends(HTTPBasic(auto_error=False))):
    if not request.url.path.startswith("/api/"):
        return True

    with _settings_lock:
        expected_username = WEB_UI_USERNAME
        expected_password = WEB_UI_PASSWORD
    
    if not expected_username or not expected_password:
        return True
    
    if not credentials or credentials.username != expected_username or credentials.password != expected_password:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Conduit", dependencies=[Depends(verify_credentials)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    init_db()
    startup_cleanup()
    set_hw_encoder(HW_ENCODER)
    set_vaapi_device(VAAPI_DEVICE)
    set_encode_options(OUTPUT_VIDEO_CODEC, VIDEO_QUALITY_CQ, AUDIO_LOSSY_ACTION, AUDIO_LANGUAGES, OUTPUT_CONTAINER,
                       SCALE_HEIGHT, PIX_FMT, ENCODER_SPEED, FORCE_STEREO, AUDIO_NORMALIZE, SUBTITLE_MODE)
    start_encoder_thread(FFMPEG_PATH)

    # Start file watcher and scan all existing folders for changes
    start_watcher()
    set_watcher_scan_settings(FFPROBE_PATH, THRESHOLD_KBPS, FLAG_AV1)
    with db_session() as conn:
        folders = conn.execute("SELECT id, path FROM folders").fetchall()
    for folder in folders:
        watch_folder(folder["id"], folder["path"])
        start_scan(folder["id"], folder["path"], FFPROBE_PATH, THRESHOLD_KBPS, FLAG_AV1)



# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AddFolderRequest(BaseModel):
    path: str


class AddJobsRequest(BaseModel):
    file_ids: list[int]
    job_type: str = "encode"                    # 'encode' or 'remux'
    keep_original: bool = False                 # keep original file after encode
    # Per-job encoder overrides (None = use global setting)
    hw_encoder: Optional[str] = None            # nvenc | qsv | amf | vaapi | software
    output_video_codec: Optional[str] = None    # hevc | av1 | h264 | vp9
    video_quality_cq: Optional[int] = None      # 0–51
    audio_lossy_action: Optional[str] = None    # opus | aac | copy
    output_container: Optional[str] = None      # mkv | mp4 | webm
    scale_height: Optional[int] = None          # None | 2160 | 1080 | 720 | 480
    pix_fmt: Optional[str] = None               # auto | yuv420p | yuv420p10le
    encoder_speed: Optional[str] = None         # fast | medium | slow | veryslow
    force_stereo: Optional[bool] = None
    audio_normalize: Optional[bool] = None
    subtitle_mode: Optional[str] = None         # copy | strip
    output_dir: Optional[str] = None            # directory to write output files into


class PresetRequest(BaseModel):
    name: str
    hw_encoder: str = "nvenc"
    output_video_codec: str = "hevc"
    video_quality_cq: int = 24
    audio_lossy_action: str = "opus"
    output_container: str = "mkv"


class UpdateSettingsRequest(BaseModel):
    ffmpeg_path: Optional[str] = None
    ffprobe_path: Optional[str] = None
    needs_optimize_bitrate_threshold_kbps: Optional[int] = None
    hw_encoder: Optional[str] = None          # nvenc | qsv | amf | vaapi | software
    flag_av1: Optional[bool] = None
    output_video_codec: Optional[str] = None  # hevc | av1 | h264 | vp9
    video_quality_cq: Optional[int] = None    # 0–51
    audio_lossy_action: Optional[str] = None  # opus | aac | copy
    audio_languages: Optional[list] = None    # [] = keep all
    output_container: Optional[str] = None    # mkv | mp4 | webm
    scale_height: Optional[int] = None        # None | 2160 | 1080 | 720 | 480
    pix_fmt: Optional[str] = None             # auto | yuv420p | yuv420p10le
    encoder_speed: Optional[str] = None       # fast | medium | slow | veryslow
    force_stereo: Optional[bool] = None
    audio_normalize: Optional[bool] = None
    subtitle_mode: Optional[str] = None       # copy | strip
    vaapi_device: Optional[str] = None
    web_ui_enabled: Optional[bool] = None
    web_ui_host: Optional[str] = None
    web_ui_port: Optional[int] = None
    web_ui_username: Optional[str] = None
    web_ui_password: Optional[str] = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    with _settings_lock:
        return {
            "ffmpeg_path": FFMPEG_PATH,
            "ffprobe_path": FFPROBE_PATH,
            "needs_optimize_bitrate_threshold_kbps": THRESHOLD_KBPS,
            "hw_encoder": HW_ENCODER,
            "flag_av1": FLAG_AV1,
            "output_video_codec": OUTPUT_VIDEO_CODEC,
            "video_quality_cq": VIDEO_QUALITY_CQ,
            "audio_lossy_action": AUDIO_LOSSY_ACTION,
            "audio_languages": AUDIO_LANGUAGES,
            "output_container": OUTPUT_CONTAINER,
            "scale_height": SCALE_HEIGHT,
            "pix_fmt": PIX_FMT,
            "encoder_speed": ENCODER_SPEED,
            "force_stereo": FORCE_STEREO,
            "audio_normalize": AUDIO_NORMALIZE,
            "subtitle_mode": SUBTITLE_MODE,
            "vaapi_device": VAAPI_DEVICE,
            "port": PORT,
            "web_ui_enabled": WEB_UI_ENABLED,
            "web_ui_host": WEB_UI_HOST,
            "web_ui_port": WEB_UI_PORT,
            "web_ui_username": WEB_UI_USERNAME,
            "web_ui_password": WEB_UI_PASSWORD,
        }


@app.post("/api/settings")
def update_settings(req: UpdateSettingsRequest):
    global FFMPEG_PATH, FFPROBE_PATH, THRESHOLD_KBPS, HW_ENCODER, FLAG_AV1
    global OUTPUT_VIDEO_CODEC, VIDEO_QUALITY_CQ, AUDIO_LOSSY_ACTION, AUDIO_LANGUAGES
    global OUTPUT_CONTAINER, SCALE_HEIGHT, PIX_FMT, ENCODER_SPEED
    global FORCE_STEREO, AUDIO_NORMALIZE, SUBTITLE_MODE
    global VAAPI_DEVICE, WEB_UI_ENABLED, WEB_UI_HOST, WEB_UI_PORT
    global WEB_UI_USERNAME, WEB_UI_PASSWORD
    
    config = load_config()
    encode_changed = False

    with _settings_lock:
        if req.ffmpeg_path is not None:
            if not req.ffmpeg_path.strip():
                raise HTTPException(status_code=400, detail="ffmpeg_path must not be empty")
            if os.path.isabs(req.ffmpeg_path) and not os.path.exists(req.ffmpeg_path):
                raise HTTPException(status_code=400, detail=f"ffmpeg_path does not exist: {req.ffmpeg_path}")
            FFMPEG_PATH = req.ffmpeg_path
            config["ffmpeg_path"] = req.ffmpeg_path
        if req.ffprobe_path is not None:
            if not req.ffprobe_path.strip():
                raise HTTPException(status_code=400, detail="ffprobe_path must not be empty")
            if os.path.isabs(req.ffprobe_path) and not os.path.exists(req.ffprobe_path):
                raise HTTPException(status_code=400, detail=f"ffprobe_path does not exist: {req.ffprobe_path}")
            FFPROBE_PATH = req.ffprobe_path
            config["ffprobe_path"] = req.ffprobe_path
        if req.needs_optimize_bitrate_threshold_kbps is not None:
            THRESHOLD_KBPS = req.needs_optimize_bitrate_threshold_kbps
            config["needs_optimize_bitrate_threshold_kbps"] = req.needs_optimize_bitrate_threshold_kbps
        if req.hw_encoder is not None and req.hw_encoder in ("nvenc", "qsv", "amf", "vaapi", "software"):
            HW_ENCODER = req.hw_encoder
            config["hw_encoder"] = req.hw_encoder
            set_hw_encoder(req.hw_encoder)
        if req.flag_av1 is not None and req.flag_av1 != FLAG_AV1:
            FLAG_AV1 = req.flag_av1
            config["flag_av1"] = req.flag_av1
            with db_session() as conn:
                if FLAG_AV1:
                    conn.execute("UPDATE files SET needs_optimize=1 WHERE video_codec='av1'")
                else:
                    conn.execute(
                        "UPDATE files SET needs_optimize=0 WHERE video_codec='av1' AND bitrate_kbps <= ?",
                        (THRESHOLD_KBPS,),
                    )
                conn.commit()

        if req.output_video_codec is not None and req.output_video_codec in ("hevc", "av1", "h264", "vp9"):
            OUTPUT_VIDEO_CODEC = req.output_video_codec
            config["output_video_codec"] = req.output_video_codec
            encode_changed = True
        if req.video_quality_cq is not None and 0 <= req.video_quality_cq <= 51:
            VIDEO_QUALITY_CQ = req.video_quality_cq
            config["video_quality_cq"] = req.video_quality_cq
            encode_changed = True
        if req.audio_lossy_action is not None and req.audio_lossy_action in ("opus", "aac", "copy"):
            AUDIO_LOSSY_ACTION = req.audio_lossy_action
            config["audio_lossy_action"] = req.audio_lossy_action
            encode_changed = True
        if req.audio_languages is not None:
            AUDIO_LANGUAGES = req.audio_languages
            config["audio_languages"] = req.audio_languages
            encode_changed = True
        if req.output_container is not None and req.output_container in ("mkv", "mp4", "webm"):
            OUTPUT_CONTAINER = req.output_container
            config["output_container"] = req.output_container
            encode_changed = True
        if req.scale_height is not None:
            SCALE_HEIGHT = req.scale_height if req.scale_height > 0 else None
            config["scale_height"] = SCALE_HEIGHT
            encode_changed = True
        if req.pix_fmt is not None and req.pix_fmt in ("auto", "yuv420p", "yuv420p10le"):
            PIX_FMT = req.pix_fmt
            config["pix_fmt"] = req.pix_fmt
            encode_changed = True
        if req.encoder_speed is not None and req.encoder_speed in ("fast", "medium", "slow", "veryslow"):
            ENCODER_SPEED = req.encoder_speed
            config["encoder_speed"] = req.encoder_speed
            encode_changed = True
        if req.force_stereo is not None:
            FORCE_STEREO = req.force_stereo
            config["force_stereo"] = req.force_stereo
            encode_changed = True
        if req.audio_normalize is not None:
            AUDIO_NORMALIZE = req.audio_normalize
            config["audio_normalize"] = req.audio_normalize
            encode_changed = True
        if req.subtitle_mode is not None and req.subtitle_mode in ("copy", "strip"):
            SUBTITLE_MODE = req.subtitle_mode
            config["subtitle_mode"] = req.subtitle_mode
            encode_changed = True
        if req.vaapi_device is not None:
            VAAPI_DEVICE = req.vaapi_device
            config["vaapi_device"] = req.vaapi_device
            set_vaapi_device(req.vaapi_device)

        if encode_changed:
            set_encode_options(OUTPUT_VIDEO_CODEC, VIDEO_QUALITY_CQ, AUDIO_LOSSY_ACTION, AUDIO_LANGUAGES, OUTPUT_CONTAINER,
                               SCALE_HEIGHT, PIX_FMT, ENCODER_SPEED, FORCE_STEREO, AUDIO_NORMALIZE, SUBTITLE_MODE)

        if req.web_ui_enabled is not None:
            WEB_UI_ENABLED = req.web_ui_enabled
            config["web_ui_enabled"] = req.web_ui_enabled
        if req.web_ui_host is not None:
            WEB_UI_HOST = req.web_ui_host
            config["web_ui_host"] = req.web_ui_host
        if req.web_ui_port is not None and 1 <= req.web_ui_port <= 65535:
            WEB_UI_PORT = req.web_ui_port
            config["web_ui_port"] = req.web_ui_port
        if req.web_ui_username is not None:
            WEB_UI_USERNAME = req.web_ui_username
            config["web_ui_username"] = req.web_ui_username
        if req.web_ui_password is not None:
            WEB_UI_PASSWORD = req.web_ui_password
            config["web_ui_password"] = req.web_ui_password

    if OUTPUT_VIDEO_CODEC == "vp9" and OUTPUT_CONTAINER == "mp4":
        raise HTTPException(status_code=400, detail="VP9 is not compatible with the MP4 container. Use MKV or WebM.")

    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    set_watcher_scan_settings(FFPROBE_PATH, THRESHOLD_KBPS, FLAG_AV1)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

@app.get("/api/folders")
def list_folders():
    with db_session() as conn:
        rows = conn.execute("""
            SELECT f.id, f.path, f.added_at,
                   COUNT(fi.id) as file_count,
                   COALESCE(SUM(fi.size_bytes), 0) as total_size
            FROM folders f
            LEFT JOIN files fi ON fi.folder_id = f.id
            GROUP BY f.id
            ORDER BY f.added_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/folders", status_code=201)
def add_folder(req: AddFolderRequest):
    path = os.path.realpath(req.path)
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Path does not exist or is not a directory: {path}")

    with db_session() as conn:
        existing = conn.execute("SELECT id FROM folders WHERE path=?", (path,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Folder already added")
        cur = conn.execute("INSERT INTO folders (path) VALUES (?)", (path,))
        folder_id = cur.lastrowid
        conn.commit()

    # Start watching and queue initial scan
    watch_folder(folder_id, path)
    start_scan(folder_id, path, FFPROBE_PATH, THRESHOLD_KBPS, FLAG_AV1)
    return {"id": folder_id, "path": path}


@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: int):
    with db_session() as conn:
        existing = conn.execute("SELECT id FROM folders WHERE id=?", (folder_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Folder not found")
        conn.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        conn.commit()
    unwatch_folder(folder_id)
    return {"ok": True}


@app.post("/api/folders/{folder_id}/scan")
def scan_folder_endpoint(folder_id: int):
    with db_session() as conn:
        folder = conn.execute("SELECT * FROM folders WHERE id=?", (folder_id,)).fetchone()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    start_scan(folder_id, folder["path"], FFPROBE_PATH, THRESHOLD_KBPS, FLAG_AV1)
    return {"ok": True, "message": "Scan started"}


# ---------------------------------------------------------------------------
# Scan status
# ---------------------------------------------------------------------------

@app.get("/api/scan/status")
def scan_status():
    return get_scan_status()


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

VALID_SORT_COLS = {
    "filename", "size_bytes", "duration_s", "bitrate_kbps",
    "width", "height", "video_codec", "hdr_type", "needs_optimize", "scanned_at",
    "audio_codec", "folder_id",
}


@app.get("/api/files")
def list_files(
    folder_id: Optional[int] = None,
    resolution: Optional[str] = None,   # 4k, 1080p, 720p, sd
    codec: Optional[str] = None,
    hdr: Optional[str] = None,           # hdr10, hlg, hdr10plus, dolby_vision, sdr
    audio_lang: Optional[str] = None,
    audio_codec: Optional[str] = None,
    needs_optimize: Optional[int] = None,
    search: Optional[str] = None,
    sort: str = "filename",
    dir: str = "asc",
    limit: int = 100,
    offset: int = 0,
):
    conditions = []
    params = []

    if folder_id is not None:
        conditions.append("f.folder_id = ?")
        params.append(folder_id)

    if resolution:
        if resolution == "4k":
            conditions.append("f.width >= 3840")
        elif resolution == "1080p":
            conditions.append("f.width >= 1920 AND f.width < 3840")
        elif resolution == "720p":
            conditions.append("f.width >= 1280 AND f.width < 1920")
        elif resolution == "sd":
            conditions.append("(f.width < 1280 OR f.width IS NULL)")

    if codec:
        conditions.append("f.video_codec = ?")
        params.append(codec)

    if hdr:
        if hdr == "sdr":
            conditions.append("(f.hdr_type IS NULL OR f.hdr_type = '')")
        else:
            conditions.append("f.hdr_type = ?")
            params.append(hdr)

    if audio_lang:
        conditions.append("f.audio_tracks LIKE ?")
        params.append(f'%"language": "{audio_lang}"%')

    if audio_codec:
        conditions.append("f.audio_tracks LIKE ?")
        params.append(f'%"codec_name": "{audio_codec}"%')

    if needs_optimize is not None:
        conditions.append("f.needs_optimize = ?")
        params.append(needs_optimize)

    if search:
        conditions.append("f.filename LIKE ?")
        params.append(f"%{search}%")

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sort_col = sort if sort in VALID_SORT_COLS else "filename"
    sort_dir = "DESC" if dir.lower() == "desc" else "ASC"

    # Build ORDER BY expression — audio_codec sorts on first track's codec via JSON extract
    if sort_col == "audio_codec":
        order_expr = f"json_extract(f.audio_tracks, '$[0].codec_name') {sort_dir}"
    else:
        order_expr = f"f.{sort_col} {sort_dir}"

    with db_session() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM files f {where_clause}", params
        ).fetchone()
        total = total_row["cnt"]

        rows = conn.execute(
            f"""
            SELECT f.*, fo.path as folder_path
            FROM files f
            JOIN folders fo ON fo.id = f.folder_id
            {where_clause}
            ORDER BY {order_expr}
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "files": [dict(r) for r in rows],
    }


@app.get("/api/files/{file_id}")
def get_file(file_id: int):
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT f.*, fo.path as folder_path
            FROM files f
            JOIN folders fo ON fo.id = f.folder_id
            WHERE f.id = ?
            """,
            (file_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@app.post("/api/jobs", status_code=201)
def create_jobs(req: AddJobsRequest):
    if req.job_type not in ("encode", "remux"):
        raise HTTPException(status_code=400, detail="job_type must be 'encode' or 'remux'")
    if not req.file_ids:
        raise HTTPException(status_code=400, detail="file_ids must not be empty")
    eff_codec     = req.output_video_codec or OUTPUT_VIDEO_CODEC
    eff_container = req.output_container   or OUTPUT_CONTAINER
    if eff_codec == "vp9" and eff_container == "mp4":
        raise HTTPException(status_code=400, detail="VP9 is not compatible with the MP4 container. Use MKV or WebM.")

    created = []
    with db_session() as conn:
        for file_id in req.file_ids:
            file_row = conn.execute("SELECT id FROM files WHERE id=?", (file_id,)).fetchone()
            if not file_row:
                continue
            # Don't duplicate queued jobs
            existing = conn.execute(
                "SELECT id FROM jobs WHERE file_id=? AND status='queued'", (file_id,)
            ).fetchone()
            if existing:
                continue
            cur = conn.execute(
                """INSERT INTO jobs
                   (file_id, job_type, keep_original,
                    hw_encoder, output_video_codec, video_quality_cq,
                    audio_lossy_action, output_container,
                    scale_height, pix_fmt, encoder_speed,
                    force_stereo, audio_normalize, subtitle_mode,
                    output_dir)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (file_id, req.job_type, 1 if req.keep_original else 0,
                 req.hw_encoder, req.output_video_codec,
                 req.video_quality_cq, req.audio_lossy_action, req.output_container,
                 req.scale_height, req.pix_fmt, req.encoder_speed,
                 1 if req.force_stereo else (0 if req.force_stereo is not None else None),
                 1 if req.audio_normalize else (0 if req.audio_normalize is not None else None),
                 req.subtitle_mode, req.output_dir),
            )
            created.append(cur.lastrowid)
        conn.commit()
    return {"created": len(created), "job_ids": created}


@app.get("/api/jobs/log")
def jobs_log():
    return {"lines": get_log()}


@app.get("/api/jobs")
def list_jobs():
    return get_queue()


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: int):
    with db_session() as conn:
        row = conn.execute("SELECT id, status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        if row["status"] != "queued":
            raise HTTPException(status_code=400, detail="Only queued jobs can be cancelled")
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Optimized files / database management
# ---------------------------------------------------------------------------

@app.get("/api/optimized-files")
def list_optimized_files():
    """Files that have had at least one completed encode/remux job."""
    with db_session() as conn:
        rows = conn.execute("""
            SELECT f.id, f.filename, f.path, f.bitrate_kbps, f.video_codec,
                   f.needs_optimize, f.size_bytes,
                   MAX(j.finished_at) AS last_optimized_at,
                   j.job_type AS last_job_type
            FROM files f
            JOIN jobs j ON j.file_id = f.id
            WHERE j.status = 'done'
            GROUP BY f.id
            ORDER BY last_optimized_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/files/{file_id}/reflag")
def reflag_file(file_id: int):
    """Mark a file as needing optimization again."""
    with db_session() as conn:
        row = conn.execute("SELECT id FROM files WHERE id=?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        conn.execute("UPDATE files SET needs_optimize=1 WHERE id=?", (file_id,))
        conn.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@app.get("/api/presets")
def list_presets():
    return {"builtin": BUILTIN_PRESETS, "user": USER_PRESETS}


@app.post("/api/presets", status_code=201)
def create_preset(req: PresetRequest):
    global USER_PRESETS
    preset = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "hw_encoder": req.hw_encoder,
        "output_video_codec": req.output_video_codec,
        "video_quality_cq": req.video_quality_cq,
        "audio_lossy_action": req.audio_lossy_action,
        "output_container": req.output_container,
        "builtin": False,
    }
    USER_PRESETS.append(preset)
    _save_config()
    return preset


@app.put("/api/presets/{preset_id}")
def update_preset(preset_id: str, req: PresetRequest):
    global USER_PRESETS
    for p in USER_PRESETS:
        if p["id"] == preset_id:
            p["name"] = req.name
            p["hw_encoder"] = req.hw_encoder
            p["output_video_codec"] = req.output_video_codec
            p["video_quality_cq"] = req.video_quality_cq
            p["audio_lossy_action"] = req.audio_lossy_action
            p["output_container"] = req.output_container
            _save_config()
            return p
    raise HTTPException(status_code=404, detail="Preset not found")


@app.delete("/api/presets/{preset_id}")
def delete_preset(preset_id: str):
    global USER_PRESETS
    before = len(USER_PRESETS)
    USER_PRESETS = [p for p in USER_PRESETS if p["id"] != preset_id]
    if len(USER_PRESETS) == before:
        raise HTTPException(status_code=404, detail="Preset not found")
    _save_config()
    return {"ok": True}


# ---------------------------------------------------------------------------
# SSE progress stream
# ---------------------------------------------------------------------------

@app.get("/api/jobs/progress")
async def jobs_progress(request: Request):
    async def event_generator():
        last_progress_json = ""
        last_queue_json = ""

        while True:
            if await request.is_disconnected():
                break

            progress = get_progress()
            queue = get_queue()

            progress_json = json.dumps(progress)
            queue_json = json.dumps(queue)

            if progress_json != last_progress_json:
                last_progress_json = progress_json
                yield f"event: progress\ndata: {progress_json}\n\n"

            if queue_json != last_queue_json:
                last_queue_json = queue_json
                yield f"event: queue\ndata: {queue_json}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from desktop import main as _desktop_main
    _desktop_main()
