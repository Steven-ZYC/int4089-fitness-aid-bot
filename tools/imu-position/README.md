[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="imu-零飘处理--windows-位置面板"></a>

# IMU drift handling · Windows position panel

Zhang Yancheng's (`Feat-Integration-Yancheng`) PC tool reads 15-column six-axis CSV from ESP32-S3 + BMI160 over USB serial. A drift profile drives bias removal, stationary detection (ZUPT), complementary filtering and position integration. Two pages display processed source data and 3D attitude/position.

> **Status (2026-11-05):** live serial reception passed locally on COM4: 49.73 Hz after reset, CONFIG 0x69, zero malformed lines. Calibration, algorithms, replay and UI were verified.

**Observed:** if ESP32-S3 has no serial reader for a long time or a previous tool leaves it reset, the port opens but emits **no bytes** (zero bytes in six seconds locally). By default the panel pulses RTS, connected to CH340 EN, after opening. `ESP-ROM` and `# BMI160_SIX_AXIS_START` then appear immediately. If the board is already streaming, uncheck reset-on-connect.

<a id="零飘实测firmwareesp32-cameraevidenceyancheng-2026-11-05capturecsv"></a>

## Measured drift (`firmware/esp32-camera/evidence/yancheng-2026-11-05/capture.csv`)

Stationary 30.061 s, 1496 samples, 49.732 Hz, COM4 / address 0x69, uncalibrated.

| Item | Measurement |
| --- | --- |
| Gyro zero bias (stationary mean) | gx **−0.2394**, gy **−0.3691**, gz **+0.2943** °/s |
| Bias stability | Six 5-second block means vary ±0.005 °/s; Allan deviation (5 s) ≈0.0015 °/s |
| Uncorrected error | 30-second direct integration drifts −7.2° / −11.1° / +8.9°; corrected residual std ≈0.029 °/s |
| Acceleration | Mean (−0.0745, −0.0866, +0.9976) g, magnitude 1.00422 g; mounting roll −4.96°, pitch +4.31° |
| Holdout validation (last 15 s) | Residual mean ≤0.0011 °/s, vector RMS 0.0321 °/s; threshold 0.1 °/s, pass |

Measured `scripts/replay.py` output: 96.7% stationary classification (first 49 samples warm up the detector window), bias-corrected residual ≈0, **position remains 0.00 cm**, attitude converges to roll −4.96° / pitch +4.32°.

The acceleration mean **is not zero bias**: it includes gravity and mounting tilt and must be retained. This tool subtracts gyro bias only.

<a id="安装与运行windows"></a>

## Windows installation and operation

Dependencies are PySide6 / numpy / pyserial in an independent venv (created locally with Anaconda 3.9; PySide6 6.9.3 supports Python 3.9–3.13):

```powershell
cd tools\imu-position
D:\Anaconda\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the panel; it defaults to the calibrated `profiles/yancheng-2026-11-05-static.json` in the repository:

```powershell
.\.venv\Scripts\python.exe -m imu_position
```

Two pages: **1. Source data after drift handling** plots corrected gyro, acceleration relative to the stationary reference and acceleration magnitude, highlighting stationary intervals pale green. **2. 3D position** shows a body-axis box, gravity direction, velocity and position trajectory. The top bar connects serial or replays CSV. Settings / Import / Calibration opens profile management for JSON import/export, parameter editing and recalibration from stationary CSV.

<a id="实时串口"></a>

### Live serial

1. Close Arduino serial monitor/plotter and `capture_bmi160.ps1`; COM ports are exclusive.
2. Select the port (COM4 locally), enable reset-on-connect, then connect.
3. Status progresses through reset → `ESP-ROM…` → `# CONFIG firmware=BMI160_SixAxis_v3_autoaddr address=0x69`. If no samples arrive for five seconds or the reader stops, diagnostics show line counts, ignored/malformed lines and port-use hints.
4. `# FATAL` or `read_errors>0` disconnects the panel and displays a warning.

<a id="串口诊断无界面"></a>

### Headless serial diagnosis

For connected-but-no-data symptoms, first run:

```powershell
.\.venv\Scripts\python.exe scripts\probe_serial.py -p COM4 -t 6
```

Exit codes: 0=samples received; 2=port opens but no bytes (hung board/port/firmware); 3=bytes but no valid samples (firmware/baud mismatch).

<a id="回放"></a>

### Replay

Replay CSV plays any capture at its original 49.73 Hz cadence through the same parser/processing path as live data, without hardware.

<a id="命令行"></a>

## Command line

Run from `tools\imu-position`:

```powershell
# Calibrate from stationary data; reject and explain failed gates
.\.venv\Scripts\python.exe scripts\calibrate.py ..\..\firmware\esp32-camera\evidence\yancheng-2026-11-05\capture.csv -o profiles\yancheng-2026-11-05-static.json

# Headless replay/drift metrics: 0 pass, 2 invalid profile, 3 insufficient stationary fraction, 4 stationary position drift
.\.venv\Scripts\python.exe scripts\replay.py ..\..\firmware\esp32-camera\evidence\yancheng-2026-11-05\capture.csv --profile profiles\yancheng-2026-11-05-static.json

# Unit tests (49, including offscreen UI smoke test)
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

<a id="profile-文件json"></a>

## Profile files (JSON)

`profiles/*.json` is the sole drift-parameter source. It stores source metadata (CSV path, SHA256, rows, duration, rate, port, address), ranges/scales, gyro bias, acceleration mean and mounting tilt, stationary thresholds, complementary-filter α, integration settings and holdout validation. `validate()` is mandatory before writing. Calibration gates follow upstream `check_bmi160_gyro_bias.ps1`:

- 45–55 Hz acquisition, no saturation or sequence gaps;
- acceleration magnitude 0.85–1.15 g, per-axis std ≤0.02 g, gyro std ≤0.2 °/s, |gyro mean| ≤5 °/s;
- second-half holdout residual mean and RMS ≤0.1 °/s.

Profiles with `gate_pass=false` appear in a warning color.

<a id="算法与已知局限"></a>

## Algorithms and limitations

- **Bias correction:** `gyro_corr = gyro − gyro_bias`; do not subtract the entire acceleration mean.
- **Stationary detection (ZUPT):** within a one-second window, acceleration-magnitude std <0.05 g, corrected gyro-magnitude std <0.15 °/s, gyro magnitude <1.0 °/s and acceleration magnitude 0.9–1.1 g imply stationary. Zero velocity and freeze position. Do not integrate during incomplete-window warm-up.
- **Attitude:** complementary filtering (α=0.98) combines acceleration roll/pitch and integrated gyro rates. BMI160 has **no magnetometer**, so **yaw is unobservable** and drifts in motion. Set yaw rate to zero while stationary to avoid noise accumulation.
- **Position:** trapezoidally integrate gravity-subtracted body-frame acceleration twice for velocity/position. ZUPT holds the stationary origin, but **double-integrated position inevitably drifts during motion**. This is not precision positioning; it suits quasi-static/intermittent-motion demos.
- `t_read_us` is read-start time, not an exact sampling instant. `sensor_ticks` is 24-bit and wraps about every 655.36 s; this tool uses `t_read_us` differences for timing.

<a id="目录"></a>

## Layout

```text
imu_position/   profile.py csvio.py pipeline.py calibration.py
                serial_reader.py replay.py __main__.py
                ui/ (panels.py scene3d.py profile_dialog.py main_window.py)
scripts/        calibrate.py replay.py probe_serial.py
profiles/       yancheng-2026-11-05-static.json
tests/          test_profile / test_csvio / test_pipeline / test_serial_parse /
                test_calibration / test_ui_smoke
```

Git ignores `.venv/` and `captures/`; do not commit acquired data.
