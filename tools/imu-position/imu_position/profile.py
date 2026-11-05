"""Zero-drift profile schema, JSON I/O and validation.

A profile is the single source of truth for how raw BMI160 samples are
corrected on the PC: gyroscope bias, mounting tilt reference, static
detection thresholds, attitude-filter and integration settings. It
deliberately stores the accelerometer mean vector instead of an
accelerometer bias: that vector encodes the mounting tilt and gravity,
which must be preserved rather than subtracted.

Validation gates mirror firmware/esp32-camera/check_bmi160_gyro_bias.ps1
from the upstream branch (accel norm 0.85-1.15 g, axis stddev <= 0.02 g,
gyro stddev <= 0.2 dps, |gyro mean| <= 5 dps, residual <= 0.1 dps).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "imu-zero-drift-profile/1"
FORMAT_VERSION = 1

GYRO_BIAS_LIMIT_DPS = 5.0
RESIDUAL_LIMIT_DPS = 0.1
ACCEL_NORM_MIN_G = 0.85
ACCEL_NORM_MAX_G = 1.15
ACCEL_AXIS_STD_LIMIT_G = 0.02
GYRO_STD_LIMIT_DPS = 0.2
MIN_CAPTURE_RATE_HZ = 45.0
MAX_CAPTURE_RATE_HZ = 55.0


class ProfileError(ValueError):
    """Raised when a profile is structurally invalid or fails hard gates."""


def _mapping(data: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ProfileError(f"{label} must be a JSON object")
    return data


def _number(data: Mapping[str, Any], key: str, default: float | None = None) -> float:
    if key not in data:
        if default is None:
            raise ProfileError(f"missing numeric field '{key}'")
        return float(default)
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"field '{key}' must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ProfileError(f"field '{key}' must be finite")
    return value


def _integer(data: Mapping[str, Any], key: str, default: int | None = None) -> int:
    value = _number(data, key, None if default is None else float(default))
    if value != int(value):
        raise ProfileError(f"field '{key}' must be an integer")
    return int(value)


def _text(data: Mapping[str, Any], key: str, default: str = "") -> str:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, str):
        raise ProfileError(f"field '{key}' must be text")
    return value


def _boolean(data: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise ProfileError(f"field '{key}' must be a boolean")
    return value


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def norm(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, data: Any, label: str) -> "Vec3":
        data = _mapping(data, label)
        return cls(_number(data, "x"), _number(data, "y"), _number(data, "z"))


@dataclass
class Tilt:
    roll_deg: float = 0.0
    pitch_deg: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"roll_deg": self.roll_deg, "pitch_deg": self.pitch_deg}

    @classmethod
    def from_dict(cls, data: Any, label: str) -> "Tilt":
        data = _mapping(data, label)
        return cls(_number(data, "roll_deg"), _number(data, "pitch_deg"))


@dataclass
class SourceInfo:
    csv: str = ""
    sha256: str = ""
    rows: int = 0
    duration_s: float = 0.0
    rate_hz: float = 0.0
    port: str = ""
    address: str = ""
    captured_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "csv": self.csv,
            "sha256": self.sha256,
            "rows": self.rows,
            "duration_s": self.duration_s,
            "rate_hz": self.rate_hz,
            "port": self.port,
            "address": self.address,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SourceInfo":
        data = _mapping(data, "source")
        return cls(
            csv=_text(data, "csv"),
            sha256=_text(data, "sha256"),
            rows=_integer(data, "rows", 0),
            duration_s=_number(data, "duration_s", 0.0),
            rate_hz=_number(data, "rate_hz", 0.0),
            port=_text(data, "port"),
            address=_text(data, "address"),
            captured_at=_text(data, "captured_at"),
        )


@dataclass
class SensorConfig:
    accel_range_g: float = 4.0
    gyro_range_dps: float = 500.0
    odr_hz: float = 50.0
    accel_lsb_per_g: float = 8192.0
    gyro_lsb_per_dps: float = 65.6

    def to_dict(self) -> dict[str, float]:
        return {
            "accel_range_g": self.accel_range_g,
            "gyro_range_dps": self.gyro_range_dps,
            "odr_hz": self.odr_hz,
            "accel_lsb_per_g": self.accel_lsb_per_g,
            "gyro_lsb_per_dps": self.gyro_lsb_per_dps,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SensorConfig":
        data = _mapping(data, "sensor")
        return cls(
            accel_range_g=_number(data, "accel_range_g", 4.0),
            gyro_range_dps=_number(data, "gyro_range_dps", 500.0),
            odr_hz=_number(data, "odr_hz", 50.0),
            accel_lsb_per_g=_number(data, "accel_lsb_per_g", 8192.0),
            gyro_lsb_per_dps=_number(data, "gyro_lsb_per_dps", 65.6),
        )


@dataclass
class StaticDetection:
    window_s: float = 1.0
    accel_norm_std_max_g: float = 0.05
    gyro_std_max_dps: float = 0.15
    gyro_abs_max_dps: float = 1.0
    accel_norm_min_g: float = 0.9
    accel_norm_max_g: float = 1.1

    def to_dict(self) -> dict[str, float]:
        return {
            "window_s": self.window_s,
            "accel_norm_std_max_g": self.accel_norm_std_max_g,
            "gyro_std_max_dps": self.gyro_std_max_dps,
            "gyro_abs_max_dps": self.gyro_abs_max_dps,
            "accel_norm_min_g": self.accel_norm_min_g,
            "accel_norm_max_g": self.accel_norm_max_g,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "StaticDetection":
        data = _mapping(data, "static_detection")
        return cls(
            window_s=_number(data, "window_s", 1.0),
            accel_norm_std_max_g=_number(data, "accel_norm_std_max_g", 0.05),
            gyro_std_max_dps=_number(data, "gyro_std_max_dps", 0.15),
            gyro_abs_max_dps=_number(data, "gyro_abs_max_dps", 1.0),
            accel_norm_min_g=_number(data, "accel_norm_min_g", 0.9),
            accel_norm_max_g=_number(data, "accel_norm_max_g", 1.1),
        )


@dataclass
class ComplementaryFilter:
    # Weight of the gyroscope prediction; lower values trust the accelerometer.
    alpha: float = 0.98

    def to_dict(self) -> dict[str, float]:
        return {"alpha": self.alpha}

    @classmethod
    def from_dict(cls, data: Any) -> "ComplementaryFilter":
        data = _mapping(data, "complementary_filter")
        return cls(alpha=_number(data, "alpha", 0.98))


@dataclass
class Integration:
    method: str = "trapezoid"
    zupt_holds_velocity: bool = True
    max_dt_s: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "zupt_holds_velocity": self.zupt_holds_velocity,
            "max_dt_s": self.max_dt_s,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Integration":
        data = _mapping(data, "integration")
        return cls(
            method=_text(data, "method", "trapezoid"),
            zupt_holds_velocity=_boolean(data, "zupt_holds_velocity", True),
            max_dt_s=_number(data, "max_dt_s", 0.1),
        )


@dataclass
class Validation:
    residual_vector_rms_dps: float = 0.0
    max_residual_mean_dps: float = 0.0
    gate_pass: bool = False
    gates: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "residual_vector_rms_dps": self.residual_vector_rms_dps,
            "max_residual_mean_dps": self.max_residual_mean_dps,
            "gate_pass": self.gate_pass,
            "gates": self.gates,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Validation":
        data = _mapping(data, "validation")
        return cls(
            residual_vector_rms_dps=_number(data, "residual_vector_rms_dps", 0.0),
            max_residual_mean_dps=_number(data, "max_residual_mean_dps", 0.0),
            gate_pass=_boolean(data, "gate_pass", False),
            gates=_text(data, "gates"),
        )


@dataclass
class Profile:
    schema: str = SCHEMA
    format_version: int = FORMAT_VERSION
    name: str = "default"
    created_at: str = ""
    source: SourceInfo = field(default_factory=SourceInfo)
    sensor: SensorConfig = field(default_factory=SensorConfig)
    gyro_bias_dps: Vec3 = field(default_factory=Vec3)
    accel_mean_g: Vec3 = field(default_factory=Vec3)
    mounting_tilt_deg: Tilt = field(default_factory=Tilt)
    static_detection: StaticDetection = field(default_factory=StaticDetection)
    complementary_filter: ComplementaryFilter = field(default_factory=ComplementaryFilter)
    integration: Integration = field(default_factory=Integration)
    validation: Validation = field(default_factory=Validation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "format_version": self.format_version,
            "name": self.name,
            "created_at": self.created_at,
            "source": self.source.to_dict(),
            "sensor": self.sensor.to_dict(),
            "gyro_bias_dps": self.gyro_bias_dps.to_dict(),
            "accel_mean_g": self.accel_mean_g.to_dict(),
            "mounting_tilt_deg": self.mounting_tilt_deg.to_dict(),
            "static_detection": self.static_detection.to_dict(),
            "complementary_filter": self.complementary_filter.to_dict(),
            "integration": self.integration.to_dict(),
            "validation": self.validation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Profile":
        data = _mapping(data, "profile")
        profile = cls(
            schema=_text(data, "schema", SCHEMA),
            format_version=_integer(data, "format_version", FORMAT_VERSION),
            name=_text(data, "name", "default"),
            created_at=_text(data, "created_at"),
            source=SourceInfo.from_dict(data.get("source", {})),
            sensor=SensorConfig.from_dict(data.get("sensor", {})),
            gyro_bias_dps=Vec3.from_dict(data.get("gyro_bias_dps", {}), "gyro_bias_dps"),
            accel_mean_g=Vec3.from_dict(data.get("accel_mean_g", {}), "accel_mean_g"),
            mounting_tilt_deg=Tilt.from_dict(data.get("mounting_tilt_deg", {}), "mounting_tilt_deg"),
            static_detection=StaticDetection.from_dict(data.get("static_detection", {})),
            complementary_filter=ComplementaryFilter.from_dict(data.get("complementary_filter", {})),
            integration=Integration.from_dict(data.get("integration", {})),
            validation=Validation.from_dict(data.get("validation", {})),
        )
        profile.validate()
        return profile

    def validate(self) -> None:
        """Raise ProfileError describing every structural violation found."""
        problems: list[str] = []
        if self.schema != SCHEMA:
            problems.append(f"schema must be '{SCHEMA}', got '{self.schema}'")
        if self.format_version != FORMAT_VERSION:
            problems.append(f"format_version must be {FORMAT_VERSION}")
        if not self.name.strip():
            problems.append("name must not be empty")

        for axis, value in self.gyro_bias_dps.to_dict().items():
            if abs(value) > GYRO_BIAS_LIMIT_DPS:
                problems.append(
                    f"gyro_bias_dps.{axis}={value:.3f} exceeds the stationary bias limit "
                    f"{GYRO_BIAS_LIMIT_DPS} dps"
                )
        accel_norm = self.accel_mean_g.norm()
        if not math.isfinite(accel_norm) or not (
            ACCEL_NORM_MIN_G <= accel_norm <= ACCEL_NORM_MAX_G
        ):
            problems.append(
                f"accel_mean_g norm {accel_norm:.3f} g is outside "
                f"{ACCEL_NORM_MIN_G}-{ACCEL_NORM_MAX_G} g"
            )

        detection = self.static_detection
        if not 0.2 <= detection.window_s <= 10.0:
            problems.append("static_detection.window_s must be within 0.2-10 s")
        if detection.accel_norm_std_max_g <= 0:
            problems.append("static_detection.accel_norm_std_max_g must be positive")
        if detection.gyro_std_max_dps <= 0:
            problems.append("static_detection.gyro_std_max_dps must be positive")
        if detection.gyro_abs_max_dps <= 0:
            problems.append("static_detection.gyro_abs_max_dps must be positive")
        if not 0.5 <= detection.accel_norm_min_g < detection.accel_norm_max_g <= 1.5:
            problems.append(
                "static_detection acceleration band must satisfy "
                "0.5 <= min < max <= 1.5 g"
            )

        if not 0.5 <= self.complementary_filter.alpha < 1.0:
            problems.append("complementary_filter.alpha must be within [0.5, 1.0)")

        if self.integration.method != "trapezoid":
            problems.append("integration.method must be 'trapezoid'")
        if not 0.001 <= self.integration.max_dt_s <= 1.0:
            problems.append("integration.max_dt_s must be within 0.001-1 s")

        if problems:
            raise ProfileError("; ".join(problems))

    def gate_problems(self) -> list[str]:
        """Validation-gate issues that make the profile unsuitable for live use."""
        problems: list[str] = []
        if not self.validation.gate_pass:
            problems.append("calibration gate did not pass; re-run calibration on a static capture")
        if self.validation.max_residual_mean_dps > RESIDUAL_LIMIT_DPS:
            problems.append(
                f"residual mean {self.validation.max_residual_mean_dps:.3f} dps exceeds "
                f"{RESIDUAL_LIMIT_DPS} dps"
            )
        if self.validation.residual_vector_rms_dps > RESIDUAL_LIMIT_DPS:
            problems.append(
                f"residual RMS {self.validation.residual_vector_rms_dps:.3f} dps exceeds "
                f"{RESIDUAL_LIMIT_DPS} dps"
            )
        return problems

    @property
    def usable(self) -> bool:
        return not self.gate_problems()

    def save(self, path: str | Path) -> Path:
        self.validate()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        raw = Path(path).read_text(encoding="utf-8-sig")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ProfileError(f"{path}: invalid JSON ({error})") from error
        return cls.from_dict(data)
