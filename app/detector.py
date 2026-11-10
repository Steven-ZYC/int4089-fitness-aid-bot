"""人体检测器。

两种实现：
  hog  —— OpenCV 自带的 HOG+SVM 行人检测器，零额外依赖，CPU 上约 10~20 FPS（480p）
  yolo —— ultralytics YOLOv8n，只保留 person 类，精度明显更高

默认用 hog：装了就能跑。想要更好的检测效果装 ultralytics 后加 --detector yolo。
两者输出统一为 [(x1, y1, x2, y2, score), ...]，方便后续换成姿态模型。
"""
import cv2
import numpy as np


class HogDetector:
    name = "HOG 行人检测"

    def __init__(self, scale: float = 1.05, min_h: int = 80):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.scale = scale
        self.min_h = min_h      # 忽略太小的框（远处噪点）

    def detect(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        # 缩到宽 400 再检测，速度提升明显，坐标按比例还原
        tw = 400
        r = tw / w
        small = cv2.resize(frame, (tw, int(h * r)))
        rects, weights = self.hog.detectMultiScale(
            small, winStride=(8, 8), padding=(8, 8), scale=self.scale)

        out = []
        for (x, y, bw, bh), conf in zip(rects, weights):
            if bh * (1 / r) < self.min_h:
                continue
            out.append((int(x / r), int(y / r), int((x + bw) / r), int((y + bh) / r), float(conf)))
        # NMS 去重（HOG 对同一人常给多个重叠框）
        return _nms(out, 0.4)


class YoloDetector:
    name = "YOLOv8n"

    def __init__(self, weights: str = "yolov8n.pt", conf: float = 0.35, imgsz: int = 480):
        from ultralytics import YOLO
        self.model = YOLO(weights)
        self.conf = conf
        self.imgsz = imgsz

    def detect(self, frame: np.ndarray):
        res = self.model.predict(frame, classes=[0], conf=self.conf,
                                 imgsz=self.imgsz, verbose=False)[0]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            out.append((int(x1), int(y1), int(x2), int(y2), float(b.conf[0])))
        return out


def _nms(boxes, iou_thr=0.4):
    if not boxes:
        return []
    arr = np.array([[b[0], b[1], b[2], b[3]] for b in boxes], dtype=np.float32)
    scores = np.array([b[4] for b in boxes], dtype=np.float32)
    idx = cv2.dnn.NMSBoxes(arr.tolist(), scores.tolist(), 0.0, iou_thr)
    if len(idx) == 0:
        return []
    return [boxes[i] for i in np.array(idx).flatten()]


def make_detector(kind: str = "hog"):
    kind = kind.lower()
    if kind == "hog":
        return HogDetector()
    if kind == "yolo":
        return YoloDetector()
    raise ValueError(f"未知检测器 {kind}（可选 hog / yolo）")


def draw(frame: np.ndarray, boxes, fps: float = 0.0, label: str = ""):
    """画框 + 顶部信息条。"""
    for i, (x1, y1, x2, y2, score) in enumerate(boxes, 1):
        cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 200, 120), 2)
        tag = f"#{i} {score:.2f}"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), (80, 200, 120), -1)
        cv2.putText(frame, tag, (x1 + 4, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)

    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 30), (30, 30, 30), -1)
    cv2.putText(frame, f"{len(boxes)} person | {fps:.1f} FPS | {label}",
                (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1)
    return frame
