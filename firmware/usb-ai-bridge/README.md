[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="当前-cam--s3-集成固件"></a>

# Current integrated CAM / S3 firmware

Active route: **CAM USB images → PC AI → CAM USB state → ESP-NOW → S3 UART → Arduino**. Images do not travel wirelessly.

<a id="文件入口"></a>

## File entry points

| File | Runs on | Responsibility |
| --- | --- | --- |
| [Cam_USB_Bridge.ino](Cam_USB_Bridge/Cam_USB_Bridge.ino) | ESP32-CAM / OV2640 | Camera, USB frame protocol, PC command reception |
| [S3_IMU_Alarm_Bridge.ino](S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino) | ESP32-S3 N16R8 | Reuse BMI160 acquisition and start independent wireless reception/UART relay task |
| [AlarmRadio.h](AlarmRadio.h) | Shared by both | Fixed peer, 20-byte packets, CRC/sequence checks, ACKs, periodic sending and timeouts |

Arduino firmware is under [alarm-Arduino](../alarm-mega/README.md). S3 includes [BMI160_SixAxis](../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) through a relative path. Preserve the repository layout for builds rather than copying a sketch alone.

<a id="固定配置"></a>

## Fixed configuration

- CAM USB: 921600 8N1; 640×480 JPEG, quality=18, two PSRAM buffers, LATEST; maximum first-DMA frame age of 200ms at acquisition.
- S3 USB: 115200 8N1; BMI160 GPIO4 SDA, GPIO5 SCL; automatic 0x68/0x69 detection.
- ESP-NOW: channel 1, fixed MACs for the current boards, 20-byte command/ACK, 200ms interval. CAM PC commands and S3 wireless reception each expire after 1.2 seconds.
- UART: S3 GPIO17 TX → Arduino D19 RX1, 9600 8N1; common GND; Arduino D18 TX disconnected.
- Arduino: D8 LED and D9 passive buzzer switch together; retain 1.5-second timeout and PC USB priority.

Each board is USB-powered independently; do not interconnect supply pins. Power off before rewiring. After board replacement, verify chip, camera pins, serial ports and fixed peer MACs rather than reusing local port assumptions.

<a id="编译烧录"></a>

## Build/upload

Stop the detection program occupying serial ports first. Run from the repository root and add `--upload` only after confirming COM3 is CAM and COM4 is S3:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32cam --upload --port COM3 firmware/usb-ai-bridge/Cam_USB_Bridge
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200 --upload --port COM4 firmware/usb-ai-bridge/S3_IMU_Alarm_Bridge
```

Reflashing replaces current firmware. Earlier standalone camera/UART/fragmented ESP-NOW image tests are historical baselines and do not run alongside the current program.

<a id="运行与验收"></a>

## Operation and acceptance

PC entry/environment: [app/README.md](../../app/README.md). The local application has already been verified in the project `.venv`; this organization task does not require reinstalling dependencies.

- USB alone: 268 frames/30 seconds, 8.93 FPS, no CRC/decode errors.
- AI page: about 9 FPS after warm-up. Scene content affects JPEG size and rate; this is not a fixed guarantee.
- Wireless ON/OFF/command expiry passed. ACK confirms receipt at S3 only.
- BMI160 currently does not respond; the user will inspect with power off. Overall concurrent acceptance including IMU still fails.
- Pending: Arduino reception and physical light/sound in the new loop, complete real exercise accuracy, physical disconnection/power loss.

Design and evidence: [architecture](../../docs/architecture/README.md), [USB](../../docs/protocols/usb-camera.md), [ESP-NOW](../../docs/protocols/espnow-alarm.md), [Arduino](../../docs/protocols/alarm-control.md), [test record guide](../../docs/README.md).
