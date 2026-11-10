"""Unified IMU adapter tests: original algorithms, no serial hardware required."""
import time
import unittest
from unittest.mock import patch

from imu_service import ImuService, EXAMPLE_CSV, read_capture


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.service=ImuService(protected_port='COM3')
        self.samples=read_capture(EXAMPLE_CSV)

    def tearDown(self):
        self.service.close()

    def test_reuses_processing_and_preserves_origin_reset_session(self):
        s=self.service
        s._sample(self.samples[0],s.session)
        before=s.processor.roll_deg
        session=s.session
        s.reset_origin()
        self.assertEqual(s.session,session)
        self.assertEqual(s.processor.roll_deg,before)
        s._sample(self.samples[1],session)
        self.assertEqual(s.snapshot()['samples'],1)
        self.assertEqual(s.snapshot()['latest']['seq'],self.samples[1].seq)

    def test_old_source_callbacks_are_ignored(self):
        s=self.service;old=s.session
        with s._lock:s._reset_data()
        s._sample(self.samples[0],old)
        self.assertEqual(s.snapshot()['samples'],0)

    def test_device_diagnostics_survive_fault_and_ignore_old_source(self):
        s=self.service
        s._diagnostic("# DETECT address=0x68 read_ok=1 chip_id=0xC4",s.session)
        s._diagnostic("# BRIDGE role=S3",s.session)
        s._diagnostic("# DETECT stale",s.session-1)
        s._fatal("IDENTITY_OR_CONFIGURATION_FAILED",s.session)
        snapshot=s.snapshot()
        self.assertEqual(snapshot["status"],"fault")
        self.assertEqual(len(snapshot["diagnostics"]),1)
        self.assertIn("0xC4",snapshot["diagnostics"][0])
        s._reset_data()
        self.assertEqual(s.snapshot()["diagnostics"],[])

    def test_camera_port_is_never_opened_as_imu(self):
        with patch('imu_service.list_serial_ports',return_value=['COM3','COM4']):
            with self.assertRaises(ValueError):self.service.connect('COM3')

    def test_replay_pause_resume_and_source_label(self):
        s=self.service;s.replay(self.samples[:50],'test measured CSV')
        time.sleep(.08);s.pause(True)
        count=s.snapshot()['samples'];time.sleep(.08)
        self.assertEqual(s.snapshot()['samples'],count)
        self.assertEqual(s.snapshot()['mode'],'replay')
        s.pause(False);time.sleep(.08)
        self.assertGreater(s.snapshot()['samples'],count)
        self.assertEqual(s.snapshot()['port'],'')

    def test_bad_csv_does_not_replace_existing_source(self):
        s=self.service;s.replay(self.samples[:30],'existing')
        session=s.session
        with self.assertRaises(ValueError):s.replay_csv('not,valid,csv')
        self.assertEqual(s.session,session)
        self.assertEqual(s.snapshot()['label'],'existing')

    def test_profile_validation_does_not_mutate_on_error(self):
        s=self.service;before=s.profile_dict()
        invalid=dict(before);invalid['format_version']=99
        with self.assertRaises(ValueError):s.apply_profile(invalid)
        self.assertEqual(s.profile_dict(),before)

    def test_csv_calibration_reuses_original_gate_and_bias(self):
        s=self.service
        profile=s.calibrate(EXAMPLE_CSV.read_text(encoding='utf-8-sig'),'stationary.csv')
        self.assertTrue(profile['validation']['gate_pass'])
        self.assertAlmostEqual(profile['gyro_bias_dps']['x'],-.2394,places=3)
        self.assertEqual(profile['source']['csv'],'stationary.csv')

    def test_history_cursor_and_filter_reset(self):
        s=self.service;s._sample(self.samples[0],s.session);s._sample(self.samples[1],s.session)
        self.assertEqual(len(s.snapshot(after=1)['history']),1)
        previous=s.snapshot()['session'];s.reset_filter()
        self.assertNotEqual(s.snapshot()['session'],previous)
        s._sample(self.samples[2],s.session)
        self.assertEqual(s.snapshot()['samples'],1)


if __name__=='__main__':unittest.main()
