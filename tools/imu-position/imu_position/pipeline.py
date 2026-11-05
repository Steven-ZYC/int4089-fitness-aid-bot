"""Zero-drift processing: bias removal, static detection, attitude and position.

Conventions:
- Body axes are the BMI160 axes as reported (g and deg/s).
- Gravity points along +z in the body frame when the board lies flat.
- The complementary filter estimates roll/pitch from accelerometer and gyro;
  yaw is gyroscope-only because the BMI160 has no magnetometer, so yaw is
  unobservable and drifts. The linear-acceleration output stays in the body
  frame (no unobservable yaw rotation is applied).

ZUPT (zero-velocity update) freezes velocity and position whenever the
windowed statistics look stationary. This is what keeps a stationary board
at the origin; it is not a general-purpose dead-reckoning solution.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from statistics import pstdev
from typing import Deque, Iterable, Sequence

from .csvio import Sample
from .profile import Profile

GRAVITY_M_S2 = 9.80665


@dataclass(frozen=True)
class ProcessedSample:
    seq: int
    t_s: float
    dt_s: float
    gyro_raw_dps: tuple[float, float, float]
    gyro_dps: tuple[float, float, float]
    accel_g: tuple[float, float, float]
    accel_norm_g: float
    accel_norm_std_g: float
    gyro_norm_std_dps: float
    linear_body_g: tuple[float, float, float]
    roll_deg: float
    pitch_deg: float
    yaw_deg: float
    velocity_m_s: tuple[float, float, float]
    position_m: tuple[float, float, float]
    is_static: bool
    warmup: bool


def accel_roll_pitch_deg(ax: float, ay: float, az: float) -> tuple[float, float]:
    """Roll/pitch in degrees from the acceleration vector (Z-Y-X convention)."""
    roll = math.degrees(math.atan2(ay, az))
    pitch = math.degrees(math.atan2(-ax, math.hypot(ay, az)))
    return roll, pitch


def gravity_body_g(roll_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    """Unit gravity direction expressed in the body frame."""
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    return (
        -math.sin(pitch),
        math.sin(roll) * math.cos(pitch),
        math.cos(roll) * math.cos(pitch),
    )


def euler_rates_from_body(roll_deg: float, pitch_deg: float, gyro_dps: Sequence[float]) -> tuple[float, float, float]:
    """Convert body rates (p, q, r) to Euler rates (roll, pitch, yaw), deg/s."""
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    p, q, r = gyro_dps
    sin_r, cos_r = math.sin(roll), math.cos(roll)
    tan_p = math.tan(pitch)
    cos_p = math.cos(pitch)
    if abs(cos_p) < 1e-6:
        cos_p = math.copysign(1e-6, cos_p)
    roll_dot = p + q * sin_r * tan_p + r * cos_r * tan_p
    pitch_dot = q * cos_r - r * sin_r
    yaw_dot = (q * sin_r + r * cos_r) / cos_p
    return roll_dot, pitch_dot, yaw_dot


def vector_norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


class DriftProcessor:
    """Streaming state machine shared by live serial input and CSV replay."""

    def __init__(self, profile: Profile, window_samples: int | None = None) -> None:
        profile.validate()
        self.profile = profile
        self.bias = profile.gyro_bias_dps.as_tuple()
        detection = profile.static_detection
        estimated_rate = profile.source.rate_hz or profile.sensor.odr_hz or 50.0
        if window_samples is None:
            window_samples = max(3, int(round(detection.window_s * estimated_rate)))
        self.window_samples = window_samples
        self._accel_norm_window: Deque[float] = deque(maxlen=window_samples)
        self._gyro_norm_window: Deque[float] = deque(maxlen=window_samples)

        self.roll_deg = profile.mounting_tilt_deg.roll_deg
        self.pitch_deg = profile.mounting_tilt_deg.pitch_deg
        self.yaw_deg = 0.0
        self.velocity = [0.0, 0.0, 0.0]
        self.position = [0.0, 0.0, 0.0]
        self._linear_prev = (0.0, 0.0, 0.0)
        self._velocity_prev = (0.0, 0.0, 0.0)
        self._last_read_us: int | None = None
        self._start_us: int | None = None

    def reset_origin(self) -> None:
        """Re-zero velocity and position without touching attitude."""
        self.velocity = [0.0, 0.0, 0.0]
        self.position = [0.0, 0.0, 0.0]
        self._velocity_prev = (0.0, 0.0, 0.0)

    def reset(self) -> None:
        self.__init__(self.profile, self.window_samples)

    def _dt_seconds(self, sample: Sample) -> float:
        if self._last_read_us is None:
            self._start_us = sample.t_read_us
            self._last_read_us = sample.t_read_us
            return 0.0
        dt = (sample.t_read_us - self._last_read_us) / 1_000_000.0
        self._last_read_us = sample.t_read_us
        if dt <= 0:
            return 0.0
        return min(dt, self.profile.integration.max_dt_s)

    def _static_statistics(self, gyro_norm: float, accel_norm: float) -> tuple[float, float]:
        self._accel_norm_window.append(accel_norm)
        self._gyro_norm_window.append(gyro_norm)
        if len(self._accel_norm_window) < self.window_samples:
            return 0.0, 0.0
        return (
            pstdev(self._accel_norm_window),
            pstdev(self._gyro_norm_window),
        )

    def process(self, sample: Sample) -> ProcessedSample:
        profile = self.profile
        dt = self._dt_seconds(sample)

        raw_gyro = sample.gyro()
        gyro = (
            raw_gyro[0] - self.bias[0],
            raw_gyro[1] - self.bias[1],
            raw_gyro[2] - self.bias[2],
        )
        accel = sample.accel()
        accel_norm = vector_norm(accel)
        gyro_norm = vector_norm(gyro)
        accel_std, gyro_std = self._static_statistics(gyro_norm, accel_norm)

        detection = profile.static_detection
        window_ready = len(self._accel_norm_window) >= self.window_samples
        is_static = (
            window_ready
            and accel_std <= detection.accel_norm_std_max_g
            and gyro_std <= detection.gyro_std_max_dps
            and gyro_norm <= detection.gyro_abs_max_dps
            and detection.accel_norm_min_g <= accel_norm <= detection.accel_norm_max_g
        )

        accel_roll, accel_pitch = accel_roll_pitch_deg(*accel)
        warmup = not window_ready
        if dt > 0:
            roll_rate, pitch_rate, yaw_rate = euler_rates_from_body(
                self.roll_deg, self.pitch_deg, gyro
            )
            if is_static:
                # Residual rates are noise while the board is still; do not
                # let yaw integrate them into unbounded heading drift.
                yaw_rate = 0.0
            alpha = profile.complementary_filter.alpha
            self.roll_deg = alpha * (self.roll_deg + roll_rate * dt) + (1.0 - alpha) * accel_roll
            self.pitch_deg = alpha * (self.pitch_deg + pitch_rate * dt) + (1.0 - alpha) * accel_pitch
            self.yaw_deg += yaw_rate * dt

        gx, gy, gz = gravity_body_g(self.roll_deg, self.pitch_deg)
        linear = (accel[0] - gx, accel[1] - gy, accel[2] - gz)

        if dt > 0 and not warmup:
            if is_static and profile.integration.zupt_holds_velocity:
                velocity = (0.0, 0.0, 0.0)
            else:
                velocity = tuple(
                    self._velocity_prev[axis]
                    + 0.5 * (self._linear_prev[axis] + linear[axis]) * GRAVITY_M_S2 * dt
                    for axis in range(3)
                )
            position = tuple(
                self.position[axis] + 0.5 * (self._velocity_prev[axis] + velocity[axis]) * dt
                for axis in range(3)
            )
            if is_static and profile.integration.zupt_holds_velocity:
                position = tuple(self.position)
            self.velocity = list(velocity)
            self.position = list(position)
            self._velocity_prev = velocity
            self._linear_prev = linear

        t_s = 0.0
        if self._start_us is not None:
            t_s = (sample.t_read_us - self._start_us) / 1_000_000.0

        return ProcessedSample(
            seq=sample.seq,
            t_s=t_s,
            dt_s=dt,
            gyro_raw_dps=raw_gyro,
            gyro_dps=gyro,
            accel_g=accel,
            accel_norm_g=accel_norm,
            accel_norm_std_g=accel_std,
            gyro_norm_std_dps=gyro_std,
            linear_body_g=linear,
            roll_deg=self.roll_deg,
            pitch_deg=self.pitch_deg,
            yaw_deg=self.yaw_deg,
            velocity_m_s=tuple(self.velocity),
            position_m=tuple(self.position),
            is_static=is_static,
            warmup=warmup,
        )


def process_samples(profile: Profile, samples: Iterable[Sample]) -> list[ProcessedSample]:
    processor = DriftProcessor(profile)
    return [processor.process(sample) for sample in samples]


def summarize(samples: Sequence[Sample], processed: Sequence[ProcessedSample]) -> dict:
    """Drift metrics used by the CLI replay check and the UI summary strip."""
    if not processed:
        return {}
    static_count = sum(1 for row in processed if row.is_static)
    warmup_count = sum(1 for row in processed if row.warmup)
    gyro = [row.gyro_dps for row in processed]
    residual_means = [sum(axis[i] for axis in gyro) / len(gyro) for i in range(3)]
    residual_rms = math.sqrt(
        sum(value * value for axis in gyro for value in axis) / (3 * len(gyro))
    )
    positions = [row.position_m for row in processed]
    max_position = max(vector_norm(position) for position in positions)
    final_position = vector_norm(positions[-1])
    velocities = [row.velocity_m_s for row in processed]
    max_velocity = max(vector_norm(velocity) for velocity in velocities)
    span = processed[-1].t_s - processed[0].t_s
    return {
        "samples": len(processed),
        "span_s": round(span, 3),
        "rate_hz": round((len(processed) - 1) / span, 3) if span > 0 else 0.0,
        "static_fraction": round(static_count / len(processed), 4),
        "warmup_samples": warmup_count,
        "corrected_gyro_mean_dps": [round(value, 4) for value in residual_means],
        "corrected_gyro_rms_dps": round(residual_rms, 4),
        "max_velocity_m_s": round(max_velocity, 5),
        "max_position_m": round(max_position, 5),
        "final_position_m": round(final_position, 5),
        "final_velocity_m_s": round(vector_norm(velocities[-1]), 5),
        "final_attitude_deg": {
            "roll": round(processed[-1].roll_deg, 3),
            "pitch": round(processed[-1].pitch_deg, 3),
            "yaw": round(processed[-1].yaw_deg, 3),
        },
        "started_us": samples[0].t_read_us if samples else 0,
    }
