[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="ai-模型与电脑端分析prototype"></a>

# AI models and PC analysis (prototype)

Owner: **Zhang Haoyu**. Assigned branch: **`Feat-Arduino-Haoyu`**, a historical name; the current task is not mainly Arduino firmware.

Read root [AGENTS.md](../AGENTS.md), confirm identity, assigned branch and worktree state. Modify/commit only on your own branch and request a PR merge into `main`.

<a id="最新任务2026-10-30-consultation-后"></a>

## Latest task after the 2026-10-30 consultation

**AI inference initially runs on the team PC; deployment on ESP32 is not required.** Dong Yuankun's dual-ESP32 system supplies data: ESP32-CAM images and motion data from a Bosch BMI-series IMU on the main ESP32-S3, which also handles PC networking.

This directory should progressively establish a reproducible **dataset selection → training/validation → PC inference → posture-result output** workflow. Cloud HPC/GPU migration may be considered after prototype validation; do not describe it as deployed now.

<a id="当前交付要求"></a>

## Current delivery requirements

1. **Task definition:** specify supported exercises, criteria for incorrect form, outputs such as keypoints/action classes/error types, and observable evaluation metrics. Generic human-pose detection is not equivalent to assessing correct form.
2. **Dataset research/selection:** compare action coverage, pose annotations, licenses, scale, availability and quality. Record download/annotation procedures and training/validation/test splits without leakage. If a dataset cannot directly support correct/incorrect form labels, describe annotation or transfer plans.
3. **Training/validation:** establish a minimum baseline, retaining versions, environment, hyperparameters, preprocessing and results. If not working, label it untrained rather than forecasting accuracy.
4. **PC inference service:** implement image input, inference, postprocessing and output runnable on the team PC. Agree with Yuankun on network message formats, camera-frame and IMU-timestamp interfaces.
5. **Fusion strategy/metrics:** state whether v1 is image-only or image+IMU. Mark fusion as unimplemented if so. Record model latency, effective FPS and integration-related end-to-end latency.
6. **Integration delivery:** define result structures with usable action, timestamp, confidence/threshold and feedback fields, examples and instructions so Yancheng can connect Arduino Uno LED/buzzer feedback.

<a id="协作接口"></a>

## Collaboration interfaces

- With **Dong Yuankun**: agree image formats, IMU units/axes, timestamps, transfer rates/fault handling and PC reception.
- With **Zhang Yancheng**: confirm prototype scope, interfaces and test scenarios; output structured normal-posture/reminder-needed messages for the hardware loop.
- Historical ESP32-S3 on-device deployment and RDK X5 NPU are no longer deliverables for this phase.

This is a task description, **not evidence of selected datasets, successful training, measured model performance or a completed PC service**. Do not commit identifiable portraits, unauthorized data or credentials. Manage weights/training data according to ignore rules and licenses.
