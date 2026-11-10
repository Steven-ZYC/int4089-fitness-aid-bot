# 第 2 步實測：S3 與 BMI160 身份通訊通過

測試日期：2026-11-03（Asia/Shanghai）。負責人：Dong Yuankun。分支：`Feat-Esp-Yuankun`。本人分支測試記錄；交付邊界見 [HANDOFF.md](HANDOFF.md)。

**結果：S3 經 GPIO4／GPIO5 的 I²C，在位址 0x68 連續兩次讀到 CHIP_ID 0xD1。第 2 步完成；六軸採樣、校準及實際採樣率留待第 3 步。**

## 接線與工具

收到四張接線照片，S3 端可見接點位置符合方案；因 BMI160 標籤及部分線路被遮擋，再由用戶於斷電時逐條核對，並明確回覆六條已確認。接法見 [BMI160_WIRING.md](BMI160_WIRING.md)：

| S3 | BMI160 |
| --- | --- |
| 3V3 | 3v3 |
| 另一個 3V3 | CS |
| GND | GND |
| 另一個 GND | SA0 |
| GPIO4 | SDA |
| GPIO5 | SCL |

VIN 及另一排 OCS／INT2／INT1／SCX／SDX 留空。只有 S3 USB 供電；未量測供電電壓或上拉電阻的實際數值。

| 項目 | 本次設定／證據 |
| --- | --- |
| 電腦到 S3 | CH340 USB 串口 COM9，115200 baud |
| S3 到 BMI160 | I²C，SDA GPIO4、SCL GPIO5，100,000 Hz 時鐘 |
| 板卡／記憶體設定 | ESP32S3 Dev Module、16MB Flash、OPI PSRAM、USB CDC On Boot Disabled |
| 程式 | [BMI160_ID_Check.ino](BMI160_ID_Check/BMI160_ID_Check.ino)，只讀身份寄存器，沒有啟動六軸採樣 |
| 已有編譯 | Arduino CLI 1.5.1／esp32 core 3.3.12；程式 306,731 bytes，靜態變數 23,500 bytes |
| 上傳前確認 | esptool 5.3.1 在 COM9 識別 ESP32-S3 QFN56 revision v0.2，16MB Flash、8MB PSRAM |
| 上傳 | 成功；bootloader、分區、應用等寫入雜湊均通過，重啟後讀取串口 |
| 讀取 | 取得兩個完整週期報告，均符合 0x68／0xD1，0x69 無裝置回應 |

本次曾先偵測到原生 USB 的 COM10（VID 303A／PID 1001）。改用同板另一個 Type-C 接口後，Windows 識別 CH340 COM9；此後所有上傳和串口觀察使用 COM9。重新插拔後仍需確認實際端口。

編譯／上傳使用的 FQBN：

```text
esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200
```

源碼 SHA256：`4C9A1EA2ED0C49118CD632D4BE0CA457B5880FD8A7915949D05D374897577AE7`。

應用 `.ino.bin`：306,880 bytes，SHA256：`CF95D27BB7DAE83DCAC19E39F8DBC0524FFD7E8468984EC94C09FFFDBB24809B`。

## 實際串口輸出

以下是實際收到的兩個完整週期；不是示例或模擬資料：

```text
=== BMI160_ID_CHECK ===
SDA=GPIO4 SCL=GPIO5 I2C_HZ=100000
ACK address=0x68 CHIP_ID=0xD1
NO_ACK address=0x69 wire_status=2
PASS: one expected BMI160 identity found. Six-axis acquisition is not tested.
=== BMI160_ID_CHECK ===
SDA=GPIO4 SCL=GPIO5 I2C_HZ=100000
ACK address=0x68 CHIP_ID=0xD1
NO_ACK address=0x69 wire_status=2
PASS: one expected BMI160 identity found. Six-axis acquisition is not tested.
```

## 你剛剛完成了甚麼

通訊有兩段：電腦透過 USB 串口替 S3 上傳程式、查看文字；S3 執行程式後，透過 I²C 與 BMI160 通訊。SDA 傳資料，SCL 由 S3 提供時鐘，依據見 [樂鑫 Arduino I²C 文件](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html)。

`0x68` 是感測器在這條 I²C 線路上的裝置位址，像門牌號碼。S3 指定讀取感測器內的 `0x00` 寄存器（一個有編號的資料格），感測器回覆 `0xD1`，與 [Bosch 官方型號代碼定義](https://github.com/boschsensortec/BMI160_SensorAPI/blob/master/bmi160_defs.h) 相符。這個型號碼由同型號晶片共用，不是這一顆的獨有序號。

SA0 接地時本方案使用 0x68，於是 0x69 顯示 NO_ACK 是本次單顆接法的預期結果。I²C 的 100,000 Hz 是通訊時鐘；每約 3 秒印一次的是身份報告，兩者都不是六軸資料的採樣率。

目前通過的是基本供電條件下的讀取與型號代碼核對；沒有測試運動量測精度、長時間穩定性、六軸採樣或全系統鏈路。

## 在 Arduino IDE 親自觀察

本次第 2 步完成時 S3 運行 BMI160_ID_Check：選 COM9，打開 Serial Monitor，設 115200 baud；約每 3 秒會出現上述報告。查看文字不需要再次點 Upload；上傳其他草圖會替換程式。

後續已完成 `ax, ay, az, gx, gy, gz` 靜止／自由轉動記錄，S3 目前運行 BMI160_SixAxis_v2，不再是本頁的身份草圖；實測及未完成項目見 [六軸結果](BMI160_SIX_AXIS_RESULT.md)。統一進度見 [PROGRESS.md](PROGRESS.md)。
