# USB camera -> PC AI -> CAM -> ESP-NOW -> S3 -> Mega

This is the current integrated prototype. Images never travel over Wi-Fi or ESP-NOW.

## Firmware and hardware

- CAM: `Cam_USB_Bridge/Cam_USB_Bridge.ino`, AI Thinker ESP32-CAM / OV2640.
  USB serial 460800 8N1. Camera pins follow the already measured USB camera baseline.
- S3: `S3_IMU_Alarm_Bridge/S3_IMU_Alarm_Bridge.ino`, ESP32-S3 N16R8.
  Reuses existing BMI160 acquisition on GPIO4 SDA / GPIO5 SCL, automatic 0x68/0x69.
  USB 115200 emits 15-column IMU CSV plus `#` diagnostics.
- S3 GPIO17 TX -> Mega D19 RX1, common GND; no Mega TX connection.
  Mega firmware remains `firmware/alarm-mega/Mega_Alarm_RX` (D8 LED, D9 buzzer).
- `AlarmRadio.h` has the verified CAM/S3 peer MACs for this hardware pair. Changing
  boards requires updating these peer addresses and recompiling both roles.

## USB image/control framing

PC requests INFO, then repeats: ALARM 0/1 -> CMD_OK; STATUS -> BRIDGE; CAPTURE.
Camera response: META line with sequence and frame times; IMG length crc=xxxxxxxx;
exactly length JPEG bytes; LF; DONE with matching sequence and length.
No radio callback/task writes USB text while a JPEG is in flight.
CRC32, JPEG markers, decoded VGA dimensions and sequence/trailer are checked on PC.
Only one worker owns the serial port; UI/inference receives the latest valid frame.
Frames older than 1.5s are unavailable; USB errors close transport and clear alarm.

## Small ESP-NOW commands

Channel 1, station mode, no router connection. Fixed peer unicast packets are 20 bytes:
magic (u32), boot session (u32), sequence (u32), version/kind/alarm/reserved (u8 each),
CRC32 (u32). Little endian on these ESP targets. Kind 1=command, 2=application ACK.
CRC covers the first 16 bytes. S3 checks source MAC, length/version/CRC/state and
fresh sequence; duplicate packets do not renew the lease. CAM tracks matching ACKs.
The link is unencrypted, intended for this bench prototype, not authenticated control.
No JPEG bytes are sent over ESP-NOW. 5 command packets per second plus ACKs still
use 2.4GHz airtime; this reduces wireless volume rather than eliminating coexistence.

PC decisions are refreshed while inference remains active. A decision older than 1s
becomes OFF in the PC worker. CAM expires PC commands after 1.2s; S3 expires radio
commands after 1.2s. S3 sends `110` or `101` every 200ms over UART at 9600 to Mega.
The existing Mega watchdog and direct-PC priority semantics remain unchanged.
ACK confirms S3 accepted the radio command, NOT that Mega or physical outputs worked.

## Computer setup and run (PowerShell from app/)

The tested local environment reuses installed AI libraries in a project venv and
installs a local pyserial to avoid a conflicting globally installed `serial` package:

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --ignore-installed pyserial==3.5
.\.venv\Scripts\python.exe -X utf8 pose_app.py --source serial://COM3 --action squat --no-browser
```

For a fresh environment, install `app/requirements.txt` as well. Current machine:
torch 1.12.1+cu116, ultralytics 8.3.141, RTX 4060 Laptop; the model smoke test
passed on this installed environment. Declared requirements are for fresh installs,
not an exact export of the tested legacy environment. Model weights download from
official Ultralytics assets on first use and remain ignored by Git.

Open http://127.0.0.1:8010 . Use `--action pushup` for pushups; action is not automatic.
One valid completed repetition with violations triggers a 2-second alarm event.
Missing required pose landmarks clear the alarm; sustained loss resets partial rep
state. This is rule-based feedback, not a calibrated exercise safety assessment.
Camera needs full body in view. Actual exercise accuracy is not established by tests.

## Build/upload

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32cam --upload --port COM3 firmware/usb-ai-bridge/Cam_USB_Bridge
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200 --upload --port COM4 firmware/usb-ai-bridge/S3_IMU_Alarm_Bridge
```

Run these from repo root; confirm ports before uploading. Upload replaces current
firmware; standalone snapshots/tests remain available in their original directories.

## Tests

From app/, use venv python:
- `test_rules.py`: original synthetic movement rules.
- `test_serial_camera.py`: synthetic JPEG, CRC corruption and trailer mismatch.
- `check_usb_bridge.py --cam COM3 --s3 COM4`: real hardware; intentionally commands
  ON briefly, verifies OFF/ON/decision-expiry ACK and S3 state plus concurrent IMU.
  Metrics saved under ignored firmware/usb-ai-bridge/captures; no image saves.

Visible/audible Mega acceptance, physical disconnect tests and real exercise accuracy
need on-site verification. Single-shot USB tests and old ESP-NOW image transport
experiments are historical baselines, not this active transport design.

Current acceptance: USB/ESP-NOW command stages passed, approximately 1.9-2.3 USB FPS. IMU has no response at 0x68/0x69 before radio initialization; user will inspect wiring. Overall concurrent-IMU test is intentionally marked failed until sensor data returns. See docs/validation/2026-11-10-usb-espnow-bridge.json.
