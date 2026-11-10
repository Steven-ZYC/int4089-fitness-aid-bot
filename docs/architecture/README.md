> Current UI integration: [Unified PC application](../../app/UNIFIED_APP.md). app/main.py reuses the existing vision pipeline and IMU core in one service; original snapshot diagrams remain historical references.

[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="系统架构与代码导航"></a>

# System architecture and code guide

<a id="三个逻辑模块"></a>

## Three logical modules

| Module | Inputs | Outputs | Code entry points |
| --- | --- | --- | --- |
| Vision AI | CAM USB JPEG images | Keypoints, action phase, repetitions, violations, alarm state | [pose_app.py](../../app/pose_app.py), [pose_engine.py](../../app/pose_engine.py), [form_rules.py](../../app/form_rules.py) |
| IMU | BMI160 six-axis data; wireless vision alarm states | USB IMU CSV; alarm frames to Mega | [Integrated S3 firmware](../../firmware/usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino), [BMI160 acquisition](../../firmware/esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) |
| Physical alarm | S3 UART or direct PC USB alarm frames | D8 LED and D9 buzzer switching together | [Mega firmware](../../firmware/alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino) |

S3 is both the IMU acquisition node and the wireless alarm relay, but these tasks are independent. Current wireless results are not IMU decisions. IMU/vision fusion and automatic IMU alarms are not implemented.

<a id="电脑端文件职责"></a>

## PC file responsibilities

| File | Responsibility |
| --- | --- |
| `app/pose_app.py` | Current application entry; inference thread, result state, web page and HTTP server; short alarm after an invalid completed repetition |
| `app/pose_engine.py` | YOLOv8n-pose; select the largest person box and 17 keypoints |
| `app/form_rules.py` | Squat/pushup angles, phase state machine, repetition counting and violation rules |
| `app/sources.py` | Select `serial://`, local camera or HTTP MJPEG input |
| `app/serial_camera.py` | Sole CAM USB serial owner; receive JPEG, check CRC/trailer, cache latest frame, return alarms and read wireless acknowledgements |
| `app/run_pose.ps1` | Launcher for the fixed local environment; choose serial port, action and web port |
| `app/test_rules.py` | Original synthetic-keypoint action-rule tests |
| `app/test_serial_camera.py` | Synthetic JPEG tests for normal input, damaged CRC and incorrect trailer |
| `app/check_usb_bridge.py` | Real dual-board test; briefly enable alarm and record wireless/IMU outcomes separately |
| `app/benchmark_usb.py` | Stage-level image transport benchmark; save metrics only |
| `app/app.py`, `detector.py` | Earlier person-detection page, not the current exercise-form entry point |
| `app/find_camera.py`, `app/firmware/esp32_cam_stream/` | Historical Wi-Fi MJPEG route, not currently used |

Only the `SerialCameraSource` worker accesses the CAM serial port. It batches alarm/status/capture requests, reads binary images by length, verifies them and caches the latest frame. The inference thread reads fresh frames and returns short-lived alarm states. HTTP threads read the result cache for display. Model weights and captured frames are not committed.

<a id="固件依赖与运行任务"></a>

## Firmware dependencies and runtime tasks

```text
Cam_USB_Bridge.ino
  |-- OV2640 camera: VGA / JPEG18 / double-buffer LATEST
  |-- USB: images, PC commands and diagnostics
  `-- AlarmRadio.h: independent periodic state sending and S3 ACK handling

S3_IMU_Alarm_Bridge.ino
  |-- Existing BMI160_SixAxis.ino: initialization and six-axis acquisition
  `-- AlarmRadio.h: independent state reception, ACKs and periodic Serial1 output

Mega_Alarm_RX.ino
  |-- USB / Serial1 independently parse three-digit commands
  `-- Source/XOR checks, PC priority, output control and timeout
```

BMI160 source remains under `firmware/esp32-camera/`. The integrated S3 firmware reuses it through a relative include, avoiding two acquisition implementations. Keeping the original path preserves historical PowerShell scripts and evidence references. Preserve the relative repository layout when compiling; copying only one `.ino` is insufficient.

<a id="接口边界"></a>

## Interface boundaries

1. **CAM ↔ PC USB**: 921600 8N1; JPEG and text commands share one serial port. Images do not use wireless. [USB image protocol](../protocols/usb-camera.md)
2. **CAM ↔ S3 ESP-NOW**: channel 1, fixed peer MACs, 20-byte state/ACK packets; no images. [Wireless alarm protocol](../protocols/espnow-alarm.md)
3. **S3 → Mega UART**: 9600 8N1, GPIO17 TX → D19 RX1, common GND, no reverse TX connection. [Mega alarm protocol](../protocols/alarm-control.md)
4. **BMI160 → S3 I²C**: GPIO4 SDA, GPIO5 SCL, automatic 0x68/0x69 detection; currently no response, pending wiring inspection.

Protocol frames separate vision analysis from actuation. Wireless confirmation ends at S3 and does not prove that Mega received a command or the LED/buzzer acted. End-to-end acknowledgement is not implemented.

<a id="当前参数与验证"></a>

## Current settings and validation

Settings remain VGA, JPEG18, double buffering and 921600; this organization pass does not change them. Acquisition accepts frames at most 200ms old. USB/inference/display add latency. See individual protocols for command freshness and timeouts.

- Optimized USB: 268 frames/30 seconds, 8.93 FPS, no observed CRC/decode errors.
- AI page: about 9 FPS, varying with lighting and scene complexity; not an exercise-accuracy metric.
- Wireless: ON/OFF/PC-command-expiry tests passed.
- IMU: neither 0x68 nor 0x69 responds; concurrent IMU acceptance still fails.
- On-site acceptance pending: complete real exercises, Mega output effects, physical disconnection/power loss.

Records: [documentation index](../README.md). Historical single-board and fragmented-image experiments remain under `firmware/esp32-camera/`. The separate UI worktree is not merged into the current page.
