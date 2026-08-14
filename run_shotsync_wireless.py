from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Start ShotSync with a BLE wrist, BLE hoop, "
            "and local web dashboard."
        )
    )

    parser.add_argument(
        "--hoop-usb",
        help=(
            "Optional USB fallback port for the hoop. "
            "Omit this argument to use hoop BLE."
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Dashboard web port. Default: 8501.",
    )

    args = parser.parse_args()

    folder = Path(__file__).resolve().parent

    integrator = (
        folder
        / "milestone3_wireless_integrator_v5.py"
    )

    dashboard = (
        folder
        / "shotsync_dashboard_v4_1.py"
    )

    missing = [
        str(path)
        for path in (integrator, dashboard)
        if not path.exists()
    ]

    if missing:
        raise SystemExit(
            "Missing required file(s):\n"
            + "\n".join(missing)
        )

    integrator_command = [
        sys.executable,
        str(integrator),
        "--live",
    ]

    if args.hoop_usb:
        integrator_command.extend(
            [
                "--hoop-mode",
                "usb",
                "--hoop",
                args.hoop_usb,
            ]
        )
    else:
        integrator_command.extend(
            [
                "--hoop-mode",
                "ble",
            ]
        )

    dashboard_command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(dashboard),
        "--server.address",
        "0.0.0.0",
        "--server.port",
        str(args.port),
    ]

    print(
        "Starting ShotSync hardware integrator..."
    )

    integrator_process = subprocess.Popen(
        integrator_command,
        cwd=folder,
    )

    time.sleep(1.0)

    print("Starting ShotSync dashboard...")

    dashboard_process = subprocess.Popen(
        dashboard_command,
        cwd=folder,
    )

    print()
    print(
        "Dashboard URL on this Mac: "
        f"http://localhost:{args.port}"
    )

    if args.hoop_usb:
        print(
            "Hoop mode: USB fallback "
            f"({args.hoop_usb})"
        )
    else:
        print(
            "Hoop mode: Bluetooth "
            "(ShotSyncHoop)"
        )

    print(
        "Press Control-C once to stop "
        "both programs."
    )
    print()

    def stop_processes(
        *_: object,
    ) -> None:
        for process in (
            integrator_process,
            dashboard_process,
        ):
            if process.poll() is None:
                process.terminate()

        for process in (
            integrator_process,
            dashboard_process,
        ):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()

        raise SystemExit(0)

    signal.signal(
        signal.SIGINT,
        stop_processes,
    )

    signal.signal(
        signal.SIGTERM,
        stop_processes,
    )

    while True:
        if (
            integrator_process.poll()
            is not None
        ):
            print(
                "The hardware integrator stopped."
            )
            stop_processes()

        if (
            dashboard_process.poll()
            is not None
        ):
            print("The dashboard stopped.")
            stop_processes()

        time.sleep(0.5)


if __name__ == "__main__":
    main()
