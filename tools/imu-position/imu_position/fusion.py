"""Join camera pose frames and IMU samples on the host clock.

Both processes run on the same PC. Camera timestamps are assigned after pose
inference; IMU timestamps are assigned when parsed samples reach the GUI. This
is a best-effort software alignment, not hardware synchronization.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImuPoint:
    host_ms: int
    seq: int
    roll_deg: float
    pitch_deg: float
    yaw_deg: float
    gyro_dps: tuple[float, float, float]
    accel_g: tuple[float, float, float]
    is_static: bool
    source: str


@dataclass(frozen=True)
class JoinedPoint:
    pose_time_ms: int
    imu_time_ms: int
    offset_ms: int
    pose: dict[str, Any]
    imu: ImuPoint

    def as_dict(self) -> dict[str, Any]:
        return {
            "pose_time_ms": self.pose_time_ms,
            "imu_time_ms": self.imu_time_ms,
            "offset_ms": self.offset_ms,
            "pose": self.pose,
            "imu": {
                "seq": self.imu.seq,
                "roll_deg": self.imu.roll_deg,
                "pitch_deg": self.imu.pitch_deg,
                "yaw_deg": self.imu.yaw_deg,
                "gyro_dps": self.imu.gyro_dps,
                "accel_g": self.imu.accel_g,
                "is_static": self.imu.is_static,
                "source": self.imu.source,
            },
        }


class FusionBuffer:
    def __init__(self, max_offset_ms: int = 400) -> None:
        self.max_offset_ms = max_offset_ms
        self.imu: deque[ImuPoint] = deque(maxlen=1000)
        self.pose: deque[tuple[int, dict[str, Any]]] = deque(maxlen=200)
        self.last_frame_id = -1
        self.last_rep_key: tuple[str, int] | None = None
        self.rep_records: list[JoinedPoint] = []

    def add_imu(self, point: ImuPoint) -> None:
        self.imu.append(point)
        self._match_rep()

    def add_pose(self, frame_id: int, timestamp_ms: int, pose: dict[str, Any]) -> None:
        if frame_id <= self.last_frame_id or timestamp_ms <= 0:
            return
        self.last_frame_id = frame_id
        self.pose.append((timestamp_ms, pose))
        self._match_rep()

    def latest(self, now_ms: int, max_age_ms: int = 1500) -> JoinedPoint | None:
        if not self.pose or now_ms - self.pose[-1][0] > max_age_ms:
            return None
        return self._join(*self.pose[-1])

    def _join(self, timestamp_ms: int, pose: dict[str, Any]) -> JoinedPoint | None:
        if not self.imu:
            return None
        nearest = min(self.imu, key=lambda point: abs(point.host_ms - timestamp_ms))
        offset = nearest.host_ms - timestamp_ms
        if abs(offset) > self.max_offset_ms:
            return None
        return JoinedPoint(timestamp_ms, nearest.host_ms, offset, pose, nearest)

    def _match_rep(self) -> None:
        if not self.pose:
            return
        timestamp_ms, pose = self.pose[-1]
        last = pose.get("last")
        if not isinstance(last, dict):
            return
        rep = last.get("rep")
        if not isinstance(rep, int):
            return
        key = (str(pose.get("action", "")), rep)
        if key == self.last_rep_key:
            return
        event_ms = last.get("completed_at_ms")
        if not isinstance(event_ms, int):
            event_ms = timestamp_ms
        joined = self._join(event_ms, pose)
        if joined is not None:
            self.rep_records.append(joined)
            self.last_rep_key = key
