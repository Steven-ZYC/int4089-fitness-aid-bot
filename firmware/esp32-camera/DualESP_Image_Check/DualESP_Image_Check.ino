#include <WiFi.h>
#include <atomic>
#include "esp_now.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "mbedtls/sha256.h"
#if CONFIG_IDF_TARGET_ESP32
#include "esp_camera.h"
#define IMAGE_CAMERA_NODE 1
static constexpr uint8_t kRole = 1;
static constexpr char kName[] = "CAM";
#elif CONFIG_IDF_TARGET_ESP32S3
#define IMAGE_CAMERA_NODE 0
static constexpr uint8_t kRole = 2;
static constexpr char kName[] = "S3";
#else
#error "Use the verified ESP32-CAM or ESP32-S3."
#endif
#if ARDUINO_USB_CDC_ON_BOOT
#error "This test uses the verified CH340 COM ports, CDC On Boot Disabled."
#endif

static constexpr char kFirmware[] = "DualESP_Image_Check_v1";
static constexpr uint32_t kMagic = 0x4934494D;
static constexpr uint8_t kChannel = 1, kPeerRole = kRole == 1 ? 2 : 1;
static constexpr size_t kPayload = 200, kMaxImage = 262144;
static constexpr uint8_t kBroadcast[6] = {255,255,255,255,255,255};
enum : uint8_t { HELLO=1, CAPTURE=2, META=3, CHUNK=4, ACK=5, END=6, ERROR_MSG=7, CONTROL=8 };
enum : uint8_t { IDLE=0, WAIT_META=1, RECEIVING=2, IMAGE_READY_STATE=3, FAILED=4 };

struct __attribute__((packed)) Packet {
  uint32_t magic;
  uint8_t version, type, role, payloadLength;
  uint32_t senderBoot, targetBoot, request, frame;
  uint16_t index, reserved;
  uint32_t totalBytes, imageCrc;
  uint8_t data[kPayload];
  uint32_t packetCrc;
};
struct __attribute__((packed)) FrameMeta {
  uint64_t requestUs, frameUs, acquiredUs;
  uint16_t width, height, sensorPid;
  uint8_t discarded, reserved;
  uint8_t sha256[32];
};
static_assert(sizeof(Packet) == 240 && sizeof(Packet) <= ESP_NOW_MAX_DATA_LEN, "Packet layout");
static_assert(sizeof(FrameMeta) == 64, "Metadata layout");
struct RxEvent { uint8_t source[6]; Packet packet; };
struct TxEvent { uint8_t destination[6]; Packet packet; };
static QueueHandle_t rxQueue, txQueue;
static std::atomic<int> txResult{-1};
static std::atomic<uint32_t> queueDrops{0};
static uint32_t txQueueDrops=0, txErrors=0, radioFails=0, badPackets=0;
static bool fatal=false, paired=false, txBusy=false, sourceBusy=false;
static uint32_t bootId=0, peerBoot=0, nextRequest=0, nextFrame=0, lastSourceRequest=0;
static uint8_t peerAddress[6];
static int64_t txStarted=0, nextHello=0, nextState=0;
static Packet pendingCapture = {}, expectedAck = {}, sourceRequest = {}, controlPacket = {};
static bool haveCapture=false, waitingAck=false, gotAck=false, controlPending=false;
static uint32_t sourceRetries=0, sourceCorruptions=0, sourceCurrentRequest=0;
static uint32_t controlAttempts=0, lastControlRequest=0;
static int64_t sourceDeadline=0, controlStarted=0, controlLastSent=0;
static bool corruptArmed=false, dropAckArmed=false;
static uint16_t corruptIndex=0, dropAckIndex=0;

static struct {
  uint8_t state=IDLE;
  uint32_t request=0, frame=0, length=0, crc=0, received=0;
  uint16_t expected=0, chunks=0;
  uint32_t duplicates=0, crcRejects=0, droppedAcks=0, requestAttempts=0;
  int64_t started=0, lastReceived=0, ready=0, lastRequestSent=0;
  FrameMeta meta={};
  uint8_t *bytes=nullptr;
} image;
static bool dumping=false;
static uint32_t dumpOffset=0;
static int64_t dumpStarted=0;
static char command[64];
static unsigned commandLength=0;
static bool commandOverflow=false;

