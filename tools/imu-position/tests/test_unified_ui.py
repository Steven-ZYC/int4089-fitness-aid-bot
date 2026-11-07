"""The dashboard must expose a paired camera/IMU event in one window."""

from __future__ import annotations

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None

from imu_position.profile import Profile  # noqa: E402
from imu_position.replay import ReplaySource  # noqa: E402
from support import STATIC_CAPTURE, STATIC_PROFILE  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class UnifiedUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])

    def test_camera_and_imu_event_are_shown_together(self) -> None:
        from imu_position.ui.unified_window import PoseFeed, UnifiedWindow

        with patch.object(PoseFeed, "start"):
            window = UnifiedWindow(Profile.load(STATIC_PROFILE), STATIC_PROFILE)
        window.show()
        window._feed(ReplaySource.from_path(STATIC_CAPTURE).samples[0])
        event_ms = window.fusion.imu[-1].host_ms
        window._show_stats({
            "pose": {"action": "深蹲", "phase": "站立", "reps": 1,
                     "angles": {"膝角": 98},
                     "last": {"rep": 1, "ok": True, "score": 100,
                              "completed_at_ms": event_ms}},
            "stats": {"frame_id": 1, "frame_time_ms": event_ms,
                      "state": "运行中", "fps": 12.0},
        })
        self.app.processEvents()
        self.assertTrue(window.gyro_chart.isVisible())
        self.assertTrue(window.scene.isVisible())
        self.assertIn("数据已配对", window.fusion_state.text())
        self.assertIn("第 1 次动作", window.rep_fusion.text())
        self.assertEqual(len(window.fusion.rep_records), 1)
        self.assertLess(abs(window.fusion.rep_records[0].offset_ms), 400)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fused.jsonl"
            with patch("imu_position.ui.unified_window.QFileDialog.getSaveFileName",
                       return_value=(str(output), "JSON Lines (*.jsonl)")):
                window._export_records()
            exported = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(exported["pose"]["last"]["rep"], 1)
            self.assertEqual(exported["imu"]["source"], "CSV 回放")
        window.close()


if __name__ == "__main__":
    unittest.main()
