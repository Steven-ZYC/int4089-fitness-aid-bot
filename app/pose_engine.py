"""YOLOv8n-pose 推理封装：输入一帧，输出 17 个 COCO 关键点。

COCO 17 点顺序（下标固定，规则引擎按这个索引取值）：
 0 鼻 1 左眼 2 右眼 3 左耳 4 右耳
 5 左肩 6 右肩 7 左肘 8 右肘
 9 左腕 10 右腕 11 左髋 12 右髋
 13 左膝 14 右膝 15 左踝 16 右踝
"""
import numpy as np
from ultralytics import YOLO

NOSE = 0
L_SHO, R_SHO = 5, 6
L_ELB, R_ELB = 7, 8
L_WRI, R_WRI = 9, 10
L_HIP, R_HIP = 11, 12
L_KNE, R_KNE = 13, 14
L_ANK, R_ANK = 15, 16

NAMES = ["鼻", "左眼", "右眼", "左耳", "右耳", "左肩", "右肩", "左肘", "右肘",
         "左腕", "右腕", "左髋", "右髋", "左膝", "右膝", "左踝", "右踝"]

SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]


class PoseEngine:
    def __init__(self, weights: str = "yolov8n-pose.pt", conf: float = 0.4, imgsz: int = 480):
        self.model = YOLO(weights)
        self.conf = conf
        self.imgsz = imgsz
        self.name = "YOLOv8n-pose"

    def infer(self, frame: np.ndarray):
        """返回画面中最大那个人的关键点 (17,3) 与包围盒，无人时返回 (None, None)。"""
        r = self.model.predict(frame, conf=self.conf, imgsz=self.imgsz, verbose=False)[0]
        if r.keypoints is None or r.boxes is None or len(r.boxes) == 0:
            return None, None

        boxes = r.boxes.xyxy.cpu().numpy()
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        idx = int(np.argmax(areas))            # 多人时取最近（框最大）的那个

        kxy = r.keypoints.xy.cpu().numpy()[idx]          # (17,2)
        kconf = r.keypoints.conf
        kconf = kconf.cpu().numpy()[idx] if kconf is not None else np.ones(17, np.float32)
        kpts = np.concatenate([kxy, kconf.reshape(-1, 1)], axis=1)   # (17,3)
        return kpts, boxes[idx]


def visible(kpts, i, thr: float = 0.35) -> bool:
    return kpts is not None and kpts[i, 2] >= thr
