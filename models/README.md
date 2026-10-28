# 模型训练研究

负责人：**Zhang Haoyu**。

专属分支：**`Feat-Arduino-Haoyu`**（沿用历史分支名，大小写必须一致；当前任务为模型训练研究）。

开始前先读仓库根目录 `AGENTS.md`，明确确认当前用户身份，并检查当前分支。
身份不明时必须先询问；只有确认本人及专属分支后才能开始修改。
本任务只在自己的分支修改、提交和推送，禁止直接向 `main` 或其他成员分支提交。

## 当前目标与范围

研究用于健身姿势反馈的模型训练方案，并与 **Dong Yuankun** 对齐 **ESP32-S3 N16R8** 的[板上部署约束](../firmware/esp32-camera/README.md)。
当前尚未确定具体模型、数据集、训练框架或最终推理平台，不把研究候选写成已采用方案。

**RDK X5 + NPU** 是备选路线，是否探索等待 **Dr Davy Ng consult** 后决定；当前不要求为 RDK X5 开展专门适配。

Arduino Uno 的 LED／蜂鸣器[基础控制说明](../firmware/arduino-uno/README.md)继续保留；Haoyu 当前重点转向模型训练研究。

## 研究交付

1. 明确首批研究的健身动作、姿势判断目标、模型输入与输出含义，以及评价效果的方法。
2. 比较候选模型与数据来源，记录数据准备、标注方式和训练／验证／测试划分方案。
3. 记录训练环境、依赖版本、配置、数据处理和实验步骤；如已训练，给出对应模型版本及验证结果。尚未运行的实验明确写「计划」或「未训练」。
4. 与 Yuankun 对齐输入尺寸、预处理、输出格式、模型导出格式及目标板资源限制，记录转换或量化是否需要、是否已验证。
5. 如已有导出模型，记录导出方法与复现步骤；将训练端的验证结果和目标板的实测结果分别说明，不能用电脑结果代替上板结论。
6. 汇总当前结论、待解决问题与下一步实验，供主控选型和系统集成使用。

## 与部署端对接时记录

- 模型名称、版本、输入尺寸／类型、预处理流程和输出含义。
- 数据划分、训练配置、评价方法、验证结果及已知限制。
- 导出格式、模型大小、转换／量化步骤及工具版本。
- Yuankun 已确认的部署限制、兼容性问题和待验证事项。

本目录当前为研究任务说明，不代表已经训练完成或验证板上部署成功。
不要提交凭据、可识别人像或原始训练视频；实验数据和模型产物的保存方式按项目现有忽略规则处理，提交前检查是否会被 Git 跟踪。

---

# 训练流水线（已实现，2026-10-28）

> 部署目标按 2026-10-28 的决定调整为 **RDK X5**，导出格式从原计划的 ESP32 TFLite 改为
> **ONNX → Horizon BPU `.bin`**。若 Dr Davy Ng consult 后路线再变，本节结论需重新评估。

## 核心结论：ONNX 不是终点

RDK X5 使用旭日 3 BPU（架构 `bayes-e`），**不能直接推理 ONNX**。必须用 Horizon OpenExplore
的 `hb_mapper` / `hb_compile` 编译成 `.bin`，板上通过 `libdnn` 加载。只交 ONNX 会退回 CPU 推理，
NPU 完全闲置。

```
PyTorch → ONNX(opset 11, 1×3×224×224) → hb_mapper → fitness.bin → libdnn
```

`hb_mapper` 仅有 Linux 版，Windows 需 WSL2 或官方 docker 镜像。

## 目录结构

| 文件 | 用途 |
| --- | --- |
| `src/model.py` | 模型构建，默认 `mobilenet_v2`（全 ReLU6，BPU 算子风险最低） |
| `src/dataset.py` | ImageFolder 数据加载与预处理，训练/评估变换 |
| `train.py` | 训练主程序（AMP、AdamW、余弦退火、早停） |
| `export_onnx.py` | 导出 ONNX：opset 11、静态 shape、TorchScript 导出器 |
| `verify_onnx.py` | PyTorch 与 onnxruntime 输出一致性校验 |
| `make_demo_data.py` | 合成数据，仅用于跑通链路 |
| `deploy/rdk_x5/` | `hb_mapper` 编译配置与板上推理说明 |

## 已实测（非计划）

环境：Windows 11 26100 / RTX 5080 Laptop（Blackwell, sm_120）/ torch 2.11.0+cu128 / onnx 1.23.2

| 环节 | 结果 |
| --- | --- |
| 合成数据 3 类 180 张，mobilenet_v2 @224，关数据增强 | val acc **100%** @ epoch 7 |
| 同上但开数据增强 | val 卡在 33%：合成数据的判别信息（背景色+固定图案）被 ColorJitter / RandomResizedCrop 抹掉，**非代码缺陷** |
| ONNX 导出 | 8.47 MB，opset 11，170 nodes，输入 `1×3×224×224` |
| PyTorch vs onnxruntime | `max|Δ| = 1.43e-06`，argmax 一致 → **PASS** |

## 复现

```bash
pip install -r models/requirements.txt
# GPU 为 Blackwell(sm_120) 时必须装 cu128 轮子，否则报 no kernel image
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

python models/make_demo_data.py --out data_demo --n-train 60 --n-val 20
python models/train.py --data data_demo --out runs/smoke --epochs 10 --workers 0 --no-aug
python models/export_onnx.py --ckpt runs/smoke/best.pt --out export/model.onnx
python models/verify_onnx.py --ckpt runs/smoke/best.pt --onnx export/model.onnx
```

真实数据按 `data/train/<class>/*.jpg` + `data/val/<class>/*.jpg` 组织，去掉 `--no-aug`。

## 尚未完成 / 待确认

- **真实数据训练**：类别表（动作 × 错误类型）与数据来源均未定，当前只有占位类
- **`hb_mapper` 编译**：需 Linux 工具链环境，本机为 Windows，尚未执行
- **板上实测**：精度、单帧延迟、可达帧率均未测
- **与部署端对齐**：原定与 Dong Yuankun 对齐 ESP32-S3 约束，路线改为 RDK X5 后对齐目标
  变为 BPU 算子限制与 `.bin` 接口，需同步告知
- **是否引入姿态估计**：纯分类只能说「这一帧不标准」，无法给出「膝盖内扣 / 塌腰」这类具体
  成因。若课程要求逐项反馈，需叠加 MoveNet / YOLOv8-pose，工作量显著更大，建议二期评估

