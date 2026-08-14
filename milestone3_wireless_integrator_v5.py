from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import queue
import statistics
import struct
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, TextIO

try:
    import serial
except ImportError:
    serial = None

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.characteristic import (
        BleakGATTCharacteristic,
    )
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import (
        AdvertisementData,
    )
except ImportError:
    BleakClient = None
    BleakScanner = None
    BleakGATTCharacteristic = None
    BLEDevice = None
    AdvertisementData = None

BAUD_RATE = 115200
GRAVITY_MPS2 = 9.80665

BLE_DEVICE_NAME = "ShotSyncWristXIAO"

BLE_EVENT_CHARACTERISTIC_UUID = (
    "7A1E0003-6A7B-4C5D-9E10-112233445566"
)

BLE_SAMPLE_CHARACTERISTIC_UUID = (
    "7A1E0004-6A7B-4C5D-9E10-112233445566"
)

BLE_SAMPLE_PACKET_FORMAT = "<BBHHhhhhhhh"
BLE_SAMPLE_PACKET_SIZE = struct.calcsize(
    BLE_SAMPLE_PACKET_FORMAT
)

HOOP_BLE_DEVICE_NAME = "ShotSyncHoop"

HOOP_BLE_EVENT_CHARACTERISTIC_UUID = (
    "7A1E1003-6A7B-4C5D-9E10-112233445566"
)

HOOP_BLE_PACKET_FORMAT = "<BBHIBBHHH"
HOOP_BLE_PACKET_SIZE = struct.calcsize(
    HOOP_BLE_PACKET_FORMAT
)

BLE_SCAN_TIMEOUT_SECONDS = 15.0
BLE_RECONNECT_DELAY_SECONDS = 2.0

MIN_PAIR_DELAY_SECONDS = -0.20
MAX_PAIR_DELAY_SECONDS = 2.75
EVENT_EXPIRY_SECONDS = 3.50

BASELINE_TARGET_SHOTS = 15
MIN_CATEGORY_SHOTS = 5


LIVE_STATE_FILENAME = "shotsync_live_state.json"
PROFILE_FILENAME = "shotsync_profiles.json"
DEFAULT_PROFILE = "Athlete 1"


def current_athlete_profile() -> str:
    """
    Return the athlete currently selected in the dashboard.

    The dashboard writes this file atomically. The integrator reads it at
    release time so a shot remains assigned to the athlete who was selected
    when the shooting motion began.
    """
    path = Path(PROFILE_FILENAME)

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
    ):
        return DEFAULT_PROFILE

    active = str(
        payload.get(
            "active_profile",
            DEFAULT_PROFILE,
        )
    ).strip()

    return active or DEFAULT_PROFILE



def write_live_state(
    path: Path,
    state: str,
    **values: object,
) -> None:
    """Atomically publish the current hardware/shot state for the dashboard."""
    payload: dict[str, object] = {
        "state": state,
        "updated_at": time.time(),
        "updated_at_iso": datetime.now().isoformat(
            timespec="milliseconds"
        ),
    }
    payload.update(values)

    temporary_path = path.with_name(
        path.name + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)


@dataclass
class MotionSample:
    relative_time_ms: float
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float


@dataclass
class WristTrigger:
    shot_id: int
    board_time_ms: int
    arrival_time: float


@dataclass
class HoopEvent:
    arrival_time: float
    hoop_event_number: int
    board_time_ms: int
    result: str
    contact_side: str
    left_peak: int
    right_peak: int
    left_share_percent: float
    beam_break_ms: int


@dataclass
class WristBlock:
    shot_id: int
    candidate_time_ms: int
    expected_samples: int
    trigger_index: int
    samples: list[MotionSample]


@dataclass
class ShotAnalytics:
    wrist_shot_id: int
    sample_count: int
    peak_gyro_dps: float
    peak_gyro_time_ms: float
    trigger_gyro_dps: float
    snap_duration_ms: float
    motion_to_trigger_ms: float
    follow_through_ms: float
    settled_in_window: bool
    rotation_x_deg: float
    rotation_y_deg: float
    rotation_z_deg: float
    total_accel_at_trigger_mps2: float
    total_accel_at_trigger_g: float
    peak_total_accel_mps2: float
    peak_total_accel_g: float


@dataclass
class PairRecord:
    trigger: WristTrigger
    hoop: HoopEvent
    host_pair_delay_seconds: float


