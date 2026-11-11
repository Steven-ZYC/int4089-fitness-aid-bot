# 第 5 步前半：收圖片時持續讀 BMI160

身份：Dong Yuankun。分支：`Feat-Esp-Yuankun`。日期：2026-11-04。

## 目的與目前狀態

第 4 步已分別證明 CAM 能拍照並經 S3 傳給電腦，第 3 步已證明 BMI160 能取得約 50 Hz 六軸資料。本步把兩部分合在同一個 S3 程式，檢查「傳照片時，動作資料有沒有中斷」。程式準備和實機驗收分開記錄，最新實測見 [IMAGE_IMU_RESULT.md](IMAGE_IMU_RESULT.md)。網絡、AI 和 Arduino 不包含在本步。

## 原理

S3 有兩份工作要交錯執行：主迴圈處理無線收圖和 USB 圖片導出；獨立的 BMI160 工作在 Core 1、優先序 3 輪詢新資料。採集工作只使用 I²C 和記憶體，不向串口列印；避免照片佔用串口時連帶阻塞採集。這是實作安排，是否達到目標仍以時間戳實測為準，不能僅憑使用背景工作宣稱即時可靠。

BMI160 保留已驗證的 50 Hz、±4 g、±500 °/s 設定，0x68／0xD1、GPIO4 SDA／GPIO5 SCL、100 kHz。只在加速度與陀螺儀都標示新資料時讀取六軸與 24-bit sensor time。沒有套用零偏補償，沒有啟用硬件 FIFO；這次仍是狀態輪詢，不能宣稱零漏樣。

背景工作持續採集；測試命令另開啟一段最多 4096 筆的 PSRAM 記錄，滿了停止記錄並標示 overflow，不覆蓋舊資料。約 50 Hz 下可容納約 82 秒；這個容量不是長時間資料流方案。傳圖及 USB 圖片導出時先存 IMU，凍結該段記錄後才逐行導出，未實作圖像／IMU 同時串流到電腦。

## 板子和操作

- CAM COM11 保留原 [DualESP_Image_Check_v1](DualESP_Image_Check/DualESP_Image_Check.ino)，不用重刷。
- S3 COM9 改用 [S3_Image_IMU_Check.ino](S3_Image_IMU_Check/S3_Image_IMU_Check.ino) 與同目錄 [imu_trace.h](S3_Image_IMU_Check/imu_trace.h)。此草圖只接受 ESP32-S3。
- S3 設定沿用 ESP32S3 Dev Module、16MB、OPI PSRAM、CDC Disabled、CH340 COM 口、115200。BMI160 [六線接法](BMI160_WIRING.md) 和兩條 USB 均維持原樣。
- 把 BMI160 麵包板平放、鏡頭對準光線充足的桌面物件；關閉 Arduino 串口監視器。測試只需靜止，暫時不用轉動。

在倉庫根目錄執行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\esp32-camera\test_s3_image_imu.ps1 -CamPort COM11 -S3Port COM9 -Case Normal
```

工具先核對兩端角色／開機編號／配對、IMU 設定，啟動記錄並留 5 秒傳圖前基線；拍一張、經 S3 接收及 USB 導出、驗證三端 SHA256／解碼／反向 TEST_ONLY，另留 3 秒傳圖後基線。最後凍結並取回 IMU CSV。`DropAck`／`CorruptPacket` 是可另外執行的受控案例，未執行者不能寫成已通過。

成功標準預先設為：整段 48–52 Hz、相鄰 S3 讀取時間差不超過 30 ms、sensor time 差為正且不超過 768 ticks（30 ms），序號連續，無讀取／設定錯誤或溢出；收圖和 USB 圖片導出各至少 10 筆，前段至少 200 筆、後段至少 100 筆。這些是桌面原型的檢查門檻，不是對人體分析準確性的標準。

## 資料與時鐘

CSV 保留 `sample_seq,t_read_us,sensor_ticks`、原始六軸及換算的 g／°/s，另加 `phase,request`：

| phase | S3 正在做甚麼 |
| --- | --- |
| 0 | 沒有正在收圖或導出圖片，包括傳圖前後 |
| 1 | 已發拍照請求，等待／接收／驗證 CAM 圖片 |
| 2 | 正在 USB 導出 JPEG，包含等串口排空 |

phase 是 S3 在 I²C 讀取開始時的工作狀態標籤，不是相機曝光時間。IMU 的 `t_read_us` 是 S3 本地讀取前時間；sensor time 每 tick 39.0625 µs、24-bit 約 655.36 秒回繞。相鄰 tick 差以模 2^24 計算。CAM 與 S3 的開機時鐘仍不同，不能直接相減；跨板校時與人體座標對齊尚未做。

JSON 記錄 CAM 基線來源、S3 草圖、IMU 模組、測試工具及 CSV 的 SHA256，並保存圖片與兩板原始文字日誌。原圖先留本機；人工查看無可識別人像後才納入倉庫工作區證據。本輪來源與已篩選證據隨本人分支交付；範圍見 [HANDOFF.md](HANDOFF.md)。

依據：[Bosch BMI160 DS000-09](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi160-ds000.pdf) 的暫存器、量程和 sensor time；[Espressif FreeRTOS](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/system/freertos_idf.html) 的工作優先序、核心綁定及共享資料保護。具體任務分配、記錄容量和門檻由本項目選定。
