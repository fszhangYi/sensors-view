"""Offline max-read-rate probe via sensors SDK ``probe_max_read_hz``.

Run standalone:
  python -m app.read_rate_probe --job job.json --out out.json

Invoked by sensors-view on a worker thread / subprocess; HTTP only waits for JSON.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

# Streaming kinds with SDK-native rate probe (bus/pipeline are orchestration only).
SUPPORTED_KINDS = frozenset({"ft", "tactile", "realsense", "gello", "gripper", "arm"})
EXCLUDED_KINDS = frozenset({"bus", "pipeline"})

MIN_PROBE_DURATION_S = 15.0


def _ensure_sensors_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    sensors_src = root / "sensors" / "src"
    if sensors_src.is_dir() and str(sensors_src) not in sys.path:
        sys.path.insert(0, str(sensors_src))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def resolve_probe_duration(duration_s: float | None, *, kind: str | None = None) -> float:
    """All rate probes run at least ``MIN_PROBE_DURATION_S`` seconds."""
    _ = kind
    if duration_s is None:
        return MIN_PROBE_DURATION_S
    return max(MIN_PROBE_DURATION_S, float(duration_s))


def default_duration_s(kind: str | None = None) -> float:
    _ = kind
    return MIN_PROBE_DURATION_S


def _downsample_dt_ms(times: list[float], *, max_points: int = 200) -> list[float]:
    """Downsample inter-sample intervals (ms) so process payload stays small."""
    if len(times) < 2:
        return []
    dts = [(times[i] - times[i - 1]) * 1000.0 for i in range(1, len(times))]
    if len(dts) <= max_points:
        return [round(d, 3) for d in dts]
    step = len(dts) / float(max_points)
    return [round(dts[min(len(dts) - 1, int(i * step))], 3) for i in range(max_points)]


def _process_payload(
    *,
    steps: list[dict[str, Any]],
    times: list[float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"steps": steps}
    if times is not None:
        out["dt_ms_series"] = _downsample_dt_ms(times)
        out["dt_ms_series_n"] = max(0, len(times) - 1)
    if extra:
        out.update(extra)
    return out


def attach_process_from_probe(probe: dict[str, Any], *, kind: str | None = None) -> dict[str, Any]:
    """Ensure probe dict has a ``process`` block (synthesize if driver-native)."""
    if not isinstance(probe, dict):
        return probe
    if isinstance(probe.get("process"), dict) and probe["process"].get("steps"):
        return probe
    method = str(probe.get("method") or "unknown")
    duration = probe.get("duration_s")
    samples = probe.get("samples")
    steps: list[dict[str, Any]] = [
        {"t_s": 0.0, "name": "start", "detail": f"method={method}" + (f" kind={kind}" if kind else "")},
        {
            "t_s": round(float(duration or 0.0), 3),
            "name": "loop",
            "detail": f"samples={samples} errors={probe.get('errors', 0)}",
        },
    ]
    if probe.get("ok"):
        steps.append(
            {
                "t_s": round(float(duration or 0.0), 3),
                "name": "done",
                "detail": (
                    f"measured_hz={probe.get('measured_hz')} "
                    f"read_cap_hz={probe.get('read_cap_hz')} "
                    f"dt_ms_p50={probe.get('dt_ms_p50')} "
                    f"dt_ms_p95={probe.get('dt_ms_p95')}"
                ).strip(),
            }
        )
    else:
        steps.append(
            {
                "t_s": round(float(duration or 0.0), 3),
                "name": "failed",
                "detail": str(probe.get("error") or "probe failed"),
            }
        )
    probe = {
        **probe,
        "process": _process_payload(
            steps=steps,
            extra={
                "summary": {
                    k: probe.get(k)
                    for k in (
                        "ok",
                        "method",
                        "samples",
                        "errors",
                        "duration_s",
                        "measured_hz",
                        "read_cap_hz",
                        "hardware_fps_cap",
                        "dt_ms_p50",
                        "dt_ms_p95",
                        "dt_ms_mean",
                        "last_error",
                    )
                    if k in probe
                }
            },
        ),
    }
    return probe


def _cap_from_measured(measured: float) -> float:
    return max(0.2, math.floor(float(measured) * 0.95 * 10) / 10)


def _prepare_config_for_probe(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    """Kind-specific tweaks so the probe measures bus/stream throughput, not UI pacing."""
    cfg = dict(config)
    if kind == "ft":
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


def run_sdk_read_probe(
    sensor: Any,
    *,
    duration_s: float | None = None,
    kind: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call driver-native ``probe_max_read_hz`` and apply view-layer caps."""
    duration = resolve_probe_duration(duration_s, kind=kind)
    read_probe = dict(sensor.probe_max_read_hz(duration_s=duration))
    if read_probe.get("ok") and "read_cap_hz" not in read_probe and read_probe.get("measured_hz"):
        read_probe["read_cap_hz"] = _cap_from_measured(float(read_probe["measured_hz"]))
    if read_probe.get("ok") and kind and config is not None:
        hw = _hardware_fps_cap(kind, config)
        if hw is not None and hw > 0 and read_probe.get("read_cap_hz") is not None:
            cap = min(float(read_probe["read_cap_hz"]), math.floor(hw * 10) / 10)
            read_probe = {**read_probe, "read_cap_hz": cap, "hardware_fps_cap": hw}
    return read_probe


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

    duration = resolve_probe_duration(
        job.get("duration_s") if job.get("duration_s") is not None else job.get("read_duration_s"),
        kind=kind,
    )
    sensor = None
    try:
        sensor = _open_sensor(sensor_id, kind, config, dry_run)
        if kind == "gripper" and not dry_run:
            try:
                sensor.initialize()
            except Exception:  # noqa: BLE001
                pass
        read_probe = run_sdk_read_probe(sensor, duration_s=duration, kind=kind, config=config)
        read_probe = attach_process_from_probe(read_probe, kind=kind)
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
