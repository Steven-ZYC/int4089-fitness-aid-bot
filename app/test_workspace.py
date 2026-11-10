"""Real module intent and session semantics, without touching hardware."""
import itertools
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from workspace import Workspace

class WorkspaceTests(unittest.TestCase):
    def setup_workspace(self):
        def pipeline():
            return SimpleNamespace(is_alive=lambda:True,running=True,join=Mock(),
                _source=Mock(),last_frame_at=9,training_active=False,training_status='idle',
                requested_partial_reset=0,requested_reset=0,engine=object(),start=Mock())
        pipe=pipeline()
        # Make shutdown observable and immediate, as a terminated worker would be.
        pipe.is_alive=lambda:pipe.running
        vision=SimpleNamespace(_LOCK=threading.RLock(),STATE={'stats':{}},Pipeline=Mock(side_effect=lambda *a,**k:pipeline()))
        server=SimpleNamespace(pipeline=pipe,imu=Mock(),vision_module=vision,vision_control=threading.Lock(),
            vision_source='serial://COM3',vision_action='squat',vision_rotate='auto',vision_mirror=True,
            orientation_revision=0,vision_language='en')
        return Workspace(server),server

    def test_all_eight_module_combinations(self):
        for values in itertools.product((False,True),repeat=3):
            with self.subTest(values=values):
                workspace,server=self.setup_workspace()
                for name,value in zip(('camera','imu','arduino'),values):workspace.module(name,value)
                self.assertEqual(workspace.enabled,dict(zip(('camera','imu','arduino'),values)))
                if values[1]:server.imu.connect.assert_called_once_with('COM4',reset=False)
                else:server.imu.disconnect.assert_called_once()

    def test_pause_freezes_timer_and_resume_preserves_elapsed(self):
        workspace,server=self.setup_workspace();now=[10.0]
        with patch('workspace.time.monotonic',side_effect=lambda:now[0]):
            workspace.training('start');self.assertTrue(server.pipeline.training_active)
            now[0]=15;workspace.training('pause');self.assertFalse(server.pipeline.training_active)
            now[0]=25
            imu={'mode':'idle','stale':True,'samples':0,'error':''}
            self.assertEqual(workspace.snapshot({},imu)['training']['elapsed_s'],5)
            server.pipeline.last_frame_at=29.5;now[0]=30;workspace.training('resume')
            now[0]=35;workspace.training('stop')
            self.assertEqual(workspace.snapshot({},imu)['training']['elapsed_s'],10)
            self.assertFalse(server.pipeline.training_active)
            self.assertEqual(server.pipeline.requested_reset,1)

    def test_alarm_disable_silences_current_source(self):
        workspace,server=self.setup_workspace();workspace.module('arduino',False)
        self.assertFalse(server.pipeline.alarm_enabled)
        server.pipeline._source.set_alarm.assert_called_with(False)
        self.assertTrue(workspace.enabled['camera'])
        self.assertFalse(server.vision_module.STATE['stats']['alarm'])

    def test_no_device_connection_is_inferred_from_enabled_switch(self):
        workspace,server=self.setup_workspace()
        imu={'mode':'idle','stale':True,'samples':0,'error':''}
        state=workspace.snapshot({'vision_alive':False,'frame_age_s':None},imu)
        self.assertTrue(all(m['enabled'] for m in state['modules'].values()))
        self.assertFalse(any(m['connected'] for m in state['modules'].values()))
        self.assertEqual(state['training']['status'],'idle')

    def test_failed_imu_connect_does_not_enable_or_reset_other_modules(self):
        workspace,server=self.setup_workspace();workspace.module('imu',False)
        server.imu.connect.side_effect=ValueError('unavailable')
        with self.assertRaises(ValueError):workspace.module('imu',True)
        self.assertFalse(workspace.enabled['imu'])
        self.assertTrue(workspace.enabled['camera'])
        self.assertTrue(workspace.enabled['arduino'])

    def test_camera_off_pauses_training_and_leaves_imu_enabled(self):
        workspace,server=self.setup_workspace()
        with patch('workspace.time.monotonic',return_value=10):workspace.training('start')
        workspace.module('camera',False)
        self.assertEqual(workspace.session,'paused')
        self.assertTrue(workspace.enabled['imu'])
        self.assertFalse(server.pipeline.training_active)

class PipelineTrainingGateTests(unittest.TestCase):
    def exercise_frame(self,active,alarm_enabled):
        from copy import deepcopy
        import numpy as np
        from pose_app import Pipeline,STATE
        keypoints=np.ones((17,3))
        pipe=Pipeline('test','squat',engine=SimpleNamespace(name='test',infer=lambda f:(keypoints,None)))
        pipe.training_active=active;pipe.training_status='paused';pipe.alarm_enabled=alarm_enabled
        pipe.orientation=SimpleNamespace(mode='0',angle=0,mirror=False,locked=True,
            update=lambda *a:None,transform=lambda f:f,state=lambda:{})
        analyzer=Mock(reps=7)
        snapshot={'action':'深蹲','phase':'站立','reps':7,'angles':{},'primary':None,'last':None}
        analyzer._snapshot.return_value=snapshot.copy()
        analyzer.update.return_value={**snapshot,'reps':8,'last':{'ok':False}}
        pipe.analyzer=analyzer
        source=Mock(desc='test',seq=1);reads=[]
        def read():
            reads.append(True)
            if len(reads)>1:pipe.running=False
            return np.zeros((480,640,3),dtype=np.uint8)
        source.read=read
        state=deepcopy(STATE)
        with patch('pose_app.STATE',state),patch('pose_app.open_source',return_value=source),patch('pose_app.make_analyzer',return_value=analyzer),patch('pose_app.draw_pose',side_effect=lambda frame,*a:frame):
            pipe._run_pipeline()
        return analyzer,source,state

    def test_paused_training_does_not_count_or_alarm(self):
        analyzer,source,state=self.exercise_frame(False,True)
        analyzer.update.assert_not_called()
        source.set_alarm.assert_called_with(False)
        self.assertFalse(state['stats']['alarm'])

    def test_disabled_alarm_stays_off_even_for_bad_rep(self):
        analyzer,source,state=self.exercise_frame(True,False)
        analyzer.update.assert_called_once()
        source.set_alarm.assert_called_with(False)
        self.assertFalse(state['stats']['alarm'])

if __name__=='__main__':unittest.main()
