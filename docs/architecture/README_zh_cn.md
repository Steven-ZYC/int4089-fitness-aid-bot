# 系统架构与代码导航

## 三个逻辑模块

| 模块 | 输入 | 输出 | 代码入口 |
| --- | --- | --- | --- |
| 视觉 AI | CAM 的 USB JPEG 图像 | 关键点、动作阶段、计次、违规项、报警状态 | [pose_app.py](../../app/pose_app.py)、[pose_engine.py](../../app/pose_engine.py)、[form_rules.py](../../app/form_rules.py) |
| IMU | BMI160 六轴数据；无线接收视觉报警状态 | USB IMU CSV；发往 Mega 的报警帧 | [S3 集成固件](../../firmware/usb-ai-bridge/S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino)、[BMI160 采集实现](../../firmware/esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino) |
| 物理警报 | S3 UART 或电脑直连 USB 的报警帧 | D8 LED、D9 蜂鸣器同开同关 | [Mega 固件](../../firmware/alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino) |

S3 同时承担 IMU 采集节点和无线报警转发节点，但两项任务独立。当前无线结果不是 IMU 判定结果；尚未实现 IMU 与视觉融合或 IMU 自动报警。

## 电脑端文件职责

| 文件 | 职责 |
| --- | --- |
| `app/pose_app.py` | 当前应用入口；推理线程、结果状态、网页与 HTTP 服务；不合格完整动作触发短时报警 |
| `app/pose_engine.py` | YOLOv8n-pose 模型，取最大人体框和 17 个关键点 |
| `app/form_rules.py` | 深蹲／俯卧撑角度、阶段状态机、计次和违规规则 |
| `app/sources.py` | 选择 `serial://`、本地摄像头或 HTTP MJPEG 输入 |
| `app/serial_camera.py` | USB 串口的唯一读写者；接收 JPEG、校验 CRC／帧尾、缓存最新帧、回传报警和读取无线确认 |
| `app/run_pose.ps1` | 本机固定环境的启动入口；参数选择串口、动作和网页端口 |
| `app/test_rules.py` | 原动作规则合成关键点测试 |
| `app/test_serial_camera.py` | 合成 JPEG 的正常、损坏 CRC、错误帧尾测试 |
| `app/check_usb_bridge.py` | 真实双板硬件测试；短暂开启报警，分别记录无线与 IMU 结果 |
| `app/benchmark_usb.py` | 图像传输分阶段测速，只保存指标 |
| `app/app.py`、`detector.py` | 旧人体检测页面；不是当前动作规范判定主入口 |
| `app/find_camera.py`、`app/firmware/esp32_cam_stream/` | 历史 Wi-Fi MJPEG 路线，当前不使用 |

电脑内只有 `SerialCameraSource` 工作线程访问 CAM 串口。它批量发送报警／状态／拍照请求，按长度读取二进制图像并校验后缓存最新帧。推理线程只读取新鲜帧并回写短期有效的报警状态；HTTP 线程读取结果缓存供网页显示。模型权重和抓帧不提交。

## 固件依赖与运行任务

```text
Cam_USB_Bridge.ino
  ├─ OV2640 相机：VGA / JPEG18 / 双缓冲 LATEST
  ├─ USB：图像、电脑命令和诊断
  └─ AlarmRadio.h：独立任务周期发送状态并处理 S3 确认

S3_IMU_Alarm_Bridge.ino
  ├─ 引入既有 BMI160_SixAxis.ino：初始化及六轴采集
  └─ AlarmRadio.h：独立任务接收状态、确认并周期写入 Serial1

Mega_Alarm_RX.ino
  ├─ USB / Serial1 各自解析三位命令
  └─ 来源／XOR 检查、电脑优先期、输出控制与超时
```

BMI160 源码仍保留在 `firmware/esp32-camera/`，S3 集成固件通过相对包含复用，避免出现两份采集实现。保留原路径也确保历史 PowerShell 脚本和证据可追溯。编译时应保留仓库相对目录；不能只复制一个 `.ino` 去编译。

## 接口边界

1. **CAM ↔ 电脑 USB**：921600 8N1，JPEG 与文本命令共用同一串口。图像不走无线。[USB 图像协议](../protocols/usb-camera.md)
2. **CAM ↔ S3 ESP-NOW**：信道 1，固定对端 MAC，20 字节状态／确认包；不传图像。[无线报警协议](../protocols/espnow-alarm.md)
3. **S3 → Mega UART**：9600 8N1，GPIO17 TX → D19 RX1，GND 共地，反向 TX 不接。[Mega 报警协议](../protocols/alarm-control.md)
4. **BMI160 → S3 I²C**：GPIO4 SDA、GPIO5 SCL，自动探测 0x68 / 0x69；当前无应答，待接线检查。

协议帧隔离了视觉分析与执行器。无线确认到 S3 为止，不能证明 Mega 接收到命令或灯／蜂鸣器执行成功。端到端确认尚未实现。

## 当前参数与验证

当前固定为 VGA、JPEG18、双缓冲、921600；本轮整理不修改这些参数。图像采集时接受最多 200ms 帧龄，USB／推理／显示还会增加延迟。命令新鲜度与超时见各协议文档。

- USB 加速后：268 帧／30 秒，8.93 FPS，未见 CRC／解码错误。
- AI 页面：约 9 FPS，随光照和画面复杂度变化；不是动作准确率指标。
- 无线：开／关／电脑命令过期测试通过。
- IMU：目前 0x68 / 0x69 均无应答；并发 IMU 验收仍失败。
- 现场待验收：真实完整动作、Mega 执行效果、物理断线／掉电。

记录入口：[文档索引](../README.md)。历史单板与分片图像实验放在 `firmware/esp32-camera/`；独立 UI 工作树尚未合入当前页面。
