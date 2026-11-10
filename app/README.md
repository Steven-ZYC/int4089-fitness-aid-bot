> Current entry point: [Unified PC application](UNIFIED_APP.md), combining vision and IMU in one page. The standalone pose_app.py remains available.

[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="电脑端视觉-ai"></a>

# PC vision AI

The current entry point is [pose_app.py](pose_app.py): CAM USB images → YOLOv8n-pose → squat/pushup geometric rules → web results → CAM USB alarm state. Images do not use ESP-NOW.

<a id="启动"></a>

## Start

This PC already has `app/.venv`. Run from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File app/run_pose.ps1 -CamPort COM3 -Action squat
```

Or run directly from this directory:

```powershell
.\.venv\Scripts\python.exe -X utf8 pose_app.py --source serial://COM3 --action squat --no-browser
```

Open the [detection page](http://127.0.0.1:8010). Use `pushup` for pushups; see `pose_app.py --help` for other options. Only one detection/test/upload process may access a serial port at a time. After USB disconnection, check the port and restart; automatic reconnection is not implemented.

<a id="环境"></a>

## Environment

The current local project environment reuses installed AI packages and isolates pyserial from a conflicting global package named `serial`:

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --ignore-installed pyserial==3.5
```

On a new PC, create an isolated virtual environment and install `requirements.txt`. This declares fresh-install dependency ranges, not an exact lockfile for the current legacy environment. The tested environment has torch 1.12.1+cu116, ultralytics 8.3.141 and an RTX 4060 Laptop GPU. Model loading and real USB-frame inference passed. First use requires the official `yolov8n-pose.pt` weights. Weights, virtual environments, logs and captured frames are ignored by Git.

<a id="代码分工"></a>

## File responsibilities

| File | Purpose |
| --- | --- |
| `pose_app.py` | Current web application and inference entry point |
| `pose_engine.py` | 17-keypoint pose estimation |
| `form_rules.py` | Angles, action state machine, repetition counting and rule penalties |
| `sources.py` | Video source selection; currently `serial://COM3` |
| `serial_camera.py` | Exclusive serial I/O, binary image verification, latest-frame cache, alarm return path and performance metrics |
| `run_pose.ps1` | Local launcher |
| `app.py` / `detector.py` | Earlier person-detection entry point, retained as a baseline |
| `find_camera.py` / `firmware/esp32_cam_stream/` | Earlier Wi-Fi MJPEG route; not currently used |

<a id="当前配置与反馈"></a>

## Current configuration and feedback

- VGA 640×480, JPEG18, two LATEST buffers, USB 921600. Keep the current measured result of about 9 FPS.
- Frames may be at most 200ms old at acquisition; the PC processes only fresh latest frames. This is not the complete display latency bound.
- Select the action manually and keep the whole body visible. An invalid completed repetition causes a two-second alarm. Missing required keypoints clear the alarm; sustained loss resets incomplete action state while preserving the completed repetition count.
- The model produces keypoints; rules produce violations and scores. Scores are not model confidence. Real exercise accuracy has not been accepted.
- `/stats` exposes pose results, FPS, wireless ACKs and image-stage timings under `transport`.

<a id="测试与测速"></a>

## Tests and benchmarks

Use `.venv/Scripts/python.exe` from this directory:

```powershell
.\.venv\Scripts\python.exe -X utf8 test_rules.py
.\.venv\Scripts\python.exe -X utf8 test_serial_camera.py
.\.venv\Scripts\python.exe -X utf8 check_usb_bridge.py --cam COM3 --s3 COM4
.\.venv\Scripts\python.exe -X utf8 benchmark_usb.py --baud 921600 --seconds 30 --out ../firmware/usb-ai-bridge/captures/speed.json
```

Stop the running detection page before hardware scripts. `check_usb_bridge.py` briefly enables the alarm and reports communication and IMU separately. The IMU currently does not respond, so overall concurrent acceptance fails even when the wireless portion passes. Benchmarks do not save images.

Details: [system architecture](../docs/architecture/README.md), [action rules](POSE.md), [USB protocol](../docs/protocols/usb-camera.md), [firmware and builds](../firmware/usb-ai-bridge/README.md).
