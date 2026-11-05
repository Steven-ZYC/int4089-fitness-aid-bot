# INT4089 Group Project — AI Fitness Form Coach

面向健身初学者的**双 ESP32 + Arduino Uno + IMU + 外部 AI 分析**课程原型：采集图像和运动数据，在计算平台分析健身动作，并通过 LED／蜂鸣器提供姿势反馈。

> **2026-11-05 Yuankun 交接：** 已完成成果、來源、測試證據與 IMU 未解決問題集中在 [交接文件](firmware/esp32-camera/HANDOFF.md)。Yuankun 沒有萬用表，已請組長接手後續硬件排查；第 5 步及完整系統仍未完成。

> [!NOTE]
> **最新方案（2026-10-30，Dr Davy Ng consultation 后）**
>
> - 当前为 **prototype**；AI 模型的训练、推理和姿势判断在**电脑**完成。
> - 未来可将 AI 服务迁移到**云端 HPC / GPU**；目前未部署。
> - 两块 ESP32 分别负责**摄像头采集**和**IMU 采集／联网网关**，Arduino Uno 继续负责本地 LED／蜂鸣器等控制。

> [!IMPORTANT]
>
> - **每人只在自己的工作分支修改并提交；默认不要在 `main` 开发。**
> - 组员与编程 agent 开始任务前应先阅读本 README 和 [AGENTS.md](AGENTS.md)；所有未完成事项须明确标记。

