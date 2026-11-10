# 物理警报模块 — Arduino Mega 2560

独立报警执行器：D8 LED（串联 220Ω），D9 无源蜂鸣器，同开同关。
固件入口：[Mega_Alarm_RX](Mega_Alarm_RX/Mega_Alarm_RX.ino)。

接受电脑 USB Serial（115200 8N1）与 ESP32 UART Serial1（9600 8N1）的统一命令。
S3 GPIO17 → Mega D19；GND 共地；Mega D18 不接；RX 内部上拉关闭。
电脑优先 1.5 秒，心跳建议 200ms；无有效命令 1.5 秒则关闭。

协议、接线电气限制、编译及电脑示例见 [通信设计](../../docs/protocols/alarm-control.md)。
实测记录见 [2026-11-10 验证](../../docs/validation/2026-11-10-alarm-protocol.txt)。
Mega 不接收 IMU 原始数据、不运行姿态识别；仅执行抽象报警状态。
代码默认无源蜂鸣器；有源低电流蜂鸣器需修改 ACTIVE_BUZZER。
当前已有 USB / UART 命令接收实测，声音和灯光仍需现场验收。
