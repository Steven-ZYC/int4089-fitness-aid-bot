"""Calibration gates: fit a profile from synthetic/real stationary data."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imu_position.calibration import build_profile, calibration_gate_problems  # noqa: E402
from imu_position.profile import ProfileError  # noqa: E402
from support import STATIC_CAPTURE, make_sample, synthetic_static, write_capture_csv  # noqa: E402


class CalibrationTest(unittest.TestCase):
    def test_fits_known_synthetic_bias(self) -> None:
        samples = synthetic_static(count=600, bias_dps=(0.4, -0.3, 0.2))
        with tempfile.TemporaryDirectory() as directory:
            capture = write_capture_csv(Path(directory) / "static.csv", samples)
            profile = build_profile(capture, name="synthetic", profile_dir=Path(directory))
        self.assertAlmostEqual(profile.gyro_bias_dps.x, 0.4, delta=0.005)
        self.assertAlmostEqual(profile.gyro_bias_dps.y, -0.3, delta=0.005)
        self.assertAlmostEqual(profile.gyro_bias_dps.z, 0.2, delta=0.005)
        self.assertTrue(profile.validation.gate_pass)
        self.assertAlmostEqual(profile.accel_mean_g.z, 1.0, delta=0.005)

    def test_rejects_moving_capture(self) -> None:
        samples = synthetic_static(count=300, noise_dps=1.5)
        with tempfile.TemporaryDirectory() as directory:
            capture = write_capture_csv(Path(directory) / "moving.csv", samples)
            with self.assertRaises(ProfileError):
                build_profile(capture, name="moving", profile_dir=Path(directory))

    def test_rejects_short_capture(self) -> None:
        samples = synthetic_static(count=50)
        problems = calibration_gate_problems(samples)
        self.assertTrue(any("at least 100" in problem for problem in problems))

    def test_rejects_clipping(self) -> None:
        base = make_sample(1, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        clipped = base.__class__(**{**base.__dict__, "gz_raw": 32767})
        samples = [clipped] * 200
        problems = calibration_gate_problems(samples)
        self.assertTrue(any("clipping" in problem for problem in problems))

    def test_real_capture_matches_documented_bias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = build_profile(STATIC_CAPTURE, name="real", profile_dir=Path(directory))
        self.assertAlmostEqual(profile.gyro_bias_dps.x, -0.2394, places=3)
        self.assertAlmostEqual(profile.gyro_bias_dps.y, -0.3691, places=3)
        self.assertAlmostEqual(profile.gyro_bias_dps.z, 0.2943, places=3)
        self.assertAlmostEqual(profile.mounting_tilt_deg.roll_deg, -4.962, places=2)
        self.assertAlmostEqual(profile.mounting_tilt_deg.pitch_deg, 4.309, places=2)
        self.assertTrue(profile.validation.gate_pass)
        self.assertEqual(profile.source.rows, 1496)
        self.assertEqual(profile.source.address, "0x69")
        self.assertEqual(len(profile.source.sha256), 64)


if __name__ == "__main__":
    unittest.main()
