"""Single-screen workout dashboard joining the pose service and IMU widgets."""

from __future__ import annotations

import json
import threading
import urllib.request

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from .main_window import MainWindow


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
            self.stop_event.wait(0.7)


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
        for widget in (self.result, self.pose_details, self.pose_feedback, self.pose_state):
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

    def _show_error(self, message: str) -> None:
        self.pose_state.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.feed.stop()
        super().closeEvent(event)
