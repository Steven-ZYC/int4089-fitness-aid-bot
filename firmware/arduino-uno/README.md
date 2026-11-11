[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="arduino-unoled-与蜂鸣器"></a>

# Arduino: LED and buzzer

Task status: **retained Arduino basic-control instructions**.

Original owner: **Zhang Haoyu**, whose focus moved to [model-training research](../../models/README.md). This file no longer describes his primary current task.
Zhang Yancheng coordinates hardware integration.

Historical task branch: **`Feat-Arduino-Haoyu`**, case-sensitive; it continues to hold Haoyu's model-training research.

Read root `AGENTS.md`, explicitly confirm the current user's identity and check the branch before starting.
If identity is unknown, ask first. Modify only after confirming the member and their assigned branch.
Make changes, commits and pushes on your own branch; do not commit directly to `main` or another member's branch.

<a id="保留的硬件目标"></a>

## Retained hardware objective

Wire LED and buzzer to **Arduino** and demonstrate independent basic control.
This directory is currently a task description; firmware and wiring have not been provided or verified here.

<a id="交付与验收"></a>

## Delivery and acceptance

1. Provide clear wiring records: components, actual pins, power/GND, required parts and photos or diagrams.
2. Provide a flashable minimal example: LED ON/OFF and buzzer start/stop by command.
3. Record actual board behavior so others can reproduce it.
4. Distinguish measured work from pending confirmation; do not present expectations as observations.

<a id="随交付记录"></a>

## Required delivery records

- Actual Arduino model/revision, LED type and buzzer type.
- Complete pin map, supply method and actual resistors/other components.
- Arduino IDE version, board selection, board package version and upload-port identification.
- Libraries/versions, or explicitly no additional libraries.
- Reproduction steps from opening, compiling and flashing through operating LED/buzzer.
- Observed behavior, failure symptoms and troubleshooting.

If hardware, pins, voltages or component types are unconfirmed, record them as pending rather than guessing wiring.
Arduino handles local LED/buzzer control and is to connect physically to **ESP32-CAM**. A separate **ESP32-S3 N16R8** is planned as the main ESP for Bosch BMI-series IMU and PC networking. **AI training/inference currently run on the team PC**, with cloud HPC considered only after a viable prototype. AI-result return routing, pins and electrical design remain pending integration validation. Earlier on-S3 inference and RDK X5 plans are no longer the main route.
Do not commit Wi-Fi keys, credentials or identifiable portraits.
