[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="固件入口"></a>

# Firmware entry points

<a id="当前部署"></a>

## Active deployment

| Board | Sketch | Responsibility |
| --- | --- | --- |
| ESP32-CAM / OV2640 | [Cam_USB_Bridge](usb-ai-bridge/Cam_USB_Bridge/Cam_USB_Bridge.ino) | USB images, USB decision return, small ESP-NOW commands |
| ESP32-S3 N16R8 | [S3_IMU_Alarm_Bridge](usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino) | Initialize IMU acquisition, receive wireless states, relay UART |
| Arduino | [Mega_Alarm_RX](alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino) | Parse alarm commands; control LED/buzzer |

Integration design and upload: [usb-ai-bridge](usb-ai-bridge/README.md). Arduino protocol/wiring: [alarm-Arduino](alarm-mega/README.md). IMU navigation/faults: [imu-s3](imu-s3/README.md).

CAM and S3 share `usb-ai-bridge/AlarmRadio.h`. S3 also includes the existing BMI160 sketch through a relative path. Compile with the complete repository layout.

<a id="历史基线与证据"></a>

## Historical baselines and evidence

- `esp32-camera/`: original USB camera, ESP-NOW text/fragmented images, IMU/gateway experiments and immutable historical evidence. Integrated firmware still reuses its BMI160 acquisition implementation.
- `imu-s3/S3_UART_TX_Test/`: independent three-second UART ON/OFF test; not the currently flashed program.
- `arduino-uno/`: Arduino LED and buzzer control instructions.

A board runs only one firmware at a time. Uploading a historical sketch replaces the active integrated program.
