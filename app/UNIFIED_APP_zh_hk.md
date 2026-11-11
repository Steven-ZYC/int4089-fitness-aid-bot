[English](UNIFIED_APP.md) | [简体中文](UNIFIED_APP_zh_cn.md) | [繁體中文（香港）](UNIFIED_APP_zh_hk.md)

# 統一電腦應用

目前電腦入口為 `app/main.py`。一個本地服務和網頁整合原來的視覺網頁與 IMU Windows 面板。舊獨立入口保留；IMU 算法直接複用，不復製成第二份實現。

## 啓動

在倉庫根目錄使用已有項目虛擬環境運行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File app/run_pose.ps1 -CamPort COM3 -ImuPort COM4 -Action squat
```

或在 `app/` 中運行：

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py --source serial://COM3 --imu-port COM4 --action squat --no-browser
```

打開 http://127.0.0.1:8010 。統一應用目前只支援 `-Action squat`，`-ImuPort ''` 跳過自動連接 IMU。USB 重插後確認連接埠身份；每個串列埠只能由一個進程佔用，使用統一應用前先停止獨立工具。

## 六個頁面

- **訓練控制台**：首 4 個動作預覽、獨立硬件開關、即時訓練及 IMU／校準預覽。
- **動作庫**：6 個動作的影片、示意及要點，卡片箭頭進入即時監測。
- **即時動作監測**：完整動作選擇器及共用的攝影機／訓練控制。目前只有深蹲支援 AI。
- **3D 姿態與位置**：機體座標軸、重力、速度、積分位置軌跡、視角／縮放、姿態參考與位置歸零。
- **IMU 數據曲線**：去偏角速度、相對靜止 Profile 的加速度、加速度模長和靜止區間。
- **連接、回放與校準**：S3 連接／斷開、可選復位、本地或歷史 CSV 回放、暫停／繼續、Profile JSON 導入／導出／編輯、靜止 CSV 校準。

IMU 數據明確標記為實時或回放。回放隻影響 IMU 視圖，真實視覺檢測仍獨立運行，只有在訓練進行中且 Arduino 報警啟用時才可能觸發視覺報警。CSV 回放本身不驅動報警，也不證明 IMU 硬件正常。

## 實現邊界

- `main.py`：統一 HTTP 服務、模組生命週期、JSON 控制介面和頁面資源。
- `web/index.html`、`web/styles.css`、`web/dashboard.js`：響應式界面及 Canvas 曲線／三維投影，無外部 UI／CDN 依賴。
- `imu_service.py`：執行緒適配層，複用 `tools/imu-position/imu_position` 的解析、零漂處理、Profile、回放和校準；網頁適配不依賴 PySide6。
- `pose_app.py`：複用既有視覺流水線，動作切換在推理執行緒內部執行。
- `serial_camera.py`：仍獨佔 CAM USB；啓動探測容忍 ROM 噪聲，身份無應答時可嘗試一次 CAM 復位。斷開後可在頁面手動重連攝影機。

相機繼續保持 640×480、JPEG18、LATEST 雙緩衝、921600。ESP-NOW／UART／Arduino 協議及板上韌體均未改變。預設連接 S3 不復位，頁面説明主動復位會短暫中斷無線轉發。

Profile 編輯與校準僅在應用會話內生效，需導出 JSON 保存，不覆蓋倉庫 Profile。上傳 CSV 使用原解析器與門檻校驗，並通過本地臨時檔案處理。本次整合不保存原始攝影機影像。

## 介面與測試

`GET /api/state?after=N` 合併視覺狀態與 IMU 來源／狀態、最新處理樣本、增量歷史；`/stats`、`/video` 保持兼容。`GET /api/ports` 列出串列埠，`/api/profile` 導出目前配置。JSON POST 介面控制 IMU 來源、回放、原點／濾波重置、配置更新／校準，以及視覺動作／重連。

控制僅監聽 localhost，要求 JSON 並拒絕其他網頁來源。攝影機連接埠不可同時用作 IMU。無效 CSV／Profile 不會取代目前有效來源／配置。

在 `app/` 中用 `.venv/Scripts/python.exe` 運行：

```powershell
.\.venv\Scripts\python.exe -X utf8 test_imu_service.py
.\.venv\Scripts\python.exe -X utf8 test_unified_api.py
.\.venv\Scripts\python.exe -X utf8 test_serial_camera.py
.\.venv\Scripts\python.exe -X utf8 test_rules.py
```

