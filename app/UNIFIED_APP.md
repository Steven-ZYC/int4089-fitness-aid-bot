# Unified PC application

[English](UNIFIED_APP.md) | [简体中文](UNIFIED_APP_zh_cn.md) | [繁體中文（香港）](UNIFIED_APP_zh_hk.md)

The current PC entry point is `app/main.py`. One local service and browser page combine the previous vision web app and IMU Windows panel. Older standalone entry points remain available; the IMU algorithms are reused rather than copied.

## Run

From the repository root, using the existing project venv:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File app/run_pose.ps1 -CamPort COM3 -ImuPort COM4 -Action squat
```

Or from `app/`:

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py --source serial://COM3 --imu-port COM4 --action squat --no-browser
```

Open http://127.0.0.1:8010 . `-Action pushup` selects pushups. An empty `-ImuPort ''` skips automatic IMU connection. Confirm port identities after reconnecting USB. Only one process can own each serial port; stop standalone tools before using the unified app.

## Four views

- **Overview:** real camera images, pose/rule feedback, repetition count, alarm state, IMU summary and wireless ACK.
- **3D attitude and position:** body axes, gravity, velocity, integrated position trail, view angle/zoom, reference orientation and position reset.
- **IMU signal charts:** corrected gyro, acceleration relative to the stationary profile, acceleration magnitude and stationary intervals.
- **Connections, replay and calibration:** S3 connect/disconnect, optional reset, uploaded or historical CSV replay, pause/resume, profile JSON import/export/editing and stationary-CSV calibration.

The IMU source is explicitly labelled live or replay. Replay affects only IMU visualization; live vision continues independently and may still trigger its normal alarm. Replaying CSV does not generate alarms or establish live IMU hardware health.

## Implementation boundaries

- `main.py`: unified HTTP server, module lifecycle, JSON control endpoints and page assets.
- `web/index.html`, `web/styles.css`, `web/dashboard.js`: responsive dashboard and canvas charts/3D projection; no external UI/CDN dependency.
- `imu_service.py`: threaded adapter reusing `tools/imu-position/imu_position` for parsing, drift processing, profiles, replay and calibration. No PySide6 dependency is needed for this web adapter.
- `pose_app.py`: existing vision pipeline reused by the unified app; action changes are applied inside the inference thread.
- `serial_camera.py`: still exclusively owns CAM USB; startup probes tolerate ROM noise and can attempt one CAM reset if identity does not respond. The page exposes manual camera reconnection after disconnection.

Camera settings remain 640×480, JPEG18, two LATEST buffers and 921600 baud. The ESP-NOW/UART/Mega protocols and flashed firmware are unchanged. Default S3 connection does not reset it; the UI explains that an explicit reset briefly interrupts its radio relay.

Profile edits/calibration take effect only in the application session. Export JSON to retain them; repository profiles are never overwritten. Uploaded CSV is validated using the original parser/gates and processed through temporary local files. No raw camera frames are saved by this integration.

## API and tests

`GET /api/state?after=N` combines vision state with IMU source/status, latest processed sample and incremental history. `/stats` and `/video` remain compatible. `GET /api/ports` lists serial ports; `/api/profile` exports the active profile. JSON POST endpoints control IMU sources, replay, origin/filter resets, profile updates/calibration and vision action/reconnection.

Controls are bound to localhost, require JSON and reject unrelated browser origins. The camera port cannot also be selected as the IMU port. Invalid CSV/profile input does not replace the active valid source/profile.

From `app/`, run these with `.venv/Scripts/python.exe`:

```powershell
.\.venv\Scripts\python.exe -X utf8 test_imu_service.py
.\.venv\Scripts\python.exe -X utf8 test_unified_api.py
.\.venv\Scripts\python.exe -X utf8 test_serial_camera.py
.\.venv\Scripts\python.exe -X utf8 test_rules.py
```

See [architecture](../docs/architecture/README.md), [USB protocol](../docs/protocols/usb-camera.md) and [original IMU application](../tools/imu-position/README.md). Original `_zh_cn` documentation snapshots from the language migration remain unchanged; this guide describes the new unified entry point.

## Current validation scope

Service/API/transport/rule tests pass. Browser checks cover explicitly labelled historical CSV replay, pause, signals and 3D display alongside real camera inference and S3 ACKs. The IMU currently has no valid live samples and still needs wiring inspection. Replay is software validation only. Real exercise accuracy, the new loop's physical light/sound output and physical disconnect/power-loss acceptance remain pending. Position double integration drifts during motion; yaw has no magnetometer reference.
## Automatic camera orientation

The unified app defaults to automatic 0°/90°/180°/270° correction and selfie mirroring. Stand upright briefly, with shoulders, hips and naturally lowered hands visible. Three consistent, sufficiently distinct orientation scans are required before locking. Initial scanning adds inference work; after locking, the app uses only the normal pose pass.

Correction is locked during exercise, so squats, forward lean and pushups do not continuously rotate the video. After physically repositioning the camera, use **Recalibrate direction**. With insufficient/ambiguous body evidence, the app retains the previous angle and pauses repetition assessment/alarms until calibration succeeds; it does not guess.

The page offers automatic mode, fixed 0°/90°/180°/270° overrides and a selfie mirror switch. Mirroring is enabled by default for front-facing use; disable it for a conventional camera view or when filming from behind. Rotation alone cannot determine the preferred left/right mirroring convention.

Both correction and mirroring occur before pose inference and overlay rendering, keeping the displayed image and rule coordinates consistent. A direction change clears the incomplete repetition/alarm while retaining completed repetitions. This handles quarter-turn mounting, not continuous arbitrary tilt stabilization.

CLI overrides: `main.py --rotate 90` fixes a clockwise quarter turn; `--no-mirror` disables selfie mirroring. The old standalone pose_app.py retains its manual defaults. USB bandwidth, JPEG parameters, firmware and alarm protocols are unchanged. Tests include all four source orientations using the installed public Ultralytics bus.jpg asset; no user camera images are saved.

## Interface languages

Use the header language selector for English (`en`), Simplified Chinese (`zh-CN`) or Traditional Chinese, Hong Kong (`zh-HK`). The browser saves your preference locally; the first visit follows the browser language. No external translation service is used.

`web/locales.json` is the shared catalog; `web/i18n.js` translates static labels, dynamic states, chart messages and feedback without changing protocol values. `localization.py` uses the same catalog for video overlays. Raw firmware diagnostics and profile JSON stay intact. The camera stream is shared, so the latest language selection also applies to its overlays for all local viewers.

The three 1920 × 1080 screenshots in `docs/assets/` show the real disconnected-device state and are embedded in the matching root README editions.
