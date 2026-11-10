[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="系统架构与代码导航"></a>

# 系統架構與程式碼導航

<a id="三个逻辑模块"></a>

## 三個邏輯模組

| 模組 | 輸入 | 輸出 | 程式碼入口 |
| --- | --- | --- | --- |
| 視覺 AI | CAM 的 USB JPEG 影像 | 關鍵點、動作階段、計次、違規項、報警狀態 | [pose_app.py](../../app/pose_app.py)、[pose_engine.py](../../app/pose_engine.py)、[form_rules.py](../../app/form_rules.py) |
| IMU | BMI160 六軸數據；無線接收視覺報警狀態 | USB IMU CSV；發往 Mega 的報警幀 | [S3 集成韌體](../../firmware/usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino)、[BMI160 採集實現](../../firmware/esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) |
| 物理警報 | S3 UART 或電腦直連 USB 的報警幀 | D8 LED、D9 蜂鳴器同開同關 | [Mega 韌體](../../firmware/alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino) |

S3 同時承擔 IMU 採集節點和無線報警轉發節點，但兩項任務獨立。目前無線結果不是 IMU 判定結果；尚未實現 IMU 與視覺融合或 IMU 自動報警。

<a id="电脑端文件职责"></a>

## 電腦端檔案職責

| 檔案 | 職責 |
| --- | --- |
| `app/pose_app.py` | 目前應用入口；推理執行緒、結果狀態、網頁與 HTTP 服務；不合格完整動作觸發短時報警 |
| `app/pose_engine.py` | YOLOv8n-pose 模型，取最大人體框和 17 個關鍵點 |
| `app/form_rules.py` | 深蹲／掌上壓角度、階段狀態機、計次和違規規則 |
| `app/sources.py` | 選擇 `serial://`、本地攝影機或 HTTP MJPEG 輸入 |
| `app/serial_camera.py` | USB 串列埠的唯一讀寫者；接收 JPEG、校驗 CRC／幀尾、緩存最新幀、回傳報警和讀取無線確認 |
| `app/run_pose.ps1` | 本機固定環境的啓動入口；參數選擇串列埠、動作和網頁連接埠 |
| `app/test_rules.py` | 原動作規則合成關鍵點測試 |
| `app/test_serial_camera.py` | 合成 JPEG 的正常、損壞 CRC、錯誤幀尾測試 |
| `app/check_usb_bridge.py` | 真實雙板硬件測試；短暫開啓報警，分別記錄無線與 IMU 結果 |
| `app/benchmark_usb.py` | 影像傳輸分階段測速，只保存指標 |
| `app/app.py`、`detector.py` | 舊人體檢測頁面；不是目前動作規範判定主入口 |
| `app/find_camera.py`、`app/firmware/esp32_cam_stream/` | 歷史 Wi-Fi MJPEG 路線，目前不使用 |

電腦內只有 `SerialCameraSource` 工作執行緒訪問 CAM 串列埠。它批量發送報警／狀態／拍照請求，按長度讀取二進制影像並校驗後緩存最新幀。推理執行緒只讀取新鮮幀並回寫短期有效的報警狀態；HTTP 執行緒讀取結果緩存供網頁顯示。模型權重和抓幀不提交。

<a id="固件依赖与运行任务"></a>

## 韌體依賴與運行任務

```text
Cam_USB_Bridge.ino
  ├─ OV2640 相機：VGA / JPEG18 / 雙緩衝 LATEST
  ├─ USB：影像、電腦命令和診斷
  └─ AlarmRadio.h：獨立任務週期發送狀態並處理 S3 確認

S3_IMU_Alarm_Bridge.ino
  ├─ 引入既有 BMI160_SixAxis.ino：初始化及六軸採集
  └─ AlarmRadio.h：獨立任務接收狀態、確認並週期寫入 Serial1

Mega_Alarm_RX.ino
  ├─ USB / Serial1 各自解析三位命令
  └─ 來源／XOR 檢查、電腦優先期、輸出控制與超時
```

BMI160 源碼仍保留在 `firmware/esp32-camera/`，S3 集成韌體通過相對包含複用，避免出現兩份採集實現。保留原路徑也確保歷史 PowerShell 腳本和證據可追溯。編譯時應保留倉庫相對目錄；不能只複製一個 `.ino` 去編譯。

<a id="接口边界"></a>

## 介面邊界

1. **CAM ↔ 電腦 USB**：921600 8N1，JPEG 與文本命令共用同一串列埠。影像不走無線。[USB 影像協議](../protocols/usb-camera_zh_hk.md)
2. **CAM ↔ S3 ESP-NOW**：信道 1，固定對端 MAC，20 位元組狀態／確認包；不傳影像。[無線報警協議](../protocols/espnow-alarm_zh_hk.md)
3. **S3 → Mega UART**：9600 8N1，GPIO17 TX → D19 RX1，GND 共地，反向 TX 不接。[Mega 報警協議](../protocols/alarm-control_zh_hk.md)
4. **BMI160 → S3 I²C**：GPIO4 SDA、GPIO5 SCL，自動探測 0x68 / 0x69；目前無應答，待接線檢查。

協議幀隔離了視覺分析與執行器。無線確認到 S3 為止，不能證明 Mega 接收到命令或燈／蜂鳴器執行成功。端到端確認尚未實現。

<a id="当前参数与验证"></a>

## 目前參數與驗證

目前固定為 VGA、JPEG18、雙緩衝、921600；本輪整理不修改這些參數。影像採集時接受最多 200ms 幀齡，USB／推理／顯示還會增加延遲。命令新鮮度與超時見各協議文檔。

- USB 加速後：268 幀／30 秒，8.93 FPS，未見 CRC／解碼錯誤。
- AI 頁面：約 9 FPS，隨光照和畫面複雜度變化；不是動作準確率指標。
- 無線：開／關／電腦命令過期測試通過。
- IMU：目前 0x68 / 0x69 均無應答；併發 IMU 驗收仍失敗。
- 現場待驗收：真實完整動作、Mega 執行效果、物理斷線／掉電。

記錄入口：[文檔索引](../README_zh_hk.md)。歷史單板與分片影像實驗放在 `firmware/esp32-camera/`；獨立 UI 工作樹尚未合入目前頁面。
