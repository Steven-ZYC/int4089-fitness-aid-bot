"""数据集与预处理。

目录约定（ImageFolder 标准结构）：

    data/
      train/
        good_squat/   *.jpg
        knee_valgus/  *.jpg
        ...
      val/
        good_squat/ ...
      test/
        good_squat/ ...

关键点：这里的评估预处理（Resize + CenterCrop + Normalize）必须和
RDK X5 板上 Python 前处理逐位一致，否则 accuracy 会无声下降。
"""
from pathlib import Path

from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.transforms import InterpolationMode

# ImageNet 统计量。板上前处理也用同一组常数。
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def build_transforms(img_size: int = 224, train: bool = True, aug: bool = True):
    if train and not aug:
        # 关闭数据增强：仅缩放+中心裁剪。用于排查「验证集不涨」到底是
        # 增强过强还是代码问题——小数据集上 RandomResizedCrop 有时会把
        # 关键区域裁掉。
        resize = int(round(img_size * 1.14))
        return transforms.Compose([
            transforms.Resize(resize, interpolation=InterpolationMode.BILINEAR),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ])

    if train:
        return transforms.Compose([
            transforms.RandomResizedCrop(img_size, scale=(0.6, 1.0),
                                         interpolation=InterpolationMode.BILINEAR),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(0.2, 0.2, 0.2),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ])

    # 评估：短边缩放到 1.14x 再中心裁剪，与板上做法一致
    resize = int(round(img_size * 1.14))
    return transforms.Compose([
        transforms.Resize(resize, interpolation=InterpolationMode.BILINEAR),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])


def build_loaders(data_root: str, img_size: int = 224, batch_size: int = 32,
                  workers: int = 4, eval_split: str = "val", aug: bool = True):
    root = Path(data_root)
    train_dir, eval_dir = root / "train", root / eval_split
    if not train_dir.is_dir():
        raise FileNotFoundError(f"找不到训练目录：{train_dir}")

    train_ds = datasets.ImageFolder(train_dir, build_transforms(img_size, True, aug))
    pin = True
    train_ld = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                          num_workers=workers, pin_memory=pin, drop_last=True,
                          persistent_workers=workers > 0)

    eval_ld = None
    if eval_dir.is_dir():
        eval_ds = datasets.ImageFolder(eval_dir, build_transforms(img_size, False))
        if eval_ds.classes != train_ds.classes:
            raise ValueError(f"类别不一致：train={train_ds.classes} / {eval_split}={eval_ds.classes}")
        eval_ld = DataLoader(eval_ds, batch_size=batch_size, shuffle=False,
                             num_workers=workers, pin_memory=pin)

    return train_ld, eval_ld, train_ds.classes
