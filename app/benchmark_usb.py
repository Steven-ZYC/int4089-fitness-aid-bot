"""Measure USB camera stages without storing images or running pose inference."""

import argparse
import json
import statistics
import time
from pathlib import Path

from serial_camera import SerialCameraSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--baud', type=int, default=921600)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('--seconds must be positive')

    source = SerialCameraSource(args.port, baud=args.baud)
    rows = []
    last_sequence = source.seq
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.seconds:
            source.set_alarm(False)
            source.read()  # Surface CRC/decode/transport errors immediately.
            if source.seq != last_sequence:
                last_sequence = source.seq
                rows.append(dict(source.metrics))
            time.sleep(0.005)
    finally:
        source.release()

    if not rows:
        raise RuntimeError('No new camera frames received during benchmark')
    result = {
        'baud': args.baud,
        'frames': len(rows),
        'elapsed_seconds': round(time.monotonic() - start, 3),
        'fps': round(len(rows) / args.seconds, 2),
        'crc_decode_errors': 0,
        'mean': {
            key: round(statistics.mean(row[key] for row in rows), 2)
            for key in rows[0]
        },
        'scope': 'Real camera frames, no image saves; no AI accuracy comparison.',
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