static uint32_t crc32(const void *buffer, size_t length) {
  auto *data=static_cast<const uint8_t *>(buffer);
  uint32_t crc=UINT32_MAX;
  for (size_t i=0;i<length;++i) {
    crc^=data[i];
    for (unsigned b=0;b<8;++b) crc=(crc>>1)^((crc&1)?0xEDB88320U:0);
  }
  return ~crc;
}
static void hexHash(const uint8_t *hash, char *text) {
  static constexpr char digits[]="0123456789ABCDEF";
  for (unsigned i=0;i<32;++i) { text[2*i]=digits[hash[i]>>4]; text[2*i+1]=digits[hash[i]&15]; }
  text[64]=0;
}
static void fail(const char *reason) {
  fatal=true;
  Serial.printf("FATAL role=%s reason=%s\n",kName,reason);
}
static void printState() {
  if (dumping) return;
  Serial.printf("STATE role=%s boot=%lu paired=%u peer_boot=%lu image_state=%u "
      "queue_drop=%lu tx_queue_drop=%lu tx_errors=%lu radio_fail=%lu bad_packets=%lu\n",
      kName,(unsigned long)bootId,paired,(unsigned long)peerBoot,image.state,
      (unsigned long)queueDrops.load(),(unsigned long)txQueueDrops,
      (unsigned long)txErrors,(unsigned long)radioFails,(unsigned long)badPackets);
}
static void printInfo() {
  uint8_t channel=0; wifi_second_chan_t secondary;
  if (esp_wifi_get_channel(&channel,&secondary)!=ESP_OK || channel!=kChannel) { fail("CHANNEL"); return; }
  Serial.printf("INFO fw=%s role=%s chip=%s boot=%lu peer_boot=%lu paired=%u "
      "channel=%u packet_bytes=%u payload_bytes=%u max_image=%u psram_bytes=%u imu=OFF\n",
      kFirmware,kName,ESP.getChipModel(),(unsigned long)bootId,(unsigned long)peerBoot,
      paired,channel,(unsigned)sizeof(Packet),(unsigned)kPayload,(unsigned)kMaxImage,ESP.getPsramSize());
  printState();
}
static Packet makePacket(uint8_t type,uint32_t request,uint32_t frame,uint16_t index,
                         uint32_t length,uint32_t crc,const void *data=nullptr,uint8_t count=0) {
  Packet p={}; p.magic=kMagic; p.version=1; p.type=type; p.role=kRole;
  p.senderBoot=bootId; p.targetBoot=type==HELLO?0:peerBoot;
  p.request=request; p.frame=frame; p.index=index; p.totalBytes=length; p.imageCrc=crc;
  p.payloadLength=count;
  if (count) memcpy(p.data,data,count);
  p.packetCrc=crc32(&p,offsetof(Packet,packetCrc));
  return p;
}
static bool post(const Packet &packet,bool broadcast=false) {
  TxEvent event={}; memcpy(event.destination,broadcast?kBroadcast:peerAddress,6); event.packet=packet;
  if (xQueueSend(txQueue,&event,0)==pdTRUE) return true;
  ++txQueueDrops; fail("TX_QUEUE"); return false;
}
static void postAck(const Packet &p) {
  uint8_t type=p.type;
  post(makePacket(ACK,p.request,p.frame,p.index,p.totalBytes,p.imageCrc,&type,1));
}
static bool sameTransfer(const Packet &a,const Packet &b) {
  return a.request==b.request && a.frame==b.frame && a.index==b.index &&
         a.totalBytes==b.totalBytes && a.imageCrc==b.imageCrc;
}
static void sendError(uint32_t request,uint32_t frame,const char *reason) {
  if (paired) post(makePacket(ERROR_MSG,request,frame,0,0,0,reason,strlen(reason)));
  if (!dumping) Serial.printf("FRAME_ERROR role=%s req=%lu frame=%lu reason=%s\n",
      kName,(unsigned long)request,(unsigned long)frame,reason);
}
static void rejectImage(const char *reason) {
  image.state=FAILED;
  sendError(image.request,image.frame,reason);
}
static void onReceive(const esp_now_recv_info_t *info,const uint8_t *data,int length) {
  if (!info || !data || length!=sizeof(Packet)) return;
  RxEvent event; memcpy(event.source,info->src_addr,6); memcpy(&event.packet,data,sizeof(Packet));
  if (xQueueSend(rxQueue,&event,0)!=pdTRUE) ++queueDrops;
}
static void onSent(const esp_now_send_info_t *,esp_now_send_status_t status) {
  txResult.store(status==ESP_NOW_SEND_SUCCESS?0:1);
}
static void dispatch() {
  if (txBusy) {
    int result=txResult.exchange(-1);
    if (result>=0) { txBusy=false; if (result) ++radioFails; }
    else if (esp_timer_get_time()-txStarted>2000000) fail("TX_CALLBACK_TIMEOUT");
    if (txBusy || fatal) return;
  }
  TxEvent event;
  if (xQueueReceive(txQueue,&event,0)!=pdTRUE) return;
  txBusy=true; txResult.store(-1); txStarted=esp_timer_get_time();
  if (esp_now_send(event.destination,reinterpret_cast<const uint8_t *>(&event.packet),sizeof(Packet))!=ESP_OK) {
    txBusy=false; ++txErrors;
  }
}

