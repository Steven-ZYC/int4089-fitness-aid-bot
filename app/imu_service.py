"""Thread-safe web adapter around the existing IMU application's processing core."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
IMU_ROOT = ROOT / 'tools' / 'imu-position'
if str(IMU_ROOT) not in sys.path:
    sys.path.insert(0, str(IMU_ROOT))

from imu_position.calibration import build_profile
from imu_position.csvio import read_capture
from imu_position.pipeline import DriftProcessor
from imu_position.profile import Profile
from imu_position.replay import ReplaySource
from imu_position.serial_reader import ImuSerialReader, list_serial_ports

DEFAULT_PROFILE = IMU_ROOT / 'profiles' / 'yancheng-2026-11-05-static.json'
EXAMPLE_CSV = ROOT / 'firmware/esp32-camera/evidence/yancheng-2026-11-05/capture.csv'


class ImuService:
    def __init__(self, protected_port='', reader_factory=ImuSerialReader):
        self._lock = threading.RLock()
        self._operations = threading.RLock()
        self._reader_factory = reader_factory
        self.protected_port = protected_port.upper()
        self.profile = Profile.load(DEFAULT_PROFILE)
        self.processor = DriftProcessor(self.profile)
        self.reader = None
        self._replay = None
        self._worker = None
        self._stop = threading.Event()
        self._paused = False
        self.session = 0
        self._revision = 0
        self._history = deque(maxlen=1200)
        self._diagnostics = deque(maxlen=30)
        self._latest = None
        self._last_at = 0.0
        self._source_started = 0.0
        self.mode = 'idle'
        self.port = ''
        self.label = ''
        self.status = 'idle'
        self.error = ''
        self._replay_elapsed = 0.0

    def _reset_data(self):
        self.session += 1
        self._revision = 0
        self._history.clear()
        self._diagnostics.clear()
        self._latest = None
        self._last_at = 0.0
        self.processor = DriftProcessor(self.profile)
        self.error = ''

    def _sample(self, sample, session):
        with self._lock:
            if session != self.session:
                return
            processed = self.processor.process(sample)
            self._revision += 1
            row = asdict(processed)
            row['revision'] = self._revision
            reference = self.profile.accel_mean_g
            row['accel_relative_g'] = [sample.ax_g-reference.x, sample.ay_g-reference.y, sample.az_g-reference.z]
            self._latest = row
            self._history.append(row)
            self._last_at = time.monotonic()
            self.status = 'running'

    def _diagnostic(self, line, session):
        with self._lock:
            if session == self.session and not line.startswith("# BRIDGE"):
                self._diagnostics.append(line[:500])

    def _fatal(self, reason, session):
        with self._lock:
            if session == self.session:
                self.error = reason
                self.status = 'fault'

    def _status(self, message, session):
        with self._lock:
            if session == self.session and not self.error:
                self.label = message

    def _stop_source(self):
        self._stop.set()
        reader, worker = self.reader, self._worker
        self.reader = None
        self._worker = None
        if reader:
            reader.stop()
        if worker and worker is not threading.current_thread():
            worker.join(timeout=2)
        self._replay = None

    def disconnect(self):
        with self._operations:
            self._stop_source()
            with self._lock:
                self.mode = 'idle'
                self.status = 'disconnected'
                self._paused = False
                self.port = ''
                self.error = ''

    def connect(self, port, reset=False):
        if not isinstance(port, str) or not port:
            raise ValueError('Select an IMU serial port')
        if port.upper() == self.protected_port:
            raise ValueError('The camera serial port cannot also be used for IMU')
        if not isinstance(reset, bool):
            raise ValueError('reset must be a boolean')
        if port not in list_serial_ports():
            raise ValueError('Serial port is not currently available: '+port)
        with self._operations:
            self._stop_source()
            with self._lock:
                self._reset_data()
                self.mode = 'live'
                self.port = port
                self.status = 'waiting'
                self._source_started = time.monotonic()
                session = self.session
                self.reader = self._reader_factory(
                    port, on_sample=lambda s: self._sample(s,session),
                    on_fatal=lambda e: self._fatal(e,session),
                    on_status=lambda s: self._status(s,session), reset_on_open=reset,
                    on_diagnostic=lambda line: self._diagnostic(line,session),
                )
            try:
                self.reader.start()
            except Exception as exc:
                self._fatal(str(exc),session)
                self._stop_source()
                raise

    def replay(self, samples, label):
        with self._operations:
            self._stop_source()
            with self._lock:
                self._reset_data()
                self._replay = ReplaySource(samples)
                self._stop = threading.Event()
                self._paused = False
                self._replay_elapsed = 0.0
                self.mode = 'replay'
                self.port = ''
                self.label = label
                self.status = 'running'
                session = self.session
                replay = self._replay
            def run():
                previous = time.monotonic()
                while not self._stop.wait(0.01):
                    now = time.monotonic()
                    with self._lock:
                        if not self._paused:
                            self._replay_elapsed += now-previous
                            for sample in replay.due(self._replay_elapsed):
                                self._sample(sample,session)
                        done = replay.finished
                        if done:
                            self.status = 'finished'
                    previous = now
                    if done:
                        return
            self._worker = threading.Thread(target=run, name='imu-replay',daemon=True)
            self._worker.start()

    def replay_csv(self, text, label='uploaded.csv'):
        self.replay(self._csv_samples(text),Path(label).name)

    def replay_example(self):
        self.replay(read_capture(EXAMPLE_CSV),'Historical measured CSV: 2026-11-05 (not live)')

    @staticmethod
    def _csv_samples(text):
        if not isinstance(text,str) or len(text.encode('utf-8'))>8_000_000:
            raise ValueError('CSV must be text of at most 8 MB')
        with tempfile.TemporaryDirectory(prefix='int4089-imu-') as directory:
            file=Path(directory)/'capture.csv'
            file.write_text(text,encoding='utf-8')
            return read_capture(file)

    def pause(self, paused):
        if not isinstance(paused,bool):
            raise ValueError('paused must be a boolean')
        with self._lock:
            if self.mode!='replay' or self.status=='finished':
                raise ValueError('Pause is available during CSV replay only')
            self._paused=paused
            self.status='paused' if paused else 'running'

    def reset_origin(self):
        with self._lock:
            self.processor.reset_origin()
            self._history.clear()
            self._latest=None
            self._revision=0
            self._view_epoch=getattr(self,'_view_epoch',0)+1

    def reset_filter(self):
        # A processing reset preserves the current source but must not invalidate callbacks.
        with self._lock:
            self.processor=DriftProcessor(self.profile)
            self._history.clear()
            self._latest=None
            self._revision=0
            self._view_epoch=getattr(self,'_view_epoch',0)+1

    def profile_dict(self):
        with self._lock:
            return self.profile.to_dict()

    def apply_profile(self, data):
        profile=Profile.from_dict(data)
        profile.validate()
        with self._lock:
            self.profile=profile
            self.reset_filter()

    def calibrate(self,text,label='stationary.csv'):
        if not isinstance(text,str) or len(text.encode('utf-8'))>8_000_000:
            raise ValueError('Stationary CSV must be at most 8 MB')
        with tempfile.TemporaryDirectory(prefix='int4089-calibration-') as directory:
            path=Path(directory)/'capture.csv';path.write_text(text,encoding='utf-8')
            profile=build_profile(path,'Web calibration',Path(directory))
        profile.source.csv=Path(label).name
        self.apply_profile(profile.to_dict())
        return self.profile_dict()

    def snapshot(self, after=0):
        with self._lock:
            now=time.monotonic()
            stale=self.mode=='live' and (not self._last_at or now-self._last_at>3)
            status=self.status
            if self.mode=='live' and not self.error and now-self._source_started>3 and stale:
                status='no_samples'
            if self.error:
                status='fault'
            stats=asdict(self.reader.parser.stats) if self.reader else {}
            if self.reader and self.reader.error and not self.error:
                self.error=self.reader.error;status='fault'
            history=[r for r in self._history if r['revision']>after]
            span=self._history[-1]['t_s']-self._history[0]['t_s'] if len(self._history)>1 else 0
            sample_hz=(len(self._history)-1)/span if span>0 else None
            return {
                'session':f'{self.session}:{getattr(self,"_view_epoch",0)}',
                'mode':self.mode,'status':status,'port':self.port,'label':self.label,
                'error':self.error,'stale':stale,'paused':self._paused,
                'sample_age_s':round(now-self._last_at,2) if self._last_at else None,
                'samples':self._revision,'latest':self._latest,'history':history,
                'diagnostics':list(self._diagnostics),
                'stats':stats,'sample_hz':sample_hz,'profile':{'name':self.profile.name,'usable':self.profile.usable,
                    'problems':self.profile.gate_problems()},
                'replay':{'elapsed_s':round(self._replay_elapsed,2),
                    'duration_s':self._replay.duration_s if self._replay else 0},
            }

    def close(self):
        self.disconnect()
