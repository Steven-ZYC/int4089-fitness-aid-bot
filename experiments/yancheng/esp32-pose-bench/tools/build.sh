#!/usr/bin/env bash
# Run from an exported ESP-IDF 5.5.x environment, in Linux / WSL.
set -euo pipefail
base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-probe}
if [[ "$mode" != probe && "$mode" != pose ]]; then
    echo 'Usage: bash tools/build.sh probe|pose' >&2; exit 2
fi
if ! command -v idf.py >/dev/null; then
    echo 'First source the ESP-IDF export.sh (5.5.x, esp32 toolchain).' >&2; exit 2
fi
# ESP-IDF project paths must not contain spaces. Never move or delete the original checkout.
scratch=$(mktemp -d /tmp/int4089-pose-build.XXXXXXXX)
cp -R "$base/firmware" "$scratch/project"
if [[ "$mode" == pose ]]; then
    cp "$base/artifacts/model/yolo11n_pose.espdl" "$scratch/project/main/"
    cp "$base/artifacts/model/manifest.json" "$scratch/project/main/model_manifest.json"
    cat "$scratch/project/sdkconfig.pose.defaults" >> "$scratch/project/sdkconfig.defaults"
fi
cd "$scratch/project"
export IDF_TARGET=esp32
idf.py build
dest="$base/artifacts/build-$mode"
mkdir -p "$dest/bootloader" "$dest/partition_table"
cp build/yancheng_pose_bench.{bin,elf,map} build/flasher_args.json sdkconfig "$dest/"
cp build/bootloader/bootloader.bin "$dest/bootloader/"
cp build/partition_table/partition-table.bin "$dest/partition_table/"
if [[ "$mode" == pose ]]; then
    cp main/model_manifest.json "$dest/model_manifest.json"
fi
echo "BUILD_OUTPUT=$dest"
echo "BUILD_SCRATCH=$scratch"
