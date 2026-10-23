"""Collect device timings; never treat capture-only or PC timings as ESP32 inference FPS."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import time


def summarize(info, rows):
    if not info or not rows:
        raise ValueError("No device metadata or measured frames; no FPS result")
    mode = info["mode"]
    if mode not in {"pose", "camera_only"} or any(row.get("mode") != mode for row in rows):
        raise ValueError("Mixed or unknown benchmark modes")
    previous_end = None
    for index, row in enumerate(rows):
        if row["frame"] != index or row["end_us"] <= row["start_us"]:
            raise ValueError("Missing/out-of-order frames or invalid timing")
        if previous_end is not None and row["start_us"] < previous_end:
            raise ValueError("Device reset or overlapping timestamps")
        previous_end = row["end_us"]
        for field in ("capture_us", "pre_us", "infer_us", "post_us"):
            if not isinstance(row[field], (int, float)) or not math.isfinite(row[field]) or row[field] < 0:
                raise ValueError("Invalid stage duration")
        if sum(row[field] for field in ("capture_us", "pre_us", "infer_us", "post_us")) > row["end_us"] - row["start_us"]:
            raise ValueError("Stage timings exceed total duration")
    span = rows[-1]["end_us"] - rows[0]["start_us"]
    result = {"device": info, "frames": len(rows), "observed_processing_fps": len(rows) * 1e6 / span,
              "inference_fps": None, "inference_ms_mean": None, "inference_ms_p95": None}
    if mode == "pose":
        times = [row["infer_us"] for row in rows]
        if min(times) <= 0 or not info.get("model_sha256") or info["model_sha256"] == "none":
            raise ValueError("Pose results require positive on-device inference times and a model hash")
        result.update(inference_fps=len(times) * 1e6 / sum(times),
                      inference_ms_mean=statistics.mean(times) / 1000,
                      inference_ms_p95=sorted(times)[math.ceil(0.95 * len(times)) - 1] / 1000)
    elif any(row["infer_us"] for row in rows):
        raise ValueError("Capture-only results cannot contain inference measurements")
    return result


def collect(port_name, timeout=600):
    import serial
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.5)
    connection.port = port_name
    connection.dtr = False
    connection.rts = False
    info, rows, raw = None, [], []
    try:
        connection.open()
        connection.rts = True
        time.sleep(0.1)
        connection.rts = False
        deadline = time.monotonic() + timeout
        complete = False
        while time.monotonic() < deadline:
            line = connection.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            raw.append(line)
            if line.startswith("BENCH_ERROR "):
                raise RuntimeError(line)
            if line.startswith("BENCH_INFO "):
                if info is not None:
                    raise RuntimeError("Device restarted; refusing to combine runs")
                info = json.loads(line[len("BENCH_INFO "):])
                print(line, flush=True)
            elif line.startswith("BENCH_ROW "):
                rows.append(json.loads(line[len("BENCH_ROW "):]))
                print(line, flush=True)
            elif line == "BENCH_DONE":
                complete = True
                break
        if not complete:
            raise TimeoutError("No BENCH_DONE; no complete benchmark result")
        return summarize(info, rows), raw
    except Exception as exc:
        exc.benchmark_info = info
        exc.benchmark_lines = raw
        raise
    finally:
        if connection.is_open:
            connection.dtr = connection.rts = False
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "results/local")
    args = parser.parse_args()
    summary, raw = collect(args.port, args.timeout)
    args.output.mkdir(parents=True, exist_ok=True)
    stem = time.strftime("%Y%m%d_%H%M%S")
    (args.output / f"{stem}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (args.output / f"{stem}.log").write_text("\n".join(raw) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
