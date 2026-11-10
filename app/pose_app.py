"""动作规范实时判定 demo（电脑端推理）

用法：
    python app.py --source http://<ESP32_IP>/stream --rotate 270 --action squat
    python app.py --action pushup            # 用本机摄像头
    python app.py --self-test 40 --action squat   # 不开 UI，跑 N 帧存图

UI: http://127.0.0.1:8010
"""
import argparse
import json
import os
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from form_rules import make_analyzer
from pose_engine import L_KNE, R_KNE, SKELETON, PoseEngine
from sources import open_source

STATE = {"jpeg": None, "fid": 0,
         "pose": {"action": "", "phase": "启动中", "reps": 0, "angles": {},
                  "primary": None, "last": None},
         "stats": {"fps": 0.0, "frames": 0, "persons": 0, "source": "", "state": "启动中"}}
_LOCK = threading.Lock()

GREEN = (90, 220, 130)
YELLOW = (60, 190, 245)
RED = (90, 90, 235)

# cv2.putText 只支持 ASCII，中文会变成 ?????。用系统字体走 PIL 渲染。
_FONT_CACHE = {}
_FONT_FILE = next((p for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
                               "C:/Windows/Fonts/simsun.ttc") if os.path.exists(p)), None)


def _font(size: int):
    if _FONT_FILE is None:
        return None
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = ImageFont.truetype(_FONT_FILE, size)
    return _FONT_CACHE[size]


