[English](README.md) | [简体中文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

# FitCoach AI

目前原型由 **IMU 模块、视觉 AI 模块、物理警报模块**组成，由 Zhang Yancheng 统一维护。当前开发分支为 `Feat-Integration-Yancheng`，main 保留稳定集成版本。

## 当前界面与训练流程

统一入口是 `app/main.py`，将视觉 AI、IMU 数据、训练会话和设备校准整合到一个本地网页。界面使用自然的奶油色、浅蓝色与陶土橙；右上角支持简体中文、英语和香港繁体中文，语言偏好保存在本机，设备状态、动作反馈、图表与视频叠字随之切换。

![FitCoach AI 训练控制台](docs/assets/fitcoach-ui-zh-cn-16x9.png)

1920 × 1080（16:9）实际界面截图，更新于 2026-11-11。截图时摄像头未就绪、IMU 无实时样本、Arduino 执行状态未确认；计时为此前测试会话记录，未填充模拟实时数据。

- **训练控制台**：先预览动作，再配置硬件；顶部动作卡片及右侧动作库只展示前 4 个动作。下方依次是实时监测、3D 姿态、位置、IMU 数据及设备校准预览。
- **动作库**：完整保留深蹲、俯卧撑、前弓步、平板支撑、臀桥、鸟狗式共 6 个动作，每个动作都有带封面的视频、三阶段姿势示意和动作要点。点击卡片主体查看教学，点击箭头进入实时动作监测。
- **实时动作监测**：位于侧栏动作库下方，可选择动作并查看画面、计次、反馈及计时；与控制台共用同一视频流和训练会话。目前仅深蹲开放 AI，其他动作提供教学并标记待开放，不能启动 AI 识别。
- **3D 姿态与位置、IMU 数据曲线、设备与校准**：保留完整 IMU 观察、明确标记的历史 CSV 回放、连接配置、位置归零及静止 CSV 校准。位置积分会漂移，回放不代表实时硬件正常。

### 硬件组合与训练控制

Arduino 报警、ESP Camera 和 ESP IMU 可以独立启用／停用。开关控制电脑端采集或报警发送，不切断硬件供电；“已启用”和“已连接”分别显示。Arduino 单向 UART 无法确认实际声光执行，界面仅报告可测的中继状态。

可在不接 IMU 的情况下使用摄像头深蹲识别，也可只连接 IMU 观察数据。视觉报警需要启用 Arduino 报警并具备 CAM → S3 → Mega 的完整链路；关闭 IMU USB 采集不会关闭 S3 上的无线中继。没有实时摄像头图像时不能开始视觉训练。

点击“开始训练”才启动计次与视觉报警；暂停会冻结计时、保留已完成次数并停止计次与视觉报警，视频预览继续。结束后可重新开始。更换页面不会重新建立另一条采集链路。

使用详情见 [统一应用说明](app/UNIFIED_APP_zh_cn.md)。

## 当前数据流

```mermaid
flowchart LR
    CAM["ESP32-CAM / OV2640"] -->|"USB：JPEG 图像"| PC["电脑：姿态估计与动作规则"]
    PC -->|"USB：报警状态"| CAM
    CAM -->|"ESP-NOW：20 字节命令"| S3["ESP32-S3 N16R8"]
    S3 -->|"ESP-NOW：确认"| CAM
    IMU["BMI160"] -->|"I²C：GPIO4 / GPIO5"| S3
    S3 -->|"UART：GPIO17 → Mega D19"| MEGA["Mega 2560"]
    PC -. "可选：直接 USB 控制" .-> MEGA
    MEGA --> OUT["D8 LED + D9 蜂鸣器"]
```

**图像始终走 USB。ESP-NOW 只传报警状态和确认，不传图像。** Mega 只执行报警状态，不依赖视觉模型或 IMU 数据格式；IMU 暂时不可用时，视觉通信链路仍可独立运行。

## 当前固定配置与状态

| 项目 | 当前配置／验证范围 |
| --- | --- |
| CAM 图像 | 640×480 JPEG，quality=18，双 PSRAM 缓冲，LATEST 模式 |
| CAM USB | 921600、8N1；当前识别为 COM3，换电脑或重插后需重新确认 |
| S3 USB | 115200、8N1；当前 COM4，输出 IMU CSV 和诊断 |
| ESP-NOW | 信道 1、固定对端 MAC、20 字节状态／确认包，每 200ms 发送 |
| S3 → Mega | UART 9600、8N1；GPIO17 TX → D19 RX1；GND 共地；Mega D18 TX 不接 |
| 报警输出 | Mega D8 LED、D9 无源蜂鸣器，同开同关 |
| 视觉 AI | YOLOv8n-pose + 几何规则；统一应用目前仅开放深蹲 AI，其余动作仅教学 |
| 性能 | 纯 USB 实测 8.93 FPS；带 AI 页面观测约 9 FPS，随取景与光照变化 |
| 已验证 | 图像 CRC／解码、真实图像推理、无线开关／确认／命令过期关闭、既有 Mega USB/UART 协议 |
| 待完成 | BMI160 尚无稳定有效的实时样本，需检查接线与读取；S3 诊断后需确认集成固件及无线中继状态；Mega 接收与声光现场验收、真实动作准确性／阈值校准 |

保留目前效果，不继续提高串口速率、压缩程度或改变分辨率。最新相机参数以当前源码为准，性能记录见 [加速前](docs/validation/2026-11-10-camera-speed-before.json)、[加速后](docs/validation/2026-11-10-camera-speed-after.json)及[控制回归](docs/validation/2026-11-10-camera-speed-control-check.json)。

## 启动电脑端

在仓库根目录运行（使用本机已配置好的项目虚拟环境）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File app/run_pose.ps1 -CamPort COM3 -ImuPort COM4 -Action squat
```

打开 [FitCoach AI 控制台](http://127.0.0.1:8010)，确认端口和模块状态，在动作库选择深蹲，再点击“开始训练”。摄像头需全身入画并完成方向校正。训练运行且 Arduino 报警已启用时，不合格的完整深蹲会产生两秒视觉报警事件；实际声光效果仍取决于硬件链路。模型不会自动选择动作类别，规则分数不是模型置信度。

不连接 IMU 时使用 `-ImuPort ''` 跳过启动连接，或在界面关闭 ESP IMU。统一应用当前只接受 `-Action squat`；旧独立规则不等于统一页面已开放其他动作。

一个 CAM 串口同时只由一个进程使用；运行硬件测试或烧录前先停止检测程序。环境安装与直接运行命令见 [电脑应用说明](app/README.md)。

## 仓库目录

```text
app/                              # 电脑端入口 main.py、训练会话 workspace.py、网页 web/、IMU 服务与测试
firmware/
  usb-ai-bridge/                  # 当前 CAM / S3 集成固件及共享 ESP-NOW 实现
  alarm-mega/                     # 当前 Mega 报警固件
  imu-s3/                         # IMU 模块索引、旧独立 UART 测试
  esp32-camera/                   # BMI160 采集单一源码 + 历史相机／无线实验与证据
  arduino-uno/                    # 早期 Uno 任务说明
models/                           # 历史模型任务与未来训练说明，不是当前运行入口
tools/imu-position/               # 独立 IMU 接收、校准、回放、可视化工具
experiments/                      # 历史 ESP32 本地推理性能实验
docs/
  architecture/README.md          # 模块职责、代码依赖和线程／任务关系
  protocols/                     # USB 图像、ESP-NOW 状态、Mega 报警协议
  validation/                    # 实测指标与验收范围，历史记录不改写
  reference/                     # 概念参考图
AGENTS.md                         # 当前维护与分支规则
```

详细入口：[系统架构](docs/architecture/README.md)、[固件导航](firmware/README.md)、[文档导航](docs/README.md)。`ui-design-worktree/` 是独立 Git 工作树，未作为当前应用依赖或提交内容；虚拟环境、权重、图片和运行日志不入库。

## 维护与历史来源

- Zhang Yancheng 已接手所有模块，不再按原成员分工限制开发范围。
- 已普通 merge Yuankun 的 `Feat-Esp-Yuankun` 和 Haoyu 的 `Feat-PC-App-Haoyu`，保留原作者提交历史；`Feat-Arduino-Haoyu` 和独立 UI 分支尚未完整合入。
- 早期方案包括 ESP32 本地 AI、Wi-Fi MJPEG、ESP-NOW 分片传图；它们保留为实验来源，不代表当前部署路线。当前 AI 在电脑上运行，云端 HPC／GPU 仅是未来方向。
- 历史课程要求记录为 Uno，当前实际联调使用 Mega 2560；是否满足课程具体要求仍需课程方确认。
- 编译、烧录、串口确认、模型推理和现场声光验收分别记录；不能互相替代。原始图像保留本地忽略目录，不提交可识别人像或凭据。
