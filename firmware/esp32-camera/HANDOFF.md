# Yuankun 交接：雙 ESP32 成果與 BMI160 通訊故障

日期：2026-11-05。交付人：**Dong Yuankun**。成果分支：**Feat-Esp-Yuankun**。

Yuankun 已要求保存並推送現有成果，請組長 **Zhang Yancheng 接手 IMU 排查與後續整合**。Yuankun 確認沒有萬用表，本輪停止要求他繼續硬件排查；這不表示 IMU 已修復或整個項目已完成。是否接手及後續安排由組長確認。

## 已完成、可保留的成果

以下均有來源、操作說明及實測證據；歷史測試通過不代表今天的 IMU 仍正常。

| 項目 | 已取得結果 | 入口 |
| --- | --- | --- |
| S3 主板自檢 | COM／CH340 通訊、上傳校驗、16MB Flash／8MB PSRAM，兩次程式報告 | [S3 結果](S3_TEST_RESULT.md)、[自檢程式](S3_Board_Check/S3_Board_Check.ino) |
| BMI160 歷史基線 | 0x68／0xD1；靜止與運動六軸約 49.73Hz、方向觀察及電腦端獨立零偏驗證 | [身份](BMI160_TEST_RESULT.md)、[六軸](BMI160_SIX_AXIS_RESULT.md)、[方向／零偏](BMI160_AXES_CALIBRATION.md) |
| CAM 自檢 | OV2640、4MB Flash／2MB PSRAM；3 張 640×480 新幀 JPEG 解碼通過，含桌面樣張 | [CAM 結果](CAM_RECHECK_RESULT.md) |
| ESP-NOW 雙板文字 | 雙向各 20／20；兩個受控漏 ACK 案例均重試恢復 | [文字結果](DUAL_ESP_TEXT_RESULT.md) |
| ESP-NOW 單張圖片 | Normal／DropAck／CorruptPacket 三案；三端 SHA256、640×480 解碼及反向 TEST_ONLY 通過 | [圖片結果](DUAL_ESP_IMAGE_RESULT.md) |
| 圖像與 IMU 並發基線 | 11-04 Normal：496 筆、49.7338Hz、最大 S3 讀取間隔 21.946ms；一張 JPEG 收取／USB 導出及反向回覆通過 | [並發結果](IMAGE_IMU_RESULT.md)、[來源](S3_Image_IMU_Check/S3_Image_IMU_Check.ino) |
| 專用 Wi-Fi／TCP 控制 | 11-05 電腦→S3→CAM→返回，5／5；空閒 TCP 重連後 1／1 | [網絡結果](WIFI_GATEWAY_RESULT.md)、[網關來源](S3_WiFi_Gateway_Check/S3_WiFi_Gateway_Check.ino) |

照片是桌面物件或天花板，未作健身動作取景驗收。並發基線只測單張 Normal，不是持續視頻或長期穩定性驗收。網絡測試只傳控制訊息，**沒有驗收照片／IMU 的 Wi-Fi payload**。

網絡控制子報告 pass=true，原外層流程報告 pass=false；兩者都保留。外層程序結果／恢復監測已修改並做語法檢查，修正版未重新做完整硬件測試。不能把這些項目寫成全部通過，詳見網絡結果。

本目錄的 Git 屬性保留 evidence 原始位元組，避免換行轉換令已記錄的 CSV／圖片 SHA256 失配；Windows 接收工具則固定 LF 換行。生成的 bin／elf 不入庫，已保留來源與構建指紋。

## 現在的阻塞：BMI160 沒有身份應答

**11-05 16:09 最新結果：S3 的 USB 正常，BMI160 在 0x68／0x69 均未應答。**

- 用戶已依 [正面位置表](BMI160_WIRING.md) 逐項確認 VIN 留空、六根線兩端全部吻合；背面被安裝結構遮擋，不再要求拆線拍照。
- 專用診斷程式成功編譯、上傳校驗，COM9 兩次讀回正確版本。兩個地址各三輪實際 STOP 探測都是 code=2；讀取身份收到 0 bytes。
- `RUN_INIT` 停在 `INITIAL_ID`，尚未執行軟重設、加速度計／陀螺儀啟動或配置寫入；本次沒有六軸資料。
- SDA／SCL 數位觀察均為高，**不是供電電壓量測**。沒有量測電源、上拉電阻或導通，原因尚未確認，不能直接判定接線錯誤或模組損壞。
- 早些時候曾讀到 D1、在 GYRO_WAKE_WRITE 失敗；那是較早診斷，不能用來描述目前身份完全未讀到的階段。
- 完整斷電、重新插牢、20／100ms 診斷，以及恢復與 11-04 成功時 SHA256 相同的映像，均未恢復。接續在同一故障總線做的 20／100ms 比較不是獨立對照；Wire code=4 亦不能直接說成 timeout。

