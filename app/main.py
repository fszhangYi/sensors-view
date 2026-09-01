from __future__ import annotations

import argparse
import base64
import io
import math
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import auth as view_auth
from .paths import (
    app_package_dir,
    default_export_dir,
    default_view_config,
    load_export_dir,
    project_root,
    save_export_dir,
    sensors_src_dir,
)


ROOT = project_root()
SENSORS_SRC = sensors_src_dir()
if SENSORS_SRC.is_dir() and str(SENSORS_SRC) not in sys.path:
    sys.path.insert(0, str(SENSORS_SRC))

from sensors.core.base import Sensor, SensorContext  # noqa: E402
from sensors.core.health import CheckResult, HealthReport, HealthStatus  # noqa: E402
from sensors.runtime.manager import SensorManager  # noqa: E402

# Kinds where "探测状态" means a real non-dry-run open+read (same bar as 单次采样).
# bus/pipeline: shallow probe only — open() may start socat / has no meaningful sample.
_LIVE_CONNECT_KINDS = frozenset({"arm", "gripper", "gello", "ft", "tactile", "realsense"})
_SHALLOW_CONNECT_KINDS = frozenset({"bus", "pipeline"})

APP_DIR = app_package_dir()
DEFAULT_VIEW_CFG = default_view_config() if default_view_config().is_file() else (ROOT / "configs" / "view.yaml")

CONNECT_FIELDS: dict[str, list[dict[str, Any]]] = {
    "bus": [
        {"key": "robot_ip", "label": "机器人 IP", "type": "text"},
        {"key": "robot_tcp_port", "label": "TCP 端口", "type": "number"},
        {"key": "local_pty", "label": "本地 PTY", "type": "text"},
        {"key": "socat_script", "label": "socat 脚本", "type": "text"},
    ],
    "arm": [
        {"key": "zmq_host", "label": "ZMQ Host", "type": "text"},
        {"key": "zmq_port", "label": "ZMQ Port", "type": "number"},
        {"key": "backend", "label": "Backend", "type": "text"},
        {"key": "robot_ip", "label": "机器人 IP", "type": "text"},
        {"key": "num_joints", "label": "关节数", "type": "number"},
        {"key": "rcv_timeout_ms", "label": "接收超时 ms", "type": "number"},
    ],
    "gello": [
        {"key": "port", "label": "串口路径", "type": "text"},
        {"key": "baudrate", "label": "波特率", "type": "number"},
        {"key": "joint_ids", "label": "关节 ID (逗号分隔)", "type": "text", "as": "int_list"},
    ],
    "gripper": [
        {"key": "port", "label": "串口路径", "type": "text"},
        {"key": "baudrate", "label": "波特率", "type": "number"},
        {"key": "slave_id", "label": "Slave ID", "type": "number"},
        {"key": "default_force", "label": "夹持力", "type": "number"},
        {"key": "default_speed", "label": "速度", "type": "number"},
        {"key": "init_on_open", "label": "打开时初始化", "type": "checkbox", "as": "bool"},
        {"key": "timeout_ms", "label": "串口超时 ms", "type": "number"},
    ],
    "realsense": [
        {"key": "serial", "label": "相机序列号", "type": "text"},
        {"key": "role", "label": "角色 left/right/middle", "type": "text"},
        {"key": "width", "label": "分辨率宽度", "type": "number"},
        {"key": "height", "label": "分辨率高度", "type": "number"},
        {
            "key": "fps",
            "label": "硬件帧率 (仅 6/15/30/60)",
            "type": "select",
            "options": [6, 15, 30, 60],
        },
        {"key": "enable_depth", "label": "深度图", "type": "checkbox", "as": "bool"},
        {"key": "align_to_color", "label": "深度对齐彩色", "type": "checkbox", "as": "bool"},
        {"key": "exposure", "label": "曝光", "type": "number"},
        {"key": "gain", "label": "增益", "type": "number"},
        {"key": "timeout_ms", "label": "取帧超时 ms", "type": "number"},
    ],
    "pipeline": [
        {"key": "flag_shm", "label": "flag SHM", "type": "text"},
        {"key": "mosaic_shm", "label": "mosaic SHM", "type": "text"},
        {"key": "joint_shm", "label": "joint SHM", "type": "text"},
    ],
    "ft": [
        {"key": "port", "label": "串口 (Windows: COM5)", "type": "text"},
        {
            "key": "port_substr",
            "label": "by-id 子串 (可选，仅 port 为空时 Linux 自动匹配)",
            "type": "text",
        },
        {"key": "baudrate", "label": "波特率", "type": "number"},
        {"key": "timeout_ms", "label": "读帧超时 ms", "type": "number"},
    ],
    "tactile": [
        {"key": "dll_path", "label": "DLL 路径 (ReadPaxiniLib)", "type": "text"},
        {"key": "paxini_channel", "label": "Paxini 通道", "type": "number"},
        {"key": "port", "label": "串口 (可选)", "type": "text"},
        {"key": "group_index", "label": "力组索引", "type": "number"},
        {"key": "dry_run_groups", "label": "dry-run 组数", "type": "number"},
    ],
}

app = FastAPI(title="sensors-view", version="0.1.0")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

_view_cfg: dict[str, Any] = {}
_mgr: SensorManager | None = None
_view_config_path: Path = DEFAULT_VIEW_CFG
_sessions: dict[str, "SampleSession"] = {}
_sessions_lock = threading.Lock()
_export_jobs: dict[str, dict[str, Any]] = {}
_export_jobs_lock = threading.Lock()
_postprocess_jobs: dict[str, dict[str, Any]] = {}
_postprocess_jobs_lock = threading.Lock()


class SampleRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool | None = None


class TickRequest(BaseModel):
    command: dict[str, Any] | None = None


class CommandRequest(BaseModel):
    command: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool | None = None


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""


class PasswordChangeBody(BaseModel):
    current_password: str = ""
    new_password: str = ""


class UserCreateBody(BaseModel):
    username: str = ""
    password: str = ""
    role: str = "user"


class UserUpdateBody(BaseModel):
    role: str | None = None
    enabled: bool | None = None
    password: str | None = None


class ProbeRequest(BaseModel):
    """Overview connectivity probe — same bar as 单次采样 (open+read with current config)."""

    id: str | None = None
    configs: dict[str, dict[str, Any]] = Field(default_factory=dict)


class GripperWriteProbeRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool | None = None
    read_hz: float = 8.0
    write_hz: float = 8.0
    hz_min: float = 1.0
    hz_max: float = 200.0
    value_min: float = 0.0
    value_max: float = 0.637
    baseline_s: float = 1.5
    max_duration_s: float = 25.0
    sync_duration_s: float = 10.0
    read_duration_s: float = 10.0


class ExportDirBody(BaseModel):
    dir: str = ""


class ExportSaveBody(BaseModel):
    filename: str = ""
    data: Any = None
    dir: str | None = None


class PostprocessBody(BaseModel):
    """Convert sensors-view-*.json under export dir into hik episode folders."""

    dir: str | None = None
    seq: str | None = None
    filename: str | None = None
    out_dir: str | None = None
    interval_ms: float = 200.0
    write_video: bool = False


