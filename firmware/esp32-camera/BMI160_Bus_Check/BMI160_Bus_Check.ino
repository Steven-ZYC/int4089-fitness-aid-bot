#include <Arduino.h>
#include <Wire.h>
#include <cstring>
#include "esp_timer.h"

#if !defined(CONFIG_IDF_TARGET_ESP32S3) || ARDUINO_USB_CDC_ON_BOOT
#error "Use ESP32S3 Dev Module, USB CDC On Boot Disabled, COM/CH340."
#endif

// Standalone diagnosis: no camera, Wi-Fi, ESP-NOW or sampling task.
// Only RUN_INIT writes volatile reset/PMU/configuration registers.
constexpr uint8_t kAddress = 0x68;
constexpr int kSda = 4, kScl = 5;
constexpr uint8_t kConfig[4] = {0x27, 0x05, 0x27, 0x02};
bool busReady = false, initialized = false;
char command[40];
size_t commandLength = 0;
bool commandOverflow = false;

void pins(const char *stage) {
  Serial.printf("PINS stage=%s sda=%d scl=%d measurement=DIGITAL_ONLY\n",
                stage, digitalRead(kSda), digitalRead(kScl));
}

bool readBytes(uint8_t address, uint8_t reg, uint8_t *bytes, size_t count,
               const char *stage, bool verbose = true) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  const int64_t start = esp_timer_get_time();
  // In this core, false queues the register selection; it is not an ACK probe.
  const uint8_t queued = Wire.endTransmission(false);
  const size_t got = queued == 0 ? Wire.requestFrom(address, count, true) : 0;
  bool ok = queued == 0 && got == count;
  if (ok) {
    for (size_t i = 0; i < count; ++i) bytes[i] = Wire.read();
  }
  while (Wire.available()) Wire.read();
  if (verbose || !ok) {
    Serial.printf("READ stage=%s address=0x%02X reg=0x%02X queued_code=%u received=%u expected=%u ok=%u elapsed_us=%lld",
                  stage, address, reg, queued, unsigned(got), unsigned(count), ok,
                  esp_timer_get_time() - start);
    if (ok && count == 1) Serial.printf(" value=0x%02X", bytes[0]);
    Serial.println();
  }
  delay(1);
  return ok;
}

void probeAll() {
  pins("PROBE");
  for (uint8_t address : {uint8_t(0x68), uint8_t(0x69)}) {
    Wire.beginTransmission(address);
    const int64_t start = esp_timer_get_time();
    const uint8_t code = Wire.endTransmission(true);
    Serial.printf("PROBE address=0x%02X stop_code=%u elapsed_us=%lld\n",
                  address, code, esp_timer_get_time() - start);
    delay(1);
    uint8_t id = 0;
    const bool ok = readBytes(address, 0x00, &id, 1, "IDENTITY");
    Serial.printf("IDENTITY address=0x%02X read_ok=%u expected_id_match=%u\n",
                  address, ok, ok && id == 0xD1);
  }
  Serial.println("PROBE_DONE configuration_written=NO");
}

bool snapshot(const char *stage, uint8_t expectedPmu) {
  uint8_t id = 0, pmu = 0, err = 0;
  const bool idOk = readBytes(kAddress, 0x00, &id, 1, stage);
  const bool pmuOk = readBytes(kAddress, 0x03, &pmu, 1, stage);
  const bool errOk = readBytes(kAddress, 0x02, &err, 1, stage);
  pins(stage);
  const bool ok = idOk && id == 0xD1 && pmuOk && (pmu & 0x3F) == expectedPmu && errOk && err == 0;
  Serial.printf("STATE stage=%s valid=%u expected_pmu=0x%02X\n", stage, ok, expectedPmu);
  return ok;
}

uint8_t writeByte(uint8_t reg, uint8_t value, const char *stage) {
  pins(stage);
  Wire.beginTransmission(kAddress);
  Wire.write(reg);
  Wire.write(value);
  const int64_t start = esp_timer_get_time();
  const uint8_t code = Wire.endTransmission(true);
  Serial.printf("WRITE stage=%s reg=0x%02X value=0x%02X code=%u elapsed_us=%lld\n",
                stage, reg, value, code, esp_timer_get_time() - start);
  delay(1); // Exceeds the datasheet post-write idle interval in suspend mode.
  return code;
}

