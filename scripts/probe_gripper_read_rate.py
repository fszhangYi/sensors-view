#!/usr/bin/env python3
"""Dedicated gripper READ-rate probe entry (forces mode=read)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.gripper_rate_probe import main, run_job  # noqa: E402


def _inject_read_mode(argv: list[str] | None = None) -> int:
    # If caller already passed a job, ensure mode=read.
    args = list(argv or sys.argv[1:])
    if "--job" in args:
        idx = args.index("--job")
        job_path = Path(args[idx + 1])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job["mode"] = "read"
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        return main(args)
    if "--stdin" in args:
        job = json.load(sys.stdin)
        job["mode"] = "read"
        result = run_job(job)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    return main(args)


if __name__ == "__main__":
    raise SystemExit(_inject_read_mode())
