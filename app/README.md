# 电脑端实时姿势检测服务（ESP32-CAM 图像 → 电脑 AI → 网页 UI）

本目录对应 **Phase 1 Prototype**：ESP32-CAM 只负责采集推流，**AI 推理在电脑上完成**，
浏览器查看实时结果。这是「电脑端 AI 推理／分析流程」的第一版实现。

> ⚠️ 本阶段的 ESP32-CAM 推流固件（`firmware/esp32_cam_stream/`）只是为了打通链路写的
> **临时最小件**。按最新分工，ESP32-CAM 的图像采集固件由 **Dong Yuankun** 负责
> （见 `firmware/esp32-camera/`），联调时应以他那边的实现为准，本目录的固件随时可被替换。

```
ESP32-CAM ──WiFi / MJPEG──> 电脑（本程序）──> 本地网页 UI
   (采集推流)                YOLOv8n 推理 7ms      127.0.0.1:8000
```

## 目录

| 文件 | 说明 |
| --- | --- |
| `app.py` | HTTP 服务（页面 / MJPEG 推流 / 状态接口）+ 推理管线 |
| `sources.py` | 视频源抽象：本地摄像头、ESP32 的 MJPEG 流 |
| `detector.py` | 检测器：YOLOv8n（默认）／OpenCV HOG |
| `find_camera.py` | 扫描局域网，找出 ESP32-CAM 的流地址 |
| `firmware/esp32_cam_stream/` | 临时推流固件 + `secrets.example.h` |

## 环境

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt

# GPU 为 NVIDIA Blackwell（如 RTX 50 系，sm_120）时必须用 cu128 轮子，
# 用 cu121/cu124 会报 "no kernel image is available for execution on the device"
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

> **OpenCV 必须固定在 4.x**：5.0 移除了 `HOGDescriptor` 和 `CascadeClassifier` 的 Python 绑定，
> `--detector hog` 会直接 `AttributeError`。

## 运行

```bash
# 接 ESP32-CAM
python app.py --source http://<ESP32_IP>/stream --rotate 270

# 没有硬件时先用本机摄像头验证
python app.py
```

浏览器自动打开 `http://127.0.0.1:8000`，显示实时画面、检测框、人数和帧率。

**不知道 ESP32 的 IP？**

```bash
python find_camera.py            # 扫描当前网段，直接给出可用的 --source 参数
```

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--source` | `0` | `0`=本机摄像头；或 `http://<ip>/stream` |
| `--rotate` | `0` | 顺时针旋转 `0/90/180/270`，摄像头装歪时用 |
| `--detector` | `yolo` | `yolo`=YOLOv8n；`hog`=OpenCV 内置，快但漏检多 |
| `--port` | `8000` | 网页端口 |
| `--no-browser` | 关 | 不自动打开浏览器 |
| `--self-test N` | - | 不开 UI，跑 N 帧存图并打印统计，用于排查链路 |

`--rotate` 不是可选优化：实测摄像头装歪 90° 时，画面里明明有人，YOLO 仍判 **0 人**；
旋转后立即变为 `1 person / conf 0.94`。模型只见过直立人体，躺倒的头部特征对不上。

## 烧录推流固件（临时工具）

```bash
cp firmware/esp32_cam_stream/secrets.example.h firmware/esp32_cam_stream/secrets.h
# 编辑 secrets.h，填 2.4 GHz 的 SSID 和密码（不要带 _5G 后缀）

arduino-cli compile --fqbn "esp32:esp32:esp32cam" \
  --build-path /tmp/esp32cam-build --output-dir /tmp/esp32cam-out firmware/esp32_cam_stream
arduino-cli upload -p <COM口> --fqbn "esp32:esp32:esp32cam" \
  --input-dir /tmp/esp32cam-out firmware/esp32_cam_stream
```

需要 `esp32:esp32` core（`arduino-cli core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json`）。

固件对外接口：`/`（状态文本）、`/stream`（MJPEG）、`/jpg`（单张快照）。

## 实测记录

2026-11-06，Windows 11 26100 / RTX 5080 Laptop（sm_120）/ YOLOv8n / ESP32-CAM(VGA) / RSSI −43 dBm：

| 指标 | 结果 |
| --- | --- |
| 端到端帧率（采集 + 推理 + JPEG 编码） | **11 – 21 FPS** |
| YOLOv8n 单帧推理 | ~7 ms（预热后） |
| 检测效果 | 半身／头部稳定检出，置信度 0.94 |
| ESP32 单独推流能力 | ~16 FPS @ 640×480 |

瓶颈在 ESP32 推流带宽，不在推理。**尚未验证**：全身远距离场景、多人场景、动作判定准确率。

## 排查记录

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 扫不到板子、串口无输出 | 板子里跑的是本地自检固件，没有联网代码 | 重烧推流固件 |
| Wi-Fi 连一次就掉，`status=6` | RSSI −80 dBm，信号在临界线 | 板子靠近路由器（−43 dBm 后秒连） |
| pyserial 读不到任何字节 | 打开端口时 DTR 默认拉高，板子被顶进下载模式 | 显式 `setDTR(False)` + RTS 脉冲复位 |
| UI 显示 129 FPS 但画面卡 | 循环在反复推理**同一帧** | 用帧序号去重，只在新帧时推理 |
| 画面侧躺、检测 0 人 | 摄像头物理装歪 90° | `--rotate 270` |
| 局域网地址连不上 | 系统代理把 `192.168.x.x` 也转发了 | `urllib` 用 `ProxyHandler({})` 强制直连 |
| OpenCV 报 `no attribute HOGDescriptor` | 5.0 移除了 HOG 的 Python 绑定 | 固定 `opencv-python<5` |
| arduino 编译报 `cannot find -lcxx` | 工具链装在含中文的路径下 | 工具链与构建目录都放纯 ASCII 路径 |

## 已知限制

- **只判断「画面里有没有人」**，不能判断动作是否标准
- 弱光下噪点大，检测框会抖动
- ESP32 IP 由 DHCP 分配，路由器重启后可能变化
- 帧率受 ESP32 推流能力限制

## 下一步

1. 换 **YOLOv8n-pose**，输出 17 个关键点 → 计算膝角、躯干倾角 → 判定深蹲等动作姿势
2. 定义分析结果的数据结构，回传给 Main ESP → ESP32-CAM → Arduino Uno 驱动 LED／蜂鸣器
3. 与 IMU 数据融合（ESP32-S3 侧采集），需要与 Dong Yuankun 对齐通信格式
