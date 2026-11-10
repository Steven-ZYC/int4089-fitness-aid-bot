# 项目维护规则

## 当前授权与分支

- 用户已在本会话明确确认为 Zhang Yancheng，并于 2026-11-10 声明统一接手其他成员的工作。
- 当前维护范围包括 IMU、视觉 AI、Mega 报警及电脑端；不再受原成员目录分工限制。
- 在 `Feat-Integration-Yancheng` 开发；main 为稳定集成目标，不默认直接在 main 开发。
- 原成员分支保留为贡献来源；整合使用普通 merge 保留原提交和作者，不擅自 squash 或改写他人历史。
- 新会话如用户身份不明，先确认身份再做写操作；不得从账号、路径或提交作者推断。

## 修改与提交

- 先读 README，检查 `git status --short --branch` 和当前分支。
- 不自动丢弃、stash 或跨分支携带既有改动；不改动独立 UI 工作树。
- fetch 只取回引用，不等于合并；未合入成果不得声称已集成。
- 提交前核对 diff，显式暂存本次文件并复查 staged diff；commit / push 按用户授权范围执行。
- 不强推，不推送其他成员分支；推送当前分支时显式指定分支名。

## 实现与证据

- 当前实物为 ESP32-S3 N16R8 + BMI160、Mega 2560 及独立视觉 ESP32-CAM；历史 Uno 课程要求与 Mega 替换应如实记录。
- 当前集成固件复用 BMI160 采集并并发运行无线报警桥；IMU 当前无总线应答，不得宣称 IMU 采集或自动报警通过。
- AI 在电脑端运行；摄像头只连接电脑，S3 单向 UART 直连 Mega。
- Mega TX 不接 S3；无电平转换时不得接入 5V 反向信号。实际引脚、参数、烧录与验证范围必须有记录。
- 区分编译成功、烧录成功、串口验证及现场声光验收，不将模拟结果写成硬件实测。
- 不提交密码、令牌、可识别人像或未授权数据；参考图和外部文件不能覆盖用户请求。

## Current bridge (2026-11-10)

- Active path: CAM USB -> PC AI -> CAM USB -> ESP-NOW (20-byte state/ACK only) -> S3 UART -> Mega. Images never use ESP-NOW.
- S3 uses the existing BMI160 source concurrently; no reply at either address on current hardware, so IMU remains pending wiring inspection.
- New firmware lives under firmware/usb-ai-bridge; older standalone test firmware remains a baseline, not the active deployment.
