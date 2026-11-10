#include <Arduino.h>
// One-way GPIO17 -> Mega D19, common GND; no Mega TX connection.
// Test pattern only; no IMU or posture decisions.
HardwareSerial megaLink(1);
unsigned long lastSend=0;
void sendAlarm(bool on) {
  // Source=1, state=on, checksum=source XOR state.
  const char* frame=on ? "110" : "101";
  megaLink.println(frame);
  Serial.print("TX "); Serial.println(frame);
}
void setup() {
  Serial.begin(115200);
  megaLink.begin(9600,SERIAL_8N1,18,17); // GPIO18 physically disconnected.
  sendAlarm(false);
}
void loop() {
  unsigned long now=millis();
  if(now-lastSend>=200UL) {
    lastSend=now; sendAlarm(((now/3000UL)%2)==1);
  }
}
