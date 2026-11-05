"""Line-protocol state for the BMI160 stream and a pyserial background reader.

The parser is transport-independent (fed line by line) so tests can drive
it without hardware. Observed on this board: after the ESP32-S3 is left
running with no serial reader (or held in reset by a previous tool), the
port opens fine but no bytes arrive until the EN line is pulsed. The
reader therefore pulses RTS (EN) after opening by default, exactly like
esptool-style resets, then tolerates the ESP-ROM boot banner that follows.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .csvio import (
    CSV_HEADER,
    LineParseError,
    Sample,
    is_data_line,
    is_diagnostic,
    parse_config_line,
    parse_data_line,
    parse_diagnostic,
)

SEQUENCE_GAP_LIMIT = 5
RESET_PULSE_S = 0.12
RESET_SETTLE_S = 0.10


@dataclass
class StreamStats:
    lines_received: int = 0
    samples: int = 0
    malformed_rows: int = 0
    ignored_lines: int = 0
    sequence_gaps: int = 0
    config_reports: int = 0
    config_problems: int = 0
    last_window_hz: float = 0.0
    last_read_errors: int = 0
    fatal_reason: str = ""
    address: str = ""


class ImuStreamParser:
    """Feed decoded serial lines one at a time; callbacks receive results."""

    def __init__(
        self,
        on_sample: Callable[[Sample], None],
        on_fatal: Optional[Callable[[str], None]] = None,
        on_config: Optional[Callable[[str, bool], None]] = None,
        on_first_line: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.on_sample = on_sample
        self.on_fatal = on_fatal
        self.on_config = on_config
        self.on_first_line = on_first_line
        self.stats = StreamStats()
        self._last_seq: int | None = None
        self._last_read_us: int | None = None

    def feed(self, raw_line: str) -> None:
        line = raw_line.strip()
        if not line or line == CSV_HEADER:
            return
        self.stats.lines_received += 1
        if is_diagnostic(line):
            self._handle_diagnostic(line)
            return
        if not is_data_line(line):
            # ESP-ROM boot banner and other noise; keep a visible counter.
            self.stats.ignored_lines += 1
            if self.stats.ignored_lines == 1 and self.on_first_line is not None:
                self.on_first_line(line)
            return
        try:
            sample = parse_data_line(line)
        except LineParseError:
            self.stats.malformed_rows += 1
            return
        if self._last_read_us is not None and sample.t_read_us <= self._last_read_us:
            self.stats.malformed_rows += 1
            return
        if self._last_seq is not None and sample.seq != self._last_seq + 1:
            self.stats.sequence_gaps += 1
            if sample.seq - self._last_seq > SEQUENCE_GAP_LIMIT:
                self._fail(f"sequence jumped {self._last_seq} -> {sample.seq}")
                return
        self._last_seq = sample.seq
        self._last_read_us = sample.t_read_us
        self.stats.samples += 1
        self.on_sample(sample)

    def _handle_diagnostic(self, line: str) -> None:
        kind, fields = parse_diagnostic(line)
        if kind == "CONFIG":
            config = parse_config_line(line)
            self.stats.config_reports += 1
            if config.address:
                self.stats.address = config.address
            if not config.valid:
                self.stats.config_problems += 1
            if self.on_config is not None:
                self.on_config(line, config.valid)
        elif kind == "STATS":
            try:
                self.stats.last_window_hz = float(fields.get("window_hz", "0"))
                self.stats.last_read_errors = int(fields.get("read_errors", "0"))
            except ValueError:
                self.stats.malformed_rows += 1
            if self.stats.last_read_errors:
                self._fail(f"device reported read_errors={self.stats.last_read_errors}")
        elif kind == "FATAL":
            self._fail(line[len("# FATAL "):].strip() if line.startswith("# FATAL ") else line)

    def _fail(self, reason: str) -> None:
        self.stats.fatal_reason = reason
        if self.on_fatal is not None:
            self.on_fatal(reason)


def _apply_line_state(port, dtr: bool, rts: bool) -> None:
    try:
        port.dtr = dtr
        port.rts = rts
    except Exception:
        pass


def reset_device(port, pulse_s: float = RESET_PULSE_S, settle_s: float = RESET_SETTLE_S) -> None:
    """Pulse RTS (wired to EN on CH340 boards) to restart the ESP32-S3."""
    _apply_line_state(port, dtr=False, rts=True)
    time.sleep(pulse_s)
    _apply_line_state(port, dtr=False, rts=False)
    time.sleep(settle_s)


class ImuSerialReader:
    """Background thread reading lines from a serial port into the parser."""

    def __init__(
        self,
        port: str,
        on_sample: Callable[[Sample], None],
        on_fatal: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        baudrate: int = 115200,
        reset_on_open: bool = True,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.reset_on_open = reset_on_open
        self.parser = ImuStreamParser(
            on_sample,
            on_fatal=on_fatal,
            on_first_line=lambda line: self._status(f"收到串口输出（首行：{line[:60]}）"),
        )
        self.on_status = on_status
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._serial = None
        self.error: str = ""

    def _status(self, text: str) -> None:
        if self.on_status is not None:
            self.on_status(text)

    def start(self) -> None:
        import serial  # imported lazily so tests never need pyserial

        self._serial = serial.Serial()
        self._serial.port = self.port
        self._serial.baudrate = self.baudrate
        self._serial.timeout = 0.2
        self._serial.rtscts = False
        self._serial.dsrdtr = False
        self._serial.dtr = False
        self._serial.rts = False
        try:
            self._serial.open()
        except Exception as error:  # SerialException varies across versions
            self.error = f"无法打开 {self.port}：{error}"
            raise
        if self.reset_on_open:
            self._status(f"已在打开 {self.port} 时复位 ESP32-S3（RTS/EN 脉冲）")
            reset_device(self._serial)
        self._status(f"已连接 {self.port} @ {self.baudrate}，等待数据…")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="imu-serial", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        serial = self._serial
        assert serial is not None
        while not self._stop.is_set():
            try:
                raw = serial.readline()
            except Exception as error:
                if not self._stop.is_set():
                    self.error = f"串口读取失败：{error}"
                    self._status(self.error)
                break
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace")
            self.parser.feed(line)
            if self.parser.stats.fatal_reason:
                break
        self._status("读线程已停止")

    def stop(self) -> None:
        self._stop.set()
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=1.0)
        self._status("已断开")

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def list_serial_ports() -> list[str]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [port.device for port in list_ports.comports()]
