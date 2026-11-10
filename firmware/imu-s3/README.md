# IMU 模块 — ESP32-S3 N16R8 + BMI160

当前硬件：用户提供的双 USB ESP32-S3-WROOM-1 N16R8；BMI160 SDA=GPIO4、SCL=GPIO5。
已有本机证据地址 0x69，代码自动探测 0x68 / 0x69；不推断其他板的地址。

## 两个独立固件入口

| 固件 | 路径 | 行为 |
| --- | --- | --- |
| 六轴采集（已提交的既有实现） | [BMI160_SixAxis](../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) | USB 输出原始／换算六轴 CSV；没有报警 UART 逻辑 |
| 通信测试（本次基线） | [S3_UART_TX_Test](S3_UART_TX_Test/S3_UART_TX_Test.ino) | GPIO17 每 200ms 发三位报警帧，三秒关／三秒开；不采集 IMU |

**两者是可替换的固件，不是同时运行的任务。当前板上烧录的是通信测试。**
原始采集源码保留历史目录以避免破坏脚本、复现记录及后续分支合并。
IMU 诊断入口：[BMI160_Bus_Check](../esp32-camera/BMI160_Bus_Check/BMI160_Bus_Check.ino)。
历史采集／构建与烧录证据：[复现记录](../esp32-camera/YANCHENG_BMI160_REPRO.md)。

通信接口：GPIO17 TX → Mega D19 RX1，GND 共地；GPIO18 悬空，Mega TX 不接。
协议与编译设置：[通信设计](../../docs/protocols/alarm-control.md)。
下一步：将采集与判定逻辑接入统一报警接口，定义阈值／标定及错误处理后实测。
视觉 ESP32-CAM 只连接电脑，不参与本链路。
