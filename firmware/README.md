# 固件入口

## 当前部署

| 板卡 | 草图 | 职责 |
| --- | --- | --- |
| ESP32-CAM / OV2640 | [Cam_USB_Bridge](usb-ai-bridge/Cam_USB_Bridge/Cam_USB_Bridge.ino) | USB 图像、USB 判定回传、ESP-NOW 小命令 |
| ESP32-S3 N16R8 | [S3_IMU_Alarm_Bridge](usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino) | IMU 采集初始化、无线接收、UART 转发 |
| Mega 2560 | [Mega_Alarm_RX](alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino) | 报警命令解析、LED／蜂鸣器控制 |

集成设计与烧录：[usb-ai-bridge](usb-ai-bridge/README.md)。Mega 协议与接线：[alarm-mega](alarm-mega/README.md)。IMU 导航与故障：[imu-s3](imu-s3/README.md)。

`usb-ai-bridge/AlarmRadio.h` 由 CAM 和 S3 共用；S3 还相对包含既有 BMI160 草图。保持完整仓库目录进行编译。

## 历史基线与证据

- `esp32-camera/`：原 USB 摄像头、ESP-NOW 文本／图像分片、IMU／网关实验及不可改写的历史测试证据；BMI160 采集实现目前仍被集成固件复用。
- `imu-s3/S3_UART_TX_Test/`：独立三秒开关 UART 测试；当前不烧录此程序。
- `arduino-uno/`：早期 Uno 任务说明；实际报警板目前是 Mega 2560。

同一块板一次只运行一个固件。历史草图替换烧录会覆盖当前集成程序。
