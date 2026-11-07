"""动作规范判定：基于关节角度的几何规则 + 计次状态机。

设计原则
--------
1. **只用 2D 角度**，不依赖 3D 估计，单目摄像头就能算
2. **阈值全部可调**，写在 RULES 里；后续用真实数据校准
3. **一次完整的下蹲/俯卧撑算一次**，在关键相位（最底点）采样判定，
   避免单帧抖动造成误判
4. 输出结构化结果，方便将来回传给 ESP32 / Arduino
"""
from __future__ import annotations

import math

import numpy as np

from pose_engine import (L_ANK, L_ELB, L_HIP, L_KNE, L_SHO, L_WRI,
                         R_ANK, R_ELB, R_HIP, R_KNE, R_SHO, R_WRI, visible)

# ---------------- 通用角度 ----------------
def angle(a, b, c) -> float:
    """三点夹角，顶点在 b，返回 0~180 度。"""
    v1 = np.array(a[:2], float) - np.array(b[:2], float)
    v2 = np.array(c[:2], float) - np.array(b[:2], float)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return float("nan")
    cos = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
    return math.degrees(math.acos(cos))


def vertical_tilt(p_top, p_bot) -> float:
    """躯干相对竖直方向的倾角（度）。0 = 完全竖直。"""
    dx = p_top[0] - p_bot[0]
    dy = p_top[1] - p_bot[1]
    if abs(dy) < 1e-6:
        return 90.0
    return abs(math.degrees(math.atan2(dx, -dy)))


class _Ema:
    """指数滑动平均，压制关键点抖动。"""

    def __init__(self, a: float = 0.35):
        self.a = a
        self.v = None

    def __call__(self, x):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return self.v
        self.v = x if self.v is None else self.a * x + (1 - self.a) * self.v
        return self.v


# ---------------- 深蹲 ----------------
SQUAT_CFG = {
    "stand": 160.0,     # 膝角大于此值视为站立
    "descend": 140.0,   # 开始下蹲
    "bottom": 115.0,    # 进入底部
    "depth_ok": 105.0,  # 底部膝角需 ≤ 此值，否则算蹲得不够深
    "torso_max": 45.0,  # 躯干倾角上限
    "sym_max": 20.0,    # 左右膝角差上限
}


class SquatAnalyzer:
    name = "深蹲"
    unit = "膝角"

    def __init__(self, cfg=None):
        self.cfg = {**SQUAT_CFG, **(cfg or {})}
        self.phase = "未开始"        # 未开始 / 站立 / 下蹲 / 底部 / 起身
        self.reps = 0
        self.knee = _Ema()
        self.torso = _Ema(0.25)
        self.min_knee = 999.0        # 本次动作的最低膝角
        self.max_torso = 0.0
        self.max_sym = 0.0
        self.violations = []
        self.last_result = None
        self.angles = {}

    # ---- 关键点 → 角度 ----
    def _measure(self, k):
        knees, torso, sym = [], None, 0.0
        left = right = None
        if visible(k, L_HIP) and visible(k, L_KNE) and visible(k, L_ANK):
            left = angle(k[L_HIP], k[L_KNE], k[L_ANK])
            knees.append(left)
        if visible(k, R_HIP) and visible(k, R_KNE) and visible(k, R_ANK):
            right = angle(k[R_HIP], k[R_KNE], k[R_ANK])
            knees.append(right)
        if left is not None and right is not None:
            sym = abs(left - right)
        elif knees:
            sym = 0.0

        hip_mid = (k[L_HIP] + k[R_HIP]) / 2 if (visible(k, L_HIP) and visible(k, R_HIP)) else None
        sho_mid = (k[L_SHO] + k[R_SHO]) / 2 if (visible(k, L_SHO) and visible(k, R_SHO)) else None
        if hip_mid is not None and sho_mid is not None:
            torso = vertical_tilt(sho_mid, hip_mid)

        knee = float(np.mean(knees)) if knees else float("nan")
        return knee, torso, sym

    def update(self, kpts):
        knee_raw, torso_raw, sym = self._measure(kpts)
        knee = self.knee(knee_raw)
        torso = self.torso(torso_raw) if torso_raw is not None else None

        self.angles = {
            "膝角": round(knee, 1) if knee else None,
            "躯干倾角": round(torso, 1) if torso else None,
            "左右差": round(sym, 1),
        }
        if knee is None:
            return self._snapshot()

        c = self.cfg
        # ---- 状态机 ----
        prev = self.phase
        if self.phase in ("未开始", "站立") and knee > c["stand"]:
            self.phase = "站立"
        elif self.phase == "站立" and knee < c["descend"]:
            self.phase = "下蹲"
            self.min_knee, self.max_torso, self.max_sym = 999.0, 0.0, 0.0
        elif self.phase == "下蹲" and knee < c["bottom"]:
            self.phase = "底部"
        elif self.phase == "底部" and knee > c["bottom"] + 10:
            self.phase = "起身"
        elif self.phase in ("下蹲", "底部", "起身") and knee > c["stand"]:
            # 只要是从下蹲过程中回到站立就算完成一次。
            # 若只允许「起身 → 站立」计数，蹲得不够深（没进底部）的动作会被漏掉，
            # 而那恰恰是最需要给反馈的情况。
            self._finish_rep()
            self.phase = "站立"

        if self.phase in ("下蹲", "底部", "起身"):
            self.min_knee = min(self.min_knee, knee)
            if torso is not None:
                self.max_torso = max(self.max_torso, torso)
            self.max_sym = max(self.max_sym, sym)
        return self._snapshot()

    def _finish_rep(self):
        c = self.cfg
        v = []
        if self.min_knee > c["depth_ok"]:
            v.append(f"下蹲深度不足：最低膝角 {self.min_knee:.0f}°，建议 ≤{c['depth_ok']:.0f}°")
        if self.max_torso > c["torso_max"]:
            v.append(f"躯干前倾过大：{self.max_torso:.0f}°，建议 ≤{c['torso_max']:.0f}°（易塌腰）")
        if self.max_sym > c["sym_max"]:
            v.append(f"左右不对称：两膝角差 {self.max_sym:.0f}°，存在代偿")
        self.reps += 1
        self.violations = v
        self.last_result = {
            "rep": self.reps,
            "ok": not v,
            "violations": v,
            "min_knee": round(self.min_knee, 1),
            "max_torso": round(self.max_torso, 1),
            "score": max(0, 100 - 25 * len(v)),
        }

    def _snapshot(self):
        return {
            "action": self.name,
            "phase": self.phase,
            "reps": self.reps,
            "angles": self.angles,
            "primary": self.angles.get(self.unit),
            "last": self.last_result,
            "live_violation": None,
        }


