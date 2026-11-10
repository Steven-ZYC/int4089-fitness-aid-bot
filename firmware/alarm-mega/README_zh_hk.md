[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="物理警报模块--arduino-mega-2560"></a>

# 物理警報模組 — Arduino Mega 2560

獨立報警執行器：D8 LED（串聯 220Ω），D9 無源蜂鳴器，同開同關。
韌體入口：[Mega_Alarm_RX](Mega_Alarm_RX/Mega_Alarm_RX.ino)。

接受電腦 USB Serial（115200 8N1）與 ESP32 UART Serial1（9600 8N1）的統一命令。
S3 GPIO17 → Mega D19；GND 共地；Mega D18 不接；RX 內部上拉關閉。
電腦優先 1.5 秒，心跳建議 200ms；無有效命令 1.5 秒則關閉。

協議、接線電氣限制、編譯及電腦示例見 [通信設計](../../docs/protocols/alarm-control_zh_hk.md)。
實測記錄見 [2026-11-10 驗證](../../docs/validation/2026-11-10-alarm-protocol.txt)。
Mega 不接收 IMU 原始數據、不運行姿態識別；僅執行抽象報警狀態。
程式碼預設無源蜂鳴器；有源低電流蜂鳴器需修改 ACTIVE_BUZZER。
目前已有 USB / UART 命令接收實測，聲音和燈光仍需現場驗收。
