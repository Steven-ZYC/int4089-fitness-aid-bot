/*
 * LED + 蜂鸣器 联动测试
 * ---------------------------------------------
 * 接线：
 *   D8  -- 220Ω -- LED 长脚(正极)，LED 短脚 -- GND
 *   D9  -- 蜂鸣器 +，蜂鸣器 - -- GND
 */

const int PIN_LED  = 8;   // LED
const int PIN_BUZZ = 9;   // 蜂鸣器

/*  0 = 无源蜂鸣器（必须用 tone() 给频率）
 *  1 = 有源蜂鸣器（给高电平自己就响）
 *  分不清先用 0；烧进去没声音就改成 1 再烧一次。
 */
#define BUZZER_ACTIVE 0

void setup() {
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZ, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  // 开机自检：亮灯 + 短响一声
  digitalWrite(PIN_LED, HIGH);
  beep(1000, 150);
  digitalWrite(PIN_LED, LOW);
  delay(600);
}

void loop() {
  // ① 亮灯 + 响一声
  digitalWrite(PIN_LED, HIGH);
  beep(1000, 200);
  digitalWrite(PIN_LED, LOW);
  delay(200);

  // ② 连响三下（像倒车雷达）
  for (int i = 0; i < 3; i++) {
    digitalWrite(PIN_LED, HIGH);
    beep(1600, 70);
    digitalWrite(PIN_LED, LOW);
    delay(80);
  }
  delay(300);

  // ③ 长鸣 + 灯常亮
  digitalWrite(PIN_LED, HIGH);
  beep(700, 500);
  digitalWrite(PIN_LED, LOW);
  delay(800);
}

/* 响一声：freq 单位 Hz，ms 单位毫秒
 * 有源蜂鸣器会忽略 freq，给高电平就响。 */
void beep(int freq, int ms) {
#if BUZZER_ACTIVE
  digitalWrite(PIN_BUZZ, HIGH);
  delay(ms);
  digitalWrite(PIN_BUZZ, LOW);
#else
  tone(PIN_BUZZ, freq);
  delay(ms);
  noTone(PIN_BUZZ);
#endif
}
