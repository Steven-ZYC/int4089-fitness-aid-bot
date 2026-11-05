"""CSV replay source paced at the capture rate.

The replay path feeds the same parser and DriftProcessor as live serial
input, so the panel can be exercised and verified without the board.
"""

from __future__ import annotations

from pathlib import Path

from .csvio import Sample, read_capture


class ReplaySource:
    """Return due samples based on elapsed wall-clock or a fixed cadence."""

    def __init__(self, samples: list[Sample], speed: float = 1.0) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.samples = samples
        self.speed = speed
        self._times = self._build_times(samples)
        self._index = 0

    @classmethod
    def from_path(cls, path: str | Path, speed: float = 1.0) -> "ReplaySource":
        return cls(read_capture(path), speed=speed)

    @staticmethod
    def _build_times(samples: list[Sample]) -> list[float]:
        if not samples:
            return []
        start = samples[0].t_read_us
        return [(sample.t_read_us - start) / 1_000_000.0 for sample in samples]

    @property
    def finished(self) -> bool:
        return self._index >= len(self.samples)

    @property
    def duration_s(self) -> float:
        return self._times[-1] if self._times else 0.0

    def reset(self) -> None:
        self._index = 0

    def due(self, elapsed_s: float) -> list[Sample]:
        """Samples whose scheduled replay time has arrived."""
        due: list[Sample] = []
        limit = elapsed_s * self.speed
        while self._index < len(self.samples) and self._times[self._index] <= limit:
            due.append(self.samples[self._index])
            self._index += 1
        return due


def load_replay(path: str | Path, speed: float = 1.0) -> ReplaySource:
    return ReplaySource(read_capture(path), speed=speed)
