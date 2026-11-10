"""HTTP integration tests for the unified app, without serial/camera side effects."""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from imu_service import ImuService
from main import UnifiedHandler


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.imu=ImuService(protected_port='COM3')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),UnifiedHandler)
        self.server.imu=self.imu
        self.server.pipeline=None
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.client=build_opener(ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown();self.thread.join(timeout=2)
        self.server.server_close();self.imu.close()

    def call(self,path,payload=None,origin=None):
        headers={}
        if origin:headers['Origin']=origin
        if payload is None:request=Request(self.base+path,headers=headers)
        else:
            headers['Content-Type']='application/json'
            request=Request(self.base+path,data=json.dumps(payload).encode(),headers=headers)
        try:
            response=self.client.open(request,timeout=3)
        except HTTPError as error:response=error
        with response:return response.status,response.read()

    def test_dashboard_static_and_state(self):
        code,body=self.call('/');self.assertEqual(code,200)
        self.assertIn('IMU'.encode(),body)
        code,body=self.call('/api/state');self.assertEqual(code,200)
        data=json.loads(body);self.assertIn('pose',data);self.assertEqual(data['imu']['mode'],'idle')
        self.assertEqual(self.call('/dashboard.js')[0],200)
        self.assertEqual(self.call('/i18n.js')[0],200)
        code,body=self.call('/locales.json')
        self.assertEqual(code,200)
        self.assertEqual(set(json.loads(body)),{'zh-CN','en','zh-HK'})

    def test_video_language_accepts_supported_locales_only(self):
        self.assertEqual(self.call('/api/vision/language',{'language':'en'})[0],200)
        self.assertEqual(self.server.vision_language,'en')
        self.assertEqual(self.call('/api/vision/language',{'language':'zh-HK'})[0],200)
        self.assertEqual(self.call('/api/vision/language',{'language':'unknown'})[0],400)
        self.assertEqual(self.server.vision_language,'zh-HK')

    def test_exercise_library_and_unavailable_ai(self):
        code,body=self.call('/exercises.json')
        self.assertEqual(code,200)
        exercises=json.loads(body)
        self.assertEqual({e['id'] for e in exercises},{'squat','pushup','lunge'})
        self.assertEqual([e['id'] for e in exercises if e['available']],['squat'])
        self.assertEqual(self.call('/exercises.js')[0],200)
        for item in exercises:
            self.assertEqual(len(item['cues']),3)
            self.assertEqual(len(item['stages']),3)
            self.assertRegex(item['video']['id'],r'^[A-Za-z0-9_-]{11}$')
            self.assertTrue(item['video']['poster'].startswith('https://i.ytimg.com/vi/'))
        from unittest.mock import Mock
        pipeline=Mock()
        pipeline.requested_action='squat'
        self.server.pipeline=pipeline
        for action in ('pushup','lunge'):
            self.assertEqual(self.call('/api/vision/action',{'action':action})[0],400)
            self.assertEqual(pipeline.requested_action,'squat')
        self.assertEqual(self.call('/api/vision/action',{'action':'squat'})[0],200)
        self.assertEqual(pipeline.requested_action,'squat')

    def test_replay_and_pause_share_existing_backend(self):
        self.assertEqual(self.call('/api/imu/example',{})[0],200)
        self.assertEqual(self.call('/api/imu/pause',{'paused':True})[0],200)
        data=json.loads(self.call('/api/state')[1])
        self.assertEqual(data['imu']['mode'],'replay');self.assertTrue(data['imu']['paused'])
        self.assertEqual(data['imu']['port'],'')

    def test_camera_port_rejected_for_imu(self):
        code,body=self.call('/api/imu/connect',{'port':'COM3'})
        self.assertEqual(code,400);self.assertIn('camera',json.loads(body)['error'])

    def test_invalid_profile_keeps_current_profile(self):
        original=self.imu.profile_dict()
        code,_=self.call('/api/profile',{'profile':{'format_version':99}})
        self.assertEqual(code,400);self.assertEqual(self.imu.profile_dict(),original)

    def test_external_origin_cannot_control_sources(self):
        code,_=self.call('/api/imu/example',{},origin='https://unrelated.example')
        self.assertEqual(code,403);self.assertEqual(self.imu.mode,'idle')

    def test_unknown_action_and_static_traversal_rejected(self):
        self.assertEqual(self.call('/api/vision/action',{'action':'unknown'})[0],400)
        self.assertEqual(self.call('/api/not-real',{})[0],404)
        self.assertEqual(self.call('/../../AGENTS.md')[0],404)


    def test_orientation_settings_and_recalibration(self):
        from types import SimpleNamespace
        self.server.vision_control=threading.Lock()
        self.server.vision_rotate='auto'
        self.server.vision_mirror=True
        self.server.orientation_revision=0
        self.server.pipeline=SimpleNamespace(requested_orientation=None)
        code,_=self.call('/api/vision/orientation',{'mode':'90','mirror':False})
        self.assertEqual(code,200)
        self.assertEqual(self.server.pipeline.requested_orientation,('90',False,0))
        code,_=self.call('/api/vision/orientation',{'mode':'auto','mirror':True,'recalibrate':True})
        self.assertEqual(code,200)
        self.assertEqual(self.server.pipeline.requested_orientation,('auto',True,1))
        self.assertEqual(self.call('/api/vision/orientation',{'mode':'45'})[0],400)
        self.assertEqual(self.call('/api/vision/orientation',{'mirror':'false'})[0],400)


if __name__=='__main__':unittest.main()
