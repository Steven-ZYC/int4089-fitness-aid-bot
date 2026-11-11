# Wi-Fi 控制通路實測：2026-11-05

身份：Dong Yuankun。分支：`Feat-Esp-Yuankun`。交付與目前未完成項目見 [HANDOFF.md](HANDOFF.md)。

**專用 Wi-Fi／TCP 控制通路及空閒 TCP 重連通過；照片與 IMU 網絡傳輸未測。** 用戶同意暫時切換電腦 Wi-Fi，並重新核對六線後，S3 更新為 S3_WiFi_Gateway_Check_v1。CAM 保留 DualESP_Image_Check_v1。

## 完成的實機測試

電腦連 S3 專用 AP，IP 192.168.4.1／TCP 4089／頻道 1。S3 保留 STA 介面與 CAM 的 ESP-NOW 配對，兩端開機編號交叉核對相符。05:27:48.560–05:27:49.578 UTC（香港／中國時間 13:27:48–13:27:49）執行以下控制測試：

| 項目 | 實測 |
| --- | --- |
| 控制路徑 | 電腦 TCP → S3 → ESP-NOW → CAM，CAM 回覆經 S3 TCP 返回電腦 |
| 正常訊息 | 5／5 成功，每條帶不同 nonce；兩端 request／nonce／TEST_ONLY 對應，全部一次嘗試 |
| S3 量測的往返 | 8.476、7.531、7.433、7.482、7.439 ms，平均 7.6722 ms；是 S3↔CAM 段，不包含電腦 TCP 往返 |
| 空閒 TCP 重連 | 關閉再重開，S3 sessions=2、disconnects=1；板子沒有重啟，重連後第 6 條回覆成功，S3↔CAM 7.486 ms |
| 計數 | 兩板收／發佇列、發送 API、底層發送、壞包計數無增加 |
| IMU | `imu=FAULT`、fault=4，這份測試沒有把 IMU 當成正常 |
| 圖像／IMU payload | 未請求或傳送，JSON 的 image_tested／imu_data_tested 均為 false |

原始控制報告保留在本輪 evidence，內容不改寫為完整第 5 步通過。網絡模組與 TCP 接收器已受本輪驗證；後續只增加的 IMU 啟動診斷需以相應啟動報告核對。

## 自動流程的兩個記錄問題

控制測試子報告為 pass=true，但外層流程報告 pass=false，原始 switch_summary 保留。外層讀取背景程序 ExitCode 的方式誤判子測試，且原網絡恢復監測窗口內未見完成連線。隨後實查 Windows WLAN 已 connected、IPv4Connectivity=Internet；AP 已收到 AP_OFF，臨時 Wi-Fi profile 及含臨時密碼的 XML 已移除。

已修正程序結果讀取／交叉檢查，以及在 AP 關閉後再核對原 profile 的順序；修正版語法檢查通過，沒有為此重跑硬件測試。不能把原始外層 false 改成 true，或聲稱修正後的整個自動流程已實測通過。對原 profile 的本輪監測為 false，後續只確認恢復了 Internet，不擴大為已逐項證明原 profile 相同。

## 尚未恢復的 IMU

原 S3 合併版重新啟動後為 IMU_INIT。重新插牢六線後仍失敗；新增診斷讀到 0x68／0xD1，證明可讀感測器身份，但後續初始化未完成。0x69 未讀到身份。診斷中的 `ack` 是 Wire.endTransmission(false) 的回傳，不可單憑它判斷該位址是否有裝置；以實際讀取成功及 ID 為準。

本網關在 IMU 失敗時明確回報 FAULT，仍可單獨測試網絡控制；完整照片／IMU 接收工具會拒絕這個狀態。初始化失敗時 INFO 的全零配置快取不是有效量測或初始化成功證據。最新逐階段診斷已確認 `IMU_INIT_FAILED stage=GYRO_WAKE_WRITE`，也就是喚醒陀螺儀時 I²C 寫入失敗；尚不能據此確定是供電、接點或其他原因。已請用戶完整斷電 10 秒後再接回 COM，等待重檢。

## 原始證據

- [控制 JSON](evidence/2026-11-05/wifi_control_20261105_052748_540Z.json)、[CAM](evidence/2026-11-05/wifi_control_20261105_052748_540Z_CAM.txt)、[S3](evidence/2026-11-05/wifi_control_20261105_052748_540Z_S3.txt)。
- [外層原始 false 報告](evidence/2026-11-05/switch_summary.json)、[後續恢復上網檢查](evidence/2026-11-05/wifi_postcheck_20261105.json)。
- [逐階段開機診斷](evidence/2026-11-05/wifi_gateway_final_diagnostic.txt)、[最後診斷版編譯摘要](evidence/2026-11-05/wifi_gateway_build_20261105.json)、[最後上傳日誌](evidence/2026-11-05/wifi_gateway_diagnostic_upload.txt)。

第 1–4 步與 11-04 的 496 筆並發記錄保留為歷史驗收；今天的 IMU 故障需要先恢復。第 5 步仍進行中，下一步定位初始化失敗、恢復六軸後，再做照片及 IMU 的 Wi-Fi 接收。固定鏡頭、AP 掉線／傳圖中斷線、長時間、AI／Arduino 也未驗收。

復現與程式入口見 [WIFI_GATEWAY.md](WIFI_GATEWAY.md)，最新狀態見 [PROGRESS.md](PROGRESS.md)。
斷電後更新：用戶確認拔掉 S3 全部 USB 10 秒再接回；本機只見 COM3／COM4／相機 COM11，暫未識別 S3 COM9。正等待重新插牢 COM 資料接口，斷電後 IMU 是否恢復未知，見 [USB 狀態](evidence/2026-11-05/s3_after_cold_usb_status_20261105.json)。前述 GYRO_WAKE_WRITE 是斷電前已確認的失敗階段。
本輪重插後（11-05）：COM9 已恢復；開機仍讀到 0x68／0xD1，失敗階段仍為 GYRO_WAKE_WRITE，fault=4。新增 IMU_BUS_DIAG 在無採集工作的初始化故障狀態下比較 I²C：20ms 時 reset／accel 寫入 code=0，gyro 寫入 code=4、耗時 6.987ms；之後身份／PMU／錯誤暫存器均讀取失敗。接續的 100ms 嘗試連 reset 亦失敗（code=4、約 99.722ms），因沿用已故障總線，不能把它當成獨立對照或判定模組損壞。

Wire code=4 是一般其他錯誤；本機 core 3.3.12 的明確 timeout 對應 code=5，因此不能單憑這個結果說「20ms 太短」。目前另編譯從開機直接使用舊成功基線 100ms 的版本，結果待補。診斷只改寫既有 volatile reset／PMU 命令，沒有寫入 NVM／eFuse；沒有啟動六軸採集。

最新重檢：COM9 已恢復；初始化仍失敗。20／100ms 總線診斷及從開機直接使用 100ms 的結果均未恢復六軸，詳見 [IMU 排查](BMI160_RECOVERY.md)。目前 AP 關閉、沒有有效 IMU 採集；需要當前接點近照進一步核對。


交接更新：以上初始化／USB 狀態按時間保留。最新 16:09 獨立診斷為 INITIAL_ID 無應答，六線位置已全部核對；現在 S3 板上是 BMI160_Bus_Check_v1，不是網關，未運行 AP／ESP-NOW。用戶沒有萬用表，已請組長接手；不再要求接點照片。最新狀態與交付見 [HANDOFF.md](HANDOFF.md)。