def magnitude3(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def trapezoid_integral(
    times_ms: list[float],
    values: list[float],
    start_index: int,
    end_index: int,
) -> float:
    total = 0.0

    for index in range(start_index, end_index):
        dt_seconds = (
            times_ms[index + 1] - times_ms[index]
        ) / 1000.0

        total += (
            values[index] + values[index + 1]
        ) * 0.5 * dt_seconds

    return total


def calculate_analytics(block: WristBlock) -> ShotAnalytics:
    samples = block.samples

    if len(samples) < 10:
        raise ValueError(
            f"Shot {block.shot_id} has only "
            f"{len(samples)} samples."
        )

    times = [
        sample.relative_time_ms
        for sample in samples
    ]

    gx = [sample.gx for sample in samples]
    gy = [sample.gy for sample in samples]
    gz = [sample.gz for sample in samples]

    gyro_magnitude = [
        magnitude3(sample.gx, sample.gy, sample.gz)
        for sample in samples
    ]

    accel_magnitude = [
        magnitude3(sample.ax, sample.ay, sample.az)
        for sample in samples
    ]

    if (
        0 <= block.trigger_index < len(samples)
    ):
        trigger_index = block.trigger_index
    else:
        trigger_index = min(
            range(len(samples)),
            key=lambda index: abs(times[index]),
        )

    peak_index = max(
        range(len(samples)),
        key=lambda index: gyro_magnitude[index],
    )

    peak_gyro = gyro_magnitude[peak_index]

    baseline_count = min(12, len(samples))
    baseline_values = gyro_magnitude[:baseline_count]

    baseline_median = statistics.median(
        baseline_values
    )

    robust_sigma = (
        1.4826 *
        median_absolute_deviation(baseline_values)
    )

    # Motion onset: find the last quiet run before
    # the main gyro peak, then treat the next sample
    # as the beginning of the release movement.
    onset_threshold = min(
        max(
            80.0,
            baseline_median + 4.0 * robust_sigma,
        ),
        0.25 * peak_gyro,
    )

    onset_index = 0
    quiet_run = 4

    for index in range(
        peak_index - quiet_run,
        -1,
        -1,
    ):
        window = gyro_magnitude[
            index:index + quiet_run
        ]

        if all(
            value < onset_threshold
            for value in window
        ):
            onset_index = index + quiet_run
            break

    # Snap duration: contiguous part of the main
    # release peak above 40% of the peak speed.
    snap_threshold = 0.40 * peak_gyro

    snap_start = peak_index
    while (
        snap_start > 0
        and gyro_magnitude[snap_start - 1]
        >= snap_threshold
    ):
        snap_start -= 1

    snap_end = peak_index
    while (
        snap_end < len(samples) - 1
        and gyro_magnitude[snap_end + 1]
        >= snap_threshold
    ):
        snap_end += 1

    if len(times) >= 2:
        sample_period_ms = statistics.median(
            times[index + 1] - times[index]
            for index in range(len(times) - 1)
        )
    else:
        sample_period_ms = 0.0

    snap_duration_ms = (
        times[snap_end]
        - times[snap_start]
        + sample_period_ms
    )

    # Follow-through: first point after the peak
    # where five consecutive samples return to a
    # low-motion range.
    settle_threshold = min(
        max(
            80.0,
            baseline_median + 3.0 * robust_sigma,
        ),
        0.20 * peak_gyro,
    )

    settle_index = len(samples) - 1
    settled_in_window = False
    settle_run = 5

    for index in range(
        peak_index + 1,
        len(samples) - settle_run + 1,
    ):
        window = gyro_magnitude[
            index:index + settle_run
        ]

        if all(
            value < settle_threshold
            for value in window
        ):
            settle_index = index
            settled_in_window = True
            break

    integration_end = max(
        onset_index,
        settle_index,
    )

    rotation_x = trapezoid_integral(
        times, gx, onset_index, integration_end
    )
    rotation_y = trapezoid_integral(
        times, gy, onset_index, integration_end
    )
    rotation_z = trapezoid_integral(
        times, gz, onset_index, integration_end
    )

    motion_to_trigger_ms = max(
        0.0,
        times[trigger_index] - times[onset_index],
    )

    follow_through_ms = max(
        0.0,
        times[settle_index] - times[trigger_index],
    )

    trigger_accel = accel_magnitude[trigger_index]
    peak_accel = max(accel_magnitude)

    return ShotAnalytics(
        wrist_shot_id=block.shot_id,
        sample_count=len(samples),
        peak_gyro_dps=peak_gyro,
        peak_gyro_time_ms=times[peak_index],
        trigger_gyro_dps=gyro_magnitude[
            trigger_index
        ],
        snap_duration_ms=snap_duration_ms,
        motion_to_trigger_ms=motion_to_trigger_ms,
        follow_through_ms=follow_through_ms,
        settled_in_window=settled_in_window,
        rotation_x_deg=rotation_x,
        rotation_y_deg=rotation_y,
        rotation_z_deg=rotation_z,
        total_accel_at_trigger_mps2=trigger_accel,
        total_accel_at_trigger_g=(
            trigger_accel / GRAVITY_MPS2
        ),
        peak_total_accel_mps2=peak_accel,
        peak_total_accel_g=peak_accel / GRAVITY_MPS2,
    )


def parse_trigger(
    line: str,
    arrival_time: float,
) -> WristTrigger | None:
    fields = line.split(",")

    if len(fields) != 3:
        return None

    try:
        return WristTrigger(
            shot_id=int(fields[1]),
            board_time_ms=int(fields[2]),
            arrival_time=arrival_time,
        )
    except ValueError:
        return None


def parse_hoop(
    line: str,
    arrival_time: float,
) -> HoopEvent | None:
    fields = line.split(",")

    if len(fields) != 9:
        return None

    try:
        return HoopEvent(
            arrival_time=arrival_time,
            hoop_event_number=int(fields[1]),
            board_time_ms=int(fields[2]),
            result=fields[3],
            contact_side=fields[4],
            left_peak=int(fields[5]),
            right_peak=int(fields[6]),
            left_share_percent=float(fields[7]),
            beam_break_ms=int(fields[8]),
        )
    except ValueError:
        return None


def parse_begin(line: str) -> WristBlock | None:
    fields = line.split(",")

    if len(fields) != 5:
        return None

    try:
        return WristBlock(
            shot_id=int(fields[1]),
            candidate_time_ms=int(fields[2]),
            expected_samples=int(fields[3]),
            trigger_index=int(fields[4]),
            samples=[],
        )
    except ValueError:
        return None


def parse_sample(line: str) -> tuple[int, MotionSample] | None:
    fields = line.split(",")

    if len(fields) != 9:
        return None

    try:
        shot_id = int(fields[1])

        sample = MotionSample(
            relative_time_ms=float(fields[2]),
            ax=float(fields[3]),
            ay=float(fields[4]),
            az=float(fields[5]),
            gx=float(fields[6]),
            gy=float(fields[7]),
            gz=float(fields[8]),
        )

        return shot_id, sample

    except ValueError:
        return None


def serial_reader(
    device_name: str,
    port: str,
    output_queue: queue.Queue[
        tuple[str, float, str]
    ],
    stop_event: threading.Event,
) -> None:
    if serial is None:
        print(
            "pyserial is not installed. Run: "
            "python3 -m pip install pyserial"
        )
        stop_event.set()
        return

    try:
        with serial.Serial(
            port,
            BAUD_RATE,
            timeout=0.1,
        ) as device:
            time.sleep(2)

            print(
                f"[CONNECTED] {device_name}: {port}"
            )

            output_queue.put(
                (
                    "SYSTEM",
                    time.monotonic(),
                    f"{device_name}_CONNECTED",
                )
            )

            while not stop_event.is_set():
                raw_line = device.readline()

                if not raw_line:
                    continue

                line = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if line:
                    output_queue.put(
                        (
                            device_name,
                            time.monotonic(),
                            line,
                        )
                    )

    except Exception as error:
        print(
            f"[ERROR] Could not use "
            f"{device_name} port {port}: {error}"
        )

        output_queue.put(
            (
                "SYSTEM",
                time.monotonic(),
                f"{device_name}_DISCONNECTED",
            )
        )

        stop_event.set()



def ble_device_filter(
    device: BLEDevice,
    advertisement: AdvertisementData,
) -> bool:
    advertised_name = (
        advertisement.local_name or device.name
    )

    return advertised_name == BLE_DEVICE_NAME


async def ble_wrist_reader(
    output_queue: queue.Queue[
        tuple[str, float, str]
    ],
    stop_event: threading.Event,
    scan_lock: asyncio.Lock,
) -> None:
    if BleakClient is None or BleakScanner is None:
        print(
            "bleak is not installed. Run: "
            "python3 -m pip install bleak"
        )
        stop_event.set()
        return

    while not stop_event.is_set():
        print(
            f"[BLE] Scanning for {BLE_DEVICE_NAME}..."
        )

        output_queue.put(
            (
                "SYSTEM",
                time.monotonic(),
                "WRIST_CONNECTING",
            )
        )

        try:
            async with scan_lock:
                device = await (
                    BleakScanner.find_device_by_filter(
                        ble_device_filter,
                        timeout=BLE_SCAN_TIMEOUT_SECONDS,
                    )
                )
        except Exception as error:
            print(f"[BLE ERROR] Scan failed: {error}")
            device = None

        if device is None:
            if stop_event.is_set():
                return

            print(
                f"[BLE] Could not find {BLE_DEVICE_NAME}. "
                "Retrying..."
            )
            await asyncio.sleep(
                BLE_RECONNECT_DELAY_SECONDS
            )
            continue

        print(f"[BLE] Found {device.name}. Connecting...")

        event_receive_buffer = bytearray()
        seen_sample_packets: set[
            tuple[int, int]
        ] = set()
        received_per_shot: dict[int, int] = {}

        def event_handler(
            characteristic: BleakGATTCharacteristic,
            data: bytearray,
        ) -> None:
            del characteristic

            event_receive_buffer.extend(data)

            while True:
                newline_index = (
                    event_receive_buffer.find(b"\n")
                )

                if newline_index < 0:
                    break

                complete_line = bytes(
                    event_receive_buffer[
                        :newline_index
                    ]
                )

                del event_receive_buffer[
                    :newline_index + 1
                ]

                text_line = complete_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if text_line:
                    print(
                        f"[WRIST BLE EVENT] {text_line}"
                    )

                    output_queue.put(
                        (
                            "WRIST",
                            time.monotonic(),
                            text_line,
                        )
                    )

        def sample_handler(
            characteristic: BleakGATTCharacteristic,
            data: bytearray,
        ) -> None:
            del characteristic

            raw = bytes(data)

            if len(raw) != BLE_SAMPLE_PACKET_SIZE:
                print(
                    "[BLE WARNING] Sample packet had "
                    f"{len(raw)} bytes; expected "
                    f"{BLE_SAMPLE_PACKET_SIZE}."
                )
                return

            try:
                (
                    marker,
                    version,
                    shot_id,
                    sample_index,
                    relative_time_ms,
                    ax_scaled,
                    ay_scaled,
                    az_scaled,
                    gx_scaled,
                    gy_scaled,
                    gz_scaled,
                ) = struct.unpack(
                    BLE_SAMPLE_PACKET_FORMAT,
                    raw,
                )
            except struct.error as error:
                print(
                    "[BLE WARNING] Could not unpack "
                    f"sample packet: {error}"
                )
                return

            if marker != 0x53 or version != 1:
                print(
                    "[BLE WARNING] Unknown sample "
                    f"packet marker/version: "
                    f"{marker}/{version}"
                )
                return

            packet_key = (shot_id, sample_index)

            if packet_key in seen_sample_packets:
                return

            seen_sample_packets.add(packet_key)

            ax = ax_scaled / 100.0
            ay = ay_scaled / 100.0
            az = az_scaled / 100.0

            gx = gx_scaled / 10.0
            gy = gy_scaled / 10.0
            gz = gz_scaled / 10.0

            synthetic_line = (
                f"WRIST_SAMPLE,{shot_id},"
                f"{float(relative_time_ms):.2f},"
                f"{ax:.3f},{ay:.3f},{az:.3f},"
                f"{gx:.2f},{gy:.2f},{gz:.2f}"
            )

            output_queue.put(
                (
                    "WRIST",
                    time.monotonic(),
                    synthetic_line,
                )
            )

            count = (
                received_per_shot.get(shot_id, 0)
                + 1
            )
            received_per_shot[shot_id] = count

            if (
                count == 1
                or count % 10 == 0
            ):
                print(
                    f"[WRIST SAMPLES] shot "
                    f"{shot_id}: {count} received"
                )

        try:
            async with BleakClient(device) as client:
                print(
                    "[CONNECTED] WRIST BLE: "
                    f"{BLE_DEVICE_NAME}"
                )

                await client.start_notify(
                    BLE_EVENT_CHARACTERISTIC_UUID,
                    event_handler,
                )

                await client.start_notify(
                    BLE_SAMPLE_CHARACTERISTIC_UUID,
                    sample_handler,
                )

                print(
                    "[BLE READY] Event and binary "
                    "sample channels subscribed."
                )

                output_queue.put(
                    (
                        "SYSTEM",
                        time.monotonic(),
                        "WRIST_CONNECTED",
                    )
                )

                while (
                    client.is_connected
                    and not stop_event.is_set()
                ):
                    await asyncio.sleep(0.10)

                if client.is_connected:
                    await client.stop_notify(
                        BLE_SAMPLE_CHARACTERISTIC_UUID
                    )

                    await client.stop_notify(
                        BLE_EVENT_CHARACTERISTIC_UUID
                    )

        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not stop_event.is_set():
                print(
                    f"[BLE ERROR] Wrist connection lost: "
                    f"{error}"
                )

        if not stop_event.is_set():
            output_queue.put(
                (
                    "SYSTEM",
                    time.monotonic(),
                    "WRIST_DISCONNECTED",
                )
            )

            print("[BLE] Reconnecting to wrist...")
            await asyncio.sleep(
                BLE_RECONNECT_DELAY_SECONDS
            )


def ble_hoop_device_filter(
    device: BLEDevice,
    advertisement: AdvertisementData,
) -> bool:
    advertised_name = (
        advertisement.local_name
        or device.name
    )

    return advertised_name == HOOP_BLE_DEVICE_NAME


async def ble_hoop_reader(
    output_queue: queue.Queue[
        tuple[str, float, str]
    ],
    stop_event: threading.Event,
    scan_lock: asyncio.Lock,
) -> None:
    if BleakClient is None or BleakScanner is None:
        print(
            "bleak is not installed. Run: "
            "python3 -m pip install bleak"
        )
        stop_event.set()
        return

    result_map = {
        1: ("CLEAN_MAKE", "NONE"),
        2: ("MAKE_WITH_RIM_CONTACT", "RIM"),
        3: ("RIM_MISS", "RIM"),
    }

    while not stop_event.is_set():
        print(
            f"[BLE] Scanning for {HOOP_BLE_DEVICE_NAME}..."
        )

        output_queue.put(
            (
                "SYSTEM",
                time.monotonic(),
                "HOOP_CONNECTING",
            )
        )

        try:
            async with scan_lock:
                device = await (
                    BleakScanner.find_device_by_filter(
                        ble_hoop_device_filter,
                        timeout=BLE_SCAN_TIMEOUT_SECONDS,
                    )
                )
        except Exception as error:
            print(
                f"[BLE ERROR] Hoop scan failed: {error}"
            )
            device = None

        if device is None:
            if stop_event.is_set():
                return

            print(
                f"[BLE] Could not find {HOOP_BLE_DEVICE_NAME}. "
                "Retrying..."
            )

            await asyncio.sleep(
                BLE_RECONNECT_DELAY_SECONDS
            )
            continue

        print(
            f"[BLE] Found {device.name}. Connecting..."
        )

        seen_events: set[
            tuple[int, int]
        ] = set()

        def hoop_handler(
            characteristic: BleakGATTCharacteristic,
            data: bytearray,
        ) -> None:
            del characteristic

            raw = bytes(data)

            if len(raw) != HOOP_BLE_PACKET_SIZE:
                print(
                    "[BLE WARNING] Hoop packet had "
                    f"{len(raw)} bytes; expected "
                    f"{HOOP_BLE_PACKET_SIZE}."
                )
                return

            try:
                (
                    marker,
                    version,
                    event_number,
                    board_time_ms,
                    result_code,
                    contact_code,
                    piezo_peak,
                    beam_break_ms,
                    reserved,
                ) = struct.unpack(
                    HOOP_BLE_PACKET_FORMAT,
                    raw,
                )
            except struct.error as error:
                print(
                    "[BLE WARNING] Could not unpack "
                    f"hoop packet: {error}"
                )
                return

            del contact_code, reserved

            if marker != 0x48 or version != 1:
                print(
                    "[BLE WARNING] Unknown hoop "
                    f"packet marker/version: "
                    f"{marker}/{version}"
                )
                return

            event_key = (
                event_number,
                board_time_ms,
            )

            if event_key in seen_events:
                return

            seen_events.add(event_key)

            result_contact = result_map.get(
                result_code
            )

            if result_contact is None:
                print(
                    "[BLE WARNING] Unknown hoop "
                    f"result code: {result_code}"
                )
                return

            result, contact = result_contact

            contact_share = (
                100.0 if piezo_peak > 0 else 0.0
            )

            synthetic_line = (
                f"HOOP,{event_number},"
                f"{board_time_ms},{result},"
                f"{contact},{piezo_peak},0,"
                f"{contact_share:.1f},"
                f"{beam_break_ms}"
            )

            print(
                f"[HOOP BLE EVENT] {synthetic_line}"
            )

            output_queue.put(
                (
                    "HOOP",
                    time.monotonic(),
                    synthetic_line,
                )
            )

        try:
            async with BleakClient(device) as client:
                print(
                    "[CONNECTED] HOOP BLE: "
                    f"{HOOP_BLE_DEVICE_NAME}"
                )

                await client.start_notify(
                    HOOP_BLE_EVENT_CHARACTERISTIC_UUID,
                    hoop_handler,
                )

                output_queue.put(
                    (
                        "SYSTEM",
                        time.monotonic(),
                        "HOOP_CONNECTED",
                    )
                )

                while (
                    client.is_connected
                    and not stop_event.is_set()
                ):
                    await asyncio.sleep(0.10)

                if client.is_connected:
                    await client.stop_notify(
                        HOOP_BLE_EVENT_CHARACTERISTIC_UUID
                    )

        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not stop_event.is_set():
                print(
                    "[BLE ERROR] Hoop connection "
                    f"lost: {error}"
                )

        if not stop_event.is_set():
            output_queue.put(
                (
                    "SYSTEM",
                    time.monotonic(),
                    "HOOP_DISCONNECTED",
                )
            )

            print("[BLE] Reconnecting to hoop...")

            await asyncio.sleep(
                BLE_RECONNECT_DELAY_SECONDS
            )


class AnalyticsSession:
    def __init__(
        self,
        summary_writer: csv.DictWriter,
        sample_writer: csv.DictWriter,
        summary_file: TextIO,
        sample_file: TextIO,
        live_state_path: Path,
        session_timestamp: str,
    ) -> None:
        self.summary_writer = summary_writer
        self.sample_writer = sample_writer
        self.summary_file = summary_file
        self.sample_file = sample_file
        self.live_state_path = live_state_path
        self.session_timestamp = session_timestamp

        self.active_blocks: dict[int, WristBlock] = {}
        self.ended_blocks: set[int] = set()

        # Capture the selected athlete when the release is detected so
        # switching accounts while a shot is still processing cannot move
        # that shot to the wrong person.
        self.shot_profiles: dict[int, str] = {}

        self.completed_analytics: dict[
            int, ShotAnalytics
        ] = {}

        self.pending_triggers: deque[
            WristTrigger
        ] = deque()

        self.pending_hoops: deque[
            HoopEvent
        ] = deque()

        self.pairs: dict[int, PairRecord] = {}
        self.emitted_shots: set[int] = set()

        self.baseline: list[ShotAnalytics] = []
        self.outcome_analytics: dict[
            str, list[ShotAnalytics]
        ] = defaultdict(list)

        self.paired_shots = 0
        self.makes = 0
        self.misses = 0
        self.unconfirmed_releases = 0
        self.unpaired_hoop_events = 0

        self.wrist_connected = False
        self.hoop_connected = False

    def publish_state(
        self,
        state: str,
        **values: object,
    ) -> None:
        base_values: dict[str, object] = {
            "session": self.session_timestamp,
            "athlete_profile": current_athlete_profile(),
            "paired_shots": self.paired_shots,
            "makes": self.makes,
            "misses": self.misses,
            "unconfirmed_releases": (
                self.unconfirmed_releases
            ),
            "unpaired_hoop_events": (
                self.unpaired_hoop_events
            ),
            "wrist_connected": self.wrist_connected,
            "hoop_connected": self.hoop_connected,
        }
        base_values.update(values)

        try:
            write_live_state(
                self.live_state_path,
                state,
                **base_values,
            )
        except OSError as error:
            print(
                "[LIVE STATE WARNING] Could not "
                f"update dashboard state: {error}"
            )

    def publish_processing_progress(
        self,
        shot_id: int,
        received_samples: int,
        expected_samples: int,
    ) -> None:
        pair = self.pairs.get(shot_id)

        values: dict[str, object] = {
            "wrist_shot_id": shot_id,
            "received_samples": received_samples,
            "expected_samples": expected_samples,
        }

        if pair is not None:
            values.update(
                {
                    "result": pair.hoop.result,
                    "contact_side": (
                        pair.hoop.contact_side
                    ),
                    "hoop_event_number": (
                        pair.hoop.hoop_event_number
                    ),
                }
            )

        self.publish_state(
            "PROCESSING",
            **values,
        )

    def publish_connection_state(self) -> None:
        if self.wrist_connected and self.hoop_connected:
            self.publish_state(
                "WAITING",
                message=(
                    "Ready — waiting for your next shot."
                ),
            )
            return

        missing = []

        if not self.wrist_connected:
            missing.append("wrist sensor")

        if not self.hoop_connected:
            missing.append("hoop sensor")

        self.publish_state(
            "CONNECTING",
            message=(
                "Connecting " + " and ".join(missing) + "."
            ),
        )

    def handle_system_line(self, line: str) -> None:
        if line == "WRIST_CONNECTED":
            self.wrist_connected = True
        elif line in {
            "WRIST_CONNECTING",
            "WRIST_DISCONNECTED",
        }:
            self.wrist_connected = False
        elif line == "HOOP_CONNECTED":
            self.hoop_connected = True
        elif line in {
            "HOOP_CONNECTING",
            "HOOP_DISCONNECTED",
        }:
            self.hoop_connected = False
        else:
            return

        self.publish_connection_state()

    def handle_line(
        self,
        device_name: str,
        arrival_time: float,
        line: str,
    ) -> None:
        if device_name == "SYSTEM":
            self.handle_system_line(line)
            return

        if line.startswith("WRIST_TRIGGER,"):
            trigger = parse_trigger(
                line,
                arrival_time,
            )

            if trigger is not None:
                self.pending_triggers.append(trigger)

                athlete_profile = (
                    current_athlete_profile()
                )

                self.shot_profiles[
                    trigger.shot_id
                ] = athlete_profile

                print(
                    f"[WRIST TRIGGER] "
                    f"shot {trigger.shot_id} "
                    f"for {athlete_profile}"
                )

                self.publish_state(
                    "RELEASE_DETECTED",
                    wrist_shot_id=trigger.shot_id,
                    athlete_profile=athlete_profile,
                    message=(
                        "Release detected — waiting for "
                        "the ball result."
                    ),
                )

                self.try_pair_events()

        elif line.startswith("WRIST_BEGIN,"):
            block = parse_begin(line)

            if block is not None:
                self.active_blocks[
                    block.shot_id
                ] = block

                self.publish_processing_progress(
                    block.shot_id,
                    0,
                    block.expected_samples,
                )

        elif line.startswith("WRIST_SAMPLE,"):
            parsed = parse_sample(line)

            if parsed is not None:
                shot_id, sample = parsed
                block = self.active_blocks.get(shot_id)

                if block is not None:
                    block.samples.append(sample)

                    received = len(block.samples)

                    if (
                        received == 1
                        or received % 5 == 0
                        or received
                        >= block.expected_samples
                    ):
                        self.publish_processing_progress(
                            shot_id,
                            received,
                            block.expected_samples,
                        )

                    if (
                        shot_id in self.ended_blocks
                        and len(block.samples)
                        >= block.expected_samples
                    ):
                        self.finish_wrist_block(
                            shot_id
                        )

        elif line.startswith("WRIST_END,"):
            fields = line.split(",")

            if len(fields) == 2:
                try:
                    shot_id = int(fields[1])
                except ValueError:
                    return

                block = self.active_blocks.get(
                    shot_id
                )

                if block is None:
                    print(
                        f"[WARNING] WRIST_END for "
                        f"unknown shot {shot_id}"
                    )
                    return

                if (
                    len(block.samples)
                    >= block.expected_samples
                ):
                    self.finish_wrist_block(
                        shot_id
                    )
                else:
                    self.ended_blocks.add(
                        shot_id
                    )

                    print(
                        f"[WRIST END] shot {shot_id}: "
                        f"{len(block.samples)}/"
                        f"{block.expected_samples} "
                        "samples received; waiting "
                        "for remaining packets."
                    )

        elif line.startswith("HOOP,"):
            hoop = parse_hoop(
                line,
                arrival_time,
            )

            if hoop is not None:
                self.pending_hoops.append(hoop)

                print(
                    f"[HOOP] {hoop.result} "
                    f"({hoop.contact_side})"
                )

                self.publish_state(
                    "HOOP_DETECTED",
                    result=hoop.result,
                    contact_side=hoop.contact_side,
                    hoop_event_number=(
                        hoop.hoop_event_number
                    ),
                    message=(
                        "Ball result received — checking "
                        "the wrist motion."
                    ),
                )

                self.try_pair_events()

    def finish_wrist_block(
        self,
        shot_id: int,
    ) -> None:
        block = self.active_blocks.pop(
            shot_id,
            None,
        )

        self.ended_blocks.discard(shot_id)

        if block is None:
            print(
                f"[WARNING] WRIST_END for "
                f"unknown shot {shot_id}"
            )
            return

        if (
            len(block.samples)
            != block.expected_samples
        ):
            print(
                f"[WARNING] Shot {shot_id}: "
                f"expected {block.expected_samples} "
                f"samples, received "
                f"{len(block.samples)}."
            )

        try:
            analytics = calculate_analytics(block)
        except ValueError as error:
            print(f"[WARNING] {error}")
            return

        self.completed_analytics[
            shot_id
        ] = analytics

        for sample in block.samples:
            self.sample_writer.writerow(
                {
                    "wrist_shot_id": shot_id,
                    "relative_time_ms": (
                        f"{sample.relative_time_ms:.2f}"
                    ),
                    "ax_mps2": sample.ax,
                    "ay_mps2": sample.ay,
                    "az_mps2": sample.az,
                    "gx_dps": sample.gx,
                    "gy_dps": sample.gy,
                    "gz_dps": sample.gz,
                }
            )

        self.sample_file.flush()

        print(
            f"[ANALYTICS READY] shot {shot_id}: "
            f"{len(block.samples)}/"
            f"{block.expected_samples} samples, "
            f"peak {analytics.peak_gyro_dps:.0f}°/s, "
            f"snap {analytics.snap_duration_ms:.0f} ms"
        )

        self.emit_if_ready(shot_id)

    def try_pair_events(self) -> None:
        for hoop in list(self.pending_hoops):
            valid_triggers = [
                trigger
                for trigger in self.pending_triggers
                if (
                    MIN_PAIR_DELAY_SECONDS
                    <= (
                        hoop.arrival_time
                        - trigger.arrival_time
                    )
                    <= MAX_PAIR_DELAY_SECONDS
                )
            ]

            if not valid_triggers:
                continue

            trigger = max(
                valid_triggers,
                key=lambda item: item.arrival_time,
            )

            self.pending_triggers.remove(trigger)
            self.pending_hoops.remove(hoop)

            pair = PairRecord(
                trigger=trigger,
                hoop=hoop,
                host_pair_delay_seconds=(
                    hoop.arrival_time
                    - trigger.arrival_time
                ),
            )

            self.pairs[trigger.shot_id] = pair

            print(
                f"[PAIRED] wrist shot "
                f"{trigger.shot_id} -> "
                f"{hoop.result}"
            )

            active_block = self.active_blocks.get(
                trigger.shot_id
            )

            self.publish_state(
                "PAIRED",
                wrist_shot_id=trigger.shot_id,
                hoop_event_number=(
                    hoop.hoop_event_number
                ),
                result=hoop.result,
                contact_side=hoop.contact_side,
                received_samples=(
                    len(active_block.samples)
                    if active_block is not None
                    else 0
                ),
                expected_samples=(
                    active_block.expected_samples
                    if active_block is not None
                    else 0
                ),
                message=(
                    "Shot confirmed — analyzing wrist "
                    "mechanics."
                ),
            )

            self.emit_if_ready(trigger.shot_id)

            self.try_pair_events()
            return

    def emit_if_ready(self, shot_id: int) -> None:
        if shot_id in self.emitted_shots:
            return

        analytics = self.completed_analytics.get(
            shot_id
        )

        pair = self.pairs.get(shot_id)

        if analytics is None or pair is None:
            return

        self.emitted_shots.add(shot_id)

        athlete_profile = self.shot_profiles.pop(
            shot_id,
            current_athlete_profile(),
        )

        self.paired_shots += 1

        if pair.hoop.result in {
            "CLEAN_MAKE",
            "MAKE_WITH_RIM_CONTACT",
        }:
            self.makes += 1
        else:
            self.misses += 1

        consistency_score = self.consistency_score(
            analytics
        )

        if (
            len(self.baseline)
            < BASELINE_TARGET_SHOTS
        ):
            self.baseline.append(analytics)

        baseline_status = (
            f"{len(self.baseline)}/"
            f"{BASELINE_TARGET_SHOTS}"
        )

        self.summary_writer.writerow(
            {
                "session_shot_number": (
                    self.paired_shots
                ),
                "athlete_profile": athlete_profile,
                "wrist_shot_id": shot_id,
                "hoop_event_number": (
                    pair.hoop.hoop_event_number
                ),
                "result": pair.hoop.result,
                "contact_side": (
                    pair.hoop.contact_side
                ),
                "host_pair_delay_seconds": (
                    f"{pair.host_pair_delay_seconds:.4f}"
                ),
                **{
                    key: value
                    for key, value
                    in asdict(analytics).items()
                    if key != "wrist_shot_id"
                },
                "consistency_score": (
                    ""
                    if consistency_score is None
                    else f"{consistency_score:.1f}"
                ),
                "baseline_progress": baseline_status,
                "left_peak": pair.hoop.left_peak,
                "right_peak": pair.hoop.right_peak,
                "left_share_percent": (
                    pair.hoop.left_share_percent
                ),
                "beam_break_ms": (
                    pair.hoop.beam_break_ms
                ),
            }
        )

        self.summary_file.flush()

        self.publish_state(
            "READY",
            wrist_shot_id=shot_id,
            athlete_profile=athlete_profile,
            hoop_event_number=(
                pair.hoop.hoop_event_number
            ),
            result=pair.hoop.result,
            contact_side=pair.hoop.contact_side,
            session_shot_number=(
                self.paired_shots
            ),
            peak_gyro_dps=(
                analytics.peak_gyro_dps
            ),
            snap_duration_ms=(
                analytics.snap_duration_ms
            ),
            motion_to_trigger_ms=(
                analytics.motion_to_trigger_ms
            ),
            follow_through_ms=(
                analytics.follow_through_ms
            ),
            rotation_x_deg=(
                analytics.rotation_x_deg
            ),
            rotation_y_deg=(
                analytics.rotation_y_deg
            ),
            rotation_z_deg=(
                analytics.rotation_z_deg
            ),
            total_accel_at_trigger_g=(
                analytics.total_accel_at_trigger_g
            ),
            consistency_score=(
                consistency_score
            ),
            received_samples=(
                analytics.sample_count
            ),
            expected_samples=(
                analytics.sample_count
            ),
            message=(
                "Shot analytics are ready."
            ),
        )

        self.outcome_analytics[
            pair.hoop.result
        ].append(analytics)

        percentage = (
            100.0 * self.makes / self.paired_shots
        )

        print()
        print("========== SHOT ANALYTICS ==========")
        print(
            f"Session shot: {self.paired_shots}"
        )
        print(f"Result: {pair.hoop.result}")
        print(
            f"Contact: {pair.hoop.contact_side}"
        )
        print(
            "Peak wrist angular speed: "
            f"{analytics.peak_gyro_dps:.0f}°/s "
            f"at {analytics.peak_gyro_time_ms:.0f} ms"
        )
        print(
            "Wrist snap duration: "
            f"{analytics.snap_duration_ms:.0f} ms"
        )
        print(
            "Movement onset to trigger: "
            f"{analytics.motion_to_trigger_ms:.0f} ms"
        )
        print(
            "Follow-through to settled motion: "
            f"{analytics.follow_through_ms:.0f} ms"
        )
        print(
            "Estimated wrist rotation X/Y/Z: "
            f"{analytics.rotation_x_deg:.1f}° / "
            f"{analytics.rotation_y_deg:.1f}° / "
            f"{analytics.rotation_z_deg:.1f}°"
        )
        print(
            "Total acceleration at trigger: "
            f"{analytics.total_accel_at_trigger_mps2:.1f} m/s² "
            f"({analytics.total_accel_at_trigger_g:.2f} g)"
        )
        print(
            "Peak total acceleration in window: "
            f"{analytics.peak_total_accel_mps2:.1f} m/s² "
            f"({analytics.peak_total_accel_g:.2f} g)"
        )

        if consistency_score is None:
            print(
                "Personal baseline: "
                f"{len(self.baseline)}/"
                f"{BASELINE_TARGET_SHOTS} shots"
            )
        else:
            print(
                "Consistency score: "
                f"{consistency_score:.1f}/100"
            )

        print(
            f"Session makes: "
            f"{self.makes}/{self.paired_shots} "
            f"({percentage:.1f}%)"
        )

        if not analytics.settled_in_window:
            print(
                "Note: wrist did not fully settle "
                "inside the 500 ms post-trigger window."
            )

        print("====================================")
        print()

    def consistency_score(
        self,
        analytics: ShotAnalytics,
    ) -> float | None:
        if (
            len(self.baseline)
            < BASELINE_TARGET_SHOTS
        ):
            return None

        fields_and_floors = [
            ("peak_gyro_dps", 120.0),
            ("snap_duration_ms", 20.0),
            ("motion_to_trigger_ms", 35.0),
            ("follow_through_ms", 40.0),
            ("rotation_y_deg", 12.0),
            ("rotation_z_deg", 10.0),
        ]

        normalized_differences = []

        for field_name, minimum_scale in (
            fields_and_floors
        ):
            values = [
                getattr(item, field_name)
                for item in self.baseline
            ]

            center = statistics.mean(values)

            spread = (
                statistics.stdev(values)
                if len(values) >= 2
                else 0.0
            )

            scale = max(
                minimum_scale,
                2.0 * spread,
            )

            difference = abs(
                getattr(analytics, field_name)
                - center
            )

            normalized_differences.append(
                difference / scale
            )

        average_difference = statistics.mean(
            normalized_differences
        )

        score = 100.0 * math.exp(
            -0.85 * average_difference
        )

        return max(0.0, min(100.0, score))

    def expire_events(self, now: float) -> None:
        while (
            self.pending_triggers
            and now
            - self.pending_triggers[0].arrival_time
            > EVENT_EXPIRY_SECONDS
        ):
            trigger = self.pending_triggers.popleft()
            self.unconfirmed_releases += 1

            print(
                f"[UNCONFIRMED RELEASE] "
                f"wrist shot {trigger.shot_id}"
            )

            self.publish_state(
                "UNCONFIRMED_RELEASE",
                wrist_shot_id=trigger.shot_id,
                message=(
                    "Movement ignored because no matching "
                    "ball result was found."
                ),
            )

        while (
            self.pending_hoops
            and now
            - self.pending_hoops[0].arrival_time
            > EVENT_EXPIRY_SECONDS
        ):
            hoop = self.pending_hoops.popleft()
            self.unpaired_hoop_events += 1

            print(
                f"[UNPAIRED HOOP EVENT] "
                f"{hoop.result}"
            )

            self.publish_state(
                "UNPAIRED_HOOP_EVENT",
                result=hoop.result,
                contact_side=hoop.contact_side,
                hoop_event_number=(
                    hoop.hoop_event_number
                ),
                message=(
                    "Hoop reading ignored because no matching "
                    "wrist release was found."
                ),
            )

    def print_outcome_comparisons(self) -> None:
        print()
        print("OUTCOME COMPARISONS")

        for result, records in (
            self.outcome_analytics.items()
        ):
            print(
                f"{result}: {len(records)} shot(s)"
            )

            if len(records) < MIN_CATEGORY_SHOTS:
                print(
                    f"  Need "
                    f"{MIN_CATEGORY_SHOTS - len(records)} "
                    "more for a stable comparison."
                )
                continue

            print(
                "  Average peak speed: "
                f"{statistics.mean(
                    item.peak_gyro_dps
                    for item in records
                ):.0f}°/s"
            )

            print(
                "  Average snap duration: "
                f"{statistics.mean(
                    item.snap_duration_ms
                    for item in records
                ):.0f} ms"
            )

            print(
                "  Average Y rotation: "
                f"{statistics.mean(
                    item.rotation_y_deg
                    for item in records
                ):.1f}°"
            )

            print(
                "  Average follow-through: "
                f"{statistics.mean(
                    item.follow_through_ms
                    for item in records
                ):.0f} ms"
            )


