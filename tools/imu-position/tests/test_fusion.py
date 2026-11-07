"""Time alignment and rep-event joining for the unified panel."""

import unittest

from imu_position.fusion import FusionBuffer, ImuPoint


def imu(at_ms: int, seq: int = 1) -> ImuPoint:
    return ImuPoint(at_ms, seq, 4.0, -2.0, 0.0, (0.1, 0.2, 0.3),
                    (0.0, 0.0, 1.0), False, "串口")


class FusionTest(unittest.TestCase):
    def test_nearest_sample_and_staleness(self):
        fusion = FusionBuffer(max_offset_ms=100)
        fusion.add_imu(imu(1000, 1))
        fusion.add_imu(imu(1080, 2))
        fusion.add_pose(1, 1060, {"action": "深蹲", "phase": "底部"})
        joined = fusion.latest(1100)
        self.assertIsNotNone(joined)
        self.assertEqual(joined.imu.seq, 2)
        self.assertEqual(joined.offset_ms, 20)
        self.assertIsNone(fusion.latest(2600))

    def test_unmatched_data_is_not_claimed_as_integrated(self):
        fusion = FusionBuffer(max_offset_ms=100)
        fusion.add_imu(imu(1000))
        fusion.add_pose(1, 1200, {"action": "深蹲"})
        self.assertIsNone(fusion.latest(1200))

    def test_completed_rep_joins_once_at_event_time(self):
        fusion = FusionBuffer(max_offset_ms=100)
        pose = {"action": "深蹲", "phase": "站立",
                "last": {"rep": 1, "ok": True, "completed_at_ms": 1030}}
        fusion.add_pose(1, 1050, pose)
        self.assertEqual(fusion.rep_records, [])
        fusion.add_imu(imu(1020))
        self.assertEqual(len(fusion.rep_records), 1)
        self.assertEqual(fusion.rep_records[0].offset_ms, -10)
        fusion.add_pose(2, 1100, pose)
        self.assertEqual(len(fusion.rep_records), 1)


if __name__ == "__main__":
    unittest.main()
