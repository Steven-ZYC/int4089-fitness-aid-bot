[English](usb-camera.md) | [简体中文 / 原文](usb-camera_zh_cn.md) | [繁體中文（香港）](usb-camera_zh_hk.md)

<a id="cam--电脑-usb-图像控制协议"></a>

# CAM ↔ 電腦 USB 影像／控制協議

目前韌體：[Cam_USB_Bridge](../../firmware/usb-ai-bridge/Cam_USB_Bridge/Cam_USB_Bridge.ino)。電腦實現：[serial_camera.py](../../app/serial_camera.py)。

<a id="串口与图像"></a>

## 串列埠與影像

921600 波特率、8N1，無流控。影像為 640×480 JPEG，quality=18，兩個 PSRAM 幀緩衝，LATEST 模式。相機與 S3 的引腳和無線 MAC 不隨本輪倉庫整理改變。

電腦啓動時發送 `INFO\n`，要求返回 `fw=Cam_USB_Bridge_v1`。隨後每輪批量寫入三條命令，韌體按順序響應：

```text
ALARM 0\n       # 或 ALARM 1；數字為報警關／開
STATUS\n
CAPTURE\n
```

響應順序：

```text
CMD_OK state=0
BRIDGE role=CAM state=... ack=... ack_state=... ack_age_ms=... errors=... drops=...
META seq=... request_us=... frame_us=... acquired_us=... discarded=... width=640 height=480 len=N
IMG N crc=xxxxxxxx
<N 個原始 JPEG 位元組>
\nDONE seq=... written=N send_us=...
```

上例 `\n` 表示換行符，`N` 和省略號是佔位符，不按字面發送。CRC 是 JPEG 原始位元組的 CRC32，8 位十六進制；不使用 Base64。電腦按精確長度讀取二進制，再檢查 CRC、JPEG 標記、解碼尺寸、幀尾序號和長度，不能把 JPEG 當作逐行文本。

`READY` 等文本可出現在幀外。無線任務不寫 CAM USB，避免將異步日誌插入影像。目前只有一個電腦工作執行緒訪問串列埠。

<a id="新鲜度与报警"></a>

## 新鮮度與報警

- 相機取幀時只接受 first-DMA 時間戳不超過目前時刻 200ms 的影像。它不是曝光時間，也不是到網頁的完整延遲；舊單次拍照要求“請求後才開始取幀”，目前雙緩衝策略改為“最近已完成的幀”。
- 電腦緩存的影像超過 1.5 秒不可用；推理執行緒跳過重複序號。
- 電腦判定超過 1 秒不刷新時，工作執行緒發送關閉。CAM 超過 1.2 秒沒有有效電腦報警命令時也發送關閉。
- `CMD_OK` 表示 CAM 解析了命令；S3 是否收到需看無線 ACK。USB 錯誤會終止工作執行緒，後續依賴兩端超時清除舊報警。
- 目前無自動重連，斷線後重新確認串列埠並啓動應用。

## 性能

實測 268 幀／30 秒，約 8.93 FPS；帶 AI 頁面約 9 FPS，畫面細節／光照會影響 JPEG 大小和速率。CRC、解碼、幀尾校驗始終保留。

電腦可用 `serial://COM3?baud=460800` 顯式選擇歷史速率，但它只修改電腦配置，韌體必須使用相同速率。預設保持 921600，不進行自動速率切換。
