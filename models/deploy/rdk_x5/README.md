# RDK X5 部署：ONNX → BPU .bin

## 结论先说

**ONNX 不能直接在 RDK X5 的 BPU 上跑。** 必须再用 Horizon OpenExplore 的
`hb_mapper` 编译成 `.bin`，板上通过 `libdnn` 加载。只交 ONNX 的话，推理会退回
CPU（hobot 的 `dnn` 框架不支持直接喂 ONNX），10 TOPS 的 NPU 完全用不上。

```
model.onnx --(hb_mapper checker)--> 算子支持检查
           --(hb_compile)--> model_output/fitness.bin  ← 板上加载这个
```

## 前置条件

`hb_mapper` **只有 Linux 版**，Windows 上必须用 WSL2 或 docker：

```bash
docker run -it --rm -v "$PWD":/work \
  openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8
```

镜像版本要和 RDK X5 系统里的 `hrt_model_exec` / `libdnn` 版本对齐，否则板上加载
会报版本不匹配。

## 步骤

### 1. 算子支持检查（必做，几秒钟）

```bash
hb_mapper checker --model-type onnx --march bayes-e --model model.onnx
```

看到 `Unsupported op` 就直接改模型结构，不要往下走——编译到一半失败会浪费十几分钟。

### 2. 准备校准集

int8 量化需要真实画面。从训练集每类随机抽 20–50 张：

```python
import cv2, numpy as np, glob, os
os.makedirs("calib_data", exist_ok=True)
files = glob.glob("data/train/*/*.jpg")[:200]
for i, f in enumerate(files):
    img = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224)).astype(np.float32)
    img.tofile(f"calib_data/{i:04d}.bin")   # 纯 float32 二进制，(3,224,224) HWC 顺序见文档
```

⚠️ **不能用随机噪声做校准**，否则量化后精度会掉得莫名其妙。校准集要覆盖真实场景的
光照、肤色、背景多样性。

### 3. 编译

```bash
hb_compile -c hb_mapper_config.yaml
```

产物在 `model_output/`：

| 文件 | 用途 |
|---|---|
| `fitness.bin` | 板上加载的定点模型 |
| `fitness_quantized_model.onnx` | 量化后的 ONNX（可用 PC 端 onnxruntime 复核精度） |
| `*_static.log` | 精度/耗时报告，重点看 `Cosine Similarity`（建议 > 0.99） |

### 4. 板上推理

```python
from hobot_dnn import pyeasy_dnn as dnn
import numpy as np, cv2

models = dnn.load("fitness.bin")
inp = models[0].inputs[0]

img = cv2.imread("frame.jpg")                      # BGR, HxWx3
img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
img = cv2.resize(img, (224, 224)).astype(np.float32)

if inp.properties.type == "nv12":
    img = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2YUV_I420)   # 按实际类型转换

outs = models[0].forward(img)
print(np.array(outs[0].buffer).argmax())
```

## 输入尺寸为什么是 224

- 训练时就是 224，改尺寸必须重新训练
- 更小的 160 也能编译，BPU 上更快，但小目标（手腕、脚踝位置）分辨率不够
- 512+ 会显著增加单帧延迟，实时反馈场景不划算

## 已知风险

| 风险 | 说明 |
|---|---|
| 量化掉点 | 分类模型一般掉 1–3 个点；掉太多就换 `calibration_type: 'mix'` 或加 `kl` |
| 算子不支持 | ResNet18 / MobileNetV2 全支持；MobileNetV3 的 Hardswish 需实测 |
| 版本不匹配 | 编译镜像版本必须与板上 `libdnn` 一致 |
| 前处理不一致 | 板上 `input_type_rt: nv12` 时由硬件做 YUV→RGB，务必用同一张图在 PC 和板上对比输出 |