# ---------------- 俯卧撑 ----------------
PUSHUP_CFG = {
    "top": 155.0,
    "descend": 130.0,
    "bottom": 100.0,
    "depth_ok": 95.0,     # 底部肘角需 ≤ 此值
    "body_min": 160.0,    # shoulder-hip-ankle 直线度下限
}


class PushupAnalyzer:
    name = "俯卧撑"
    unit = "肘角"

    def __init__(self, cfg=None):
        self.cfg = {**PUSHUP_CFG, **(cfg or {})}
        self.phase = "未开始"
        self.reps = 0
        self.elbow = _Ema()
        self.body = _Ema(0.25)
        self.min_elbow = 999.0
        self.min_body = 999.0
        self.violations = []
        self.last_result = None
        self.angles = {}

    def _measure(self, k):
        elbows = []
        if visible(k, L_SHO) and visible(k, L_ELB) and visible(k, L_WRI):
            elbows.append(angle(k[L_SHO], k[L_ELB], k[L_WRI]))
        if visible(k, R_SHO) and visible(k, R_ELB) and visible(k, R_WRI):
            elbows.append(angle(k[R_SHO], k[R_ELB], k[R_WRI]))
        body = None
        if visible(k, L_SHO) and visible(k, L_HIP) and visible(k, L_ANK):
            body = angle(k[L_SHO], k[L_HIP], k[L_ANK])
        elif visible(k, R_SHO) and visible(k, R_HIP) and visible(k, R_ANK):
            body = angle(k[R_SHO], k[R_HIP], k[R_ANK])
        return (float(np.mean(elbows)) if elbows else float("nan")), body

    def update(self, kpts):
        e_raw, b_raw = self._measure(kpts)
        e = self.elbow(e_raw)
        b = self.body(b_raw) if b_raw is not None else None
        self.angles = {"肘角": round(e, 1) if e else None,
                       "身体直线度": round(b, 1) if b else None}
        if e is None:
            return self._snapshot()

        c = self.cfg
        if self.phase in ("未开始", "撑起") and e > c["top"]:
            self.phase = "撑起"
        elif self.phase == "撑起" and e < c["descend"]:
            self.phase = "下放"
            self.min_elbow, self.min_body = 999.0, 999.0
        elif self.phase == "下放" and e < c["bottom"]:
            self.phase = "最低点"
        elif self.phase == "最低点" and e > c["bottom"] + 10:
            self.phase = "推起"
        elif self.phase in ("下放", "最低点", "推起") and e > c["top"]:
            self._finish_rep()
            self.phase = "撑起"

        if self.phase in ("下放", "最低点", "推起"):
            self.min_elbow = min(self.min_elbow, e)
            if b is not None:
                self.min_body = min(self.min_body, b)
        return self._snapshot()

    def _finish_rep(self):
        c = self.cfg
        v = []
        if self.min_elbow > c["depth_ok"]:
            v.append(f"幅度不够：最低肘角 {self.min_elbow:.0f}°，建议 ≤{c['depth_ok']:.0f}°")
        if self.min_body < c["body_min"]:
            v.append(f"身体没成一条线：最小 {self.min_body:.0f}°，建议 ≥{c['body_min']:.0f}°（塌腰或撅臀）")
        self.reps += 1
        self.violations = v
        self.last_result = {"rep": self.reps, "ok": not v, "violations": v,
                            "min_elbow": round(self.min_elbow, 1),
                            "min_body": round(self.min_body, 1),
                            "score": max(0, 100 - 30 * len(v))}

    def _snapshot(self):
        return {"action": self.name, "phase": self.phase, "reps": self.reps,
                "angles": self.angles, "primary": self.angles.get(self.unit),
                "last": self.last_result, "live_violation": None}


ANALYZERS = {"squat": SquatAnalyzer, "pushup": PushupAnalyzer}


def make_analyzer(kind: str):
    if kind not in ANALYZERS:
        raise ValueError(f"未知动作 {kind}（可选 {list(ANALYZERS)}）")
    return ANALYZERS[kind]()
