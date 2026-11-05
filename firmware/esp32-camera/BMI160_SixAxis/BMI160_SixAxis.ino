#include <Arduino.h>
#include <Wire.h>
#include <esp_timer.h>

#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "Select ESP32S3 Dev Module."
#endif
#if ARDUINO_USB_CDC_ON_BOOT
#error "Use USB CDC On Boot: Disabled with the COM/CH340 port."
#endif

// Register values and sensitivities: Bosch BMI160 datasheet DS000-09.
constexpr uint8_t IMU_ADDRESS = 0x68;
constexpr int SDA_PIN = 4;
constexpr int SCL_PIN = 5;
constexpr uint32_t I2C_HZ = 100000;
constexpr uint8_t EXPECTED_CONFIG[] = {0x27, 0x05, 0x27, 0x02};
constexpr float ACCEL_LSB_PER_G = 8192.0f;  // +/-4 g
constexpr float GYRO_LSB_PER_DPS = 65.6f;  // +/-500 degrees/second
constexpr char CSV_HEADER[] =
    "sample_seq,t_read_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,"
    "ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps";

bool ready = false;
uint32_t sampleCount = 0;
uint32_t readErrors = 0;
unsigned consecutiveErrors = 0;
uint32_t windowSamples = 0;
int64_t windowStartUs = 0;
int64_t lastDataUs = 0;

bool readRegisters(uint8_t reg, uint8_t *data, size_t length) {
  Wire.beginTransmission(IMU_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(IMU_ADDRESS, length, true) != length) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for (size_t i = 0; i < length; ++i) data[i] = Wire.read();
  return true;
}

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(IMU_ADDRESS);
  Wire.write(reg);
  Wire.write(value);
  const uint8_t result = Wire.endTransmission(true);
  // Also meets the longer post-write delay needed while sensors are suspended.
  delay(1);
  return result == 0;
}

void stopAcquisition(const char *reason) {
  ready = false;
  Serial.printf("# FATAL %s; inspect output and disconnect USB before changing wires.\n", reason);
}

bool printAndCheckConfig() {
  uint8_t config[4] = {};
  uint8_t power = 0, error = 0, identity = 0;
  if (!readRegisters(0x40, config, sizeof(config)) ||
      !readRegisters(0x03, &power, 1) ||
      !readRegisters(0x02, &error, 1) ||
      !readRegisters(0x00, &identity, 1)) return false;

  Serial.printf("# CONFIG firmware=BMI160_SixAxis_v2 chip_id=0x%02X address=0x68 "
                "acc_conf=0x%02X acc_range=0x%02X gyr_conf=0x%02X gyr_range=0x%02X "
                "pmu=0x%02X err=0x%02X odr_hz=50 accel_unit=g gyro_unit=deg/s calibrated=NO\n",
                identity, config[0], config[1], config[2], config[3], power, error);
  if (identity != 0xD1 || (power & 0x3F) != 0x14 || error != 0) return false;
  for (size_t i = 0; i < sizeof(config); ++i) {
    if (config[i] != EXPECTED_CONFIG[i]) return false;
  }
  return true;
}

int16_t decodeInt16(const uint8_t *bytes) {
  int32_t value = bytes[0] | (static_cast<uint16_t>(bytes[1]) << 8);
  if (value & 0x8000) value -= 0x10000;
  return static_cast<int16_t>(value);
}

bool initializeSensor() {
  uint8_t identity = 0;
  if (!readRegisters(0x00, &identity, 1) || identity != 0xD1) return false;
  // Reset volatile settings, then wake each sensor with its specified delay.
  // No NVM programming or persistent offset compensation is performed.
  if (!writeRegister(0x7E, 0xB6)) return false;
  delay(100);
  if (!writeRegister(0x7E, 0x11)) return false;
  delay(10);
  if (!writeRegister(0x7E, 0x15)) return false;
  delay(100);

  // Both sensors: nominal 50 Hz, normal bandwidth; accel +/-4 g, gyro +/-500 dps.
  for (uint8_t i = 0; i < sizeof(EXPECTED_CONFIG); ++i) {
    if (!writeRegister(0x40 + i, EXPECTED_CONFIG[i])) return false;
  }
  delay(200);  // Allow digital filters to settle before retaining samples.
  uint8_t discard[15];
  if (!readRegisters(0x0C, discard, sizeof(discard))) return false;
  return printAndCheckConfig();
}

