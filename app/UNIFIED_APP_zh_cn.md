# 统一电脑应用

当前电脑入口为 `app/main.py`。一个本地服务和网页整合原来的视觉网页与 IMU Windows 面板。旧独立入口保留；IMU 算法直接复用，不复制成第二份实现。

## 启动

在仓库根目录使用已有项目虚拟环境运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File app/run_pose.ps1 -CamPort COM3 -ImuPort COM4 -Action squat
```

或在 `app/` 中运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py --source serial://COM3 --imu-port COM4 --action squat --no-browser
```

打开 http://127.0.0.1:8010 。统一应用目前只支持 `-Action squat`，`-ImuPort ''` 跳过自动连接 IMU。USB 重插后确认端口身份；每个串口只能由一个进程占用，使用统一应用前先停止独立工具。

## 六个页面

- **训练控制台**：前 4 个动作预览、独立硬件开关、实时训练及 IMU／校准预览。
- **动作库**：6 个动作的视频、示意及要点，卡片箭头进入实时监测。
- **实时动作监测**：完整动作选择器及共用的摄像头／训练控制。目前只有深蹲支持 AI。
- **3D 姿态与位置**：机体坐标轴、重力、速度、积分位置轨迹、视角／缩放、姿态参考与位置归零。
- **IMU 数据曲线**：去偏角速度、相对静止 Profile 的加速度、加速度模长和静止区间。
- **连接、回放与校准**：S3 连接／断开、可选复位、本地或历史 CSV 回放、暂停／继续、Profile JSON 导入／导出／编辑、静止 CSV 校准。

IMU 数据明确标记为实时或回放。回放只影响 IMU 视图，真实视觉检测仍独立运行，仅在训练进行中且 Arduino 报警启用时可能触发视觉报警。CSV 回放本身不驱动报警，也不证明 IMU 硬件正常。

## 实现边界

- `main.py`：统一 HTTP 服务、模块生命周期、JSON 控制接口和页面资源。
- `web/index.html`、`web/styles.css`、`web/dashboard.js`：响应式界面及 Canvas 曲线／三维投影，无外部 UI／CDN 依赖。
- `imu_service.py`：线程适配层，复用 `tools/imu-position/imu_position` 的解析、零漂处理、Profile、回放和校准；网页适配不依赖 PySide6。
- `pose_app.py`：复用既有视觉流水线，动作切换在推理线程内部执行。
- `serial_camera.py`：仍独占 CAM USB；启动探测容忍 ROM 噪声，身份无应答时可尝试一次 CAM 复位。断开后可在页面手动重连摄像头。

相机继续保持 640×480、JPEG18、LATEST 双缓冲、921600。ESP-NOW／UART／Arduino 协议及板上固件均未改变。默认连接 S3 不复位，页面说明主动复位会短暂中断无线转发。

Profile 编辑与校准仅在应用会话内生效，需导出 JSON 保存，不覆盖仓库 Profile。上传 CSV 使用原解析器与门槛校验，并通过本地临时文件处理。本次整合不保存原始摄像头图像。

## 接口与测试

`GET /api/state?after=N` 合并视觉状态与 IMU 来源／状态、最新处理样本、增量历史；`/stats`、`/video` 保持兼容。`GET /api/ports` 列出串口，`/api/profile` 导出当前配置。JSON POST 接口控制 IMU 来源、回放、原点／滤波重置、配置更新／校准，以及视觉动作／重连。

控制仅监听 localhost，要求 JSON 并拒绝其他网页来源。摄像头端口不可同时用作 IMU。无效 CSV／Profile 不会取代当前有效来源／配置。

