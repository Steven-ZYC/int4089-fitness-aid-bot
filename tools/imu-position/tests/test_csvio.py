"""CSV/line parsing tests, including malformed input and the real capture."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imu_position.csvio import (  # noqa: E402
    CSV_HEADER,
    LineParseError,
    parse_config_line,
    parse_data_line,
    parse_diagnostic,
    read_capture,
    read_rate_hz,
)
from support import STATIC_CAPTURE, make_sample, write_capture_csv  # noqa: E402

GOOD_LINE = (
    "1267,27396329,658965,-614,-706,8182,-16,-25,17,"
    "-0.07495,-0.08618,0.99878,-0.2439,-0.3811,0.2591"
)
CONFIG_LINE = (
    "# CONFIG firmware=BMI160_SixAxis_v3_autoaddr chip_id=0xD1 address=0x69 "
    "acc_conf=0x27 acc_range=0x05 gyr_conf=0x27 gyr_range=0x02 "
    "pmu=0x14 err=0x00 odr_hz=50 accel_unit=g gyro_unit=deg/s calibrated=NO"
)


class DataLineTest(unittest.TestCase):
    def test_parses_reference_line(self) -> None:
        sample = parse_data_line(GOOD_LINE)
        self.assertEqual(sample.seq, 1267)
        self.assertEqual(sample.t_read_us, 27396329)
        self.assertAlmostEqual(sample.az_g, 0.99878)
        self.assertAlmostEqual(sample.gx_dps, -0.2439)
        self.assertEqual(sample.to_csv_line(), GOOD_LINE)

    def test_rejects_wrong_column_count(self) -> None:
        with self.assertRaises(LineParseError):
            parse_data_line("1,2,3")

    def test_rejects_non_finite(self) -> None:
        with self.assertRaises(LineParseError):
            parse_data_line(GOOD_LINE.replace("0.99878", "nan"))

    def test_rejects_out_of_range_raw(self) -> None:
        with self.assertRaises(LineParseError):
            parse_data_line(GOOD_LINE.replace(",-614,", ",-40000,"))

    def test_rejects_sensor_tick_overflow(self) -> None:
        with self.assertRaises(LineParseError):
            parse_data_line(GOOD_LINE.replace(",658965,", ",20000000,"))


class DiagnosticTest(unittest.TestCase):
    def test_config_line_is_valid_for_this_firmware(self) -> None:
        config = parse_config_line(CONFIG_LINE)
        self.assertTrue(config.valid, config.problems)
        self.assertEqual(config.address, "0x69")

    def test_config_line_flags_wrong_address(self) -> None:
        config = parse_config_line(CONFIG_LINE.replace("address=0x69", "address=0x70"))
        self.assertFalse(config.valid)

    def test_config_line_flags_calibrated_flag(self) -> None:
        config = parse_config_line(CONFIG_LINE.replace("calibrated=NO", "calibrated=YES"))
        self.assertFalse(config.valid)

    def test_stats_and_fatal_fields(self) -> None:
        kind, fields = parse_diagnostic("# STATS samples=2736 window_hz=49.800 read_errors=0")
        self.assertEqual(kind, "STATS")
        self.assertEqual(fields["window_hz"], "49.800")
        kind, _ = parse_diagnostic("# FATAL NO_FRESH_SIX_AXIS_DATA_FOR_1S")
        self.assertEqual(kind, "FATAL")


class CaptureFileTest(unittest.TestCase):
    def test_real_capture_matches_documented_rate(self) -> None:
        samples = read_capture(STATIC_CAPTURE)
        self.assertEqual(len(samples), 1496)
        self.assertAlmostEqual(read_rate_hz(samples), 49.73, places=1)
        self.assertEqual(samples[0].seq, 1267)
        self.assertEqual(samples[-1].seq - samples[0].seq + 1, len(samples))

    def test_round_trip_file(self) -> None:
        samples = [make_sample(seq, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)) for seq in range(1, 11)]
        with tempfile.TemporaryDirectory() as directory:
            path = write_capture_csv(Path(directory) / "capture.csv", samples)
            loaded = read_capture(path)
        self.assertEqual(len(loaded), 10)
        self.assertAlmostEqual(loaded[5].az_g, 1.0)

    def test_sequence_gap_is_rejected(self) -> None:
        lines = [CSV_HEADER]
        for seq in (1, 2, 4):
            lines.append(make_sample(seq, (0, 0, 0), (0, 0, 1)).to_csv_line())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gap.csv"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(LineParseError):
                read_capture(path)

    def test_malformed_row_is_counted(self) -> None:
        lines = [CSV_HEADER, make_sample(1, (0, 0, 0), (0, 0, 1)).to_csv_line(), "2,3"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(LineParseError):
                read_capture(path)


if __name__ == "__main__":
    unittest.main()
