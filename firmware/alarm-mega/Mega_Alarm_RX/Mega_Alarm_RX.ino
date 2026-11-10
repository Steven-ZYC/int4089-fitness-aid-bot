#include <Arduino.h>
// Mega: USB Serial=PC, Serial1 RX=D19=ESP32. D18 MUST stay disconnected.
constexpr uint8_t LED_PIN=8, BUZZ_PIN=9;
constexpr bool ACTIVE_BUZZER=false;
constexpr unsigned long TIMEOUT_MS=1500;
struct Parser { char digits[3]; uint8_t used=0; bool bad=false; unsigned long lastByte=0; };
Parser pc, esp;
bool alarmOn=false, haveFrame=false, pcOwns=false;
unsigned long lastFrame=0, lastPc=0;
void setAlarm(bool on) {
  if(on==alarmOn) return;
  alarmOn=on; digitalWrite(LED_PIN,on ? HIGH : LOW);
  if(ACTIVE_BUZZER) digitalWrite(BUZZ_PIN,on ? HIGH : LOW);
  else if(on) tone(BUZZ_PIN,1600); else noTone(BUZZ_PIN);
}
void accept(Parser &p, uint8_t expectedSource) {
  if(p.bad || p.used!=3) { Serial.println(F("ERR FORMAT")); return; }
  uint8_t source=p.digits[0]-'0', state=p.digits[1]-'0', check=p.digits[2]-'0';
  if(source!=expectedSource) { Serial.println(F("ERR SOURCE")); return; }
  if(check!=(source ^ state)) { Serial.println(F("ERR CHECKSUM")); return; }
  unsigned long now=millis();
  if(source==1 && pcOwns && now-lastPc<=TIMEOUT_MS) return;
  pcOwns=(source==0);
  if(pcOwns) lastPc=now;
  lastFrame=now; haveFrame=true; setAlarm(state==1);
  Serial.print(F("ACK ")); Serial.write(p.digits,3); Serial.println();
}
void poll(Stream &stream, Parser &p, uint8_t source) {
  // Bound work per iteration so either interface cannot starve the watchdog.
  for(uint8_t count=0; count<32 && stream.available(); ++count) {
    unsigned long now=millis();
    if((p.used || p.bad) && now-p.lastByte>250UL) { p.used=0; p.bad=false; }
    char c=stream.read(); p.lastByte=now;
    if(c=='\n') { accept(p,source); p.used=0; p.bad=false; }
    else if(c=='\r') { /* Permit CRLF serial monitors. */ }
    else if((c=='0' || c=='1') && p.used<3 && !p.bad) p.digits[p.used++]=c;
    else p.bad=true;
  }
}
void setup() {
  pinMode(LED_PIN,OUTPUT); pinMode(BUZZ_PIN,OUTPUT);
  digitalWrite(LED_PIN,LOW); digitalWrite(BUZZ_PIN,LOW);
  Serial.begin(115200); Serial1.begin(9600);
  pinMode(19,INPUT); digitalWrite(19,LOW); // No 5V pull-up on S3 TX.
  Serial.println(F("READY protocol=3ASCII-XOR PC=0 ESP=1 outputs=OFF"));
}
void loop() {
  poll(Serial,pc,0); poll(Serial1,esp,1);
  if(haveFrame && millis()-lastFrame>TIMEOUT_MS) {
    haveFrame=false; pcOwns=false; setAlarm(false);
    Serial.println(F("TIMEOUT outputs=OFF"));
  }
}
