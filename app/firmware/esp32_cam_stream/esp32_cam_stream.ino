/*
 * ESP32-CAM 极简 MJPEG 推流固件
 * ---------------------------------------------
 * 比官方的 CameraWebServer 精简得多：只做一件事——把摄像头画面推成 MJPEG 流。
 * 没有 SD 卡、人脸识别、LED 控制那些用不上的代码，启动更快、内存占用更小。
 *
 * 接口：
 *   http://<IP>/        → 一行文字，打印 IP 和状态
 *   http://<IP>/stream  → MJPEG 视频流（PC 端的 app.py 用这个）
 *   http://<IP>/jpg     → 单张 JPEG 快照
 *
 * 烧录：
 *   板型选 "AI Thinker ESP32-CAM"，端口选 CH340 那个 COM 口。
 *   需要 GPIO0 接 GND 才能进下载模式（烧完拔掉再上电）。
 *
 * ⚠️ 只能连 2.4 GHz 的 Wi-Fi，ESP32 不支持 5 GHz。
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// ==================== 凭据 ====================
// 放在同目录的 secrets.h 里（不要提交到版本库）。
// ESP32 只能连 2.4 GHz，SSID 不要带 _5G 后缀。
#include "secrets.h"
#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_SSID"
#define WIFI_PASS "YOUR_PASS"
#endif
// =============================================

// AI Thinker ESP32-CAM 的摄像头引脚
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define BOUNDARY "frameboundary"

static httpd_handle_t server = NULL;

// ---------- MJPEG 流 ----------
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=" BOUNDARY);
  if (res != ESP_OK) return res;

  char part[96];
  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[cam] fb_get 失败");
      return ESP_FAIL;
    }
    size_t hlen = snprintf(part, sizeof(part),
                           "\r\n--" BOUNDARY "\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
                           (unsigned)fb->len);
    res = httpd_resp_send_chunk(req, part, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (res != ESP_OK) break;      // 客户端断开
  }
  return res;
}

// ---------- 单张快照 ----------
static esp_err_t jpg_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return httpd_resp_send_500(req);
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  esp_err_t r = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return r;
}

// ---------- 首页 ----------
static esp_err_t index_handler(httpd_req_t *req) {
  char msg[200];
  snprintf(msg, sizeof(msg),
           "ESP32-CAM ready\nIP: %s\nstream: http://%s/stream\nsnapshot: http://%s/jpg\n",
           WiFi.localIP().toString().c_str(),
           WiFi.localIP().toString().c_str(),
           WiFi.localIP().toString().c_str());
  httpd_resp_set_type(req, "text/plain; charset=utf-8");
  return httpd_resp_send(req, msg, HTTPD_RESP_USE_STRLEN);
}

void startServer() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.ctrl_port = 32768;
  cfg.max_uri_handlers = 8;
  cfg.lru_purge_enable = true;      // 客户端断开后自动回收连接，防止长时间推流把句柄占满

  if (httpd_start(&server, &cfg) != ESP_OK) {
    Serial.println("[http] 启动失败");
    return;
  }
  httpd_uri_t u1 = {"/",       HTTP_GET, index_handler,  NULL};
  httpd_uri_t u2 = {"/stream", HTTP_GET, stream_handler, NULL};
  httpd_uri_t u3 = {"/jpg",    HTTP_GET, jpg_handler,    NULL};
  httpd_register_uri_handler(server, &u1);
  httpd_register_uri_handler(server, &u2);
  httpd_register_uri_handler(server, &u3);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== ESP32-CAM MJPEG server ===");

  camera_config_t cfg;
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer   = LEDC_TIMER_0;
  cfg.pin_d0 = Y2_GPIO_NUM;  cfg.pin_d1 = Y3_GPIO_NUM;
  cfg.pin_d2 = Y4_GPIO_NUM;  cfg.pin_d3 = Y5_GPIO_NUM;
  cfg.pin_d4 = Y6_GPIO_NUM;  cfg.pin_d5 = Y7_GPIO_NUM;
  cfg.pin_d6 = Y8_GPIO_NUM;  cfg.pin_d7 = Y9_GPIO_NUM;
  cfg.pin_xclk = XCLK_GPIO_NUM;
  cfg.pin_pclk = PCLK_GPIO_NUM;
  cfg.pin_vsync = VSYNC_GPIO_NUM;
  cfg.pin_href = HREF_GPIO_NUM;
  cfg.pin_sccb_sda = SIOD_GPIO_NUM;
  cfg.pin_sccb_scl = SIOC_GPIO_NUM;
  cfg.pin_pwdn = PWDN_GPIO_NUM;
  cfg.pin_reset = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.grab_mode = CAMERA_GRAB_LATEST;   // 追最新帧，避免延迟累积
  cfg.fb_location  = CAMERA_FB_IN_PSRAM;
  cfg.frame_size   = FRAMESIZE_VGA;     // 640x480，检测精度和带宽的折中
  cfg.jpeg_quality = 12;                // 0~63，越小越清晰也越占带宽
  cfg.fb_count     = 2;

  esp_err_t err = esp_camera_init(&cfg);
  if (err != ESP_OK) {
    Serial.printf("[cam] 初始化失败 0x%x\n", err);
    return;
  }
  sensor_t *s = esp_camera_sensor_get();
  Serial.printf("[cam] sensor PID=0x%02x\n", s ? s->id.PID : 0);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);          // 关省电，降低推流延迟（也减少掉线）
  WiFi.setAutoReconnect(true);

  // 先扫一遍，把目标 AP 的信号强度和加密方式打出来，方便排障
  Serial.println("[scan] 扫描中...");
  int n = WiFi.scanNetworks();
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == WIFI_SSID) {
      Serial.printf("[scan] 目标 %s RSSI=%d dBm 信道=%d 加密=%d\n",
                    WiFi.SSID(i).c_str(), WiFi.RSSI(i), WiFi.channel(i), (int)WiFi.encryptionType(i));
    }
  }
  Serial.printf("[scan] 共 %d 个 AP\n", n);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("[wifi] 连接 %s ", WIFI_SSID);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries++ < 60) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[wifi] 已连接，IP = %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[http] 视频流地址 http://%s/stream\n", WiFi.localIP().toString().c_str());
    startServer();
  } else {
    Serial.println("[wifi] 连接失败：检查 SSID 是否为 2.4G、密码是否正确");
  }
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last < 2000) {
    delay(20);
    return;
  }
  last = millis();

  wl_status_t st = WiFi.status();
  if (st != WL_CONNECTED) {
    Serial.printf("[wifi] 断开 status=%d，重连中...\n", (int)st);
    WiFi.reconnect();
    delay(1000);
    return;
  }
  Serial.printf("[wifi] 正常 IP=%s RSSI=%d dBm 在线\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());
}
