[English](POSE.md) | [简体中文 / 原文](POSE_zh_cn.md) | [繁體中文（香港）](POSE_zh_hk.md)

<a id="动作规范实时判定电脑端-ai"></a>

# Real-time exercise-form assessment (PC AI)

ESP32-CAM capture → PC pose estimation → geometric form rules → live web display.

This is the first implementation of form assessment. Earlier `esp32_cam_app` only answered whether a person was present. The project needs to determine **whether that person's exercise form is correct**. This directory adds that stage through `pose_app.py`, sharing `sources.py` with the detection-only `app.py`.

<a id="方案"></a>

## Approach

```
ESP32-CAM --MJPEG--> PC
                     |-- YOLOv8n-pose -> 17 COCO keypoints
                     |-- Angles -> knee / elbow / torso tilt / left-right difference
                     |-- Action rules -> thresholds + violations
                     `-- State machine -> repetitions, assessment at the bottom
                              |
                     Web UI (skeleton + angles + decision)
```

**Why rules rather than end-to-end classification**

| | Rule-based approach (this implementation) | End-to-end classification |
| --- | --- | --- |
| Explain what is wrong | Yes, item by item | Only labels form as incorrect |
| Labeled data required | No | A large amount |
| Adjustable thresholds | Yes | No |
| Support another action | Add thresholds | Retrain |

First close the loop using rules, then use real data to decide whether a classifier is needed for further calibration.

<a id="文件"></a>

## Files

| File | Description |
| --- | --- |
| `pose_engine.py` | YOLOv8n-pose wrapper producing 17 keypoints; choose the largest box with multiple people |
| `form_rules.py` | Angle calculations, squat/pushup rules and repetition state machine |
| `pose_app.py` | Inference pipeline and web UI with skeleton, angles and decision panel |
| `sources.py` | Video sources: local camera / ESP32 MJPEG stream |
| `test_rules.py` | Synthetic-keypoint rule tests, independent of camera hardware |

<a id="运行"></a>

## Run

```bash
# Use ESP32-CAM; add --rotate if mounted sideways
python pose_app.py --source http://<ESP32_IP>/stream --rotate 270 --action squat

# Use the local camera
python pose_app.py --action pushup

# Rule-engine tests, no hardware required
python test_rules.py

# Run N frames without UI and save a diagnostic image
python pose_app.py --self-test 40 --action squat
```

UI: `http://127.0.0.1:8010`

<a id="拍摄要求很关键"></a>

## Framing requirements (critical)

Rules calculate angles from keypoints. **Missing required keypoints prevent assessment**:

1. **The whole body must be visible**. Squats require ankles; an upper-body crop cannot produce knee angles.
2. **Use a distance of 2–3 meters**, with the person occupying over 60% of image height.
3. **A side view or 45° front view is ideal**. A pure front view hides forward torso lean; a pure side view hides left/right symmetry.
4. **Avoid backlighting**. Silhouettes cause ESP32-CAM keypoints to disappear.

At the time of this note, the camera showed only arms or the ceiling, so knee angles stayed `None` and the phase stayed not started. This was a framing issue rather than an algorithm issue.

<a id="判定规则阈值都可改见-squat_cfg--pushup_cfg"></a>

## Assessment rules (adjustable in `SQUAT_CFG` / `PUSHUP_CFG`)

**Squat**

| Metric | Threshold | Violation |
| --- | --- | --- |
| Minimum knee angle | ≤ 105° | Insufficient depth |
| Torso tilt | ≤ 45° | Excessive forward lean (possible lower-back collapse) |
| Left/right knee angle difference | ≤ 20° | Asymmetry / compensation |

**Pushup**

| Metric | Threshold | Violation |
| --- | --- | --- |
| Minimum elbow angle | ≤ 95° | Insufficient range |
| Shoulder–hip–ankle alignment | ≥ 160° | Body not straight (sagging or raised hips) |

Repetition logic uses EMA-smoothed knee/elbow angles to drive the state machine: standing → descending → bottom → rising → standing. Count a repetition on return to standing, tracking minimum angle and maximum tilt throughout the motion.

**Note:** an initiated descent can count when completed even if shallow. Otherwise the insufficient-depth violation that most needs feedback would be missed. Unit tests revealed this bug.

<a id="测试结果"></a>

## Test results

`python test_rules.py` passes all synthetic-keypoint cases reproducibly:

```
[PASS] 角度计算
[PASS] 标准深蹲 计次=1 最低膝角=90.9 分数=100
[PASS] 浅蹲 违规=['下蹲深度不足：最低膝角 131°，建议 ≤105°']
[PASS] 躯干前倾 违规=['躯干前倾过大：63°，建议 ≤45°（易塌腰）']
[PASS] 俯卧撑 计次=1 最低肘角=93.2
[PASS] 塌腰 违规=['身体没成一条线：最小 152°，建议 ≥160°（塌腰或撅臀）']
```

Performance: YOLOv8n-pose inference **7 ms/frame** on RTX 5080, imgsz 480. End-to-end rate was limited by ESP32 streaming to about 7–16 FPS.

<a id="输出数据结构后续回传给-esp32--arduino-用"></a>

## Output structure (for later ESP32 / Arduino feedback)

```json
{
  "action": "深蹲",
  "phase": "底部",
  "reps": 3,
  "angles": {"膝角": 92.0, "躯干倾角": 18.0, "左右差": 4.0},
  "last": {
    "rep": 3,
    "ok": false,
    "violations": ["下蹲深度不足：最低膝角 131°，建议 ≤105°"],
    "score": 75
  }
}
```

`/stats` returns this structure directly. It could also be sent over serial/UDP to Arduino for LED/buzzer control.

<a id="已知限制"></a>

## Known limitations

- **Monocular 2D rules** cannot assess issues such as knee valgus requiring precise frontal/top-down views; only knee angles, tilt and symmetry are assessed.
- Keypoint jitter can produce ±5° angle variations. EMA smoothing reduces jitter but adds lag.
- Only squat and pushup are supported; deadlift/bench-press rules must be added.
- Torso tilt is meaningful in a side view but largely ineffective in a front view.
- Thresholds are based on general exercise knowledge and **have not been calibrated with real data**.

<a id="下一步"></a>

## Next steps

1. Calibrate thresholds with real squat videos, recording 10–20 repetitions and examining angle distributions.
2. Add action recognition to select squat or pushup rules automatically.
3. Send decisions over UDP/serial to Arduino to close the loop.
4. Evaluate classifier training only if finer violations such as knee valgus or weight shifts are required.
