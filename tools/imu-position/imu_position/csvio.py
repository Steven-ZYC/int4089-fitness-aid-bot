"""Parser for the BMI160 six-axis CSV stream.

Mirrors the schema and validation rules of
firmware/esp32-camera/capture_bmi160.ps1 so live serial input and archived
capture files go through identical checks. ``t_read_us`` is the ESP32-S3
timer sampled just before the I2C burst, not an exact sensor sample time;
``sensor_ticks`` is the 24-bit BMI160 clock (39.0625 us per tick).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

CSV_HEADER = (
    "sample_seq,t_read_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,"
    "ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps"
)

COLUMN_COUNT = 15
EXPECTED_ADDRESSES = ("0x68", "0x69")
EXPECTED_FIRMWARE = "BMI160_SixAxis_v3_autoaddr"
EXPECTED_CONFIG_FIELDS = (
    "chip_id=0xD1",
    "acc_conf=0x27",
    "acc_range=0x05",
    "gyr_conf=0x27",
    "gyr_range=0x02",
    "pmu=0x14",
    "err=0x00",
    "odr_hz=50",
    "calibrated=NO",
)
MAX_SENSOR_TICKS = 16_777_215


class LineParseError(ValueError):
    """A numeric data line violated the firmware schema."""


@dataclass(frozen=True)
class Sample:
    seq: int
    t_read_us: int
    sensor_ticks: int
    ax_g: float
    ay_g: float
    az_g: float
    gx_dps: float
    gy_dps: float
    gz_dps: float
    ax_raw: int
    ay_raw: int
    az_raw: int
    gx_raw: int
    gy_raw: int
    gz_raw: int

    def gyro(self) -> tuple[float, float, float]:
        return (self.gx_dps, self.gy_dps, self.gz_dps)

    def accel(self) -> tuple[float, float, float]:
        return (self.ax_g, self.ay_g, self.az_g)

    def to_csv_line(self) -> str:
        return (
            f"{self.seq},{self.t_read_us},{self.sensor_ticks},"
            f"{self.ax_raw},{self.ay_raw},{self.az_raw},"
            f"{self.gx_raw},{self.gy_raw},{self.gz_raw},"
            f"{self.ax_g:.5f},{self.ay_g:.5f},{self.az_g:.5f},"
            f"{self.gx_dps:.4f},{self.gy_dps:.4f},{self.gz_dps:.4f}"
        )


@dataclass(frozen=True)
class ConfigInfo:
    raw_line: str
    fields: dict[str, str]
    problems: tuple[str, ...]
    address: str

    @property
    def valid(self) -> bool:
        return not self.problems


def is_diagnostic(line: str) -> bool:
    return line.startswith("#")


def is_data_line(line: str) -> bool:
    return bool(line) and line[0].isdigit()


def parse_diagnostic(line: str) -> tuple[str, dict[str, str]]:
    """Split a ``#`` line into (kind, key=value fields)."""
    body = line[1:].strip()
    if not body:
        return "OTHER", {}
    parts = body.split()
    kind = parts[0]
    fields: dict[str, str] = {}
    for token in parts[1:]:
        if "=" in token:
            key, _, value = token.partition("=")
            fields[key] = value
    return kind, fields


def parse_config_line(line: str) -> ConfigInfo:
    _, fields = parse_diagnostic(line)
    problems: list[str] = []
    if fields.get("address") not in EXPECTED_ADDRESSES:
        problems.append(f"unexpected address {fields.get('address')!r}")
    if fields.get("firmware") != EXPECTED_FIRMWARE:
        problems.append(f"unexpected firmware {fields.get('firmware')!r}")
    for expected in EXPECTED_CONFIG_FIELDS:
        key, _, value = expected.partition("=")
        if fields.get(key) != value:
            problems.append(f"expected {expected}, got {key}={fields.get(key)!r}")
    return ConfigInfo(
        raw_line=line,
        fields=fields,
        problems=tuple(problems),
        address=fields.get("address", ""),
    )


