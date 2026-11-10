#include <WiFi.h>
#include <atomic>
#include "esp_now.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_random.h"

// Communication diagnostic only. Camera/IMU acquisition is not run here.
#if CONFIG_IDF_TARGET_ESP32S3
static constexpr uint8_t kRole = 2;
static constexpr char kName[] = "S3";
static constexpr char kPeerName[] = "CAM";
#elif CONFIG_IDF_TARGET_ESP32
static constexpr uint8_t kRole = 1;
static constexpr char kName[] = "CAM";
static constexpr char kPeerName[] = "S3";
#else
#error "Use the verified ESP32-CAM or ESP32-S3 board."
#endif

static constexpr uint8_t kPeerRole = kRole == 1 ? 2 : 1;
static constexpr uint8_t kChannel = 1;
static constexpr uint32_t kMagic = 0x49343839;
static constexpr char kFirmware[] = "DualESP_Text_Check_v1";
static constexpr uint8_t kBroadcast[6] = {255,255,255,255,255,255};
enum : uint8_t { HELLO = 1, PING = 2, ACK = 3 };

struct __attribute__((packed)) Packet {
  uint32_t magic;
  uint8_t version, type, role, textLength;
  uint32_t senderBoot, targetBoot, sequence;
  char text[24];
  uint32_t crc;
};
static_assert(sizeof(Packet) == 48, "Wire layout changed");
static_assert(sizeof(Packet) <= ESP_NOW_MAX_DATA_LEN, "Use <=250 bytes");
struct RxEvent { uint8_t source[6]; Packet packet; };
struct TxEvent { uint8_t destination[6]; Packet packet; };
static QueueHandle_t rxQueue, txQueue;
static std::atomic<uint32_t> rxQueueDrops{0};
static std::atomic<int> txCallbackResult{-1};
static uint32_t txQueueDrops = 0, badCrc = 0, invalid = 0;
static uint32_t txApiErrors = 0, txRadioFails = 0;
static uint32_t rxUnique = 0, rxDuplicate = 0, ackQueued = 0;
static uint32_t bootId, peerBoot = 0, nextSequence = 0, lastRxSequence = 0;
static uint8_t peerAddress[6];
static bool paired = false, fatal = false, txBusy = false, dropNextAck = false;
static int64_t txStartUs = 0, nextHelloUs = 0, nextStateUs = 0;
static char command[48];
static unsigned commandLength = 0;
static bool commandOverflow = false;

struct Run {
  bool active = false, pending = false, queued = false;
  uint32_t id = 0, count = 0, acked = 0, failed = 0, retries = 0;
  uint32_t firstSequence = 0, lastSequence = 0, sequence = 0, attempts = 0;
  uint32_t minRtt = UINT32_MAX, maxRtt = 0;
  uint64_t sumRtt = 0;
  int64_t firstSentUs = 0, lastSentUs = 0, nextPingUs = 0;
} run;

static uint32_t crc32(const void *bytes, size_t length) {
  uint32_t crc = UINT32_MAX;
  const auto *data = static_cast<const uint8_t *>(bytes);
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (unsigned bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320U : 0);
  }
  return ~crc;
}

static void fail(const char *reason) {
  fatal = true;
  Serial.printf("FATAL role=%s reason=%s\n", kName, reason);
}

static void printState() {
  Serial.printf(
      "STATE role=%s boot=%lu paired=%u peer_boot=%lu rx_unique=%lu "
      "rx_duplicate=%lu ack_queued=%lu tx_api_errors=%lu tx_radio_fail=%lu "
      "rx_queue_drop=%lu tx_queue_drop=%lu bad_crc=%lu invalid=%lu\n",
      kName, (unsigned long)bootId, paired, (unsigned long)peerBoot,
      (unsigned long)rxUnique, (unsigned long)rxDuplicate,
      (unsigned long)ackQueued, (unsigned long)txApiErrors,
      (unsigned long)txRadioFails, (unsigned long)rxQueueDrops.load(),
      (unsigned long)txQueueDrops, (unsigned long)badCrc, (unsigned long)invalid);
}

