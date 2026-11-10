# IMU 零飘处理 · Windows 位置面板

Zhang Yancheng（`Feat-Integration-Yancheng`）的电脑端工具：读取 ESP32-S3 + BMI160 经 USB 串口输出的
15 列 CSV 六轴数据，按零飘 profile 做去偏、静态检测（ZUPT）、互补滤波与位置积分，并在两页面板中
显示处理后的源数据和 3D 姿态/位置。

> **状态说明（2026-11-05）**：实时串口读取已在本机 COM4 实测通过（复位后 49.73 Hz、CONFIG 0x69、
> 0 畸形行）；标定、处理算法、回放与 UI 均已验证。

**实测发现**：若 ESP32-S3 长时间无人读取串口或被上一个工具留在复位状态，端口能打开但**没有任何字节**
（本机实测 6 秒 0 字节）。面板默认在打开端口后用 RTS（CH340 的 EN 引脚）脉冲复位板子，复位后立即
出现 `ESP-ROM` 启动信息和 `# BMI160_SIX_AXIS_START`。若板子已正常输出，可取消勾选「连接时复位板子」。

## 零飘实测（`firmware/esp32-camera/evidence/yancheng-2026-11-05/capture.csv`）

静止 30.061 s、1496 组、49.732 Hz、COM4 / 地址 0x69、未校准。

| 项 | 实测 |
| --- | --- |
| 陀螺零偏（静止均值） | gx **−0.2394**、gy **−0.3691**、gz **+0.2943** °/s |
| 零偏稳定性 | 6 个 5 s 块均值波动 ±0.005 °/s；Allan 偏差（5 s）≈0.0015 °/s |
| 未处理误差 | 30 s 纯积分漂移 −7.2° / −11.1° / +8.9°；去偏后残差 std ≈0.029 °/s |
| 加速度 | 均值 (−0.0745, −0.0866, +0.9976) g（模长 1.00422 g），放置倾斜 roll −4.96°、pitch +4.31° |
| 留出验证（后 15 s） | 残差均值 ≤0.0011 °/s，矢量 RMS 0.0321 °/s（门槛 0.1 °/s，通过） |

处理结果（`scripts/replay.py` 实测输出）：静止判定 96.7%（前 49 个样本为检测窗口预热）、去偏残差
≈0、**位置保持 0.00 cm**、姿态收敛到 roll −4.96° / pitch +4.32°。

加速度均值**不是零偏**：它包含重力与安装倾斜，必须保留；本工具只减去陀螺零偏。

## 安装与运行（Windows）

依赖仅 PySide6 / numpy / pyserial，使用独立 venv（本机用 Anaconda 3.9 创建；PySide6 6.9.3 支持 Python 3.9–3.13）：

```powershell
cd tools\imu-position
D:\Anaconda\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动面板（默认加载仓库内已标定的 `profiles/yancheng-2026-11-05-static.json`）：

```powershell
.\.venv\Scripts\python.exe -m imu_position
```

两页：**① 源数据（零飘处理后）** 滚动显示去偏陀螺、相对静止参考的加速度、加速度模长，静止段淡绿
底纹标出；**② 3D 位置** 体轴方盒、重力方向、速度与位置轨迹。顶栏可连接串口或回放 CSV；
「设置 / 导入 / 标定…」打开 profile 管理（导入/导出 JSON、编辑参数、从静止 CSV 重新标定）。

### 实时串口

1. 关闭 Arduino 串口监视器、串口绘图器或 `capture_bmi160.ps1`（COM 口独占）。
2. 选择端口（本机为 COM4）→ 勾选「连接时复位板子」→ 点「连接」。
3. 状态栏依次显示：复位 → 收到 `ESP-ROM…` → `# CONFIG firmware=BMI160_SixAxis_v3_autoaddr address=0x69`。
   若 5 秒无样本或读线程停止，状态栏会给出诊断（行数/忽略行/畸形行/端口占用提示）。