void setup() {
  // Queue diagnostic text so its UART transmission does not stall sampling.
  const size_t txBufferSize = Serial.setTxBufferSize(2048);
  Serial.begin(115200);
  delay(1500);
  if (txBufferSize < 2048) {
    stopAcquisition("SERIAL_TX_BUFFER_ALLOCATION_FAILED");
    return;
  }
  Serial.println("# BMI160_SIX_AXIS_START");
  if (!Wire.begin(SDA_PIN, SCL_PIN, I2C_HZ)) {
    stopAcquisition("I2C_INIT_FAILED");
    return;
  }
  Wire.setTimeOut(100);
  if (!initializeSensor()) {
    stopAcquisition("IDENTITY_OR_CONFIGURATION_FAILED");
    return;
  }
  Serial.println(CSV_HEADER);
  ready = true;
  windowStartUs = lastDataUs = esp_timer_get_time();
}

void noteReadError() {
  ++readErrors;
  if (++consecutiveErrors >= 5) stopAcquisition("REPEATED_I2C_READ_FAILURE");
  delay(20);
}

void loop() {
  if (!ready) {
    delay(100);
    return;
  }
  uint8_t status = 0;
  if (!readRegisters(0x1B, &status, 1)) {
    noteReadError();
    return;
  }

  // Read only after BOTH sensors indicate new data, avoiding stale zero samples.
  if ((status & 0xC0) == 0xC0) {
    uint8_t data[15];  // One burst: gyro XYZ, accel XYZ, then 24-bit sensor clock.
    const int64_t readStartUs = esp_timer_get_time();
    if (!readRegisters(0x0C, data, sizeof(data))) {
      noteReadError();
      return;
    }
    consecutiveErrors = 0;
    lastDataUs = esp_timer_get_time();
    const int16_t gx = decodeInt16(data), gy = decodeInt16(data + 2), gz = decodeInt16(data + 4);
    const int16_t ax = decodeInt16(data + 6), ay = decodeInt16(data + 8), az = decodeInt16(data + 10);
    const uint32_t sensorTicks = data[12] | (static_cast<uint32_t>(data[13]) << 8) |
                                (static_cast<uint32_t>(data[14]) << 16);
    // t_read_us is S3 time just BEFORE reading, not an exact sensor sample time.
    Serial.printf("%lu,%lld,%lu,%d,%d,%d,%d,%d,%d,%.5f,%.5f,%.5f,%.4f,%.4f,%.4f\n",
                  static_cast<unsigned long>(++sampleCount), static_cast<long long>(readStartUs),
                  static_cast<unsigned long>(sensorTicks), ax, ay, az, gx, gy, gz,
                  ax / ACCEL_LSB_PER_G, ay / ACCEL_LSB_PER_G, az / ACCEL_LSB_PER_G,
                  gx / GYRO_LSB_PER_DPS, gy / GYRO_LSB_PER_DPS, gz / GYRO_LSB_PER_DPS);
    ++windowSamples;
  }

  const int64_t nowUs = esp_timer_get_time();
  if (nowUs - lastDataUs > 1000000) {
    stopAcquisition("NO_FRESH_SIX_AXIS_DATA_FOR_1S");
    return;
  }
  if (nowUs - windowStartUs >= 5000000) {
    Serial.printf("# STATS samples=%lu window_hz=%.3f read_errors=%lu\n",
                  static_cast<unsigned long>(sampleCount),
                  windowSamples * 1000000.0 / (nowUs - windowStartUs),
                  static_cast<unsigned long>(readErrors));
    if (!printAndCheckConfig()) {
      stopAcquisition("RUNTIME_CONFIGURATION_CHECK_FAILED");
      return;
    }
    windowStartUs = nowUs;
    windowSamples = 0;
  }
  delay(1);
}