static void receiveImage(const Packet &p) {
  if (p.request!=image.request) return;
  if (p.type==META) {
    if (p.payloadLength!=sizeof(FrameMeta) || !p.frame || p.totalBytes<4 || p.totalBytes>kMaxImage) {
      rejectImage("META_SIZE"); return;
    }
    FrameMeta metadata; memcpy(&metadata,p.data,sizeof(metadata));
    if (metadata.width!=640 || metadata.height!=480 || metadata.sensorPid!=0x26 ||
        metadata.frameUs<metadata.requestUs || metadata.acquiredUs<metadata.frameUs) {
      rejectImage("META_FIELDS"); return;
    }
    if (image.state==WAIT_META) {
      image.frame=p.frame; image.length=p.totalBytes; image.crc=p.imageCrc; image.meta=metadata;
      image.chunks=(p.totalBytes+kPayload-1)/kPayload; image.expected=0; image.received=0;
      image.state=RECEIVING; image.lastReceived=esp_timer_get_time();
      Serial.printf("META_ACCEPT req=%lu frame=%lu bytes=%lu chunks=%u\n",
          (unsigned long)p.request,(unsigned long)p.frame,(unsigned long)p.totalBytes,image.chunks);
    } else if ((image.state!=RECEIVING && image.state!=IMAGE_READY_STATE) ||
        p.frame!=image.frame || p.totalBytes!=image.length || p.imageCrc!=image.crc ||
        memcmp(&metadata,&image.meta,sizeof(metadata))!=0) return;
    postAck(p); return;
  }
  if (p.frame!=image.frame || p.totalBytes!=image.length || p.imageCrc!=image.crc) return;
  if (p.type==CHUNK && image.state==RECEIVING) {
    size_t offset=static_cast<size_t>(p.index)*kPayload;
    if (p.index>=image.chunks || offset>=image.length ||
        p.payloadLength!=min(kPayload,static_cast<size_t>(image.length-offset))) {
      rejectImage("CHUNK_SIZE"); return;
    }
    if (p.index==image.expected) {
      memcpy(image.bytes+offset,p.data,p.payloadLength);
      ++image.expected; image.received+=p.payloadLength;
    } else if (p.index<image.expected) {
      if (memcmp(image.bytes+offset,p.data,p.payloadLength)!=0) { rejectImage("CHUNK_CONFLICT"); return; }
      ++image.duplicates;
    } else { rejectImage("CHUNK_ORDER"); return; }
    image.lastReceived=esp_timer_get_time();
    if (dropAckArmed && p.index==dropAckIndex) {
      dropAckArmed=false; ++image.droppedAcks;
      Serial.printf("FAULT_DROP_ACK req=%lu frame=%lu idx=%u\n",
                    (unsigned long)p.request,(unsigned long)p.frame,p.index);
      return;
    }
    postAck(p); return;
  }
  if (p.type==END && (image.state==RECEIVING || image.state==IMAGE_READY_STATE)) {
    if (p.index!=image.chunks || p.payloadLength!=0) { rejectImage("END_FIELDS"); return; }
    if (image.state==RECEIVING) {
      if (image.expected!=image.chunks || image.received!=image.length ||
          crc32(image.bytes,image.length)!=image.crc || image.bytes[0]!=255 || image.bytes[1]!=216 ||
          image.bytes[image.length-2]!=255 || image.bytes[image.length-1]!=217) {
        rejectImage("IMAGE_CRC_OR_LENGTH"); return;
      }
      uint8_t digest[32];
      if (mbedtls_sha256(image.bytes,image.length,digest,0)!=0 ||
          memcmp(digest,image.meta.sha256,32)!=0) { rejectImage("IMAGE_SHA256"); return; }
      image.ready=esp_timer_get_time(); image.state=IMAGE_READY_STATE;
      char sha[65]; hexHash(digest,sha);
      Serial.printf("IMAGE_READY req=%lu frame=%lu bytes=%lu chunks=%u crc32=%08lX sha256=%s "
          "gateway_elapsed_us=%lld duplicate_chunks=%lu crc_rejects=%lu dropped_ack=%lu\n",
          (unsigned long)image.request,(unsigned long)image.frame,(unsigned long)image.length,image.chunks,
          (unsigned long)image.crc,sha,image.ready-image.started,(unsigned long)image.duplicates,
          (unsigned long)image.crcRejects,(unsigned long)image.droppedAcks);
    }
    postAck(p);
  }
}

