# 统一运动分析面板

共享分支 `Feat-UI-Design` 将 Haoyu 的电脑端姿态服务与 Yancheng 的 ESP32-S3／BMI160 IMU 面板放到同一窗口。画面布局参考用户提供的 FitCoach AI 截图，但只展示实际可用的数据；示例图中的教程视频、膝轨迹和动作质量项目没有接入真实来源，暂不显示。

## 启动

在仓库根目录分别启动两个进程：

```powershell
# 终端 1：姿态服务。先安装 app/requirements.txt 所需依赖。
cd app
python pose_app.py --source 0 --action squat --no-browser

# 终端 2：统一面板。先按 tools/imu-position/README.md 安装其依赖。
cd tools/imu-position
python -m imu_position --unified
```

摄像头为 ESP32-CAM 时，把 `--source 0` 换成 `--source http://<IP>/stream`；姿态服务默认在 `127.0.0.1:8010`。若端口改变，面板使用 `--pose-url http://127.0.0.1:<端口>`。

统一窗口上半部显示姿态视频、动作阶段、计次、角度、最近一次判定和评分。下半部同时显示 IMU 源数据曲线与 3D 姿态／位置。顶栏沿用原有串口连接、CSV 回放、零飘 profile 管理和暂停操作。姿态服务未启动或断线时，窗口显示连接错误并自动重试；IMU 未连接时可独立查看姿态结果。

## 两路数据配对

姿态服务在每帧推理后输出 `frame_time_ms`、`frame_id`，在完成一次动作时给 `last` 结果附 `completed_at_ms`。IMU 面板在电脑端处理串口样本或 CSV 回放样本时记录本机到达时间，保留零飘处理后的姿态、陀螺和加速度值。统一面板按时间最近原则配对，只有时间差不超过 **±400 ms** 且姿态帧新鲜时才显示“数据已配对”；否则明确显示等待状态。每次完成动作只记录一次相机判定与同时刻 IMU 数据，避免重复计次。可在面板点击“导出已配对动作记录”保存 JSONL；默认目录为被 Git 忽略的 `tools/imu-position/captures/`，文件只含数值和判定，不含图像。

两套进程都在同一台电脑上，故使用同一个系统时钟。串口接收、推理与 HTTP 轮询会带来延迟，因此这是软件级近似对齐，**不是硬件同步或经验证的传感器融合算法**。CSV 回放会按播放时的本机时间配对，并标为“CSV 回放”。姿态服务仍需全身入画，动作阈值尚未用真实训练数据校准；Arduino Uno 的反馈链路尚未接入。