def _safe_export_filename(name: str) -> str:
    base = Path(str(name or "").strip().replace("\\", "/")).name
    if not base or base in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid filename")
    if not base.lower().endswith(".json"):
        base = f"{base}.json"
    if any(c in base for c in '<>:"|?*') or not all(c.isalnum() or c in "._-" for c in base):
        raise HTTPException(status_code=400, detail="filename has invalid characters")
    return base


def _resolve_export_dir(raw: str | None = None) -> Path:
    text = (raw or "").strip()
    if text:
        return Path(text).expanduser().resolve()
    return load_export_dir()


def _write_export_json(directory: Path, filename: str, data: Any) -> Path:
    import json

    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / filename).resolve()
    try:
        target.relative_to(directory)
    except ValueError as exc:
        raise ValueError("path escapes export dir") from exc
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _resolve_export_target(directory: Path, filename: str) -> Path:
    directory = directory.resolve()
    target = (directory / filename).resolve()
    try:
        target.relative_to(directory)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes export dir") from exc
    return target


@dataclass
class SampleSession:
    id: str
    sensor_id: str
    kind: str
    name: str
    dry_run: bool
    sensor: Any
    config_used: dict[str, Any]
    tick: int = 0
    started_at: float = field(default_factory=time.time)


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
    dry_run = bool(_view_cfg.get("dry_run", False))
    _mgr = SensorManager.from_yaml(cfg_path, dry_run=dry_run)
    return _mgr


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return {"_ndarray": True, "dtype": str(obj.dtype), "shape": list(obj.shape)}
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _encode_image_b64(arr: np.ndarray, *, max_side: int = 640) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    if arr.ndim == 2:
        img = Image.fromarray(arr.astype(np.uint8), mode="L")
    elif arr.ndim == 3 and arr.shape[2] >= 3:
        rgb = arr[:, :, :3][:, :, ::-1]
        img = Image.fromarray(np.ascontiguousarray(rgb.astype(np.uint8)), mode="RGB")
    else:
        return None
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _depth_preview(depth: np.ndarray) -> str | None:
    if depth is None:
        return None
    d = np.squeeze(depth).astype(np.float32)
    if d.size == 0:
        return None
    finite = d[np.isfinite(d)]
    if finite.size == 0:
        return None
    lo, hi = np.percentile(finite, [5, 95])
    if hi <= lo:
        hi = lo + 1.0
    norm = np.clip((d - lo) / (hi - lo), 0, 1)
    gray = (norm * 255).astype(np.uint8)
    return _encode_image_b64(gray)


def _synthetic_color(width: int = 320, height: int = 180, tick: int = 0) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width]
    phase = (tick % 40) / 40.0
    b = (168 + 28 * (xx / max(width - 1, 1)) - 20 * (yy / max(height - 1, 1))).astype(np.uint8)
    g = (162 + 18 * (yy / max(height - 1, 1))).astype(np.uint8)
    r = (148 + 12 * ((xx + yy) / max(width + height - 2, 1))).astype(np.uint8)
    img = np.stack([b, g, r], axis=-1)
    img[::20, :, :] = np.clip(img[::20, :, :].astype(np.int16) - 18, 0, 255).astype(np.uint8)
    img[:, ::20, :] = np.clip(img[:, ::20, :].astype(np.int16) - 18, 0, 255).astype(np.uint8)
    x0 = 16 + int(phase * max(width - 48, 1))
    img[12:18, x0 : min(width - 16, x0 + 28), :] = (140, 90, 30)
    return img


def _tactile_z_heatmap(component_forces: Any, grid_hw: tuple[int, int] = (6, 10)) -> np.ndarray | None:
    """Build an upscaled Z-channel heatmap (H×W×3 BGR) from 60×3 component forces."""
    try:
        arr = np.asarray(component_forces, dtype=np.float64)
    except Exception:  # noqa: BLE001
        return None
    if arr.ndim != 2 or arr.shape[0] < grid_hw[0] * grid_hw[1] or arr.shape[1] < 3:
        return None
    z = arr[: grid_hw[0] * grid_hw[1], 2].reshape(grid_hw)
    zmax = float(np.max(np.abs(z))) or 1.0
    norm = np.clip(z / zmax, 0.0, 1.0)
    # teal→spark style ramp without depending on CSS
    h, w = grid_hw
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[:, :, 0] = (20 + 40 * (1.0 - norm)).astype(np.uint8)  # B
    rgb[:, :, 1] = (80 + 150 * norm).astype(np.uint8)  # G
    rgb[:, :, 2] = (40 + 200 * norm).astype(np.uint8)  # R
    # nearest upscale for card preview
    scale = 24
    return np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)