def make_writers(
    timestamp: str,
) -> tuple[
    TextIO,
    TextIO,
    csv.DictWriter,
    csv.DictWriter,
    Path,
    Path,
]:
    summary_path = Path(
        f"basketball_analytics_summary_"
        f"{timestamp}.csv"
    )

    sample_path = Path(
        f"basketball_analytics_samples_"
        f"{timestamp}.csv"
    )

    summary_file = summary_path.open(
        "w",
        newline="",
        encoding="utf-8",
    )

    sample_file = sample_path.open(
        "w",
        newline="",
        encoding="utf-8",
    )

    summary_fields = [
        "session_shot_number",
        "athlete_profile",
        "wrist_shot_id",
        "hoop_event_number",
        "result",
        "contact_side",
        "host_pair_delay_seconds",
        "sample_count",
        "peak_gyro_dps",
        "peak_gyro_time_ms",
        "trigger_gyro_dps",
        "snap_duration_ms",
        "motion_to_trigger_ms",
        "follow_through_ms",
        "settled_in_window",
        "rotation_x_deg",
        "rotation_y_deg",
        "rotation_z_deg",
        "total_accel_at_trigger_mps2",
        "total_accel_at_trigger_g",
        "peak_total_accel_mps2",
        "peak_total_accel_g",
        "consistency_score",
        "baseline_progress",
        "left_peak",
        "right_peak",
        "left_share_percent",
        "beam_break_ms",
    ]

    sample_fields = [
        "wrist_shot_id",
        "relative_time_ms",
        "ax_mps2",
        "ay_mps2",
        "az_mps2",
        "gx_dps",
        "gy_dps",
        "gz_dps",
    ]

    summary_writer = csv.DictWriter(
        summary_file,
        fieldnames=summary_fields,
    )

    sample_writer = csv.DictWriter(
        sample_file,
        fieldnames=sample_fields,
    )

    summary_writer.writeheader()
    sample_writer.writeheader()

    return (
        summary_file,
        sample_file,
        summary_writer,
        sample_writer,
        summary_path,
        sample_path,
    )


