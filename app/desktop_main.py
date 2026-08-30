"""Desktop entry: local uvicorn + system browser / pywebview."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser


def _pick_port(preferred: int = 6008) -> int:
    env = os.environ.get("SENSORS_VIEW_PORT") or os.environ.get("EOAT_PORT")
    if env:
        return int(env)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])


def _wait_health(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> None:
    # 1) env before importing settings / app
    from app.paths import APP_TITLE, ensure_runtime_env, default_view_config

    ensure_runtime_env(desktop=True)

    import uvicorn

    from app.main import app

    cfg = default_view_config()
    if cfg.is_file():
        app.state.view_config = str(cfg.resolve())

    host = "127.0.0.1"
    port = _pick_port(6008)
    url = f"http://{host}:{port}/"
    health = f"http://{host}:{port}/api/health"

    def _serve() -> None:
        uvicorn.run(app, host=host, port=port, log_level="info")

    thread = threading.Thread(target=_serve, name="sensors-view-uvicorn", daemon=True)
    thread.start()

    if not _wait_health(health):
        print(f"[sensors-view] health check failed: {health}", file=sys.stderr)
        sys.exit(1)

    print(f"[sensors-view] open {url}")
    opened = False
    try:
        import webview  # type: ignore

        webview.create_window(APP_TITLE, url, width=1280, height=860)
        webview.start()
        opened = True
    except Exception as exc:  # noqa: BLE001
        print(f"[sensors-view] pywebview unavailable ({exc}); falling back to browser")

    if not opened:
        webbrowser.open(url)
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