static void consume(const RxEvent &event) {
  const Packet &p=event.packet;
  if (p.magic!=kMagic || p.version!=1 || p.role!=kPeerRole) return;
  if (p.packetCrc!=crc32(&p,offsetof(Packet,packetCrc))) {
    if (paired && memcmp(event.source,peerAddress,6)==0) {
      ++badPackets;
      if (kRole==2 && image.state==RECEIVING && p.request==image.request) ++image.crcRejects;
      if (!dumping) Serial.printf("PACKET_REJECT role=%s req=%lu frame=%lu idx=%u reason=CRC32\n",
          kName,(unsigned long)p.request,(unsigned long)p.frame,p.index);
    }
    return;
  }
  if (p.payloadLength>kPayload || !p.senderBoot) return;
  if (p.type==HELLO && p.targetBoot==0 && p.payloadLength==13 &&
      memcmp(p.data,"INT4089_IMAGE",13)==0) {
    if (paired && memcmp(event.source,peerAddress,6)!=0) return;
    if (!paired) {
      esp_now_peer_info_t peer={}; memcpy(peer.peer_addr,event.source,6);
      peer.channel=kChannel; peer.ifidx=WIFI_IF_STA;
      if (esp_now_add_peer(&peer)!=ESP_OK) { fail("ADD_PEER"); return; }
      memcpy(peerAddress,event.source,6);
    }
    if (!paired || peerBoot!=p.senderBoot) {
      if (sourceBusy || image.state==WAIT_META || image.state==RECEIVING || dumping || controlPending) {
        fail("PEER_RESTART_ACTIVE"); return;
      }
      peerBoot=p.senderBoot; paired=true; lastSourceRequest=0; lastControlRequest=0;
      if (!dumping) Serial.printf("PAIRED role=%s peer_boot=%lu\n",kName,(unsigned long)peerBoot);
    }
    return;
  }
  if (!paired || memcmp(event.source,peerAddress,6)!=0 || p.senderBoot!=peerBoot || p.targetBoot!=bootId) return;
  if (p.type==ERROR_MSG) {
    if (!dumping) Serial.printf("FRAME_ERROR role=%s req=%lu frame=%lu reason=PEER_%.*s\n",
        kName,(unsigned long)p.request,(unsigned long)p.frame,p.payloadLength,p.data);
    if (kRole==2 && p.request==image.request) image.state=FAILED;
    return;
  }
  if (p.type==ACK && p.payloadLength==1) {
    if (waitingAck && p.data[0]==expectedAck.type && sameTransfer(p,expectedAck)) gotAck=true;
    if (kRole==2 && controlPending && p.data[0]==CONTROL && sameTransfer(p,controlPacket)) {
      controlPending=false;
      Serial.printf("CONTROL_OK req=%lu nonce=%lu attempts=%lu rtt_us=%lld test_only=YES\n",
          (unsigned long)p.request,(unsigned long)p.frame,(unsigned long)controlAttempts,
          esp_timer_get_time()-controlStarted);
    }
    return;
  }
  if (kRole==1 && p.type==CAPTURE && p.request>lastSourceRequest) {
    if (!sourceBusy && !haveCapture) { sourceRequest=p; haveCapture=true; }
    return;
  }
  if (kRole==1 && p.type==CONTROL && p.payloadLength==9 && memcmp(p.data,"TEST_ONLY",9)==0) {
    if (sourceBusy) { sendError(p.request,p.frame,"BUSY"); return; }
    bool duplicate=p.request<=lastControlRequest;
    if (!duplicate) lastControlRequest=p.request;
    Serial.printf("CONTROL_RX req=%lu nonce=%lu duplicate=%u text=TEST_ONLY\n",
                  (unsigned long)p.request,(unsigned long)p.frame,duplicate);
    postAck(p); return;
  }
  if (kRole==2) receiveImage(p);
}

