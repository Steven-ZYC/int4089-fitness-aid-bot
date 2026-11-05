# ESP32-S3 基本自檢結果：通過

日期：2026-10-31。負責人：Dong Yuankun。分支：`Feat-Esp-Yuankun`。本機工作記錄，未 commit／push。

## 實際做了甚麼

1. Windows 識別到 `USB-SERIAL CH340 (COM9)`。
2. 使用 esptool `5.3.1`，以指定 `esp32s3` 型號、115200 baud、`--no-stub flash-id` 讀取晶片／Flash 資訊，成功連接確切 ESP32-S3。
3. 核對倉庫原始碼與已編譯副本的 SHA256 一致，再用 Arduino CLI 上傳既有 `S3_Board_Check`。寫入後的資料雜湊校驗通過，板子重啟。
4. 透過 Windows PowerShell／.NET 串口，以 115200、8N1、DTR／RTS Disabled 讀取程式輸出。收到兩次含完整記憶體欄位及 READY 的週期報告，讀取程式結束後已關閉串口。

沒有輸出或保存 MAC、設備唯一序號。未操作 eFuse 或新增外部接線。

## 已讀回的資料

| 項目 | 實際結果 |
| --- | --- |
| 端口 | COM9，CH340 USB-to-UART |
| ROM 工具識別 | ESP32-S3 (QFN56)，revision v0.2 |
| ROM 工具列出的硬件特徵 | 雙核、240MHz、內建 8MB PSRAM |
| Flash 探測 | 16MB，Quad SPI，設定電壓 3.3V（只讀取既有設定） |
| 程式晶片欄位 | `chip=ESP32-S3` |
| 執行時 Flash | `flash_bytes=16777216` |
| PSRAM 初始化 | `psram_found=YES` |
| PSRAM 可用容量 | `psram_bytes=8388608` |
| PSRAM heap 總量 | `psram_heap_bytes=8388608` |
| 當下空閒 PSRAM | `free_psram_bytes=8384788`，這是當時讀值，會隨程式使用而變化 |
| 當下空閒內部 heap | `free_heap_bytes=356100`，同樣是當時讀值 |
| Arduino 核心／ESP-IDF | `3.3.12`／`v5.5.5` |
| 程式執行證據 | 兩次週期報告均有預期 chip、Flash、PSRAM 與 READY 欄位 |

原始碼 SHA256：

```text
275F8D7C30E8E1D2AF9843ADA22263E98CA6FD228CA91E7001569F5C3A7271BF
```

編譯設定與開啟方法見 [S3_BRINGUP.md](S3_BRINGUP.md)。本次是上傳已核對的既有編譯產物；沒有為相同未變動的程式重複編譯。

## 串口輸出節錄

以下欄位在兩次報告中一致；空閒記憶體是本次瞬時讀值，不作後續固定驗收值：

```text
=== S3_BOARD_CHECK ===
chip=ESP32-S3
revision=2 cores=2 cpu_mhz=240
arduino_core=3.3.12
esp_idf=v5.5.5
flash_bytes=16777216
psram_found=YES
psram_bytes=8388608
psram_heap_bytes=8388608
free_psram_bytes=8384788
free_heap_bytes=356100
MEMORY: matches expected N16R8 capacities.
READY: serial diagnostics only; peripherals and networking are not tested.
```

## 這些證據表示甚麼

- **可連接**：USB 串口與晶片下載程式可以通信。
- **可寫入**：自檢程式寫入 Flash 並通過寫入校驗。
- **可執行**：重啟後，自己的程式持續執行 `loop()` 並輸出報告。
- **記憶體初始化成功**：執行時識別到與 N16R8 標示相符的容量。

這次可將「S3 基本自檢」標為完成。尚未進行全容量記憶體壓力測試、長時間穩定性測試、Wi-Fi、IMU 讀值或雙板通信驗證；這些保留為各自後續任務。

## 你可以親眼觀察

新 S3 保持接在 COM 接口。在 Arduino IDE 選 Port **COM9**，打開 Serial Monitor，設 **115200 baud**，應約每 5 秒看到相同格式的報告。現在不需要再次上傳。

「編譯」是產生機器能執行的程式；「上傳／燒錄」是寫入 Flash；「串口監視器」則讓你看到程式執行時主動傳出的文字。本次三個階段都有對應證據。

下一步按 [進度清單](PROGRESS.md) 第 2 步，核實 BMI160 的供電、接線和晶片 ID。
