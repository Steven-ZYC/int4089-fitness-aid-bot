"""Offscreen UI smoke test: construct the window, replay, switch pages."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - environment without PySide6
    QApplication = None

from imu_position.profile import Profile  # noqa: E402
from imu_position.replay import ReplaySource  # noqa: E402
from support import STATIC_CAPTURE, STATIC_PROFILE  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])

    def test_replay_updates_both_pages(self) -> None:
        from imu_position.ui.main_window import MainWindow

        profile = Profile.load(STATIC_PROFILE)
        window = MainWindow(profile, STATIC_PROFILE)
        self.assertEqual(window.tabs.count(), 2)
        replay = ReplaySource.from_path(STATIC_CAPTURE)
        for sample in replay.samples:
            window._feed(sample)
        window._update_summary()
        self.app.processEvents()

        self.assertIn("静止判定", window.summary_label.text())
        self.assertGreater(len(window.gyro_chart.times), 1000)
        self.assertLess(window.scene.state.position[0], 0.001)
        # Both pages must paint without exceptions.
        for index in range(2):
            window.tabs.setCurrentIndex(index)
            self.app.processEvents()
            pixmap = window.grab()
            self.assertFalse(pixmap.isNull())

        window.close()

    def test_profile_switch_resets_pipeline(self) -> None:
        from imu_position.ui.main_window import MainWindow

        profile = Profile.load(STATIC_PROFILE)
        window = MainWindow(profile, STATIC_PROFILE)
        for sample in ReplaySource.from_path(STATIC_CAPTURE).samples[:400]:
            window._feed(sample)
        self.assertTrue(window._all_processed)
        window._reset_origin()
        self.assertEqual(window._all_processed, [])
        self.assertEqual(window.scene.trail, [])
        window.close()


if __name__ == "__main__":
    unittest.main()
