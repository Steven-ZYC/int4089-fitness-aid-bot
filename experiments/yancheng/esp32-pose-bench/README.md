# Yancheng：经典 ESP32-CAM 板端姿态推理实验

负责人 **Zhang Yancheng**，仅在 **`Feat-Integration-Yancheng`** 工作。开始前遵守根 [AGENTS.md](../../../AGENTS.md) 的身份确认及分支规则。Dong Yuankun 的原摄像头实现保留在 `firmware/esp32-camera/`，本目录独立放集成与性能测试代码。

**2026-10-23 已实测：128×128 INT8 的纯推理约 15.126 秒／帧（0.0661 FPS），完整取帧处理约 0.0655 FPS。** 10 帧均未检测到人体，尚未验证关键点准确度。原拍照固件已恢复并校验。见 [完整实测记录](results/2026-10-23-classic-esp32.md)。

## 实验范围与限制

本机已实测 **ESP32-D0WD-V3，revision v3.1，双核、运行于 240 MHz，4 MB Flash，2 MB PSRAM，COM4 / CH340**。板上标识为 ESP32S、HW381、ESP32-CAM-MB；2 MB 容量来自本目录预检固件的实际读取，不是从名称推测。

**ESP-DL COCO Pose 就是 YOLO11n-Pose 的封装，并非两个独立模型。** 官方现成模型为 640×640、INT8，提供 S3/P4 等目标版本；经典 ESP32 需要自行量化为 `target="c"`、构建目标设为 `esp32`。本目录没有把 S3 模型直接烧到经典 ESP32，也不在电脑运行模型后将结果算作板端 FPS。

首轮低负载配置：

| 项目 | 本实验 |
| --- | --- |
| 模型 | YOLO11**n**-Pose，nano 版本 |
| 输入 | 默认 128×128；可另行量化 96/160/192/224/320，每次尺寸变更必须重新导出、量化和编译 |
| 量化 | W8A8 / INT8，ESP-PPQ C target |
| 输出 | 17 个 COCO 人体关键点；最多保留 1 人，仅减少后处理开销 |
| 相机 | 沿用 Yuankun 的 AI Thinker 引脚，RGB565，160×120，单帧缓冲 |
| 预处理 | RGB、居中 letterbox（114）、归一化到 [0,1] |
| 内存策略 | 权重留在 Flash，优先减少 PSRAM 占用，可能牺牲推理速度 |
| 测量 | 默认预热 2 帧不计入，随后记录 10 帧 |

这是**自定义低分辨率实验**，不是已经验证精度的官方低功耗模型。nano 仍可能装不下或运行极慢；减小输入主要降低激活内存和运算量，不会同比减少权重大小。低分辨率和 INT8 也可能明显损失关键点准确度，不能据此判断健身动作是否安全。

## 目录与执行顺序

```text
firmware/                  ESP-IDF 5.5.x 工程；默认只测硬件及取帧
tools/prepare_model.py     导出九路原始 Pose head，量化 C-target 模型并记录 SHA256
tools/build.sh             在无空格的临时项目路径编译 probe / pose
tools/device.py            读取板卡、完整备份、测试、自动恢复原固件
tools/collect_metrics.py   收集设备时间戳，生成真实板端统计
tests/                    检查 FPS 口径、掉帧、复位及模式混淆
results/                  可提交的测试结论；本地原始记录在 results/local/（忽略）
artifacts/                模型、构建产物及固件备份（忽略）
datasets/                 本地校准数据（忽略）
```

### 1. Windows 串口环境

在本目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-device.txt
.\.venv\Scripts\python.exe tools/device.py probe --port COM4
```

关闭其他串口监视器；按实际端口修改 `COM4`。本目录只针对目前确认的经典 ESP32-CAM，不能把 S3/C3 的引脚或固件直接套用。

### 2. 编译并运行预检

编译使用 Linux / WSL 中导出的 **ESP-IDF 5.5.x**；组件固定为 ESP-DL **3.3.14**、esp32-camera **2.1.5**。若尚未安装工具链，按下方官方 ESP-IDF 文档安装并执行 `install.sh esp32`。

本机已准备的 WSL 路径是 `/opt/int4089-espdl-tools/esp-idf`，工具目录为 `/opt/int4089-espdl-tools/idf-tools`。在该 WSL 环境执行：

```bash
export IDF_TOOLS_PATH=/opt/int4089-espdl-tools/idf-tools
source /opt/int4089-espdl-tools/esp-idf/export.sh
cd "/mnt/d/projects/int4089-STEM AI-GP/experiments/yancheng/esp32-pose-bench"
bash tools/build.sh probe
```

脚本复制工程到不含空格的 `/tmp/int4089-pose-build.*` 再构建，保留原始源码；产物回到 `artifacts/build-probe/`。回到 Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe tools/device.py run --mode probe --port COM4
```

