import unittest
import numpy as np
from orientation import OrientationController, rotate_frame, upright_score


def standing():
    k=np.zeros((17,3),dtype=float)
    for i,xy in {0:(150,50),5:(125,100),6:(175,100),9:(120,230),10:(180,230),11:(135,210),12:(165,210),13:(135,300),14:(165,300),15:(135,390),16:(165,390)}.items():
        k[i]=[*xy,.95]
    return k


class OrientationTests(unittest.TestCase):
    def test_no_people_or_weak_points_do_not_calibrate(self):
        self.assertEqual(upright_score(None,480),0)
        self.assertEqual(upright_score(np.zeros((17,3)),480),0)

    def test_standing_evidence_and_horizontal_pushup_rejection(self):
        k=standing();self.assertGreater(upright_score(k,480),.8)
        k[[9,10],1]=100
        self.assertEqual(upright_score(k,480),0)

    def test_all_quarter_turns_are_recovered_and_locked(self):
        original=np.arange(40*30*3,dtype=np.uint16).reshape(40,30,3)
        for source_angle in (0,90,180,270):
            source=rotate_frame(original,source_angle)
            expected=(360-source_angle)%360
            calls=[]
            def infer(frame):
                calls.append(1)
                return (standing() if np.array_equal(frame,original) else None),None
            control=OrientationController(mirror=False)
            for i in range(3):control.update(source,infer,float(i))
            self.assertTrue(control.locked);self.assertEqual(control.angle,expected)
            self.assertTrue(np.array_equal(control.transform(source),original))
            before=len(calls);control.update(source,infer,10)
            self.assertEqual(len(calls),before) # Normal exercise must not trigger rescans.

    def test_conflicting_votes_do_not_flip_display(self):
        image=np.arange(8*6*3).reshape(8,6,3).astype(np.uint8)
        targets=[90,180,90]
        c=OrientationController(mirror=False)
        for now,target in enumerate(targets):
            selected=rotate_frame(image,target)
            c.update(image,lambda f: (standing() if np.array_equal(f,selected) else None,None),float(now))
        self.assertFalse(c.locked);self.assertEqual(c.angle,0)

    def test_mirror_and_manual_override(self):
        frame=np.arange(8*6*3).reshape(8,6,3).astype(np.uint8)
        c=OrientationController(mode='90',mirror=True)
        self.assertTrue(np.array_equal(c.transform(frame),rotate_frame(frame,90)[:,::-1]))
        c.configure('auto',False,recalibrate=True)
        self.assertFalse(c.locked)
        with self.assertRaises(ValueError):c.configure('45',False)

    def test_ambiguous_candidates_do_not_lock(self):
        c=OrientationController();image=np.zeros((480,640,3),np.uint8)
        for i in range(4):c.update(image,lambda f:(standing(),None),float(i))
        self.assertFalse(c.locked)


if __name__=='__main__':unittest.main()
