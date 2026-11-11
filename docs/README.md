[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="文档导航"></a>

# Documentation guide

<a id="当前设计"></a>

## Current design

- [System architecture and code dependencies](architecture/README.md)
- [CAM USB image/control protocol](protocols/usb-camera.md)
- [CAM ↔ S3 ESP-NOW alarm protocol](protocols/espnow-alarm.md)
- [Arduino USB/UART alarm protocol](protocols/alarm-control.md)
- [Firmware guide and active entry points](../firmware/README.md)
- [PC setup, operation and tests](../app/README.md)

<a id="本轮验证记录"></a>

## Validation records for this iteration

| Record | Validation scope |
| --- | --- |
| [Alarm protocol](validation/2026-11-10-alarm-protocol.txt) | Arduino USB commands, rejection of bad checksum/source, ESP takeover after PC priority |
| [Camera baseline](validation/2026-11-10-camera-reproduction.json) | Historical 115200 USB single-photo capture/decoding |
| [Real-image AI](validation/2026-11-10-usb-ai-smoke.json) | USB image model input; no exercise-accuracy acceptance |
| [Wireless and IMU separately](validation/2026-11-10-usb-espnow-bridge.json) | Wireless state succeeded; IMU unresponsive; overall concurrent test failed |
| [Before optimization](validation/2026-11-10-camera-speed-before.json) | 460800 / single buffer / JPEG12, 3.53 FPS |
| [After optimization](validation/2026-11-10-camera-speed-after.json) | 921600 / double buffer / JPEG18, 8.93 FPS; 268 frames without CRC/decode errors |
| [High-speed control regression](validation/2026-11-10-camera-speed-control-check.json) | Wireless ON/OFF/command expiry passed during fast image transfer; IMU still failed |

These are real records from different stages. Preserve the settings and failures at the time; do not present historical firmware/low-speed data as the current deployment. Raw images remain only in local ignored directories.

<a id="历史资料"></a>

## Historical material

Experimental documentation and `evidence/` under `firmware/esp32-camera/` retain member contributions, older firmware and troubleshooting history. `experiments/` retains on-ESP32 inference experiments. Historical model tasks are in `models/`; the active runtime entry point is `app/pose_app.py`. `reference/` contains concepts, not physical wiring specifications.
