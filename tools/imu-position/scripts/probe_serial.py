"""CLI: probe the BMI160 serial stream without the GUI.

Diagnoses the most common failure modes:
  exit 0  samples received
  exit 2  port opened but no bytes at all (board hung / wrong port / no firmware output)
  exit 3  bytes received but no valid samples (wrong firmware, wrong baud, garbled)

By default the board is reset via RTS (EN) after opening; observed on this
board that an idle ESP32-S3 stops emitting until it is reset.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imu_position.csvio import parse_config_line  # noqa: E402
from imu_position.serial_reader import ImuSerialReader, list_serial_ports  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe the BMI160 serial stream.")
    parser.add_argument("-p", "--port", default=None, help="serial port (default: first found)")
    parser.add_argument("-t", "--seconds", type=float, default=6.0, help="listen duration (default 6 s)")
    parser.add_argument("--no-reset", action="store_true", help="do not pulse RTS (EN) after opening")
    args = parser.parse_args(argv)

    ports = list_serial_ports()
    port = args.port or (ports[0] if ports else None)
    if not port:
        print("no serial ports found; connect the board and check the CH340 driver")
        return 2
    print(f"ports: {', '.join(ports)}")
    print(f"probing {port} @115200 for {args.seconds:.1f}s (reset_on_open={not args.no_reset})")

    samples = []
    configs = []
    reader = ImuSerialReader(
        port,
        on_sample=samples.append,
        on_status=lambda text: print(f"[status] {text}"),
        on_fatal=lambda reason: print(f"[fatal] {reason}"),
        reset_on_open=not args.no_reset,
    )
    reader.parser.on_config = lambda line, valid: configs.append(parse_config_line(line))
    try:
        reader.start()
    except Exception as error:
        print(f"open failed: {error}")
        return 2

    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline:
            time.sleep(0.2)
            if reader.parser.stats.fatal_reason:
                break
    finally:
        stats = reader.parser.stats
        reader.stop()

    print(
        f"lines={{'received': {stats.lines_received}, 'samples': {stats.samples}, "
        f"'ignored': {stats.ignored_lines}, 'malformed': {stats.malformed_rows}, "
        f"'gaps': {stats.sequence_gaps}, 'configs': {stats.config_reports}}}"
    )
    for config in configs:
        print("config:", "OK" if config.valid else f"PROBLEMS {config.problems}", "address", config.address)
    if samples:
        first, last = samples[0], samples[-1]
        span = (last.t_read_us - first.t_read_us) / 1e6
        rate = (len(samples) - 1) / span if span > 0 else 0.0
        print(f"samples: {len(samples)}, span {span:.2f}s, rate {rate:.2f} Hz")
        return 0
    if stats.lines_received == 0:
        print("no bytes received: board appears silent (try without --no-reset, or re-flash BMI160_SixAxis_v3_autoaddr)")
        return 2
    print("bytes received but no valid samples: wrong firmware or baud rate?")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
