# BMI160 分段診斷

日期：2026-11-05。用戶：Dong Yuankun。分支：`Feat-Esp-Yuankun`。交付與目前未完成項目見 [HANDOFF.md](HANDOFF.md)。

用戶已按晶片正面的位置表核對 VIN 留空及六根線全部吻合，無法在現有安裝方式拍背面帶線照；不再要求拆線拍照。位置吻合不等於量測過電壓或接點導通。

## 這次要查甚麼

電腦與 S3 的 USB 已可通訊，但原成功映像只回報一般的 IMU_INIT。使用獨立的 [BMI160_Bus_Check](BMI160_Bus_Check/BMI160_Bus_Check.ino)，分開記錄：

1. S3 的 GPIO4／GPIO5 啟動 I²C。
2. 在 0x68、0x69 讀取預期身份 0xD1。
3. 僅在 0x68 身份符合時，依序測軟重設、加速度計正常模式、陀螺儀正常模式；每一步讀回身份、電源管理及錯誤暫存器。
4. 前面全部通過才設定原基線的 50Hz／±4g／±500°/s，核對讀回值。
5. 只有完整初始化通過，才允許約 3 秒的新資料就緒讀取，列出六軸原始值及感測器時鐘。

這份程式不啟動 Wi-Fi、ESP-NOW 或相機，不代表完整圖像／IMU／網絡驗收。診斷時會替換 S3 上的應用；CAM 不刷寫，舊成功映像另行保留。

## 操作與輸出

沿用 COM／CH340、115200 baud、ESP32S3 Dev Module、16MB Flash、OPI PSRAM、USB CDC On Boot Disabled。SDA=GPIO4、SCL=GPIO5，100kHz，Wire 等待上限 100ms。

| 命令 | 做甚麼 | 判讀範圍 |
| --- | --- | --- |
| INFO | 讀回診斷版本及是否已初始化 | 不重新初始化 |
| PROBE | 兩個地址的實際 STOP 探測，以及身份暫存器讀取 | 不改感測器配置 |
| RUN_INIT | 依序測重設／啟動／配置，遇第一個失敗即停止後續步驟 | 只寫暫時設定，不寫 NVM／eFuse |
| SAMPLE | 初始化成功後讀約 3 秒新資料 | 只驗基本資料可讀，未做頻率／校準驗收 |

程式開機只執行身份探測，RUN_INIT 需由電腦明確發出；故障後仍能處理 INFO／PROBE，不必為了重讀狀態反覆刷寫。

`PROBE stop_code` 是實際 `endTransmission(true)` 的結果。`READ queued_code` 只是選擇暫存器的排隊結果；必須同時看到 `received=expected` 才代表讀取成功，不能把 queued_code=0 當作收到裝置 ACK。讀取失敗時沒有輸出一個假的有效身份值。

`INIT_RESULT pass=0 stage=...` 表示本次停在哪一階段。命令寫入錯誤後仍等候該步穩定時間並記錄讀回狀態，以免只看一個回傳碼便判定原因。`PINS` 是 SDA／SCL 的數位邏輯觀察，**不是電壓量測**。它不能直接證明電源、上拉電阻或模組好壞。

## 時序與來源

軟重設後等 100ms、加速度計啟動後等 10ms、陀螺儀啟動後等 100ms；每次一般寫入後另等 1ms。依 [Bosch BMI160 資料表](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi160-ds000.pdf) 第 86 頁命令執行時間與第 97 頁寫入後間隔。這些等待不是已證明的故障修復。

回傳碼依本機 [Arduino ESP32 Wire 3.3.12](https://github.com/espressif/arduino-esp32/blob/3.3.12/libraries/Wire/src/Wire.cpp)：4 是一般其他錯誤，明確 timeout 是 5。`endTransmission(false)` 在此版本只排隊，讀取由後續 requestFrom 執行。

## 結果狀態

16:09 已編譯／上傳校驗成功，並在 COM9 讀回 BMI160_Bus_Check_v1。0x68／0x69 各三次實際探測均 stop_code=2，身份讀取收到 0 bytes；RUN_INIT 停在 INITIAL_ID，未執行重設、啟動或配置寫入，也未執行 SAMPLE。SDA／SCL 的數位觀察均為高，不是電壓量測。不能據此直接判定模組損壞。

證據：[構建與實測摘要](evidence/2026-11-05/bmi160_bus_build_20261105_080905_504Z.json)、[串口原始記錄](evidence/2026-11-05/bmi160_bus_diagnostic_20261105_080905_504Z.txt)、[上傳校驗](evidence/2026-11-05/bmi160_bus_upload_20261105_080905_504Z.txt)。當前板上是這份獨立診斷程式，不是網關或原成功並發版；舊成功映像已驗證保留。後續見 [恢復排查](BMI160_RECOVERY.md)，不沿用 11-04 歷史成功作為目前正常的證明。
