"""CLI: fit an IMU zero-drift profile from a stationary capture CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imu_position.calibration import build_profile
from imu_position.profile import ProfileError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="stationary BMI160 capture CSV")
    parser.add_argument("-o", "--output", type=Path, required=True, help="profile JSON to write")
    parser.add_argument("--name", default=None, help="profile name (default: output stem)")
    parser.add_argument("--created-at", default=None, help="override creation date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    try:
        profile = build_profile(
            args.capture,
            name=args.name or args.output.stem,
            profile_dir=args.output.parent,
            created_at=args.created_at,
        )
    except ProfileError as error:
        print(f"calibration failed: {error}", file=sys.stderr)
        return 1

    profile.save(args.output)
    bias = profile.gyro_bias_dps
    print(f"profile: {args.output}")
    print(f"  gyro bias (dps): x={bias.x:+.4f} y={bias.y:+.4f} z={bias.z:+.4f}")
    print(
        "  mounting tilt: "
        f"roll={profile.mounting_tilt_deg.roll_deg:+.2f} deg "
        f"pitch={profile.mounting_tilt_deg.pitch_deg:+.2f} deg"
    )
    print(
        "  holdout residual: "
        f"max mean={profile.validation.max_residual_mean_dps:.4f} dps, "
        f"RMS={profile.validation.residual_vector_rms_dps:.4f} dps"
    )
    print(f"  gate_pass: {profile.validation.gate_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
