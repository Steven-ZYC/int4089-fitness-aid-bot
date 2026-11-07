"""App entry: ``python -m imu_position``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from .profile import Profile, ProfileError
from .ui.main_window import PROFILE_DIR, MainWindow

DEFAULT_PROFILE = PROFILE_DIR / "yancheng-2026-11-05-static.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="IMU zero-drift handling and 3D position panel (GUI)."
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="zero-drift profile JSON (default: the calibrated profile shipped in profiles/)",
    )
    parser.add_argument("--unified", action="store_true", help="show pose and IMU in one dashboard")
    parser.add_argument("--pose-url", default="http://127.0.0.1:8010", help="Haoyu pose service URL")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    app.setFont(QFont("Microsoft YaHei UI", 9))

    profile_path = args.profile
    if profile_path is None and DEFAULT_PROFILE.is_file():
        profile_path = DEFAULT_PROFILE
    if profile_path is None:
        chosen, _ = QFileDialog.getOpenFileName(None, "选择零飘 profile", str(PROFILE_DIR), "JSON (*.json)")
        if not chosen:
            QMessageBox.information(None, "需要 profile", "未选择 profile，程序退出。")
            return 2
        profile_path = Path(chosen)

    try:
        profile = Profile.load(profile_path)
    except ProfileError as error:
        QMessageBox.critical(None, "profile 无效", str(error))
        return 2

    if args.unified:
        from .ui.unified_window import UnifiedWindow
        window = UnifiedWindow(profile, profile_path, args.pose_url)
    else:
        window = MainWindow(profile, profile_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
