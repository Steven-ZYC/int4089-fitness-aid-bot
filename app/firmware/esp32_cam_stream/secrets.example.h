// 复制本文件为 secrets.h，填入自己的 Wi-Fi，然后编译。
// secrets.h 已被 .gitignore 忽略，不要提交真实密码。
//
// ⚠️ ESP32（经典款）只支持 2.4 GHz。SSID 不要带 _5G 后缀，
//    否则扫描能看到、但永远连不上（实测表现：连 30 秒后掉线）。
#pragma once
#define WIFI_SSID "YOUR_SSID_2G"
#define WIFI_PASS "YOUR_PASSWORD"
