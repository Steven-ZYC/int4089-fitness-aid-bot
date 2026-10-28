"""BPU 友好的分类模型构建。

面向 RDK X5（地平线 旭日3 BPU）的选型原则：
  - 只用 BPU 算子支持表内的算子：Conv / BN / ReLU / ReLU6 / Add / Concat /
    MaxPool / GlobalAvgPool / Gemm / Softmax
  - 不使用 Hardswish、动态 shape、5D 张量、自定义算子
  - 输入固定 NCHW 1x3x224x224

因此默认骨架选 mobilenet_v2（ReLU6），而不是 mobilenet_v3（Hardswish）。
需要更高精度时换 resnet18，同样全算子支持。
"""
import torch.nn as nn
from torchvision import models

SUPPORTED = ("mobilenet_v2", "resnet18", "mobilenet_v3_small")


def build_model(arch: str = "mobilenet_v2", num_classes: int = 4, pretrained: bool = False):
    if arch not in SUPPORTED:
        raise ValueError(f"arch 必须是 {SUPPORTED} 之一，收到 {arch!r}")

    if arch == "mobilenet_v2":
        net = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1 if pretrained else None)
        in_f = net.classifier[-1].in_features
        net.classifier[-1] = nn.Linear(in_f, num_classes)

    elif arch == "resnet18":
        net = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)
        net.fc = nn.Linear(net.fc.in_features, num_classes)

    else:  # mobilenet_v3_small —— 含 Hardswish，BPU 转换风险较高，仅作对照
        net = models.mobilenet_v3_small(
            weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None)
        in_f = net.classifier[-1].in_features
        net.classifier[-1] = nn.Linear(in_f, num_classes)

    return net


def count_params(net) -> int:
    return sum(p.numel() for p in net.parameters())
