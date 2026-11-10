"""Unified local vision + IMU application; standalone legacy entry points remain usable."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
import webbrowser

from imu_service import ImuService, list_serial_ports
import pose_app as vision
from workspace import Workspace

WEB = Path(__file__).resolve().parent / 'web'
STATIC = {'/':'index.html','/dashboard.js':'dashboard.js','/styles.css':'styles.css','/i18n.js':'i18n.js','/locales.json':'locales.json','/exercises.js':'exercises.js','/exercises.json':'exercises.json','/workspace.js':'workspace.js'}


class UnifiedHandler(vision.Handler):
    def _json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)

    def do_GET(self):
        parsed=urlsplit(self.path)
        if parsed.path in STATIC:
            path=WEB/STATIC[parsed.path]
            types={'.json':'application/json; charset=utf-8','.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
            self._send(path.read_bytes(),types[path.suffix]);return
        if parsed.path=='/api/state':
            try:
                after=max(0,int(parse_qs(parsed.query).get('after',['0'])[0]))
            except ValueError:
                self._json({'error':'Invalid history cursor'},400);return
            with vision._LOCK:
                state={'pose':dict(vision.STATE['pose']),'stats':dict(vision.STATE['stats'])}
            import time
            pipeline=self.server.pipeline
            state['stats']['vision_alive']=bool(pipeline and pipeline.is_alive())
            state['stats']['frame_age_s']=round(time.monotonic()-pipeline.last_frame_at,3) if pipeline and pipeline.last_frame_at else None
            state['stats']['video_language']=getattr(pipeline,'language',getattr(self.server,'vision_language','en'))
            state['service_id']=getattr(self.server,'service_id','')
            state['camera_port']=self.server.imu.protected_port
            state['imu']=self.server.imu.snapshot(after)
            if hasattr(self.server,'workspace'):state.update(self.server.workspace.snapshot(state['stats'],state['imu']))
            self._json(state);return
        if parsed.path=='/api/ports':
            self._json({'ports':list_serial_ports(),'camera_port':self.server.imu.protected_port});return
        if parsed.path=='/api/profile':
            self._json(self.server.imu.profile_dict());return
        super().do_GET()

    def do_POST(self):
        # JSON + same-origin checks keep unrelated web pages from driving local serial actions.
        expected={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
        if self.headers.get('Origin') and self.headers['Origin'] not in expected:
            self.close_connection=True
            self._json({'error':'Origin not allowed'},403);return
        if self.headers.get_content_type()!='application/json':
            self.close_connection=True
            self._json({'error':'Expected application/json'},415);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8_500_000:
                raise ValueError('JSON request must be between 1 byte and 8.5 MB')
            payload=json.loads(self.rfile.read(size).decode('utf-8'))
            if not isinstance(payload,dict):raise ValueError('Expected a JSON object')
            action=urlsplit(self.path).path
            imu=self.server.imu
            if action=='/api/modules':
                self.server.workspace.module(payload.get('module'),payload.get('enabled'),payload.get('port'))
            elif action=='/api/training':
                self.server.workspace.training(payload.get('action'),payload.get('exercise','squat'))
            elif action=='/api/vision/language':
                language=payload.get('language')
                if language not in ('zh-CN','en','zh-HK'):raise ValueError('Unsupported language')
                self.server.vision_language=language
                if self.server.pipeline:self.server.pipeline.language=language
            elif action=='/api/vision/orientation':
                mode=str(payload.get('mode','auto'))
                mirror=payload.get('mirror',True)
                recalibrate=payload.get('recalibrate',False)
                if mode not in ('auto','0','90','180','270') or not isinstance(mirror,bool) or not isinstance(recalibrate,bool):
                    raise ValueError('Invalid orientation settings')
                with self.server.vision_control:
                    self.server.vision_rotate=mode
                    self.server.vision_mirror=mirror
                    if recalibrate:self.server.orientation_revision+=1
                    if self.server.pipeline:
                        self.server.pipeline.requested_orientation=(mode,mirror,self.server.orientation_revision)
            elif action=='/api/vision/reconnect':
                self.server.workspace.camera(True,reconnect=True)
            elif action=='/api/vision/action':
                selected=payload.get('action')
                if selected != 'squat':raise ValueError('Exercise AI is not available yet')
                if not self.server.pipeline:raise ValueError('Vision pipeline is not running')
                self.server.vision_action=selected
                self.server.pipeline.requested_action=selected
            elif action=='/api/imu/connect':
                imu.connect(payload.get('port',''),payload.get('reset',False))
                if hasattr(self.server,'workspace'):
                    self.server.workspace.enabled['imu']=True
                    self.server.workspace.imu_port=payload['port']
            elif action=='/api/imu/disconnect':
                imu.disconnect()
                if hasattr(self.server,'workspace'):self.server.workspace.enabled['imu']=False
            elif action=='/api/imu/example':imu.replay_example()
            elif action=='/api/imu/replay':imu.replay_csv(payload.get('csv'),payload.get('name','uploaded.csv'))
            elif action=='/api/imu/pause':imu.pause(payload.get('paused'))
            elif action=='/api/imu/origin':imu.reset_origin()
            elif action=='/api/imu/reset':imu.reset_filter()
            elif action=='/api/profile':imu.apply_profile(payload.get('profile'))
            elif action=='/api/imu/calibrate':
                self._json({'ok':True,'profile':imu.calibrate(payload.get('csv'),payload.get('name','stationary.csv'))});return
            else:
                self._json({'error':'Unknown endpoint'},404);return
            self._json({'ok':True})
        except (ValueError,TypeError,KeyError,OSError) as exc:
            self.close_connection=True
            self._json({'error':str(exc)},400)
        except Exception as exc:
            self._json({'error':str(exc)},500)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='serial://COM3')
    parser.add_argument('--imu-port',default='COM4',help='Empty string disables automatic IMU connection')
    parser.add_argument('--action',choices=['squat'],default='squat')
    parser.add_argument('--rotate',choices=['auto','0','90','180','270'],default='auto')
    parser.add_argument('--no-mirror',action='store_true',help='Disable selfie mirror')
    parser.add_argument('--port',type=int,default=8010)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--no-vision',action='store_true',help='Run the dashboard/IMU without opening a camera')
    args=parser.parse_args()
    camera_port=urlsplit(args.source).netloc if args.source.startswith('serial://') else ''
    imu=ImuService(protected_port=camera_port)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),UnifiedHandler)
    server.imu=imu
    pipeline=None
    server.pipeline=None
    import threading
    server.vision_control=threading.Lock()
    server.vision_source=args.source
    server.vision_action=args.action
    server.vision_rotate=args.rotate
    server.vision_mirror=not args.no_mirror
    server.orientation_revision=0
    server.vision_language="en"
    import uuid
    server.service_id=uuid.uuid4().hex
    server.vision_module=vision
    server.workspace=Workspace(server,camera=not args.no_vision,imu=bool(args.imu_port),imu_port=args.imu_port or "COM4")
    try:
        if args.imu_port:
            try:imu.connect(args.imu_port,reset=False)
            except Exception as exc:print('IMU unavailable:',exc)
        if not args.no_vision:
            try:
                pipeline=vision.Pipeline(args.source,args.action,args.rotate,mirror=not args.no_mirror)
                pipeline.language=server.vision_language
                server.workspace.configure_pipeline(pipeline)
                pipeline.start()
                server.pipeline=pipeline
            except Exception as exc:
                with vision._LOCK:vision.STATE['stats'].update(state='Vision unavailable: '+str(exc))
        else:
            with vision._LOCK:vision.STATE['stats'].update(state='Vision disabled')
        url=f'http://127.0.0.1:{args.port}'
        print('Unified application:',url)
        if not args.no_browser:webbrowser.open(url)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if server.pipeline:
            server.pipeline.running=False
            server.pipeline.join(timeout=5)
        imu.close();server.server_close()


if __name__=='__main__':main()
