# Yuankun：先完成 S3 主板自檢

更新日期：2026-11-04。依據 `origin/main` 的 `e5757b6` 版本（2026-10-30 consultation 後的新分工）。工作分支：`Feat-Esp-Yuankun`。

## 現在需要交付甚麼

你負責硬件資料採集與通信：舊 ESP32-CAM 拍照 → 新 ESP32-S3 主節點接收圖像並採集 IMU → 主節點傳給電腦；電腦的姿勢結果經主節點回到 CAM，再由 CAM 交給 Arduino 控制 LED／蜂鳴器。Haoyu 負責電腦端 AI，Yancheng 統籌接口和集成。本階段以電腦 AI 為主，板上部署模型不在目前工作清單。

| 順序 | 要做的事 | 現況／完成證據 |
| --- | --- | --- |
| 1 | 新 S3 的識別、燒錄、串口、Flash／PSRAM 自檢 | **已通過基本自檢**：COM9、16MB Flash／8MB PSRAM、兩次週期報告 |
| 2 | 舊 ESP32-CAM 拍照基線 | 11-03 COM11 重測通過，OV2640、4MB Flash／2MB PSRAM，新固件 3 張新畫面均通過解碼，見 [CAM 重測](CAM_RECHECK_RESULT.md) |
| 3 | 紫色 BMI160 的識別、六軸讀值與校準基線 | **基礎採集驗收通過**：約 49.73 Hz、照片參考方向、平面轉動及獨立零偏，見 [結果與後續項目](BMI160_AXES_CALIBRATION.md)；完整精密校準等尚未完成 |
| 4 | CAM ↔ S3 圖像與結果雙向傳輸 | **基礎通過**：三個單張圖片案例的指紋／解碼及反向 TEST_ONLY 通過；受控漏 ACK／壞包各重試一次，見 [圖片結果](DUAL_ESP_IMAGE_RESULT.md) |
| 5 | S3 ↔ 電腦網絡上傳／結果回傳 | 未實現；需確認可用網絡、電腦接口和錯誤處理 |
| 6 | 時間戳、圖像／IMU 格式及 Arduino 回傳協作 | 待與 Haoyu、Yancheng 對齊並聯調 |

S3 自檢與 IMU 基礎採集驗收已通過。你有藍色 GY-801 三塊、紫色 BMI160 一塊，選型理由見 [IMU_SELECTION.md](IMU_SELECTION.md)。以 [PROGRESS.md](PROGRESS.md) 作統一清單：第 1–4 步基礎驗收完成；合併版 Normal 並發檢查也已通過，見 [並發結果](IMAGE_IMU_RESULT.md)。下一步固定鏡頭並做網絡。當前 S3 合併版已讀 IMU，各節點時間仍需後續對齊。本檔下方為 S3 初次自檢的復現流程；目前使用中的草圖見進度清單。

## 照片已確認與尚未確認的硬件

- 屏蔽罩印字為 **ESP32-S3-N16R8**；背面印有 **ESP32-S3**。
- 可見 **CH340C** USB 串口晶片、RST 和 BOOT 按鈕，以及背面標為 **COM**、**USB** 的兩個 Type-C 接口。第一步只接 **COM**。
- S3 主板照片中沒有攝像頭或 IMU；你已確認仍有舊 ESP32-CAM，並新提供 GY-801 與 BMI160 標示模組照片，第一版選紫色 BMI160。這些是分開的模組，需要後續連接與讀值驗證。
- N16R8 標示對應的 16MB Flash／8MB PSRAM 已於 2026-10-31 讀回；見 [實測結果](S3_TEST_RESULT.md)。整塊開發板的廠商、原理圖版本和每個排針的可用條件仍需各自核實。
- 舊 CAM 與 S3 使用不同草圖和開發板設定；本自檢不涉及攝像頭接線。

## 第一個可操作步驟

暫不接外部感測器或板間跳線。用能傳資料的 USB 線，連到 S3 **背面標示 COM 的接口**。標示 USB 的另一個接口留待原生 USB／OTG 階段再處理。

1. Arduino IDE 打開 [`S3_Board_Check.ino`](S3_Board_Check/S3_Board_Check.ino)。
2. 在開發板選單選 **esp32 by Espressif Systems → ESP32S3 Dev Module**。
3. 在 Tools 設定下表選項。這組選項已按本機安裝的 `esp32 3.3.12` 板卡定義核對，並已在這塊板子完成基本自檢。

| Arduino IDE 選項 | 第一次自檢設定 |
| --- | --- |
| Board | ESP32S3 Dev Module |
| Port | 插上 COM 接口後新增的端口；不能沿用舊 CAM 的 COM9 假定 |
| Flash Size | 16MB (128Mb) |
| PSRAM | OPI PSRAM |
| USB CDC On Boot | **Disabled**（本次使用 CH340C COM 接口） |
| USB Mode | Hardware CDC and JTAG |
| Partition Scheme | 16M Flash (3MB APP/9.9MB FATFS) |
| Upload Speed | 115200（先以連線穩定為優先） |
| Serial Monitor | 115200 baud |

