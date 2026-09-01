"""Dedicated gripper rate-probe script (read / write / calibrate) via sensors SDK.

Run standalone:
  python -m app.gripper_rate_probe --job job.json --out out.json

Or invoked by sensors-view in a worker thread; the HTTP API only waits and returns the JSON result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .read_rate_probe import (
    MIN_PROBE_DURATION_S,
    attach_process_from_probe,
    resolve_probe_duration,
    run_sdk_read_probe,
)


def _ensure_sensors_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    sensors_src = root / "sensors" / "src"
    if sensors_src.is_dir() and str(sensors_src) not in sys.path:
        sys.path.insert(0, str(sensors_src))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _open_gripper(sensor_id: str, config: dict[str, Any], dry_run: bool) -> Any:
    _ensure_sensors_path()
    from sensors.core.base import SensorContext
    from sensors.drivers.gripper.dh_ag95 import DhAg95Sensor

    sensor = DhAg95Sensor(sensor_id, config, SensorContext(dry_run=bool(dry_run)))
    sensor.open()
    return sensor


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    """Execute one probe job. Called from a worker thread or CLI."""
    mode = str(job.get("mode") or "").strip().lower()
    sensor_id = str(job.get("sensor_id") or "gripper")
    config = dict(job.get("config") or {})
    dry_run = bool(job.get("dry_run", False))
    read_duration_s = resolve_probe_duration(job.get("read_duration_s"), kind="gripper")

    sensor = None
    try:
        sensor = _open_gripper(sensor_id, config, dry_run)
        if mode in ("calibrate", "init"):
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
            if mode == "init" and bool(job.get("embed_read_probe")):
                if not dry_run:
                    try:
                        sensor.initialize()
                    except Exception:  # noqa: BLE001
                        pass
                read_probe = attach_process_from_probe(
                    run_sdk_read_probe(sensor, duration_s=read_duration_s, kind="gripper", config=cfg_out),
                    kind="gripper",
                )
                out["read_probe"] = read_probe
                if not read_probe.get("ok"):
                    out["ok"] = False
                    out["error"] = read_probe.get("error") or "read probe failed"
            return out

        if mode == "write":
            init = dict(sensor.initialize())
            sync_duration_s = resolve_probe_duration(
                job.get("sync_duration_s") if job.get("sync_duration_s") is not None else job.get("max_duration_s"),
                kind="gripper",
            )
            write_probe = dict(
                sensor.probe_max_sync_write_hz(
                    duration_s=sync_duration_s,
                    baseline_s=float(job.get("baseline_s") or 1.5),
                    value_min=float(job.get("value_min") or 0.0),
                    value_max=float(job.get("value_max") or 0.637),
                    hz_min=float(job.get("hz_min") or 1.0),
                    hz_max=float(job.get("hz_max") or 200.0),
                )
            )
            write_probe = attach_process_from_probe(write_probe, kind="gripper")
            return {
                "ok": bool(write_probe.get("ok")),
                "id": sensor_id,
                "kind": "gripper",
                "dry_run": dry_run,
                "config_used": config,
                "init_result": init,
                "write_probe": write_probe,
                "via": "gripper_rate_probe_script",
                "mode": "write",
                "error": write_probe.get("error"),
            }

        if mode == "read":
            if not dry_run:
                try:
                    sensor.initialize()
                except Exception:  # noqa: BLE001
                    pass
            read_probe = attach_process_from_probe(
                run_sdk_read_probe(sensor, duration_s=read_duration_s, kind="gripper", config=config),
                kind="gripper",
            )
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
