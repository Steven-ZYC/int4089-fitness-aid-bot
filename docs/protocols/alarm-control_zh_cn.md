# Modular alarm controller: USB PC or UART ESP32-S3

Owner: Zhang Yancheng / Feat-Integration-Yancheng. Arduino controls LED D8
(via 220 ohm) and passive buzzer D9 together. Set ACTIVE_BUZZER=true for an
active low-current buzzer. Higher-current buzzers need a driver.

## Wiring
- S3 GPIO17 TX -> Arduino D19 RX1; GND -> GND.
- Arduino D18 TX1 and S3 GPIO18 RX remain disconnected.
- Do not connect supply pins between boards. Use each board's USB power.
- Change wiring with both boards unpowered; operate with both powered.
- Arduino RX internal pull-up is disabled. This avoids driving 5V into S3.
- Nominal 3.3V -> 5V logic is not guaranteed across worst-case tolerances;
  current wiring passed UART reception testing, not a full electrical qualification.

## Protocol v2
Exactly THREE ASCII digits followed by LF (CRLF also accepted):
source, alarm state, checksum. No commas or square brackets are transmitted.
Source: 0=PC via USB Serial (115200 8N1); 1=ESP via Serial1 (9600 8N1).
State: 0=both outputs OFF, 1=both outputs ON.
Checksum: numeric source XOR state, encoded as ASCII 0/1.

| Frame (append LF) | Meaning |
| --- | --- |
| 000 | PC OFF |
| 011 | PC ON |
| 101 | ESP OFF |
| 110 | ESP ON |

Source must match the physical input. Incorrect source, checksum, nonbinary
characters and wrong lengths are rejected without refreshing control timeout.
Incomplete frames expire after 250ms between bytes. LF terminates the frame.
The XOR bit detects single-bit errors, not every possible corruption and is
not authentication or a substitute for a CRC on a noisy link.

PC has priority for 1500ms after each valid PC frame. During this lease ESP
frames are ignored. Send every 200ms to retain control. After PC lease expiry
ESP may take over on its next valid frame. If no accepted frame for 1500ms,
outputs turn OFF. Startup defaults to OFF. This is not safety-rated behavior.
USB reports ACK <frame> only when applied; ERR FORMAT/SOURCE/CHECKSUM on
rejection; TIMEOUT outputs=OFF on loss. UART has no return wire/acknowledgement.

## PC usage
Arduino Serial Monitor: 115200 baud, newline ending, send 011 for ON or 000 for
OFF. A single command leases control for 1.5 seconds; repeated commands retain
it. Opening USB may reset Arduino: wait about 2 seconds before sending.
Python with pyserial, replace port if needed:

```python
import serial, time
with serial.Serial('COM3', 115200, timeout=0.1) as port:
    time.sleep(2)
    for _ in range(25):  # Hold ON for five seconds
        port.write(b'011\n')
        time.sleep(0.2)
        print(port.read_all().decode(errors='replace'), end='')
    port.write(b'000\n')
```

This decouples the alarm actuator from IMU acquisition/decision algorithms:
either upstream module emits the same alarm-state abstraction. Source ownership
and heartbeat remain part of the interface contract. The Arduino does not parse
IMU samples or decide posture correctness.

S3_UART_TX_Test is a deliberate 3-second OFF/ON test pattern, not IMU logic.
Uploading it replaces running IMU firmware; original BMI160 source is preserved.
Old ALARM,0 / ALARM,1 commands are no longer supported. Both boards must use v2.

## Validation
2026-11-10 initial v1: both boards uploaded, real Arduino UART reception observed.
Protocol v2 validation is recorded in ../validation/2026-11-10-alarm-protocol.txt after upload/testing.
Visible LED, audible buzzer and physical wire-disconnect behavior require
on-site observation. No branch merge performed.

## Source locations and builds

- Arduino: `firmware/alarm-mega/Mega_Alarm_RX/Mega_Alarm_RX.ino`
- S3 test sender: `firmware/imu-s3/S3_UART_TX_Test/S3_UART_TX_Test.ino`
- BMI160 acquisition: `firmware/esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino` (historical location, unchanged).

```powershell
arduino-cli compile --fqbn arduino:avr:mega firmware/alarm-mega/Mega_Alarm_RX
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200 firmware/imu-s3/S3_UART_TX_Test
```

Append `--upload --port COM3` for Arduino or `--upload --port COM4` for S3 only after confirming port identity; port numbers may change.
