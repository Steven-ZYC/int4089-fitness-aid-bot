import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from collect_metrics import summarize


class TimingContractTests(unittest.TestCase):
    def setUp(self):
        self.info = {"mode": "pose", "model_sha256": "a" * 64}
        self.rows = [
            dict(mode="pose", frame=0, start_us=100, end_us=150100,
                 capture_us=10000, pre_us=10000, infer_us=100000, post_us=10000),
            dict(mode="pose", frame=1, start_us=200100, end_us=550100,
                 capture_us=10000, pre_us=10000, infer_us=300000, post_us=10000),
        ]

    def test_throughput_uses_total_time_and_includes_between_frame_delay(self):
        result = summarize(self.info, self.rows)
        self.assertAlmostEqual(result["inference_fps"], 5.0)
        self.assertAlmostEqual(result["observed_processing_fps"], 2 / 0.55)
        self.assertEqual(result["inference_ms_p95"], 300)

    def test_camera_baseline_is_never_reported_as_pose_inference(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row.update(mode="camera_only", infer_us=0)
        result = summarize({"mode": "camera_only"}, rows)
        self.assertIsNone(result["inference_fps"])

    def test_reset_dropped_frames_mixed_modes_and_invalid_durations_are_rejected(self):
        variants = []
        for field, value in (("start_us", 50), ("frame", 3), ("mode", "camera_only"),
                             ("infer_us", 0), ("pre_us", -1), ("post_us", float("nan")),
                             ("infer_us", 900000)):
            rows = copy.deepcopy(self.rows)
            rows[1][field] = value
            variants.append(rows)
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                summarize(self.info, rows)

    def test_no_samples_produces_no_fps(self):
        with self.assertRaises(ValueError):
            summarize(self.info, [])


if __name__ == "__main__":
    unittest.main()
