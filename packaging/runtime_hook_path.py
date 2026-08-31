"""PyInstaller runtime hook: keep frozen sys.path / native libs sane before imports.

Prevents the misleading numpy error:
  Error importing numpy: you should not try to import numpy from its source directory
which usually means __config__ / _multiarray_umath failed because cwd or sys.path
pointed at an on-disk numpy/ tree (module_collection_mode=py) or libs were not found.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _apply() -> None:
    if not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    root = Path(meipass).resolve()

    # Prefer bundled shared libs for extension modules (numpy.libs, etc.).
    lib_dirs = [root / "numpy.libs", root / "Pillow.libs", root]
    prepend = [str(p) for p in lib_dirs if p.is_dir()]
    if prepend:
        cur = os.environ.get("LD_LIBRARY_PATH", "")
        parts = prepend + ([cur] if cur else [])
        os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(parts)

    # If we were started with cwd inside a packaged package tree (e.g. …/_internal/numpy),
    # '' on sys.path makes "import numpy" treat cwd as the package → source-tree failure.
    try:
        cwd = Path.cwd().resolve()
    except Exception:  # noqa: BLE001
        cwd = None
    if cwd is not None and (cwd / "__init__.py").is_file() and cwd.name in {
        "numpy",
        "PIL",
        "cv2",
        "sensors",
        "app",
    }:
        safe = root.parent if (root.parent / "sensors-view").exists() else root
        try:
            os.chdir(safe)
        except Exception:  # noqa: BLE001
            pass

    mp = str(root)
    # Drop empty/cwd entries and ensure _MEIPASS is first.
    cleaned: list[str] = []
    for p in sys.path:
        if p in ("", "."):
            continue
        try:
            if Path(p).resolve() == root:
                continue
        except Exception:  # noqa: BLE001
            pass
        if p not in cleaned:
            cleaned.append(p)
    sys.path[:] = [mp, *cleaned]


_apply()
