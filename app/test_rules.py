"""规则引擎单元测试：用合成关键点验证角度计算与计次，不依赖摄像头。

跑法：python test_rules.py
"""
import math

import numpy as np

from form_rules import PushupAnalyzer, SquatAnalyzer, angle

S, W = 0.99, 0.99          # 关键点置信度


def kp_from_angles(knee_deg: float, torso_deg: float = 0.0):
    """构造正面视角的深蹲关键点：髋-膝-踝夹角 = knee_deg，躯干倾角 = torso_deg。

    图像坐标 y 向下。膝为顶点，髋在正上方，踝按夹角展开：
    要得到夹角 θ，踝相对膝的方向取 (sinθ, -cosθ)。
    """
    k = np.zeros((17, 3), np.float32)
    k[:, 2] = S

    knee = np.array([400.0, 400.0])
    hip = knee + 120 * np.array([0.0, -1.0])
    th = math.radians(knee_deg)
    ankle = knee + 120 * np.array([math.sin(th), -math.cos(th)])

    lean = math.radians(torso_deg)
    shoulder = hip + 150 * np.array([math.sin(lean), -math.cos(lean)])

    k[11, :2] = k[12, :2] = hip          # 左右髋
    k[13, :2] = k[14, :2] = knee         # 左右膝
    k[15, :2] = k[16, :2] = ankle        # 左右踝
    k[5, :2] = k[6, :2] = shoulder       # 左右肩
    return k


def run_squat(knee_profile, torso_profile=None):
    a = SquatAnalyzer()
    res = None
    for i, kn in enumerate(knee_profile):
        t = torso_profile[i] if torso_profile else 0.0
        res = a.update(kp_from_angles(kn, t))
    return a, res


def test_angle():
    a = angle((0, 0, 1), (0, 100, 1), (100, 100, 1))
    assert abs(a - 90) < 1e-6, f"直角应为 90，得到 {a}"
    b = angle((0, 100, 1), (0, 0, 1), (0, -100, 1))
    assert abs(b - 180) < 1e-6, f"直线应为 180，得到 {b}"
    print("[PASS] 角度计算")


def test_good_squat():
    # 注意 EMA 平滑有滞后，底部必须保持足够多帧，否则平滑后的膝角到不了 105 以下
    prof = ([175] * 10 + [170, 160, 150, 140, 130, 120, 110, 100, 92, 90] + [90] * 6 +
            [92, 100, 115, 130, 148, 165, 175] + [176] * 5)
    ana, res = run_squat(prof)
    assert ana.reps == 1, f"应计 1 次，实际 {ana.reps}"
    assert res["last"]["ok"], f"标准深蹲不应报违规：{res['last']}"
    print(f"[PASS] 标准深蹲 计次={ana.reps} 最低膝角={res['last']['min_knee']} 分数={res['last']['score']}")


def test_shallow_squat():
    prof = ([175] * 10 + [168, 158, 148, 140, 134, 131, 130] + [130] * 6 +
            [132, 140, 152, 165, 175] + [176] * 5)
    ana, res = run_squat(prof)
    v = res["last"]["violations"]
    assert any("深度不足" in x for x in v), f"应报深度不足，实际 {v}"
    print(f"[PASS] 浅蹲 违规={v}")


def test_lean_squat():
    prof = ([175] * 10 + [170, 158, 145, 132, 120, 110, 100, 93, 90] + [90] * 6 +
            [95, 108, 125, 145, 165, 175] + [176] * 5)
    torso = ([0] * 10 + [8, 18, 30, 42, 52, 58, 62, 64, 65] + [65] * 6 +
             [58, 45, 30, 16, 6, 0] + [0] * 5)
    ana, res = run_squat(prof, torso)
    v = res["last"]["violations"]
    assert any("前倾" in x for x in v), f"应报躯干前倾，实际 {v}"
    print(f"[PASS] 躯干前倾 违规={v}")


def test_pushup():
    def kp(elbow_deg, sag=0.0):
        """侧面视角：躯干水平。sag 为髋部下沉像素数（>0 表示塌腰）。"""
        k = np.zeros((17, 3), np.float32)
        k[:, 2] = S
        elb = np.array([300.0, 400.0])
        th = math.radians(elbow_deg)
        sho = elb + 100 * np.array([-1.0, 0.0])          # 肘 → 肩
        wri = elb + 100 * np.array([-math.cos(th), -math.sin(th)])   # 肘 → 腕，夹角 = θ
        hip = sho + 150 * np.array([1.0, sag / 150.0])
        ank = hip + 150 * np.array([1.0, 0.0])
        k[5, :2] = k[6, :2] = sho
        k[7, :2] = k[8, :2] = elb
        k[9, :2] = k[10, :2] = wri
        k[11, :2] = k[12, :2] = hip
        k[15, :2] = k[16, :2] = ank
        k[13, :2] = k[14, :2] = (hip + ank) / 2
        return k

    a = PushupAnalyzer()
    res = None
    for e in [170] * 8 + [168, 160, 150, 140, 130, 118, 108, 98, 92] + [92] * 6 + \
             [95, 105, 120, 138, 155, 168] + [170] * 5:
        res = a.update(kp(e))
    assert a.reps == 1, f"应计 1 次，实际 {a.reps}"
    assert res["last"]["ok"], f"标准俯卧撑不应报违规：{res['last']}"
    print(f"[PASS] 俯卧撑 计次={a.reps} 最低肘角={res['last']['min_elbow']}")

    # 塌腰：髋部下沉，身体直线度不足
    a2 = PushupAnalyzer()
    res2 = None
    for e in [170] * 8 + [160, 150, 140, 130, 118, 108, 98, 92] + [92] * 10 + \
             [95, 108, 125, 145, 165, 170] + [170] * 5:
        res2 = a2.update(kp(e, sag=80))
    v = res2["last"]["violations"] if res2["last"] else []
    assert any("一条线" in x for x in v), f"应报身体不成直线，实际 {v}"
    print(f"[PASS] 塌腰 违规={v}")


if __name__ == "__main__":
    test_angle()
    test_good_squat()
    test_shallow_squat()
    test_lean_squat()
    test_pushup()
    print("\n全部通过")