> [!TIP]
>
> - [项目方案与架构](#项目方案与架构)
> - [成员与分工](#成员与分工)
> - [给两位同学及其 agent 的最短指引](#给两位同学及其-agent-的最短指引)
> - [打开自己的分支](#打开自己的分支)
> - [当前进展/To-do list](#当前进展to-do-list)

GitHub：[Steven-ZYC/int4089-fitness-aid-bot](https://github.com/Steven-ZYC/int4089-fitness-aid-bot)（私有仓库；组员须先获得访问权限）。

## 项目背景

针对健身新手缺乏即时指导的问题，本项目尝试在健身动作过程中识别姿势异常，向用户提供低成本、直观的提醒。课程要求以 **Arduino Uno** 参与传感器与执行器控制；ESP32 和电脑作为协作模块。

### 为什么改变方案？

早期尝试直接在 ESP32-CAM 上运行 AI 模型，但既有测试表明该方式性能不足，不适合作为当前实时动作分析路径：

| 已测项目（旧 ESP32-CAM 本地推理方案） | 测试结果 |
| --- | ---: |
| PSRAM | 2 MB |
| 平均纯模型推理耗时 | 15.126 s/frame |
| 纯推理速度 | 0.0661 FPS |
| 包含采集与前／后处理的速度 | 0.0655 FPS |

以上是旧方案实测，不是新架构的吞吐量。consultation 后，原型改为图像 + IMU 采集、电脑端 AI 处理；ESP32-S3 板上推理和 RDK X5 不再是本阶段主线。

## 项目方案与架构

### 当前计划：两个 ESP32、一个 IMU、Arduino Uno 和电脑

| 模块 | 职责 | 当前定位 |
| --- | --- | --- |
| **ESP32-CAM（Camera Node）** | 获取健身图像／图像帧，并与 **Arduino Uno** 建立硬件连接 | 图像采集端；**不负责运行姿势识别 AI** |
| **ESP32-S3 N16R8（Main ESP / Gateway）** | 连接 **Bosch BMI-series IMU**，采集运动数据，统筹与计算机的网络通信 | 两块 ESP32 中的主 ESP；不承担主要 AI 推理 |
| **Bosch BMI-series IMU** | 提供加速度／角速度等运动信息，辅助姿势分析 | consultation 后加入的传感器 |
| **Arduino Uno** | 保留课程要求的控制职责，最终控制 LED、蜂鸣器等提醒装置 | 与 ESP32-CAM 连接 |
| **电脑（Prototype AI Platform）** | 接收两路信息，负责数据预处理、AI 推理、姿势判断、结果回传；用于模型开发与测试 | **当前首选计算平台** |
| **Cloud HPC / GPU Server** | 将来替代电脑承载 AI 服务，供进一步扩展和部署 | **未来方向，尚未启动，估计只在ppt中介绍** |

Yuankun 的 ESP32-S3-N16R8 已完成基本自检，在 COM9 读回 16MB Flash／8MB PSRAM 并成功运行诊断程序，见 [S3 实测结果](firmware/esp32-camera/S3_TEST_RESULT.md)。现有蓝色 GY-801 三块及紫色 BMI160 模组一块，第一版使用紫色 BMI160。2026-11-03 已完成 0x68／0xD1 身份通讯、约 49.73 Hz 六轴记录、照片参考下的加速度方向、顺时针主要负 Z 及电脑端独立零偏验证；见 [方向与零偏结果](firmware/esp32-camera/BMI160_AXES_CALIBRATION.md)。CAM 已在 COM11 重连，读回 ESP32-D0WD-V3、4MB Flash、2MB PSRAM、OV2640；新自检固件 3 张 640×480 JPEG 通过新画面时间门槛、长度／序号及解码，其中一张为桌面物件，见 [CAM 重测](firmware/esp32-camera/CAM_RECHECK_RESULT.md)。ESP-NOW 双向文字各 20／20 次及两个漏 ACK 重试案例已通过，平均往返约 5.043／4.075 ms，见 [双板文字结果](firmware/esp32-camera/DUAL_ESP_TEXT_RESULT.md)。11-04 三个单张图片案例均通过三端 SHA256、640×480 解码和反向 TEST_ONLY；正常零重试，受控漏 ACK／坏包各重试一次，见 [图片实测](firmware/esp32-camera/DUAL_ESP_IMAGE_RESULT.md)。01:04 合并版 Normal 并发检查通过：496 笔、49.7338 Hz、最大间隔 21.946 ms，收图／USB 导出时均有 IMU 数据，见 [并发实测](firmware/esp32-camera/IMAGE_IMU_RESULT.md)。以上为 11-04 及之前的历史成果；当时 S3 运行合并版、CAM 保留图片版。最新板上版本与未完成项目见下方 11-05 更新及交接文件。见 [IMU 选型记录](firmware/esp32-camera/IMU_SELECTION.md)。

**11-05 本人分支更新：** 专用 Wi-Fi／TCP 控制及空闲重连通过，见 [网络实测](firmware/esp32-camera/WIFI_GATEWAY_RESULT.md)。之后 IMU 初始化故障；原成功映像在今天重试也未恢复。用户已依正面位置表确认 VIN 留空、六线全部吻合。16:09 已上板独立 BMI160_Bus_Check_v1 并读回版本：0x68／0x69 各三次未应答，停在 INITIAL_ID，未执行后续配置写入或取得六轴。见 [分段诊断](firmware/esp32-camera/BMI160_BUS_DIAG.md) 与 [恢复排查](firmware/esp32-camera/BMI160_RECOVERY.md)。原因未确认，下一步量实际供电／接点，或使用现有 GY-801 做独立通信对照；第 5 步先恢复 IMU。网关源码与 11-04 原成功映像保留，当前 S3 未运行网关；照片／IMU 网络验收尚未完成。

### 计划数据流

```mermaid
flowchart LR
    USER["用户健身动作"] --> CAM["ESP32-CAM<br/>图像采集"]
    IMU["Bosch BMI-series IMU"] --> MASTER["ESP32-S3 N16R8<br/>主 ESP · 运动采集／联网"]
    CAM -->|"图像数据"| MASTER
    MASTER -->|"图像 + IMU 数据"| PC["电脑<br/>AI 分析与姿势判定"]
    PC -. "姿势结果" .-> MASTER
    MASTER -. "姿势结果" .-> CAM
    CAM -. "姿势结果" .-> UNO["Arduino Uno<br/>LED／蜂鸣器控制"]
    PC -. "未来：服务迁移" .-> HPC["云端 HPC / GPU"]
    UNO --> LED["LED / 蜂鸣器提醒"]
```

> [!TIP]
> Camera Node ↔ Main ESP 可优先评估 **ESP-NOW**（Espressif 官方无线协议）或 **UART**（有线）。ESP-NOW 适合小数据包，传图像帧需要分片并实测吞吐；UART 的速率取决于波特率和接线长度。最终按帧大小、带宽、距离和稳定性选择。

这是**计划架构**；双板通信、IMU、电脑推理和闭环提示的具体链路待联调确认。

**待联调的接口：**

- **Camera Node ↔ Main ESP**：图像上传和姿势结果回传；优先评估 **ESP-NOW**（无线）或 **UART**（有线），再按帧大小、带宽、距离和延迟实测选择。
- **IMU ↔ Main ESP**：确认 Bosch BMI 型号、I²C/SPI 接口、引脚和供电，并做时间戳对齐。
- **Main ESP ↔ Computer**：打通图像 + IMU 上传和姿势结果回传，检查数据格式、可靠性、延迟和断网处理。
- **ESP32-CAM ↔ Arduino Uno**：姿势结果按 **电脑 → Main ESP → ESP32-CAM → Arduino Uno** 回传；确认 CAM–Uno 的硬件连接、接口和时序。
- **AI 模型**：确定动作范围、判断标准、数据集和评估指标，并在电脑上测量推理延迟与端到端响应。

### 两阶段计算部署路线

| 阶段 | AI 所在位置 | 目标 | 状态 |
| --- | --- | --- | --- |
| **Phase 1 — Prototype** | 电脑（可用 GPU／CPU） | 跑通摄像头与 IMU 数据接收、数据集准备、模型训练、实时／准实时姿势分析、LED／蜂鸣器反馈 | **当前开发方向；完整链路尚未验证** |
| **Phase 2 — Future Extension** | 云端 HPC／GPU 计算平台 | 在原型有效后评估可扩展服务、远程推理性能、部署成本与网络延迟 | **长期规划；不是目前必做项** |

## 成员与分工

PIC 指模块负责人。**每位同学只在本人分支提交；`main` 仅用于经审核合并的成果。** 现有分支名保留；Haoyu 的 `Feat-Arduino-Haoyu` 是历史命名。

| 成员 | 最新职责 | 本人工作分支 |
| --- | --- | --- |
| **Zhang Yancheng** | 项目统筹、根据 consultation 更新技术方案；协调 Arduino、双 ESP32、IMU 与电脑 AI 的接口；负责集成验证、审核 PR | `Feat-Integration-Yancheng` |
| **Zhang Haoyu** | **AI / 电脑端**：寻找适合健身姿势分析的数据集，确定动作类别与标签，训练／验证模型；搭建电脑端推理和分析服务，定义模型输入输出、反馈数据结构与评估指标 | `Feat-Arduino-Haoyu` |
| **Dong Yuankun** | **ESP32 / 传感器／通信**：从“ESP32 板上运行 AI”改为“双 ESP32 数据采集和连接”；实现 ESP32-CAM 图像采集、ESP32-S3 + IMU 采集、主 ESP 联网／上传，并与 Arduino Uno 的控制接口协同 | `Feat-Esp-Yuankun` |

两位同学完成工作后从本人分支发起 PR，base 为 `main`，交由 Zhang Yancheng 审核集成。不要直接推送 `main`，也不要修改他人分支。

## 给两位同学及其 agent 的最短指引

开始时把下面对应的说明发送给自己的 agent。**先读 [AGENTS.md](AGENTS.md)，确认用户身份及本人分支，才能修改文件。**

**Zhang Haoyu：**

> 我是 Zhang Haoyu。请先读根目录 AGENTS.md，确认当前分支为 Feat-Arduino-Haoyu，只在我的分支工作。最新任务是选择适合健身动作／姿势分析的数据集、训练和评估模型，并搭建**在团队电脑运行的 AI 推理／分析流程**。请按 models/README.md 执行，与 Dong Yuankun 对齐图像、IMU 数据及分析结果的通信格式；**本阶段不要求把模型部署在 ESP32**。每轮对话后给我一个recap。

**Dong Yuankun：**

> 我是 Dong Yuankun。请先读根目录 AGENTS.md，确认当前分支为 Feat-Esp-Yuankun，只在我的分支工作。最新任务是实现**双 ESP32 采集与通信**：ESP32-CAM 采集图像并与 Arduino Uno 连接；ESP32-S3 N16R8 作为主 ESP，接入 Bosch BMI-series IMU 并负责联网、上传数据与结果回传。请按 firmware/esp32-camera/README.md 执行，优先验证硬件接口和数据链路，**不再以板上 AI 模型部署作为主要任务**。每轮对话后给我一个recap。

### 打开自己的分支

安装 Git 后打开终端。**两人各自只运行对应的一组**，这样首次克隆就会进入本人分支。若提示仓库不存在或无权限，先联系 Zhang Yancheng 确认访问权限，不要创建另一个仓库。

Zhang Haoyu：

```powershell
git clone --branch Feat-Arduino-Haoyu --single-branch https://github.com/Steven-ZYC/int4089-fitness-aid-bot.git int4089-haoyu
cd int4089-haoyu
git branch --show-current
```

Dong Yuankun：

```powershell
git clone --branch Feat-Esp-Yuankun --single-branch https://github.com/Steven-ZYC/int4089-fitness-aid-bot.git int4089-yuankun
cd int4089-yuankun
git branch --show-current
```

已有克隆时，先运行 `git status --short --branch`。工作区干净后：

```powershell
git fetch origin
git switch <本人分支>
git pull --ff-only
git branch --show-current
```

若本地没有本人分支，改用 `git switch --track origin/<本人分支>`。上面的 `<本人分支>` 必须替换成分工表中的完整名字。如果远端没有这个分支，联系 Zhang Yancheng，不要回退到 `main`。有未提交改动时先停止切换，不能直接丢弃或覆盖。

### 保存、提交与推送

每次修改前、提交前都确认 `git branch --show-current` 输出是自己的分支；输出为 `main`、对方分支或空白时停止操作。第一次提交前，请用自己的姓名和邮箱设置仓库级 `git config user.name`、`git config user.email`，不要复制别人的身份。

Zhang Haoyu 的提交示例：

```powershell
git status --short --branch
git diff
git add models/<本次修改的文件>
git diff --cached
git commit -m "feat(ai): prototype computer-side posture analysis"
git push -u origin Feat-Arduino-Haoyu
```

Dong Yuankun 的提交示例：

```powershell
git status --short --branch
git diff
git add firmware/esp32-camera/<本次修改的文件>
git diff --cached
git commit -m "feat(esp32): integrate camera imu and networking"
git push -u origin Feat-Esp-Yuankun
```

将示例文件占位符替换为实际文件名，只暂存本次相关文件。**不要执行 `git push --all`、强制推送或向 `main` 推送。** 然后在 GitHub 选择 Compare & pull request：base 为 `main`，compare 为本人分支。PR 写明改动、研究结论、相关模型或板卡配置、复现步骤和实测结果；尚未训练或未做板上验证时明确注明。

## 当前进展/To-do list

- [x] **完成方案 consultation**：确认可由电脑承担 prototype 的 AI 推理，并根据建议增加 IMU。
- [x] **记录旧 ESP32-CAM 本地推理性能**：明确该方案不符合团队对交互速度的预期。
- [ ] **Haoyu / AI**：选定并记录合法可用的数据集、目标动作与标签；建立训练／验证／测试流程，训练基线模型，搭建电脑端推理服务，测量准确性和处理时延。见 [AI 模型工作](models/README.md)。
- [ ] **Yuankun / Dual ESP32**：确认两块板和 IMU 的具体型号；完成 Camera Node、IMU 数据采集、两板通信、主 ESP 网络上传与电脑端最小通信演示。见 [ESP32 与 IMU 工作](firmware/esp32-camera/README.md) 及 [本人分步进度](firmware/esp32-camera/PROGRESS.md)。S3 与 IMU 基础采集历史验收完成；CAM 的 USB 新画面自检亦通过，包含 OV2640 身份、3 张 640×480 解码、时间／序号及耗时证据，见 [CAM 重测](firmware/esp32-camera/CAM_RECHECK_RESULT.md)。ESP-NOW 双向文字各 20／20 次及两个漏 ACK 重试案例已通过，见 [文字结果](firmware/esp32-camera/DUAL_ESP_TEXT_RESULT.md)。11-04 三个图片案例全部通过三端指纹、解码及反向测试回覆，见 [图片实测](firmware/esp32-camera/DUAL_ESP_IMAGE_RESULT.md)。第 1–4 步基础验收完成；第 5 步的合并版 Normal 检查亦通过，见 [并发实测](firmware/esp32-camera/IMAGE_IMU_RESULT.md)。11-04 曾同时采集 IMU 和收图，镜头当时朝天花板；11-05 Wi-Fi 控制／空闲重连通过，但图像／IMU 网络传输未验收。当前 IMU 无身份应答，用户无万用表，已请组长接手硬件排查；第 5 步未完成，见 [交接文件](firmware/esp32-camera/HANDOFF.md)。
- [ ] **Yancheng / Integration**：定义跨设备消息格式和时间戳、Arduino Uno 反馈接口，集成姿势判断结果到 LED／蜂鸣器；记录端到端测试与错误处理。见 [Arduino 控制基线](firmware/arduino-uno/README.md)。
- [ ] **未来评估**：只有在本地原型有效后，才考虑云端 HPC 的部署可行性、网络和成本问题。

> [!WARNING]
> 以上为计划，未实测的数据不要写成结果。不要提交 Wi-Fi 密码、密钥、可识别人像或未授权数据集。

## 概念参考图

![用户提供的 AI 生成健身姿势辅助装置概念图](docs/reference/ai-fitness-form-coach.png)

此图为 AI 生成的产品概念参考，不代表真实接线或已完成系统；压力垫、屏幕和外壳为可选扩展。

## 仓库结构

```text
AGENTS.md                         # 身份确认、分支边界与协作规则
README.md                         # 方案、技术架构、进度、协作流程
models/README.md                  # Haoyu：数据集、训练与电脑端 AI 推理
firmware/esp32-camera/README.md   # Yuankun：双 ESP32、Camera、IMU 与联网通信
firmware/arduino-uno/README.md    # Arduino Uno 的 LED／蜂鸣器控制基线
docs/reference/                   # 概念参考图
```