static void service() {
  RxEvent event;
  while (!fatal && xQueueReceive(rxQueue,&event,0)==pdTRUE) consume(event);
  if (fatal) return;
  int64_t now=esp_timer_get_time();
  if (now>=nextHello && !sourceBusy && !dumping && image.state!=WAIT_META && image.state!=RECEIVING) {
    post(makePacket(HELLO,0,0,0,0,0,"INT4089_IMAGE",13),true); nextHello=now+1000000;
  }
  if (kRole==2 && image.state==WAIT_META && now-image.lastRequestSent>=500000) {
    if (image.requestAttempts>=3) rejectImage("META_TIMEOUT");
    else { post(pendingCapture); ++image.requestAttempts; image.lastRequestSent=now; }
  }
  if (kRole==2 && image.state==RECEIVING &&
      (now-image.lastReceived>3000000 || now-image.started>30000000)) rejectImage("TRANSFER_TIMEOUT");
  if (controlPending && now-controlLastSent>=200000) {
    if (controlAttempts>=3) { controlPending=false; sendError(controlPacket.request,controlPacket.frame,"CONTROL_TIMEOUT"); }
    else { post(controlPacket); ++controlAttempts; controlLastSent=now; }
  }
  dispatch();
  if (now>=nextState) { printState(); nextState=now+5000000; }
}

static bool sendReliable(const Packet &packet) {
  expectedAck=packet; waitingAck=true; gotAck=false;
  for (unsigned attempt=0;attempt<3 && !fatal;++attempt) {
    if (attempt) {
      ++sourceRetries;
      Serial.printf("TX_RETRY req=%lu frame=%lu kind=%u idx=%u attempt=%u\n",
          (unsigned long)packet.request,(unsigned long)packet.frame,packet.type,packet.index,attempt+1);
    }
    Packet wire=packet;
    if (packet.type==CHUNK && corruptArmed && packet.index==corruptIndex) {
      wire.data[0]^=1; corruptArmed=false; ++sourceCorruptions;
      Serial.printf("FAULT_CORRUPT req=%lu frame=%lu idx=%u\n",
                    (unsigned long)packet.request,(unsigned long)packet.frame,packet.index);
    }
    if (!post(wire)) break;
    int64_t deadline=esp_timer_get_time()+200000;
    while (!fatal && !gotAck && esp_timer_get_time()<deadline && esp_timer_get_time()<sourceDeadline) {
      service(); delay(1);
    }
    if (gotAck) { waitingAck=false; return true; }
    if (esp_timer_get_time()>=sourceDeadline) break;
  }
  waitingAck=false; return false;
}

