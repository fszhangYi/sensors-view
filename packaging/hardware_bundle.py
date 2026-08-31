"""Shared PyInstaller collection for hik-sensors hardware extras."""

from __future__ import annotations

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Import names (not pip names): pyserial → serial, pyzmq → zmq
HARDWARE_PACKAGES = (
    "pyrealsense2",
    "dynamixel_sdk",
    "serial",
    "zmq",
)


def extend_analysis(
    datas: list,
    binaries: list,
    hiddenimports: list,
) -> tuple[list, list, list]:
    """Collect datas/binaries/hiddenimports for hardware SDKs (required for desktop)."""
    missing: list[str] = []
    for pkg in HARDWARE_PACKAGES:
        try:
            d, b, h = collect_all(pkg)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{pkg} ({exc})")
            continue
        datas += d
        binaries += b
        hiddenimports += h
        try:
            hiddenimports += collect_submodules(pkg)
        except Exception:  # noqa: BLE001
            pass

    # Explicit lazy-import targets used by sensors drivers
    hiddenimports += [
        "pyrealsense2",
        "dynamixel_sdk",
        "dynamixel_sdk.robotis_def",
        "dynamixel_sdk.packet_handler",
        "dynamixel_sdk.port_handler",
        "dynamixel_sdk.group_sync_read",
        "serial",
        "serial.serialutil",
        "serial.tools",
        "serial.tools.list_ports",
        "zmq",
        "zmq.backend",
        "zmq.backend.cython",
    ]

    if missing:
        raise SystemExit(
            "desktop packaging requires hardware SDKs in the build env; missing: "
            + ", ".join(missing)
            + " — pip install -r requirements-hardware.txt"
        )
    return datas, binaries, hiddenimports
