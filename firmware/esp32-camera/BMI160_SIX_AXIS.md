# 第 3 步：讀懂並記錄 BMI160 六軸資料

更新日期：2026-11-03。負責人：Dong Yuankun。分支：`Feat-Esp-Yuankun`。本人分支測試記錄；交付邊界見 [HANDOFF.md](HANDOFF.md)。

**第 3 步 IMU 基礎採集驗收已完成。** 除原有約 49.73 Hz 基線外，照片參考下的加速度方向、順時針主要負 Z 及電腦端獨立零偏驗證已有證據；精密比例／溫度等校準另列後續，見 [方向與校準續記](BMI160_AXES_CALIBRATION.md)。最初基線見 [六軸實測](BMI160_SIX_AXIS_RESULT.md)，第 2 步身份證據見 [BMI160_TEST_RESULT.md](BMI160_TEST_RESULT.md)。

## 你在做甚麼

BMI160 是量測運動的器件；S3 透過 I²C 讀取它，把數字經 USB 送到電腦。將來這些運動資訊會和相機影像一起交給電腦分析，目前先讓一條資料鏈路可靠運作。

| 輸出 | 意義 | 這一步如何看 |
| --- | --- | --- |
| ax、ay、az | 感測器三個方向的加速度量測，含重力分量；這裡單位是 g | 靜止時三個值合起來的大小接近 1 g，傾斜時重力分配到各軸的比例會變 |
| gx、gy、gz | 繞三個方向的轉動速度；單位是 °/s | 靜止時接近零，轉動時對應軸會明顯改變；停止轉動後應回到靜止附近 |

例如 90 °/s 是「每秒轉 90 度的速度」，不是「目前角度是 90 度」。單顆 IMU 的軸屬於模組本身，還需要實物正負方向測試及人體固定位置定義；不能直接當成膝蓋角度或全身骨架。

## 這次使用的程式

- S3 草圖：[BMI160_SixAxis.ino](BMI160_SixAxis/BMI160_SixAxis.ino)，只需板卡核心隨附的 Wire，無額外 Arduino 感測器函式庫。
- 電腦記錄：[capture_bmi160.ps1](capture_bmi160.ps1)，保存 CSV、診斷文字和 JSON 統計；預設輸出在 Git 忽略的 `captures/bmi160/`。
- 六條接線沿用 [BMI160_WIRING.md](BMI160_WIRING.md)。上傳前關閉串口監視器；COM9 是本機已確認的 CH340 通道，重新插拔後仍需核對。
- 板卡設定沿用 S3 自檢：ESP32S3 Dev Module、16MB、OPI PSRAM、USB CDC On Boot Disabled、115200 baud。

草圖先確認 0x68／0xD1，重設暫存設定，分別喚醒加速度計及陀螺儀，再設定量程與資料率。它會讀回設定／電源狀態，遇到身份不符、設定讀回異常、連續讀取失敗或一秒沒有新資料時停止輸出樣本並顯示 FATAL。

| 項目 | 設定 |
| --- | --- |
| I²C | GPIO4 SDA、GPIO5 SCL、100 kHz |
| 加速度 | ±4 g；raw ÷ 8192 → g |
| 角速度 | ±500 °/s；raw ÷ 65.6 → °/s |
| 兩個感測器 ODR | 目標各 50 Hz，normal bandwidth；實際讀取率須實測 |
| 設定讀回 | ACC_CONF 0x27、ACC_RANGE 0x05、GYR_CONF 0x27、GYR_RANGE 0x02；PMU_STATUS 低六位 0x14 |
| 讀取策略 | 輪詢兩個 data-ready 狀態位，兩者都有新資料時，一次連讀六軸與感測器時鐘 |
| 校準 | 保留原始值，`calibrated=NO`；沒有寫入永久補償或自動扣除重力 |

寄存器、量程和單位換算依據：[Bosch BMI160 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi160-ds000.pdf)，尤其第 52–61 頁及 CMD 章節；常數交叉核對 [Bosch 官方 SensorAPI](https://github.com/boschsensortec/BMI160_SensorAPI/blob/master/bmi160_defs.h)。本草圖為本項目自行編寫的最小讀取程式。

## 輸出欄位

每筆 CSV 共有 15 欄：

```text
sample_seq,t_read_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps
```

- `sample_seq`：S3 成功讀取後遞增的序號，重新開機會歸零；電腦可用它檢查本次串流的缺行或重啟。
- `t_read_us`：S3 開機後，開始這次 I²C 資料讀取前的微秒時間；不是準確的感測器量測時刻，也不是電腦時鐘。
- `sensor_ticks`：連讀得到的 BMI160 24-bit 本地時鐘原始值，會回繞；它屬於感測器時鐘域，不直接等於 S3 的微秒或相機時間戳。
- 六個 `raw`：帶正負號的 16-bit 原始數字。
- 六個換算欄位：前三個是 g、後三個是 °/s。
- 以 `#` 開頭的是設定／統計／錯誤說明；記錄器會分開處理，CSV 只保留資料行。

每約 5 秒重印設定與一段時間內的讀取率。v2 使用 2048-byte 串口發送緩衝，讓診斷文字排隊傳出。50 Hz 是目標；能否持續收到足量且連續的資料，需要以 CSV 中的時間和序號核對。

本版輪詢最新值，尚未使用 FIFO；成功讀取的序號連續不代表能證明晶片內部一筆也未覆蓋。接收工具會列出讀取間隔超過 30 ms 的次數，作為時序排查線索，不能直接換算成精確的晶片丟樣數。

## 先做靜止，再做轉動

1. **靜止基線**：把模組所在麵包板穩放在桌上，記錄至少 15 秒。觀察加速度合量、各軸波動、角速度平均偏移與實際讀取率。
2. **轉動反應**：輕拿 BMI160 所在麵包板，在杜邦線有餘量的範圍內，緩慢前後／左右傾斜及轉動，途中停一下。記錄哪個方向、哪段時間，觀察各軸與停止後的變化。
3. **軸向與校準**：再逐軸確認正負方向。靜止時陀螺儀均值可作本次偏置候選；須比較轉動前後及暖機狀態，確認穩定後才討論補償。加速度三軸的靜止值含重力，不能把整組均值直接全部扣掉。

電腦重做一段記錄的方式（先進入本目錄，Windows PowerShell）：

```powershell
.\capture_bmi160.ps1 -Port COM9 -Seconds 15 -Label stationary
```

`Label` 只是用來描述你當時做的動作；程式不會因為檔名寫 stationary 就認定真的靜止或已校準。JSON 的 `transport_check_passed` 只檢查設定、解析、序號、時間連續性，以及 45–55 Hz 的原型讀取率範圍，不是量測精度認證。

後續修正：記錄工具現在先等第一筆可解析資料，再開始要求的秒數；啟動等待最多 8 秒，JSON 分別記錄 `port_open_utc` 和 `capture_start_utc`。過往證據檔維持原始欄位語義，詳見 [續記](BMI160_AXES_CALIBRATION.md)。

統一進度見 [PROGRESS.md](PROGRESS.md)。完整第 3 步仍需保留實際數據、軸向／單位／量程／時間的定義、靜止與轉動證據，以及偏置處理方案。
