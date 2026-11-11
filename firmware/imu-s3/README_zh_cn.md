# IMU 模块 — ESP32-S3 N16R8 + BMI160

## 当前部署

当前运行 [S3_IMU_Alarm_Bridge](../usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino)。它初始化既有 BMI160 六轴采集实现，同时用独立任务接收 CAM 的 ESP-NOW 报警状态，并向 Arduino 转发 UART 命令。IMU 与视觉结果不做融合，尚无 IMU 自动报警判断。

- BMI160：SDA=GPIO4，SCL=GPIO5，I²C 自动探测 0x68 / 0x69。
- S3 → Arduino：GPIO17 TX → D19 RX1，GND 共地；GPIO18 和 Arduino TX 不接。
- USB：115200，输出采集 CSV 与以 `#` 开头的诊断。
- **当前故障**：两个地址均无应答；用户已确认仍接着 IMU，将断电检查。无线报警任务独立运行。

## 保留的源码入口

| 实现 | 用途 |
| --- | --- |
| [BMI160_SixAxis](../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) | 采集单一源码，被当前 S3 集成固件复用，也可单独烧录 |
| [BMI160_Bus_Check](../esp32-camera/BMI160_Bus_Check/BMI160_Bus_Check.ino) | 独立总线诊断 |
| [S3_UART_TX_Test](S3_UART_TX_Test/S3_UART_TX_Test.ino) | 历史三秒开关测试，不读取 IMU |

[历史成功复现](../esp32-camera/YANCHENG_BMI160_REPRO.md)曾验证本机 0x69，不代表当前接线已恢复。保留原路径以保护脚本和证据引用。

详细说明：[当前集成固件](../usb-ai-bridge/README.md)、[系统架构](../../docs/architecture/README.md)、[Arduino 接口](../../docs/protocols/alarm-control.md)。
