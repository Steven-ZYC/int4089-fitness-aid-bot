"""Hardware smoke test; briefly commands the alarm ON. Saves metrics, never images."""
import argparse
import json
import threading
import time
from pathlib import Path

import serial
from serial_camera import SerialCameraSource


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cam',default='COM3')
    ap.add_argument('--s3',default='COM4')
    ap.add_argument('--report',default='../firmware/usb-ai-bridge/captures/bridge-check.json')
    args=ap.parse_args()
    monitor=serial.Serial()
    monitor.port=args.s3;monitor.baudrate=115200;monitor.timeout=0.2
    monitor.dtr=False;monitor.rts=False;monitor.open()
    stop=threading.Event();lines=[]
    def collect():
        buf=b''
        while not stop.is_set():
            buf+=monitor.read(monitor.in_waiting or 1)
            while b'\n' in buf:
                line,buf=buf.split(b'\n',1)
                lines.append(line.decode(errors='replace').strip())
    reader=threading.Thread(target=collect,daemon=True);reader.start()
    src=None
    report={'date':'2026-11-10','route':'USB JPEG -> PC state -> USB CAM -> ESP-NOW -> S3 UART TX',
            'cam':args.cam,'s3':args.s3,'stages':[]}
    try:
        src=SerialCameraSource(args.cam)
        start=time.monotonic();first=src.seq
        for name,wanted,refresh in [('OFF',False,True),('ON',True,True),('EXPIRED',False,False)]:
            mark=len(lines);deadline=time.monotonic()+3.5
            states=[]
            while time.monotonic()<deadline:
                if refresh:src.set_alarm(wanted)
                src.read()  # fail immediately on corrupt/truncated JPEG
                states.append(dict(src.radio))
                time.sleep(0.05)
            expected='1' if wanted else '0'
            ack=any(s.get('ack_state')==expected and int(s.get('ack','0'))>0 and int(s.get('ack_age_ms','99999'))<800 for s in states[-12:])
            rx=any('BRIDGE role=S3 state='+expected in s for s in lines[mark:])
            report['stages'].append({'name':name,'cam_ack_matches':ack,'s3_state_matches':rx})
            assert ack and rx, (name,states[-1],lines[-3:])
        report['frames']=src.seq-first
        report['seconds']=round(time.monotonic()-start,3)
        report['usb_frames_per_second']=round(report['frames']/report['seconds'],2)
        samples=[s for s in lines if s and s[0].isdigit() and len(s.split(','))==15]
        report['imu_samples_during_test']=len(samples)
        assert len(samples)>100,'Concurrent IMU data not observed'
        report['last_radio_status']=src.radio
        report['pass']=True
    except Exception as exc:
        report['pass']=False;report['error']=str(exc)
    finally:
        if src:src.release()
        stop.set();reader.join(timeout=2);monitor.close()
    report['communication_pass']=len(report['stages'])==3 and all(s['cam_ack_matches'] and s['s3_state_matches'] for s in report['stages'])
    report['imu_pass']=report.get('imu_samples_during_test',0)>100
    report['limits']='No real exercise accuracy test, no observed Mega RX or visible/audible actuator acceptance; no physical radio/power disconnect test.'
    path=Path(args.report);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
