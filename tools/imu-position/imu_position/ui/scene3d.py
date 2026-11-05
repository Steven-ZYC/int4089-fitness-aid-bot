"""Minimal QPainter 3D view: attitude box, gravity/velocity vectors, trajectory.

The camera looks down at the scene from a fixed yaw/pitch; the world
frame uses the first sample's attitude as its reference, so the box shows
rotation relative to the start pose. There is no magnetometer, so yaw is
labelled unobservable and will drift during motion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

BG = QColor("#12171c")
GRID = QColor("#2a343d")
AXIS_TEXT = QColor("#8fa3b3")
AXIS_COLORS = (QColor("#ff6b6b"), QColor("#6bcB77"), QColor("#5b9cf5"))
TRAIL = QColor("#f2c94c")
GRAVITY = QColor("#9aa5b1")
VELOCITY = QColor("#56ccf2")
BOX_FACES = (
    QColor(70, 120, 160, 70),
    QColor(70, 120, 160, 110),
)

BOX_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)
BOX_CORNERS = (
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
)
BOX_FACE_QUADS = (
    (4, 5, 6, 7),  # top
    (0, 1, 2, 3),  # bottom
    (0, 1, 5, 4),  # front
    (2, 3, 7, 6),  # back
)


def rotation_xyz(roll_deg: float, pitch_deg: float, yaw_deg: float):
    """Row-major body->world rotation for Z-Y-X Euler angles."""
    r = math.radians(roll_deg)
    p = math.radians(pitch_deg)
    y = math.radians(yaw_deg)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def mat_vec(matrix, vector):
    return tuple(
        matrix[row][0] * vector[0] + matrix[row][1] * vector[1] + matrix[row][2] * vector[2]
        for row in range(3)
    )


IDENTITY_ROTATION = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@dataclass
class SceneState:
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    gravity_body: tuple[float, float, float] = (0.0, 0.0, 1.0)
    velocity_body: tuple[float, float, float] = (0.0, 0.0, 0.0)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    is_static: bool = False
    warmup: bool = True
    rotation: tuple = field(default=IDENTITY_ROTATION)


class Scene3D(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.state = SceneState()
        self.trail: list[tuple[float, float, float]] = []
        self.reference_rotation = None
        self.zoom = 1.0
        self.setMinimumSize(420, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def update_state(self, state: SceneState) -> None:
        self.state = state
        state.rotation = rotation_xyz(state.roll_deg, state.pitch_deg, state.yaw_deg)
        if self.reference_rotation is None:
            self.reference_rotation = state.rotation
        if not self.trail or self.trail[-1] != state.position:
            self.trail.append(state.position)
            if len(self.trail) > 20000:
                del self.trail[: len(self.trail) - 20000]
        self.update()

    def reset_view(self) -> None:
        self.reference_rotation = None
        self.trail.clear()
        self.zoom = 1.0
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.2, min(8.0, zoom))
        self.update()

    def _relative_rotation(self):
        rotation = self.state.rotation or IDENTITY_ROTATION
        reference = self.reference_rotation
        if reference is None:
            return rotation
        return tuple(
            tuple(
                reference[0][col] * rotation[0][row]
                + reference[1][col] * rotation[1][row]
                + reference[2][col] * rotation[2][row]
                for col in range(3)
            )
            for row in range(3)
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), BG)

        width, height = self.width(), self.height()
        center = QPointF(width * 0.5, height * 0.60)
        scene_scale = min(width, height) * 0.22 * self.zoom

        camera_yaw = math.radians(35.0)
        camera_pitch = math.radians(28.0)
        cos_yaw, sin_yaw = math.cos(camera_yaw), math.sin(camera_yaw)
        cos_pitch, sin_pitch = math.cos(camera_pitch), math.sin(camera_pitch)

        def project(point):
            # World (x right, y forward, z up) -> camera view -> screen.
            x = point[0] * cos_yaw - point[1] * sin_yaw
            depth = point[0] * sin_yaw + point[1] * cos_yaw
            z = point[2]
            screen_x = x
            screen_y = z * cos_pitch - depth * sin_pitch
            return QPointF(center.x() + screen_x * scene_scale, center.y() - screen_y * scene_scale)

        self._draw_ground_grid(painter, project, scene_scale)

        relative = self._relative_rotation()
        corners = [project(mat_vec(relative, corner)) for corner in BOX_CORNERS]

        top_face = QPolygonF([corners[index] for index in BOX_FACE_QUADS[0]])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BOX_FACES[0])
        painter.drawPolygon(top_face)
        front_face = QPolygonF([corners[index] for index in BOX_FACE_QUADS[2]])
        painter.setBrush(BOX_FACES[1])
        painter.drawPolygon(front_face)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#7fb3d5"), 1.4))
        for start, end in BOX_EDGES:
            painter.drawLine(corners[start], corners[end])

        origin = project((0.0, 0.0, 0.0))
        axis_length = 1.6
        for axis, color in enumerate(AXIS_COLORS):
            basis = tuple(1.0 if index == axis else 0.0 for index in range(3))
            tip = project(mat_vec(relative, tuple(value * axis_length for value in basis)))
            painter.setPen(QPen(color, 2.2))
            painter.drawLine(origin, tip)

        painter.setPen(QPen(GRAVITY, 1.6, Qt.PenStyle.DashLine))
        gravity_tip = project(
            mat_vec(relative, tuple(-0.9 * value for value in self.state.gravity_body))
        )
        painter.drawLine(origin, gravity_tip)

        speed = math.sqrt(sum(value * value for value in self.state.velocity_body))
        if speed > 1e-4:
            painter.setPen(QPen(VELOCITY, 2.0))
            scale = min(1.2, 0.2 + speed * 2.0)
            velocity_tip = project(
                mat_vec(relative, tuple(value * scale for value in self.state.velocity_body))
            )
            painter.drawLine(origin, velocity_tip)

        if len(self.trail) > 1:
            painter.setPen(QPen(TRAIL, 1.6))
            points = [project(point) for point in self.trail]
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)

        self._draw_hud(painter)
        painter.end()

    def _draw_ground_grid(self, painter, project, scene_scale) -> None:
        painter.setPen(QPen(GRID, 0.8))
        extent = 1.2
        for step in range(-2, 3):
            value = step * extent
            painter.drawLine(
                project((value, -extent * 2, 0.0)),
                project((value, extent * 2, 0.0)),
            )
            painter.drawLine(
                project((-extent * 2, value, 0.0)),
                project((extent * 2, value, 0.0)),
            )

    def _draw_hud(self, painter: QPainter) -> None:
        font = QFont(painter.font())
        font.setPointSizeF(8.5)
        painter.setFont(font)
        painter.setPen(AXIS_TEXT)
        state = self.state
        lines = [
            f"姿态  roll {state.roll_deg:+7.2f}°  pitch {state.pitch_deg:+7.2f}°  yaw {state.yaw_deg:+7.2f}°",
            f"位置  ({state.position[0]*100:+7.2f}, {state.position[1]*100:+7.2f}, {state.position[2]*100:+7.2f}) cm",
            "yaw 无磁力计不可观测，运动时会漂移",
        ]
        y = 18
        for line in lines:
            painter.drawText(QRectF(10, y, self.width() - 20, 16), Qt.AlignmentFlag.AlignLeft, line)
            y += 16

        legend_x = self.width() - 150
        legend_y = 18
        for color, label in (
            (AXIS_COLORS[0], "机体 X"),
            (AXIS_COLORS[1], "机体 Y"),
            (AXIS_COLORS[2], "机体 Z"),
            (GRAVITY, "重力方向"),
            (VELOCITY, "速度"),
            (TRAIL, "位置轨迹"),
        ):
            painter.setPen(QPen(color, 2))
            painter.drawLine(legend_x, legend_y + 6, legend_x + 16, legend_y + 6)
            painter.setPen(AXIS_TEXT)
            painter.drawText(legend_x + 22, legend_y + 10, label)
            legend_y += 17
