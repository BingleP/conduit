import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mediamanager.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_session():
    """Context manager for database connections to ensure they are always closed."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    """Returns a new connection. User is responsible for closing."""
    return _connect()


def init_db():
    with db_session() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                path     TEXT    NOT NULL UNIQUE,
                added_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id        INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                path             TEXT    NOT NULL UNIQUE,
                filename         TEXT    NOT NULL,
                size_bytes       INTEGER,
                duration_s       REAL,
                bitrate_kbps     INTEGER,
                video_codec      TEXT,
                video_profile    TEXT,
                pix_fmt          TEXT,
                width            INTEGER,
                height           INTEGER,
                hdr_type         TEXT,
                color_transfer   TEXT,
                color_space      TEXT,
                audio_tracks     TEXT,
                subtitle_tracks  TEXT,
                has_attachments  INTEGER NOT NULL DEFAULT 0,
                needs_optimize   INTEGER NOT NULL DEFAULT 0,
                scanned_at       TEXT,
                mtime            REAL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id             INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                status              TEXT    NOT NULL DEFAULT 'queued',
                job_type            TEXT    NOT NULL DEFAULT 'encode',
                keep_original       INTEGER NOT NULL DEFAULT 0,
                hw_encoder          TEXT,
                output_video_codec  TEXT,
                video_quality_cq    INTEGER,
                audio_lossy_action  TEXT,
                added_at            TEXT    NOT NULL DEFAULT (datetime('now')),
                started_at          TEXT,
                finished_at         TEXT,
                error_msg           TEXT
            )
        """)

        # Migrations for existing databases
        existing_cols = [r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()]
        for col, defn in [
            ("keep_original",      "INTEGER NOT NULL DEFAULT 0"),
            ("hw_encoder",         "TEXT"),
            ("output_video_codec", "TEXT"),
            ("video_quality_cq",   "INTEGER"),
            ("audio_lossy_action", "TEXT"),
            ("output_container",   "TEXT"),
            ("scale_height",       "INTEGER"),
            ("pix_fmt",            "TEXT"),
            ("encoder_speed",      "TEXT"),
            ("force_stereo",       "INTEGER"),
            ("audio_normalize",    "INTEGER"),
            ("subtitle_mode",      "TEXT"),
            ("output_dir",         "TEXT"),
            ("deinterlace",        "INTEGER NOT NULL DEFAULT 0"),
            ("fps_cap",            "INTEGER"),
            ("autocrop",           "INTEGER NOT NULL DEFAULT 0"),
            ("denoise",            "INTEGER NOT NULL DEFAULT 0"),
            ("force_encode_audio", "INTEGER NOT NULL DEFAULT 0"),
            ("extra_args",         "TEXT"),
        ]:
            if col not in existing_cols:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {col} {defn}")

        conn.commit()
