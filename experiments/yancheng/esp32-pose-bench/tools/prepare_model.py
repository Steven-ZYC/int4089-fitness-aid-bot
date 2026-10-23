"""Export YOLO11n-Pose raw heads, then INT8-quantize for the classic ESP32 C backend.

Based on the head contract in Espressif's YOLO11n-Pose deployment tutorial.
This is a custom low-resolution experiment, not an official prebuilt COCO Pose model.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[1]
HEAD_NAMES = ["box0", "score0", "box1", "score1", "box2", "score2", "kpt0", "kpt1", "kpt2"]


def raw_pose(self, features):
    boxes_scores = []
    keypoints = []
    for stage in range(3):
        boxes_scores.extend((self.cv2[stage](features[stage]), self.cv3[stage](features[stage])))
        keypoints.append(self.cv4[stage](features[stage]))
    return tuple(boxes_scores + keypoints)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=128, choices=(96, 128, 160, 192, 224, 320))
    parser.add_argument("--calibration", required=True, type=Path, help="Directory of representative RGB images")
    parser.add_argument("--calib-steps", type=int, default=32, choices=range(8, 513), metavar="8..512")
    parser.add_argument("--weights", default="yolo11n-pose.pt", help="Official Ultralytics weights or a local path")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "model")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if Path(args.weights).is_file():
        args.weights = str(Path(args.weights).resolve())
    paths = sorted(p for p in args.calibration.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if len(paths) < args.calib_steps:
        parser.error(f"Need at least {args.calib_steps} distinct calibration images; found {len(paths)}")
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".cache" / "ultralytics"))

    import numpy as np
    import onnx
    from onnxsim import simplify
    from PIL import Image
    import torch
    from torch.utils.data import DataLoader, Dataset
    from ultralytics import YOLO
    from ultralytics.nn.modules import Pose
    from esp_ppq.api import espdl_quantize_onnx
    from esp_ppq.api.setting import QuantizationSettingFactory

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.manual_seed(0)
    # Keep downloaded weights and exported models out of the tracked source tree.
    previous_dir = Path.cwd()
    try:
        os.chdir(args.output)
        network = YOLO(args.weights).model.cpu().eval().fuse(verbose=False)
    finally:
        os.chdir(previous_dir)
    heads = [m for m in network.modules() if isinstance(m, Pose)]
    if len(heads) != 1 or heads[0].nl != 3:
        raise RuntimeError("Expected the three-stage YOLO11 Pose head")
    heads[0].forward = types.MethodType(raw_pose, heads[0])
    example = torch.zeros(1, 3, args.size, args.size)
    onnx_path = args.output / "yolo11n_pose.onnx"
    torch.onnx.export(network, example, str(onnx_path), opset_version=13, dynamo=False,
                      input_names=["images"], output_names=HEAD_NAMES, dynamic_axes=None)
    simplified, valid = simplify(onnx.load(onnx_path))
    if not valid:
        raise RuntimeError("ONNX simplification verification failed")
    onnx.checker.check_model(simplified)
    if [v.name for v in simplified.graph.output] != HEAD_NAMES:
        raise RuntimeError("Exported head names differ from ESP-DL postprocessor contract")
    onnx.save(simplified, onnx_path)

    class CalibrationImages(Dataset):
        def __len__(self):
            return args.calib_steps

        def __getitem__(self, index):
            # Same centered 114/114/114 letterbox and [0,1] RGB normalization as firmware.
            with Image.open(paths[index]) as source:
                rgb = source.convert("RGB")
                scale = min(args.size / rgb.width, args.size / rgb.height)
                width, height = round(rgb.width * scale), round(rgb.height * scale)
                resized = rgb.resize((width, height), Image.Resampling.BILINEAR)
                canvas = Image.new("RGB", (args.size, args.size), (114, 114, 114))
                canvas.paste(resized, ((args.size - width) // 2, (args.size - height) // 2))
                values = np.asarray(canvas, dtype=np.float32) / 255.0
            return torch.from_numpy(values.transpose(2, 0, 1).copy())

    model_path = args.output / "yolo11n_pose.espdl"
    settings = QuantizationSettingFactory.espdl_setting()
    espdl_quantize_onnx(
        onnx_import_file=str(onnx_path), espdl_export_file=str(model_path),
        calib_dataloader=DataLoader(CalibrationImages(), batch_size=1, shuffle=False),
        calib_steps=args.calib_steps, input_shape=[1, 3, args.size, args.size],
        target="c", num_of_bits=8, setting=settings, device="cpu",
        error_report=True, export_test_values=False,
    )
    if not model_path.is_file() or not model_path.stat().st_size:
        raise RuntimeError("Quantizer did not produce a model")
    manifest = {
        "model": "YOLO11n-Pose", "variant": "custom_low_resolution_raw_heads",
        "target": "c", "chip": "esp32", "bits": 8, "input_size": args.size,
        "calibration_images": args.calib_steps, "accuracy_validated": False,
        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "model_bytes": model_path.stat().st_size, "outputs": HEAD_NAMES,
        "packages": {name: importlib.metadata.version(name) for name in
                     ("torch", "ultralytics", "esp-ppq", "onnx")},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print("Accuracy is unvalidated. FPS is measured on the device, never inferred from this CPU quantization run.")


if __name__ == "__main__":
    main()