4. 點 Verify，再點 Upload。上傳會替換這塊 S3 現有的應用程式；不要選到舊 CAM 或 Arduino 的端口。
5. 上傳成功後打開 Serial Monitor，設 115200 baud。程式每 5 秒重印報告，方便打開監視器後讀取。
6. 保存報告中的晶片、Flash、PSRAM 數值及任何錯誤文字；依實際輸出填寫下方記錄。

預期看到的例子（**示例，不是本次實測**）：

```text
=== S3_BOARD_CHECK ===
chip=ESP32-S3
...
flash_bytes=16777216
psram_found=YES
psram_bytes=8388608
...
MEMORY: matches expected N16R8 capacities.
READY: serial diagnostics only; peripherals and networking are not tested.
```

`psram_bytes` 透過 ESP-IDF 讀取已初始化 PSRAM 的可用容量，`psram_heap_bytes` 是加入動態記憶體配置器的總量，`free_psram_bytes` 是當下剩餘量，三者不應混為一談。自檢只輸出串口診斷；未測試 PSRAM 全容量讀寫可靠性，也未啟動 Wi-Fi、CAM 或 IMU。程式不會改寫 eFuse 或格式化檔案系統。

## 遇到問題

- **沒有新增 COM 口**：核對 COM 接口與資料線，在裝置管理員看 CH340 是否被識別；必要時只從 WCH 官方來源準備驅動，不先更改腳位。
- **一直 Connecting／無法進入下載模式**：先關 Serial Monitor；按住 BOOT、按一下 RST、放開 RST，再開始 Upload，連上後放開 BOOT。不同底板自動下載電路可能不同；失敗時記錄完整錯誤。
- **畫面亂碼／沒有報告**：確認 115200 baud、選對 COM 口，且 USB CDC On Boot 為 Disabled；可按一下 RST。
- **PSRAM 為 0 或初始化失敗**：核對 OPI PSRAM 與板上 N16R8 標示，記錄錯誤；不要透過改電壓、eFuse 或隨機換接 GPIO 排查。
- **編譯提示選錯板**：本程式只允許 ESP32-S3 及 COM 路線的 CDC 設定；檢查 Board 和 USB CDC On Boot。

## 自檢記錄（2026-10-31 已實測）

| 項目 | 實際結果 |
| --- | --- |
| COM 端口 | COM9，已讀到確切 ESP32-S3 |
| 上傳成功 | 成功，寫入後雜湊校驗通過並重啟 |
| 晶片／Flash／PSRAM | ESP32-S3／16MB／8MB，PSRAM 初始化成功 |
| 串口報告 | 連續讀到兩次週期報告；去除唯一識別資料的記錄見 [S3_TEST_RESULT.md](S3_TEST_RESULT.md) |
| 本地編譯 | **通過**：Arduino CLI 1.5.1、esp32 3.3.12；程式 280,467 bytes，靜態全域變數 22,076 bytes。不是實機容量或硬件測試結果 |
| 後續進度（2026-11-04） | [IMU 基礎採集](BMI160_AXES_CALIBRATION.md)、[CAM USB](CAM_RECHECK_RESULT.md)、[雙板文字](DUAL_ESP_TEXT_RESULT.md) 已通過。兩板曾運行 DualESP_Image_Check_v1；[三個圖片案例](DUAL_ESP_IMAGE_RESULT.md) 的三端指紋、解碼及反向回覆通過；後續 [合併版 Normal 並發檢查](IMAGE_IMU_RESULT.md) 亦通過，S3 已換合併版；網絡未開始 |

本次編譯使用與上表相同的 S3／16MB／OPI PSRAM／CDC Disabled 設定：

```text
esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200
```

本機工具曾在自訂中文 build 路徑的連結階段失敗；改在英文臨時目錄編譯同一份草圖後通過。Arduino IDE 可先用其預設臨時建置目錄，不必把你的整個專案搬走。

## 參考資料

- [樂鑫模組命名規則](https://developer.espressif.com/blog/2025/03/espressif-part-numbers-explained/)：N／R 容量標示。
- [Arduino ESP32 Tools 選項](https://docs.espressif.com/projects/arduino-esp32/en/latest/guides/tools_menu.html)：開發板、Flash、PSRAM 選項。
- [原生 USB CDC 設定](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/cdc_dfu_flash.html)：原生 USB 路線和本次 COM 路線需要區分。

只有明確驗證的項目才改成已完成。提交及推送按根 [AGENTS.md](../../AGENTS.md) 的兩階段確認流程處理。
最新狀態（2026-11-05）：[Wi-Fi 控制／TCP 重連](WIFI_GATEWAY_RESULT.md) 通過；S3 已更新為網關版，但 IMU 在 GYRO_WAKE_WRITE 初始化失敗，0x68／0xD1 身份可讀。COM9 已恢復，斷電與從開機使用 100ms 重檢仍未恢復，見 [IMU 排查](BMI160_RECOVERY.md)；照片／IMU 的 Wi-Fi 傳輸未測。此頁其餘內容保留 11-04 成功基線；當前統一狀態見 [PROGRESS.md](PROGRESS.md)。
