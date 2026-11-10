"""Single-owner USB transport: JPEG + command reply multiplexing, no raw image saves."""
import re
import threading
import time
import zlib

import cv2
import numpy as np
import serial


class SerialCameraSource:
    kind = "serial"

    def __init__(self, port, baud=921600, timeout=12):
        self.desc = f"USB camera {port} @ {baud}"
        self.seq = 0
        self._frame = None
        self._frame_at = 0.0
        self._alarm = False
        self._decision_at = 0.0
        self._error = None
        self.radio = {}
        self.metrics = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.port = serial.Serial()
        self.port.port, self.port.baudrate = port, baud
        self.port.timeout, self.port.write_timeout = 0.3, 2
        self.port.dtr = False
        self.port.rts = False
        self.port.open()
        if hasattr(self.port, 'set_buffer_size'):
            # CH340 at 921600 can outrun the Windows default buffer during inference stalls.
            self.port.set_buffer_size(rx_size=262144, tx_size=4096)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.seq:
                return
            if self._error:
                break
            time.sleep(0.05)
        self.release()
        raise RuntimeError(self._error or "USB camera first-frame timeout")

    def _line(self, deadline):
        # read one byte at a time: a timeout must never discard a partial header
        buf = bytearray()
        while time.monotonic() < deadline and not self._stop.is_set():
            c = self.port.read(1)
            if c == b'\n':
                return bytes(buf).rstrip(b'\r').decode('ascii', errors='strict')
            buf.extend(c)
            if len(buf) > 2048:
                raise ValueError('USB text header too long')
        raise TimeoutError('USB line timeout')

    def _until(self, prefix, seconds=4):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            line = self._line(deadline)
            if line.startswith('ERR_'):
                raise RuntimeError(line)
            if line.startswith(prefix):
                return line
        raise TimeoutError(f'Expected {prefix}')

    def _exact(self, size, seconds=4):
        deadline = time.monotonic() + seconds
        data = bytearray()
        while len(data) < size and time.monotonic() < deadline and not self._stop.is_set():
            data.extend(self.port.read(size-len(data)))
        if len(data) != size:
            raise TimeoutError('Truncated JPEG')
        return bytes(data)

    def _handshake(self):
        """Retry startup probes and recover a CAM left in reset after USB reconnect."""
        deadline = time.monotonic() + 8
        started = time.monotonic()
        next_probe = 0.0
        reset_once = False
        while time.monotonic() < deadline and not self._stop.is_set():
            now = time.monotonic()
            if now - started > 2 and not reset_once:
                # CAM only: no image/control result has been accepted yet.
                self.port.rts = True
                self._stop.wait(0.12)
                self.port.rts = False
                self._stop.wait(1.3)
                reset_once = True
                next_probe = 0.0
            if time.monotonic() >= next_probe:
                self.port.write(b'INFO\n')
                next_probe = time.monotonic() + 0.7
            try:
                line = self._line(min(deadline, time.monotonic()+0.4))
            except (TimeoutError, UnicodeDecodeError):
                # ROM banners use another baud rate. Only startup tolerates them.
                continue
            if line.startswith('ERR_'):
                raise RuntimeError(line)
            if line.startswith('INFO '):
                if 'fw=Cam_USB_Bridge_v1 ' not in line:
                    raise RuntimeError('Wrong camera firmware; expected Cam_USB_Bridge_v1')
                return
        raise TimeoutError('Camera INFO handshake timed out; check USB and board power')

    def _loop(self):
        try:
            self._handshake()
            while not self._stop.is_set():
                cycle_start = time.monotonic()
                with self._lock:
                    on = self._alarm and time.monotonic()-self._decision_at < 1.0
                self.port.write((b'ALARM 1\n' if on else b'ALARM 0\n') + b'STATUS\nCAPTURE\n')
                self._until('CMD_OK ')
                radio = self._until('BRIDGE ')
                fields = dict(token.split('=',1) for token in radio.split()[1:] if '=' in token)
                meta = self._until('META ')
                match = re.search(r'\bseq=(\d+)\b',meta)
                if not match:
                    raise ValueError('Missing image sequence')
                image_seq = int(match[1])
                metadata = dict(x.split("=",1) for x in meta.split()[1:])
                header = self._until('IMG ')
                match = re.fullmatch(r'IMG (\d+) crc=([0-9a-fA-F]{8})', header)
                if not match or not 4 <= int(match[1]) <= 2_097_152:
                    raise ValueError('Invalid image header')
                jpeg = self._exact(int(match[1]))
                if zlib.crc32(jpeg) != int(match[2],16) or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                    raise ValueError('JPEG checksum/markers mismatch')
                done = self._until('DONE ')
                if not re.search(rf'\bseq={image_seq}\b',done) or f'written={len(jpeg)} ' not in done:
                    raise ValueError('Image trailer mismatch')
                frame = cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
                if frame is None or frame.shape[:2] != (480,640):
                    raise ValueError('JPEG decode/dimensions failed')
                with self._lock:
                    self.metrics = {
                        "jpeg_bytes":len(jpeg),
                        "capture_ms":(int(metadata.get("acquired_us",0))-int(metadata.get("request_us",0)))/1000,
                        "sensor_frame_age_ms":(int(metadata.get("acquired_us",0))-int(metadata.get("frame_us",0)))/1000,
                        "uart_send_ms":int(re.search(r"send_us=(\d+)",done)[1])/1000,
                        "cycle_ms":(time.monotonic()-cycle_start)*1000,
                    }
                    self.radio = fields
                    self._frame, self._frame_at = frame,time.monotonic()
                    self.seq += 1
        except Exception as exc:
            if not self._stop.is_set():
                self._error = str(exc)
        finally:
            # No stale ON refresh on failure. CAM and S3 watchdogs expire on their own.
            if self.port.is_open:
                try:
                    self.port.write(b'ALARM 0\n')
                except Exception:
                    pass  # A disconnected USB port cannot deliver OFF; device watchdogs expire.
                finally:
                    self.port.close()

    def set_alarm(self,on):
        with self._lock:
            self._alarm = bool(on)
            self._decision_at = time.monotonic()

    def read(self):
        if self._error:
            raise RuntimeError(self._error)
        with self._lock:
            if time.monotonic()-self._frame_at > 1.5:
                return None
            return None if self._frame is None else self._frame.copy()

    def release(self):
        self._stop.set()
        self._thread.join(timeout=5)
