"""Drift-pipeline tests: bias removal, static detection, ZUPT, attitude."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imu_position.csvio import read_capture  # noqa: E402
from imu_position.pipeline import (  # noqa: E402
    DriftProcessor,
    euler_rates_from_body,
    gravity_body_g,
    process_samples,
    summarize,
)
from imu_position.profile import Profile, Vec3  # noqa: E402
from support import (  # noqa: E402
    STATIC_CAPTURE,
    STATIC_PROFILE,
    identity_profile,
    make_sample,
    synthetic_static,
    yaw_rotation_samples,
)


class BiasRemovalTest(unittest.TestCase):
    def test_static_synthetic_bias_is_removed(self) -> None:
        samples = synthetic_static(count=600, bias_dps=(0.4, -0.3, 0.2))
        profile = identity_profile(gyro_bias_dps=Vec3(0.4, -0.3, 0.2))
        processed = process_samples(profile, samples)
        tail = processed[100:]
        means = [sum(row.gyro_dps[i] for row in tail) / len(tail) for i in range(3)]
        for mean in means:
            self.assertLess(abs(mean), 0.02)
        summary = summarize(samples, processed)
        self.assertGreaterEqual(summary["static_fraction"], 0.9)
        self.assertLessEqual(summary["max_position_m"], 0.001)

    def test_unremoved_bias_integrates_yaw(self) -> None:
        # A large unremoved bias keeps the gyro-vector gate from declaring
        # the board static, so yaw integrates instead of being frozen.
        samples = synthetic_static(count=250, bias_dps=(0.2, 0.2, 1.5))
        profile = identity_profile()  # intentionally no bias correction
        processed = process_samples(profile, samples)
        self.assertFalse(processed[-1].is_static)
        self.assertGreater(abs(processed[-1].yaw_deg), 1.0)


class StaticDetectionTest(unittest.TestCase):
    def test_static_samples_are_detected_after_warmup(self) -> None:
        samples = synthetic_static(count=300)
        processed = process_samples(identity_profile(), samples)
        warmup = [row for row in processed if row.warmup]
        self.assertEqual(len(warmup), 49)
        self.assertFalse(any(row.is_static for row in warmup))
        self.assertTrue(all(row.is_static for row in processed[100:]))

    def test_moving_samples_are_not_static(self) -> None:
        profile = identity_profile()
        processor = DriftProcessor(profile)
        samples = synthetic_static(count=150)
        samples += [
            make_sample(151 + i, (0.0, 0.0, 90.0), (0.0, 0.0, 1.0)) for i in range(50)
        ]
        processed = [processor.process(sample) for sample in samples]
        self.assertTrue(processed[60].is_static)
        self.assertFalse(any(row.is_static for row in processed[160:]))


class IntegrationTest(unittest.TestCase):
    def test_static_board_stays_at_origin(self) -> None:
        samples = synthetic_static(count=400)
        processed = process_samples(identity_profile(), samples)
        self.assertFalse(processed[-1].warmup)
        self.assertLess(summarize(samples, processed)["max_position_m"], 0.0005)
        self.assertAlmostEqual(processed[-1].velocity_m_s[0], 0.0)

    def test_constant_yaw_rate_integrates_to_known_angle(self) -> None:
        samples = yaw_rotation_samples(rate_dps=45.0, duration_s=2.0)
        processed = process_samples(identity_profile(), samples)
        self.assertAlmostEqual(processed[-1].yaw_deg, 90.0, delta=1.0)
        # Pure rotation with ideal accelerometer: ZUPT must not fire.
        self.assertFalse(any(row.is_static for row in processed[60:]))

    def test_yaw_rotation_produces_no_translation(self) -> None:
        samples = yaw_rotation_samples(rate_dps=30.0, duration_s=1.5)
        summary = summarize(samples, process_samples(identity_profile(), samples))
        self.assertLess(summary["max_position_m"], 0.01)

    def test_generated_euler_rates_match_body_rates_at_level(self) -> None:
        roll_dot, pitch_dot, yaw_dot = euler_rates_from_body(0.0, 0.0, (1.0, 2.0, 3.0))
        self.assertAlmostEqual(roll_dot, 1.0)
        self.assertAlmostEqual(pitch_dot, 2.0)
        self.assertAlmostEqual(yaw_dot, 3.0)

    def test_gravity_vector_matches_tilt_convention(self) -> None:
        gx, gy, gz = gravity_body_g(-5.0, 4.0)
        self.assertLess(gx, 0.0)  # positive pitch tilts gravity toward -x
        self.assertLess(gy, 0.0)  # negative roll tilts gravity toward -y
        self.assertAlmostEqual(math.sqrt(gx * gx + gy * gy + gz * gz), 1.0)


class RealCaptureTest(unittest.TestCase):
    def test_recorded_static_capture_holds_origin(self) -> None:
        profile = Profile.load(STATIC_PROFILE)
        samples = read_capture(STATIC_CAPTURE)
        summary = summarize(samples, process_samples(profile, samples))
        self.assertEqual(summary["samples"], len(samples))
        self.assertAlmostEqual(summary["rate_hz"], 49.732, places=2)
        self.assertGreaterEqual(summary["static_fraction"], 0.95)
        self.assertLessEqual(summary["max_position_m"], 0.0005)
        self.assertGreaterEqual(summary["corrected_gyro_rms_dps"], 0.02)
        self.assertLessEqual(summary["corrected_gyro_rms_dps"], 0.05)
        self.assertAlmostEqual(summary["final_attitude_deg"]["roll"], -4.962, places=2)
        self.assertAlmostEqual(summary["final_attitude_deg"]["pitch"], 4.315, places=2)


if __name__ == "__main__":
    unittest.main()
