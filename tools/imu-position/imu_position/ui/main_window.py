"""Main window: two pages — corrected source data and 3D position.

Data flow: live serial reader (background thread) or CSV replay (timer)
-> ImuStreamParser -> DriftProcessor -> page widgets. The profile can be
swapped at runtime; switching restarts the processing state.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..csvio import Sample
from ..pipeline import DriftProcessor, ProcessedSample, summarize
from ..profile import Profile
from ..replay import ReplaySource
from ..serial_reader import ImuSerialReader, list_serial_ports
from .panels import SeriesChart, ValueBadge
from .profile_dialog import ProfileDialog
from .scene3d import Scene3D, SceneState

TOOL_ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE_DIR = TOOL_ROOT / "profiles"
STATUS_STYLE = "color:#9be6a3"
WARN_STYLE = "color:#ffb36b"


class MainWindow(QMainWindow):
    _sample_received = Signal(object)
    _status_received = Signal(str)
    _fatal_received = Signal(str)

    def __init__(self, profile: Profile, profile_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("IMU 零飘处理 · 位置面板")
        self.resize(1180, 760)

        self.profile = profile
        self.profile_path = profile_path
        self.processor = DriftProcessor(profile)
        self._all_processed: list[ProcessedSample] = []
        self.reader: ImuSerialReader | None = None
        self.replay: ReplaySource | None = None
        self._replay_started: float | None = None
        self._pause_started: float | None = None
        self._paused = False
        self._last_feed = 0.0
        self._reader_started_at = 0.0
        self._got_serial_data = False

        self._sample_received.connect(self._on_sample, Qt.ConnectionType.QueuedConnection)
        self._status_received.connect(self._apply_status, Qt.ConnectionType.QueuedConnection)
        self._fatal_received.connect(self._handle_fatal, Qt.ConnectionType.QueuedConnection)

        self._build_ui()
        self._replay_timer = QTimer(self)
        self._replay_timer.setInterval(20)
        self._replay_timer.timeout.connect(self._pump_replay)

        self._process_timer = QTimer(self)
        self._process_timer.setInterval(250)
        self._process_timer.timeout.connect(self._update_summary)
        self._process_timer.start()

        self._refresh_ports()
        self._apply_profile(profile)

    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(10, 8, 10, 8)

        top = QHBoxLayout()
        self.connect_button = QPushButton("连接")
        self.connect_button.setCheckable(True)
        self.connect_button.clicked.connect(self._toggle_connection)
        top.addWidget(self.connect_button)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(110)
        top.addWidget(QLabel("端口"))
        top.addWidget(self.port_combo)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self._refresh_ports)
        top.addWidget(refresh_button)

        top.addSpacing(12)
        self.reset_checkbox = QCheckBox("连接时复位板子")
        self.reset_checkbox.setChecked(True)
        self.reset_checkbox.setToolTip("通过 CH340 的 RTS→EN 引脚脉冲复位 ESP32-S3；板子挂起或没有输出时需要")
        top.addWidget(self.reset_checkbox)

        top.addSpacing(12)
        self.replay_button = QPushButton("回放 CSV")
        self.replay_button.setCheckable(True)
        self.replay_button.clicked.connect(self._toggle_replay)
        top.addWidget(self.replay_button)
        replay_pick = QPushButton("选择回放文件…")
        replay_pick.clicked.connect(self._pick_replay_file)
        top.addWidget(replay_pick)

        self.pause_button = QPushButton("暂停")
        self.pause_button.setCheckable(True)
        self.pause_button.clicked.connect(self._toggle_pause)
        top.addWidget(self.pause_button)
        top.addStretch(1)

        top.addWidget(QLabel("Profile"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(220)
        self.profile_combo.activated.connect(self._profile_chosen)
        top.addWidget(self.profile_combo)
        self.profile_button = QPushButton("设置 / 导入 / 标定…")
        self.profile_button.clicked.connect(self._open_profile_dialog)
        top.addWidget(self.profile_button)
        outer.addLayout(top)

        self.status_label = QLabel("未连接 · 请关闭 Arduino 串口监视器或 PowerShell 采集脚本后连接")
        outer.addWidget(self.status_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_source_page(), "① 源数据（零飘处理后）")
        self.tabs.addTab(self._build_scene_page(), "② 3D 位置")
        outer.addWidget(self.tabs, 1)

        self.setCentralWidget(central)
        self._refresh_profile_combo()

    def _build_source_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary_label = QLabel("等待数据…")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        body = QHBoxLayout()
        charts = QVBoxLayout()
        self.gyro_chart = SeriesChart("陀螺（已去零偏）", "°/s")
        self.accel_chart = SeriesChart("加速度（相对静止参考，保留重力方向）", "g", show_zero=True)
        self.norm_chart = SeriesChart("加速度模长", "g", reference=1.0, show_zero=False)
        charts.addWidget(self.gyro_chart, 3)
        charts.addWidget(self.accel_chart, 3)
        charts.addWidget(self.norm_chart, 2)
        body.addLayout(charts, 1)
        self.value_badge = ValueBadge()
        body.addWidget(self.value_badge)
        layout.addLayout(body, 1)
        return page

    def _build_scene_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.scene = Scene3D()
        layout.addWidget(self.scene, 1)

        controls = QHBoxLayout()
        reset_origin = QPushButton("重置原点")
        reset_origin.clicked.connect(self._reset_origin)
        reset_view = QPushButton("重置视图")
        reset_view.clicked.connect(self.scene.reset_view)
        zoom_in = QPushButton("放大")
        zoom_in.clicked.connect(lambda: self.scene.set_zoom(self.scene.zoom * 1.25))
        zoom_out = QPushButton("缩小")
        zoom_out.clicked.connect(lambda: self.scene.set_zoom(self.scene.zoom / 1.25))
        for widget in (reset_origin, reset_view, zoom_in, zoom_out):
            controls.addWidget(widget)
        controls.addStretch(1)
        self.scene_hint = QLabel("体轴方盒随姿态旋转；轨迹为积分位置。静止时 ZUPT 冻结，运动段位置会漂移。")
        controls.addWidget(self.scene_hint)
        layout.addLayout(controls)
        return page

    # ------------------------------------------------------------ profile
    def _refresh_profile_combo(self) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        paths = sorted(PROFILE_DIR.glob("*.json"))
        for path in paths:
            self.profile_combo.addItem(path.stem, str(path))
        if self.profile_path is not None and Path(self.profile_path) in paths:
            self.profile_combo.setCurrentIndex(paths.index(Path(self.profile_path)))
        else:
            self.profile_combo.addItem(self.profile.name + "（当前）", None)
            self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)
        self.profile_combo.blockSignals(False)

    def _profile_chosen(self, index: int) -> None:
        path = self.profile_combo.itemData(index)
        if not path:
            return
        try:
            profile = Profile.load(path)
        except Exception as error:  # user-facing
            QMessageBox.warning(self, "加载失败", str(error))
            return
        self.profile_path = Path(path)
        self._apply_profile(profile)

    def _open_profile_dialog(self) -> None:
        dialog = ProfileDialog(self.profile, PROFILE_DIR, self)
        if dialog.exec() and dialog.result_profile is not None:
            self.profile = dialog.result_profile
            self._refresh_profile_combo()
            self._apply_profile(dialog.result_profile)

    def _apply_profile(self, profile: Profile) -> None:
        self.profile = profile
        self.processor = DriftProcessor(profile)
        self._all_processed.clear()
        self.gyro_chart.clear()
        self.accel_chart.clear()
        self.norm_chart.clear()
        self.scene.reset_view()
        state = (
            f"Profile：<b>{profile.name}</b> · 零偏 "
            f"({profile.gyro_bias_dps.x:+.3f}, {profile.gyro_bias_dps.y:+.3f}, "
            f"{profile.gyro_bias_dps.z:+.3f}) °/s · 倾斜 "
            f"roll {profile.mounting_tilt_deg.roll_deg:+.2f}° / "
            f"pitch {profile.mounting_tilt_deg.pitch_deg:+.2f}°"
        )
        problems = profile.gate_problems()
        if problems:
            self.summary_label.setText(state + "<br>⚠ " + "；".join(problems))
            self.summary_label.setStyleSheet(WARN_STYLE)
        else:
            self.summary_label.setText(state)
            self.summary_label.setStyleSheet("")

    # ------------------------------------------------------------- sources
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        ports = list_serial_ports()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current and current not in ports:
            self.port_combo.setEditText(current)
        elif not current and ports:
            preferred = next((p for p in ports if p == "COM4"), ports[0])
            self.port_combo.setCurrentText(preferred)
        self.status_label.setText(
            ("可用端口：" + "、".join(ports) if ports else "未发现串口（开发板未连接？）")
            + " · 串口独占：请先关闭 Arduino 串口监视器 / PowerShell 采集脚本"
        )

    def _toggle_connection(self, checked: bool) -> None:
        if not checked:
            self._stop_sources()
            self.connect_button.setText("连接")
            return
        if self.replay_button.isChecked():
            self.replay_button.setChecked(False)
            self._stop_replay()
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "无端口", "请选择串口（开发板应已在设备管理器中显示）。")
            self.connect_button.setChecked(False)
            return
        self.reader = ImuSerialReader(
            port,
            on_sample=lambda sample: self._sample_received.emit(sample),
            on_fatal=self._on_fatal,
            on_status=self._set_status,
            reset_on_open=self.reset_checkbox.isChecked(),
        )
        self._got_serial_data = False
        try:
            self.reader.start()
        except Exception as error:
            self.reader = None
            self.connect_button.setChecked(False)
            self._set_status(f"连接失败：{error}（端口是否被其他程序占用？）")
            return
        self._reader_started_at = time.monotonic()
        self.connect_button.setText("断开")
        self._set_status(f"已连接 {port}，等待设备数据…（若 5 秒无数据请勾选“连接时复位板子”后重连）")

    def _toggle_replay(self, checked: bool) -> None:
        if not checked:
            self._stop_sources()
            return
        if self.connect_button.isChecked():
            self.connect_button.setChecked(False)
            self._stop_sources()
        if self.replay is None:
            default = TOOL_ROOT.parents[1] / "firmware" / "esp32-camera" / "evidence" / "yancheng-2026-11-05" / "capture.csv"
            if not self._pick_replay_file(str(default)):
                self.replay_button.setChecked(False)
                return
        self._start_replay()

    def _pick_replay_file(self, initial: str = "") -> bool:
        start_dir = initial or str(TOOL_ROOT.parents[1] / "firmware" / "esp32-camera" / "evidence")
        path, _ = QFileDialog.getOpenFileName(self, "选择回放 CSV", start_dir, "CSV (*.csv)")
        if not path:
            return False
        try:
            self.replay = ReplaySource.from_path(path)
        except Exception as error:  # user-facing
            QMessageBox.warning(self, "回放文件无效", str(error))
            return False
        self._apply_profile(self.profile)
        if self.replay_button.isChecked():
            self._start_replay()
        return True

    def _start_replay(self) -> None:
        assert self.replay is not None
        self.replay.reset()
        self._replay_started = time.monotonic()
        self._replay_timer.start()
        self._set_status(f"回放中 · {len(self.replay.samples)} 组 · {self.replay.duration_s:.1f} s")

    def _pump_replay(self) -> None:
        if self.replay is None or self._replay_started is None or self._paused:
            return
        elapsed = time.monotonic() - self._replay_started
        for sample in self.replay.due(elapsed):
            self._feed(sample)
        if self.replay.finished:
            self._replay_timer.stop()
            self._set_status("回放结束 · 可再次点击“回放 CSV”重播")

    def _stop_replay(self) -> None:
        self._replay_timer.stop()
        self._replay_started = None

    def _stop_sources(self) -> None:
        self._stop_replay()
        if self.reader is not None:
            self.reader.stop()
            self.reader = None
        self.connect_button.setText("连接")

    def _on_fatal(self, reason: str) -> None:
        # Called from the reader thread; marshal to the GUI thread.
        self._fatal_received.emit(reason)

    def _handle_fatal(self, reason: str) -> None:
        had_reader = self.reader is not None
        self._stop_sources()
        self.connect_button.setChecked(False)
        if had_reader:
            self.replay_button.setChecked(False)
            self._set_status(f"设备报告 FATAL：{reason}")
        else:
            self._set_status(reason)

    def _set_status(self, text: str) -> None:
        self._status_received.emit(text)

    def _apply_status(self, text: str) -> None:
        self.status_label.setText(text)

    # ------------------------------------------------------------ sampling
    def _on_sample(self, sample: Sample) -> None:
        self._got_serial_data = True
        self._feed(sample)

    def _feed(self, sample: Sample) -> None:
        if self._paused:
            return
        processed = self.processor.process(sample)
        self._all_processed.append(processed)
        accel_reference = self.profile.accel_mean_g.as_tuple()
        accel_deviation = tuple(
            processed.accel_g[axis] - accel_reference[axis] for axis in range(3)
        )
        self.gyro_chart.append(processed.t_s, processed.gyro_dps, processed.is_static)
        self.accel_chart.append(processed.t_s, accel_deviation, processed.is_static)
        self.norm_chart.append(processed.t_s, (processed.accel_norm_g,) * 3, processed.is_static)
        self.value_badge.set_values(
            processed.gyro_dps, processed.accel_g, processed.is_static, processed.warmup
        )
        self.scene.update_state(
            SceneState(
                roll_deg=processed.roll_deg,
                pitch_deg=processed.pitch_deg,
                yaw_deg=processed.yaw_deg,
                gravity_body=self._gravity_body(processed),
                velocity_body=processed.velocity_m_s,
                position=processed.position_m,
                is_static=processed.is_static,
                warmup=processed.warmup,
            )
        )

    @staticmethod
    def _gravity_body(processed: ProcessedSample):
        from ..pipeline import gravity_body_g

        return gravity_body_g(processed.roll_deg, processed.pitch_deg)

    # ------------------------------------------------------------- summary
    def _update_summary(self) -> None:
        self._watch_connection()
        if not self._all_processed:
            return
        metrics = summarize([], self._all_processed)
        parts = [
            f"样本 {metrics['samples']} · {metrics['rate_hz']:.2f} Hz · {metrics['span_s']:.1f} s",
            f"静止判定 {metrics['static_fraction'] * 100:.1f}%",
            "去偏残差 " + ", ".join(f"{value:+.3f}" for value in metrics["corrected_gyro_mean_dps"]) + " °/s",
            f"|位置| {metrics['final_position_m'] * 100:.2f} cm（峰值 {metrics['max_position_m'] * 100:.2f} cm）",
            f"|速度| {metrics['final_velocity_m_s']:.3f} m/s",
            f"姿态 roll {metrics['final_attitude_deg']['roll']:+.2f}° pitch {metrics['final_attitude_deg']['pitch']:+.2f}° yaw {metrics['final_attitude_deg']['yaw']:+.2f}°",
        ]
        self.summary_label.setText(" · ".join(parts))

    # ------------------------------------------------------------- monitor
    def _watch_connection(self) -> None:
        """Surface dead readers and silent ports on the status line."""
        reader = self.reader
        if reader is None:
            return
        elapsed = time.monotonic() - self._reader_started_at
        stats = reader.parser.stats
        if not reader.alive:
            if elapsed > 1.0:
                self._handle_fatal(reader.error or "串口读线程已停止（USB 断开？端口被占用？）")
        elif stats.samples == 0 and elapsed > 5.0:
            self._set_status(
                f"已连接但 5 秒未收到样本（收到 {stats.lines_received} 行，"
                f"忽略 {stats.ignored_lines} 行，畸形 {stats.malformed_rows} 行）"
                f" · 端口 {reader.port} 是否被其他程序占用？板子是否运行 BMI160_SixAxis 固件？"
            )

    def _reset_origin(self) -> None:
        self.processor.reset_origin()
        self.scene.reset_view()
        self._all_processed.clear()
        self.gyro_chart.clear()
        self.accel_chart.clear()
        self.norm_chart.clear()

    def _toggle_pause(self, checked: bool) -> None:
        self._paused = checked
        self.pause_button.setText("继续" if checked else "暂停")
        if checked:
            self._pause_started = time.monotonic()
        elif self._pause_started is not None and self._replay_started is not None:
            # Do not fast-forward the replay across the paused interval.
            self._replay_started += time.monotonic() - self._pause_started
            self._pause_started = None

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_sources()
        super().closeEvent(event)
