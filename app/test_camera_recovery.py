"""Camera faults must release the USB owner and retry without reloading the model."""
import unittest
from unittest.mock import Mock, patch
from copy import deepcopy
from pose_app import Pipeline, STATE

class RecoveryTests(unittest.TestCase):
    def test_corrupt_serial_stream_releases_then_retries(self):
        pipeline=Pipeline('serial://COM3','squat',engine=Mock())
        engine=pipeline.engine
        source=Mock()
        calls=[]
        def attempt():
            calls.append(True)
            if len(calls)==1:
                pipeline._source=source
                raise UnicodeDecodeError('ascii',b'\xff',0,1,'bad frame boundary')
            pipeline.running=False
        with patch('pose_app.STATE',deepcopy(STATE)),patch.object(pipeline,'_run_pipeline',side_effect=attempt),patch('pose_app.time.sleep'):
            pipeline.run()
        self.assertEqual(len(calls),2)
        source.set_alarm.assert_called_once_with(False)
        source.release.assert_called_once()
        self.assertIs(pipeline.engine,engine)

    def test_shutdown_interrupts_retry_wait(self):
        pipeline=Pipeline('serial://COM3','squat',engine=Mock())
        def stop(_):pipeline.running=False
        with patch('pose_app.STATE',deepcopy(STATE)),patch.object(pipeline,'_run_pipeline',side_effect=RuntimeError('USB unavailable')) as attempt,patch('pose_app.time.sleep',side_effect=stop):
            pipeline.run()
        self.assertEqual(attempt.call_count,1)

if __name__=='__main__':unittest.main()
