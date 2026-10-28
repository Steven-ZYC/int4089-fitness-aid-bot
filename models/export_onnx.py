"""把训练好的 .pt 导出为 RDK X5 需要的 ONNX。

为什么这样导：
  - opset 11：Horizon OpenExplore 的 hb_mapper 对 11 支持最完整，12+ 容易报
    "unsupported operator"
  - batch 固定为 1：BPU 编译时 batch 必须静态；动态轴在 hb_mapper 里会直接失败
  - 用 TorchScript 导出器（dynamo=False）：torch>=2.6 默认走 dynamo，
    产出的图常带 hb_mapper 不认识的算子
  - 关掉 constant folding 的反面：这里开着，能把 BatchNorm 折叠进 Conv，
    减少板上算子数量

用法：
    python export_onnx.py --ckpt runs/exp1/best.pt --out export/model.onnx
"""
import argparse
import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.model import build_model

OPSET = 11


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ckpt", required=True)
    p.add_argument("--out", default="export/model.onnx")
    p.add_argument("--opset", type=int, default=OPSET)
    args = p.parse_args()

    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    arch, classes, size = ckpt["arch"], ckpt["classes"], ckpt["img_size"]

    net = build_model(arch, len(classes), pretrained=False)
    net.load_state_dict(ckpt["state_dict"])
    net.eval()

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, size, size)

    kwargs = dict(
        input_names=["input"],
        output_names=["output"],
        opset_version=args.opset,
        do_constant_folding=True,
        dynamic_axes=None,          # 全静态，BPU 必需
    )
    try:
        torch.onnx.export(net, dummy, str(out), dynamo=False, **kwargs)
    except TypeError:
        # 老版本 torch 没有 dynamo 参数
        torch.onnx.export(net, dummy, str(out), **kwargs)

    import onnx
    model = onnx.load(str(out))
    onnx.checker.check_model(model)
    n_op = len(model.graph.node)

    meta = {
        "arch": arch,
        "classes": classes,
        "img_size": size,
        "mean": ckpt["mean"],
        "std": ckpt["std"],
        "opset": args.opset,
        "input_name": "input",
        "output_name": "output",
        "input_shape": [1, 3, size, size],
        "val_acc_in_pytorch": ckpt.get("val_acc"),
    }
    (out.parent / "model_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"[ok] {out}  {size_mb:.2f} MB  opset={args.opset}  nodes={n_op}")
    print(f"[ok] meta -> {out.parent/'model_meta.json'}")
    print("\n下一步（Linux / WSL 上执行）：")
    print("  1. 复制 ONNX 到 RDK X5 工具链环境（OpenExplore docker）")
    print("  2. 按 deploy/rdk_x5/hb_mapper_config.yaml 填好校准数据路径")
    print("  3. hb_mapper checker --model-type onnx --march bayes-e --model model.onnx")
    print("  4. hb_compile -c config.yaml -o model_output")


if __name__ == "__main__":
    main()
