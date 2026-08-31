#!/usr/bin/env python3
"""Build sensors-view desktop packages (native Linux or Windows via Wine)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "sensors-view"
APP_EXE = "sensors-view"
PIP_INDEX = os.environ.get("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _run(cmd: list[str], *, env: dict | None = None, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, env=env, cwd=str(cwd or ROOT))


def _linux_to_wine_path(path: Path) -> str:
    p = path.resolve()
    return "Z:" + str(p).replace("/", "\\")


def _ensure_win_python(tools: Path) -> Path:
    py = tools / "win-python"
    python_exe = py / "python.exe"
    if python_exe.is_file():
        return py

    tools.mkdir(parents=True, exist_ok=True)
    ver = "3.10.11"
    # Prefer npmmirror on AutoDL; fall back to python.org
    urls = [
        f"https://registry.npmmirror.com/-/binary/python/{ver}/python-{ver}-embed-amd64.zip",
        f"https://www.python.org/ftp/python/{ver}/python-{ver}-embed-amd64.zip",
    ]
    zip_path = tools / f"python-{ver}-embed-amd64.zip"
    if not zip_path.is_file() or zip_path.stat().st_size < 1_000_000:
        ok = False
        for url in urls:
            try:
                _run(["curl", "-L", "--retry", "3", "-o", str(zip_path), url])
                if zip_path.is_file() and zip_path.stat().st_size > 1_000_000:
                    ok = True
                    break
            except Exception:
                continue
        if not ok:
            raise SystemExit("failed to download embeddable CPython")
    if py.exists():
        shutil.rmtree(py)
    py.mkdir(parents=True)
    _run(["unzip", "-o", str(zip_path), "-d", str(py)])

    # Enable site + site-packages in ._pth
    pth = next(py.glob("python*._pth"))
    lines = pth.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("#") and "import site" in s:
            out.append("import site")
        elif s == "import site":
            out.append("import site")
        else:
            out.append(line)
    if "import site" not in "\n".join(out):
        out.append("import site")
    if "Lib\\site-packages" not in "\n".join(out) and "Lib/site-packages" not in "\n".join(out):
        out.append("Lib\\site-packages")
    pth.write_text("\n".join(out) + "\n", encoding="utf-8")
    (py / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)

    get_pip = tools / "get-pip.py"
    if not get_pip.is_file():
        _run(["curl", "-L", "-o", str(get_pip), "https://bootstrap.pypa.io/get-pip.py"])
    return py


def _wine_env(prefix: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["WINEARCH"] = "win64"
    env["WINEDEBUG"] = "-all"
    env["PIP_INDEX_URL"] = PIP_INDEX
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _wine_bin() -> str:
    for cand in ("wine64", "wine"):
        if shutil.which(cand):
            return cand
    raise SystemExit("wine64/wine not found — install wine (win64) first")


def build_windows(*, skip_frontend: bool = True) -> Path:
    wine = _wine_bin()
    tools = ROOT / ".tools"
    prefix = Path(os.environ.get("WINEPREFIX") or (ROOT / ".wine-sensors-view"))
    prefix.parent.mkdir(parents=True, exist_ok=True)
    py_dir = _ensure_win_python(tools)
    env = _wine_env(prefix)

    # Initialize prefix
    _run([wine, "wineboot", "--init"], env=env)

    py_wine = _linux_to_wine_path(py_dir / "python.exe")
    get_pip = _linux_to_wine_path(tools / "get-pip.py")
    _run([wine, py_wine, get_pip, "-i", PIP_INDEX], env=env)
    # Verify pip actually installed (embed + bad get-pip mirrors often fail silently)
    try:
        _run([wine, py_wine, "-m", "pip", "--version"], env=env)
    except subprocess.CalledProcessError as e:
        raise SystemExit(
            "pip not available in Wine embed Python after get-pip; "
            "re-download bootstrap.pypa.io/get-pip.py and ensure python*._pth has 'import site'"
        ) from e

    req = _linux_to_wine_path(ROOT / "requirements.txt")
    req_d = _linux_to_wine_path(ROOT / "requirements-desktop.txt")
    _run([wine, py_wine, "-m", "pip", "install", "-i", PIP_INDEX, "-r", req], env=env)
    _run([wine, py_wine, "-m", "pip", "install", "-i", PIP_INDEX, "-r", req_d], env=env)
    # Force numpy pin for Wine 6
    _run([wine, py_wine, "-m", "pip", "install", "-i", PIP_INDEX, "numpy==1.23.5"], env=env)

    dist = Path("/tmp/sensors-view-dist-win")
    work = Path("/tmp/sensors-view-work-win")
    for d in (dist, work):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    runner = _linux_to_wine_path(ROOT / "packaging" / "run_pyinstaller_wine.py")
    spec = _linux_to_wine_path(ROOT / "packaging" / "sensors-view-desktop-win.spec")
    dist_w = _linux_to_wine_path(dist)
    work_w = _linux_to_wine_path(work)
    _run(
        [
            wine,
            py_wine,
            runner,
            "--noconfirm",
            "--clean",
            "--distpath",
            dist_w,
            "--workpath",
            work_w,
            spec,
        ],
        env=env,
    )

    built = dist / APP_EXE
    if not built.is_dir():
        raise SystemExit(f"PyInstaller output missing: {built}")

    _postprocess_windows(built, py_dir)

    stamp = _utc_stamp()
    release = ROOT / "release" / f"{APP_ID}-desktop-windows-x64-{stamp}"
    if release.exists():
        shutil.rmtree(release)
    shutil.copytree(built, release)

    info = {
        "app_id": APP_ID,
        "platform": "windows-x64",
        "self_contained": True,
        "built_at": stamp,
        "entry": f"{APP_EXE}.exe",
        "notes": "Built on Linux via Wine + embeddable CPython + PyInstaller",
    }
    (release / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    (release / "README.txt").write_text(
        "\n".join(
            [
                "sensors-view desktop (Windows x64)",
                "",
                "1. Unzip this folder",
                "2. Double-click sensors-view.exe",
                "3. No need to install Python / Node",
                "4. User data: %APPDATA%\\sensors-view\\",
                "5. Login: username sensors; first-run password is random",
                "   → open %APPDATA%\\sensors-view\\config\\.auth.json",
                "   or watch the console line [auth] created admin ...",
                "6. Optional: set SENSORS_VIEW_AUTH_PASSWORD before launch",
                "7. Default dry_run=true; edit configs\\view.yaml under AppData after first run",
                "",
            ]
        ),
        encoding="utf-8",
    )

    zip_path = release.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in release.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(release.parent)))
    print(f"release: {release}")
    print(f"zip: {zip_path}")
    return release


def _postprocess_windows(built: Path, py_dir: Path) -> None:
    internal = built / "_internal"
    internal.mkdir(parents=True, exist_ok=True)
    embed_zip = py_dir / "python310.zip"
    if embed_zip.is_file():
        shutil.copy2(embed_zip, internal / "python310.zip")

    base = internal / "base_library.zip"
    if not base.is_file():
        # Sometimes named differently; search
        hits = list(internal.glob("base_library.zip"))
        if hits:
            base = hits[0]
    if not base.is_file() or not embed_zip.is_file():
        print("[warn] skip base_library inject (missing zip)")
        return

    import zipfile as zfmod

    need_prefixes = (
        "pkgutil",
        "inspect",
        "copy",
        "pathlib",
        "typing",
        "contextlib",
        "dataclasses",
        "importlib",
        "json",
        "logging",
        "collections",
        "urllib",
        "email",
        "html",
        "xml",
        "encodings",
        "asyncio",
        "concurrent",
        "multiprocessing",
        "zoneinfo",
    )
    with zfmod.ZipFile(embed_zip, "r") as src, zfmod.ZipFile(base, "a") as dst:
        existing = set(dst.namelist())
        for name in src.namelist():
            top = name.split("/")[0].split(".")[0]
            if any(top == p or name.startswith(p + "/") or name.startswith(p + ".") for p in need_prefixes):
                if name not in existing:
                    dst.writestr(name, src.read(name))


def _ensure_linux_venv(tools: Path) -> Path:
    venv = tools / "linux-venv"
    py = venv / "bin" / "python"
    if py.is_file():
        return venv
    tools.mkdir(parents=True, exist_ok=True)
    # Prefer 3.10 when ensurepip/venv is available; else fall back to current interpreter
    creators: list[str] = []
    for cand in ("python3.10", "python3.11", sys.executable, "python3"):
        path = cand if "/" in cand else shutil.which(cand)
        if path and path not in creators:
            creators.append(path)
    if not creators:
        raise SystemExit("python3 not found for Linux venv")
    last_err: Exception | None = None
    for creator in creators:
        try:
            if venv.exists():
                shutil.rmtree(venv)
            _run([creator, "-m", "venv", str(venv)])
            if (venv / "bin" / "python").is_file():
                print(f"[linux-venv] created with {creator}", flush=True)
                return venv
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[linux-venv] skip {creator}: {exc}", flush=True)
            continue
    raise SystemExit(f"failed to create linux venv: {last_err}")


def _platform_tag() -> str:
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "linux-x64"
    if machine in {"aarch64", "arm64"}:
        return "linux-arm64"
    return f"linux-{machine}"


def _numpy_spec_for(py: str) -> str:
    """Wine builds need 1.23.5; native Linux follows the interpreter's wheels."""
    out = subprocess.check_output([py, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"], text=True)
    major_minor = out.strip()
    major, minor = (int(x) for x in major_minor.split("."))
    if (major, minor) <= (3, 10):
        return "numpy==1.23.5"
    # 1.23.5 has no cp312 wheels and fails to build from sdist on 3.12
    return "numpy>=1.26.4,<2"


def build_native(*, skip_frontend: bool = True) -> Path:
    del skip_frontend  # sensors-view UI is Jinja/static; stub frontend-dist is enough
    tools = ROOT / ".tools"
    venv = _ensure_linux_venv(tools)
    py = str(venv / "bin" / "python")
    pip = [py, "-m", "pip"]
    numpy_spec = _numpy_spec_for(py)

    _run([*pip, "install", "-U", "pip", "setuptools", "wheel", "-i", PIP_INDEX])
    # Install app deps without the Windows/Wine numpy pin when on newer Python
    _run(
        [
            *pip,
            "install",
            "-i",
            PIP_INDEX,
            "fastapi>=0.110",
            "uvicorn[standard]>=0.27",
            "jinja2>=3.1",
            "PyYAML>=6.0",
            "Pillow>=10.0",
            numpy_spec,
        ]
    )
    _run(
        [
            *pip,
            "install",
            "-i",
            PIP_INDEX,
            "pyinstaller>=6.3",
            "pywebview>=5.0",
            "Pillow>=10.0",
            numpy_spec,
        ]
    )
    dist = Path("/tmp/sensors-view-dist-linux")
    work = Path("/tmp/sensors-view-work-linux")
    for d in (dist, work):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    spec = ROOT / "packaging" / "sensors-view-desktop.spec"
    if not spec.is_file():
        raise SystemExit(f"missing spec: {spec}")

    _run(
        [
            py,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
            str(spec),
        ]
    )

    built = dist / APP_EXE
    if not built.is_dir():
        raise SystemExit(f"PyInstaller output missing: {built}")
    entry = built / APP_EXE
    if not entry.is_file():
        raise SystemExit(f"missing binary: {entry}")
    entry.chmod(entry.stat().st_mode | 0o111)

    stamp = _utc_stamp()
    plat = _platform_tag()
    release = ROOT / "release" / f"{APP_ID}-desktop-{plat}-{stamp}"
    if release.exists():
        shutil.rmtree(release)
    shutil.copytree(built, release)

    info = {
        "app_id": APP_ID,
        "product": APP_ID,
        "kind": "desktop",
        "platform": plat,
        "self_contained": True,
        "requires_python_on_target": False,
        "built_at": stamp,
        "built_at_utc": stamp,
        "entry": APP_EXE,
        "notes": "Built on Linux via native PyInstaller onedir",
    }
    (release / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    (release / "README.txt").write_text(
        "\n".join(
            [
                "sensors-view desktop (Linux)",
                "",
                "1. Extract this folder",
                "2. Run: ./sensors-view",
                "3. No need to install Python / Node",
                "4. User data: ~/.local/share/sensors-view/",
                "5. Login: username sensors; first-run password is random",
                "   → see console [auth] created admin ...",
                "   → or ~/.local/share/sensors-view/config/.auth.json",
                "6. Optional: SENSORS_VIEW_AUTH_PASSWORD / SENSORS_VIEW_PORT before launch",
                "7. Without DISPLAY / pywebview, falls back to system browser; Ctrl+C stops",
                "8. Default dry_run=true; edit configs/view.yaml under the data dir after first run",
                "",
            ]
        ),
        encoding="utf-8",
    )

    tar_path = release.with_suffix(".tar.gz")
    if tar_path.exists():
        tar_path.unlink()
    _run(["tar", "-C", str(release.parent), "-czf", str(tar_path), release.name])

    zip_path = Path(str(release) + ".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in release.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(release.parent)))

    print(f"release: {release}")
    print(f"tar.gz: {tar_path}")
    print(f"zip: {zip_path}")
    return release


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sensors-view desktop packages")
    parser.add_argument(
        "--target",
        choices=["windows", "native", "linux"],
        default="windows",
        help="windows = Wine cross-build; native/linux = current Linux host",
    )
    parser.add_argument("--skip-frontend", action="store_true", default=True)
    args = parser.parse_args()
    target = "native" if args.target == "linux" else args.target
    if target == "windows":
        build_windows(skip_frontend=args.skip_frontend)
    else:
        build_native(skip_frontend=args.skip_frontend)


if __name__ == "__main__":
    main()