async def run_live(
    hoop_mode: str,
    hoop_port: str | None,
) -> None:
    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    (
        summary_file,
        sample_file,
        summary_writer,
        sample_writer,
        summary_path,
        sample_path,
    ) = make_writers(timestamp)

    live_state_path = Path(
        LIVE_STATE_FILENAME
    )

    session = AnalyticsSession(
        summary_writer,
        sample_writer,
        summary_file,
        sample_file,
        live_state_path,
        timestamp,
    )

    session.publish_state(
        "CONNECTING",
        message=(
            "Connecting the wrist and hoop sensors."
        ),
    )

    incoming: queue.Queue[
        tuple[str, float, str]
    ] = queue.Queue()

    stop_event = threading.Event()
    scan_lock = asyncio.Lock()

    hoop_thread: threading.Thread | None = None
    hoop_task: asyncio.Task[None] | None = None

    if hoop_mode == "usb":
        if not hoop_port:
            raise ValueError(
                "USB hoop mode requires a serial port."
            )

        hoop_thread = threading.Thread(
            target=serial_reader,
            args=(
                "HOOP",
                hoop_port,
                incoming,
                stop_event,
            ),
            daemon=True,
        )

        hoop_thread.start()
    else:
        hoop_task = asyncio.create_task(
            ble_hoop_reader(
                incoming,
                stop_event,
                scan_lock,
            )
        )

    wrist_task = asyncio.create_task(
        ble_wrist_reader(
            incoming,
            stop_event,
            scan_lock,
        )
    )

    print()
    print(
        "ShotSync wireless analytics integrator running."
    )
    print(f"Wrist BLE device: {BLE_DEVICE_NAME}")

    if hoop_mode == "ble":
        print(
            "Hoop BLE device: "
            f"{HOOP_BLE_DEVICE_NAME}"
        )
    else:
        print(f"Hoop USB port: {hoop_port}")

    print(f"Summary CSV: {summary_path.resolve()}")
    print(f"Raw samples CSV: {sample_path.resolve()}")

    print(
        "Live dashboard state: "
        f"{live_state_path.resolve()}"
    )

    print("Press Control-C to stop.")
    print()

    try:
        while not stop_event.is_set():
            processed_message = False

            while True:
                try:
                    (
                        device_name,
                        arrival_time,
                        line,
                    ) = incoming.get_nowait()
                except queue.Empty:
                    break

                processed_message = True

                session.handle_line(
                    device_name,
                    arrival_time,
                    line,
                )

            session.expire_events(
                time.monotonic()
            )

            if not processed_message:
                await asyncio.sleep(0.02)

    except asyncio.CancelledError:
        print("\nStopping...")

    finally:
        stop_event.set()

        tasks = [wrist_task]

        if hoop_task is not None:
            tasks.append(hoop_task)

        for task in tasks:
            task.cancel()

        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        if hoop_thread is not None:
            hoop_thread.join(timeout=1)

        session.publish_state(
            "STOPPED",
            message="ShotSync is offline.",
        )

        summary_file.close()
        sample_file.close()

    print()
    print("SESSION SUMMARY")
    print(f"Paired shots: {session.paired_shots}")
    print(f"Makes: {session.makes}")
    print(f"Misses: {session.misses}")

    print(
        "Unconfirmed releases: "
        f"{session.unconfirmed_releases}"
    )

    print(
        "Unpaired hoop events: "
        f"{session.unpaired_hoop_events}"
    )

    session.print_outcome_comparisons()

    print()
    print(f"Saved summary: {summary_path.resolve()}")
    print(f"Saved samples: {sample_path.resolve()}")


