[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="当前-cam--s3-集成固件"></a>

# 目前 CAM / S3 集成韌體

目前鏈路：**CAM USB 影像 → 電腦 AI → CAM USB 狀態 → ESP-NOW → S3 UART → Arduino**。影像不走無線。

<a id="文件入口"></a>

## 檔案入口

| 檔案 | 運行位置 | 職責 |
| --- | --- | --- |
| [Cam_USB_Bridge.ino](Cam_USB_Bridge/Cam_USB_Bridge.ino) | ESP32-CAM / OV2640 | 相機、USB 幀協議、電腦命令接收 |
| [S3_IMU_Alarm_Bridge.ino](S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino) | ESP32-S3 N16R8 | 複用 BMI160 採集，啓動獨立無線接收／UART 轉發任務 |
| [AlarmRadio.h](AlarmRadio.h) | 兩端共用 | 固定對端、20 位元組包、CRC／序號檢查、ACK、週期發送和超時 |

Arduino 韌體位於 [alarm-Arduino](../alarm-mega/README_zh_hk.md)。S3 相對包含 [BMI160_SixAxis](../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino)，編譯時保持倉庫目錄，避免複製單個草圖。

## 固定配置

- CAM USB：921600 8N1；640×480 JPEG、quality=18、雙 PSRAM 緩衝、LATEST；取幀時最大 first-DMA 幀齡 200ms。
- S3 USB：115200 8N1；BMI160 GPIO4 SDA、GPIO5 SCL，自動探測 0x68 / 0x69。
- ESP-NOW：信道 1、固定目前兩板 MAC、20 位元組命令／ACK、200ms 週期；CAM 電腦命令和 S3 無線接收均為 1.2 秒超時。
- UART：S3 GPIO17 TX → Arduino D19 RX1，9600 8N1；GND 共地；Arduino D18 TX 不接。
- Arduino：D8 LED、D9 無源蜂鳴器，同開同關；1.5 秒超時及電腦 USB 優先策略保留。

目前兩板各自 USB 供電，電源腳不互接；改線前斷電。換板後核對晶片、相機引腳、串列埠和固定對端 MAC，不沿用本機連接埠假設。

<a id="编译烧录"></a>

## 編譯／燒錄

先停止佔用串列埠的檢測程式，在倉庫根目錄執行；確認 COM3 為 CAM、COM4 為 S3 後才帶 `--upload`：

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32cam --upload --port COM3 firmware/usb-ai-bridge/Cam_USB_Bridge
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200 --upload --port COM4 firmware/usb-ai-bridge/S3_IMU_Alarm_Bridge
```

重刷會覆蓋目前韌體。舊獨立相機、UART、ESP-NOW 分片影像測試僅作為歷史基線，不與目前程式同時運行。

<a id="运行与验收"></a>

## 運行與驗收

電腦入口與環境：[app/README.md](../../app/README_zh_hk.md)。目前本機應用已用項目 `.venv` 驗證，無需為了本次整理重新安裝依賴。

- 純 USB：268 幀／30 秒，8.93 FPS，無 CRC／解碼錯誤。
- AI 頁面：預熱後約 9 FPS。取景會影響 JPEG 大小和速率，並非固定保證值。
- 無線開／關／命令過期通過；ACK 只確認到 S3。
- BMI160 目前無應答，用户將斷電檢查；包含 IMU 的整體併發驗收仍失敗。
- 新閉環的 Arduino 接收與現場聲光效果、真實完整動作準確性、物理斷線／掉電仍需驗收。

設計與證據：[系統架構](../../docs/architecture/README_zh_hk.md)、[USB 協議](../../docs/protocols/usb-camera_zh_hk.md)、[ESP-NOW 協議](../../docs/protocols/espnow-alarm_zh_hk.md)、[Arduino 協議](../../docs/protocols/alarm-control_zh_hk.md)、[測試記錄導航](../../docs/README_zh_hk.md)。