def _build_viz(kind: str, sample: dict[str, Any], *, dry_run: bool, tick: int = 0) -> dict[str, Any]:
    viz: dict[str, Any] = {"kind": kind, "charts": [], "images": [], "metrics": [], "note": ""}
    t = tick * 0.18

    if kind == "arm":
        joints = sample.get("joints")
        if joints is None and dry_run:
            joints = [math.sin(t + i * 0.45) * (0.35 + 0.05 * i) for i in range(7)]
            viz["note"] = "dry-run 连续占位关节角"
        if isinstance(joints, list) and joints:
            viz["charts"].append(
                {
                    "type": "bars",
                    "title": "关节角 (rad)",
                    "labels": [f"j{i + 1}" for i in range(len(joints))],
                    "values": [float(x) for x in joints],
                }
            )
            viz["metrics"].append({"label": "dofs", "value": str(len(joints))})

    elif kind == "gello":
        joints = sample.get("joints_rad")
        if joints is None and dry_run:
            joints = [math.sin(t + i * 0.35) * 0.5 * ((-1) ** i) for i in range(7)]
            viz["note"] = "dry-run 连续占位 Gello"
        if isinstance(joints, list) and joints:
            viz["charts"].append(
                {
                    "type": "bars",
                    "title": "Leader 关节 (rad)",
                    "labels": [f"id{i + 1}" for i in range(len(joints))],
                    "values": [float(x) for x in joints],
                }
            )

    elif kind == "gripper":
        raw = sample.get("position_raw")
        norm = sample.get("position_norm")
        if raw is None and dry_run:
            norm = 0.3185 + 0.25 * math.sin(t)
            raw = int(1000 - norm / 0.000637)
            viz["note"] = "dry-run 连续占位夹爪"
        viz["charts"].append(
            {
                "type": "gauge",
                "title": "夹爪开合",
                "value": float(norm) if norm is not None else 0.0,
                "min": 0.0,
                "max": 0.637,
            }
        )
        viz["metrics"].extend(
            [
                {"label": "raw", "value": str(raw)},
                {"label": "norm", "value": f"{norm:.4f}" if isinstance(norm, (int, float)) else str(norm)},
                {"label": "init", "value": str(sample.get("init_state"))},
                {"label": "grip", "value": str(sample.get("grip_state"))},
            ]
        )

    elif kind == "realsense":
        color = sample.get("color")
        depth = sample.get("depth")
        if color is None and dry_run:
            color = _synthetic_color(tick=tick)
            viz["note"] = "dry-run 连续占位彩图"
        if isinstance(color, np.ndarray):
            b64 = _encode_image_b64(color)
            if b64:
                viz["images"].append({"title": "Color", "src": b64})
            viz["metrics"].append({"label": "color", "value": str(tuple(color.shape))})
        if isinstance(depth, np.ndarray):
            b64 = _depth_preview(depth)
            if b64:
                viz["images"].append({"title": "Depth", "src": b64})
            viz["metrics"].append({"label": "depth", "value": str(tuple(depth.shape))})
        if sample.get("serial"):
            viz["metrics"].append({"label": "serial", "value": str(sample.get("serial"))})
        if sample.get("role"):
            viz["metrics"].append({"label": "role", "value": str(sample.get("role"))})
        for k in ("width", "height", "fps", "fps_requested", "enable_depth", "align_to_color"):
            if k in sample:
                viz["metrics"].append({"label": k, "value": str(sample.get(k))})
        if sample.get("fps_requested") and sample.get("fps") and sample.get("fps_requested") != sample.get("fps"):
            viz["note"] = (
                viz.get("note")
                or (
                    f"相机硬件帧率回退: 请求 {sample.get('fps_requested')} → 实际 {sample.get('fps')} "
                    f"(RealSense 仅支持离散帧率，常见 6/15/30/60)"
                )
            )

    elif kind == "bus":
        for k in ("local_pty", "pty_exists", "socat_running", "proc_alive", "robot"):
            if k in sample:
                viz["metrics"].append({"label": k, "value": str(sample.get(k))})
        hits = sample.get("expect_hits") or {}
        if isinstance(hits, dict) and hits:
            viz["charts"].append(
                {
                    "type": "bars",
                    "title": "by-id 命中",
                    "labels": list(hits.keys()),
                    "values": [1.0 if v else 0.0 for v in hits.values()],
                }
            )

    elif kind == "ft":
        force = sample.get("force")
        torque = sample.get("torque")
        wrench = sample.get("wrench")
        if (force is None or torque is None) and isinstance(wrench, list) and len(wrench) >= 6:
            force = wrench[:3]
            torque = wrench[3:6]
        if force is None and dry_run:
            force = [
                0.8 * math.sin(t * 0.9),
                0.6 * math.cos(t * 1.1),
                2.0 + 0.5 * math.sin(t * 0.55),
            ]
            torque = [
                0.05 * math.sin(t * 1.3 + 0.2),
                0.04 * math.cos(t * 1.05),
                0.03 * math.sin(t * 0.7),
            ]
            viz["note"] = "dry-run 腕部六维力 (HIK_LMM_FORCE_TORQUE)"
        if isinstance(force, list) and isinstance(torque, list) and len(force) >= 3 and len(torque) >= 3:
            fl = sample.get("force_labels") or ["Fx", "Fy", "Fz"]
            tl = sample.get("torque_labels") or ["Tx", "Ty", "Tz"]
            viz["charts"].append(
                {
                    "type": "bars",
                    "title": "力 force (N)",
                    "labels": list(fl)[:3],
                    "values": [float(x) for x in force[:3]],
                }
            )
            viz["charts"].append(
                {
                    "type": "bars",
                    "title": "力矩 torque (N·m)",
                    "labels": list(tl)[:3],
                    "values": [float(x) for x in torque[:3]],
                }
            )
            bias = sample.get("bias") or [0, 0, 0, 0, 0, 0]
            viz["metrics"].extend(
                [
                    {"label": "|F|", "value": f"{float(sample.get('force_norm', 0)):.4f}"},
                    {"label": "|T|", "value": f"{float(sample.get('torque_norm', 0)):.4f}"},
                    {
                        "label": "bias F",
                        "value": ", ".join(f"{float(v):.3f}" for v in list(bias)[:3]),
                    },
                    {
                        "label": "bias T",
                        "value": ", ".join(f"{float(v):.3f}" for v in list(bias)[3:6]),
                    },
                    {"label": "backend", "value": "serial"},
                    {"label": "port", "value": str(sample.get("port", "—"))},
                ]
            )
        elif dry_run:
            viz["note"] = viz.get("note") or "六维力无数据"

    elif kind == "tactile":
        rest = sample.get("rest_force")
        contact = sample.get("contact_force")
        comps = sample.get("component_forces")
        num = int(sample.get("num") or 0)
        if rest is None and dry_run:
            rest = [
                0.12 * math.sin(t * 0.9),
                0.10 * math.cos(t * 1.1),
                max(0.05, 0.8 + 0.6 * math.sin(t * 0.65)),
            ]
            contact = rest[2]
            viz["note"] = "dry-run 帕西尼触觉 (rest_force + 6×10 分力)"
        if isinstance(rest, list) and len(rest) >= 3:
            viz["charts"].append(
                {
                    "type": "bars",
                    "title": "合力 rest_force (N)",
                    "labels": ["Rx", "Ry", "Rz"],
                    "values": [float(x) for x in rest[:3]],
                }
            )
            cf = float(contact) if contact is not None else float(rest[2])
            viz["charts"].append(
                {
                    "type": "gauge",
                    "title": "接触力 get_force() ≡ Rz",
                    "value": cf,
                    "min": 0.0,
                    "max": max(cf * 1.4, 2.0),
                }
            )
            heat = _tactile_z_heatmap(comps)
            if heat is not None:
                b64 = _encode_image_b64(heat)
                if b64:
                    viz["images"].append({"title": "分力 Z · 6×10", "src": b64})
            groups = sample.get("groups") or []
            viz["metrics"].extend(
                [
                    {"label": "num", "value": str(num or len(groups) or 1)},
                    {"label": "group", "value": str(sample.get("group_index", 0))},
                    {"label": "Rz", "value": f"{float(rest[2]):.4f}"},
                    {"label": "contact", "value": f"{cf:.4f}"},
                    {"label": "grid", "value": str(sample.get("grid_shape") or [6, 10, 3])},
                    {"label": "channel", "value": str(sample.get("paxini_channel", "—"))},
                ]
            )
            if len(groups) > 1:
                viz["charts"].append(
                    {
                        "type": "bars",
                        "title": "各组 Rz",
                        "labels": [f"g{i}" for i in range(len(groups))],
                        "values": [
                            float((g.get("rest_force") or [0, 0, 0])[2]) if isinstance(g, dict) else 0.0
                            for g in groups
                        ],
                    }
                )
        elif dry_run:
            viz["note"] = viz.get("note") or "帕西尼触觉无数据"

    else:
        for k, v in sample.items():
            if k in ("color", "depth", "ts", "groups", "component_forces", "original_forces"):
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                viz["metrics"].append({"label": k, "value": str(v)})
            if len(viz["metrics"]) >= 8:
                break
        if dry_run:
            viz["note"] = viz.get("note") or "该 kind 以 JSON / 指标展示为主"

    viz["metrics"].append({"label": "tick", "value": str(tick)})
    return viz


