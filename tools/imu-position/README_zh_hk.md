[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="imu-零飘处理--windows-位置面板"></a>

# IMU 零點漂移處理 · Windows 位置面板

Zhang Yancheng（`Feat-Integration-Yancheng`）的電腦端工具：讀取 ESP32-S3 + BMI160 經 USB 串列埠輸出的
15 列 CSV 六軸數據，按零點漂移 profile 做去偏、靜態檢測（ZUPT）、互補濾波與位置積分，並在兩頁面板中
顯示處理後的源數據和 3D 姿態/位置。

> **狀態説明（2026-11-05）**：實時串列埠讀取已在本機 COM4 實測通過（復位後 49.73 Hz、CONFIG 0x69、
> 0 畸形行）；校準、處理算法、回放與 UI 均已驗證。

**實測發現**：若 ESP32-S3 長時間無人讀取串列埠或被上一個工具留在復位狀態，連接埠能打開但**沒有任何位元組**
（本機實測 6 秒 0 位元組）。面板預設在打開連接埠後用 RTS（CH340 的 EN 引腳）脈衝復位板子，復位後立即
出現 `ESP-ROM` 啓動信息和 `# BMI160_SIX_AXIS_START`。若板子已正常輸出，可取消勾選「連接時復位板子」。

<a id="零飘实测firmwareesp32-cameraevidenceyancheng-2026-11-05capturecsv"></a>

## 零點漂移實測（`firmware/esp32-camera/evidence/yancheng-2026-11-05/capture.csv`）

靜止 30.061 s、1496 組、49.732 Hz、COM4 / 地址 0x69、未校準。

| 項 | 實測 |
| --- | --- |
| 陀螺零偏（靜止均值） | gx **−0.2394**、gy **−0.3691**、gz **+0.2943** °/s |
| 零偏穩定性 | 6 個 5 s 塊均值波動 ±0.005 °/s；Allan 偏差（5 s）≈0.0015 °/s |
| 未處理誤差 | 30 s 純積分漂移 −7.2° / −11.1° / +8.9°；去偏後殘差 std ≈0.029 °/s |
| 加速度 | 均值 (−0.0745, −0.0866, +0.9976) g（模長 1.00422 g），放置傾斜 roll −4.96°、pitch +4.31° |
| 留出驗證（後 15 s） | 殘差均值 ≤0.0011 °/s，矢量 RMS 0.0321 °/s（門檻 0.1 °/s，通過） |

處理結果（`scripts/replay.py` 實測輸出）：靜止判定 96.7%（前 49 個樣本為檢測窗口預熱）、去偏殘差
≈0、**位置保持 0.00 cm**、姿態收斂到 roll −4.96° / pitch +4.32°。

加速度均值**不是零偏**：它包含重力與安裝傾斜，必須保留；本工具只減去陀螺零偏。

<a id="安装与运行windows"></a>

## 安裝與運行（Windows）

依賴僅 PySide6 / numpy / pyserial，使用獨立 venv（本機用 Anaconda 3.9 創建；PySide6 6.9.3 支持 Python 3.9–3.13）：

```powershell
cd tools\imu-position
D:\Anaconda\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

啓動面板（預設加載倉庫內已校準的 `profiles/yancheng-2026-11-05-static.json`）：

```powershell
.\.venv\Scripts\python.exe -m imu_position
```

兩頁：**① 源數據（零點漂移處理後）** 滾動顯示去偏陀螺、相對靜止參考的加速度、加速度模長，靜止段淡綠
底紋標出；**② 3D 位置** 體軸方盒、重力方向、速度與位置軌跡。頂欄可連接串列埠或回放 CSV；
「設置 / 導入 / 校準…」打開 profile 管理（導入/導出 JSON、編輯參數、從靜止 CSV 重新校準）。

<a id="实时串口"></a>

### 實時串列埠

1. 關閉 Arduino 串列埠監視器、串列埠繪圖器或 `capture_bmi160.ps1`（COM 口獨佔）。
2. 選擇連接埠（本機為 COM4）→ 勾選「連接時復位板子」→ 點「連接」。
3. 狀態欄依次顯示：復位 → 收到 `ESP-ROM…` → `# CONFIG firmware=BMI160_SixAxis_v3_autoaddr address=0x69`。
   若 5 秒無樣本或讀執行緒停止，狀態欄會給出診斷（行數/忽略行/畸形行/連接埠占用提示）。
4. 設備報 `# FATAL` 或 `read_errors>0` 時面板斷開並提示。

<a id="串口诊断无界面"></a>

### 串列埠診斷（無界面）

排查"連上但沒數據"時先運行：

```powershell
.\.venv\Scripts\python.exe scripts\probe_serial.py -p COM4 -t 6
```

退出碼：0 收到樣本；2 連接埠能開但無位元組（板子掛起/連接埠/韌體問題）；3 收到位元組但無合法樣本（韌體或波特率不符）。

### 回放

點「回放 CSV」按原 49.73 Hz 節拍重放任意 capture CSV（走與實時相同的解析與處理路徑），無需設備。

## 命令行

從 `tools\imu-position` 運行：

```powershell
# 从静止采集标定 profile（门槛不通过会拒绝并说明原因）
.\.venv\Scripts\python.exe scripts\calibrate.py ..\..\firmware\esp32-camera\evidence\yancheng-2026-11-05\capture.csv -o profiles\yancheng-2026-11-05-static.json

# 无界面回放并输出漂移指标（退出码 0 通过；2 profile 不可用；3 静止比例不足；4 静止位置漂移）
.\.venv\Scripts\python.exe scripts\replay.py ..\..\firmware\esp32-camera\evidence\yancheng-2026-11-05\capture.csv --profile profiles\yancheng-2026-11-05-static.json

# 单元测试（49 项，含离屏 UI 冒烟）
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

<a id="profile-文件json"></a>

## Profile 檔案（JSON）

`profiles/*.json` 是唯一的零點漂移參數來源，包含：來源元數據（CSV 路徑、SHA256、行數、時長、速率、連接埠、
地址）、傳感器量程與刻度、陀螺零偏、加速度均值與安裝傾斜、靜止檢測閾值、互補濾波 α、積分設置、
留出校驗結果。寫入前強制 `validate()`；校準門檻沿用上游 `check_bmi160_gyro_bias.ps1`：

- 採集速率 45–55 Hz、無飽和、無序號斷裂；
- 加速度模長 0.85–1.15 g、各軸 std ≤0.02 g、陀螺 std ≤0.2 °/s、|陀螺均值| ≤5 °/s；
- 後半段留出殘差均值與 RMS ≤0.1 °/s。

`gate_pass=false` 的 profile 在面板中會以警示色標註。

<a id="算法与已知局限"></a>

## 算法與已知侷限

- **去偏**：`gyro_corr = gyro − gyro_bias`；加速度不做整體減除。
- **靜態檢測（ZUPT）**：1 s 窗內加速度模長 std <0.05 g、去偏陀螺模長 std <0.15 °/s、陀螺模長
  <1.0 °/s、且加速度模長在 0.9–1.1 g → 判靜態，速度清零、位置凍結。窗口未滿的預熱段不積分。
- **姿態**：互補濾波（α=0.98）融合加速度 roll/pitch 與陀螺積分速率。BMI160 **沒有磁力計**，
  **yaw 不可觀測**，運動時會漂移；靜止時 yaw 速率置零以防噪聲累積。
- **位置**：線性加速度（扣重力後，機體座標系）梯形積分兩次得速度與位置。靜止段靠 ZUPT 保持原點；
  **運動段雙積分位置必然漂移**，本工具不做高精度定位，適用於準靜態/間歇動作演示。
- `t_read_us` 是讀取起始時間而非精確採樣時刻；`sensor_ticks` 為 24 位、約 655.36 s 迴繞，本工具按
  `t_read_us` 差分計時。

<a id="目录"></a>

## 目錄

```text
imu_position/   profile.py csvio.py pipeline.py calibration.py
                serial_reader.py replay.py __main__.py
                ui/ (panels.py scene3d.py profile_dialog.py main_window.py)
scripts/        calibrate.py replay.py probe_serial.py
profiles/       yancheng-2026-11-05-static.json
tests/          test_profile / test_csvio / test_pipeline / test_serial_parse /
                test_calibration / test_ui_smoke
```

`.venv/`、`captures/` 均被 Git 忽略；不提交任何採集數據。
