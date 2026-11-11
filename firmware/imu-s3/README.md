[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="imu-模块--esp32-s3-n16r8--bmi160"></a>

# IMU module — ESP32-S3 N16R8 + BMI160

<a id="当前部署"></a>

## Active deployment

The board runs [S3_IMU_Alarm_Bridge](../usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino). It initializes the existing BMI160 six-axis acquisition and independently receives CAM ESP-NOW alarm states and relays UART commands to Arduino. IMU and vision results are not fused; automatic IMU alarm decisions are not implemented.

- BMI160: SDA=GPIO4, SCL=GPIO5; automatic I²C detection at 0x68/0x69.
- S3 → Arduino: GPIO17 TX → D19 RX1, common GND; GPIO18 and Arduino TX disconnected.
- USB: 115200; acquisition CSV and diagnostics prefixed with `#`.
- **Current fault**: neither address responds. The user confirmed the IMU is still wired and will inspect with power off. Wireless alarms operate independently.

<a id="保留的源码入口"></a>

## Preserved source entry points

| Implementation | Purpose |
| --- | --- |
| [BMI160_SixAxis](../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) | Single acquisition implementation reused by integrated S3 firmware; also independently flashable |
| [BMI160_Bus_Check](../esp32-camera/BMI160_Bus_Check/BMI160_Bus_Check.ino) | Independent bus diagnostics |
| [S3_UART_TX_Test](S3_UART_TX_Test/S3_UART_TX_Test.ino) | Historical three-second ON/OFF test without IMU readings |

The [historical successful reproduction](../esp32-camera/YANCHENG_BMI160_REPRO.md) verified local address 0x69; this does not establish that current wiring has recovered. Original paths preserve script and evidence references.

Details: [current integrated firmware](../usb-ai-bridge/README.md), [system architecture](../../docs/architecture/README.md), [Arduino interface](../../docs/protocols/alarm-control.md).
