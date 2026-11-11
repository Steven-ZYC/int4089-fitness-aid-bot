[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="物理警报模块--arduino-Arduino-2560"></a>

# Physical alarm module — Arduino

Independent actuator: D8 LED through a 220Ω resistor and D9 passive buzzer, switching on/off together.
Firmware entry: [Mega_Alarm_RX](Mega_Alarm_RX/Mega_Alarm_RX.ino).

Accepts the same abstract commands from PC USB Serial (115200 8N1) and ESP32 UART Serial1 (9600 8N1).
S3 GPIO17 → Arduino D19; common GND; Arduino D18 disconnected; RX internal pull-up disabled.
PC priority lasts 1.5 seconds; recommended heartbeat is 200ms. No valid command for 1.5 seconds turns outputs off.

See [communication design](../../docs/protocols/alarm-control.md) for the protocol, electrical/wiring limits, builds and PC examples.
See [2026-11-10 validation](../../docs/validation/2026-11-10-alarm-protocol.txt) for measurements.

Arduino does not receive raw IMU data or run pose recognition; it executes abstract alarm states only.
The code defaults to a passive buzzer. Change ACTIVE_BUZZER for an active low-current buzzer.
USB/UART command reception has been measured; sound and light still require on-site acceptance.
