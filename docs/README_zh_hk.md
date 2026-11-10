[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="文档导航"></a>

# 文檔導航

<a id="当前设计"></a>

## 目前設計

- [系統架構與程式碼依賴](architecture/README_zh_hk.md)
- [CAM USB 影像／控制協議](protocols/usb-camera_zh_hk.md)
- [CAM ↔ S3 ESP-NOW 報警協議](protocols/espnow-alarm_zh_hk.md)
- [Mega USB／UART 報警協議](protocols/alarm-control_zh_hk.md)
- [韌體導航與目前入口](../firmware/README_zh_hk.md)
- [電腦端運行與測試](../app/README_zh_hk.md)

<a id="本轮验证记录"></a>

## 本輪驗證記錄

| 記錄 | 驗證內容 |
| --- | --- |
| [報警協議](validation/2026-11-10-alarm-protocol.txt) | Mega USB 命令、校驗／來源拒絕、電腦優先後 ESP 接管 |
| [攝影機基線](validation/2026-11-10-camera-reproduction.json) | 歷史 115200 USB 單張拍照／解碼 |
| [真實影像 AI](validation/2026-11-10-usb-ai-smoke.json) | USB 影像輸入模型，未進行動作準確性驗收 |
| [無線與 IMU 分項](validation/2026-11-10-usb-espnow-bridge.json) | 無線狀態成功，IMU 無應答；整體併發測試失敗 |
| [加速前](validation/2026-11-10-camera-speed-before.json) | 460800／單緩衝／JPEG12，3.53 FPS |
| [加速後](validation/2026-11-10-camera-speed-after.json) | 921600／雙緩衝／JPEG18，8.93 FPS，268 幀無 CRC／解碼錯誤 |
| [高速下控制迴歸](validation/2026-11-10-camera-speed-control-check.json) | 高速影像下無線開、關、命令過期成功；IMU 仍失敗 |

這些是不同階段的真實記錄，保留當時參數和失敗項，不把歷史韌體／低速數據寫成目前部署。原始影像只保留在本地忽略目錄。

<a id="历史资料"></a>

## 歷史資料

`firmware/esp32-camera/` 的實驗説明及 `evidence/` 保留同學貢獻、舊韌體和故障排查過程；`experiments/` 保留 ESP32 板端推理實驗。歷史模型任務在 `models/`，目前運行入口是 `app/pose_app.py`。`reference/` 為概念參考，不是實物接線依據。
