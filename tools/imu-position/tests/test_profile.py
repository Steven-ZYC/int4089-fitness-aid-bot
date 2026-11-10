"""Profile schema, round-trip and gate tests."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imu_position.profile import (  # noqa: E402
    RESIDUAL_LIMIT_DPS,
    Profile,
    ProfileError,
    Validation,
    Vec3,
)
from support import STATIC_PROFILE, identity_profile  # noqa: E402


class ProfileRoundTripTest(unittest.TestCase):
    def test_round_trip_preserves_values(self) -> None:
        profile = identity_profile(
            gyro_bias_dps=Vec3(0.25, -0.5, 0.75),
            validation=Validation(
                residual_vector_rms_dps=0.03,
                max_residual_mean_dps=0.01,
                gate_pass=True,
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            profile.save(path)
            loaded = Profile.load(path)
        self.assertEqual(loaded.name, profile.name)
        self.assertAlmostEqual(loaded.gyro_bias_dps.z, 0.75)
        self.assertTrue(loaded.usable)

    def test_committed_static_profile_is_valid_and_usable(self) -> None:
        profile = Profile.load(STATIC_PROFILE)
        self.assertTrue(profile.validation.gate_pass)
        self.assertTrue(profile.usable)
        self.assertLess(abs(profile.gyro_bias_dps.x), 1.0)
        self.assertAlmostEqual(profile.source.rows, 1496)
        self.assertAlmostEqual(profile.mounting_tilt_deg.roll_deg, -4.962, places=2)

    def test_bias_beyond_stationary_limit_is_rejected(self) -> None:
        profile = identity_profile(gyro_bias_dps=Vec3(0.0, 0.0, 900.0))
        with self.assertRaises(ProfileError):
            profile.validate()

    def test_inverted_static_band_is_rejected(self) -> None:
        profile = identity_profile()
        profile.static_detection.accel_norm_min_g = 1.1
        profile.static_detection.accel_norm_max_g = 0.9
        with self.assertRaises(ProfileError):
            profile.validate()

    def test_alpha_out_of_range_is_rejected(self) -> None:
        profile = identity_profile()
        profile.complementary_filter.alpha = 1.0
        with self.assertRaises(ProfileError):
            profile.validate()

    def test_accel_norm_outside_gate_is_rejected(self) -> None:
        profile = identity_profile(accel_mean_g=Vec3(0.0, 0.0, 0.2))
        with self.assertRaises(ProfileError):
            profile.validate()

    def test_failed_gate_marks_profile_unusable(self) -> None:
        profile = identity_profile(
            validation=Validation(
                residual_vector_rms_dps=RESIDUAL_LIMIT_DPS * 2,
                max_residual_mean_dps=0.0,
                gate_pass=True,
            )
        )
        self.assertFalse(profile.usable)
        self.assertTrue(profile.gate_problems())

    def test_invalid_json_reports_profile_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ProfileError):
                Profile.load(path)


if __name__ == "__main__":
    unittest.main()
