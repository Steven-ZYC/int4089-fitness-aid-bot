[English](usb-camera.md) | [简体中文 / 原文](usb-camera_zh_cn.md) | [繁體中文（香港）](usb-camera_zh_hk.md)

<a id="cam--电脑-usb-图像控制协议"></a>

# CAM ↔ PC USB image/control protocol

Current firmware: [Cam_USB_Bridge](../../firmware/usb-ai-bridge/Cam_USB_Bridge/Cam_USB_Bridge.ino). PC implementation: [serial_camera.py](../../app/serial_camera.py).

<a id="串口与图像"></a>

## Serial link and images

921600 baud, 8N1, no flow control. Images are 640×480 JPEG, quality=18, with two PSRAM buffers in LATEST mode. Camera/S3 pins and wireless MACs are unchanged by the repository organization task.

At startup, the PC sends `INFO\n` and requires `fw=Cam_USB_Bridge_v1`. Each cycle then batches three commands; firmware responds in order:

```text
ALARM 0\n       # Or ALARM 1; 0=alarm OFF, 1=ON
STATUS\n
CAPTURE\n
```

Response order:

```text
CMD_OK state=0
BRIDGE role=CAM state=... ack=... ack_state=... ack_age_ms=... errors=... drops=...
META seq=... request_us=... frame_us=... acquired_us=... discarded=... width=640 height=480 len=N
IMG N crc=xxxxxxxx
<N raw JPEG bytes>
\nDONE seq=... written=N send_us=...
```

Here `\n` means LF; `N` and ellipses are placeholders, not literal transmitted text. CRC is an eight-digit hexadecimal CRC32 of the raw JPEG bytes. Base64 is not used. Read the exact binary length, then verify CRC, JPEG markers, decoded dimensions, trailer sequence and length. Do not treat JPEG as line-oriented text.

Text such as `READY` may appear outside frames. The wireless task never writes CAM USB, preventing asynchronous logs from entering images. A single PC worker owns the serial port.

<a id="新鲜度与报警"></a>

## Freshness and alarms

- At acquisition, accept only images whose first-DMA timestamp is no more than 200ms old. This is neither exposure time nor full web-display latency. The older snapshot baseline required capture after the request; current double buffering uses the most recently completed frame.
- PC-cached images older than 1.5 seconds are unavailable; inference skips duplicate sequences.
- If a PC decision is not refreshed for one second, the worker sends OFF. CAM also sends OFF after 1.2 seconds without a valid PC alarm command.
- `CMD_OK` means CAM parsed the command; wireless ACK indicates S3 receipt. USB errors terminate the worker, after which endpoint timeouts clear stale alarms.
- Automatic reconnection is not implemented. Re-identify the port and restart after disconnection.

<a id="性能"></a>

## Performance

Measured 268 frames/30 seconds, about 8.93 FPS; AI page about 9 FPS. Scene detail/lighting affect JPEG size and rate. CRC, decoding and trailer checks remain enabled.

The PC can explicitly select the historical rate with `serial://COM3?baud=460800`, but this changes only PC configuration: firmware must match. Default remains 921600 without automatic baud switching.