def _coerce_overrides(kind: str, raw: dict[str, Any]) -> dict[str, Any]:
    fields = {f["key"]: f for f in CONNECT_FIELDS.get(kind, [])}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        meta = fields.get(k, {})
        as_type = meta.get("as")
        ftype = meta.get("type")
        if as_type == "int_list":
            if isinstance(v, list):
                out[k] = [int(x) for x in v]
            else:
                parts = [p.strip() for p in str(v).split(",") if p.strip()]
                out[k] = [int(p) for p in parts]
        elif ftype == "checkbox" or as_type == "bool":
            if isinstance(v, bool):
                out[k] = v
            else:
                out[k] = str(v).lower() in ("1", "true", "on", "yes")
        elif ftype == "number":
            if v == "" or v is None:
                continue
            num = float(v)
            out[k] = int(num) if num.is_integer() else num
        elif ftype == "select":
            if v == "" or v is None:
                continue
            opts = meta.get("options") or []
            if opts and all(isinstance(o, (int, float)) for o in opts):
                num = float(v)
                out[k] = int(num) if num.is_integer() else num
            else:
                out[k] = v
        else:
            out[k] = v
    return out


def _control_schema(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    if kind == "arm":
        n = int(config.get("num_joints", 6))
        return {
            "writable": True,
            "mode": "joints",
            "num_dofs": n,
            "labels": [f"j{i + 1}" for i in range(n)],
            "unit": "rad",
            "hint": "关节角直接读写（无 scale/offset）",
        }
    if kind == "gripper":
        return {
            "writable": True,
            "mode": "gripper",
            "num_dofs": 1,
            "labels": ["open"],
            "unit": "norm",
            "value_min": 0.0,
            "value_max": 0.637,
            "hint": "夹爪开合直接读写 position_norm（无 scale/offset）",
        }
    return {"writable": False}


def _public_config(cfg: dict[str, Any]) -> dict[str, Any]:
    skip = {"role_serials", "name", "enabled", "kind", "id"}
    return {k: v for k, v in cfg.items() if k not in skip and not str(k).startswith("_")}


def _merged_connect_config(base: Sensor, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    kind = base.kind.value
    coerced = _coerce_overrides(kind, overrides or {})
    return {**dict(base.config), **coerced}


def _pack_sample_response(
    *,
    sensor_id: str,
    kind: str,
    name: str,
    dry_run: bool,
    config_used: dict[str, Any],
    sample: dict[str, Any],
    tick: int = 0,
    session_id: str | None = None,
) -> dict[str, Any]:
    viz = _build_viz(kind, sample, dry_run=dry_run, tick=tick)
    light = {k: v for k, v in sample.items() if k not in ("color", "depth")}
    out: dict[str, Any] = {
        "id": sensor_id,
        "kind": kind,
        "name": name,
        "dry_run": dry_run,
        "config_used": config_used,
        "sample": _jsonable(light),
        "viz": viz,
        "tick": tick,
    }
    if session_id:
        out["session_id"] = session_id
    return out


def _close_session_locked(session_id: str) -> bool:
    sess = _sessions.pop(session_id, None)
    if sess is None:
        return False
    try:
        sess.sensor.close()
    except Exception:  # noqa: BLE001
        pass
    return True


def _close_sessions_for_sensor(sensor_id: str) -> None:
    with _sessions_lock:
        doomed = [sid for sid, s in _sessions.items() if s.sensor_id == sensor_id]
        for sid in doomed:
            _close_session_locked(sid)


def _gripper_probe_script_path(mode: str | None = None) -> Path:
    m = str(mode or "").strip().lower()
    if m == "read":
        return ROOT / "scripts" / "probe_gripper_read_rate.py"
    if m == "write":
        return ROOT / "scripts" / "probe_gripper_write_rate.py"
    # calibrate / init / generic
    return ROOT / "scripts" / "probe_gripper_rate.py"


def _run_probe_script(
    script: Path,
    job: dict[str, Any],
    *,
    timeout_s: float = 180.0,
    fallback_run_job: Any = None,
    thread_name: str = "probe",
) -> dict[str, Any]:
    """
    Start a dedicated probe script on a worker thread and wait for its JSON result.

    Prefer subprocess so probing is isolated from the HTTP worker; fall back to
    an in-process run_job callable in that thread (frozen builds).
    """
    import json
    import os
    import subprocess
    import tempfile

    sensor_id = str(job.get("sensor_id") or "")
    if sensor_id:
        _close_sessions_for_sensor(sensor_id)

    box: dict[str, Any] = {"result": None, "error": None}

    def worker() -> None:
        try:
            if script.is_file() and not getattr(sys, "frozen", False):
                with tempfile.TemporaryDirectory(prefix="sv-probe-") as td:
                    job_path = Path(td) / "job.json"
                    out_path = Path(td) / "out.json"
                    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
                    env = os.environ.copy()
                    pp = [str(SENSORS_SRC), str(ROOT)]
                    if env.get("PYTHONPATH"):
                        pp.append(env["PYTHONPATH"])
                    env["PYTHONPATH"] = os.pathsep.join(pp)
                    proc = subprocess.run(
                        [
                            sys.executable,
                            str(script),
                            "--job",
                            str(job_path),
                            "--out",
                            str(out_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=timeout_s,
                        env=env,
                        cwd=str(ROOT),
                    )
                    raw = ""
                    if out_path.is_file():
                        raw = out_path.read_text(encoding="utf-8")
                    elif proc.stdout.strip():
                        raw = proc.stdout
                    if not raw.strip():
                        box["error"] = (proc.stderr or "").strip() or f"probe script exit {proc.returncode}"
                        return
                    data = json.loads(raw)
                    if proc.returncode != 0 and not data.get("ok"):
                        box["error"] = data.get("error") or (proc.stderr or "").strip() or f"exit {proc.returncode}"
                    box["result"] = data
                    return

            if fallback_run_job is None:
                box["error"] = "probe script missing and no in-process fallback"
                return
            box["result"] = fallback_run_job(job)
        except subprocess.TimeoutExpired:
            box["error"] = f"probe script timed out after {timeout_s:.0f}s"
        except Exception as e:  # noqa: BLE001
            box["error"] = str(e)

    thread = threading.Thread(
        target=worker,
        name=f"{thread_name}-{job.get('mode') or 'x'}-{sensor_id or 'x'}",
        daemon=True,
    )
    thread.start()
    thread.join(timeout=timeout_s + 5.0)
    if thread.is_alive():
        raise HTTPException(status_code=504, detail="probe worker thread still running (timeout)")
    if box["result"] is None:
        raise HTTPException(status_code=500, detail=box["error"] or "probe returned no result")
    result = dict(box["result"])
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or box["error"] or "probe failed")
    return result


def _run_gripper_probe_script(job: dict[str, Any], *, timeout_s: float = 180.0) -> dict[str, Any]:
    from .gripper_rate_probe import run_job as gripper_run_job

    return _run_probe_script(
        _gripper_probe_script_path(str(job.get("mode") or "")),
        job,
        timeout_s=timeout_s,
        fallback_run_job=gripper_run_job,
        thread_name="gripper-probe",
    )


def _gripper_probe_base(sensor_id: str, body: GripperWriteProbeRequest) -> tuple[dict[str, Any], bool]:
    mgr = get_manager()
    if sensor_id not in mgr.ids():
        raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
    base = mgr.get(sensor_id)
    if base.kind.value != "gripper":
        raise HTTPException(status_code=400, detail="probe is for gripper only")
    overrides = _coerce_overrides("gripper", body.config or {})
    merged = {**base.config, **overrides}
    dry_run = mgr.ctx.dry_run if body.dry_run is None else bool(body.dry_run)
    return merged, dry_run


class ReadRateProbeRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool | None = None
    duration_s: float | None = None
    read_duration_s: float | None = None


def _read_rate_probe_base(sensor_id: str, body: ReadRateProbeRequest) -> tuple[Any, dict[str, Any], bool, float]:
    from .read_rate_probe import SUPPORTED_KINDS, default_duration_s

    mgr = get_manager()
    if sensor_id not in mgr.ids():
        raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
    base = mgr.get(sensor_id)
    kind = base.kind.value
    if kind == "arm":
        raise HTTPException(status_code=400, detail="read-rate probe not enabled for arm yet")
    if kind not in SUPPORTED_KINDS:
        raise HTTPException(status_code=400, detail=f"read-rate probe not supported for kind={kind}")
    overrides = _coerce_overrides(kind, body.config or {})
    merged = {**base.config, **overrides}
    dry_run = mgr.ctx.dry_run if body.dry_run is None else bool(body.dry_run)
    duration = body.duration_s if body.duration_s is not None else body.read_duration_s
    if duration is None:
        duration = default_duration_s(kind)
    return base, merged, dry_run, float(duration)


@app.on_event("startup")
def _startup() -> None:
    global _view_cfg, _view_config_path
    info = view_auth.init_auth()
    print(f"[auth] enabled={info.get('enabled')} source={info.get('source')} user={info.get('username')}", flush=True)
    cfg = getattr(app.state, "view_config", None) or str(_view_config_path)
    _view_config_path = Path(cfg)
    _view_cfg = _load_view_cfg(_view_config_path)
    get_manager(reload=True)


@app.middleware("http")
async def _auth_gate(request: Request, call_next):  # type: ignore[no-untyped-def]
    path = request.url.path
    if view_auth.path_requires_auth(path):
        if not view_auth.is_authenticated(request.headers.get("cookie")):
            return JSONResponse(
                {
                    "ok": False,
                    "authRequired": True,
                    "loginPath": "/login",
                    "error": "unauthorized",
                },
                status_code=401,
            )
    return await call_next(request)


@app.on_event("shutdown")
def _shutdown() -> None:
    with _sessions_lock:
        for sid in list(_sessions.keys()):
            _close_session_locked(sid)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    st = view_auth.public_status()
    return {"ok": True, **st}


@app.get("/api/auth/status")
def api_auth_status() -> dict[str, Any]:
    return view_auth.public_status()


@app.get("/api/auth/me")
def api_auth_me(request: Request) -> dict[str, Any]:
    return view_auth.auth_me(request.headers.get("cookie"))


@app.post("/api/auth/login")
def api_auth_login(body: LoginBody) -> JSONResponse:
    out = view_auth.try_login(body.username, body.password)
    set_cookie = out.pop("_set_cookie", None)
    status = 200 if out.get("ok") else 401
    resp = JSONResponse(out, status_code=status)
    if set_cookie:
        resp.headers.append("Set-Cookie", set_cookie)
    return resp


@app.post("/api/auth/logout")
def api_auth_logout(request: Request) -> JSONResponse:
    out = view_auth.auth_logout(request.headers.get("cookie"))
    clear = out.pop("_clear_cookie", None)
    resp = JSONResponse(out)
    if clear:
        resp.headers.append("Set-Cookie", clear)
    return resp


def _require_user(request: Request) -> dict[str, Any]:
    user = view_auth.current_user(request.headers.get("cookie"))
    if not user and view_auth.auth_enabled():
        raise HTTPException(
            status_code=401,
            detail={"ok": False, "authRequired": True, "loginPath": "/login", "error": "unauthorized"},
        )
    return user or {"username": "anonymous", "role": "admin"}


def _require_admin(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    if view_auth.auth_enabled() and not view_auth.is_admin(user.get("username")):
        raise HTTPException(status_code=403, detail="admin required")
    return user


@app.post("/api/auth/password")
def api_change_password(request: Request, body: PasswordChangeBody) -> dict[str, Any]:
    user = _require_user(request)
    try:
        view_auth.change_own_password(user["username"], body.current_password, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@app.get("/api/users")
def api_users_list(request: Request) -> dict[str, Any]:
    _require_admin(request)
    return {"ok": True, "users": view_auth.list_users_public()}


@app.post("/api/users")
def api_users_create(request: Request, body: UserCreateBody) -> dict[str, Any]:
    _require_admin(request)
    try:
        row = view_auth.create_user(body.username, body.password, body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "user": row}


@app.put("/api/users/{username}")
def api_users_update(username: str, request: Request, body: UserUpdateBody) -> dict[str, Any]:
    _require_admin(request)
    try:
        row = view_auth.update_user(
            username,
            role=body.role,
            enabled=body.enabled,
            password=body.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if body.password:
        view_auth.destroy_sessions_for_user(username)
    return {"ok": True, "user": row}


@app.delete("/api/users/{username}")
def api_users_delete(username: str, request: Request) -> dict[str, Any]:
    actor = _require_admin(request)
    try:
        view_auth.delete_user(username, actor=str(actor.get("username") or ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    view_auth.destroy_sessions_for_user(username)
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": _view_cfg.get("title", "sensors-view"),
            "dry_run": bool(_view_cfg.get("dry_run", False)),
            "sensors_config": str(
                _resolve_sensors_config(_view_cfg.get("sensors_config", "sensors/configs/default.yaml"))
            ),
        },
    )


@app.get("/api/meta")
def api_meta() -> dict[str, Any]:
    mgr = get_manager()
    export_dir = load_export_dir()
    return {
        "title": _view_cfg.get("title", "sensors-view"),
        "site": mgr.bundle.site,
        "dry_run": mgr.ctx.dry_run,
        "sensors_config": str(
            _resolve_sensors_config(_view_cfg.get("sensors_config", "sensors/configs/default.yaml"))
        ),
        "device_ids": mgr.ids(),
        "count": len(mgr),
        "export_dir": str(export_dir),
        "export_dir_default": str(default_export_dir()),
    }


@app.get("/api/export")
def api_export_get() -> dict[str, Any]:
    return {
        "dir": str(load_export_dir()),
        "default_dir": str(default_export_dir()),
    }


@app.put("/api/export")
def api_export_put(body: ExportDirBody) -> dict[str, Any]:
    text = (body.dir or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="dir required")
    try:
        path = save_export_dir(Path(text))
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"cannot use dir: {exc}") from exc
    return {"ok": True, "dir": str(path), "default_dir": str(default_export_dir())}


@app.post("/api/export")
def api_export_save(body: ExportSaveBody) -> dict[str, Any]:
    """Queue JSON export on a dedicated background thread (non-blocking)."""
    import copy

    filename = _safe_export_filename(body.filename)
    if body.data is None:
        raise HTTPException(status_code=400, detail="data required")
    directory = _resolve_export_dir(body.dir)
    try:
        target = _resolve_export_target(directory, filename)
        directory.mkdir(parents=True, exist_ok=True)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"cannot use dir: {exc}") from exc

    job_id = uuid.uuid4().hex
    data_copy = copy.deepcopy(body.data)
    persist_dir = bool((body.dir or "").strip())

    with _export_jobs_lock:
        _export_jobs[job_id] = {
            "status": "running",
            "path": str(target),
            "dir": str(directory.resolve()),
            "filename": filename,
            "error": None,
        }

    def _worker() -> None:
        try:
            written = _write_export_json(directory, filename, data_copy)
            if persist_dir:
                try:
                    save_export_dir(directory)
                except OSError:
                    pass
            with _export_jobs_lock:
                job = _export_jobs.get(job_id)
                if job is not None:
                    job.update(status="done", path=str(written), error=None)
        except Exception as exc:  # noqa: BLE001
            with _export_jobs_lock:
                job = _export_jobs.get(job_id)
                if job is not None:
                    job.update(status="error", error=str(exc))

    threading.Thread(target=_worker, name=f"sensors-view-export-{job_id[:8]}", daemon=True).start()
    return {
        "ok": True,
        "job_id": job_id,
        "status": "running",
        "path": str(target),
        "dir": str(directory.resolve()),
        "filename": filename,
    }


@app.get("/api/export/jobs/{job_id}")
def api_export_job(job_id: str) -> dict[str, Any]:
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
        snapshot = dict(job) if job else None
    if not snapshot:
        raise HTTPException(status_code=404, detail="unknown export job")
    return {"ok": True, "job_id": job_id, **snapshot}


@app.post("/api/postprocess")
def api_postprocess(body: PostprocessBody) -> dict[str, Any]:
    """Queue hik-format batch postprocess on a dedicated background thread."""
    from .postprocess import convert_file, list_export_jsons

    directory = _resolve_export_dir(body.dir)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"export dir not found: {directory}")

    try:
        if body.filename:
            name = Path(str(body.filename).replace("\\", "/")).name
            files = [directory / name]
            if not files[0].is_file():
                raise FileNotFoundError(str(files[0]))
        else:
            files = list_export_jsons(directory, seq=(body.seq or "").strip() or None)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not files:
        raise HTTPException(status_code=404, detail="no sensors-view export JSON found")

    out_root = Path(body.out_dir).expanduser().resolve() if (body.out_dir or "").strip() else (directory / "aligned")
    interval = float(body.interval_ms) if body.interval_ms and body.interval_ms > 0 else 200.0
    write_video = bool(body.write_video)

    job_id = uuid.uuid4().hex
    file_list = [str(p.resolve()) for p in files]
    with _postprocess_jobs_lock:
        _postprocess_jobs[job_id] = {
            "status": "running",
            "dir": str(directory.resolve()),
            "out_dir": str(out_root),
            "files": file_list,
            "results": [],
            "error": None,
        }

    def _worker() -> None:
        results: list[dict[str, Any]] = []
        try:
            out_root.mkdir(parents=True, exist_ok=True)
            for fp in file_list:
                results.append(
                    convert_file(
                        Path(fp),
                        out_root,
                        interval_ms=interval,
                        write_video=write_video,
                    )
                )
            with _postprocess_jobs_lock:
                job = _postprocess_jobs.get(job_id)
                if job is not None:
                    job.update(
                        status="done",
                        results=results,
                        path=results[-1]["path"] if results else str(out_root),
                        error=None,
                    )
        except Exception as exc:  # noqa: BLE001
            with _postprocess_jobs_lock:
                job = _postprocess_jobs.get(job_id)
                if job is not None:
                    job.update(status="error", results=results, error=str(exc))

    threading.Thread(target=_worker, name=f"sensors-view-post-{job_id[:8]}", daemon=True).start()
    return {
        "ok": True,
        "job_id": job_id,
        "status": "running",
        "dir": str(directory.resolve()),
        "out_dir": str(out_root),
        "files": file_list,
    }


@app.get("/api/postprocess/jobs/{job_id}")
def api_postprocess_job(job_id: str) -> dict[str, Any]:
    with _postprocess_jobs_lock:
        job = _postprocess_jobs.get(job_id)
        snapshot = dict(job) if job else None
    if not snapshot:
        raise HTTPException(status_code=404, detail="unknown postprocess job")
    return {"ok": True, "job_id": job_id, **snapshot}


@app.get("/api/probe")
def api_probe_get(id: str | None = Query(default=None)) -> dict[str, Any]:
    """Legacy GET probe (YAML defaults only). Prefer POST with saved card configs."""
    return _run_connectivity_probe(only=[id] if id else None, configs={})


@app.post("/api/probe")
def api_probe_post(body: ProbeRequest) -> dict[str, Any]:
    """Per-device connection check using UI/card config overrides."""
    only = [body.id] if body.id else None
    return _run_connectivity_probe(only=only, configs=body.configs or {})


def _run_connectivity_probe(
    *,
    only: list[str] | None,
    configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Per-device connection check for the overview cards.

    Semantics (real hardware, never dry-run):
      ok      — non-dry-run open+read succeeded (same bar as 单次采样)
      offline — open/read failed (or shallow probe says unreachable)
      warn    — connected, but other non-critical anomalies remain
    """
    mgr = get_manager()
    wanted = set(only) if only else None
    bases = [s for s in mgr if wanted is None or s.id in wanted]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    by_id: dict[str, HealthReport] = {}
    config_used: dict[str, dict[str, Any]] = {}
    workers = min(4, max(1, len(bases)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                _connectivity_probe_device,
                b,
                configs.get(b.id) or {},
            ): b.id
            for b in bases
        }
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                report, used_cfg = fut.result()
                by_id[sid] = report
                config_used[sid] = used_cfg
            except Exception as e:  # noqa: BLE001
                by_id[sid] = HealthReport(
                    sensor_id=sid,
                    kind="unknown",
                    status=HealthStatus.OFFLINE,
                    message=str(e),
                    checks=[CheckResult("connect", False, str(e), critical=True)],
                )
                config_used[sid] = {}

    devices: list[dict[str, Any]] = []
    order = only if only else mgr.ids()
    for sid in order:
        r = by_id.get(sid)
        if r is None:
            continue
        d = r.to_dict()
        try:
            sensor = mgr.get(sid)
            d["name"] = sensor.name
            d["config"] = _public_config(config_used.get(sid) or sensor.config)
            d["config_used"] = d["config"]
            d["kind"] = sensor.kind.value
        except KeyError:
            d["name"] = sid
            d["config"] = _public_config(config_used.get(sid) or {})
            d["config_used"] = d["config"]
        devices.append(d)
    return {"site": mgr.bundle.site, "dry_run": mgr.ctx.dry_run, "devices": devices}


def _remap_shallow_status(status: HealthStatus) -> HealthStatus:
    if status == HealthStatus.OK:
        return HealthStatus.OK
    if status == HealthStatus.WARN:
        return HealthStatus.WARN
    return HealthStatus.OFFLINE


def _shallow_connectivity_probe(base: Sensor) -> HealthReport:
    """bus/pipeline: use driver probe() with dry_run forced off; map error→offline."""
    live = type(base)(base.id, dict(base.config), SensorContext(dry_run=False))
    report = live.probe()
    status = _remap_shallow_status(report.status)
    return HealthReport(
        sensor_id=report.sensor_id,
        kind=report.kind,
        status=status,
        message=report.message,
        checks=list(report.checks),
        metrics=dict(report.metrics),
        hints=list(report.hints),
    )


def _live_sample_connectivity_probe(base: Sensor) -> HealthReport:
    """Try the same path as 单次采样: open + read with dry_run=False."""
    sid = base.id
    kind = base.kind.value
    config = dict(base.config)
    checks: list[CheckResult] = []
    metrics: dict[str, Any] = {"method": "open_read"}
    hints: list[str] = []

    _close_sessions_for_sensor(sid)
    sensor = type(base)(sid, config, SensorContext(dry_run=False))
    try:
        sensor.open()
        sample = dict(sensor.read())
        checks.append(CheckResult("connect", True, "open+read ok"))
        metrics["sample_keys"] = [str(k) for k in list(sample.keys())[:16]]
        return HealthReport(
            sensor_id=sid,
            kind=kind,
            status=HealthStatus.OK,
            message="connected",
            checks=checks,
            metrics=metrics,
            hints=hints,
        )
    except Exception as e:  # noqa: BLE001
        err = str(e) or e.__class__.__name__
        checks.append(CheckResult("connect", False, err, critical=True))
        return HealthReport(
            sensor_id=sid,
            kind=kind,
            status=HealthStatus.OFFLINE,
            message=err,
            checks=checks,
            metrics=metrics,
            hints=hints,
        )
    finally:
        try:
            sensor.close()
        except Exception:  # noqa: BLE001
            pass


def _connectivity_probe_device(
    base: Sensor,
    overrides: dict[str, Any] | None = None,
) -> tuple[HealthReport, dict[str, Any]]:
    config = _merged_connect_config(base, overrides)
    merged = type(base)(base.id, config, base.ctx)
    kind = str(merged.kind.value).lower()
    if kind in _SHALLOW_CONNECT_KINDS or kind not in _LIVE_CONNECT_KINDS:
        return _shallow_connectivity_probe(merged), config
    return _live_sample_connectivity_probe(merged), config


@app.get("/api/device/{sensor_id}")
def api_device(sensor_id: str) -> dict[str, Any]:
    mgr = get_manager()
    if sensor_id not in mgr.ids():
        raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
    sensor = mgr.get(sensor_id)
    kind = sensor.kind.value
    return {
        "id": sensor_id,
        "name": sensor.name,
        "kind": kind,
        "config": _public_config(sensor.config),
        "fields": CONNECT_FIELDS.get(kind, []),
        "control": _control_schema(kind, sensor.config),
        # dry-run is UI opt-in; never push server/manager default as checked
        "dry_run_default": False,
    }


@app.post("/api/sample/{sensor_id}")
def api_sample(sensor_id: str, body: SampleRequest) -> dict[str, Any]:
    mgr = get_manager()
    if sensor_id not in mgr.ids():
        raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
    base = mgr.get(sensor_id)
    kind = base.kind.value
    overrides = _coerce_overrides(kind, body.config or {})
    merged = {**base.config, **overrides}
    dry_run = mgr.ctx.dry_run if body.dry_run is None else bool(body.dry_run)
    sensor = type(base)(sensor_id, merged, SensorContext(dry_run=dry_run))
    try:
        sensor.open()
        sample = dict(sensor.read())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        try:
            sensor.close()
        except Exception:  # noqa: BLE001
            pass
    return _pack_sample_response(
        sensor_id=sensor_id,
        kind=kind,
        name=sensor.name,
        dry_run=dry_run,
        config_used=_public_config(merged),
        sample=sample,
        tick=0,
    )


@app.post("/api/session/start/{sensor_id}")
def api_session_start(sensor_id: str, body: SampleRequest) -> dict[str, Any]:
    mgr = get_manager()
    if sensor_id not in mgr.ids():
        raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
    base = mgr.get(sensor_id)
    kind = base.kind.value
    overrides = _coerce_overrides(kind, body.config or {})
    merged = {**base.config, **overrides}
    dry_run = mgr.ctx.dry_run if body.dry_run is None else bool(body.dry_run)
    sensor = type(base)(sensor_id, merged, SensorContext(dry_run=dry_run))
    try:
        sensor.open()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e

    _close_sessions_for_sensor(sensor_id)
    sid = uuid.uuid4().hex
    sess = SampleSession(
        id=sid,
        sensor_id=sensor_id,
        kind=kind,
        name=sensor.name,
        dry_run=dry_run,
        sensor=sensor,
        config_used=_public_config(merged),
    )
    with _sessions_lock:
        _sessions[sid] = sess

    try:
        sample = dict(sensor.read())
    except Exception as e:  # noqa: BLE001
        with _sessions_lock:
            _close_session_locked(sid)
        raise HTTPException(status_code=500, detail=str(e)) from e

    sess.tick = 1
    return _pack_sample_response(
        sensor_id=sensor_id,
        kind=kind,
        name=sess.name,
        dry_run=dry_run,
        config_used=sess.config_used,
        sample=sample,
        tick=sess.tick,
        session_id=sid,
    )


@app.post("/api/session/{session_id}/reset")
def api_session_reset(session_id: str, body: SampleRequest) -> dict[str, Any]:
    """Close and reopen the session sensor with merged form config (e.g. RealSense fps)."""
    mgr = get_manager()
    with _sessions_lock:
        sess = _sessions.get(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="session not found or already stopped")
        kind = sess.kind
        overrides = _coerce_overrides(kind, body.config or {})
        merged = {**sess.config_used, **overrides}
        dry_run = sess.dry_run if body.dry_run is None else bool(body.dry_run)
        try:
            sess.sensor.close()
        except Exception:  # noqa: BLE001
            pass
        base = mgr.get(sess.sensor_id)
        sensor = type(base)(sess.sensor_id, merged, SensorContext(dry_run=dry_run))
        try:
            sensor.open()
            sample = dict(sensor.read())
        except Exception as e:  # noqa: BLE001
            _close_session_locked(session_id)
            raise HTTPException(status_code=500, detail=str(e)) from e
        sess.sensor = sensor
        sess.config_used = _public_config(merged)
        sess.dry_run = dry_run
        sess.tick = 1
        pack = _pack_sample_response(
            sensor_id=sess.sensor_id,
            kind=sess.kind,
            name=sess.name,
            dry_run=sess.dry_run,
            config_used=sess.config_used,
            sample=sample,
            tick=sess.tick,
            session_id=session_id,
        )
    return pack


@app.post("/api/session/{session_id}/tick")
def api_session_tick(session_id: str, body: TickRequest | None = None) -> dict[str, Any]:
    req = body or TickRequest()
    with _sessions_lock:
        sess = _sessions.get(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="session not found or already stopped")
        try:
            command_result: dict[str, Any] | None = None
            if req.command:
                command_result = dict(sess.sensor.write(req.command))
            sample = dict(sess.sensor.read())
        except Exception as e:  # noqa: BLE001
            _close_session_locked(session_id)
            raise HTTPException(status_code=500, detail=str(e)) from e
        sess.tick += 1
        tick = sess.tick
        pack = _pack_sample_response(
            sensor_id=sess.sensor_id,
            kind=sess.kind,
            name=sess.name,
            dry_run=sess.dry_run,
            config_used=sess.config_used,
            sample=sample,
            tick=tick,
            session_id=session_id,
        )
    if command_result is not None:
        pack["command_result"] = command_result
    return pack


@app.post("/api/session/{session_id}/stop")
def api_session_stop(session_id: str) -> dict[str, Any]:
    with _sessions_lock:
        ok = _close_session_locked(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found or already stopped")
    return {"ok": True, "session_id": session_id}


@app.post("/api/session/{session_id}/command")
def api_session_command(session_id: str, body: CommandRequest) -> dict[str, Any]:
    with _sessions_lock:
        sess = _sessions.get(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="session not found or already stopped")
        if not (_control_schema(sess.kind, sess.config_used).get("writable")):
            raise HTTPException(status_code=400, detail=f"{sess.kind} does not support write")
        try:
            result = dict(sess.sensor.write(body.command or {}))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e)) from e
        sid = sess.sensor_id
        kind = sess.kind
    return {
        "ok": True,
        "session_id": session_id,
        "id": sid,
        "kind": kind,
        "command_result": result,
    }


@app.post("/api/probe/{sensor_id}/gripper/calibrate")
def api_probe_gripper_calibrate(sensor_id: str, body: GripperWriteProbeRequest) -> dict[str, Any]:
    """Calibration only — dedicated probe script (mode=calibrate)."""
    merged, dry_run = _gripper_probe_base(sensor_id, body)
    return _run_gripper_probe_script(
        {
            "mode": "calibrate",
            "sensor_id": sensor_id,
            "config": merged,
            "dry_run": dry_run,
        },
        timeout_s=180.0,
    )


@app.post("/api/probe/{sensor_id}/gripper/init")
def api_probe_gripper_init(sensor_id: str, body: GripperWriteProbeRequest) -> dict[str, Any]:
    """Compat: calibrate script then read-rate script (two separate script launches)."""
    cal = api_probe_gripper_calibrate(sensor_id, body)
    cfg = dict(cal.get("config_used") or {})
    # Re-run read with calibrated raw min/max in config.
    body2 = GripperWriteProbeRequest(
        config={**(body.config or {}), **cfg},
        dry_run=body.dry_run,
        read_duration_s=body.read_duration_s,
    )
    read = api_probe_gripper_read(sensor_id, body2)
    return {
        "ok": True,
        "id": sensor_id,
        "kind": "gripper",
        "dry_run": read.get("dry_run"),
        "config_used": cfg or read.get("config_used"),
        "command_result": cal.get("command_result") or {},
        "read_probe": (read.get("read_probe") or {}),
        "via": "calibrate_script+read_script",
    }


@app.post("/api/probe/{sensor_id}/gripper/read")
def api_probe_gripper_read(sensor_id: str, body: GripperWriteProbeRequest) -> dict[str, Any]:
    """Max-read probe only — dedicated read-rate script on a worker thread."""
    merged, dry_run = _gripper_probe_base(sensor_id, body)
    return _run_gripper_probe_script(
        {
            "mode": "read",
            "sensor_id": sensor_id,
            "config": merged,
            "dry_run": dry_run,
            "read_duration_s": float(body.read_duration_s or 10.0),
        },
        timeout_s=60.0,
    )


@app.post("/api/probe/{sensor_id}/gripper/write")
def api_probe_gripper_write(sensor_id: str, body: GripperWriteProbeRequest) -> dict[str, Any]:
    """Max sync write probe via dedicated write-rate script on a worker thread."""
    merged, dry_run = _gripper_probe_base(sensor_id, body)
    return _run_gripper_probe_script(
        {
            "mode": "write",
            "sensor_id": sensor_id,
            "config": merged,
            "dry_run": dry_run,
            "read_hz": float(body.read_hz),
            "write_hz": float(body.write_hz),
            "hz_min": float(body.hz_min),
            "hz_max": float(body.hz_max),
            "value_min": float(body.value_min),
            "value_max": float(body.value_max),
            "baseline_s": float(body.baseline_s),
            "max_duration_s": float(body.max_duration_s),
            "sync_duration_s": float(body.sync_duration_s or 10.0),
        },
        timeout_s=120.0,
    )


@app.post("/api/probe/{sensor_id}/read-rate")
def api_probe_read_rate(sensor_id: str, body: ReadRateProbeRequest) -> dict[str, Any]:
    """Offline max-read probe for non-arm streaming sensors (ft/tactile/realsense/gello/gripper)."""
    from .read_rate_probe import run_job as read_rate_run_job

    base, merged, dry_run, duration = _read_rate_probe_base(sensor_id, body)
    kind = base.kind.value
    # RealSense frame wait can be slow; allow headroom beyond duration.
    timeout_s = max(60.0, duration + 30.0)
    return _run_probe_script(
        ROOT / "scripts" / "probe_read_rate.py",
        {
            "mode": "read",
            "kind": kind,
            "sensor_id": sensor_id,
            "config": merged,
            "dry_run": dry_run,
            "duration_s": duration,
        },
        timeout_s=timeout_s,
        fallback_run_job=read_rate_run_job,
        thread_name="read-rate-probe",
    )


@app.post("/api/command/{sensor_id}")
def api_command(sensor_id: str, body: CommandRequest) -> dict[str, Any]:
    """One-shot open → write → close (for arm/gripper when not in a session)."""
    mgr = get_manager()
    if sensor_id not in mgr.ids():
        raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
    base = mgr.get(sensor_id)
    kind = base.kind.value
    schema = _control_schema(kind, base.config)
    if not schema.get("writable"):
        raise HTTPException(status_code=400, detail=f"{kind} does not support write")
    overrides = _coerce_overrides(kind, body.config or {})
    merged = {**base.config, **overrides}
    dry_run = mgr.ctx.dry_run if body.dry_run is None else bool(body.dry_run)
    sensor = type(base)(sensor_id, merged, SensorContext(dry_run=dry_run))
    try:
        sensor.open()
        result = dict(sensor.write(body.command or {}))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        try:
            sensor.close()
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "id": sensor_id, "kind": kind, "command_result": result}


@app.get("/api/read/{sensor_id}")
def api_read(sensor_id: str) -> dict[str, Any]:
    return api_sample(sensor_id, SampleRequest())


@app.post("/api/reload")
def api_reload() -> dict[str, Any]:
    global _view_cfg
    with _sessions_lock:
        for sid in list(_sessions.keys()):
            _close_session_locked(sid)
    _view_cfg = _load_view_cfg(_view_config_path)
    mgr = get_manager(reload=True)
    return {"ok": True, "count": len(mgr), "site": mgr.bundle.site}


def main(argv: list[str] | None = None) -> None:
    global _view_config_path
    parser = argparse.ArgumentParser(prog="sensors-view")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_VIEW_CFG)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6008)
    args = parser.parse_args(argv)
    if not args.config.is_file():
        raise SystemExit(f"view config missing: {args.config}")
    _view_config_path = args.config.resolve()
    app.state.view_config = str(_view_config_path)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
