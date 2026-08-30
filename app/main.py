from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
SENSORS_SRC = ROOT / "sensors" / "src"
if SENSORS_SRC.is_dir() and str(SENSORS_SRC) not in sys.path:
    sys.path.insert(0, str(SENSORS_SRC))

from sensors.runtime.manager import SensorManager  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
DEFAULT_VIEW_CFG = ROOT / "configs" / "view.yaml"

app = FastAPI(title="sensors-view", version="0.1.0")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

_view_cfg: dict[str, Any] = {}
_mgr: SensorManager | None = None
_view_config_path: Path = DEFAULT_VIEW_CFG


def _load_view_cfg(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return dict(data)


def _resolve_sensors_config(raw: str | Path) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def get_manager(*, reload: bool = False) -> SensorManager:
    global _mgr
    if _mgr is not None and not reload:
        return _mgr
    cfg_path = _resolve_sensors_config(_view_cfg.get("sensors_config", "sensors/configs/default.yaml"))
    if not cfg_path.is_file():
        raise FileNotFoundError(f"sensors config not found: {cfg_path}")
    dry_run = bool(_view_cfg.get("dry_run", True))
    _mgr = SensorManager.from_yaml(cfg_path, dry_run=dry_run)
    return _mgr


def _jsonable(obj: Any) -> Any:
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return {"_ndarray": True, "dtype": str(obj.dtype), "shape": list(obj.shape)}
        if isinstance(obj, (np.floating, np.integer)):
            return obj.item()
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


@app.on_event("startup")
def _startup() -> None:
    global _view_cfg, _view_config_path
    cfg = getattr(app.state, "view_config", None) or str(_view_config_path)
    _view_config_path = Path(cfg)
    _view_cfg = _load_view_cfg(_view_config_path)
    get_manager(reload=True)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": _view_cfg.get("title", "sensors-view"),
            "refresh_seconds": int(_view_cfg.get("refresh_seconds", 5)),
            "dry_run": bool(_view_cfg.get("dry_run", True)),
            "sensors_config": str(
                _resolve_sensors_config(_view_cfg.get("sensors_config", "sensors/configs/default.yaml"))
            ),
        },
    )


@app.get("/api/meta")
def api_meta() -> dict[str, Any]:
    mgr = get_manager()
    return {
        "title": _view_cfg.get("title", "sensors-view"),
        "site": mgr.bundle.site,
        "dry_run": mgr.ctx.dry_run,
        "refresh_seconds": int(_view_cfg.get("refresh_seconds", 5)),
        "sensors_config": str(
            _resolve_sensors_config(_view_cfg.get("sensors_config", "sensors/configs/default.yaml"))
        ),
        "device_ids": mgr.ids(),
        "count": len(mgr),
    }


@app.get("/api/probe")
def api_probe(id: str | None = Query(default=None)) -> dict[str, Any]:
    mgr = get_manager()
    only = [id] if id else None
    reports = mgr.probe_all(only=only)
    devices: list[dict[str, Any]] = []
    for r in reports:
        d = r.to_dict()
        try:
            d["name"] = mgr.get(r.sensor_id).name
        except KeyError:
            d["name"] = r.sensor_id
        devices.append(d)
    return {
        "site": mgr.bundle.site,
        "dry_run": mgr.ctx.dry_run,
        "devices": devices,
    }


@app.get("/api/read/{sensor_id}")
def api_read(sensor_id: str) -> dict[str, Any]:
    mgr = get_manager()
    if sensor_id not in mgr.ids():
        raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
    try:
        sample = mgr.read(sensor_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"id": sensor_id, "sample": _jsonable(sample)}


@app.post("/api/reload")
def api_reload() -> dict[str, Any]:
    global _view_cfg
    _view_cfg = _load_view_cfg(_view_config_path)
    mgr = get_manager(reload=True)
    return {"ok": True, "count": len(mgr), "site": mgr.bundle.site}


def main(argv: list[str] | None = None) -> None:
    global _view_config_path
    parser = argparse.ArgumentParser(prog="sensors-view")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_VIEW_CFG)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not args.config.is_file():
        raise SystemExit(f"view config missing: {args.config}")
    _view_config_path = args.config.resolve()
    app.state.view_config = str(_view_config_path)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
