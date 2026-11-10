[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="固件入口"></a>

# 韌體入口

<a id="当前部署"></a>

## 目前部署

| 板卡 | 草圖 | 職責 |
| --- | --- | --- |
| ESP32-CAM / OV2640 | [Cam_USB_Bridge](usb-ai-bridge/Cam_USB_Bridge/Cam_USB_Bridge.ino) | USB 影像、USB 判定回傳、ESP-NOW 小命令 |
| ESP32-S3 N16R8 | [S3_IMU_Alarm_Bridge](usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino) | IMU 採集初始化、無線接收、UART 轉發 |
| Mega 2560 | [Mega_Alarm_RX](alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino) | 報警命令解析、LED／蜂鳴器控制 |

集成設計與燒錄：[usb-ai-bridge](usb-ai-bridge/README_zh_hk.md)。Mega 協議與接線：[alarm-mega](alarm-mega/README_zh_hk.md)。IMU 導航與故障：[imu-s3](imu-s3/README_zh_hk.md)。

`usb-ai-bridge/AlarmRadio.h` 由 CAM 和 S3 共用；S3 還相對包含既有 BMI160 草圖。保持完整倉庫目錄進行編譯。

<a id="历史基线与证据"></a>

## 歷史基線與證據

- `esp32-camera/`：原 USB 攝影機、ESP-NOW 文本／影像分片、IMU／網關實驗及不可改寫的歷史測試證據；BMI160 採集實現目前仍被集成韌體複用。
- `imu-s3/S3_UART_TX_Test/`：獨立三秒開關 UART 測試；目前不燒錄此程式。
- `arduino-uno/`：早期 Uno 任務説明；實際報警板目前是 Mega 2560。

同一塊板一次只運行一個韌體。歷史草圖替換燒錄會覆蓋目前集成程式。
