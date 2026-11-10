"""Transport tests with synthetic JPEGs; no camera/model or hardware required."""
import threading
import unittest
import zlib
import cv2
import numpy as np
from serial_camera import SerialCameraSource

class FakePort:
    def __init__(self,data):self.data=bytearray(data);self.is_open=True;self.writes=[]
    def read(self,n):
        if not self.data:raise EOFError('fixture exhausted')
        data=bytes(self.data[:n]);del self.data[:n];return data
    def write(self,data):self.writes.append(data)
    def close(self):self.is_open=False

class TransportTests(unittest.TestCase):
    def run_fixture(self,crc_delta=0,done_seq=1):
        ok,jpg=cv2.imencode('.jpg',np.zeros((480,640,3),np.uint8));self.assertTrue(ok)
        jpg=jpg.tobytes();crc=zlib.crc32(jpg)^crc_delta
        raw=(b'INFO fw=Cam_USB_Bridge_v1 chip=ESP32\nCMD_OK state=0\n'
             b'BRIDGE role=CAM state=0 ack=1 ack_state=0 ack_age_ms=1\n'
             b'META seq=1\n'+f'IMG {len(jpg)} crc={crc:08x}\n'.encode()+jpg+
             f'\nDONE seq={done_seq} written={len(jpg)} send_us=10\n'.encode())
        obj=SerialCameraSource.__new__(SerialCameraSource)
        obj.port=FakePort(raw);obj._stop=threading.Event();obj._lock=threading.Lock()
        obj._alarm=False;obj._decision_at=0;obj.seq=0;obj._error=None;obj._frame=None
        obj._loop()
        self.assertFalse(obj.port.is_open)
        self.assertEqual(obj.port.writes[-1],b'ALARM 0\n')
        return obj
    def test_valid_frame(self):
        obj=self.run_fixture();self.assertEqual(obj.seq,1)
        self.assertEqual(obj._frame.shape,(480,640,3))
    def test_corrupt_payload_rejected(self):
        obj=self.run_fixture(crc_delta=1);self.assertEqual(obj.seq,0)
        self.assertIn('checksum',obj._error)
    def test_wrong_trailer_rejected(self):
        obj=self.run_fixture(done_seq=2);self.assertEqual(obj.seq,0)
        self.assertIn('trailer',obj._error)

class HandshakeTests(unittest.TestCase):
    def test_rom_noise_is_ignored_only_during_handshake(self):
        obj=SerialCameraSource.__new__(SerialCameraSource)
        obj.port=FakePort(b'\xffROM noise\nINFO fw=Cam_USB_Bridge_v1 chip=ESP32\n')
        obj._stop=threading.Event()
        obj._handshake()
        self.assertEqual(obj.port.writes[0],b'INFO\n')

    def test_wrong_firmware_is_rejected(self):
        obj=SerialCameraSource.__new__(SerialCameraSource)
        obj.port=FakePort(b'INFO fw=some_other_firmware chip=ESP32\n')
        obj._stop=threading.Event()
        with self.assertRaises(RuntimeError):obj._handshake()

if __name__=='__main__':unittest.main()
