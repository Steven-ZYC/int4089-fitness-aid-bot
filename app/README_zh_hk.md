> 目前入口：[統一電腦應用](UNIFIED_APP_zh_hk.md)，將視覺與 IMU 整合到同一網頁；獨立 pose_app.py 仍保留。

[English](README.md) | [简体中文 / 原文](README_zh_cn.md) | [繁體中文（香港）](README_zh_hk.md)

<a id="电脑端视觉-ai"></a>

# 電腦端視覺 AI

目前入口是 [pose_app.py](pose_app.py)：CAM USB 影像 → YOLOv8n-pose → 深蹲／掌上壓幾何規則 → 網頁結果 → CAM USB 報警狀態。影像不經過 ESP-NOW。

<a id="启动"></a>

## 啓動

本機已有 `app/.venv`。在倉庫根目錄運行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File app/run_pose.ps1 -CamPort COM3 -Action squat
```

或在本目錄直接運行：

```powershell
.\.venv\Scripts\python.exe -X utf8 pose_app.py --source serial://COM3 --action squat --no-browser
```

打開 [檢測頁面](http://127.0.0.1:8010)。掌上壓使用 `pushup`；其他命令行參數見 `pose_app.py --help`。一個串列埠同時只允許一個檢測／測試／燒錄進程訪問。USB 斷開後需檢查連接埠並重新啓動，目前沒有自動重連。

<a id="环境"></a>

## 環境

目前本機環境基於已有 AI 包建立項目虛擬環境，隔離 pyserial 與全局同名 `serial` 包衝突：

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --ignore-installed pyserial==3.5
```

新電腦可創建獨立虛擬環境並安裝 `requirements.txt`。它是新安裝依賴範圍，不是目前舊環境的精確鎖檔案。目前實測 torch 1.12.1+cu116、ultralytics 8.3.141、RTX 4060 Laptop，模型加載／真實 USB 影像推理已通過。首次運行需要官方 `yolov8n-pose.pt` 權重；權重、虛擬環境、運行日誌、抓幀均被 Git 忽略。

<a id="代码分工"></a>

## 程式碼分工

| 檔案 | 用途 |
| --- | --- |
| `pose_app.py` | 目前網頁和推理主程式 |
| `pose_engine.py` | 17 點姿態估計 |
| `form_rules.py` | 角度、動作狀態機、計次和規則扣分 |
| `sources.py` | 影片源選擇；目前使用 `serial://COM3` |
| `serial_camera.py` | 串列埠獨佔讀寫、二進制影像校驗、最新幀緩存、報警回傳和性能指標 |
| `run_pose.ps1` | 本機啓動腳本 |
| `app.py` / `detector.py` | 舊人體檢測入口，保留為基線 |
| `find_camera.py` / `firmware/esp32_cam_stream/` | 舊 Wi-Fi MJPEG 路線；目前不使用 |

<a id="当前配置与反馈"></a>

## 目前配置與反饋

- VGA 640×480、JPEG18、雙緩衝 LATEST、USB 921600。保持目前約 9 FPS 的實測效果。
- 相機幀在採集時最多 200ms 舊；電腦僅處理新鮮最新幀。這個邊界不是完整顯示延遲。
- 動作手動選擇，全身需入畫。完成一次不合格動作時產生兩秒報警事件；關鍵點不足時清除報警，持續丟失時清除未完成動作狀態，累計完成次數保留。
- 原模型輸出關鍵點，規則產生違規項和分數；分數不是模型置信度。真實動作準確率尚未驗收。
- `/stats` 提供姿態結果、幀率、無線 ACK 和 `transport` 影像分階段指標。

<a id="测试与测速"></a>

## 測試與測速

從本目錄使用 `.venv/Scripts/python.exe`：

```powershell
.\.venv\Scripts\python.exe -X utf8 test_rules.py
.\.venv\Scripts\python.exe -X utf8 test_serial_camera.py
.\.venv\Scripts\python.exe -X utf8 check_usb_bridge.py --cam COM3 --s3 COM4
.\.venv\Scripts\python.exe -X utf8 benchmark_usb.py --baud 921600 --seconds 30 --out ../firmware/usb-ai-bridge/captures/speed.json
```

先停止正在運行的檢測頁面，再執行硬件腳本。`check_usb_bridge.py` 會短暫開啓報警，並分開報告通信與 IMU；目前 IMU 無應答，所以整體併發驗收失敗，即使無線部分通過。測速不保存影像。

詳細資料：[系統架構](../docs/architecture/README_zh_hk.md)、[動作規則説明](POSE_zh_hk.md)、[USB 協議](../docs/protocols/usb-camera_zh_hk.md)、[韌體與編譯](../firmware/usb-ai-bridge/README_zh_hk.md)。
