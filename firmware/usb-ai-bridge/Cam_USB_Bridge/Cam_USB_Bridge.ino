#include "../AlarmRadio.h"
#include "esp_camera.h"
#include "esp_timer.h"

#if !CONFIG_IDF_TARGET_ESP32
#error "Use AI Thinker ESP32-CAM, not the ESP32-S3 IMU board."
#endif

// This sketch uses the same AI Thinker camera pins as the preserved USB demo.
static constexpr char kFirmware[] = "Cam_USB_Bridge_v1";
static bool cameraReady = false;
static uint32_t sequence = 0;
static unsigned long lastReady = 0;
static char command[32];
static size_t commandLength = 0;
static bool commandOverflow = false;

static void printInfo() {
  sensor_t *sensor = esp_camera_sensor_get();
  if (!cameraReady || !sensor) {
    Serial.println("ERR_NOT_READY");
    return;
  }
  const char *name = sensor->id.PID == OV2640_PID ? "OV2640" : "UNKNOWN";
  Serial.printf(
      "INFO fw=%s chip=%s cpu_mhz=%u flash_bytes=%u psram_bytes=%u "
      "sensor_pid=0x%04X sensor_ver=0x%02X sensor_name=%s "
      "width=640 height=480 format=JPEG fb_count=2 grab=LATEST baud=921600 jpeg_quality=18\n",
      kFirmware, ESP.getChipModel(), ESP.getCpuFreqMHz(),
      ESP.getFlashChipSize(), ESP.getPsramSize(), sensor->id.PID,
      sensor->id.VER, name);
}

static void sendFreshPhoto() {
  const int64_t requestUs = esp_timer_get_time();
  camera_fb_t *fb = nullptr;
  int64_t frameUs = 0;
  unsigned discarded = 0;

  // Double-buffer latest mode overlaps capture and USB transfer. Accept only
  // frames whose first-DMA timestamp is at most 200 ms old, never future-dated.
  for (unsigned attempt = 0; attempt < 4; ++attempt) {
    if (esp_timer_get_time() - requestUs > 2000000) break;
    fb = esp_camera_fb_get();  // The driver's own wait can extend the 2 s budget.
    if (!fb) {
      Serial.println("ERR_CAPTURE");
      return;
    }
    frameUs = static_cast<int64_t>(fb->timestamp.tv_sec) * 1000000LL +
              fb->timestamp.tv_usec;
    const int64_t nowUs = esp_timer_get_time();
    if (frameUs >= nowUs - 200000 && frameUs <= nowUs) break;
    esp_camera_fb_return(fb);
    fb = nullptr;
    ++discarded;
    delay(1);
  }
  if (!fb) {
    Serial.println("ERR_FRESH_FRAME");
    return;
  }

  const int64_t acquiredUs = esp_timer_get_time();
  if (fb->format != PIXFORMAT_JPEG || fb->width != 640 || fb->height != 480 ||
      fb->len < 4 || fb->len > 2097152 || fb->buf[0] != 0xFF ||
      fb->buf[1] != 0xD8 || fb->buf[fb->len - 2] != 0xFF ||
      fb->buf[fb->len - 1] != 0xD9) {
    esp_camera_fb_return(fb);
    Serial.println("ERR_JPEG_FRAME");
    return;
  }

  ++sequence;
  const size_t length = fb->len;
  Serial.printf(
      "META seq=%lu request_us=%lld frame_us=%lld acquired_us=%lld "
      "discarded=%u width=%u height=%u len=%u\n",
      static_cast<unsigned long>(sequence), requestUs, frameUs, acquiredUs,
      discarded, static_cast<unsigned>(fb->width),
      static_cast<unsigned>(fb->height), static_cast<unsigned>(length));
  Serial.printf("IMG %u crc=%08lx\n", static_cast<unsigned>(length), (unsigned long)bridge::crc32(fb->buf,length));
  const int64_t sendStartUs = esp_timer_get_time();
  size_t sent = 0;
  while (sent < length) {
    sent += Serial.write(fb->buf + sent, length - sent);
    if (sent < length) delay(1);
  }
  Serial.flush();
  const int64_t sendUs = esp_timer_get_time() - sendStartUs;
  esp_camera_fb_return(fb);
  Serial.printf("\nDONE seq=%lu written=%u send_us=%lld\n",
                static_cast<unsigned long>(sequence),
                static_cast<unsigned>(sent), sendUs);
}

void setup() {
  Serial.begin(921600);
  delay(1200);
  if (!psramFound()) {
    Serial.println("ERR_PSRAM");
    return;
  }

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5;
  config.pin_d1 = 18;
  config.pin_d2 = 19;
  config.pin_d3 = 21;
  config.pin_d4 = 36;
  config.pin_d5 = 39;
  config.pin_d6 = 34;
  config.pin_d7 = 35;
  config.pin_xclk = 0;
  config.pin_pclk = 22;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_sccb_sda = 26;
  config.pin_sccb_scl = 27;
  config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 18;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  const esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("ERR_INIT 0x%x\n", err);
    return;
  }
  // Let the sensor start producing frames before accepting requests.
  for (unsigned i = 0; i < 3; ++i) {
    camera_fb_t *warmup = esp_camera_fb_get();
    if (!warmup) {
      Serial.println("ERR_WARMUP");
      return;
    }
    esp_camera_fb_return(warmup);
    delay(20);
  }
  if (!bridge::begin()) { Serial.println("ERR_RADIO_INIT"); return; }
  cameraReady = true;
  Serial.println("CAMERA_OK");
  printInfo();
}

void loop() {
  if (!cameraReady) {
    delay(1000);
    return;
  }
  if (millis() - lastReady >= 1000) {
    Serial.println("READY");
    lastReady = millis();
  }
  while (Serial.available()) {
    const char next = static_cast<char>(Serial.read());
    if (next == '\r') continue;
    if (next != '\n') {
      if (commandLength < sizeof(command) - 1) command[commandLength++] = next;
      else commandOverflow = true;
      continue;
    }
    command[commandLength] = '\0';
    if (commandOverflow) Serial.println("ERR_COMMAND_LENGTH");
    else if (strcmp(command, "INFO") == 0) printInfo();
    else if (strcmp(command, "CAPTURE") == 0) sendFreshPhoto();
    else if (strcmp(command, "ALARM 0") == 0 || strcmp(command, "ALARM 1") == 0) {
      bridge::command(command[6]=='1');
      Serial.printf("CMD_OK state=%c\n",command[6]);
    }
    else if (strcmp(command, "STATUS") == 0) bridge::status();
    else Serial.println("ERR_COMMAND");
    commandLength = 0;
    commandOverflow = false;
  }
  delay(1);
}
