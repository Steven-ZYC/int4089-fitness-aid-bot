#include <Arduino.h>
#include <Wire.h>
#include <esp_timer.h>
#include "../AlarmRadio.h"
#if !CONFIG_IDF_TARGET_ESP32S3
#error "Select ESP32-S3 N16R8"
#endif
// Preserve the measured acquisition implementation as the single source of truth.
#define setup imuSetup
#define loop imuLoop
namespace imu {
#include "../../esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino"
}
#undef setup
#undef loop
bool radioReady=false;
void setup(){
  imu::imuSetup(); // Owns Serial initialization and TX buffer allocation.
  radioReady=bridge::begin();
  Serial.printf("# RADIO_INIT pass=%u\n",radioReady);
}
void loop(){
  imu::imuLoop();
  static unsigned long last=0;
  if(millis()-last>=1000){last=millis();Serial.print("# ");bridge::status();}
}