在 `app/` 中用 `.venv/Scripts/python.exe` 运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 test_imu_service.py
.\.venv\Scripts\python.exe -X utf8 test_unified_api.py
.\.venv\Scripts\python.exe -X utf8 test_serial_camera.py
.\.venv\Scripts\python.exe -X utf8 test_rules.py
```

参见 [架构](../docs/architecture/README_zh_cn.md)、[USB 协议](../docs/protocols/usb-camera_zh_cn.md)、[原 IMU 应用](../tools/imu-position/README_zh_cn.md)。维护中文档的迁移哈希保存在本地化清单中，排除的历史记录保持不变；统一入口以本文为准。

## 当前验证范围

服务／接口／传输／规则测试通过。浏览器已检查明确标记的历史 CSV 回放、暂停、曲线和 3D，同时真实图像推理及 S3 ACK 正常。IMU 当前仍无有效实时样本，待检查接线；回放只证明软件路径。真实动作准确性、新闭环声光效果、物理断线／掉电验收仍待完成。位置双积分会漂移，Yaw 无磁力计参考。
## 自动画面方向

统一应用默认启用 0°／90°／180°／270° 自动校正和自拍镜像。初次请短暂站直，让肩、髋和自然下垂的手进入画面。连续三次扫描方向一致、且候选足够明确时才锁定；初次扫描会增加推理工作，锁定后只保留正常姿态推理。

运动时保持方向锁定，深蹲、弯腰和俯卧撑不会令画面不断旋转。重新摆放摄像头后点击“重新校正方向”。人体信息不足或候选不明确时保持上一角度，暂停计次判定与报警，等待校正成功，不猜测方向。

页面提供自动、固定 0°／90°／180°／270° 和“自拍镜像”开关。默认镜像适合正面自拍习惯；常规摄影或背面拍摄时可关闭。旋转本身不能判断使用者偏好的左右镜像方式。

旋转和镜像在姿态推理、骨架绘制前执行，画面与规则使用同一坐标。方向改变时清除未完成动作和报警，保留已完成次数。当前解决 90° 倍数放置，不是任意倾斜角的连续防抖。

命令行可用 `main.py --rotate 90` 固定顺时针 90°，`--no-mirror` 关闭镜像；旧独立 pose_app.py 保留手动默认值。USB 带宽、JPEG 参数、固件和报警协议均不变。测试包含本机公开 Ultralytics bus.jpg 的四种旋转，不保存用户摄像头图像。

## 界面语言

右上角语言选择器支持英语（`en`）、简体中文（`zh-CN`）及香港繁体中文（`zh-HK`）。浏览器会在本机保存偏好，首次访问跟随浏览器语言；不使用外部翻译服务。

`web/locales.json` 是共享词典；`web/i18n.js` 翻译静态标签、动态状态、图表提示及反馈，不改变协议值。`localization.py` 使用同一词典翻译视频叠字。原始固件诊断和 Profile JSON 保持原样。摄像头视频流为共享资源，因此最后一次语言选择也会改变其他本地查看者的视频叠字。

`docs/assets/` 中三张 1920 × 1080 截图已于 2026-11-11 更新，并嵌入对应语言的根 README，展示摄像头未就绪、IMU 无实时数据的实际状态，没有填入模拟实时测量。

## 动作库与实时训练

六个动作：深蹲、俯卧撑、前弓步、平板支撑、臀桥和鸟狗式，均提供视频、要点和三阶段示意。目前仅深蹲支持 AI 识别，其余为教学预览。新增视频来自 ScottHermanFitness（臀桥）和 Point Performance（鸟狗式）。

侧栏“动作库”下方新增“实时动作监测”。点击卡片主体查看教学，点击箭头进入实时页面；控制台和实时页面沿用同一视频流和训练会话。未支持的动作不能启动 AI 识别。

控制台支持 Arduino 报警、ESP Camera 和 ESP IMU 独立开关，分别显示启用意图与连接状态。开关控制采集及报警发送，不切断供电；Arduino 实际声光执行仍需现场确认。开始／暂停／继续／结束控制计次与视觉报警，暂停冻结计时、保留已完成次数，视频仍可预览。接口为 `/api/modules`、`/api/training`，生命周期测试为 `test_workspace.py`。