#if IMAGE_CAMERA_NODE
static bool initCamera() {
  camera_config_t c={}; c.ledc_channel=LEDC_CHANNEL_0; c.ledc_timer=LEDC_TIMER_0;
  c.pin_d0=5; c.pin_d1=18; c.pin_d2=19; c.pin_d3=21; c.pin_d4=36; c.pin_d5=39; c.pin_d6=34; c.pin_d7=35;
  c.pin_xclk=0; c.pin_pclk=22; c.pin_vsync=25; c.pin_href=23; c.pin_sccb_sda=26; c.pin_sccb_scl=27;
  c.pin_pwdn=32; c.pin_reset=-1; c.xclk_freq_hz=20000000; c.pixel_format=PIXFORMAT_JPEG;
  c.frame_size=FRAMESIZE_VGA; c.jpeg_quality=12; c.fb_count=1;
  c.fb_location=CAMERA_FB_IN_PSRAM; c.grab_mode=CAMERA_GRAB_WHEN_EMPTY;
  if (esp_camera_init(&c)!=ESP_OK) return false;
  sensor_t *s=esp_camera_sensor_get();
  if (!s || s->id.PID!=OV2640_PID) return false;
  for (unsigned i=0;i<3;++i) {
    camera_fb_t *f=esp_camera_fb_get(); if (!f) return false;
    esp_camera_fb_return(f); delay(20);
  }
  Serial.printf("CAMERA_OK sensor_pid=0x%04X sensor_ver=0x%02X\n",s->id.PID,s->id.VER);
  return true;
}
static void takeAndSend() {
  haveCapture=false; sourceBusy=true; lastSourceRequest=sourceRequest.request;
  sourceCurrentRequest=sourceRequest.request; sourceRetries=0; sourceCorruptions=0;
  FrameMeta meta={}; meta.requestUs=esp_timer_get_time();
  camera_fb_t *fb=nullptr;
  for (unsigned attempt=0;attempt<4;++attempt) {
    fb=esp_camera_fb_get();
    if (!fb) break;
    meta.frameUs=static_cast<uint64_t>(fb->timestamp.tv_sec)*1000000ULL+fb->timestamp.tv_usec;
    if (meta.frameUs>=meta.requestUs && meta.frameUs<=(uint64_t)esp_timer_get_time()) break;
    esp_camera_fb_return(fb); fb=nullptr; ++meta.discarded; delay(1);
  }
  meta.acquiredUs=esp_timer_get_time();
  if (!fb || !fb->buf || fb->format!=PIXFORMAT_JPEG || fb->width!=640 || fb->height!=480 ||
      fb->len<4 || fb->len>kMaxImage || fb->buf[0]!=255 || fb->buf[1]!=216 ||
      fb->buf[fb->len-2]!=255 || fb->buf[fb->len-1]!=217) {
    if (fb) esp_camera_fb_return(fb);
    sendError(sourceCurrentRequest,0,"CAPTURE"); sourceBusy=false; return;
  }
  meta.width=fb->width; meta.height=fb->height; meta.sensorPid=esp_camera_sensor_get()->id.PID;
  if (mbedtls_sha256(fb->buf,fb->len,meta.sha256,0)!=0) {
    esp_camera_fb_return(fb); sendError(sourceCurrentRequest,0,"CAM_SHA"); sourceBusy=false; return;
  }
  uint32_t length=fb->len, imageCrc=crc32(fb->buf,fb->len), frame=++nextFrame;
  uint16_t chunks=(length+kPayload-1)/kPayload;
  char sha[65]; hexHash(meta.sha256,sha);
  Serial.printf("CAM_SOURCE req=%lu frame=%lu bytes=%lu chunks=%u crc32=%08lX sha256=%s "
      "request_us=%llu frame_us=%llu acquired_us=%llu discarded=%u\n",
      (unsigned long)sourceCurrentRequest,(unsigned long)frame,(unsigned long)length,chunks,
      (unsigned long)imageCrc,sha,(unsigned long long)meta.requestUs,(unsigned long long)meta.frameUs,
      (unsigned long long)meta.acquiredUs,meta.discarded);
  int64_t start=esp_timer_get_time(); sourceDeadline=start+25000000;
  bool ok=sendReliable(makePacket(META,sourceCurrentRequest,frame,0,length,imageCrc,&meta,sizeof(meta)));
  for (uint16_t i=0;ok && i<chunks;++i) {
    size_t offset=(size_t)i*kPayload;
    uint8_t count=min(kPayload,(size_t)length-offset);
    ok=sendReliable(makePacket(CHUNK,sourceCurrentRequest,frame,i,length,imageCrc,fb->buf+offset,count));
  }
  if (ok) ok=sendReliable(makePacket(END,sourceCurrentRequest,frame,chunks,length,imageCrc));
  esp_camera_fb_return(fb);
  if (ok) Serial.printf("CAM_COMPLETE req=%lu frame=%lu bytes=%lu chunks=%u retries=%lu "
      "corruptions=%lu radio_elapsed_us=%lld\n",(unsigned long)sourceCurrentRequest,
      (unsigned long)frame,(unsigned long)length,chunks,(unsigned long)sourceRetries,
      (unsigned long)sourceCorruptions,esp_timer_get_time()-start);
  else sendError(sourceCurrentRequest,frame,"ACK_TIMEOUT");
  sourceBusy=false;
}
#endif

