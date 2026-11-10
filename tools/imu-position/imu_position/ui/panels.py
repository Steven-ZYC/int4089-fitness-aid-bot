"""QPainter chart widgets for the source-data page.

Rolling time-series charts are drawn manually to keep the dependency set
at PySide6 only. Static (ZUPT) spans are shaded so the effect of the
zero-drift profile is visible at a glance.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

BG = QColor("#141a20")
GRID = QColor("#26313a")
AXIS_TEXT = QColor("#8fa3b3")
ZERO_LINE = QColor("#4a5a68")
STATIC_SHADE = QColor(70, 130, 90, 40)
SERIES_COLORS = (QColor("#ff6b6b"), QColor("#6bcB77"), QColor("#5b9cf5"))


@dataclass
class SeriesChart(QWidget):
    title: str
    unit: str
    y_min: float | None = None
    y_max: float | None = None
    show_zero: bool = True
    reference: float | None = None
    max_points: int = 1500
    times: deque = field(default_factory=deque)
    values: list = field(default_factory=lambda: [deque(), deque(), deque()])
    static: deque = field(default_factory=deque)
    latest: tuple = field(default_factory=lambda: (0.0, 0.0, 0.0))

    def __init__(self, title: str, unit: str, **kwargs) -> None:
        super().__init__()
        self.title = title
        self.unit = unit
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.times = deque(maxlen=self.max_points)
        self.values = [deque(maxlen=self.max_points) for _ in range(3)]
        self.static = deque(maxlen=self.max_points)
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def append(self, t_s: float, triple: Sequence[float], is_static: bool) -> None:
        self.times.append(t_s)
        for axis in range(3):
            self.values[axis].append(triple[axis])
        self.static.append(is_static)
        self.latest = tuple(triple)
        self.update()

    def clear(self) -> None:
        self.times.clear()
        for series in self.values:
            series.clear()
        self.static.clear()
        self.latest = (0.0, 0.0, 0.0)
        self.update()

    def _range(self) -> tuple[float, float]:
        low, high = self.y_min, self.y_max
        if low is None or high is None:
            points = [value for series in self.values for value in series]
            if self.reference is not None:
                points.append(self.reference)
            if not points:
                points = [0.0, 1.0]
            data_low, data_high = min(points), max(points)
            pad = max((data_high - data_low) * 0.15, 0.05)
            low = data_low - pad if low is None else low
            high = data_high + pad if high is None else high
        return low, high

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), BG)

        plot = QRectF(self.rect()).adjusted(44, 22, -10, -16)
        painter.setPen(QPen(GRID, 1))
        painter.drawRect(plot)

        painter.setPen(AXIS_TEXT)
        font = QFont(painter.font())
        font.setPointSizeF(8.5)
        painter.setFont(font)
        painter.drawText(QRectF(8, 4, self.width() - 16, 16), Qt.AlignmentFlag.AlignLeft, f"{self.title}  ({self.unit})")

        if not self.times:
            painter.end()
            return

        low, high = self._range()
        span = high - low if high > low else 1.0
        t_start, t_end = self.times[0], self.times[-1]
        t_span = t_end - t_start if t_end > t_start else 1.0

        def x_of(t_s: float) -> float:
            return plot.left() + (t_s - t_start) / t_span * plot.width()

        def y_of(value: float) -> float:
            return plot.bottom() - (value - low) / span * plot.height()

        # Static spans as background shading.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(STATIC_SHADE)
        run_start = None
        for index, static in enumerate(self.static):
            t = self.times[index]
            if static and run_start is None:
                run_start = t
            elif not static and run_start is not None:
                painter.drawRect(QRectF(x_of(run_start), plot.top(), x_of(t) - x_of(run_start), plot.height()))
                run_start = None
        if run_start is not None:
            painter.drawRect(QRectF(x_of(run_start), plot.top(), x_of(self.times[-1]) - x_of(run_start), plot.height()))

        # Axis labels.
        painter.setPen(AXIS_TEXT)
        painter.drawText(QRectF(0, plot.top() - 6, 42, 14), Qt.AlignmentFlag.AlignRight, f"{high:.2f}")
        painter.drawText(QRectF(0, plot.bottom() - 8, 42, 14), Qt.AlignmentFlag.AlignRight, f"{low:.2f}")

        if self.show_zero and low <= 0.0 <= high:
            painter.setPen(QPen(ZERO_LINE, 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), y_of(0.0)), QPointF(plot.right(), y_of(0.0)))
        if self.reference is not None and low <= self.reference <= high:
            painter.setPen(QPen(QColor("#c9a227"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y_of(self.reference)), QPointF(plot.right(), y_of(self.reference)))

        for axis in range(3):
            painter.setPen(QPen(SERIES_COLORS[axis], 1.4))
            previous = None
            for index, value in enumerate(self.values[axis]):
                point = QPointF(x_of(self.times[index]), y_of(value))
                if previous is not None:
                    painter.drawLine(previous, point)
                previous = point
        painter.end()


class ValueBadge(QWidget):
    """Large current-value text plus a static/moving state badge."""

    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, tuple[float, float, float]] = {}
        self.state = "—"
        self.state_ok = True
        self.setMinimumWidth(210)

    def set_values(self, gyro, accel, static: bool, warmup: bool) -> None:
        self.values = {"gyro": tuple(gyro), "accel": tuple(accel)}
        self.state = "预热中" if warmup else ("静止 ZUPT" if static else "运动")
        self.state_ok = static or warmup
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), BG)
        font = QFont(painter.font())
        font.setPointSizeF(9)
        painter.setFont(font)
        painter.setPen(AXIS_TEXT)
        painter.drawText(12, 20, "当前值")

        font.setPointSizeF(11)
        font.setFamily("Consolas")
        painter.setFont(font)
        y = 44
        for label, key, unit in (("陀螺", "gyro", "°/s"), ("加速度", "accel", "g")):
            triple = self.values.get(key)
            painter.setPen(AXIS_TEXT)
            painter.drawText(12, y, label)
            y += 18
            for axis, name in enumerate(("x", "y", "z")):
                if triple is None:
                    text = "—"
                else:
                    text = f"{name} {triple[axis]:+8.3f} {unit}"
                painter.setPen(SERIES_COLORS[axis] if triple is not None else AXIS_TEXT)
                painter.drawText(24, y, text)
                y += 18
            y += 6

        painter.setPen(QColor("#9be6a3") if self.state_ok else QColor("#ffb36b"))
        font.setPointSizeF(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(12, self.height() - 18, self.state)
        painter.end()
