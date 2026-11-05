"""Profile management dialog: import, export, edit and calibrate.

Every change is validated before it can be applied, so a broken profile
can never reach the live pipeline.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..calibration import build_profile
from ..profile import Profile, ProfileError

FIELD_SPECS = (
    ("gyro_bias_dps.x", "陀螺零偏 X (°/s)", -5.0, 5.0, 0.001, 4),
    ("gyro_bias_dps.y", "陀螺零偏 Y (°/s)", -5.0, 5.0, 0.001, 4),
    ("gyro_bias_dps.z", "陀螺零偏 Z (°/s)", -5.0, 5.0, 0.001, 4),
    ("mounting_tilt_deg.roll_deg", "安装倾斜 roll (°)", -90.0, 90.0, 0.01, 2),
    ("mounting_tilt_deg.pitch_deg", "安装倾斜 pitch (°)", -90.0, 90.0, 0.01, 2),
    ("static_detection.window_s", "静止检测窗口 (s)", 0.2, 10.0, 0.1, 2),
    ("static_detection.accel_norm_std_max_g", "加速度模长 std 上限 (g)", 0.001, 0.5, 0.001, 3),
    ("static_detection.gyro_std_max_dps", "陀螺模长 std 上限 (°/s)", 0.01, 5.0, 0.01, 2),
    ("static_detection.gyro_abs_max_dps", "陀螺模长上限 (°/s)", 0.05, 20.0, 0.05, 2),
    ("static_detection.accel_norm_min_g", "加速度模长下限 (g)", 0.5, 1.0, 0.01, 2),
    ("static_detection.accel_norm_max_g", "加速度模长上限 (g)", 1.0, 1.5, 0.01, 2),
    ("complementary_filter.alpha", "互补滤波 α", 0.5, 0.999, 0.001, 3),
)


def _split(path: str) -> tuple[str, str]:
    section, _, field = path.partition(".")
    return section, field


def _get(profile: Profile, path: str) -> float:
    section, field = _split(path)
    return float(getattr(getattr(profile, section), field))


def _set(profile: Profile, path: str, value: float) -> None:
    section, field = _split(path)
    setattr(getattr(profile, section), field, value)


class ProfileDialog(QDialog):
    def __init__(self, profile: Profile, profile_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("零飘处理 Profile")
        self.setMinimumWidth(480)
        self.profile_dir = profile_dir
        self.profile = copy.deepcopy(profile)
        self.result_profile: Optional[Profile] = None

        layout = QVBoxLayout(self)
        self.name_label = QLabel()
        layout.addWidget(self.name_label)

        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)

        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)

        form_box = QGroupBox("可编辑参数")
        form = QFormLayout(form_box)
        self.fields: dict[str, QDoubleSpinBox] = {}
        for path, label, low, high, step, decimals in FIELD_SPECS:
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setValue(_get(self.profile, path))
            form.addRow(label, spin)
            self.fields[path] = spin
        layout.addWidget(form_box)

        buttons = QHBoxLayout()
        import_button = QPushButton("导入…")
        export_button = QPushButton("导出…")
        calibrate_button = QPushButton("从静态 CSV 标定…")
        import_button.clicked.connect(self._import)
        export_button.clicked.connect(self._export)
        calibrate_button.clicked.connect(self._calibrate)
        buttons.addWidget(import_button)
        buttons.addWidget(export_button)
        buttons.addWidget(calibrate_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("应用")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self._apply)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self._refresh_labels()

    def _refresh_labels(self) -> None:
        profile = self.profile
        self.name_label.setText(f"当前 profile：<b>{profile.name}</b>")
        source = profile.source
        self.source_label.setText(
            f"来源：{source.csv or '（未标定）'}<br>"
            f"{source.rows} 组 / {source.duration_s:.2f} s / {source.rate_hz:.2f} Hz · "
            f"端口 {source.port or '—'} · 地址 {source.address or '—'}"
        )
        problems = profile.gate_problems()
        if problems:
            self.validation_label.setText("⚠ " + "；".join(problems))
            self.validation_label.setStyleSheet("color:#ffb36b")
        else:
            self.validation_label.setText(
                f"✓ 校验通过：残差均值 ≤{profile.validation.max_residual_mean_dps:.4f} °/s，"
                f"RMS {profile.validation.residual_vector_rms_dps:.4f} °/s"
            )
            self.validation_label.setStyleSheet("color:#9be6a3")

    def _collect(self) -> Profile:
        candidate = copy.deepcopy(self.profile)
        for path, spin in self.fields.items():
            _set(candidate, path, spin.value())
        return candidate

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入零飘 profile", str(self.profile_dir), "JSON (*.json)")
        if not path:
            return
        try:
            imported = Profile.load(path)
        except (ProfileError, OSError) as error:
            QMessageBox.warning(self, "导入失败", str(error))
            return
        self.profile = imported
        for field_path, spin in self.fields.items():
            spin.setValue(_get(self.profile, field_path))
        self._refresh_labels()

    def _export(self) -> None:
        try:
            self.profile = self._collect()
            self.profile.validate()
        except ProfileError as error:
            QMessageBox.warning(self, "参数无效", str(error))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出零飘 profile", str(self.profile_dir / f"{self.profile.name}.json"), "JSON (*.json)"
        )
        if not path:
            return
        try:
            self.profile.save(path)
        except (ProfileError, OSError) as error:
            QMessageBox.warning(self, "导出失败", str(error))
            return
        QMessageBox.information(self, "已导出", path)

    def _calibrate(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择静止采集 CSV", "", "CSV (*.csv)")
        if not path:
            return
        try:
            fitted = build_profile(path, name=Path(path).stem, profile_dir=self.profile_dir)
        except (ProfileError, ValueError, OSError) as error:
            QMessageBox.warning(self, "标定失败", str(error))
            return
        target = self.profile_dir / f"{fitted.name}.json"
        try:
            fitted.save(target)
        except OSError as error:
            QMessageBox.warning(self, "保存失败", str(error))
            return
        self.profile = fitted
        for field_path, spin in self.fields.items():
            spin.setValue(_get(self.profile, field_path))
        self._refresh_labels()
        QMessageBox.information(self, "标定完成", f"已生成并可应用到：\n{target}")

    def _apply(self) -> None:
        try:
            candidate = self._collect()
            candidate.validate()
        except ProfileError as error:
            QMessageBox.warning(self, "参数无效", str(error))
            return
        if candidate.gate_problems():
            answer = QMessageBox.question(
                self,
                "校验未通过",
                "该 profile 的校验门槛未通过：\n"
                + "\n".join(candidate.gate_problems())
                + "\n\n仍要应用吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.result_profile = candidate
        self.accept()
