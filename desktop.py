"""
desktop.py — Desktop entry point for Conduit.

Starts the FastAPI server in a background thread, then opens a pywebview
window. Closing the window shuts down the server cleanly.

Usage:
    python desktop.py            # desktop window (default)
    python desktop.py --no-gui  # headless server only (same as running main.py directly)
"""

import os
import sys
import socket
import threading
import time
import urllib.request
import urllib.error

# Ensure the project directory is on the path so imports work regardless of cwd
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)
os.chdir(_PROJECT_DIR)

# ---------------------------------------------------------------------------
# Logging to file (helps debug app-menu launches where stdout is invisible)
# ---------------------------------------------------------------------------

import logging

_LOG_PATH = os.path.join(_PROJECT_DIR, "desktop.log")
logging.basicConfig(
    filename=_LOG_PATH,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("desktop")

# Also log to stderr so terminal runs still show output
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setLevel(logging.DEBUG)
log.addHandler(_stderr_handler)

# ---------------------------------------------------------------------------
# Qt WebEngine / Wayland compatibility flags (must be set before Qt imports)
# ---------------------------------------------------------------------------

def _configure_qt_env():
    """Set environment flags for Qt WebEngine rendering (Linux/X11/Wayland only)."""
    if sys.platform == 'win32':
        return  # pywebview uses Edge WebView2 on Windows — Qt env vars don't apply
    # Prefer Wayland native if available; fall back to xcb (X11)
    if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "wayland"
    # Disable GPU sandbox — required on some compositors and avoids blank-window crashes
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    extra = []
    if "--no-sandbox" not in flags:
        extra.append("--no-sandbox")
    if "--disable-gpu-sandbox" not in flags:
        extra.append("--disable-gpu-sandbox")
    if extra:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " " + " ".join(extra)).strip()

_configure_qt_env()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_display() -> bool:
    if sys.platform == 'win32':
        return True  # Windows always has a display session
    return bool(
        os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
    )


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=== Conduit starting ===")
    log.info("PROJECT_DIR: %s", _PROJECT_DIR)
    log.info("DISPLAY=%s  WAYLAND_DISPLAY=%s", os.environ.get("DISPLAY"), os.environ.get("WAYLAND_DISPLAY"))
    log.info("QT_QPA_PLATFORM=%s", os.environ.get("QT_QPA_PLATFORM"))
    log.info("QTWEBENGINE_CHROMIUM_FLAGS=%s", os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"))

    no_gui = "--no-gui" in sys.argv or not _has_display()

    from main import app, load_config

    cfg = load_config()
    web_ui_enabled = cfg.get("web_ui_enabled", False)
    web_ui_host    = cfg.get("web_ui_host", "0.0.0.0")
    web_ui_port    = cfg.get("web_ui_port", 8000)
    desktop_port   = cfg.get("port", 8000)

    if no_gui:
        host = web_ui_host if web_ui_enabled else "127.0.0.1"
        port = web_ui_port if web_ui_enabled else desktop_port
        import uvicorn
        log.info("Headless mode on %s:%d", host, port)
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    if web_ui_enabled:
        bind_host = web_ui_host
        bind_port = web_ui_port
    else:
        bind_host = "127.0.0.1"
        bind_port = desktop_port

    # Fall back to a free port if configured one is taken
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", bind_port))
    except OSError:
        free = _find_free_port()
        log.warning("Port %d in use, falling back to %d", bind_port, free)
        bind_port = free
        bind_host = "127.0.0.1"

    # -----------------------------------------------------------------------
    # Start uvicorn in a daemon thread
    # -----------------------------------------------------------------------
    import uvicorn

    log.info("Starting server on %s:%d", bind_host, bind_port)
    uv_config = uvicorn.Config(app, host=bind_host, port=bind_port, log_level="warning")
    server = uvicorn.Server(uv_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    local_url = f"http://127.0.0.1:{bind_port}"
    if not _wait_for_server(local_url + "/api/settings"):
        log.error("Server failed to start in time — aborting.")
        server.should_exit = True
        sys.exit(1)
    log.info("Server ready at %s", local_url)

    # -----------------------------------------------------------------------
    # Open pywebview window
    # -----------------------------------------------------------------------
    try:
        import webview
        log.info("pywebview imported OK")
    except Exception as e:
        log.exception("Failed to import webview: %s", e)
        sys.exit(1)

    try:
        class _Api:
            def pick_folder(self):
                result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
                return result[0] if result else None

            def pick_files(self):
                """Open a multi-file picker; returns list of selected file paths."""
                result = webview.windows[0].create_file_dialog(
                    webview.OPEN_DIALOG, allow_multiple=True
                )
                return list(result) if result else []

            def pick_folder_for_encode(self):
                """Open a folder picker for browse-to-encode; returns the folder path."""
                result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
                return result[0] if result else None

        if sys.platform != 'win32':
            # Linux: pre-configure Qt/PySide6 identity before webview.start() so
            # the Wayland compositor gets the correct app_id when the XDG surface
            # is first mapped.  pywebview reuses an existing QApplication instance.
            _icon_path = os.path.join(_PROJECT_DIR, "frontend", "icons", "conduit-256.png")
            try:
                from PySide6.QtWidgets import QApplication
                from PySide6.QtGui import QIcon
                _qt_app = QApplication.instance() or QApplication(sys.argv)
                _qt_app.setApplicationName("Conduit")
                _qt_app.setDesktopFileName("conduit")
                if os.path.exists(_icon_path):
                    _qt_app.setWindowIcon(QIcon(_icon_path))
                log.info("Qt app identity set before window creation")
            except Exception as exc:
                log.warning("Could not pre-configure Qt app: %s", exc)

        window = webview.create_window(
            "Conduit",
            local_url,
            width=1400,
            height=900,
            resizable=True,
            min_size=(900, 600),
            js_api=_Api(),
        )
        log.info("Window created")

        def on_closed():
            log.info("Window closed — shutting down server")
            server.should_exit = True

        window.events.closed += on_closed

        if sys.platform == 'win32':
            _ico_path = os.path.join(_PROJECT_DIR, "frontend", "icons", "conduit.ico")

            def _on_shown_win32():
                """Set window/taskbar icon via Win32 API after Edge WebView2 appears."""
                if not os.path.exists(_ico_path):
                    return
                try:
                    import ctypes
                    WM_SETICON      = 0x0080
                    ICON_SMALL      = 0
                    ICON_BIG        = 1
                    IMAGE_ICON      = 1
                    LR_LOADFROMFILE = 0x00000010
                    LR_DEFAULTSIZE  = 0x00000040
                    user32 = ctypes.windll.user32
                    hicon_big   = user32.LoadImageW(None, _ico_path, IMAGE_ICON, 0,  0,  LR_LOADFROMFILE | LR_DEFAULTSIZE)
                    hicon_small = user32.LoadImageW(None, _ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                    hwnd = user32.FindWindowW(None, "Conduit")
                    if hwnd:
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG,   hicon_big)
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                        log.info("Windows icon applied via Win32 API")
                except Exception as exc:
                    log.warning("Could not set Windows icon: %s", exc)

            window.events.shown += _on_shown_win32

        log.info("Calling webview.start()")
        webview.start(debug=False)
        log.info("webview.start() returned")
    except Exception as e:
        log.exception("webview error: %s", e)
        server.should_exit = True
        sys.exit(1)

    server_thread.join(timeout=5)
    log.info("=== Conduit exited ===")


if __name__ == "__main__":
    main()
