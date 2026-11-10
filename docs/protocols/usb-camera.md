# CAM ↔ 电脑 USB 图像／控制协议

当前固件：[Cam_USB_Bridge](../../firmware/usb-ai-bridge/Cam_USB_Bridge/Cam_USB_Bridge.ino)。电脑实现：[serial_camera.py](../../app/serial_camera.py)。

## 串口与图像

921600 波特率、8N1，无流控。图像为 640×480 JPEG，quality=18，两个 PSRAM 帧缓冲，LATEST 模式。相机与 S3 的引脚和无线 MAC 不随本轮仓库整理改变。

电脑启动时发送 `INFO\n`，要求返回 `fw=Cam_USB_Bridge_v1`。随后每轮批量写入三条命令，固件按顺序响应：

```text
ALARM 0\n       # 或 ALARM 1；数字为报警关／开
STATUS\n
CAPTURE\n
```

响应顺序：

```text
CMD_OK state=0
BRIDGE role=CAM state=... ack=... ack_state=... ack_age_ms=... errors=... drops=...
META seq=... request_us=... frame_us=... acquired_us=... discarded=... width=640 height=480 len=N
IMG N crc=xxxxxxxx
<N 个原始 JPEG 字节>
\nDONE seq=... written=N send_us=...
```

上例 `\n` 表示换行符，`N` 和省略号是占位符，不按字面发送。CRC 是 JPEG 原始字节的 CRC32，8 位十六进制；不使用 Base64。电脑按精确长度读取二进制，再检查 CRC、JPEG 标记、解码尺寸、帧尾序号和长度，不能把 JPEG 当作逐行文本。

`READY` 等文本可出现在帧外。无线任务不写 CAM USB，避免将异步日志插入图像。当前只有一个电脑工作线程访问串口。

## 新鲜度与报警

- 相机取帧时只接受 first-DMA 时间戳不超过当前时刻 200ms 的图像。它不是曝光时间，也不是到网页的完整延迟；旧单次拍照要求“请求后才开始取帧”，当前双缓冲策略改为“最近已完成的帧”。
- 电脑缓存的图像超过 1.5 秒不可用；推理线程跳过重复序号。
- 电脑判定超过 1 秒不刷新时，工作线程发送关闭。CAM 超过 1.2 秒没有有效电脑报警命令时也发送关闭。
- `CMD_OK` 表示 CAM 解析了命令；S3 是否收到需看无线 ACK。USB 错误会终止工作线程，后续依赖两端超时清除旧报警。
- 当前无自动重连，断线后重新确认串口并启动应用。

## 性能

实测 268 帧／30 秒，约 8.93 FPS；带 AI 页面约 9 FPS，画面细节／光照会影响 JPEG 大小和速率。CRC、解码、帧尾校验始终保留。

电脑可用 `serial://COM3?baud=460800` 显式选择历史速率，但它只修改电脑配置，固件必须使用相同速率。默认保持 921600，不进行自动速率切换。
