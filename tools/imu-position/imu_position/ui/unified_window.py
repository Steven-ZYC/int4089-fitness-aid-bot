"""Single-screen workout dashboard joining the pose service and IMU widgets."""

from __future__ import annotations

import json
import threading
import time
import urllib.request

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..fusion import FusionBuffer, ImuPoint
from .main_window import MainWindow, TOOL_ROOT


class PoseFeed(QObject):
    frame = Signal(bytes)
    stats = Signal(dict)
    error = Signal(str)

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for target in (self._read_video, self._read_stats):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self.stop_event.set()
        for thread in self._threads:
            thread.join(timeout=0.2)

    def _read_video(self) -> None:
        while not self.stop_event.is_set():
            try:
                with urllib.request.urlopen(self.base_url + "/video", timeout=5) as stream:
                    buf = b""
                    while not self.stop_event.is_set():
                        chunk = stream.read(4096)
                        if not chunk:
                            raise ConnectionError("视频流已断开")
                        buf += chunk
                        while True:
                            start = buf.find(b"\xff\xd8")
                            end = buf.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                            if start < 0 or end < 0:
                                buf = buf[-2_000_000:]
                                break
                            self.frame.emit(buf[start:end + 2])
                            buf = buf[end + 2:]
            except Exception as exc:  # reconnect after a service restart
                self.error.emit(f"姿态视频未连接：{exc}")
                self.stop_event.wait(2)

    def _read_stats(self) -> None:
        while not self.stop_event.is_set():
            try:
                with urllib.request.urlopen(self.base_url + "/stats", timeout=2) as response:
                    self.stats.emit(json.load(response))
            except Exception as exc:
                self.error.emit(f"姿态服务未连接：{exc}")
            self.stop_event.wait(0.2)


def _card(title: str, body: QWidget) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    label = QLabel(title)
    label.setObjectName("cardTitle")
    layout.addWidget(label)
    layout.addWidget(body, 1)
    return card