最新原始證據：[摘要與來源指紋](evidence/2026-11-05/bmi160_bus_build_20261105_080905_504Z.json)、[三輪探測／初始化記錄](evidence/2026-11-05/bmi160_bus_diagnostic_20261105_080905_504Z.txt)、[上傳校驗](evidence/2026-11-05/bmi160_bus_upload_20261105_080905_504Z.txt)。完整歷程見 [BMI160_RECOVERY.md](BMI160_RECOVERY.md)。

## 接手時的實物與程式狀態

| 實物 | 狀態 |
| --- | --- |
| ESP32-S3 N16R8 | 本機 COM9／CH340；板上為 **BMI160_Bus_Check_v1**，未啟動 Wi-Fi／ESP-NOW，沒有背景六軸採集 |
| ESP32-CAM 與 USB 底座 | 本機 COM11；保留 **DualESP_Image_Check_v1**，本輪未重刷 |
| 紫色 BMI160 ×1 | 主選 IMU，歷史成功；目前身份通訊故障 |
| 藍色 GY-801 ×3 | 已知在手邊；未逐塊確認晶片／供電或做總線對照，不是已驗收的 BMI 替代品 |
| 杜邦線／麵包板 | 用戶確認有；六線位置核對完成，未做電氣量測 |
| 萬用表 | **Yuankun 確認沒有**；後續量測需由具備工具的人接手 |

接法：S3 3V3→BMI160 3v3、另一個 3V3→CS、GND→GND、另一個 GND→SA0、GPIO4→SDA、GPIO5→SCL；VIN 和另外五針排留空。以 [照片與位置表](BMI160_WIRING.md) 為準，不靠線色猜測。

## 組長接手後的最短檢查路徑

1. 按根 [AGENTS.md](../../AGENTS.md) 使用組長自己的工作分支審查／整合。本分支提供交接，不直接改 main 或代替組長合併。
2. 先保留目前接線與診斷程式，打開 S3 的串口（本機 COM9，換電腦後重新辨認），115200 baud、換行結尾。依次發 `INFO`、`PROBE`、`RUN_INIT`，核對是否與最新記錄一致。只有初始化成功才發 `SAMPLE`；操作電腦腳本前關閉 IDE 串口監視器。
3. 用萬用表實測 BMI160 3v3 對 GND 的電壓，並在斷電後檢查接點導通、CS／SA0 與訊號路徑；必要時比較其他線材或模組。若使用現有 GY-801 作對照，先核對它的供電／腳位，只作主控總線排查，不直接宣稱可代替 BMI160。
4. 若需重刷診斷版，開啟 [BMI160_Bus_Check.ino](BMI160_Bus_Check/BMI160_Bus_Check.ino)，選 ESP32S3 Dev Module、16MB Flash、OPI PSRAM、USB CDC On Boot Disabled、COM／CH340。原測試 Arduino IDE 2.3.10、CLI 1.5.1、ESP32 core 3.3.12、IDF 5.5.5。完整命令與判讀見 [診斷指南](BMI160_BUS_DIAG.md)。
5. 身份及六軸恢復後，先重跑 [合併版 Normal 並發檢查](IMAGE_IMU_CONCURRENCY.md)，再驗收 [Wi-Fi 圖像／IMU](WIFI_GATEWAY.md)。原成功映像僅本機保留，生成的 bin 不入庫；來源、工具版本及指紋在證據中，供接手者重新編譯核對。

## 尚未完成的項目

- IMU 現在的通訊恢復與根因確認。
- 圖像／IMU 的 Wi-Fi 傳輸、傳圖中斷線恢復、長時間穩定性及固定取景。
- 精密校準、跨板時間對齊、感測器佩戴／固定位置。
- 與 Haoyu 的電腦 AI 輸入輸出對齊；與 Yancheng 的 CAM→Arduino 電平／訊息及 LED／蜂鳴器閉環整合。

**交付邊界：已有軟件、實測資料與故障證據可交接；項目第 5 步仍未完成。** 後續硬件排查請組長安排，不再要求 Yuankun 在沒有量測工具的情況下反覆重接或重試。
