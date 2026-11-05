# 第 4 步之一：ESP32-CAM 重連與新畫面自檢

身份：Dong Yuankun。分支：`Feat-Esp-Yuankun`。更新日期：2026-11-03。

本步先驗證「相機 → USB → 電腦」的單張 JPEG。第 4 步還包含 CAM ↔ S3 圖像和反向訊息，須另外實測才可整步標完成。總進度見 [PROGRESS.md](PROGRESS.md)，當次硬件結果見 [重測記錄](CAM_RECHECK_RESULT.md)。

## 你正在做甚麼

相機把光線轉成圖片，CAM 把圖片存成 JPEG，電腦發出 `CAPTURE` 命令後接收它。JPEG 是壓縮圖片格式；640×480 表示橫向 640、縱向 480 個像素。檔案的位元組數會隨畫面內容改變。

USB 底座在此提供電源和串口連接。COM 是 Windows 給串口的編號，重插後可能改變；本輪相機曾在 COM11，不能用這個名稱推斷其他裝置身份。先辨認相機，再上傳程式。

## 為甚麼另做一個自檢版本

10-23 的 [原始 USB 演示](USB_CAMERA_DEMO.md) 和 `ESP32CAM_USB_Capture` 保留作歷史基線。新程式 [ESP32CAM_USB_Check](ESP32CAM_USB_Check/ESP32CAM_USB_Check.ino) 另外提供：

- `INFO`：固件版本、晶片、Flash／PSRAM 容量和相機 PID／版本讀值。
- `META`：命令時間、畫面首個 DMA 緩衝時間、取得時間、序號及圖片大小。
- 新畫面門檻：釋放早於命令的畫面，最多嘗試 4 次；只接受 `frame_us >= request_us` 的畫面，否則報錯。
- `DONE`：本次序號、已寫入長度和相機端串口發送耗時。

官方 [camera_grab_mode_t 說明](https://github.com/espressif/esp32-camera/blob/master/driver/include/esp_camera.h) 指出 `WHEN_EMPTY` 的首批畫面可能較舊；單一緩衝也不能單靠 `LATEST` 名稱保證最新畫面。新程式明確保留單緩衝模式並檢查本地時間，而不是只改一個模式名稱。

`frame_us` 是驅動標示的首個 DMA 緩衝時間，**不是精密曝光／快門時間**。它和 `request_us` 同屬 CAM 開機後的本地時鐘；不能直接與 S3 或電腦時間相減。校時仍屬後續整合工作。取幀的 2 秒預算加上驅動本身可能阻塞的等待，不是硬即時期限。

## 操作順序

1. 相機保持原有排線及 USB 底座接法；鏡頭對準明亮、有文字或紋理的桌上物件。
2. 開發板選 **AI Thinker ESP32-CAM**，相機使用本輪已核實的端口。S3 的 IMU 程式是另一個草圖。
3. 新自檢版本採用 240 MHz、DIO、40 MHz Flash、Huge APP 分區、4 MB Flash 板卡設定，上傳時用 115200。完整 FQBN 及實際編譯／上傳結果見重測記錄。
4. 開啟 [ESP32CAM_USB_Check.ino](ESP32CAM_USB_Check/ESP32CAM_USB_Check.ino) 編譯上傳；成功啟動後會回覆 `CAMERA_OK`、`INFO` 和週期性的 `READY`。
5. 關閉 Arduino 串口監視器；在倉庫根目錄執行下面接收工具，端口須按實際裝置修改。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\esp32-camera\receive_esp32cam_check.ps1 -Port COM11
```

每次接收會產生 JPG、JSON 統計及文字日誌，預設在 Git 忽略的 `captures/cam-check/`。可加 `-OutputDirectory` 指定其他本機資料夾。拍攝人像只作本機測試時，原始照片留在本機接收目錄，按 [AGENTS.md](../../AGENTS.md) 的資料規則處理。

## 甚麼算通過

[接收工具](receive_esp32cam_check.ps1) 逐項核對固件版本、時間順序、META／IMG／DONE 長度與序號、JPEG 首尾標記，並以 Windows 圖片解碼器建立 640×480 點陣圖。任何檢查失敗便輸出錯誤及失敗 JSON；只有檢查通過才寫出 JPG。

成功 JSON 的 `pass=true` 代表上述通訊／格式檢查通過。圖片清晰度、朝向、是否適合 AI 分析仍需另外看圖。這個 USB 協議尚無端到端 payload CRC，不宣稱已檢出所有可能的位元錯誤。

| 數字 | 它表示甚麼 |
| --- | --- |
| `device_request_to_acquired_ms` | CAM 解析完命令至取得符合時間門檻的畫面，含丟棄較舊畫面的等待 |
| `device_dma_to_acquired_ms` | 畫面首 DMA 時間至應用程式取得畫面的間隔 |
| `device_jpeg_uart_send_ms` | CAM 從送出圖片標頭後到 JPEG 串口發送完成的本地耗時 |
| `host_payload_read_ms` | 電腦解析 IMG 後至讀完 N 個 JPEG 位元組的耗時 |
| `host_request_to_payload_end_ms` | 電腦送命令前至讀完 JPEG 的耗時 |
| `host_run_elapsed_ms` | 工具啟動後的整段時間，包含等 READY、INFO、驗證及儲存等開銷 |

不同計時範圍不能混用；這些單張測試不能換算成已驗證的連續 FPS。CAM ↔ S3 仍需獨立實作、驗收。
