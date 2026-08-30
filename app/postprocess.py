"""Convert sensors-view batch JSON → hik_gello data_merge_datapostprocess episode layout.

Output (aligned with parse_pickle_data / __main__ in data_merge_datapostprocess.py):
  {out_dir}/{seq}/
    metadata.json
    steps.json
    rgb_{cam_name}_{i}.jpg
  {out_dir}/video/{seq}.mp4   (optional, skipped if OpenCV missing)
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

# Role / device-id → hik camera_name_refator style names
CAMERA_NAME_MAP: dict[str, str] = {
    "left": "rear_left_1",
    "right": "rear_right_1",
    "middle": "top",
    "rs-left": "rear_left_1",
    "rs-right": "rear_right_1",
    "rs-middle": "top",
    "top": "top",
    "wrist": "wrist_1",
    "wrist_1": "wrist_1",
    "wrist_2": "wrist_2",
}


def _iso_to_ms(t: Any) -> float | None:
    if t is None:
        return None
    if isinstance(t, (int, float)):
        v = float(t)
        return v * 1000.0 if v < 1e12 else v
    s = str(t).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp() * 1000.0
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def _decode_data_url(src: str | None) -> np.ndarray | None:
    if not src or not isinstance(src, str):
        return None
    raw = src
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        buf = base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        return None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(buf)).convert("RGB")
        rgb = np.asarray(img, dtype=np.uint8)
        # hik / OpenCV expect BGR for imwrite; we write via Pillow RGB JPEG
        return rgb
    except Exception:  # noqa: BLE001
        return None


def _save_jpeg(path: Path, rgb: np.ndarray, *, quality: int = 90) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, format="JPEG", quality=quality)


def _joints_from_frame(frame: dict[str, Any]) -> list[float] | None:
    sample = frame.get("sample") or {}
    kind = frame.get("kind") or ""
    for key in ("joints", "joints_rad", "arm_joints"):
        v = sample.get(key)
        if isinstance(v, list) and v:
            return [float(x) for x in v]
    raw = frame.get("raw")
    if isinstance(raw, list) and raw and kind in ("arm", "gello", ""):
        return [float(x) for x in raw]
    display = frame.get("display")
    if isinstance(display, list) and display and kind in ("arm", "gello", ""):
        return [float(x) for x in display]
    viz = frame.get("viz") or {}
    for ch in viz.get("charts") or []:
        if ch.get("type") == "bars" and isinstance(ch.get("values"), list) and ch["values"]:
            return [float(x) for x in ch["values"]]
    return None


def _gripper_from_frame(frame: dict[str, Any]) -> float:
    sample = frame.get("sample") or {}
    if sample.get("position_norm") is not None:
        try:
            return float(sample["position_norm"])
        except (TypeError, ValueError):
            pass
    display = frame.get("display")
    if isinstance(display, list) and display:
        try:
            return float(display[0])
        except (TypeError, ValueError):
            pass
    viz = frame.get("viz") or {}
    for ch in viz.get("charts") or []:
        if ch.get("type") == "gauge" and ch.get("value") is not None:
            try:
                return float(ch["value"])
            except (TypeError, ValueError):
                pass
    return 0.0


def _color_from_frame(frame: dict[str, Any]) -> np.ndarray | None:
    viz = frame.get("viz") or {}
    for im in viz.get("images") or []:
        title = str(im.get("title") or "").lower()
        if title.startswith("depth"):
            continue
        rgb = _decode_data_url(im.get("src"))
        if rgb is not None:
            return rgb
    for im in viz.get("images") or []:
        rgb = _decode_data_url(im.get("src"))
        if rgb is not None:
            return rgb
    return None


def _cam_logical_name(device_id: str, meta: dict[str, Any], frame0: dict[str, Any] | None) -> str:
    sample = (frame0 or {}).get("sample") or {}
    role = str(sample.get("role") or meta.get("role") or "").strip().lower()
    if role and role in CAMERA_NAME_MAP:
        return CAMERA_NAME_MAP[role]
    did = str(device_id).strip().lower()
    if did in CAMERA_NAME_MAP:
        return CAMERA_NAME_MAP[did]
    serial = str(sample.get("serial") or "").strip()
    if serial and serial in CAMERA_NAME_MAP:
        return CAMERA_NAME_MAP[serial]
    # fallback: sanitize id
    safe = re.sub(r"[^\w]+", "_", did).strip("_") or "cam"
    return safe


def _default_intrinsic(w: int = 1280, h: int = 720) -> list[list[float]]:
    fx = fy = float(max(w, h))
    return [[fx, 0.0, w / 2.0], [0.0, fy, h / 2.0], [0.0, 0.0, 1.0]]


def _eye4() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _nearest(frames: list[dict[str, Any]], t_ms: float) -> dict[str, Any] | None:
    if not frames:
        return None
    return min(frames, key=lambda f: abs(float(f["_t_ms"]) - t_ms))


def _stamp_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fr in frames or []:
        t = _iso_to_ms(fr.get("t"))
        if t is None:
            continue
        item = dict(fr)
        item["_t_ms"] = t
        out.append(item)
    out.sort(key=lambda x: x["_t_ms"])
    return out


def _sample_timestamps(times_ms: list[float], interval_ms: float) -> list[float]:
    if not times_ms:
        return []
    sampled = [times_ms[0]]
    last = times_ms[0]
    for ts in times_ms:
        if ts >= last + interval_ms:
            sampled.append(ts)
            last = ts
    return sampled


def _pose_xyz_rpy(joints6: list[float]) -> list[float]:
    """Placeholder Cartesian pose when robot FK is unavailable (zeros translation + joint-derived stub)."""
    # Keep structure identical to hik steps; values are placeholders without RL_ROBOT.
    j = list(joints6) + [0.0] * 6
    return [0.0, 0.0, 0.0, float(j[3]), float(j[4]), float(j[5])]


def _build_metadata(cam_names: list[str], intrinsics: dict[str, list], extrinsics: dict[str, list]) -> dict[str, Any]:
    sensor_list: list[str] = []
    for name in cam_names:
        sensor_list.append(f"rgb_{name}")
        sensor_list.append(f"d_{name}")
    meta: dict[str, Any] = {
        "name": "hik_ebai_data",
        "robot": "ur5e",
        "task_morphology": "single_arm",
        "dof": 6,
        "sensor_list": sensor_list,
        "rgb_camera_num": len(cam_names),
        "depth_camera_num": len(cam_names),
        "natural_language": "",
        "extrinsic_matrix": {},
        "intrinsic_matrix": {},
        "source": "sensors-view-postprocess",
    }
    for name in cam_names:
        K = intrinsics.get(name) or _default_intrinsic()
        E = extrinsics.get(name) or _eye4()
        meta["extrinsic_matrix"][f"rgb_{name}"] = E
        meta["extrinsic_matrix"][f"d_{name}"] = E
        meta["intrinsic_matrix"][f"rgb_{name}"] = K
        meta["intrinsic_matrix"][f"d_{name}"] = K
    return meta


def convert_batch_json(
    data: dict[str, Any],
    out_root: Path,
    *,
    seq: str | None = None,
    interval_ms: float = 200.0,
    write_video: bool = False,
) -> dict[str, Any]:
    """Convert one sensors-view export JSON object into hik episode folder."""
    streams: dict[str, list] = dict(data.get("streams") or {})
    devices_meta = {d["id"]: d for d in (data.get("devices") or []) if isinstance(d, dict) and d.get("id")}
    seq_text = str(seq or data.get("seq") or "0").strip() or "0"
    safe_seq = re.sub(r"[^\w.\-]+", "_", seq_text)

    cam_streams: dict[str, list[dict[str, Any]]] = {}
    cam_names_order: list[str] = []
    arm_frames: list[dict[str, Any]] = []
    action_frames: list[dict[str, Any]] = []
    grip_frames: list[dict[str, Any]] = []

    for dev_id, frames in streams.items():
        stamped = _stamp_frames(frames if isinstance(frames, list) else [])
        if not stamped:
            continue
        kind = str(stamped[0].get("kind") or devices_meta.get(dev_id, {}).get("kind") or "")
        if kind == "realsense":
            name = _cam_logical_name(dev_id, devices_meta.get(dev_id, {}), stamped[0])
            # keep first occurrence order; avoid overwrite of same logical name
            key = name
            n = 2
            while key in cam_streams:
                key = f"{name}_{n}"
                n += 1
            cam_streams[key] = stamped
            cam_names_order.append(key)
        elif kind == "arm":
            arm_frames.extend(stamped)
        elif kind == "gello":
            action_frames.extend(stamped)
        elif kind == "gripper":
            grip_frames.extend(stamped)

    arm_frames.sort(key=lambda x: x["_t_ms"])
    action_frames.sort(key=lambda x: x["_t_ms"])
    grip_frames.sort(key=lambda x: x["_t_ms"])

    if not cam_streams and not arm_frames:
        raise ValueError("no camera or arm streams to postprocess")

    # Primary camera for time base (prefer rear_left / left / first)
    primary_name = None
    for prefer in ("rear_left_1", "top", "rear_right_1"):
        if prefer in cam_streams:
            primary_name = prefer
            break
    if primary_name is None:
        primary_name = cam_names_order[0] if cam_names_order else None

    if primary_name is not None:
        master_times = [f["_t_ms"] for f in cam_streams[primary_name]]
    elif arm_frames:
        master_times = [f["_t_ms"] for f in arm_frames]
    else:
        raise ValueError("empty timeline")

    sampled_times = _sample_timestamps(master_times, interval_ms)
    if not sampled_times:
        raise ValueError("no sampled timestamps")

    aligned: list[dict[str, Any]] = []
    last_joints = [0.0] * 6
    for t_ms in sampled_times:
        joints = [0.0] * 6
        grip = 0.0
        arm_fr = _nearest(arm_frames, t_ms)
        if arm_fr is not None:
            j = _joints_from_frame(arm_fr) or []
            joints = (j + [0.0] * 6)[:6]
        grip_fr = _nearest(grip_frames, t_ms)
        if grip_fr is not None:
            grip = _gripper_from_frame(grip_fr)
        elif arm_fr is not None:
            jfull = _joints_from_frame(arm_fr) or []
            if len(jfull) >= 7:
                grip = float(jfull[6])

        # drop near-static frames when arm stream exists (same as hik)
        if arm_frames and aligned and sum(abs(a - b) for a, b in zip(joints, last_joints)) < 0.001:
            continue
        last_joints = list(joints)

        action_joints = list(joints)
        act_fr = _nearest(action_frames, t_ms) if action_frames else None
        if act_fr is not None:
            aj = _joints_from_frame(act_fr) or []
            if aj:
                action_joints = (aj + [0.0] * 6)[:6]

        cams: dict[str, np.ndarray | None] = {}
        for cname, cframes in cam_streams.items():
            fr = _nearest(cframes, t_ms)
            cams[cname] = _color_from_frame(fr) if fr else None

        robot_state = joints[:6] + [grip]
        action_state = (action_joints[:6] + [grip])[:7]
        aligned.append(
            {
                "timestamp": t_ms,
                "robot_state": robot_state,
                "action_state": action_state,
                "cameras": cams,
            }
        )

    if not aligned:
        raise ValueError("alignment produced 0 frames (check streams / motion filter)")

    img_path = out_root / safe_seq
    img_path.mkdir(parents=True, exist_ok=True)

    intrinsics: dict[str, list] = {}
    extrinsics: dict[str, list] = {}
    for cname in cam_names_order:
        # infer size from first available image
        w, h = 1280, 720
        for fr in cam_streams.get(cname, []):
            rgb = _color_from_frame(fr)
            if rgb is not None:
                h, w = int(rgb.shape[0]), int(rgb.shape[1])
                break
        intrinsics[cname] = _default_intrinsic(w, h)
        extrinsics[cname] = _eye4()

    metadata = _build_metadata(cam_names_order, intrinsics, extrinsics)

    steps: dict[str, Any] = {
        "actions": {
            "cartesian_position": [],
            "gripper_position": [[]],
        },
        "observations": {
            "cartesian_position": [],
            "joint_position": [],
            "gripper_position": [[]],
        },
    }

    n = len(aligned)
    for i, frame in enumerate(aligned):
        joints6 = list(frame["robot_state"][:6])
        grip = float(frame["robot_state"][-1]) if len(frame["robot_state"]) > 6 else 0.0
        steps["observations"]["joint_position"].append(joints6)
        steps["observations"]["gripper_position"][0].append(grip)
        cur_cart = _pose_xyz_rpy(joints6)
        steps["observations"]["cartesian_position"].append(cur_cart)

        if i + 1 < n:
            nxt = aligned[i + 1]["robot_state"]
            nxt_joints = list(nxt[:6])
            nxt_grip = float(nxt[-1]) if len(nxt) > 6 else 0.0
            nxt_cart = _pose_xyz_rpy(nxt_joints)
            # delta xyz + rpy (placeholder FK → often near-zero)
            delta = [nxt_cart[k] - cur_cart[k] for k in range(6)]
            steps["actions"]["cartesian_position"].append(delta)
            steps["actions"]["gripper_position"][0].append(nxt_grip)
        else:
            steps["actions"]["cartesian_position"].append([0.0] * 6)
            steps["actions"]["gripper_position"][0].append(0.0)

        for cname in cam_names_order:
            rgb = frame["cameras"].get(cname)
            if rgb is None:
                continue
            _save_jpeg(img_path / f"rgb_{cname}_{i}.jpg", rgb)

    (img_path / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (img_path / "steps.json").write_text(
        json.dumps(steps, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    video_path = None
    if write_video and cam_names_order:
        video_path = _try_write_video(out_root / "video", safe_seq, aligned, cam_names_order)

    return {
        "ok": True,
        "seq": safe_seq,
        "frames": n,
        "cameras": cam_names_order,
        "path": str(img_path.resolve()),
        "metadata": str((img_path / "metadata.json").resolve()),
        "steps": str((img_path / "steps.json").resolve()),
        "video": str(video_path) if video_path else None,
        "interval_ms": interval_ms,
        "note": "cartesian_position uses placeholder FK (no RL_ROBOT); joints/images follow hik layout",
    }


def _try_write_video(
    video_dir: Path,
    seq: str,
    aligned: list[dict[str, Any]],
    cam_names: list[str],
) -> Path | None:
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    video_dir.mkdir(parents=True, exist_ok=True)
    out = video_dir / f"{seq}.mp4"
    # pick first available frame size
    sample = None
    for fr in aligned:
        for c in cam_names:
            im = fr["cameras"].get(c)
            if im is not None:
                sample = im
                break
        if sample is not None:
            break
    if sample is None:
        return None
    h, w = sample.shape[:2]
    cols = min(3, len(cam_names)) or 1
    rows = int(math.ceil(len(cam_names) / cols))
    writer = cv2.VideoWriter(
        str(out),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5,
        (w * cols, h * rows),
    )
    if not writer.isOpened():
        return None
    for fr in aligned:
        tiles = []
        for c in cam_names:
            im = fr["cameras"].get(c)
            if im is None:
                im = np.zeros((h, w, 3), dtype=np.uint8)
            elif im.shape[0] != h or im.shape[1] != w:
                im = cv2.resize(im, (w, h))
            tiles.append(cv2.cvtColor(im, cv2.COLOR_RGB2BGR))
        while len(tiles) < rows * cols:
            tiles.append(np.zeros((h, w, 3), dtype=np.uint8))
        row_imgs = []
        for r in range(rows):
            row_imgs.append(cv2.hconcat(tiles[r * cols : (r + 1) * cols]))
        writer.write(cv2.vconcat(row_imgs))
    writer.release()
    return out.resolve()


def convert_file(
    json_path: Path,
    out_root: Path | None = None,
    *,
    interval_ms: float = 200.0,
    write_video: bool = False,
) -> dict[str, Any]:
    json_path = json_path.resolve()
    if not json_path.is_file():
        raise FileNotFoundError(str(json_path))
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("export JSON root must be an object")
    root = out_root.resolve() if out_root else (json_path.parent / "aligned")
    root.mkdir(parents=True, exist_ok=True)
    result = convert_batch_json(
        data,
        root,
        seq=str(data.get("seq") or json_path.stem),
        interval_ms=interval_ms,
        write_video=write_video,
    )
    result["source"] = str(json_path)
    result["out_root"] = str(root)
    return result


def list_export_jsons(directory: Path, seq: str | None = None) -> list[Path]:
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"not a directory: {directory}")
    if seq:
        safe = re.sub(r"[^\w.\-]+", "_", str(seq).strip())
        candidates = [
            directory / f"sensors-view-{safe}.json",
            directory / f"{safe}.json",
            directory / safe,
        ]
        found = [p for p in candidates if p.is_file()]
        if found:
            return found[:1]
        # fallback: any file containing seq
        hits = sorted(directory.glob(f"*{safe}*.json"))
        if hits:
            return [hits[0]]
        raise FileNotFoundError(f"no export JSON for seq={seq!r} under {directory}")
    files = sorted(directory.glob("sensors-view-*.json"))
    if not files:
        files = sorted(p for p in directory.glob("*.json") if p.is_file())
    return files
