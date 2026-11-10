[English](espnow-alarm.md) | [简体中文 / 原文](espnow-alarm_zh_cn.md) | [繁體中文（香港）](espnow-alarm_zh_hk.md)

<a id="cam--s3-esp-now-报警协议"></a>

# CAM ↔ S3 ESP-NOW 報警協議

共享實現：[AlarmRadio.h](../../firmware/usb-ai-bridge/AlarmRadio.h)。本鏈路只發送報警狀態與應用確認，影像始終走 CAM USB。

<a id="无线配置与帧结构"></a>

## 無線配置與幀結構

Station 模式，不連接路由器；信道 1；固定目前 CAM / S3 的 MAC 為對端。更換板卡須核對 MAC 並重新編譯。目前無加密，屬於本機原型鏈路。

| 字段 | 位元組 | 用途 |
| --- | ---: | --- |
| magic | 4 | `0x41493438`，識別本協議 |
| boot | 4 | CAM 隨機啓動標識；ACK 回顯 |
| seq | 4 | CAM 遞增序號；ACK 回顯 |
| version | 1 | 目前為 1 |
| kind | 1 | 1=命令，2=應用 ACK |
| alarm | 1 | 0=關，1=開 |
| reserved | 1 | 必須為 0 |
| crc | 4 | 對前 16 位元組計算 CRC32 |

共 20 位元組，packed 結構；目前兩種 ESP 平台按小端表示整數。檢查來源 MAC、長度、magic、版本、保留位、狀態及 CRC。CRC 是差錯檢查，不是身分認證。

<a id="状态确认与超时"></a>

## 狀態、確認與超時

- CAM 每 200ms 發送目前有效狀態；電腦命令超過 1.2 秒未刷新時改發關閉。
- S3 接受有效命令後回顯 boot、seq、alarm，kind 改為 2，重新計算 CRC。
- 同一啓動標識下，重複／舊序號不刷新 S3 超時。新的啓動標識允許序號重新開始；這是原型會話區分，不是防重放安全機制。
- CAM 追蹤匹配目前啓動標識、已發送序號範圍的遞增 ACK；狀態診斷顯示最近 ACK 序號、狀態和時間。
- S3 超過 1.2 秒無有效命令時關閉；每 200ms 向 Mega UART 寫 `110`（開）或 `101`（關）。無線接收與轉發運行在獨立任務，BMI160 初始化失敗不阻塞這一任務。

**確認範圍到 S3 為止。** 單向 UART 無 Mega 回覆，不能用無線 ACK 證明燈或蜂鳴器已執行。Mega 自身保留來源／XOR 校驗、電腦 USB 優先和 1.5 秒超時，見 [報警協議](alarm-control_zh_hk.md)。

ESP-NOW 仍使用 2.4GHz 空口，每秒約 5 條命令及對應確認；目前減少的是無線數據量，不代表完全不影響其他無線設備。
