"""Frozen / desktop path helpers for sensors-view (Scheme A compat)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_ID = "sensors-view"
APP_TITLE = "sensors-view"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def meipass() -> Path | None:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return None


def project_root() -> Path:
    """Repo root (dev) or PyInstaller bundle root (_MEIPASS)."""
    mp = meipass()
    if mp is not None:
        return mp
    return Path(__file__).resolve().parents[1]


def app_package_dir() -> Path:
    """Directory containing static/ and templates/."""
    root = project_root()
    bundled = root / "app"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parent


def sensors_src_dir() -> Path:
    """Directory that contains the `sensors` Python package."""
    root = project_root()
    for candidate in (
        root / "sensors_src",
        root / "sensors" / "src",
        root.parent / "sensors" / "src",
    ):
        if (candidate / "sensors").is_dir():
            return candidate
    return root / "sensors" / "src"


def resolve_frontend_dist() -> Path:
    """Scheme A checklist path; sensors-view UI is Jinja+static under app/."""
    root = project_root()
    for candidate in (
        Path(os.environ["FRONTEND_DIST"]) if os.environ.get("FRONTEND_DIST") else None,
        root / "frontend-dist",
        app_package_dir() / "static",
    ):
        if candidate is None:
            continue
        if candidate.is_dir():
            return candidate
    return app_package_dir() / "static"


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_ID
    return Path.home() / ".local" / "share" / APP_ID


def install_location() -> Path:
    """Directory that represents where sensors-view is installed / running from."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    env = (os.environ.get("SENSORS_VIEW_USER_DATA") or "").strip()
    if env:
        return Path(env).resolve()
    return project_root().resolve()


def drive_root_of(path: Path | None = None) -> Path:
    """Drive / volume root for a path (Windows drive letter or Unix '/')."""
    p = (path or install_location()).resolve()
    anchor = p.anchor or "/"
    return Path(anchor)


def default_export_dir() -> Path:
    env = (os.environ.get("SENSORS_VIEW_EXPORT_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return drive_root_of(install_location())


def export_prefs_path() -> Path:
    return user_data_dir() / "config" / "export.json"


def load_export_dir() -> Path:
    prefs = export_prefs_path()
    if prefs.is_file():
        try:
            import json

            raw = json.loads(prefs.read_text(encoding="utf-8"))
            d = str((raw or {}).get("dir") or "").strip()
            if d:
                return Path(d).expanduser().resolve()
        except Exception:
            pass
    return default_export_dir()


def save_export_dir(path: Path) -> Path:
    import json

    resolved = path.expanduser().resolve()
    prefs = export_prefs_path()
    prefs.parent.mkdir(parents=True, exist_ok=True)
    prefs.write_text(
        json.dumps({"dir": str(resolved)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved


def default_view_config() -> Path:
    env = os.environ.get("SENSORS_VIEW_CONFIG")
    if env:
        return Path(env)
    data = user_data_dir() / "configs" / "view.yaml"
    if data.is_file():
        return data
    bundled = project_root() / "configs" / "view.yaml"
    if bundled.is_file():
        return bundled
    return data


def _seed_file(src: Path, dst: Path) -> None:
    if dst.exists() or not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _seed_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        return
    if not dst.exists():
        shutil.copytree(src, dst)


def ensure_runtime_env(*, desktop: bool = False) -> Path:
    """
    Prepare writable user data dir and env for desktop / frozen runs.
    Returns user_data_dir().
    """
    data = user_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    (data / "config").mkdir(parents=True, exist_ok=True)
    (data / "configs").mkdir(parents=True, exist_ok=True)

    root = project_root()
    _seed_file(root / "configs" / "view.yaml", data / "configs" / "view.yaml")
    # Bundle default sensors YAML next to user view config when frozen
    bundled_sensors_cfg = root / "sensors" / "configs"
    if not bundled_sensors_cfg.is_dir():
        bundled_sensors_cfg = root / "sensors_configs"
    _seed_tree(bundled_sensors_cfg, data / "sensors" / "configs")

    view_cfg = data / "configs" / "view.yaml"
    if view_cfg.is_file():
        # Prefer user-local sensors config path for portability
        text = view_cfg.read_text(encoding="utf-8")
        if "sensors/configs/default.yaml" in text and (data / "sensors" / "configs" / "default.yaml").is_file():
            # keep relative path; we chdir to data when desktop
            pass

    frontend = resolve_frontend_dist()
    os.environ.setdefault("FRONTEND_DIST", str(frontend.resolve()))
    os.environ.setdefault("SENSORS_VIEW_CONFIG", str(view_cfg.resolve() if view_cfg.is_file() else default_view_config()))
    os.environ.setdefault("SENSORS_VIEW_USER_DATA", str(data.resolve()))

    src = sensors_src_dir()
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

    if desktop or is_frozen():
        # Never chdir into a tree that could shadow site-packages (e.g. a local
        # numpy/ checkout). Prefer an explicit empty workdir under user data.
        work = data / "run"
        work.mkdir(parents=True, exist_ok=True)
        os.chdir(work)
    return data
