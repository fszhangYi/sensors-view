"""Generic offline max-read-rate probe (non-arm sensors).

Run standalone:
  python -m app.read_rate_probe --job job.json --out out.json

Invoked by sensors-view on a worker thread / subprocess; HTTP only waits for JSON.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

# Kinds that expose a meaningful streaming read() for rate probing.
# arm: deferred per product request. pipeline/bus: not high-rate sample streams.
SUPPORTED_KINDS = frozenset({"ft", "tactile", "realsense", "gello", "gripper"})
EXCLUDED_KINDS = frozenset({"arm", "pipeline", "bus"})


def _ensure_sensors_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    sensors_src = root / "sensors" / "src"
    if sensors_src.is_dir() and str(sensors_src) not in sys.path:
        sys.path.insert(0, str(sensors_src))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _measure_rate_from_times(times: list[float]) -> float | None:
    if len(times) < 3:
        return None
    span = times[-1] - times[0]
    if span <= 0:
        return None
    return (len(times) - 1) / span


def probe_read_hz(sensor: Any, *, duration_s: float = 10.0) -> dict[str, Any]:
    """Tight sensor.read() loop; return measured Hz and ×0.95 cap."""
    duration_s = max(0.5, float(duration_s))
    times: list[float] = []
    errors = 0
    last_error: str | None = None
    deadline = time.perf_counter() + duration_s
    while time.perf_counter() < deadline:
        try:
            sensor.read()
            times.append(time.perf_counter())
        except Exception as e:  # noqa: BLE001
            errors += 1
            last_error = str(e)
            if errors >= 5 and len(times) < 3:
                break
    measured = _measure_rate_from_times(times)
    if measured is None:
        return {
            "ok": False,
            "error": last_error or "read-rate probe failed (too few samples)",
            "samples": len(times),
            "errors": errors,
            "duration_s": round(duration_s, 3),
        }
    cap = max(0.2, math.floor(measured * 0.95 * 10) / 10)
    return {
        "ok": True,
        "samples": len(times),
        "errors": errors,
        "duration_s": round(duration_s, 3),
        "measured_hz": round(measured, 3),
        "read_cap_hz": cap,
    }


def default_duration_s(kind: str) -> float:
    k = str(kind or "").lower()
    if k == "realsense":
        return 3.0
    return 10.0


def _open_sensor(sensor_id: str, kind: str, config: dict[str, Any], dry_run: bool) -> Any:
    _ensure_sensors_path()
    from sensors.core.base import SensorContext
    from sensors.core.registry import get_sensor_class
    from sensors.drivers import load_all_drivers

    load_all_drivers()
    cls = get_sensor_class(kind)
    sensor = cls(sensor_id, config, SensorContext(dry_run=bool(dry_run)))
    sensor.open()
    return sensor


def _hardware_fps_cap(kind: str, config: dict[str, Any]) -> float | None:
    if str(kind).lower() != "realsense":
        return None
    for key in ("fps", "framerate", "frame_rate"):
        if key in config and config[key] is not None:
            try:
                return float(config[key])
            except (TypeError, ValueError):
                pass
    return None


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    kind = str(job.get("kind") or "").strip().lower()
    sensor_id = str(job.get("sensor_id") or "sensor")
    config = dict(job.get("config") or {})
    dry_run = bool(job.get("dry_run", False))

    if not kind:
        return {"ok": False, "error": "kind required", "id": sensor_id}
    if kind in EXCLUDED_KINDS or kind not in SUPPORTED_KINDS:
        return {
            "ok": False,
            "error": f"read-rate probe not supported for kind={kind!r}",
            "id": sensor_id,
            "kind": kind,
        }

    duration = float(job.get("duration_s") or job.get("read_duration_s") or default_duration_s(kind))
    sensor = None
    try:
        sensor = _open_sensor(sensor_id, kind, config, dry_run)
        read_probe = probe_read_hz(sensor, duration_s=duration)
        if read_probe.get("ok"):
            hw = _hardware_fps_cap(kind, config)
            if hw is not None and hw > 0:
                cap = min(float(read_probe["read_cap_hz"]), math.floor(hw * 10) / 10)
                read_probe = {**read_probe, "read_cap_hz": cap, "hardware_fps_cap": hw}
        return {
            "ok": bool(read_probe.get("ok")),
            "id": sensor_id,
            "kind": kind,
            "dry_run": dry_run,
            "config_used": config,
            "read_probe": read_probe,
            "via": "read_rate_probe_script",
            "mode": "read",
            "error": read_probe.get("error"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "id": sensor_id, "kind": kind}
    finally:
        if sensor is not None:
            try:
                sensor.close()
            except Exception:  # noqa: BLE001
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generic sensor read-rate probe")
    parser.add_argument("--job", type=Path, help="Job JSON file")
    parser.add_argument("--out", type=Path, help="Write result JSON here")
    parser.add_argument("--stdin", action="store_true", help="Read job JSON from stdin")
    args = parser.parse_args(argv)

    if args.stdin:
        job = json.load(sys.stdin)
    elif args.job:
        job = json.loads(args.job.read_text(encoding="utf-8"))
    else:
        parser.error("provide --job or --stdin")
        return 2

    result = run_job(job)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