static void startDump() {
  if (kRole!=2 || image.state!=IMAGE_READY_STATE || dumping) { Serial.println("ERR_DUMP_NOT_READY"); return; }
  char sha[65]; hexHash(image.meta.sha256,sha);
  dumping=true; dumpOffset=0; dumpStarted=esp_timer_get_time();
  Serial.printf("USB_META req=%lu frame=%lu bytes=%lu chunks=%u crc32=%08lX sha256=%s "
      "width=%u height=%u cam_request_us=%llu cam_frame_us=%llu cam_acquired_us=%llu discarded=%u "
      "gateway_elapsed_us=%lld duplicate_chunks=%lu crc_rejects=%lu dropped_ack=%lu\n",
      (unsigned long)image.request,(unsigned long)image.frame,(unsigned long)image.length,image.chunks,
      (unsigned long)image.crc,sha,image.meta.width,image.meta.height,
      (unsigned long long)image.meta.requestUs,(unsigned long long)image.meta.frameUs,
      (unsigned long long)image.meta.acquiredUs,image.meta.discarded,image.ready-image.started,
      (unsigned long)image.duplicates,(unsigned long)image.crcRejects,(unsigned long)image.droppedAcks);
  Serial.printf("IMG %lu\n",(unsigned long)image.length);
}
static void advanceDump() {
  if (!dumping) return;
  if (esp_timer_get_time()-dumpStarted>60000000) { dumping=false; fail("USB_TIMEOUT"); return; }
  size_t space=Serial.availableForWrite();
  if (space && dumpOffset<image.length) {
    size_t remaining=static_cast<size_t>(image.length-dumpOffset);
    size_t count=min((size_t)256,min(space,remaining));
    dumpOffset+=Serial.write(image.bytes+dumpOffset,count);
  }
  if (dumpOffset==image.length) {
    Serial.flush(); dumping=false;
    Serial.printf("\nUSB_DONE req=%lu frame=%lu bytes=%lu uart_elapsed_us=%lld\n",
        (unsigned long)image.request,(unsigned long)image.frame,(unsigned long)image.length,
        esp_timer_get_time()-dumpStarted);
  }
}
static void handleCommand() {
  command[commandLength]=0; unsigned value=0; char extra;
  if (commandOverflow) Serial.println("ERR_COMMAND_LENGTH");
  else if (strcmp(command,"INFO")==0) printInfo();
  else if (kRole==2 && strcmp(command,"CAPTURE")==0) {
    if (!paired || image.state==WAIT_META || image.state==RECEIVING || controlPending) Serial.println("ERR_BUSY");
    else {
      image.state=WAIT_META; image.request=++nextRequest; image.frame=0;
      image.received=0; image.expected=0; image.duplicates=0; image.crcRejects=0; image.droppedAcks=0;
      image.started=esp_timer_get_time(); image.lastRequestSent=image.started; image.requestAttempts=1;
      pendingCapture=makePacket(CAPTURE,image.request,0,0,0,0);
      Serial.printf("CAPTURE_START req=%lu\n",(unsigned long)image.request); post(pendingCapture);
    }
  } else if (kRole==2 && strcmp(command,"DUMP")==0) startDump();
  else if (kRole==2 && sscanf(command,"CONTROL %u %c",&value,&extra)==1 && value) {
    if (!paired || image.state==WAIT_META || image.state==RECEIVING || controlPending) Serial.println("ERR_BUSY");
    else {
      controlPacket=makePacket(CONTROL,++nextRequest,value,0,0,0,"TEST_ONLY",9);
      controlPending=true; controlAttempts=1; controlStarted=esp_timer_get_time(); controlLastSent=controlStarted;
      post(controlPacket);
    }
  } else if (kRole==2 && sscanf(command,"FAULT_DROP_ACK %u %c",&value,&extra)==1 && value<1311) {
    dropAckArmed=true; dropAckIndex=value;
    Serial.printf("FAULT_ARMED role=S3 kind=DROP_ACK idx=%u\n",value);
  } else if (kRole==1 && sscanf(command,"FAULT_CORRUPT %u %c",&value,&extra)==1 && value<1311) {
    corruptArmed=true; corruptIndex=value;
    Serial.printf("FAULT_ARMED role=CAM kind=CORRUPT idx=%u\n",value);
  } else Serial.println("ERR_COMMAND");
  commandLength=0; commandOverflow=false;
}
void setup() {
  Serial.setTxBufferSize(2048); Serial.begin(115200); delay(1000);
  if (!psramFound()) { fail("PSRAM"); return; }
  rxQueue=xQueueCreate(16,sizeof(RxEvent)); txQueue=xQueueCreate(16,sizeof(TxEvent));
  if (!rxQueue || !txQueue) { fail("QUEUE_ALLOC"); return; }
#if IMAGE_CAMERA_NODE
  if (!initCamera()) { fail("CAMERA_INIT"); return; }
#else
  image.bytes=static_cast<uint8_t *>(heap_caps_malloc(kMaxImage,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  if (!image.bytes) { fail("IMAGE_ALLOC"); return; }
#endif
  bootId=esp_random(); if (!bootId) bootId=1;
  WiFi.persistent(false); if (!WiFi.mode(WIFI_STA)) { fail("WIFI"); return; }
  WiFi.disconnect(false,false); delay(100);
  if (!WiFi.setSleep(false) || esp_wifi_set_channel(kChannel,WIFI_SECOND_CHAN_NONE)!=ESP_OK ||
      esp_now_init()!=ESP_OK || esp_now_register_recv_cb(onReceive)!=ESP_OK ||
      esp_now_register_send_cb(onSent)!=ESP_OK) { fail("RADIO_INIT"); return; }
  esp_now_peer_info_t broadcast={}; memcpy(broadcast.peer_addr,kBroadcast,6);
  broadcast.channel=kChannel; broadcast.ifidx=WIFI_IF_STA;
  if (esp_now_add_peer(&broadcast)!=ESP_OK) { fail("BROADCAST"); return; }
  printInfo(); Serial.printf("READY role=%s\n",kName);
}
void loop() {
  if (fatal) { delay(100); return; }
  if (!dumping) while (Serial.available()) {
    char c=Serial.read(); if (c=='\r') continue;
    if (c=='\n') handleCommand();
    else if (commandLength<sizeof(command)-1) command[commandLength++]=c;
    else commandOverflow=true;
    if (dumping) break;
  }
  service(); if (fatal) return;
#if IMAGE_CAMERA_NODE
  if (haveCapture) takeAndSend();
#endif
  advanceDump(); delay(1);
}