4. 设备报 `# FATAL` 或 `read_errors>0` 时面板断开并提示。

### 串口诊断（无界面）

排查"连上但没数据"时先运行：

```powershell
.\.venv\Scripts\python.exe scripts\probe_serial.py -p COM4 -t 6
```

退出码：0 收到样本；2 端口能开但无字节（板子挂起/端口/固件问题）；3 收到字节但无合法样本（固件或波特率不符）。

### 回放

点「回放 CSV」按原 49.73 Hz 节拍重放任意 capture CSV（走与实时相同的解析与处理路径），无需设备。

## 命令行

从 `tools\imu-position` 运行：

```powershell
# 从静止采集标定 profile（门槛不通过会拒绝并说明原因）
.\.venv\Scripts\python.exe scripts\calibrate.py ..\..\firmware\esp32-camera\evidence\yancheng-2026-11-05\capture.csv -o profiles\yancheng-2026-11-05-static.json

# 无界面回放并输出漂移指标（退出码 0 通过；2 profile 不可用；3 静止比例不足；4 静止位置漂移）
.\.venv\Scripts\python.exe scripts\replay.py ..\..\firmware\esp32-camera\evidence\yancheng-2026-11-05\capture.csv --profile profiles\yancheng-2026-11-05-static.json

# 单元测试（49 项，含离屏 UI 冒烟）
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

## Profile 文件（JSON）

`profiles/*.json` 是唯一的零飘参数来源，包含：来源元数据（CSV 路径、SHA256、行数、时长、速率、端口、
地址）、传感器量程与刻度、陀螺零偏、加速度均值与安装倾斜、静止检测阈值、互补滤波 α、积分设置、
留出校验结果。写入前强制 `validate()`；标定门槛沿用上游 `check_bmi160_gyro_bias.ps1`：

- 采集速率 45–55 Hz、无饱和、无序号断裂；
- 加速度模长 0.85–1.15 g、各轴 std ≤0.02 g、陀螺 std ≤0.2 °/s、|陀螺均值| ≤5 °/s；
- 后半段留出残差均值与 RMS ≤0.1 °/s。

`gate_pass=false` 的 profile 在面板中会以警示色标注。

## 算法与已知局限

- **去偏**：`gyro_corr = gyro − gyro_bias`；加速度不做整体减除。
- **静态检测（ZUPT）**：1 s 窗内加速度模长 std <0.05 g、去偏陀螺模长 std <0.15 °/s、陀螺模长
  <1.0 °/s、且加速度模长在 0.9–1.1 g → 判静态，速度清零、位置冻结。窗口未满的预热段不积分。
- **姿态**：互补滤波（α=0.98）融合加速度 roll/pitch 与陀螺积分速率。BMI160 **没有磁力计**，
  **yaw 不可观测**，运动时会漂移；静止时 yaw 速率置零以防噪声累积。
- **位置**：线性加速度（扣重力后，机体坐标系）梯形积分两次得速度与位置。静止段靠 ZUPT 保持原点；
  **运动段双积分位置必然漂移**，本工具不做高精度定位，适用于准静态/间歇动作演示。
- `t_read_us` 是读取起始时间而非精确采样时刻；`sensor_ticks` 为 24 位、约 655.36 s 回绕，本工具按
  `t_read_us` 差分计时。

## 目录

```text
imu_position/   profile.py csvio.py pipeline.py calibration.py
                serial_reader.py replay.py __main__.py
                ui/ (panels.py scene3d.py profile_dialog.py main_window.py)
scripts/        calibrate.py replay.py probe_serial.py
profiles/       yancheng-2026-11-05-static.json
tests/          test_profile / test_csvio / test_pipeline / test_serial_parse /
                test_calibration / test_ui_smoke
```

`.venv/`、`captures/` 均被 Git 忽略；不提交任何采集数据。
