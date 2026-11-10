"""视频源：本地摄像头 / ESP32-CAM 的 MJPEG 流。

ESP32-CAM 跑 CameraWebServer 示例时，视频流地址通常是：
    http://<板子IP>/stream          （多数编译版本）
    http://<板子IP>:81/stream       （部分旧版本）
自动探测地址见 find_camera.py。
"""
import threading
import time
import urllib.request

import cv2
import numpy as np


class WebcamSource:
    """本地 USB 摄像头。"""

    kind = "webcam"

    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            raise RuntimeError(f"打不开摄像头 index={index}")
        self.desc = f"本地摄像头 #{index}"
        self.seq = 0

    def read(self):
        ok, frame = self.cap.read()
        if ok:
            self.seq += 1
            return frame
        return None

    def release(self):
        self.cap.release()


class MJPEGSource:
    """ESP32-CAM 的 multipart/x-mixed-replace 流。

    自己解析 multipart 边界而不是用 cv2.VideoCapture —— cv2 对 MJPEG 会缓冲，
    延迟能积到十几秒；手动取最新的 JPEG 帧延迟稳定在一帧左右。
    """

    kind = "mjpeg"

    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url
        self.desc = url
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        self._error = None
        self._last = 0.0
        self.seq = 0            # 每来一个新帧 +1，供上层判断是否是同一帧
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        # 等第一帧，确认流是通的
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self._frame is not None:
                return
            if self._error:
                raise RuntimeError(f"连接失败：{self._error}")
            time.sleep(0.05)
        raise RuntimeError("连接超时：10 秒内没有收到任何画面")

    def _loop(self):
        try:
            # 强制直连，不走系统代理：代理会把 192.168.x.x 也转发出去导致连不上
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            stream = opener.open(self.url, timeout=10)
            buf = b""
            while self._running:
                chunk = stream.read(4096)
                if not chunk:
                    self._error = "流已结束"
                    break
                buf += chunk
                while True:
                    start = buf.find(b"\xff\xd8")
                    end = buf.find(b"\xff\xd9", start + 2 if start != -1 else 0)
                    if start == -1 or end == -1:
                        # 防止缓冲区无限增长
                        if len(buf) > 2_000_000:
                            buf = buf[-1_000_000:]
                        break
                    jpg = buf[start:end + 2]
                    buf = buf[end + 2:]
                    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        with self._lock:
                            self._frame = img
                            self._last = time.time()
                            self.seq += 1
        except Exception as e:      # noqa: BLE001
            self._error = str(e)[:200]

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def release(self):
        self._running = False


def open_source(src: str):
    """src: '0' 表示本地摄像头，'http://...' 表示 ESP32 流。"""
    if src.startswith("serial://"):
        from serial_camera import SerialCameraSource
        from urllib.parse import urlsplit, parse_qs
        parsed = urlsplit(src)
        baud = int(parse_qs(parsed.query).get("baud", ["921600"])[0])
        return SerialCameraSource(parsed.netloc, baud=baud)
    if src.isdigit():
        return WebcamSource(int(src))
    if src.startswith("http://") or src.startswith("https://"):
        return MJPEGSource(src)
    raise ValueError(f"无法识别的视频源：{src}（用 0 表示本机摄像头，或 http://ip/stream）")