class UnifiedWindow(MainWindow):
    """Keep the proven IMU data path; present both sources on one screen."""

    def __init__(self, profile, profile_path=None, pose_url="http://127.0.0.1:8010") -> None:
        self.pose_url = pose_url
        self.fusion = FusionBuffer()
        super().__init__(profile, profile_path)
        self.setWindowTitle("FitCoach AI · 运动分析")
        self.resize(1500, 980)
        self.feed = PoseFeed(pose_url)
        self.feed.frame.connect(self._show_frame)
        self.feed.stats.connect(self._show_stats)
        self.feed.error.connect(self._show_error)
        self.feed.start()

    def _build_ui(self) -> None:
        super()._build_ui()
        outer = self.centralWidget().layout()
        outer.removeWidget(self.tabs)
        source = self.tabs.widget(0)
        scene = self.tabs.widget(1)
        self.tabs.removeTab(1)
        self.tabs.removeTab(0)
        source.setParent(None)
        scene.setParent(None)
        self.tabs.deleteLater()

        page = QWidget()
        grid = QGridLayout(page)
        grid.setSpacing(14)

        self.video = QLabel("等待姿态视频…\n请先启动 Haoyu 的 pose_app.py")
        self.video.setObjectName("video")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumSize(640, 360)
        self.video.setScaledContents(False)
        grid.addWidget(_card("实时画面 · 姿态识别", self.video), 0, 0)

        verdict = QWidget()
        verdict_layout = QVBoxLayout(verdict)
        self.result = QLabel("等待动作…")
        self.result.setObjectName("result")
        self.result.setWordWrap(True)
        self.pose_details = QLabel("动作 — · 阶段 — · 次数 0")
        self.pose_details.setWordWrap(True)
        self.pose_feedback = QLabel("完成一个动作后显示判断和建议。")
        self.pose_feedback.setWordWrap(True)
        self.pose_state = QLabel("姿态服务：连接中")
        self.pose_state.setWordWrap(True)
        self.fusion_state = QLabel("数据配对：等待摄像头与 IMU")
        self.fusion_state.setWordWrap(True)
        self.fusion_details = QLabel("两路数据到达后显示同一时刻的姿态与 IMU 数值。")
        self.fusion_details.setWordWrap(True)
        self.rep_fusion = QLabel("完整动作配对：等待首次计次。")
        self.rep_fusion.setWordWrap(True)
        self.export_button = QPushButton("导出已配对动作记录")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_records)
        for widget in (self.result, self.pose_details, self.pose_feedback,
                       self.pose_state, self.fusion_state, self.fusion_details,
                       self.rep_fusion, self.export_button):
            verdict_layout.addWidget(widget)
        verdict_layout.addStretch(1)
        grid.addWidget(_card("动作分析", verdict), 0, 1)

        grid.addWidget(_card("ESP32-S3 · BMI160 源数据", source), 1, 0)
        grid.addWidget(_card("3D 姿态与位置", scene), 1, 1)
        source.show()
        scene.show()
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        self.setStyleSheet("""
            QMainWindow, QScrollArea, QWidget { background: #f3ede4; color: #201b16; }
            QFrame#card { background: #fffaf3; border: 1px solid #dfd4c5; border-radius: 13px; }
            QLabel#cardTitle { font-size: 16px; font-weight: 700; color: #46502a; padding: 3px; }
            QLabel#video { background: #242824; color: #f7f2e9; border-radius: 8px; font-size: 17px; }
            QLabel#result { font-size: 28px; font-weight: 700; color: #46502a; }
            QPushButton { background: #e6e0d3; border: 1px solid #c9bfad; border-radius: 6px; padding: 5px 8px; }
            QPushButton:checked { background: #596139; color: white; }
        """)

    def _show_frame(self, jpg: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(jpg):
            self.video.setPixmap(pixmap.scaled(
                self.video.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def _show_stats(self, payload: dict) -> None:
        pose = payload.get("pose") or {}
        stats = payload.get("stats") or {}
        self.fusion.add_pose(stats.get("frame_id", 0), stats.get("frame_time_ms", 0), pose)
        action = pose.get("action") or "—"
        phase = pose.get("phase") or "—"
        reps = pose.get("reps", 0)
        angles = pose.get("angles") or {}
        angle_text = " · ".join(f"{key} {value}°" for key, value in angles.items() if value is not None)
        self.pose_details.setText(f"{action} · {phase} · {reps} 次\n{angle_text}")
        last = pose.get("last")
        if last:
            self.result.setText("动作标准" if last.get("ok") else "需要调整")
            details = "；".join(last.get("violations") or []) or "保持当前动作。"
            score = last.get("score")
            self.pose_feedback.setText(f"第 {last.get('rep', reps)} 次 · {details}" +
                                       (f" · 评分 {score}" if score is not None else ""))
        else:
            self.result.setText("等待完整动作")
            self.pose_feedback.setText("请确保全身进入画面。")
        self.pose_state.setText(f"姿态服务：{stats.get('state', '未知')} · {stats.get('fps', 0)} FPS")
        self._refresh_fusion()

    def _show_error(self, message: str) -> None:
        self.pose_state.setText(message)
        self._refresh_fusion()

    def _apply_profile(self, profile) -> None:
        super()._apply_profile(profile)
        self.fusion = FusionBuffer()
        self.rep_fusion.setText("完整动作配对：等待首次计次。")
        self._refresh_fusion()

    def _start_replay(self) -> None:
        self.fusion = FusionBuffer()
        self.rep_fusion.setText("完整动作配对：等待首次计次。")
        super()._start_replay()

    def _toggle_connection(self, checked: bool) -> None:
        if checked:
            self.fusion = FusionBuffer()
            self.rep_fusion.setText("完整动作配对：等待首次计次。")
        super()._toggle_connection(checked)

    def _feed(self, sample) -> None:
        if self._paused:
            return
        super()._feed(sample)
        processed = self._all_processed[-1]
        self.fusion.add_imu(ImuPoint(
            host_ms=time.time_ns() // 1_000_000,
            seq=processed.seq,
            roll_deg=processed.roll_deg,
            pitch_deg=processed.pitch_deg,
            yaw_deg=processed.yaw_deg,
            gyro_dps=processed.gyro_dps,
            accel_g=processed.accel_g,
            is_static=processed.is_static,
            source="串口" if self.reader is not None else "CSV 回放",
        ))
        self._refresh_fusion()

    def _refresh_fusion(self) -> None:
        now_ms = time.time_ns() // 1_000_000
        self.export_button.setEnabled(bool(self.fusion.rep_records))
        if self.fusion.rep_records:
            event = self.fusion.rep_records[-1]
            result = event.pose["last"]
            self.rep_fusion.setText(
                f"第 {result['rep']} 次动作：相机判定{'标准' if result['ok'] else '需调整'}；"
                f"同刻 IMU roll {event.imu.roll_deg:+.1f}° / "
                f"pitch {event.imu.pitch_deg:+.1f}°（差 {event.offset_ms:+d} ms）"
            )
        joined = self.fusion.latest(now_ms)
        if joined is None:
            self.fusion_state.setText("数据配对：等待两路新数据（允许时间差 ±400 ms）")
            self.fusion_details.setText("摄像头与 IMU 尚无可配对样本。")
            return
        self.fusion_state.setText(
            f"数据已配对 · 时间差 {joined.offset_ms:+d} ms · IMU {joined.imu.source}"
        )
        self.fusion_details.setText(
            f"相机：{joined.pose.get('action', '—')} / {joined.pose.get('phase', '—')}  "
            f"IMU：roll {joined.imu.roll_deg:+.1f}°、pitch {joined.imu.pitch_deg:+.1f}°、"
            f"yaw {joined.imu.yaw_deg:+.1f}° · "
            f"{'静止' if joined.imu.is_static else '运动'}"
        )

    def _export_records(self) -> None:
        capture_dir = TOOL_ROOT / "captures"
        capture_dir.mkdir(exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出已配对动作记录", str(capture_dir / "fused-reps.jsonl"),
            "JSON Lines (*.jsonl)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as stream:
            for record in self.fusion.rep_records:
                stream.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.feed.stop()
        super().closeEvent(event)
