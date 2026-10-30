# Agent 协作规则（必须遵守）

## 1. 任何改动前，先确认用户身份，不可跳过

- 在编辑、新建、删除文件，或执行 checkout/switch、add、commit、push 等 Git 写操作前，必须确认本会话的实际用户是哪位成员。
- 只有用户在本会话中的明确身份声明才算确认；不能通过 Git author、GitHub 账号、当前分支、文件路径或任务内容猜测。身份不明时必须先询问：**「你是 Zhang Yancheng、Zhang Haoyu，还是 Dong Yuankun？」** 收到明确答复前只能只读检查。
- 用户在本会话已明确声明身份时，必须核对并记录该身份，无需重复询问。身份切换或出现歧义时重新确认。子 agent 继承已经确认的用户身份与权限，不能自行换用其他成员身份。
- 身份确认是硬性前置条件，不能为了赶进度、初始化环境或完成任务而跳过；确认后，普通的本人分支工作无需逐步重复请求许可。

## 2. 身份、任务和分支一一对应

| 已确认身份 | 唯一工作分支（大小写必须一致） | 职责 |
| --- | --- | --- |
| Zhang Haoyu | `Feat-Arduino-Haoyu` | 当前负责数据集选择、模型训练／评估及团队电脑端 AI 推理；主要目录 `models/`。分支保留历史命名，Arduino Uno 基础控制说明仍保留 |
| Dong Yuankun | `Feat-Esp-Yuankun` | 当前负责双 ESP32 图像／IMU 采集、主 ESP 联网与数据传输；主要目录 `firmware/esp32-camera/`，与 Haoyu 对齐输入、输出和通信约定 |
| Zhang Yancheng | `Feat-Integration-Yancheng` | 项目统筹、consultation 后的架构与系统集成；负责 Arduino／双 ESP／AI 的接口协调、审核和合并 PR |

- **默认不得在 `main` 开发。只能在已确认用户自己的工作分支修改、暂存、提交和推送。不得替其他成员提交。**
- `main` 只承载经 Zhang Yancheng 审核合并的结果。Zhang Yancheng 也在自己的工作分支开发。
- **仅首次建仓的例外**：身份已确认的 Zhang Yancheng 可在自己的分支完成初始提交，并把这一份相同的初始提交创建、首次推送为尚不存在的 `main` 和两个成员分支。这不是在他人分支开发或提交的授权；首次发布后全部遵守下述本人分支和 PR 规则，不得覆盖已有远端分支。
- 两位同学通过本人分支的 Pull Request 请求合并，不得自行合并到 `main` 或修改对方分支。修改共享文档也必须留在本人分支中。

## 3. 开始工作与提交前的检查

先读取根 README 的「成员与分工」「打开自己的分支」，再执行：

```powershell
git status --short --branch
git branch --show-current
```

1. 将已确认身份映射到上表，检查当前分支精确匹配。遇到 `main`、其他成员分支或 detached HEAD，停止修改。
2. 如需切换，先确认工作区干净；有既有改动时不要自动 stash、reset、丢弃或携带到别的分支，先说明情况并与用户确认处理方式。
3. 干净工作区执行 `git fetch origin`，已有本人本地分支用 `git switch <本人分支>`；没有时用 `git switch --track origin/<本人分支>`。远端分支不存在就停止并报告，**不得回退到 `main`，不得自动新建别人的分支**。
4. 在本人分支执行 `git pull --ff-only`。没有配置远端时可进行本人本地工作，但必须如实说明无法同步或推送。
5. 提交和推送前再次检查分支、`git status` 和 `git diff`；仅 `git add` 本次明确修改的文件，检查 `git diff --cached` 后提交。
6. 推送必须显式写出本人分支：`git push -u origin <本人分支>`。禁止 `git push --all`、`--mirror`、强推，以及推送到 `main` 或其他成员分支（上文严格限定的首次建仓发布除外）。
7. PR 使用本人分支作为 source、`main` 作为 target，交由 Zhang Yancheng 审核。有冲突先报告，禁止用覆盖历史的命令自动解决。

`AGENTS.md` 是 agent 协作约束，并非 GitHub 权限控制；不要声称仅靠这个文件就能技术上阻止他人直接推送。

## 4. 项目与实现边界

- 课程原型必须保留 **Arduino Uno**，用于本地 LED／蜂鸣器等传感器／执行器相关控制，不能由 ESP32 完全替代。
- **2026-10-30 consultation 后的现阶段方案**：双 ESP32 + Bosch BMI-series IMU + Arduino Uno + 团队电脑上的 AI。原 ESP32-CAM 板上推理测试仅约 0.0655 FPS（包含采集和预／后处理），因此不再要求本阶段在 ESP32 上运行姿态模型。
- **ESP32-CAM** 采集图像，与 Arduino Uno 建立硬件连接；**ESP32-S3 N16R8（主 ESP，须以实物确认）** 接入 Bosch BMI-series IMU 并负责与电脑的网络通信。准确 IMU 型号、引脚和两板间链路均待验证，不能猜测。
- **Zhang Haoyu** 负责找数据集、训练和评估姿势分析 AI、建立电脑端推理流程；**Dong Yuankun** 负责 ESP32-CAM、IMU、双板通信、主 ESP 网络与控制接口，不再研究把主 AI 模型部署在 ESP32 上作为第一优先级。
- 早先的 ESP32-S3 板上模型部署与 RDK X5 NPU 两条候选路线已被此次方案调整取代；不要继续把它们写成现阶段必须推进的主线。
- 云端 HPC／GPU 是**原型有效后的未来部署设想**，不是已经建成的平台，也不是本阶段的验收前提。
- 电脑负责图像与 IMU 数据处理、AI 姿势判断和反馈产生；最后需要把判断结果传给 Arduino Uno 以控制输出，具体回传路径、协议、数据格式和时序需联调确认。
- 未确认板卡、传感器、摄像头、供电与引脚前，不得猜测 pin map 或宣称硬件测试通过。所有实验记录实际环境、数据集许可、实现步骤、测量方法和结果，区分“计划”“进行中”“已验证”。
- `docs/reference/ai-fitness-form-coach.png` 仅是 AI 生成概念图，不是电路接线依据。IMU 已进入新方案；压力垫、显示屏和外壳仍是可选扩展。
- 不提交 Wi-Fi 密码、令牌、密钥、原始含可识别人像的照片／视频或未经许可的数据集。
