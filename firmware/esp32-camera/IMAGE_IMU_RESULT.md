# 收圖與 BMI160 同時採集：2026-11-04 實測

身份：Dong Yuankun。分支：`Feat-Esp-Yuankun`。2026-11-04，交付與目前未完成項目見 [HANDOFF.md](HANDOFF.md)。

**Normal 單張圖片與 IMU 並發採集測試通過。** 用戶確認板子放穩、鏡頭及串口監視器就緒後，S3 更新為 `S3_Image_IMU_Check_v1`，CAM 保留 `DualESP_Image_Check_v1`。實際取得 496 筆六軸記錄、約 49.7338 Hz；收圖期間 25 筆、USB 圖片導出期間 45 筆。圖片三端 SHA256、640×480 解碼及反向 TEST_ONLY 回覆均通過。

## 編譯與上傳

- Arduino CLI 1.5.1、esp32 core 3.3.12／IDF 5.5.5、esptool 5.3.1。
- S3 COM9／CH340、16MB Flash、OPI PSRAM、CDC Disabled、115200；GPIO4 SDA／GPIO5 SCL 和 BMI160 六線維持原樣。
- 程式 909,278 bytes、靜態變數 47,356 bytes；應用 bin 909,424 bytes。編譯完成約 01:01:44（UTC+8）；映像目標先核對 ESP32-S3，再上傳 COM9，寫入校驗通過。沒有重刷 CAM。
- S3 草圖 SHA256：`145437674FE1FA3D76460F71A5C9038528FA7D93517D4FC6ADDBB4E9F1AD3834`。
- IMU 模組 SHA256：`4500E9EEE05D451732A841997DCC19127A6A865048E07FBA80115DBCBD2A3502`。
- 測試工具 SHA256：`590CF95174AA9EDCA0E27DD9AFD87390E253582C9733D7B9847EA06F714D28BA`。
- bin SHA256：`9E169486B66DF3350139B59AE4D441D116992D8ADDB38EA19B1D95FB57726779`。

[構建摘要](evidence/2026-11-04/s3_image_imu_build_upload_20261104.json)、[已過濾裝置唯一位址的上傳日誌](evidence/2026-11-04/s3_image_imu_upload_20261104.txt)。

## 並發採集實測

工具於 01:04:12.465–01:04:25.430（UTC+8）執行約 12.899 秒，包含查詢、記錄、拍照、圖像／CSV 導出和驗證；其中第一到最後一筆 IMU 約 9.953 秒，不能把整次工具時間當採樣分母。

| 項目 | 結果 |
| --- | --- |
| IMU 設定 | 0x68／0xD1；acc_conf/range=0x27/0x05、gyr_conf/range=0x27/0x02、PMU=0x14、err=0；50 Hz、±4 g、±500 °/s，未校準 |
| 原始記錄 | 496 筆，序號 1–496 連續；含原始六軸、g／°/s、S3 時間及 sensor ticks |
| 整段速率 | 49.7337986 Hz，門檻 48–52 Hz |
| 最大 S3 相鄰讀取間隔 | 21,946 µs，低於 30,000 µs 門檻 |
| 最大相鄰 sensor time 差 | 555 ticks，低於 768 ticks 門檻；沒有零或倒退差值 |
| 工作狀態標籤 | phase 0=426 筆、phase 1 收圖=25 筆、phase 2 USB 圖片導出=45 筆；兩個忙碌階段均對應本次 request 1 |
| 前／後對照 | 收圖前 251 筆、USB 導出後 171 筆；phase 0 還包含兩階段之間少量空閒記錄 |
| 異常 | 讀取／設定錯誤、fault、overflow 均為零；S3 回報最大間隔與電腦從 CSV 重算相同 |

背景工作持續讀感測器，測試結束只停止保留該段記錄；串口工具已關閉。這次沒有發現超過門檻的空檔，不宣稱硬件每一次 ODR 更新皆零漏樣。IMU 先存 PSRAM、之後另行導出，尚未同時把兩種資料串流上網。

## 同一輪的圖片及反向訊息

JPEG 10,031 bytes，51 片、零重試；CAM request 1／frame 4，每次取幀丟棄 1 張較舊緩衝。CAM 原圖、S3 重組及 PC 收到的 SHA256 均為 `5686D2A6D20D8F673207735EA9AAFBC1A14D8484699E7965816987F58794E82B`，完整解碼 640×480 通過。

CAM 取得新幀 44.046 ms、CAM 無線至 END ACK 450.390 ms、S3 命令至就緒 497.037 ms、PC 讀 USB payload 約 851.718 ms；各段有重疊，不可相加或換算持續 FPS。反向 TEST_ONLY 的 request 2／nonce 1478797411，一次嘗試、往返 7.542 ms。兩端未重啟，無線／佇列／API／壞包計數沒有增加。

原圖人工查看為天花板及空調，無可識別人像；原始 bytes 未修改。**這輪用戶要求鏡頭朝桌面，但實際取景仍不符，固定方向與正式動作取景尚未驗收。** 它可用作資料傳輸與並發採集證據，不是人體分析樣本。

## 原始證據與下一步

- [JSON 完整結果](evidence/2026-11-04/imageimu_20261104_010412_465_normal.json)
- [IMU CSV](evidence/2026-11-04/imageimu_20261104_010412_465_normal_imu.csv)
- [未修改 JPEG](evidence/2026-11-04/imageimu_20261104_010412_465_normal.jpg)
- [CAM 日誌](evidence/2026-11-04/imageimu_20261104_010412_465_normal_CAM.txt)、[S3 日誌](evidence/2026-11-04/imageimu_20261104_010412_465_normal_S3.txt)

第 5 步前半的 Normal 桌面並發檢查完成，**第 5 步整體仍未完成**。下一步固定鏡頭方向，建立 S3 ↔ 電腦的網絡通路，先用明確 TEST_ONLY 回覆；與 Haoyu 對齊格式、跨板時鐘及固定位置後再聯調 AI。

本合併版未執行 DropAck／CorruptPacket、長時間／距離／自然干擾、FIFO、串流壓力、網絡斷線／重連、跨板校時、AI 或 Uno。第 4 步的三案例屬於舊獨立圖片版，不能當作新合併版三案例皆已通過。

操作、資料欄位與預先訂定的門檻見 [IMAGE_IMU_CONCURRENCY.md](IMAGE_IMU_CONCURRENCY.md)。
最新狀態（2026-11-05）：[Wi-Fi 控制／TCP 重連](WIFI_GATEWAY_RESULT.md) 通過；S3 已更新為網關版，但 IMU 在 GYRO_WAKE_WRITE 初始化失敗，0x68／0xD1 身份可讀。COM9 已恢復，斷電與從開機使用 100ms 重檢仍未恢復，見 [IMU 排查](BMI160_RECOVERY.md)；照片／IMU 的 Wi-Fi 傳輸未測。此頁其餘內容保留 11-04 成功基線；當前統一狀態見 [PROGRESS.md](PROGRESS.md)。
