"""Discrete camera orientation calibration, locked independently of exercise motion."""
from __future__ import annotations
import math
import cv2
import numpy as np

ANGLES=(0,90,180,270)


def rotate_frame(frame, angle):
    if angle==0:return frame
    return cv2.rotate(frame,{90:cv2.ROTATE_90_CLOCKWISE,180:cv2.ROTATE_180,270:cv2.ROTATE_90_COUNTERCLOCKWISE}[angle])


def upright_score(keypoints, height):
    """Conservative standing/arms-down evidence, not generic body-angle normalization."""
    if keypoints is None or np.shape(keypoints)!=(17,3):return 0.0
    k=np.asarray(keypoints)
    if not np.isfinite(k).all():return 0.0
    required=[0,5,6,11,12]
    if any(k[i,2]<.45 for i in required):return 0.0
    shoulder=(k[5,:2]+k[6,:2])/2
    hip=(k[11,:2]+k[12,:2])/2
    delta=hip-shoulder
    length=float(np.linalg.norm(delta))
    if length<height*.06 or delta[1]<=0:return 0.0
    vertical=float(delta[1]/length)
    if vertical<.94 or k[0,1]>=shoulder[1]-length*.08:return 0.0
    wrists=[k[i] for i in (9,10) if k[i,2]>=.45]
    # A rotated pushup can resemble an upright torso. Hanging hands help reject it.
    if not any(shoulder[1]+length*.35<w[1]<hip[1]+length*1.3 for w in wrists):return 0.0
    for h,n,a in [(11,13,15),(12,14,16)]:
        if all(k[i,2]>=.45 for i in (h,n,a)):
            v=k[h,:2]-k[n,:2];w=k[a,:2]-k[n,:2]
            norm=float(np.linalg.norm(v)*np.linalg.norm(w))
            if norm<1e-6:return 0.0
            angle=math.degrees(math.acos(float(np.clip(np.dot(v,w)/norm,-1,1))))
            if angle<150:return 0.0
    confidence=float(np.mean(k[required,2]))
    coverage=float(np.count_nonzero(k[:,2]>=.45))/17
    return .55*confidence+.35*vertical+.1*coverage


class OrientationController:
    def __init__(self, mode='auto', mirror=True, confirmations=3, interval=.8):
        self.confirmations=confirmations
        self.interval=interval
        self.angle=0
        self.mode='auto'
        self.mirror=mirror
        self.locked=False
        self.candidate=None
        self.votes=0
        self.confidence=0.0
        self.next_scan=0.0
        self.configure(mode,mirror,recalibrate=True)

    def configure(self, mode, mirror, recalibrate=False):
        mode=str(mode)
        if mode not in ('auto','0','90','180','270') or not isinstance(mirror,bool):
            raise ValueError('Invalid orientation setting')
        changed=mode!=self.mode
        self.mode=mode;self.mirror=mirror
        if mode!='auto':
            self.angle=int(mode);self.locked=True
            self.candidate=None;self.votes=0
        elif changed or recalibrate:
            self.locked=False;self.candidate=None;self.votes=0
            self.confidence=0.0;self.next_scan=0.0

    def update(self, frame, infer, now):
        if self.mode!='auto' or self.locked or now<self.next_scan:return
        self.next_scan=now+self.interval
        scores=[]
        for angle in ANGLES:
            candidate=rotate_frame(frame,angle)
            keypoints,_=infer(candidate)
            scores.append((upright_score(keypoints,candidate.shape[0]),angle))
        scores.sort(reverse=True)
        best,angle=scores[0]
        self.confidence=best
        if best<.75 or best-scores[1][0]<.12:
            self.candidate=None;self.votes=0;return
        self.votes=self.votes+1 if self.candidate==angle else 1
        self.candidate=angle
        if self.votes>=self.confirmations:
            self.angle=angle;self.locked=True

    def transform(self, frame):
        corrected=rotate_frame(frame,self.angle)
        return cv2.flip(corrected,1) if self.mirror else corrected

    def state(self):
        return {'mode':self.mode,'degrees':self.angle,'mirror':self.mirror,
                'locked':self.locked,'votes':self.votes,'required_votes':self.confirmations,
                'confidence':round(self.confidence,3)}