def parse_data_line(line: str) -> Sample:
    """Parse one numeric CSV row; raise LineParseError when malformed."""
    parts = line.split(",")
    if len(parts) != COLUMN_COUNT:
        raise LineParseError(f"expected {COLUMN_COUNT} columns, got {len(parts)}")
    try:
        values = [float(part) for part in parts]
    except ValueError as error:
        raise LineParseError(f"non-numeric field: {error}") from error
    if any(not math.isfinite(value) for value in values):
        raise LineParseError("non-finite value")

    seq, read_us, ticks = values[0], values[1], values[2]
    if seq < 1 or seq != int(seq):
        raise LineParseError("invalid sample sequence")
    if read_us < 0:
        raise LineParseError("negative read timestamp")
    if ticks < 0 or ticks > MAX_SENSOR_TICKS or ticks != int(ticks):
        raise LineParseError("sensor clock out of range")
    raw = values[3:9]
    for value in raw:
        if value != int(value) or not -32768 <= value <= 32767:
            raise LineParseError("raw sample outside int16 range")

    return Sample(
        seq=int(seq),
        t_read_us=int(read_us),
        sensor_ticks=int(ticks),
        ax_raw=int(raw[0]),
        ay_raw=int(raw[1]),
        az_raw=int(raw[2]),
        gx_raw=int(raw[3]),
        gy_raw=int(raw[4]),
        gz_raw=int(raw[5]),
        ax_g=values[9],
        ay_g=values[10],
        az_g=values[11],
        gx_dps=values[12],
        gy_dps=values[13],
        gz_dps=values[14],
    )


def read_capture(path: str | Path) -> list[Sample]:
    """Load a capture CSV written by capture_bmi160.ps1 (header optional)."""
    samples: list[Sample] = []
    last_seq: Optional[int] = None
    last_read_us: Optional[int] = None
    bad_rows = 0
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line == CSV_HEADER or is_diagnostic(line):
                continue
            if not is_data_line(line):
                bad_rows += 1
                continue
            try:
                sample = parse_data_line(line)
            except LineParseError:
                bad_rows += 1
                continue
            if last_seq is not None and sample.seq != last_seq + 1:
                raise LineParseError(
                    f"sequence discontinuity at row {len(samples) + 1}: "
                    f"{last_seq} -> {sample.seq}"
                )
            if last_read_us is not None and sample.t_read_us <= last_read_us:
                raise LineParseError(f"non-monotonic timestamp at seq {sample.seq}")
            samples.append(sample)
            last_seq = sample.seq
            last_read_us = sample.t_read_us
    if not samples:
        raise LineParseError(f"{path}: no numeric samples found")
    if bad_rows:
        raise LineParseError(f"{path}: {bad_rows} malformed rows")
    return samples


def read_serial_log(path: str | Path) -> Iterator[str]:
    """Yield non-empty stripped lines from a saved serial log."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                yield line


def iter_samples(lines: Iterable[str]) -> Iterator[Sample]:
    """Yield parsed samples from raw stream lines, skipping diagnostics."""
    for line in lines:
        line = line.strip()
        if not line or is_diagnostic(line) or line == CSV_HEADER:
            continue
        if is_data_line(line):
            yield parse_data_line(line)


def load_capture_summary(path: str | Path) -> dict:
    """Load the capture_bmi160.ps1 JSON summary (may be absent)."""
    summary_path = Path(path)
    if summary_path.suffix.lower() == ".csv":
        summary_path = summary_path.with_suffix(".json")
    try:
        return json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_rate_hz(samples: list[Sample]) -> float:
    if len(samples) < 2:
        return 0.0
    span_us = samples[-1].t_read_us - samples[0].t_read_us
    if span_us <= 0:
        return 0.0
    return (len(samples) - 1) * 1_000_000.0 / span_us
