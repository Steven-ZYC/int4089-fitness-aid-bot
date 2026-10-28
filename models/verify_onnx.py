"""导出后的自检：PyTorch 与 onnxruntime 的输出必须一致。

目的：ONNX 转换最常见的坑是"导出了但输出不对"（漏算子、Softmax 位置错、
归一化写错），必须在进 hb_mapper 之前发现，否则会白编译一轮。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.model import build_model


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ckpt", required=True)
    p.add_argument("--onnx", default="export/model.onnx")
    p.add_argument("--tol", type=float, default=1e-4)
    args = p.parse_args()

    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    size = ckpt["img_size"]

    net = build_model(ckpt["arch"], len(ckpt["classes"]), pretrained=False)
    net.load_state_dict(ckpt["state_dict"]); net.eval()

    x = torch.randn(1, 3, size, size)
    with torch.no_grad():
        ref = net(x).numpy()

    sess = ort.InferenceSession(args.onnx, providers=["CPUExecutionProvider"])
    got = sess.run(None, {sess.get_inputs()[0].name: x.numpy()})[0]

    diff = float(np.abs(ref - got).max())
    same_argmax = bool((ref.argmax(1) == got.argmax(1)).all())
    meta = json.loads((Path(args.onnx).parent / "model_meta.json").read_text(encoding="utf-8"))

    print(f"[shape] torch={ref.shape} onnx={got.shape}")
    print(f"[classes] {meta['classes']}")
    print(f"[diff] max|Δ| = {diff:.3e}  (tol={args.tol})  argmax一致={same_argmax}")
    print(f"[size] {Path(args.onnx).stat().st_size/1024/1024:.2f} MB  input={meta['input_shape']}")

    if diff > args.tol or not same_argmax:
        print("[FAIL] ONNX 与 PyTorch 输出不一致，不要拿去编译 BPU 模型")
        sys.exit(1)
    print("[PASS] 可以进入 hb_mapper 编译阶段")


if __name__ == "__main__":
    main()
