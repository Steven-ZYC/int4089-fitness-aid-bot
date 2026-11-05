#include <Arduino.h>
#include <Wire.h>

#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "Select ESP32S3 Dev Module for this sketch."
#endif

#if ARDUINO_USB_CDC_ON_BOOT
#error "Use USB CDC On Boot: Disabled with the COM/CH340 port."
#endif

constexpr int SDA_PIN = 4;
constexpr int SCL_PIN = 5;
constexpr uint32_t I2C_HZ = 100000;
constexpr uint8_t CHIP_ID_REGISTER = 0x00;
constexpr uint8_t EXPECTED_CHIP_ID = 0xD1;
bool busReady = false;

void printIdentityReport() {
  const uint8_t addresses[] = {0x68, 0x69};
  unsigned responses = 0;
  unsigned matches = 0;

  Serial.println();
  Serial.println("=== BMI160_ID_CHECK ===");
  Serial.printf("SDA=GPIO%d SCL=GPIO%d I2C_HZ=%lu\n",
                SDA_PIN, SCL_PIN, static_cast<unsigned long>(I2C_HZ));

  for (uint8_t address : addresses) {
    Wire.beginTransmission(address);
    const uint8_t probeStatus = Wire.endTransmission(true);
    if (probeStatus != 0) {
      Serial.printf("NO_ACK address=0x%02X wire_status=%u\n", address, probeStatus);
      continue;
    }
    ++responses;

    // Select the read-only identity register; no configuration is written.
    Wire.beginTransmission(address);
    Wire.write(CHIP_ID_REGISTER);
    const uint8_t registerStatus = Wire.endTransmission(false);
    if (registerStatus != 0) {
      Serial.printf("READ_ERROR address=0x%02X wire_status=%u\n", address, registerStatus);
      continue;
    }
    if (Wire.requestFrom(address, static_cast<size_t>(1), true) != 1) {
      Serial.printf("READ_ERROR address=0x%02X missing_identity_byte\n", address);
      continue;
    }

    const uint8_t chipId = static_cast<uint8_t>(Wire.read());
    Serial.printf("ACK address=0x%02X CHIP_ID=0x%02X\n", address, chipId);
    if (chipId == EXPECTED_CHIP_ID) {
      ++matches;
    } else {
      Serial.println("CHIP_ID_MISMATCH: expected 0xD1; record the value before changing drivers.");
    }
  }

  if (matches == 1 && responses == 1) {
    Serial.println("PASS: one expected BMI160 identity found. Six-axis acquisition is not tested.");
  } else if (responses == 0) {
    Serial.println("CHECK: no reply at 0x68/0x69. Disconnect USB before inspecting wiring.");
  } else {
    Serial.println("CHECK: identity/read/response count differs from the single-BMI160 plan.");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  busReady = Wire.begin(SDA_PIN, SCL_PIN, I2C_HZ);
  if (busReady) {
    Wire.setTimeOut(100);
  }
}

void loop() {
  if (busReady) {
    printIdentityReport();
  } else {
    Serial.println("I2C_INIT_FAILED: check board and GPIO configuration.");
  }
  delay(3000);
}
