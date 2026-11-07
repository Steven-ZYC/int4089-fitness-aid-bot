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

当前两套数据尚未统一时间戳；面板只是共同展示，不能据此声称摄像头和 IMU 已完成同步融合。姿态服务仍需全身入画，且动作阈值尚未用真实训练数据校准。Arduino Uno 的反馈链路也尚未接入。