def run_file(input_path: Path) -> None:
    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    (
        summary_file,
        sample_file,
        summary_writer,
        sample_writer,
        summary_path,
        sample_path,
    ) = make_writers(timestamp)

    session = AnalyticsSession(
        summary_writer,
        sample_writer,
        summary_file,
        sample_file,
        Path(LIVE_STATE_FILENAME),
        timestamp,
    )

    # File mode analyzes wrist blocks. It does not
    # invent hoop outcomes or paired-shot results.
    with input_path.open(
        "r",
        encoding="utf-8",
    ) as input_file:
        for line_number, raw_line in enumerate(
            input_file,
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                continue

            session.handle_line(
                "FILE",
                line_number / 1000.0,
                line,
            )

    summary_file.close()
    sample_file.close()

    print()
    print(
        "File analysis completed. "
        "No hoop outcomes were assigned."
    )
    print(
        f"Completed wrist blocks: "
        f"{len(session.completed_analytics)}"
    )

    for shot_id in sorted(
        session.completed_analytics
    ):
        item = session.completed_analytics[shot_id]

        print(
            f"Shot {shot_id}: "
            f"peak {item.peak_gyro_dps:.0f}°/s, "
            f"snap {item.snap_duration_ms:.0f} ms, "
            f"rotation Y {item.rotation_y_deg:.1f}°"
        )

    print(f"Raw samples saved: {sample_path.resolve()}")
    print(
        "The summary CSV remains empty in file mode "
        "because no paired hoop records were present."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Combine basketball wrist motion records "
            "with hoop outcomes and calculate analytics."
        )
    )

    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--live",
        action="store_true",
        help=(
            "Read the wrist over BLE and the hoop "
            "over BLE or USB."
        ),
    )

    mode.add_argument(
        "--input-file",
        type=Path,
        help=(
            "Analyze an existing text capture "
            "containing WRIST_BEGIN/SAMPLE/END records."
        ),
    )

    parser.add_argument(
        "--hoop-mode",
        choices=("ble", "usb"),
        default="ble",
        help=(
            "Hoop connection type. Default: ble."
        ),
    )

    parser.add_argument(
        "--hoop",
        help=(
            "Hoop serial port when "
            "--hoop-mode usb is used."
        ),
    )

    args = parser.parse_args()

    if args.live:
        if (
            args.hoop_mode == "usb"
            and not args.hoop
        ):
            parser.error(
                "--hoop-mode usb requires --hoop."
            )

        try:
            asyncio.run(
                run_live(
                    args.hoop_mode,
                    args.hoop,
                )
            )
        except KeyboardInterrupt:
            print("\nStopped.")

    else:
        run_file(args.input_file)


if __name__ == "__main__":
    main()
