[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="imu-模块--esp32-s3-n16r8--bmi160"></a>

# IMU 模組 — ESP32-S3 N16R8 + BMI160

<a id="当前部署"></a>

## 目前部署

目前運行 [S3_IMU_Alarm_Bridge](../usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino)。它初始化既有 BMI160 六軸採集實現，同時用獨立任務接收 CAM 的 ESP-NOW 報警狀態，並向 Mega 轉發 UART 命令。IMU 與視覺結果不做融合，尚無 IMU 自動報警判斷。

- BMI160：SDA=GPIO4，SCL=GPIO5，I²C 自動探測 0x68 / 0x69。
- S3 → Mega：GPIO17 TX → D19 RX1，GND 共地；GPIO18 和 Mega TX 不接。
- USB：115200，輸出採集 CSV 與以 `#` 開頭的診斷。
- **目前故障**：兩個地址均無應答；用户已確認仍接着 IMU，將斷電檢查。無線報警任務獨立運行。

<a id="保留的源码入口"></a>

## 保留的源碼入口

| 實現 | 用途 |
| --- | --- |
| [BMI160_SixAxis](../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) | 採集單一源碼，被目前 S3 集成韌體複用，也可單獨燒錄 |
| [BMI160_Bus_Check](../esp32-camera/BMI160_Bus_Check/BMI160_Bus_Check.ino) | 獨立總線診斷 |
| [S3_UART_TX_Test](S3_UART_TX_Test/S3_UART_TX_Test.ino) | 歷史三秒開關測試，不讀取 IMU |

[歷史成功復現](../esp32-camera/YANCHENG_BMI160_REPRO.md)曾驗證本機 0x69，不代表目前接線已恢復。保留原路徑以保護腳本和證據引用。

詳細説明：[目前集成韌體](../usb-ai-bridge/README_zh_hk.md)、[系統架構](../../docs/architecture/README_zh_hk.md)、[Mega 介面](../../docs/protocols/alarm-control_zh_hk.md)。
