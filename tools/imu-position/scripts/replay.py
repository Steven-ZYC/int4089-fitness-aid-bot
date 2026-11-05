"""CLI: replay a capture through the drift pipeline and print metrics.

No GUI and no device needed: this is the headless verification path for
the zero-drift profile and the integration behaviour.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imu_position.csvio import read_capture, read_rate_hz
from imu_position.pipeline import process_samples, summarize
from imu_position.profile import Profile, ProfileError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="BMI160 capture CSV to replay")
    parser.add_argument("--profile", type=Path, required=True, help="zero-drift profile JSON")
    args = parser.parse_args(argv)

    try:
        profile = Profile.load(args.profile)
        samples = read_capture(args.capture)
    except ProfileError as error:
        print(f"invalid profile: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"invalid capture: {error}", file=sys.stderr)
        return 1

    raw_rate = read_rate_hz(samples)
    processed = process_samples(profile, samples)
    metrics = summarize(samples, processed)
    metrics["capture_rate_hz"] = round(raw_rate, 3)
    metrics["profile"] = profile.name
    metrics["profile_usable"] = profile.usable
    if profile.gate_problems():
        metrics["profile_problems"] = profile.gate_problems()

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if not profile.usable:
        return 2
    if metrics["static_fraction"] < 0.95:
        return 3
    if metrics["max_position_m"] > 0.001:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
