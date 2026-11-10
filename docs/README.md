# 文档导航

## 当前设计

- [系统架构与代码依赖](architecture/README.md)
- [CAM USB 图像／控制协议](protocols/usb-camera.md)
- [CAM ↔ S3 ESP-NOW 报警协议](protocols/espnow-alarm.md)
- [Mega USB／UART 报警协议](protocols/alarm-control.md)
- [固件导航与当前入口](../firmware/README.md)
- [电脑端运行与测试](../app/README.md)

## 本轮验证记录

| 记录 | 验证内容 |
| --- | --- |
| [报警协议](validation/2026-11-10-alarm-protocol.txt) | Mega USB 命令、校验／来源拒绝、电脑优先后 ESP 接管 |
| [摄像头基线](validation/2026-11-10-camera-reproduction.json) | 历史 115200 USB 单张拍照／解码 |
| [真实图像 AI](validation/2026-11-10-usb-ai-smoke.json) | USB 图像输入模型，未进行动作准确性验收 |
| [无线与 IMU 分项](validation/2026-11-10-usb-espnow-bridge.json) | 无线状态成功，IMU 无应答；整体并发测试失败 |
| [加速前](validation/2026-11-10-camera-speed-before.json) | 460800／单缓冲／JPEG12，3.53 FPS |
| [加速后](validation/2026-11-10-camera-speed-after.json) | 921600／双缓冲／JPEG18，8.93 FPS，268 帧无 CRC／解码错误 |
| [高速下控制回归](validation/2026-11-10-camera-speed-control-check.json) | 高速图像下无线开、关、命令过期成功；IMU 仍失败 |

这些是不同阶段的真实记录，保留当时参数和失败项，不把历史固件／低速数据写成当前部署。原始图像只保留在本地忽略目录。

## 历史资料

`firmware/esp32-camera/` 的实验说明及 `evidence/` 保留同学贡献、旧固件和故障排查过程；`experiments/` 保留 ESP32 板端推理实验。历史模型任务在 `models/`，当前运行入口是 `app/pose_app.py`。`reference/` 为概念参考，不是实物接线依据。
