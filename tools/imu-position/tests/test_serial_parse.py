"""Stream-parser and replay-source tests (no hardware)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imu_position.replay import ReplaySource, load_replay  # noqa: E402
from imu_position.serial_reader import ImuStreamParser  # noqa: E402
from support import STATIC_CAPTURE, make_sample  # noqa: E402

CONFIG_LINE = (
    "# CONFIG firmware=BMI160_SixAxis_v3_autoaddr chip_id=0xD1 address=0x69 "
    "acc_conf=0x27 acc_range=0x05 gyr_conf=0x27 gyr_range=0x02 "
    "pmu=0x14 err=0x00 odr_hz=50 accel_unit=g gyro_unit=deg/s calibrated=NO"
)


class StreamParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.samples = []
        self.fatals = []
        self.configs = []
        self.parser = ImuStreamParser(
            on_sample=self.samples.append,
            on_fatal=self.fatals.append,
            on_config=lambda line, valid: self.configs.append(valid),
        )

    def test_consumes_startup_and_samples(self) -> None:
        self.parser.feed("# BMI160_SIX_AXIS_START")
        self.parser.feed(CONFIG_LINE)
        self.parser.feed("sample_seq,t_read_us,sensor_ticks,ax_raw,ay_raw,az_raw,"
                         "gx_raw,gy_raw,gz_raw,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps")
        for seq in range(1, 4):
            self.parser.feed(make_sample(seq, (0, 0, 0), (0, 0, 1)).to_csv_line() + "\r\n")
        self.assertEqual(len(self.samples), 3)
        self.assertEqual(self.configs, [True])
        self.assertEqual(self.parser.stats.sequence_gaps, 0)
        self.assertEqual(self.parser.stats.malformed_rows, 0)

    def test_malformed_rows_are_counted_not_fatal(self) -> None:
        self.parser.feed("ESP-ROM:esp32s3-20210327")
        self.parser.feed("1,2,3")
        self.parser.feed(make_sample(1, (0, 0, 0), (0, 0, 1)).to_csv_line())
        self.assertEqual(self.parser.stats.ignored_lines, 1)
        self.assertEqual(self.parser.stats.malformed_rows, 1)
        self.assertEqual(len(self.samples), 1)
        self.assertEqual(self.fatals, [])

    def test_boot_banner_is_ignored(self) -> None:
        self.parser.feed("ESP-ROM:esp32s3-20210327")
        self.parser.feed("Build:Mar 27 2021")
        self.parser.feed("rst:0x1 (POWERON),boot:0x2b (SPI_FAST_FLASH_BOOT)")
        self.parser.feed("entry 0x403c88b8")
        self.assertEqual(self.parser.stats.ignored_lines, 4)
        self.assertEqual(self.parser.stats.malformed_rows, 0)
        self.assertEqual(self.samples, [])

    def test_sequence_gap_is_counted(self) -> None:
        self.parser.feed(make_sample(1, (0, 0, 0), (0, 0, 1)).to_csv_line())
        self.parser.feed(make_sample(3, (0, 0, 0), (0, 0, 1)).to_csv_line())
        self.assertEqual(self.parser.stats.sequence_gaps, 1)

    def test_fatal_line_stops_parser(self) -> None:
        self.parser.feed("# FATAL NO_FRESH_SIX_AXIS_DATA_FOR_1S")
        self.assertEqual(self.fatals, ["NO_FRESH_SIX_AXIS_DATA_FOR_1S"])

    def test_stats_read_errors_are_fatal(self) -> None:
        self.parser.feed("# STATS samples=100 window_hz=49.8 read_errors=3")
        self.assertTrue(self.fatals)
        self.assertEqual(self.parser.stats.last_read_errors, 3)

    def test_stats_without_errors_is_not_fatal(self) -> None:
        self.parser.feed("# STATS samples=100 window_hz=49.8 read_errors=0")
        self.assertEqual(self.fatals, [])
        self.assertAlmostEqual(self.parser.stats.last_window_hz, 49.8)

    def test_bad_config_is_reported(self) -> None:
        self.parser.feed(CONFIG_LINE.replace("address=0x69", "address=0x70"))
        self.assertEqual(self.configs, [False])
        self.assertEqual(self.parser.stats.config_problems, 1)


class ReplaySourceTest(unittest.TestCase):
    def test_due_follows_capture_time(self) -> None:
        samples = [make_sample(seq, (0, 0, 0), (0, 0, 1)) for seq in range(1, 11)]
        source = ReplaySource(samples)
        self.assertEqual(len(source.due(0.0)), 1)
        self.assertEqual(len(source.due(0.0999)), 4)
        self.assertEqual(len(source.due(1.0)), 5)
        self.assertTrue(source.finished)

    def test_reset_and_duration(self) -> None:
        samples = [make_sample(seq, (0, 0, 0), (0, 0, 1)) for seq in range(1, 11)]
        source = ReplaySource(samples)
        self.assertAlmostEqual(source.duration_s, 0.18, places=3)
        source.due(10.0)
        source.reset()
        self.assertFalse(source.finished)

    def test_loads_committed_capture(self) -> None:
        source = load_replay(STATIC_CAPTURE)
        self.assertEqual(len(source.samples), 1496)
        self.assertAlmostEqual(source.duration_s, 30.061, places=2)

    def test_rejects_non_positive_speed(self) -> None:
        with self.assertRaises(ValueError):
            ReplaySource([], speed=0.0)


if __name__ == "__main__":
    unittest.main()