參見 [架構](../docs/architecture/README_zh_hk.md)、[USB 協議](../docs/protocols/usb-camera_zh_hk.md)、[原 IMU 應用](../tools/imu-position/README_zh_hk.md)。維護中文件的遷移雜湊保存在本地化清單中，排除的歷史記錄保持不變；統一入口以本文為準。

## 目前驗證範圍

服務／介面／傳輸／規則測試通過。瀏覽器已檢查明確標記的歷史 CSV 回放、暫停、曲線和 3D，同時真實影像推理及 S3 ACK 正常。IMU 目前仍無有效實時樣本，待檢查接線；回放只證明軟件路徑。真實動作準確性、新閉環聲光效果、物理斷線／掉電驗收仍待完成。位置雙積分會漂移，Yaw 無磁力計參考。

## 自動畫面方向

統一應用預設啟用 0°／90°／180°／270° 自動校正及自拍鏡像。初次請短暫站直，讓肩、髖及自然下垂的手進入畫面。連續三次掃描方向一致、候選足夠明確後才鎖定；初次掃描會增加推理工作，鎖定後只保留正常姿態推理。

運動時保持方向鎖定，深蹲、彎腰及掌上壓不會令畫面不斷旋轉。重新擺放攝影機後按「重新校正方向」。人體資訊不足或候選不明確時保留上一角度，暫停次數判定及警報，等候校正成功，不猜測方向。

頁面提供自動、固定 0°／90°／180°／270° 及自拍鏡像開關。預設鏡像適合正面自拍習慣；一般攝影或背面拍攝可關閉。旋轉本身不能判斷使用者偏好的左右鏡像方式。

旋轉及鏡像在姿態推理、骨架繪製前執行，畫面與規則使用同一座標。方向改變時清除未完成動作及警報，保留已完成次數。目前處理 90° 倍數擺放，並非任意傾斜角度的連續防震。

命令列可用 `main.py --rotate 90` 固定順時針 90°，`--no-mirror` 關閉鏡像；舊獨立 pose_app.py 保留手動預設值。USB 頻寬、JPEG 參數、韌體及警報協議均不變。測試包含本機公開 Ultralytics bus.jpg 的四種旋轉，不儲存使用者攝影機影像。

## 界面語言

右上角語言選擇器支援英文（`en`）、簡體中文（`zh-CN`）及繁體中文（香港）（`zh-HK`）。瀏覽器會在本機儲存偏好，首次開啟時跟隨瀏覽器語言；不使用外部翻譯服務。

`web/locales.json` 是共用字典；`web/i18n.js` 翻譯靜態標籤、動態狀態、圖表提示及回饋，不改變協議值。`localization.py` 使用同一字典翻譯影片疊字。原始韌體診斷及 Profile JSON 保持原樣。攝影機影片串流是共用資源，因此最後一次語言選擇亦會改變其他本機檢視者的影片疊字。

`docs/assets/` 內三張 1920 × 1080 截圖已於 2026-11-11 更新，並嵌入相應語言的根目錄 README，展示攝影機未就緒、IMU 沒有即時數據的實際狀態，沒有填入模擬即時測量。

## 動作庫與即時訓練

六個動作：深蹲、掌上壓、前弓步、平板支撐、臀橋及鳥狗式，均提供影片、要點及三階段示意。目前只有深蹲支援 AI 識別，其餘為教學預覽。新增影片來自 ScottHermanFitness（臀橋）及 Point Performance（鳥狗式）。

側欄「動作庫」下方新增「即時動作監測」。點擊卡片主體查看教學，點擊箭頭進入即時頁面；控制台及即時頁面沿用同一影片串流及訓練會話。未支援的動作不能啟動 AI 識別。

控制台支援 Arduino 報警、ESP Camera 及 ESP IMU 獨立開關，分開顯示啟用意圖與連接狀態。開關控制採集及報警傳送，不切斷供電；Arduino 實際聲光執行仍需現場確認。開始／暫停／繼續／結束控制計次及視覺報警，暫停凍結計時、保留已完成次數，影片仍可預覽。介面為 `/api/modules`、`/api/training`，生命週期測試為 `test_workspace.py`。