bool powerStep(const char *stage, uint8_t value, unsigned waitMs, uint8_t pmu) {
  const uint8_t code = writeByte(0x7E, value, stage);
  // Inspect after settling even if the command transaction returned an error.
  delay(waitMs);
  const bool stateOk = snapshot(stage, pmu);
  if (code || !stateOk) {
    Serial.printf("INIT_RESULT pass=0 stage=%s write_code=%u state_ok=%u\n", stage, code, stateOk);
    return false;
  }
  return true;
}

void runInit() {
  initialized = false;
  Serial.println("INIT_BEGIN address=0x68 settings=VOLATILE_ONLY");
  uint8_t id = 0;
  if (!readBytes(kAddress, 0x00, &id, 1, "INITIAL_ID") || id != 0xD1) {
    Serial.println("INIT_RESULT pass=0 stage=INITIAL_ID");
    return;
  }
  if (!powerStep("SOFT_RESET", 0xB6, 100, 0x00)) return;
  if (!powerStep("ACCEL_WAKE", 0x11, 10, 0x10)) return;
  if (!powerStep("GYRO_WAKE", 0x15, 100, 0x14)) return;
  for (unsigned i = 0; i < 4; ++i) {
    if (writeByte(0x40 + i, kConfig[i], "CONFIG") != 0) {
      Serial.println("INIT_RESULT pass=0 stage=CONFIG_WRITE");
      return;
    }
  }
  delay(200);
  uint8_t actual[4] = {};
  const bool configOk = readBytes(kAddress, 0x40, actual, 4, "CONFIG_VERIFY") &&
                        memcmp(actual, kConfig, sizeof(actual)) == 0;
  const bool stateOk = snapshot("FINAL", 0x14);
  initialized = configOk && stateOk;
  Serial.printf("INIT_RESULT pass=%u stage=FINAL config_ok=%u state_ok=%u\n",
                initialized, configOk, stateOk);
}

int16_t signed16(const uint8_t *bytes) {
  int32_t value = bytes[0] | (uint16_t(bytes[1]) << 8);
  if (value & 0x8000) value -= 65536;
  return int16_t(value);
}

void samples() {
  if (!initialized) { Serial.println("ERR_SAMPLE_REQUIRES_INIT_PASS"); return; }
  unsigned count = 0, errors = 0;
  const int64_t start = esp_timer_get_time();
  while (esp_timer_get_time() - start < 3000000) {
    uint8_t status = 0, bytes[15] = {};
    if (!readBytes(kAddress, 0x1B, &status, 1, "SAMPLE_STATUS", false)) ++errors;
    else if ((status & 0xC0) == 0xC0) {
      if (!readBytes(kAddress, 0x0C, bytes, sizeof(bytes), "SAMPLE_DATA", false)) ++errors;
      else {
        const uint32_t ticks = bytes[12] | (uint32_t(bytes[13]) << 8) | (uint32_t(bytes[14]) << 16);
        Serial.printf("SAMPLE seq=%u sensor_ticks=%lu ax=%d ay=%d az=%d gx=%d gy=%d gz=%d\n",
                      ++count, (unsigned long)ticks, signed16(bytes + 6), signed16(bytes + 8),
                      signed16(bytes + 10), signed16(bytes), signed16(bytes + 2), signed16(bytes + 4));
      }
    }
    if (errors >= 3) break;
    delay(2);
  }
  Serial.printf("SAMPLE_DONE count=%u errors=%u elapsed_us=%lld timing_acceptance=NOT_TESTED\n",
                count, errors, esp_timer_get_time() - start);
}

void info() {
  Serial.printf("INFO fw=BMI160_Bus_Check_v1 bus_ready=%u initialized=%u sda=4 scl=5 hz=100000 timeout_ms=100 wifi=OFF\n",
                busReady, initialized);
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  busReady = Wire.begin(kSda, kScl, 100000);
  if (busReady) Wire.setTimeOut(100);
  info();
  if (busReady) probeAll();
  Serial.println("READY commands=INFO,PROBE,RUN_INIT,SAMPLE");
}

void loop() {
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      command[commandLength] = 0;
      if (commandOverflow) Serial.println("ERR_COMMAND_TOO_LONG");
      else if (strcmp(command, "INFO") == 0) info();
      else if (!busReady) Serial.println("ERR_I2C_BEGIN");
      else if (strcmp(command, "PROBE") == 0) probeAll();
      else if (strcmp(command, "RUN_INIT") == 0) runInit();
      else if (strcmp(command, "SAMPLE") == 0) samples();
      else Serial.println("ERR_COMMAND");
      commandLength = 0; commandOverflow = false;
    } else if (commandLength < sizeof(command) - 1) command[commandLength++] = c;
    else commandOverflow = true;
  }
  delay(1);
}