def draw_cn(frame, items):
    """在帧上写中文。items: [(文本, (x, y), 字号, BGR 颜色), ...]"""
    if _FONT_FILE is None or not items:
        return frame
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    for text, pos, size, color in items:
        d.text(pos, text, font=_font(size), fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def draw_pose(frame, kpts, res, action):
    h, w = frame.shape[:2]

    for a, b in SKELETON:
        if kpts[a, 2] > 0.35 and kpts[b, 2] > 0.35:
            cv2.line(frame, tuple(kpts[a, :2].astype(int)), tuple(kpts[b, :2].astype(int)),
                     GREEN, 2, cv2.LINE_AA)
    for i in range(17):
        if kpts[i, 2] > 0.35:
            cv2.circle(frame, tuple(kpts[i, :2].astype(int)), 3, (255, 255, 255), -1, cv2.LINE_AA)

    # 主角度标注：深蹲标在膝，俯卧撑标在肘
    if action == "squat" and res.get("primary"):
        for idx in (L_KNE, R_KNE):
            if kpts[idx, 2] > 0.35:
                p = tuple(kpts[idx, :2].astype(int))
                cv2.putText(frame, f"{res['primary']:.0f}", (p[0] + 8, p[1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2, cv2.LINE_AA)

    ok = res.get("last") and res["last"]["ok"]
    color = GREEN if ok else (YELLOW if not res.get("last") else RED)

    cv2.rectangle(frame, (0, 0), (w, 38), (28, 28, 32), -1)
    cv2.rectangle(frame, (0, h - 40), (w, h), (28, 28, 32), -1)

    texts = [(f"{res['action']} · {res['phase']} · 第 {res['reps']} 次", (10, 9), 18, (235, 235, 235))]
    if res.get("primary"):
        texts.append((f"{res['primary']:.0f}°", (w - 78, 7), 22, color))

    if res.get("last"):
        last = res["last"]
        msg = "姿势标准" if last["ok"] else "；".join(last["violations"])
        texts.append((msg[:52], (10, h - 32), 16, GREEN if last["ok"] else RED))
    else:
        texts.append(("做一个完整动作开始计次…", (10, h - 32), 16, (170, 170, 170)))

    return draw_cn(frame, texts)


class Pipeline(threading.Thread):
    def __init__(self, src, action, rotate=0, max_width=800, jpeg_quality=75):
        super().__init__(daemon=True)
        self.src_arg, self.action, self.rotate = src, action, rotate
        self.max_width, self.jpeg_quality = max_width, jpeg_quality
        self.engine = PoseEngine()
        self.analyzer = make_analyzer(action)
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
            STATE["stats"].update(state="运行中", source=src.desc)
        print(f"[信息] 视频源：{src.desc} | 模型：{self.engine.name} | 动作：{self.analyzer.name}")

        for _ in range(60):                          # 预热，消化首次 CUDA 初始化
            f0 = src.read()
            if f0 is not None:
                self.engine.infer(f0)
                break
            time.sleep(0.05)

        last_seq = -1
        alarm_until = 0.0
        last_rep = 0
        missing_since = None
        while self.running:
            try:
                frame = src.read()
            except Exception as exc:
                with _LOCK:
                    STATE["stats"].update(state=f"USB/source error: {exc}", alarm=False, persons=0)
                if hasattr(src,"set_alarm"):
                    src.set_alarm(False)
                src.release()
                return
            if frame is None:
                time.sleep(0.01)
                continue
            if src.seq == last_seq:
                time.sleep(0.004)
                continue
            last_seq = src.seq

            if self.rotate:
                code = (cv2.ROTATE_90_CLOCKWISE if self.rotate == 90 else
                        cv2.ROTATE_180 if self.rotate == 180 else cv2.ROTATE_90_COUNTERCLOCKWISE)
                frame = cv2.rotate(frame, code)
            if frame.shape[1] > self.max_width:
                r = self.max_width / frame.shape[1]
                frame = cv2.resize(frame, (self.max_width, int(frame.shape[0] * r)))

            kpts, _ = self.engine.infer(frame)
            valid_pose = kpts is not None and any(
                all(kpts[i, 2] >= 0.35 for i in indices)
                for indices in ([(11, 13, 15), (12, 14, 16)] if self.action == "squat"
                                else [(5, 7, 9, 11, 15), (6, 8, 10, 12, 16)]))
            if valid_pose and self.action == "squat":
                valid_pose = all(kpts[i, 2] >= 0.35 for i in (5, 6, 11, 12))
            if valid_pose:
                missing_since = None
                res = self.analyzer.update(kpts)
                if res["reps"] > last_rep:
                    last_rep = res["reps"]
                    alarm_until = time.monotonic()+2.0 if res.get("last") and not res["last"]["ok"] else 0.0
                frame = draw_pose(frame, kpts, res, self.action)
            else:
                alarm_until = 0.0
                if missing_since is None:
                    missing_since = time.monotonic()
                if time.monotonic()-missing_since > 1.0:
                    completed_reps = self.analyzer.reps
                    self.analyzer = make_analyzer(self.action)
                    self.analyzer.reps = completed_reps
                    last_rep = completed_reps
                res = self.analyzer._snapshot()
                cv2.rectangle(frame, (0, 0), (frame.shape[1], 38), (28, 28, 32), -1)
                frame = draw_cn(frame, [("未检测到人 — 请确保全身进入画面",
                                         (10, 9), 17, (180, 180, 180))])

            if hasattr(src,"set_alarm"):
                src.set_alarm(valid_pose and time.monotonic()<alarm_until)
            self._times.append(time.time())
            fps = 0.0
            if len(self._times) >= 2:
                span = self._times[-1] - self._times[0]
                fps = (len(self._times) - 1) / span if span > 0 else 0.0

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if not ok:
                continue
            with _LOCK:
                STATE["jpeg"] = buf.tobytes()
                STATE["fid"] += 1
                STATE["pose"] = json.loads(json.dumps(res, default=str))
                STATE["stats"].update(fps=round(fps, 1), persons=int(kpts is not None),
                                      alarm=bool(valid_pose and time.monotonic()<alarm_until),
                                      radio=getattr(src,"radio",{}),
                                      transport=getattr(src,"metrics",{}),
                                      frames=STATE["stats"]["frames"] + 1)
        src.release()


PAGE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>动作规范判定</title><style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:#0f1115;color:#e8eaed;
 font-family:system-ui,"Segoe UI","Microsoft YaHei",sans-serif;
 display:flex;flex-direction:column;align-items:center;padding:22px 16px}
h1{font-size:17px;font-weight:500;margin:0 0 14px}
.wrap{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap;justify-content:center}
.card{background:#161a21;border:1px solid #232833;border-radius:14px;padding:12px}
img{display:block;max-width:100%;border-radius:8px;background:#000}
.panel{width:250px;background:#161a21;border:1px solid #232833;border-radius:14px;padding:16px}
.row{display:flex;justify-content:space-between;padding:7px 0;font-size:13px;
 border-bottom:1px solid #232833}
.row:last-child{border:0}
.k{color:#8b94a3}.v{font-weight:500;font-variant-numeric:tabular-nums}
.ok{color:#5dcf8a}.bad{color:#e2706d}.warn{color:#e2b15d}
.msg{margin-top:12px;font-size:13px;line-height:1.7;color:#c9d1dc}
.msg li{margin-bottom:4px}
</style></head><body>
<h1>动作规范实时判定</h1>
<div class="wrap">
  <div class="card"><img src="/video"></div>
  <div class="panel">
    <div class="row"><span class="k">动作</span><span class="v" id="action">-</span></div>
    <div class="row"><span class="k">阶段</span><span class="v" id="phase">-</span></div>
    <div class="row"><span class="k">完成次数</span><span class="v ok" id="reps">0</span></div>
    <div class="row"><span class="k" id="a1k">角度</span><span class="v" id="a1">-</span></div>
    <div class="row"><span class="k" id="a2k">次要</span><span class="v" id="a2">-</span></div>
    <div class="row"><span class="k">帧率</span><span class="v" id="fps">-</span></div>
    <div class="msg" id="msg">等待动作…</div>
  </div>
</div>
<script>
async function tick(){
 try{
  const s = await (await fetch('/stats')).json();
  const p = s.pose || {};
  document.getElementById('action').textContent = p.action || '-';
  document.getElementById('phase').textContent = p.phase || '-';
  document.getElementById('reps').textContent = p.reps ?? 0;
  const a = p.angles || {};
  const ks = Object.keys(a);
  document.getElementById('a1k').textContent = ks[0] || '角度';
  document.getElementById('a1').textContent = ks[0] ? (a[ks[0]] ?? '-') + '°' : '-';
  document.getElementById('a2k').textContent = ks[1] || '次要';
  document.getElementById('a2').textContent = ks[1] ? (a[ks[1]] ?? '-') : '-';
  document.getElementById('fps').textContent = (s.stats.fps||0).toFixed(1);
  const m = document.getElementById('msg');
  if (p.last){
    m.innerHTML = p.last.ok
      ? '<span class="ok">第 '+p.last.rep+' 次：姿势标准 ✓</span>'
      : '<span class="bad">第 '+p.last.rep+' 次：</span><ul>' +
        p.last.violations.map(v=>'<li>'+v+'</li>').join('') + '</ul>';
  } else { m.textContent = '等待一个完整动作…'; }
 }catch(e){}
}
setInterval(tick, 700); tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/stats":
            with _LOCK:
                body = json.dumps({"pose": STATE["pose"], "stats": STATE["stats"]},
                                  ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8")
        elif self.path == "/video":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                last = -1
                while True:
                    with _LOCK:
                        jpg, fid = STATE["jpeg"], STATE["fid"]
                    if jpg and fid != last:
                        last = fid
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n")
                        self.wfile.write(jpg + b"\r\n")
                    time.sleep(0.005)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
        else:
            self.send_error(404)


def self_test(src, action, n, out_path, rotate):
    s = open_source(src)
    eng, ana = PoseEngine(), make_analyzer(action)
    print(f"[自检] 源={s.desc} 动作={ana.name}")
    last, res = None, None
    t0 = time.time()
    got = 0
    while got < n:
        f = s.read()
        if f is None:
            time.sleep(0.02)
            continue
        got += 1
        if rotate:
            code = (cv2.ROTATE_90_CLOCKWISE if rotate == 90 else
                    cv2.ROTATE_180 if rotate == 180 else cv2.ROTATE_90_COUNTERCLOCKWISE)
            f = cv2.rotate(f, code)
        k, _ = eng.infer(f)
        if k is not None:
            res = ana.update(k)
            last = draw_pose(f, k, res, action)
        else:
            last = f
    dt = time.time() - t0
    s.release()
    if last is None:
        print("[自检] 失败：没有取到画面")
        return 1
    cv2.imwrite(out_path, last)
    print(f"[自检] {got} 帧 / {dt:.1f}s → {got/dt:.1f} FPS")
    print(f"[自检] 角度={res['angles'] if res else None} 阶段={res['phase'] if res else None}")
    print(f"[自检] 结果图 {out_path}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--action", default="squat", choices=["squat", "pushup"])
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270])
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--self-test", type=int, default=0, metavar="N")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        raise SystemExit(self_test(args.source, args.action, args.self_test,
                                   "selftest_pose.jpg", args.rotate))

    Pipeline(args.source, args.action, args.rotate).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"[信息] UI: {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:      # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[信息] 已退出")


if __name__ == "__main__":
    main()
