# 当前 CAM / S3 集成固件

当前链路：**CAM USB 图像 → 电脑 AI → CAM USB 状态 → ESP-NOW → S3 UART → Mega**。图像不走无线。

## 文件入口

| 文件 | 运行位置 | 职责 |
| --- | --- | --- |
| [Cam_USB_Bridge.ino](Cam_USB_Bridge/Cam_USB_Bridge.ino) | ESP32-CAM / OV2640 | 相机、USB 帧协议、电脑命令接收 |
| [S3_IMU_Alarm_Bridge.ino](S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino) | ESP32-S3 N16R8 | 复用 BMI160 采集，启动独立无线接收／UART 转发任务 |
| [AlarmRadio.h](AlarmRadio.h) | 两端共用 | 固定对端、20 字节包、CRC／序号检查、ACK、周期发送和超时 |

Mega 固件位于 [alarm-mega](../alarm-mega/README.md)。S3 相对包含 [BMI160_SixAxis](../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino)，编译时保持仓库目录，避免复制单个草图。

## 固定配置

- CAM USB：921600 8N1；640×480 JPEG、quality=18、双 PSRAM 缓冲、LATEST；取帧时最大 first-DMA 帧龄 200ms。
- S3 USB：115200 8N1；BMI160 GPIO4 SDA、GPIO5 SCL，自动探测 0x68 / 0x69。
- ESP-NOW：信道 1、固定当前两板 MAC、20 字节命令／ACK、200ms 周期；CAM 电脑命令和 S3 无线接收均为 1.2 秒超时。
- UART：S3 GPIO17 TX → Mega D19 RX1，9600 8N1；GND 共地；Mega D18 TX 不接。
- Mega：D8 LED、D9 无源蜂鸣器，同开同关；1.5 秒超时及电脑 USB 优先策略保留。

当前两板各自 USB 供电，电源脚不互接；改线前断电。换板后核对芯片、相机引脚、串口和固定对端 MAC，不沿用本机端口假设。

## 编译／烧录

先停止占用串口的检测程序，在仓库根目录执行；确认 COM3 为 CAM、COM4 为 S3 后才带 `--upload`：

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32cam --upload --port COM3 firmware/usb-ai-bridge/Cam_USB_Bridge
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200 --upload --port COM4 firmware/usb-ai-bridge/S3_IMU_Alarm_Bridge
```

重刷会覆盖当前固件。旧独立相机、UART、ESP-NOW 分片图像测试仅作为历史基线，不与当前程序同时运行。

## 运行与验收

电脑入口与环境：[app/README.md](../../app/README.md)。当前本机应用已用项目 `.venv` 验证，无需为了本次整理重新安装依赖。

- 纯 USB：268 帧／30 秒，8.93 FPS，无 CRC／解码错误。
- AI 页面：预热后约 9 FPS。取景会影响 JPEG 大小和速率，并非固定保证值。
- 无线开／关／命令过期通过；ACK 只确认到 S3。
- BMI160 当前无应答，用户将断电检查；包含 IMU 的整体并发验收仍失败。
- 新闭环的 Mega 接收与现场声光效果、真实完整动作准确性、物理断线／掉电仍需验收。

设计与证据：[系统架构](../../docs/architecture/README.md)、[USB 协议](../../docs/protocols/usb-camera.md)、[ESP-NOW 协议](../../docs/protocols/espnow-alarm.md)、[Mega 协议](../../docs/protocols/alarm-control.md)、[测试记录导航](../../docs/README.md)。
