#include "esp_camera.h"

// AI Thinker ESP32-CAM camera pins
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

bool cameraReady = false;
unsigned long lastReadyMessage = 0;

void sendPhoto() {
  camera_fb_t *fb = esp_camera_fb_get();

  if (!fb) {
    Serial.println("ERR_CAPTURE");
    return;
  }

  if (fb->format != PIXFORMAT_JPEG) {
    Serial.println("ERR_NOT_JPEG");
    esp_camera_fb_return(fb);
    return;
  }

  // Header: IMG <byte count> followed by the raw JPEG bytes.
  Serial.printf("IMG %lu\n", (unsigned long)fb->len);

  size_t sent = 0;
  while (sent < fb->len) {
    size_t n = Serial.write(fb->buf + sent, fb->len - sent);
    if (n == 0) {
      delay(1);
    } else {
      sent += n;
    }
  }

  Serial.flush();
  esp_camera_fb_return(fb);
  Serial.println("\nDONE");
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  delay(1200);

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;  // 640 x 480
  config.jpeg_quality = 12;
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("ERR_INIT 0x%x\n", err);
    cameraReady = false;
    return;
  }

  cameraReady = true;
  Serial.println("CAMERA_OK");
}

void loop() {
  if (!cameraReady) {
    delay(1000);
    return;
  }

  // The PC receiver waits for READY before requesting a photo.
  if (millis() - lastReadyMessage >= 1000) {
    Serial.println("READY");
    lastReadyMessage = millis();
  }

  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "CAPTURE") {
      sendPhoto();
    }
  }
}