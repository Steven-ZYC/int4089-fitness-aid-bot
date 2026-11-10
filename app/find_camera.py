"""扫描局域网，找出 ESP32-CAM 的地址。

ESP32-CAM 跑 CameraWebServer 时一般监听 80 或 81 端口，网页标题里带 "ESP32"。
找到后会直接给出可用的 --source 参数。

    python find_camera.py
    python find_camera.py --subnet 192.168.1
"""
import argparse
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PORTS = (81, 80)


def local_subnet() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # 不会真的发包，只为拿到出口网卡 IP
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ".".join(ip.split(".")[:3])


def probe(ip: str):
    for port in PORTS:
        try:
            with socket.create_connection((ip, port), timeout=0.35):
                pass
        except OSError:
            continue
        for path in ("/", "/stream"):
            url = f"http://{ip}:{port}{path}"
            try:
                with urllib.request.urlopen(url, timeout=1.5) as r:
                    head = r.read(2048)
                    ctype = r.headers.get("Content-Type", "")
            except Exception:            # noqa: BLE001
                continue
            if "multipart" in ctype:
                return (ip, port, path, "MJPEG 视频流")
            if b"ESP32" in head or b"esp32" in head or b"camera" in head.lower():
                return (ip, port, path, "ESP32 网页（含视频流）")
        return (ip, port, "/", "HTTP 服务（未确认是 ESP32）")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subnet", default=None, help="例如 192.168.1；默认自动探测")
    args = ap.parse_args()

    subnet = args.subnet or local_subnet()
    print(f"[扫描] {subnet}.1 - {subnet}.254 ...")
    targets = [f"{subnet}.{i}" for i in range(1, 255)]

    hits = []
    with ThreadPoolExecutor(max_workers=128) as ex:
        for res in ex.map(probe, targets):
            if res:
                hits.append(res)
                print(f"  ✓ {res[0]}:{res[1]}  {res[3]}")
                break_all = False

    if not hits:
        print("[结果] 没找到。检查：① ESP32 是否已连上同一个 Wi-Fi ② 是否已烧录 CameraWebServer")
        return

    print("\n[结果] 可用的 --source 参数：")
    for ip, port, path, kind in hits:
        print(f"   --source http://{ip}:{port}/stream     # {kind}")


if __name__ == "__main__":
    main()
