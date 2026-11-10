#include <Arduino.h>
#include <esp_arduino_version.h>
#include <esp_psram.h>

#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "Select ESP32S3 Dev Module for this sketch, not AI Thinker ESP32-CAM."
#endif

#if ARDUINO_USB_CDC_ON_BOOT
#error "This COM-port guide requires USB CDC On Boot: Disabled."
#endif

// Stage 1: inspect the S3 through its USB-to-UART (COM) port.
// No external GPIO, camera, IMU, Wi-Fi, or flash filesystem is accessed.
void printBoardReport() {
  const uint32_t flashBytes = ESP.getFlashChipSize();
  const bool hasPsram = psramFound();
  const size_t psramBytes = hasPsram ? esp_psram_get_size() : 0;

  Serial.println();
  Serial.println("=== S3_BOARD_CHECK ===");
  Serial.printf("chip=%s\n", ESP.getChipModel());
  Serial.printf("revision=%u cores=%u cpu_mhz=%u\n",
                ESP.getChipRevision(), ESP.getChipCores(), ESP.getCpuFreqMHz());
  Serial.printf("arduino_core=%s\n", ESP_ARDUINO_VERSION_STR);
  Serial.printf("esp_idf=%s\n", ESP.getSdkVersion());
  Serial.printf("flash_bytes=%lu\n", static_cast<unsigned long>(flashBytes));
  Serial.printf("psram_found=%s\n", hasPsram ? "YES" : "NO");
  Serial.printf("psram_bytes=%lu\n", static_cast<unsigned long>(psramBytes));
  Serial.printf("psram_heap_bytes=%lu\n",
                static_cast<unsigned long>(ESP.getPsramSize()));
  Serial.printf("free_psram_bytes=%lu\n",
                static_cast<unsigned long>(ESP.getFreePsram()));
  Serial.printf("free_heap_bytes=%lu\n",
                static_cast<unsigned long>(ESP.getFreeHeap()));

  if (!hasPsram || psramBytes == 0) {
    Serial.println("CHECK: PSRAM not detected. Verify OPI PSRAM setting and board marking.");
  } else if (flashBytes == 16UL * 1024 * 1024 &&
             psramBytes == 8UL * 1024 * 1024) {
    Serial.println("MEMORY: matches expected N16R8 capacities.");
  } else {
    Serial.println("CHECK: capacities differ from expected N16R8. Record actual values.");
  }

  Serial.println("READY: serial diagnostics only; peripherals and networking are not tested.");
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  printBoardReport();
}

void loop() {
  delay(5000);
  printBoardReport();
}
