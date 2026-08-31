"""Dedicated gripper rate-probe script (read / write / init+read).

Run standalone:
  python -m app.gripper_rate_probe --job job.json --out out.json

Or invoked by sensors-view in a worker thread; the HTTP API only waits and returns the JSON result.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any


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


def _open_gripper(sensor_id: str, config: dict[str, Any], dry_run: bool) -> Any:
    _ensure_sensors_path()
    from sensors.core.base import SensorContext
    from sensors.drivers.gripper.dh_ag95 import DhAg95Sensor

    sensor = DhAg95Sensor(sensor_id, config, SensorContext(dry_run=bool(dry_run)))
    sensor.open()
    return sensor


def probe_read_hz(sensor: Any, *, duration_s: float = 10.0) -> dict[str, Any]:
    duration_s = max(0.5, float(duration_s))
    times: list[float] = []
    errors = 0
    deadline = time.perf_counter() + duration_s
    while time.perf_counter() < deadline:
        try:
            sensor.read()
            times.append(time.perf_counter())
        except Exception:  # noqa: BLE001
            errors += 1
            if errors >= 5 and len(times) < 3:
                break
    measured = _measure_rate_from_times(times)
    if measured is None:
        return {
            "ok": False,
            "error": "read-rate probe failed (too few samples)",
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


def probe_write_hz(
    sensor: Any,
    *,
    read_hz: float,
    write_hz: float,
    hz_min: float,
    hz_max: float,
    value_min: float = 0.0,
    value_max: float = 0.637,
    baseline_s: float = 1.5,
    max_duration_s: float = 25.0,
    sync_duration_s: float | None = None,
) -> dict[str, Any]:
    """Measure max 1:1 sync rate: each cycle is random write then read (same bus).

    The old paced dual-timer design reported *commanded* write_hz (often the UI
    ceiling, e.g. 40) while reads were only scheduled at the already-capped read
    rate — so "max sync write" could vastly exceed max read. That is wrong.

    Here we hammer write→read pairs and report the measured cycle Hz (×0.95).
    """
    _ = read_hz, write_hz  # kept for API compat; sync probe does not pace by them
    hz_min = max(0.2, float(hz_min))
    hz_max = max(hz_min, float(hz_max))
    lo = float(value_min)
    hi = float(value_max)
    if hi < lo:
        lo, hi = hi, lo
    baseline_s = max(0.5, float(baseline_s))
    sync_duration_s = float(sync_duration_s if sync_duration_s is not None else min(10.0, float(max_duration_s)))
    sync_duration_s = max(3.0, min(float(max_duration_s), sync_duration_s))

    # Short read-only baseline for comparison / sanity cap.
    baseline = probe_read_hz(sensor, duration_s=baseline_s)
    baseline_read_hz = baseline.get("measured_hz") if baseline.get("ok") else None

    times: list[float] = []
    write_ok = 0
    write_fail = 0
    read_fail = 0
    t_start = time.perf_counter()
    deadline = t_start + sync_duration_s
    while time.perf_counter() < deadline:
        target = lo + random.random() * (hi - lo) if hi > lo else lo
        try:
            result = dict(sensor.write({"position_norm": target, "wait_ms": 0}))
            ok = bool(result.get("ok", True)) and not result.get("error")
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            write_fail += 1
            if write_fail >= 8 and write_ok < 3:
                break
            continue
        write_ok += 1
        try:
            sensor.read()
            times.append(time.perf_counter())
        except Exception:  # noqa: BLE001
            read_fail += 1
            if read_fail >= 8 and len(times) < 3:
                break

    measured = _measure_rate_from_times(times)
    finish_reason = "measured"
    if measured is None:
        return {
            "ok": False,
            "error": "sync write-rate probe failed (too few successful write→read cycles)",
            "finish_reason": "too_few_samples",
            "duration_s": round(time.perf_counter() - t_start, 3),
            "baseline_read_hz": None if baseline_read_hz is None else round(float(baseline_read_hz), 3),
            "read_samples": 0,
            "write_samples": write_ok,
            "write_fail": write_fail,
            "read_fail": read_fail,
            "max_sync_write_hz": None,
        }

    # Margin + clamp to UI bounds; never claim sync faster than read-only baseline.
    cap = max(0.2, math.floor(measured * 0.95 * 10) / 10)
    if baseline_read_hz is not None and baseline_read_hz > 0:
        cap = min(cap, math.floor(float(baseline_read_hz) * 0.95 * 10) / 10)
    cap = min(hz_max, max(hz_min, cap))
    if abs(cap - hz_max) < 0.05 and measured * 0.95 >= hz_max - 0.05:
        finish_reason = "ceiling"

    return {
        "ok": True,
        "finish_reason": finish_reason,
        "duration_s": round(time.perf_counter() - t_start, 3),
        "sync_duration_s": round(sync_duration_s, 3),
        "read_hz": None,
        "write_hz_final": round(cap, 3),
        "read_measured_hz": None if baseline_read_hz is None else round(float(baseline_read_hz), 3),
        "write_measured_hz": round(measured, 3),
        "baseline_read_hz": None if baseline_read_hz is None else round(float(baseline_read_hz), 3),
        "max_sync_write_hz": round(cap, 3),
        "read_samples": len(times),
        "write_samples": write_ok,
        "write_fail": write_fail,
        "read_fail": read_fail,
    }


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    """Execute one probe job. Called from a worker thread or CLI."""
    mode = str(job.get("mode") or "").strip().lower()
    sensor_id = str(job.get("sensor_id") or "gripper")
    config = dict(job.get("config") or {})
    dry_run = bool(job.get("dry_run", False))

    sensor = None
    try:
        sensor = _open_gripper(sensor_id, config, dry_run)
        if mode in ("calibrate", "init"):
            # "init" kept as alias for calibrate-only; read probe is a separate script run.
            calibrate = dict(sensor.write({"calibrate": True}))
            if not calibrate.get("ok", True):
                return {
                    "ok": False,
                    "error": calibrate.get("error") or "calibration failed",
                    "command_result": calibrate,
                }
            cfg_out = {
                **config,
                **{
                    k: calibrate[k]
                    for k in ("position_raw_min", "position_raw_max")
                    if calibrate.get(k) is not None
                },
            }
            out = {
                "ok": True,
                "id": sensor_id,
                "kind": "gripper",
                "dry_run": dry_run,
                "config_used": cfg_out,
                "command_result": calibrate,
                "via": "gripper_rate_probe_script",
                "mode": "calibrate",
            }
            # Legacy: mode=init may still request an embedded read probe.
            if mode == "init" and bool(job.get("embed_read_probe")):
                read_probe = probe_read_hz(sensor, duration_s=float(job.get("read_duration_s") or 10.0))
                out["read_probe"] = read_probe
                if not read_probe.get("ok"):
                    out["ok"] = False
                    out["error"] = read_probe.get("error") or "read probe failed"
            return out

        if mode == "write":
            init = dict(sensor.write({"initialize": True}))
            write_probe = probe_write_hz(
                sensor,
                read_hz=float(job.get("read_hz") or 8),
                write_hz=float(job.get("write_hz") or 8),
                hz_min=float(job.get("hz_min") or 1),
                hz_max=float(job.get("hz_max") or 200),
                value_min=float(job.get("value_min") or 0.0),
                value_max=float(job.get("value_max") or 0.637),
                baseline_s=float(job.get("baseline_s") or 1.5),
                max_duration_s=float(job.get("max_duration_s") or 25.0),
                sync_duration_s=float(job["sync_duration_s"]) if job.get("sync_duration_s") is not None else 10.0,
            )
            return {
                "ok": True,
                "id": sensor_id,
                "kind": "gripper",
                "dry_run": dry_run,
                "config_used": config,
                "init_result": init,
                "write_probe": write_probe,
                "via": "gripper_rate_probe_script",
                "mode": "write",
            }

        if mode == "read":
            # Optional: ensure Modbus init before hammering reads on live hardware.
            if not dry_run:
                try:
                    sensor.write({"initialize": True})
                except Exception:  # noqa: BLE001
                    pass
            read_probe = probe_read_hz(sensor, duration_s=float(job.get("read_duration_s") or 10.0))
            return {
                "ok": bool(read_probe.get("ok")),
                "id": sensor_id,
                "kind": "gripper",
                "dry_run": dry_run,
                "config_used": config,
                "read_probe": read_probe,
                "via": "gripper_rate_probe_script",
                "mode": "read",
                "error": read_probe.get("error"),
            }

        return {"ok": False, "error": f"unknown mode: {mode}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "id": sensor_id, "kind": "gripper"}
    finally:
        if sensor is not None:
            try:
                sensor.close()
            except Exception:  # noqa: BLE001
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gripper rate probe script")
    parser.add_argument("--job", type=Path, help="Job JSON file")
    parser.add_argument("--out", type=Path, help="Write result JSON here (also printed)")
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