static void printInfo() {
  uint8_t actualChannel = 0;
  wifi_second_chan_t secondary;
  if (esp_wifi_get_channel(&actualChannel, &secondary) != ESP_OK ||
      actualChannel != kChannel) { fail("CHANNEL_READBACK"); return; }
  Serial.printf(
      "INFO fw=%s role=%s chip=%s channel=%u packet_bytes=%u boot=%lu "
      "paired=%u peer_role=%s peer_boot=%lu usb_cdc=%u acquisition=OFF\n",
      kFirmware, kName, ESP.getChipModel(), actualChannel, (unsigned)sizeof(Packet),
      (unsigned long)bootId, paired, kPeerName, (unsigned long)peerBoot,
      (unsigned)ARDUINO_USB_CDC_ON_BOOT);
  printState();
}

static Packet makePacket(uint8_t type, uint32_t seq, uint32_t target,
                         const char *text) {
  Packet p = {};
  p.magic = kMagic; p.version = 1; p.type = type; p.role = kRole;
  p.senderBoot = bootId; p.targetBoot = target; p.sequence = seq;
  p.textLength = strlen(text);
  memcpy(p.text, text, p.textLength);
  p.crc = crc32(&p, offsetof(Packet, crc));
  return p;
}

static bool textIs(const Packet &p, const char *text) {
  return p.textLength == strlen(text) &&
         p.textLength <= sizeof(p.text) &&
         memcmp(p.text, text, p.textLength) == 0;
}

static bool post(const uint8_t *destination, const Packet &packet) {
  TxEvent event = {};
  memcpy(event.destination, destination, 6);
  event.packet = packet;
  if (xQueueSend(txQueue, &event, 0) == pdTRUE) return true;
  ++txQueueDrops;
  fail("TX_QUEUE_FULL");
  return false;
}

static void onReceive(const esp_now_recv_info_t *info, const uint8_t *data,
                      int length) {
  if (!info || !data || length != sizeof(Packet)) return;
  RxEvent event;
  memcpy(event.source, info->src_addr, 6);
  memcpy(&event.packet, data, sizeof(Packet));
  if (xQueueSend(rxQueue, &event, 0) != pdTRUE) ++rxQueueDrops;
}

static void onSent(const esp_now_send_info_t *, esp_now_send_status_t status) {
  txCallbackResult.store(status == ESP_NOW_SEND_SUCCESS ? 0 : 1);
}

static void finishRun() {
  Serial.printf(
      "RUN_DONE role=%s run=%lu count=%lu acked=%lu failed=%lu retries=%lu "
      "first_seq=%lu last_seq=%lu rtt_min_us=%lu rtt_mean_us=%llu rtt_max_us=%lu\n",
      kName, (unsigned long)run.id, (unsigned long)run.count,
      (unsigned long)run.acked, (unsigned long)run.failed,
      (unsigned long)run.retries, (unsigned long)run.firstSequence,
      (unsigned long)run.lastSequence,
      (unsigned long)(run.acked ? run.minRtt : 0),
      (unsigned long long)(run.acked ? run.sumRtt / run.acked : 0),
      (unsigned long)run.maxRtt);
  run.active = false;
  printState();
}

