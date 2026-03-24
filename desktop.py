"""
desktop.py — Desktop entry point for Conduit.

Starts the FastAPI server in a background thread, then opens a pywebview
window. Closing the window shuts down the server cleanly.

Usage:
    python desktop.py            # desktop window (default)
    python desktop.py --no-gui  # headless server only (same as running main.py directly)
"""

import json as _json
import os
import sys
import socket
import threading
import time
import urllib.parse as _urlparse
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
    """Set environment flags for stable Qt WebEngine rendering under Wayland/X11."""
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
# Native drag-and-drop interception
# ---------------------------------------------------------------------------

def _setup_native_dnd(pywebview_window):
    """Intercept file-manager drops at the native layer and pass paths to JS.
    Tries the GTK backend first, then Qt. Called from webview.start(func=...)
    which runs in a background thread after the window is shown."""
    try:
        _setup_gtk_dnd(pywebview_window)
        return
    except Exception as e:
        log.debug("GTK DnD not available: %s", e)
    try:
        _setup_qt_dnd(pywebview_window)
        return
    except Exception as e:
        log.debug("Qt DnD not available: %s", e)
    log.warning("No native DnD backend available — drag-and-drop will not work")


def _setup_gtk_dnd(pywebview_window):
    import gi
    from gi.repository import GLib

    def _on_idle():
        try:
            gi.require_version('Gtk', '3.0')
            gi.require_version('Gdk', '3.0')
            from gi.repository import Gtk, Gdk, GObject

            toplevels = [w for w in Gtk.Window.list_toplevels() if w.get_visible()]
            if not toplevels:
                log.warning("GTK DnD: no visible toplevel windows")
                return False

            gtk_window = toplevels[0]
            target = _find_gtk_webview(gtk_window) or gtk_window

            target.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
            target.drag_dest_add_uri_targets()

            def on_drop(widget, ctx, x, y, sel, info, ts):
                uris = sel.get_uris() or []
                paths = [_urlparse.unquote(u[7:]) for u in uris if u.startswith('file://')]
                if paths:
                    js = f'window._pyDroppedPaths({_json.dumps(paths)})'
                    GLib.idle_add(lambda: _eval_js(pywebview_window, js) or False)
                Gtk.drag_finish(ctx, bool(paths), False, ts)
                try:
                    GObject.signal_stop_emission_by_name(widget, 'drag-data-received')
                except Exception:
                    pass

            target.connect('drag-data-received', on_drop)
            log.info("GTK DnD: connected to %s", type(target).__name__)
        except Exception as e:
            log.warning("GTK DnD idle error: %s", e)
        return False

    GLib.idle_add(_on_idle)


def _setup_qt_dnd(pywebview_window):
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QObject, QEvent
    except ImportError:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QObject, QEvent

    app = QApplication.instance()
    if app is None:
        raise RuntimeError("No QApplication instance")

    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            QWebEngineView = None

    class _DropFilter(QObject):
        def eventFilter(self, obj, event):
            t = event.type()
            if t == QEvent.Type.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif t == QEvent.Type.DragMove:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif t == QEvent.Type.Drop:
                urls = event.mimeData().urls()
                paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
                if paths:
                    js = f'window._pyDroppedPaths({_json.dumps(paths)})'
                    _eval_js(pywebview_window, js)
                event.acceptProposedAction()
                return True
            return False

    drop_filter = _DropFilter()
    app.installEventFilter(drop_filter)

    for widget in app.topLevelWidgets():
        if widget.isVisible():
            widget.setAcceptDrops(True)
            if QWebEngineView:
                for wv in widget.findChildren(QWebEngineView):
                    wv.setAcceptDrops(True)

    app._conduit_drop_filter = drop_filter  # prevent GC
    log.info("Qt DnD: event filter installed")


def _find_gtk_webview(container):
    """Recursively find a WebKit2.WebView in a GTK widget tree."""
    try:
        import gi
        for ver in ('4.1', '4.0'):
            try:
                gi.require_version('WebKit2', ver)
                break
            except Exception:
                continue
        from gi.repository import WebKit2
        if isinstance(container, WebKit2.WebView):
            return container
    except Exception:
        pass
    if hasattr(container, 'get_children'):
        for child in container.get_children():
            result = _find_gtk_webview(child)
            if result:
                return result
    return None


def _eval_js(pywebview_window, js):
    try:
        pywebview_window.evaluate_js(js)
    except Exception as e:
        log.warning("evaluate_js error: %s", e)


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

        log.info("Calling webview.start()")
        webview.start(debug=False, func=_setup_native_dnd, args=[window])
        log.info("webview.start() returned")
    except Exception as e:
        log.exception("webview error: %s", e)
        server.should_exit = True
        sys.exit(1)

    server_thread.join(timeout=5)
    log.info("=== Conduit exited ===")


if __name__ == "__main__":
    main()
