[English](alarm-control.md) | [简体中文 / 原文](alarm-control_zh_cn.md) | [繁體中文（香港）](alarm-control_zh_hk.md)

<a id="modular-alarm-controller-usb-pc-or-uart-esp32-s3"></a>

# 模組化警報控制器：USB 電腦或 UART ESP32-S3

維護者：Zhang Yancheng / Feat-Integration-Yancheng。Mega 2560 同時控制 D8 LED（串聯 220Ω）及 D9 無源蜂鳴器。低電流有源蜂鳴器須設定 ACTIVE_BUZZER=true；較高電流型號須使用驅動電路。

<a id="wiring"></a>

## 接線

- S3 GPIO17 TX → Mega D19 RX1；GND → GND。
- Mega D18 TX1 與 S3 GPIO18 RX 均不連接。
- 不要互接兩板的電源腳；各自使用 USB 供電。
- 改線時兩板均須斷電；運作時兩板均須供電。
- Mega RX 已停用內部上拉，避免將 5V 施加到 S3。
- 標稱 3.3V → 5V 邏輯在最差容差條件下未必可靠；目前接線通過 UART 接收測試，並非完整電氣認證。

<a id="protocol-v2"></a>

## 協議 v2

每幀為三個 ASCII 數字，後接 LF（亦接受 CRLF），依次為來源、警報狀態、校驗。不傳送逗號或方括號。
來源：0=電腦 USB Serial（115200 8N1），1=ESP Serial1（9600 8N1）。
狀態：0=兩項輸出均關閉，1=兩項輸出均開啟。
校驗：來源數值與狀態做 XOR，以 ASCII 0/1 編碼。

| 幀（後加 LF） | 意義 |
| --- | --- |
| 000 | 電腦關閉警報 |
| 011 | 電腦開啟警報 |
| 101 | ESP 關閉警報 |
| 110 | ESP 開啟警報 |

來源必須與實際輸入介面相符。來源、校驗、非二進制字元或長度錯誤均拒絕，不刷新控制逾時計時。未完成幀的位元組間隔超過 250ms 即失效，LF 為幀結束符。
XOR 位可偵測單一位元錯誤，不能偵測所有損壞，亦不是身分認證或有雜訊鏈路上 CRC 的替代品。

每個有效電腦幀令電腦優先控制 1500ms；期間忽略 ESP 幀。每 200ms 傳送一次即可持續控制。電腦優先期結束後，ESP 可用下一個有效幀接管。1500ms 沒有被接受的幀時關閉輸出；啟動亦預設關閉。這並非經安全認證的行為。
USB 只在命令被套用後回報 ACK <frame>；拒絕時回報 ERR FORMAT/SOURCE/CHECKSUM，失去控制時回報 TIMEOUT outputs=OFF。UART 沒有回傳線或確認。

<a id="pc-usage"></a>

## 電腦使用方式

Arduino Serial Monitor 設 115200、換行結尾，傳送 011 開啟或 000 關閉。單一命令維持 1.5 秒優先期，重複傳送可維持控制。開啟 USB 可能重設 Mega，請等候約 2 秒再傳送。
使用 pyserial 的 Python 範例；按實際情況更改連接埠：

```python
import serial, time
with serial.Serial('COM3', 115200, timeout=0.1) as port:
    time.sleep(2)
    for _ in range(25):  # Hold ON for five seconds
        port.write(b'011\n')
        time.sleep(0.2)
        print(port.read_all().decode(errors='replace'), end='')
    port.write(b'000\n')
```

這使警報執行器與 IMU 採集／判定演算法解耦：兩種上位模組都輸出相同的抽象警報狀態。來源控制權與心跳仍屬介面約定。Mega 不解析 IMU 樣本，也不判斷姿勢是否正確。

S3_UART_TX_Test 是刻意設計的三秒關／開測試，並非 IMU 邏輯。燒錄會取代正在執行的 IMU 韌體；原 BMI160 源碼保留。舊 ALARM,0 / ALARM,1 命令已不支援，兩板均須使用 v2。

<a id="validation"></a>

## 驗證

2026-11-10 初版 v1：兩板燒錄完成，觀察到 Mega 實際 UART 接收。
v2 燒錄／測試後的驗證記錄為 ../validation/2026-11-10-alarm-protocol.txt。
LED 是否亮起、蜂鳴器是否發聲及實體拔線行為均須現場觀察。本階段未進行分支合併。

<a id="source-locations-and-builds"></a>

## 源碼位置與編譯

- Mega：`firmware/alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino`
- S3 測試發送端：`firmware/imu-s3/S3_UART_TX_Test/S3_UART_TX_Test.ino`
- BMI160 採集：`firmware/esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino`（歷史路徑，未變更）。

```powershell
arduino-cli compile --fqbn arduino:avr:mega firmware/alarm-mega/Mega_Alarm_RX
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200 firmware/imu-s3/S3_UART_TX_Test
```

確認連接埠身分後，Mega 可加 `--upload --port COM3`，S3 可加 `--upload --port COM4`；連接埠編號可能改變。
