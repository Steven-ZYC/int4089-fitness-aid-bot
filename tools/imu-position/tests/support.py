"""Shared helpers: synthetic BMI160 samples with known physical truth."""

from __future__ import annotations

import math
import random
from pathlib import Path

from imu_position.csvio import CSV_HEADER, Sample
from imu_position.profile import Profile, SensorConfig, SourceInfo, Vec3

REPO_ROOT = Path(__file__).resolve().parents[3]
STATIC_CAPTURE = (
    REPO_ROOT / "firmware" / "esp32-camera" / "evidence" / "yancheng-2026-11-05" / "capture.csv"
)
STATIC_PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "yancheng-2026-11-05-static.json"

RATE_HZ = 50.0


def make_sample(
    seq: int,
    gyro_dps: tuple[float, float, float],
    accel_g: tuple[float, float, float],
    rate_hz: float = RATE_HZ,
    start_us: int = 10_000_000,
) -> Sample:
    dt_us = int(round(1_000_000 / rate_hz))
    return Sample(
        seq=seq,
        t_read_us=start_us + (seq - 1) * dt_us,
        sensor_ticks=(seq * 512) % 16_777_216,
        ax_g=accel_g[0],
        ay_g=accel_g[1],
        az_g=accel_g[2],
        gx_dps=gyro_dps[0],
        gy_dps=gyro_dps[1],
        gz_dps=gyro_dps[2],
        ax_raw=int(round(accel_g[0] * 8192.0)),
        ay_raw=int(round(accel_g[1] * 8192.0)),
        az_raw=int(round(accel_g[2] * 8192.0)),
        gx_raw=int(round(gyro_dps[0] * 65.6)),
        gy_raw=int(round(gyro_dps[1] * 65.6)),
        gz_raw=int(round(gyro_dps[2] * 65.6)),
    )


def synthetic_static(
    count: int = 500,
    bias_dps: tuple[float, float, float] = (0.3, -0.2, 0.1),
    noise_dps: float = 0.02,
    accel_noise_g: float = 0.001,
    seed: int = 7,
) -> list[Sample]:
    rng = random.Random(seed)
    samples = []
    for seq in range(1, count + 1):
        gyro = tuple(value + rng.gauss(0.0, noise_dps) for value in bias_dps)
        accel = (rng.gauss(0.0, accel_noise_g), rng.gauss(0.0, accel_noise_g), 1.0 + rng.gauss(0.0, accel_noise_g))
        samples.append(make_sample(seq, gyro, accel))
    return samples


def yaw_rotation_samples(
    rate_dps: float = 50.0,
    duration_s: float = 1.0,
    rate_hz: float = RATE_HZ,
    accel_g: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> list[Sample]:
    """Rotate around the body z axis at a constant rate (perfectly static accel)."""
    count = int(round(duration_s * rate_hz))
    return [
        make_sample(seq, (0.0, 0.0, rate_dps), accel_g, rate_hz=rate_hz)
        for seq in range(1, count + 1)
    ]


def identity_profile(**overrides) -> Profile:
    profile = Profile(
        name="test",
        source=SourceInfo(rate_hz=RATE_HZ),
        sensor=SensorConfig(),
        accel_mean_g=Vec3(0.0, 0.0, 1.0),
        validation=__import__("imu_position.profile", fromlist=["Validation"]).Validation(
            gate_pass=True
        ),
    )
    for key, value in overrides.items():
        setattr(profile, key, value)
    return profile


def write_capture_csv(path: Path, samples: list[Sample]) -> Path:
    lines = [CSV_HEADER] + [sample.to_csv_line() for sample in samples]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


__all__ = [
    "REPO_ROOT",
    "STATIC_CAPTURE",
    "STATIC_PROFILE",
    "identity_profile",
    "make_sample",
    "synthetic_static",
    "write_capture_csv",
    "yaw_rotation_samples",
    "math",
]
