import os
import shutil
import sys
from pathlib import Path

APP_NAME = "conduit"


def bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return bundle_dir().joinpath(*parts)


def _user_home() -> Path:
    return Path.home()


def _platform_config_root() -> Path:
    if sys.platform == "darwin":
        return _user_home() / "Library" / "Application Support"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", _user_home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME", _user_home() / ".config"))


def _platform_data_root() -> Path:
    if sys.platform == "darwin":
        return _user_home() / "Library" / "Application Support"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", _user_home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_DATA_HOME", _user_home() / ".local" / "share"))


def _platform_state_root() -> Path:
    if sys.platform == "darwin":
        return _user_home() / "Library" / "Logs"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", _user_home() / "AppData" / "Local"))
    return Path(os.environ.get("XDG_STATE_HOME", _user_home() / ".local" / "state"))


def config_dir() -> Path:
    return _platform_config_root() / APP_NAME


def data_dir() -> Path:
    return _platform_data_root() / APP_NAME


def state_dir() -> Path:
    return _platform_state_root() / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def db_path() -> Path:
    return data_dir() / "mediamanager.db"


def log_path() -> Path:
    return state_dir() / "desktop.log"


def ensure_runtime_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    data_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)


def ensure_default_config() -> Path:
    ensure_runtime_dirs()
    destination = config_path()
    if destination.exists():
        return destination

    bundled = resource_path("config.json")
    if bundled.exists():
        shutil.copyfile(bundled, destination)
    else:
        destination.write_text("{}\n", encoding="utf-8")
    return destination
