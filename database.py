import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mediamanager.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
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
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            status      TEXT    NOT NULL DEFAULT 'queued',
            job_type    TEXT    NOT NULL DEFAULT 'encode',
            added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            started_at  TEXT,
            finished_at TEXT,
            error_msg   TEXT
        )
    """)

    conn.commit()
    conn.close()
