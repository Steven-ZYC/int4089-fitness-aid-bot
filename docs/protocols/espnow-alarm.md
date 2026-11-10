[English](espnow-alarm.md) | [简体中文 / 原文](espnow-alarm_zh_cn.md) | [繁體中文（香港）](espnow-alarm_zh_hk.md)

<a id="cam--s3-esp-now-报警协议"></a>

# CAM ↔ S3 ESP-NOW alarm protocol

Shared implementation: [AlarmRadio.h](../../firmware/usb-ai-bridge/AlarmRadio.h). This link carries only alarm states and application acknowledgements. Images always use CAM USB.

<a id="无线配置与帧结构"></a>

## Wireless configuration and packet layout

Station mode without a router connection; channel 1; fixed current CAM/S3 peer MACs. Verify MACs and recompile after replacing boards. The current link is an unencrypted local prototype.

| Field | Bytes | Purpose |
| --- | ---: | --- |
| magic | 4 | `0x41493438`, protocol identifier |
| boot | 4 | Random CAM boot identifier, echoed by ACK |
| seq | 4 | Increasing CAM sequence, echoed by ACK |
| version | 1 | Currently 1 |
| kind | 1 | 1=command, 2=application ACK |
| alarm | 1 | 0=OFF, 1=ON |
| reserved | 1 | Must be 0 |
| crc | 4 | CRC32 over the first 16 bytes |

The packed structure totals 20 bytes; integers are little-endian on these ESP platforms. Validate source MAC, length, magic, version, reserved byte, state and CRC. CRC checks errors, not identity.

<a id="状态确认与超时"></a>

## State, acknowledgement and expiry

- CAM sends its valid state every 200ms. If the PC command is not refreshed for 1.2 seconds, send OFF.
- After accepting a valid command, S3 echoes boot, seq and alarm, changes kind to 2 and recalculates CRC.
- Duplicate/old sequences within one boot identifier do not renew the S3 timeout. A new boot identifier permits sequence restart; this distinguishes prototype sessions, not secure replay protection.
- CAM tracks increasing ACKs matching its current boot and sent sequence range. Diagnostics expose the latest ACK sequence, state and time.
- S3 turns OFF after 1.2 seconds without a valid command and writes `110` (ON) or `101` (OFF) to Mega UART every 200ms. Wireless reception/relaying runs independently; BMI160 initialization failure does not block it.

**Acknowledgement ends at S3.** One-way UART has no Mega reply, so wireless ACK does not prove physical light/buzzer execution. Mega retains source/XOR validation, PC USB priority and a 1.5-second timeout. See the [alarm protocol](alarm-control.md).

ESP-NOW still uses 2.4GHz airtime for approximately five commands and corresponding ACKs per second. This reduces wireless data volume, not all effects on other wireless devices.
