# Zhang Yancheng：ESP32-S3 + BMI160 本机复现

2026-11-05，Asia/Singapore。身份已由用户明确声明为 Zhang Yancheng，工作分支 `Feat-Integration-Yancheng`。

**本机六轴采集已跑通，当前 S3 保留连续采集固件，串口已释放。** 本轮未接入 CAM、Arduino、Wi-Fi 或电脑 AI，不能把本结果视为完整健身机器人验收。

## 来源与修正

复现来源为 `Feat-Esp-Yuankun` 的提交 `9d583fd1cf0c070752298a1a1233336b12645249`，只引入其 BMI160 诊断、六轴采集和 Windows 接收脚本，再做地址兼容修改。集成分支基点为 `c9646cc175c0b9ab44fe9ee70b234b8c3f5619ca`。本次没有修改其他成员的远端分支。

初次读取板上 `BMI160_Bus_Check_v1`：

- COM4／CH340 可以正常通信；SDA=GPIO4、SCL=GPIO5、I²C=100kHz。
- 0x68 无应答；**0x69 有应答且芯片 ID=0xD1**。
- 原程序把 `RUN_INIT` 固定在 0x68，故停在 INITIAL_ID。

现将两个固件改为：先读取两个合法地址的芯片 ID，仅在恰好一个地址匹配 0xD1 时选择该地址；后续重设、启动、配置和采集均使用选中的地址。无匹配或两个都匹配时停止，避免配置错误对象。接收脚本同步验证新固件版本与选中的地址。

[Bosch BMI160 数据表](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi160-ds000.pdf) 第 93 页说明 0x68 与 0x69 是由 SDO 电平选择的合法地址。本次没有重新接线或量测 SA0/SDO 电压；因此只确认本机实际响应为 0x69，不推断该电平由何种接法产生，也不据此解释 Yuankun 先前在另一台电脑记录的故障。

## 本机环境

| 项目 | 本次值 |
| --- | --- |
| 芯片 | ESP32-S3，revision v0.2 |
| Flash | esptool 实读 16MB |
| PSRAM | 芯片识别报告 embedded 8MB；未做全容量读写测试 |
| 串口 | USB-SERIAL CH340，COM4，115200 baud，8N1 |
| Arduino CLI | 1.5.2-rc.1，fef6e48df |
| ESP32 Arduino core | 本机已有 3.3.3；来源分支曾使用 3.3.12，本轮未升级 |
| esptool | 5.1.0；部分备份使用已有 Python 版 4.5.1 |
| 额外 Arduino 库 | 无，使用 core 自带 Wire 和 esp_timer |
| 固件 | BMI160_Bus_Check_v2_autoaddr；BMI160_SixAxis_v3_autoaddr |
| 编译设置 | ESP32S3 Dev Module、16MB Flash、OPI PSRAM、CDC On Boot Disabled、Hardware CDC and JTAG、16M Flash (3MB APP/9.9MB FATFS) |
| 采集设置 | 两个传感器标称 50Hz；加速度 ±4g；角速度 ±500°/s；未校准 |

有效 FQBN：

```text
esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,CDCOnBoot=default,USBMode=hwcdc,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=115200
```

## 实测结果

证据位于 [evidence/yancheng-2026-11-05](evidence/yancheng-2026-11-05/)。

| 检查 | 结果 |
| --- | --- |
| 新诊断初始化 | 0x69；SOFT_RESET、ACCEL_WAKE、GYRO_WAKE、CONFIG_VERIFY、FINAL 全部通过 |
| 电源管理／错误读回 | PMU=0x14，ERR=0x00 |
| 三秒诊断采样 | 150 组，读取错误 0 |
| 连续采集 | 19:43:49 起，1496 组；设备时间跨度 30.061 秒 |
| 实测读取频率 | 49.7322 Hz |
| 最大读取间隔 | 23.008 ms；大于 30ms 的间隔为 0 |
| 格式／诊断错误 | 0／0 |
| 序号中断／非递增时间戳 | 0／0 |
| 饱和行 | 0 |
| 加速度模长均值 | 1.00422g；物理放置及精密标定未单独确认 |
| 独立 CSV 核验 | 有限值、int16 范围、原始值到 g/°/s 换算、序号、读取时间、24-bit 传感器时钟递增均通过 |
| 构建和上传 | 两个固件均成功，写入哈希校验均通过 |

连续采集程序报告 6 次有效配置、`read_errors=0`。读取频率按设备读取起始时间计算；它不等同于精确内部采样时刻，也不能证明无限时长零丢样。0x69 已上板实测；0x68 路径未通过改线另做硬件测试。

## 再次使用

板上已经是六轴采集固件，保持现有接线即可。Arduino 串口监视器选 **COM4／115200**，可直接看到 15 列 CSV 和每五秒的配置、状态信息。采集脚本与监视器需要轮流独占串口。

在仓库根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\esp32-camera\capture_bmi160.ps1 -Port COM4 -Seconds 30 -Label yancheng_repeat
```

默认保存在该目录下被 Git 忽略的 `captures/bmi160/`；生成 CSV、串口日志与 JSON 汇总，校验失败时返回错误。

需重新编译／烧录时，在 Arduino IDE 打开 `BMI160_SixAxis/BMI160_SixAxis.ino`，使用上述开发板设置和 COM4；无需安装第三方传感器库。诊断版则打开 `BMI160_Bus_Check/BMI160_Bus_Check.ino`，上传后依次发送 `INFO`、`PROBE`、`RUN_INIT`，仅在 `INIT_RESULT pass=1` 后发送 `SAMPLE`。

烧录前已备份原 Flash 的前 512KiB，足够覆盖本次替换的引导、分区表及原诊断应用；**它不是完整 16MB 备份**，保留在本轮 outputs 中。高速完整读取曾因串口数据不完整失败，最后 115200 的 512KiB 读取成功。备份 SHA256：`1487766a7fb0cf13f06d148362d1298abd71c812569b899eb3706c5201b11897`。

## 后续边界

本次完成 S3 + BMI160 → USB → 电脑 CSV。运动方向标定、零偏校准、长时间稳定性、CAM 图像、双板通信、Wi-Fi 数据上传、AI 和 Arduino 反馈均未在本机验收。
