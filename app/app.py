"""ESP32-CAM 实时人体检测 —— PC 端推理 + 本地网页 UI

用法：
    python app.py                                  # 用本机摄像头测试
    python app.py --source http://192.168.1.23/stream
    python app.py --source http://192.168.1.23/stream --detector yolo
    python app.py --self-test 40                   # 不启 UI，跑 N 帧存一张结果图

UI 打开后访问 http://127.0.0.1:8000
"""
import argparse
import json
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from detector import draw, make_detector
from sources import open_source

STATE = {
    "jpeg": None,
    "fid": 0,
    "stats": {"fps": 0.0, "persons": 0, "frames": 0, "source": "", "detector": "", "state": "启动中"},
}
_LOCK = threading.Lock()


class Pipeline(threading.Thread):
    def __init__(self, src: str, detector_name: str, jpeg_quality: int = 75,
                 max_width: int = 800, rotate: int = 0):
        super().__init__(daemon=True)
        self.src_arg = src
        self.detector = make_detector(detector_name)
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width
        self.rotate = rotate          # 摄像头装歪时用（顺时针角度）
        self.running = True
        self._times = deque(maxlen=20)

    def run(self):
        try:
            src = open_source(self.src_arg)
        except Exception as e:                       # noqa: BLE001
            with _LOCK:
                STATE["stats"].update(state=f"连接失败：{e}")
            print(f"[错误] {e}")
            return

        with _LOCK:
            STATE["stats"].update(state="运行中", source=src.desc, detector=self.detector.name)
        print(f"[信息] 视频源：{src.desc}")
        print(f"[信息] 检测器：{self.detector.name}")

        # 预热：首次推理含 CUDA 初始化（1~3 秒），提前跑掉，别让它污染 FPS 统计
        for _ in range(50):
            f0 = src.read()
            if f0 is not None:
                self.detector.detect(f0)
                break
            time.sleep(0.05)

        last_seq = -1
        while self.running:
            frame = src.read()
            if frame is None:
                time.sleep(0.01)
                continue
            # ESP32 只有十几帧/秒，而 CPU 能把同一帧算 100 次以上。
            # 帧序号没变就跳过，避免空转做无用的推理。
            if src.seq == last_seq:
                time.sleep(0.004)
                continue
            last_seq = src.seq

            if self.rotate:
                code = cv2.ROTATE_90_CLOCKWISE if self.rotate == 90 else (
                    cv2.ROTATE_180 if self.rotate == 180 else cv2.ROTATE_90_COUNTERCLOCKWISE)
                frame = cv2.rotate(frame, code)

            if frame.shape[1] > self.max_width:
                r = self.max_width / frame.shape[1]
                frame = cv2.resize(frame, (self.max_width, int(frame.shape[0] * r)))

            boxes = self.detector.detect(frame)

            self._times.append(time.time())
            fps = 0.0
            if len(self._times) >= 2:
                span = self._times[-1] - self._times[0]
                fps = (len(self._times) - 1) / span if span > 0 else 0.0

            frame = draw(frame, boxes, fps, self.detector.name)
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if not ok:
                continue

            with _LOCK:
                STATE["jpeg"] = buf.tobytes()
                STATE["fid"] += 1
                STATE["stats"].update(fps=round(fps, 1), persons=len(boxes),
                                      frames=STATE["stats"]["frames"] + 1)
        src.release()


PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>人体检测 · ESP32-CAM</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;background:#0f1115;color:#e8eaed;
       font-family:system-ui,"Segoe UI","Microsoft YaHei",sans-serif;
       display:flex;flex-direction:column;align-items:center;padding:24px 16px}
  h1{font-size:17px;font-weight:500;margin:0 0 4px}
  .sub{font-size:13px;color:#8b94a3;margin-bottom:18px}
  .card{background:#161a21;border:1px solid #232833;border-radius:14px;padding:12px;
        box-shadow:0 8px 28px rgba(0,0,0,.35)}
  img{display:block;max-width:100%;border-radius:8px;background:#000}
  .bar{display:flex;gap:26px;justify-content:center;margin-top:14px;flex-wrap:wrap}
  .k{font-size:12px;color:#8b94a3;margin-bottom:2px}
  .v{font-size:19px;font-weight:500;font-variant-numeric:tabular-nums}
  .ok{color:#5dcf8a}.bad{color:#e2706d}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;
       background:#5dcf8a;margin-right:6px;animation:p 1.6s infinite}
  @keyframes p{50%{opacity:.25}}
</style></head>
<body>
  <h1><span class="dot"></span>ESP32-CAM 实时人体检测</h1>
  <div class="sub" id="sub">AI 推理运行在本机</div>
  <div class="card"><img src="/video" alt="video"></div>
  <div class="bar">
    <div><div class="k">检测到人数</div><div class="v ok" id="persons">-</div></div>
    <div><div class="k">推理帧率</div><div class="v" id="fps">-</div></div>
    <div><div class="k">累计帧</div><div class="v" id="frames">-</div></div>
    <div><div class="k">状态</div><div class="v" id="state">-</div></div>
  </div>
<script>
async function tick(){
  try{
    const s = await (await fetch('/stats')).json();
    document.getElementById('persons').textContent = s.persons;
    document.getElementById('fps').textContent = s.fps.toFixed(1);
    document.getElementById('frames').textContent = s.frames;
    const st = document.getElementById('state');
    st.textContent = s.state;
    st.className = 'v ' + (s.state === '运行中' ? 'ok' : 'bad');
    document.getElementById('sub').textContent = (s.source||'') + ' · ' + (s.detector||'');
  }catch(e){}
}
setInterval(tick, 800); tick();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):        # 静音，避免刷屏
        pass

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/stats":
            with _LOCK:
                body = json.dumps(STATE["stats"], ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/video":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                last_id = -1
                while True:
                    with _LOCK:
                        jpg, fid = STATE["jpeg"], STATE["fid"]
                    if jpg and fid != last_id:      # 只推新帧，不重复发同一张
                        last_id = fid
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n")
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.005)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
        else:
            self.send_error(404)


def self_test(src: str, detector_name: str, n_frames: int, out_path: str):
    """不开 UI，跑 N 帧并存一张标注图，用于验证链路。"""
    src_obj = open_source(src)
    det = make_detector(detector_name)
    print(f"[自检] 源={src_obj.desc} 检测器={det.name}")
    last, boxes, t0 = None, [], time.time()
    for i in range(n_frames):
        f = src_obj.read()
        if f is None:
            time.sleep(0.02)
            continue
        boxes = det.detect(f)
        last = f
    dt = time.time() - t0
    if last is None:
        print("[自检] 失败：一帧都没取到")
        return 1
    fps = n_frames / dt if dt > 0 else 0
    cv2.imwrite(out_path, draw(last.copy(), boxes, fps, det.name))
    src_obj.release()
    print(f"[自检] {n_frames} 帧 / {dt:.1f}s → {fps:.1f} FPS，最后一帧检出 {len(boxes)} 人")
    print(f"[自检] 结果图：{out_path}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0",
                    help="0=本机摄像头；或 ESP32 流地址 http://<ip>/stream")
    ap.add_argument("--detector", default="yolo", choices=["hog", "yolo"])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--self-test", type=int, default=0, metavar="N")
    ap.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                    help="画面顺时针旋转角度，摄像头装歪时用")
    args = ap.parse_args()

    if args.self_test:
        raise SystemExit(self_test(args.source, args.detector, args.self_test, "selftest_result.jpg"))

    Pipeline(args.source, args.detector, rotate=args.rotate).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"[信息] UI 已启动：{url}  （Ctrl+C 退出）")
    try:
        if not args.no_browser:
            webbrowser.open(url)
    except Exception:       # noqa: BLE001
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[信息] 已退出")


if __name__ == "__main__":
    main()