static void consume(const RxEvent &event) {
  const Packet &p = event.packet;
  if (p.magic != kMagic || p.version != 1 || p.role != kPeerRole) return;
  if (p.crc != crc32(&p, offsetof(Packet, crc))) { ++badCrc; return; }
  if (!p.senderBoot || p.textLength > sizeof(p.text)) { ++invalid; return; }
  if (p.type == HELLO && p.targetBoot == 0 && p.sequence == 0 &&
      textIs(p, "INT4089_PAIR")) {
    if (paired && memcmp(event.source, peerAddress, 6) != 0) return;
    if (!paired) {
      esp_now_peer_info_t peer = {};
      memcpy(peer.peer_addr, event.source, 6);
      peer.channel = kChannel; peer.ifidx = WIFI_IF_STA; peer.encrypt = false;
      if (esp_now_add_peer(&peer) != ESP_OK) { fail("ADD_PEER"); return; }
      memcpy(peerAddress, event.source, 6);
    }
    if (!paired || peerBoot != p.senderBoot) {
      if (run.active) { fail("PEER_RESTART_DURING_RUN"); return; }
      peerBoot = p.senderBoot; lastRxSequence = 0; paired = true;
      Serial.printf("PAIRED role=%s peer_role=%s peer_boot=%lu\n",
                    kName, kPeerName, (unsigned long)peerBoot);
    }
    return;
  }
  if (!paired || memcmp(event.source, peerAddress, 6) != 0 ||
      p.senderBoot != peerBoot || p.targetBoot != bootId) return;

  if (p.type == PING && p.sequence &&
      textIs(p, kPeerRole == 1 ? "HELLO_FROM_CAM" : "HELLO_FROM_S3")) {
    bool duplicate = p.sequence <= lastRxSequence;
    if (duplicate) ++rxDuplicate;
    else { lastRxSequence = p.sequence; ++rxUnique; }
    Serial.printf(
        "APP_RX role=%s from=%s from_boot=%lu target_boot=%lu seq=%lu "
        "duplicate=%u text=%.*s\n", kName, kPeerName,
        (unsigned long)p.senderBoot, (unsigned long)bootId,
        (unsigned long)p.sequence, duplicate, p.textLength, p.text);
    if (dropNextAck) {
      dropNextAck = false;
      Serial.printf("FAULT_DROP_ACK role=%s seq=%lu\n",
                    kName, (unsigned long)p.sequence);
      return;
    }
    if (post(peerAddress, makePacket(ACK, p.sequence, peerBoot,
             kRole == 1 ? "RECEIVED_BY_CAM" : "RECEIVED_BY_S3"))) ++ackQueued;
  } else if (p.type == ACK && run.active && run.pending &&
             run.firstSentUs && p.sequence == run.sequence &&
             textIs(p, kPeerRole == 1 ? "RECEIVED_BY_CAM" : "RECEIVED_BY_S3")) {
    uint32_t rtt = esp_timer_get_time() - run.firstSentUs;
    Serial.printf(
        "APP_ACK role=%s from=%s from_boot=%lu target_boot=%lu run=%lu "
        "seq=%lu attempts=%lu rtt_us=%lu text=%.*s\n", kName, kPeerName,
        (unsigned long)p.senderBoot, (unsigned long)bootId,
        (unsigned long)run.id, (unsigned long)p.sequence,
        (unsigned long)run.attempts, (unsigned long)rtt, p.textLength, p.text);
    ++run.acked; run.sumRtt += rtt;
    if (rtt < run.minRtt) run.minRtt = rtt;
    if (rtt > run.maxRtt) run.maxRtt = rtt;
    run.pending = false;
    run.nextPingUs = esp_timer_get_time() + 200000;
    if (run.acked + run.failed == run.count) finishRun();
  }
}

static void dispatch() {
  if (txBusy) {
    int result = txCallbackResult.exchange(-1);
    if (result >= 0) { txBusy = false; if (result) ++txRadioFails; }
    else if (esp_timer_get_time() - txStartUs > 2000000) fail("TX_CALLBACK_TIMEOUT");
    if (txBusy || fatal) return;
  }
  TxEvent event;
  if (xQueueReceive(txQueue, &event, 0) != pdTRUE) return;
  txCallbackResult.store(-1); txBusy = true;
  txStartUs = esp_timer_get_time();
  if (event.packet.type == PING && run.pending &&
      event.packet.sequence == run.sequence) {
    run.queued = false;
    if (run.attempts++) ++run.retries;
    if (!run.firstSentUs) run.firstSentUs = txStartUs;
    run.lastSentUs = txStartUs;
  }
  if (esp_now_send(event.destination,
          reinterpret_cast<const uint8_t *>(&event.packet), sizeof(Packet)) != ESP_OK) {
    txBusy = false; ++txApiErrors;
  }
}

static void queuePing() {
  run.queued = post(peerAddress, makePacket(PING, run.sequence, peerBoot,
                     kRole == 1 ? "HELLO_FROM_CAM" : "HELLO_FROM_S3"));
}

