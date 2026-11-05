"""Fit a zero-drift profile from a stationary BMI160 capture.

The capture must pass the same stationary gates as the upstream
check_bmi160_gyro_bias.ps1: transport checks passed, no clipping, accel
norm 0.85-1.15 g, accel axis stddev <= 0.02 g, gyro stddev <= 0.2 dps and
|gyro mean| <= 5 dps. Bias is the per-axis gyro mean; the accelerometer
mean vector is stored as-is because it carries gravity and mounting tilt.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime
from pathlib import Path
from statistics import pstdev

from .csvio import Sample, load_capture_summary, read_capture, read_rate_hz
from .profile import (
    ACCEL_AXIS_STD_LIMIT_G,
    ACCEL_NORM_MAX_G,
    ACCEL_NORM_MIN_G,
    GYRO_STD_LIMIT_DPS,
    MAX_CAPTURE_RATE_HZ,
    MIN_CAPTURE_RATE_HZ,
    RESIDUAL_LIMIT_DPS,
    ComplementaryFilter,
    Integration,
    Profile,
    ProfileError,
    SensorConfig,
    SourceInfo,
    StaticDetection,
    Tilt,
    Validation,
    Vec3,
)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def calibration_gate_problems(samples: list[Sample]) -> list[str]:
    """Stationary-capture gates that must pass before bias fitting."""
    problems: list[str] = []
    if len(samples) < 100:
        problems.append(f"only {len(samples)} samples; need at least 100 for a stable bias")
    rate = read_rate_hz(samples)
    if not MIN_CAPTURE_RATE_HZ <= rate <= MAX_CAPTURE_RATE_HZ:
        problems.append(f"capture rate {rate:.2f} Hz is outside {MIN_CAPTURE_RATE_HZ}-{MAX_CAPTURE_RATE_HZ} Hz")

    raw_columns = [sample.ax_raw for sample in samples] + [
        sample.ay_raw for sample in samples
    ] + [
        sample.az_raw for sample in samples
    ] + [
        sample.gx_raw for sample in samples
    ] + [
        sample.gy_raw for sample in samples
    ] + [
        sample.gz_raw for sample in samples
    ]
    if any(abs(value) >= 32760 for value in raw_columns):
        problems.append("clipping detected in raw samples")

    accel_norm = [math.sqrt(a * a + b * b + c * c) for a, b, c in (sample.accel() for sample in samples)]
    norm_mean = _mean(accel_norm)
    if not ACCEL_NORM_MIN_G <= norm_mean <= ACCEL_NORM_MAX_G:
        problems.append(f"accel norm mean {norm_mean:.4f} g is outside {ACCEL_NORM_MIN_G}-{ACCEL_NORM_MAX_G} g")
    for axis, values in zip(("ax", "ay", "az"), zip(*(sample.accel() for sample in samples))):
        deviation = pstdev(values)
        if deviation > ACCEL_AXIS_STD_LIMIT_G:
            problems.append(f"accel {axis} stddev {deviation:.4f} g exceeds {ACCEL_AXIS_STD_LIMIT_G} g; capture is not stationary")
    for axis, values in zip(("gx", "gy", "gz"), zip(*(sample.gyro() for sample in samples))):
        deviation = pstdev(values)
        mean = _mean(values)
        if deviation > GYRO_STD_LIMIT_DPS:
            problems.append(f"gyro {axis} stddev {deviation:.4f} dps exceeds {GYRO_STD_LIMIT_DPS} dps")
        if abs(mean) > 5.0:
            problems.append(f"gyro {axis} mean {mean:.4f} dps exceeds 5 dps")
    return problems


def build_profile(
    capture_path: str | Path,
    name: str,
    profile_dir: str | Path,
    created_at: str | None = None,
) -> Profile:
    """Fit and validate a profile; raise ProfileError when gates fail."""
    capture = Path(capture_path)
    if not capture.is_file():
        raise ProfileError(f"capture not found: {capture}")
    samples = read_capture(capture)
    problems = calibration_gate_problems(samples)
    if problems:
        raise ProfileError("stationary capture gate failed: " + "; ".join(problems))

    summary = load_capture_summary(capture)
    if summary.get("transport_check_passed") is False:
        raise ProfileError("capture summary reports transport_check_passed=false")
    if summary.get("clipping_rows", 0):
        raise ProfileError("capture summary reports clipping rows")

    gyro = list(zip(*(sample.gyro() for sample in samples)))
    accel = list(zip(*(sample.accel() for sample in samples)))
    bias = [round(_mean(values), 6) for values in gyro]
    accel_mean = Vec3(*(round(_mean(values), 6) for values in accel))

    half = len(samples) // 2
    holdout = samples[half:]
    holdout_means = [_mean(values) for values in zip(*(sample.gyro() for sample in holdout))]
    residual_means = [value - bias[axis] for axis, value in enumerate(holdout_means)]
    residual_rms = math.sqrt(
        sum(
            (value - bias[axis]) ** 2
            for sample in holdout
            for axis, value in enumerate(sample.gyro())
        )
        / (3 * len(holdout))
    )
    max_residual = max(abs(value) for value in residual_means)
    gate_pass = max_residual <= RESIDUAL_LIMIT_DPS and residual_rms <= RESIDUAL_LIMIT_DPS

    roll = math.degrees(math.atan2(accel_mean.y, accel_mean.z))
    pitch = math.degrees(math.atan2(-accel_mean.x, math.hypot(accel_mean.y, accel_mean.z)))
    rate = read_rate_hz(samples)
    span = (samples[-1].t_read_us - samples[0].t_read_us) / 1_000_000.0

    try:
        csv_label = str(capture.resolve().relative_to(Path(profile_dir).resolve().parent.parent.parent))
    except ValueError:
        csv_label = str(capture)

    profile = Profile(
        name=name,
        created_at=created_at or datetime.now().strftime("%Y-%m-%d"),
        source=SourceInfo(
            csv=csv_label.replace("\\", "/"),
            sha256=_sha256(capture),
            rows=len(samples),
            duration_s=round(span, 3),
            rate_hz=round(rate, 3),
            port=str(summary.get("port", "")),
            address=str(summary.get("address", "")).replace("address=", ""),
            captured_at=str(summary.get("capture_start_utc", "")),
        ),
        sensor=SensorConfig(),
        gyro_bias_dps=Vec3(*bias),
        accel_mean_g=accel_mean,
        mounting_tilt_deg=Tilt(roll_deg=round(roll, 3), pitch_deg=round(pitch, 3)),
        static_detection=StaticDetection(),
        complementary_filter=ComplementaryFilter(),
        integration=Integration(),
        validation=Validation(
            residual_vector_rms_dps=round(residual_rms, 4),
            max_residual_mean_dps=round(max_residual, 4),
            gate_pass=gate_pass,
            gates=(
                "transport pass, no clipping, accel norm 0.85-1.15 g, accel axis stddev "
                "<=0.02 g, gyro stddev <=0.2 dps, |gyro mean| <=5 dps, second-half "
                "residual mean/RMS <=0.1 dps"
            ),
        ),
    )
    profile.validate()
    return profile
