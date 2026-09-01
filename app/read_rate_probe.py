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


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    w = idx - lo
    return sorted_vals[lo] * (1.0 - w) + sorted_vals[hi] * w


def _timing_stats(times: list[float]) -> dict[str, Any]:
    if len(times) < 2:
        return {"dt_ms_p50": None, "dt_ms_p95": None, "dt_ms_mean": None}
    dts = sorted((times[i] - times[i - 1]) * 1000.0 for i in range(1, len(times)))
    mean = sum(dts) / len(dts)
    return {
        "dt_ms_p50": None if not dts else round(float(_percentile(dts, 50) or 0.0), 3),
        "dt_ms_p95": None if not dts else round(float(_percentile(dts, 95) or 0.0), 3),
        "dt_ms_mean": round(mean, 3),
    }


def _cap_from_measured(measured: float) -> float:
    return max(0.2, math.floor(float(measured) * 0.95 * 10) / 10)


def probe_read_hz(sensor: Any, *, duration_s: float = 10.0) -> dict[str, Any]:
    """Tight sensor.read() loop; return measured Hz and ×0.95 cap."""
    duration_s = max(0.5, float(duration_s))
    times: list[float] = []
    errors = 0
    last_error: str | None = None
    t0 = time.perf_counter()
    deadline = t0 + duration_s
    while time.perf_counter() < deadline:
        try:
            sensor.read()
            times.append(time.perf_counter())
        except Exception as e:  # noqa: BLE001
            errors += 1
            last_error = str(e)
            if errors >= 8 and len(times) < 3:
                break
    elapsed = max(1e-9, time.perf_counter() - t0)
    measured = _measure_rate_from_times(times)
    stats = _timing_stats(times)
    if measured is None:
        return {
            "ok": False,
            "error": last_error or "read-rate probe failed (too few samples)",
            "samples": len(times),
            "errors": errors,
            "duration_s": round(elapsed, 3),
            "method": "tight_read_loop",
            **stats,
        }
    return {
        "ok": True,
        "samples": len(times),
        "errors": errors,
        "duration_s": round(elapsed, 3),
        "measured_hz": round(measured, 3),
        "read_cap_hz": _cap_from_measured(measured),
        "method": "tight_read_loop",
        "last_error": last_error,
        **stats,
    }


def default_duration_s(kind: str) -> float:
    k = str(kind or "").lower()
    if k == "realsense":
        return 3.0
    if k in ("ft", "gello"):
        return 5.0
    return 10.0


def _prepare_config_for_probe(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    """Kind-specific tweaks so the probe measures bus/stream throughput, not UI pacing."""
    cfg = dict(config)
    if kind == "ft":
        # Prefer short waits so a missing frame fails fast; stream probe counts frames.
        try:
            cur = int(cfg.get("timeout_ms") or 500)
        except (TypeError, ValueError):
            cur = 500
        cfg["timeout_ms"] = max(20, min(cur, 80))
    return cfg


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
    config = _prepare_config_for_probe(kind, dict(job.get("config") or {}))
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
        # Prefer driver-native probe when available (e.g. FT serial frame counting).
        if hasattr(sensor, "probe_max_read_hz") and callable(getattr(sensor, "probe_max_read_hz")):
            read_probe = dict(sensor.probe_max_read_hz(duration_s=duration))
            if read_probe.get("ok") and "read_cap_hz" not in read_probe and read_probe.get("measured_hz"):
                read_probe["read_cap_hz"] = _cap_from_measured(float(read_probe["measured_hz"]))
        else:
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
