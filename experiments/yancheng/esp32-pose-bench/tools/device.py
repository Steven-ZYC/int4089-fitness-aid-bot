"""Probe, back up, flash and run a device benchmark, restoring the original firmware afterward."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from collect_metrics import collect

ROOT = Path(__file__).resolve().parents[1]
FLASH_BAUD = 230400


def esptool(port, *args):
    print("ESPTOOL_OPERATION=" + str(args[0]), flush=True)
    command = [sys.executable, "-B", "-m", "esptool", "--chip", "esp32", "--port", port,
               "--baud", str(FLASH_BAUD), *map(str, args)]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    folder = ROOT / "artifacts" / "device-logs"
    folder.mkdir(parents=True, exist_ok=True)
    log_path = folder / f"{time.time_ns()}_{args[0]}.log"
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        print("\n".join(completed.stdout.replace("\r", "\n").splitlines()[-12:]), flush=True)
        raise subprocess.CalledProcessError(completed.returncode, command)
    print("ESPTOOL_OK=" + str(args[0]) + " LOG=" + str(log_path), flush=True)


def backup(port):
    folder = ROOT / "artifacts" / "backups" / time.strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "original.bin"
    esptool(port, "read-flash", "0", "ALL", path)
    content = path.read_bytes()
    if len(content) != 4 * 1024 * 1024:
        raise RuntimeError("Expected this board's verified 4 MB flash; do not flash a different board")
    metadata = {"port": port, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return path


def validated_backup(path):
    path = Path(path)
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    content = path.read_bytes()
    if len(content) != metadata["bytes"] or hashlib.sha256(content).hexdigest() != metadata["sha256"]:
        raise RuntimeError("Backup hash/size verification failed; refusing to restore")
    return path


def restore(port, path):
    path = validated_backup(path)
    esptool(port, "write-flash", "0", path)


def flash_files(build_dir):
    build_dir = build_dir.resolve()
    manifest = json.loads((build_dir / "flasher_args.json").read_text(encoding="utf-8"))
    files = []
    previous_end = 0
    for address, relative in sorted(manifest["flash_files"].items(), key=lambda item: int(item[0], 0)):
        image = (build_dir / relative).resolve()
        if not image.is_relative_to(build_dir) or not image.is_file():
            raise ValueError("Flash manifest refers outside its build directory or to a missing file")
        start, end = int(address, 0), int(address, 0) + image.stat().st_size
        if start < previous_end or end > 4 * 1024 * 1024:
            raise ValueError("Overlapping or out-of-range flash images")
        files.extend((address, image))
        previous_end = end
    if not files:
        raise ValueError("Empty flash manifest")
    return files


def main():
    global FLASH_BAUD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe", "backup", "run", "restore"))
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baud", type=int, choices=(115200, 230400, 460800), default=FLASH_BAUD)
    parser.add_argument("--mode", choices=("probe", "pose"), default="probe")
    parser.add_argument("--backup-file", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    FLASH_BAUD = args.baud
    if args.action == "probe":
        esptool(args.port, "flash-id")
    elif args.action == "backup":
        print("BACKUP_FILE=" + str(backup(args.port)))
    elif args.action == "restore":
        if not args.backup_file:
            parser.error("restore requires --backup-file")
        restore(args.port, args.backup_file)
    else:
        images = flash_files(ROOT / "artifacts" / f"build-{args.mode}")
        if args.backup_file:
            saved = validated_backup(args.backup_file)
            # Compare the full flash on-device before reusing a backup from a previous run.
            esptool(args.port, "verify-flash", "0", saved)
        else:
            saved = backup(args.port)
        print("BACKUP_FILE=" + str(saved), flush=True)
        folder = ROOT / "results" / "local"
        folder.mkdir(parents=True, exist_ok=True)
        stem = time.strftime("%Y%m%d_%H%M%S") + "_" + args.mode
        try:
            esptool(args.port, "write-flash", *images)
            summary, raw = collect(args.port, args.timeout)
            (folder / f"{stem}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            (folder / f"{stem}.log").write_text("\n".join(raw) + "\n", encoding="utf-8")
            print(json.dumps(summary, indent=2), flush=True)
        except Exception as exc:
            failure = {"complete": False, "mode": args.mode, "reason": str(exc),
                       "device": getattr(exc, "benchmark_info", None), "inference_fps": None}
            (folder / f"{stem}_failed.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
            (folder / f"{stem}_failed.log").write_text("\n".join(getattr(exc, "benchmark_lines", [])) + "\n", encoding="utf-8")
            raise
        finally:
            # A failed/OOM model run must not strand the existing working camera firmware.
            print("RESTORING_ORIGINAL_FIRMWARE", flush=True)
            restore(args.port, saved)


if __name__ == "__main__":
    main()
