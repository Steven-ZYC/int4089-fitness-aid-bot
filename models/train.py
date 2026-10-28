"""训练入口。

用法：
    python train.py --data data --arch mobilenet_v2 --epochs 30
    python train.py --data data --arch resnet18 --epochs 60 --pretrained
"""
import argparse
import json
import random
import time
from pathlib import Path
import sys

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.dataset import build_loaders, MEAN, STD
from src.model import build_model, count_params


def set_seed(s: int):
    random.seed(s); np.random.seed(s)
    torch.manual_seed(s); torch.cuda.manual_seed_all(s)


@torch.no_grad()
def evaluate(net, loader, device, criterion):
    net.eval()
    loss_sum, correct, total = 0.0, 0, 0
    for x, y in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        logits = net(x)
        loss_sum += criterion(logits, y).item() * y.size(0)
        correct += (logits.argmax(1) == y).sum().item()
        total += y.size(0)
    return loss_sum / max(total, 1), correct / max(total, 1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="runs/exp1")
    p.add_argument("--arch", default="mobilenet_v2")
    p.add_argument("--img-size", type=int, default=224)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--wd", type=float, default=0.05)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--pretrained", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--patience", type=int, default=8, help="val acc 连续多少轮不升就停")
    p.add_argument("--no-aug", action="store_true", help="关闭数据增强（排查用）")
    args = p.parse_args()

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    train_ld, eval_ld, classes = build_loaders(
        args.data, args.img_size, args.batch_size, args.workers, aug=not args.no_aug)
    print(f"[data] classes={classes} train_batches={len(train_ld)} "
          f"val_batches={len(eval_ld) if eval_ld else 0}")

    net = build_model(args.arch, len(classes), args.pretrained).to(device)
    print(f"[model] {args.arch} params={count_params(net)/1e6:.2f}M device={device}")

    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    opt = AdamW(net.parameters(), lr=args.lr, weight_decay=args.wd)
    sched = CosineAnnealingLR(opt, T_max=max(args.epochs, 1))
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    best_acc, best_epoch, stale = -1.0, -1, 0
    history = []

    for epoch in range(1, args.epochs + 1):
        net.train()
        t0 = time.time()
        run_loss, seen, hit = 0.0, 0, 0

        for x, y in train_ld:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=use_amp):
                logits = net(x)
                loss = criterion(logits, y)
            scaler.scale(loss).backward()
            scaler.step(opt); scaler.update()

            run_loss += loss.item() * y.size(0)
            hit += (logits.argmax(1) == y).sum().item()
            seen += y.size(0)

        sched.step()
        train_loss, train_acc = run_loss / max(seen, 1), hit / max(seen, 1)
        val_loss, val_acc = evaluate(net, eval_ld, device, criterion) if eval_ld else (float("nan"), float("nan"))
        history.append(dict(epoch=epoch, train_loss=train_loss, train_acc=train_acc,
                            val_loss=val_loss, val_acc=val_acc, lr=sched.get_last_lr()[0]))

        print(f"[ep {epoch:03d}] train loss={train_loss:.4f} acc={train_acc:.4f} | "
              f"val loss={val_loss:.4f} acc={val_acc:.4f} | {time.time()-t0:.1f}s")

        score = val_acc if eval_ld else train_acc
        if score > best_acc:
            best_acc, best_epoch, stale = score, epoch, 0
            torch.save({
                "state_dict": net.state_dict(),
                "arch": args.arch,
                "classes": classes,
                "img_size": args.img_size,
                "mean": MEAN,
                "std": STD,
                "val_acc": val_acc,
                "epoch": epoch,
            }, out / "best.pt")
            print(f"        -> saved best.pt (score={score:.4f})")
        else:
            stale += 1
            if stale >= args.patience:
                print(f"[early stop] 连续 {args.patience} 轮无提升")
                break

    (out / "metrics.json").write_text(
        json.dumps({"args": vars(args), "history": history,
                    "best_acc": best_acc, "best_epoch": best_epoch,
                    "classes": classes}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[done] best_acc={best_acc:.4f} @ epoch {best_epoch}  -> {out/'best.pt'}")


if __name__ == "__main__":
    main()
