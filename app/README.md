# 电脑端视觉 AI

当前入口是 [pose_app.py](pose_app.py)：CAM USB 图像 → YOLOv8n-pose → 深蹲／俯卧撑几何规则 → 网页结果 → CAM USB 报警状态。图像不经过 ESP-NOW。

## 启动

本机已有 `app/.venv`。在仓库根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File app/run_pose.ps1 -CamPort COM3 -Action squat
```

或在本目录直接运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 pose_app.py --source serial://COM3 --action squat --no-browser
```

打开 [检测页面](http://127.0.0.1:8010)。俯卧撑使用 `pushup`；其他命令行参数见 `pose_app.py --help`。一个串口同时只允许一个检测／测试／烧录进程访问。USB 断开后需检查端口并重新启动，当前没有自动重连。

## 环境

当前本机环境基于已有 AI 包建立项目虚拟环境，隔离 pyserial 与全局同名 `serial` 包冲突：

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --ignore-installed pyserial==3.5
```

新电脑可创建独立虚拟环境并安装 `requirements.txt`。它是新安装依赖范围，不是当前旧环境的精确锁文件。当前实测 torch 1.12.1+cu116、ultralytics 8.3.141、RTX 4060 Laptop，模型加载／真实 USB 图像推理已通过。首次运行需要官方 `yolov8n-pose.pt` 权重；权重、虚拟环境、运行日志、抓帧均被 Git 忽略。

## 代码分工

| 文件 | 用途 |
| --- | --- |
| `pose_app.py` | 当前网页和推理主程序 |
| `pose_engine.py` | 17 点姿态估计 |
| `form_rules.py` | 角度、动作状态机、计次和规则扣分 |
| `sources.py` | 视频源选择；当前使用 `serial://COM3` |
| `serial_camera.py` | 串口独占读写、二进制图像校验、最新帧缓存、报警回传和性能指标 |
| `run_pose.ps1` | 本机启动脚本 |
| `app.py` / `detector.py` | 旧人体检测入口，保留为基线 |
| `find_camera.py` / `firmware/esp32_cam_stream/` | 旧 Wi-Fi MJPEG 路线；当前不使用 |

## 当前配置与反馈

- VGA 640×480、JPEG18、双缓冲 LATEST、USB 921600。保持当前约 9 FPS 的实测效果。
- 相机帧在采集时最多 200ms 旧；电脑仅处理新鲜最新帧。这个边界不是完整显示延迟。
- 动作手动选择，全身需入画。完成一次不合格动作时产生两秒报警事件；关键点不足时清除报警，持续丢失时清除未完成动作状态，累计完成次数保留。
- 原模型输出关键点，规则产生违规项和分数；分数不是模型置信度。真实动作准确率尚未验收。
- `/stats` 提供姿态结果、帧率、无线 ACK 和 `transport` 图像分阶段指标。

## 测试与测速

从本目录使用 `.venv/Scripts/python.exe`：

```powershell
.\.venv\Scripts\python.exe -X utf8 test_rules.py
.\.venv\Scripts\python.exe -X utf8 test_serial_camera.py
.\.venv\Scripts\python.exe -X utf8 check_usb_bridge.py --cam COM3 --s3 COM4
.\.venv\Scripts\python.exe -X utf8 benchmark_usb.py --baud 921600 --seconds 30 --out ../firmware/usb-ai-bridge/captures/speed.json
```

先停止正在运行的检测页面，再执行硬件脚本。`check_usb_bridge.py` 会短暂开启报警，并分开报告通信与 IMU；当前 IMU 无应答，所以整体并发验收失败，即使无线部分通过。测速不保存图像。

详细资料：[系统架构](../docs/architecture/README.md)、[动作规则说明](POSE.md)、[USB 协议](../docs/protocols/usb-camera.md)、[固件与编译](../firmware/usb-ai-bridge/README.md)。
