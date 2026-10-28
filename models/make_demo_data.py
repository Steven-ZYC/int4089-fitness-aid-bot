"""生成合成数据，仅用于验证流水线是否跑通（不是真实训练数据）。

真实训练前用它确认「数据加载 → 训练 → 导出 ONNX → 一致性校验」这条链没断，
免得等真实数据到位后才发现是代码问题。

    python make_demo_data.py --out data_demo --n-train 60 --n-val 20
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

CLASSES = ["good_form", "knee_valgus", "back_rounded"]


def make_image(cls_idx: int, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    size = 256
    # 背景色按类别固定（只加轻微抖动），否则训练集和验证集毫无共性，
    # 冒烟测试会一直停在随机准确率，反而让人误判成代码有问题
    base = [(45, 55, 70), (65, 45, 55), (50, 65, 45)][cls_idx]
    bg = tuple(int(np.clip(c + rng.integers(-6, 6), 0, 255)) for c in base)
    img = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(img)

    # 每个类别一个明显不同的几何图案，让模型能在几十张图内就学会
    if cls_idx == 0:
        d.ellipse([80, 60, 176, 200], fill=(90, 190, 120))
        d.line([128, 200, 128, 240], fill=(200, 200, 200), width=10)
    elif cls_idx == 1:
        d.polygon([(128, 60), (70, 200), (186, 200)], fill=(220, 120, 90))
        d.line([128, 190, 80, 240], fill=(200, 200, 200), width=10)
    else:
        d.arc([70, 80, 186, 240], start=200, end=340, fill=(120, 140, 230), width=16)
        d.line([128, 150, 170, 240], fill=(200, 200, 200), width=10)

    arr = np.asarray(img).astype(np.int16) + rng.integers(-8, 8, (size, size, 3))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data_demo")
    p.add_argument("--n-train", type=int, default=60)
    p.add_argument("--n-val", type=int, default=20)
    args = p.parse_args()

    root = Path(args.out)
    for split, n in (("train", args.n_train), ("val", args.n_val)):
        for ci, cname in enumerate(CLASSES):
            d = root / split / cname
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                make_image(ci, seed=(ci * 100000 + i * 7 + (0 if split == "train" else 500000))).save(
                    d / f"{i:04d}.jpg", quality=90)
            print(f"  {d}  {n} imgs")
    print(f"[ok] demo dataset -> {root.resolve()}")


if __name__ == "__main__":
    main()