static void advanceRun() {
  if (!run.active) return;
  int64_t now = esp_timer_get_time();
  if (!run.pending && now >= run.nextPingUs) {
    run.sequence = ++nextSequence; run.pending = true;
    run.attempts = 0; run.firstSentUs = 0; run.lastSentUs = 0;
    queuePing();
  } else if (run.pending && !run.queued && run.lastSentUs &&
             now - run.lastSentUs >= 1000000) {
    if (run.attempts < 3) queuePing();
    else {
      ++run.failed; run.pending = false; run.nextPingUs = now + 200000;
      Serial.printf("APP_TIMEOUT role=%s run=%lu seq=%lu attempts=%lu\n",
          kName, (unsigned long)run.id, (unsigned long)run.sequence,
          (unsigned long)run.attempts);
      if (run.acked + run.failed == run.count) finishRun();
    }
  }
}

static void handleCommand() {
  command[commandLength] = 0;
  unsigned count = 0;
  char trailing;
  if (commandOverflow) Serial.println("ERR_COMMAND_LENGTH");
  else if (strcmp(command, "INFO") == 0) printInfo();
  else if (strcmp(command, "DROP_NEXT_ACK") == 0) {
    dropNextAck = true;
    Serial.printf("FAULT_ARMED role=%s drop_next_ack=1\n", kName);
  } else if (sscanf(command, "RUN %u %c", &count, &trailing) == 1 && count && count <= 100) {
    if (!paired || run.active) Serial.println("ERR_RUN_NOT_READY");
    else {
      uint32_t id = run.id + 1;
      run = Run{}; run.id = id; run.count = count; run.active = true;
      run.firstSequence = nextSequence + 1; run.lastSequence = nextSequence + count;
      Serial.printf("RUN_START role=%s run=%lu count=%u first_seq=%lu last_seq=%lu\n",
          kName, (unsigned long)id, count, (unsigned long)run.firstSequence,
          (unsigned long)run.lastSequence);
    }
  } else Serial.println("ERR_COMMAND");
  commandLength = 0; commandOverflow = false;
}

void setup() {
  Serial.begin(115200);
  unsigned long serialWait = millis();
  while (!Serial && millis() - serialWait < 2000) delay(10);
  rxQueue = xQueueCreate(16, sizeof(RxEvent));
  txQueue = xQueueCreate(16, sizeof(TxEvent));
  if (!rxQueue || !txQueue) { fail("QUEUE_ALLOC"); return; }
  bootId = esp_random(); if (!bootId) bootId = 1;
  WiFi.persistent(false);
  if (!WiFi.mode(WIFI_STA)) { fail("WIFI_MODE"); return; }
  WiFi.disconnect(false, false);
  delay(100);
  if (!WiFi.setSleep(false) ||
      esp_wifi_set_channel(kChannel, WIFI_SECOND_CHAN_NONE) != ESP_OK ||
      esp_now_init() != ESP_OK ||
      esp_now_register_recv_cb(onReceive) != ESP_OK ||
      esp_now_register_send_cb(onSent) != ESP_OK) { fail("RADIO_INIT"); return; }
  esp_now_peer_info_t broadcast = {};
  memcpy(broadcast.peer_addr, kBroadcast, 6);
  broadcast.channel = kChannel; broadcast.ifidx = WIFI_IF_STA;
  if (esp_now_add_peer(&broadcast) != ESP_OK) { fail("BROADCAST_PEER"); return; }
  printInfo();
  Serial.printf("READY role=%s\n", kName);
}

void loop() {
  if (fatal) { delay(100); return; }
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') handleCommand();
    else if (commandLength < sizeof(command) - 1) command[commandLength++] = c;
    else commandOverflow = true;
  }
  RxEvent event;
  while (!fatal && xQueueReceive(rxQueue, &event, 0) == pdTRUE) consume(event);
  if (fatal) return;
  int64_t now = esp_timer_get_time();
  if (now >= nextHelloUs) {
    post(kBroadcast, makePacket(HELLO, 0, 0, "INT4089_PAIR"));
    nextHelloUs = now + 1000000;
  }
  advanceRun(); dispatch();
  if (now >= nextStateUs) { printState(); nextStateUs = now + 5000000; }
  delay(1);
}