脚本先备份整片 4 MB Flash，再烧录测试固件、测量，最后在 `finally` 中恢复备份。原程序备份和 SHA256 在 `artifacts/backups/<时间>/`。测试输出包括实际 CPU 时钟、物理 PSRAM 和映射 PSRAM 字节数；`camera_only` 模式的 FPS **只表示取帧处理吞吐，不是 AI 推理帧率**。

Flash 读写默认使用 230400 baud；CH340 连接不稳定时加 `--baud 115200`。已有完整备份且原程序已恢复时，可在下次 `run` 中加 `--backup-file <备份路径>`；脚本会先在板上校验整片 Flash 与备份一致，才允许复用，否则停止。

如果电脑进程被强制终止或断电，`finally` 无法保证执行；重新接好设备后，可指定已记录的备份文件恢复：

```powershell
.\.venv\Scripts\python.exe tools/device.py restore --port COM4 --backup-file artifacts/backups/<时间>/original.bin
```

### 3. 准备最低负载的 Pose 模型

量化在 **WSL / Linux，Python 3.12** 执行；Windows 串口读取与板端推理不依赖 PyTorch。首次准备独立环境：

```bash
python3 -m venv .venv-model
.venv-model/bin/python -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu
.venv-model/bin/python -m pip install -r requirements-model.txt
```

把至少 32 张有代表性的真实场景照片放在 `datasets/calibration/`，再执行：

```bash
.venv-model/bin/python tools/prepare_model.py --size 128 --calibration datasets/calibration --calib-steps 32
```

首次调用会从 Ultralytics 下载 `yolo11n-pose.pt`。脚本将预训练模型导出为 ESP-DL 后处理所需的 `box0/score0/box1/score1/box2/score2/kpt0/kpt1/kpt2` 九路输出，然后量化为 `target=c`。产物为 `artifacts/model/yolo11n_pose.espdl` 与 `manifest.json`。

仅检查导出／量化链路时，可使用 [Ultralytics COCO8-Pose](https://docs.ultralytics.com/datasets/pose/coco8-pose/) 的 8 张图片并显式指定 `--calib-steps 8`；这不能代替真实场景的精度验证。不要用随机噪声校准后声称姿态精度可用。

本机额外准备的量化环境为 `/opt/int4089-espdl-tools/quant-venv/bin/python`，可替换上面的 `.venv-model/bin/python`。权重、ONNX、ESP-DL 模型和校准图片不提交到 Git；清单记录模型哈希、输入尺寸、目标和包版本。

### 4. 编译并测量板端 Pose

在同一 ESP-IDF WSL 环境中：

```bash
bash tools/build.sh pose
```

构建会核对 `target=c` 和模型 SHA256。只有固件与模型总大小能装入本板约 3.94 MiB 的应用分区，才能继续烧录；不能用更改分区声明来伪造更大的物理 Flash。Windows 运行：

```powershell
.\.venv\Scripts\python.exe tools/device.py run --mode pose --port COM4 --timeout 1800
```

PSRAM 不可用、内存不足、模型不兼容、复位或超时都应记录为**未完成测量**，不能填写 0 FPS 或用官方 S3 数值代替。原固件会在正常／异常退出时尝试恢复；完整备份必须保留。

## 如何读结果

- `inference_fps = 测量帧数 / 板上神经网络推理总时间`，不包括相机和预／后处理。
- `observed_processing_fps = 测量帧数 / 从第一帧开始到最后一帧完成的板上时间`，包括取帧、预处理、模型、后处理及测量帧之间的日志／调度间隔；不包括 PC 显示、网络上传或相机曝光到显示的完整延迟。
- 同时保存推理均值与 P95 毫秒、每帧各阶段耗时、实际输入尺寸、模型哈希和 PSRAM。不能平均各帧 FPS 代替总体吞吐。
- 预热、模型加载、启动时间不计入稳定帧率，但加载失败必须报告。先小样本跑通，再增加帧数并另测准确度与连续稳定性。

开发检查：`python -B -m unittest discover -s tests -v`。合成测试只验证统计口径，绝不是硬件性能证据。

## 官方资料

- [ESP-DL 入门与经典 ESP32 C target](https://docs.espressif.com/projects/esp-dl/en/latest/getting_started/readme.html)
- [YOLO11n-Pose 导出、量化与原始 head 接口](https://docs.espressif.com/projects/esp-dl/en/latest/tutorials/how_to_deploy_yolo11n-pose.html)
- [COCO Pose 支持目标与官方 640×640 基准](https://github.com/espressif/esp-dl/blob/eb72563e6a4e61d2bbc0d46e4c79f2c9f816c3c6/models/coco_pose/README.md)
- [ESP-IDF 5.5.2 Linux 安装](https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32/get-started/linux-macos-setup.html)

Ultralytics、预训练权重及 ESP-DL 依赖保留各自的许可证；本目录未将这些依赖源码或模型权重重新打包发布。
