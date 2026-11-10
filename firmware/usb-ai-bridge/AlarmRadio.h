#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <atomic>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_random.h>
namespace bridge {
#if CONFIG_IDF_TARGET_ESP32
constexpr bool isCam=true;
const uint8_t peerMac[6]={0x28,0x84,0x85,0x43,0x72,0xb0};
#else
constexpr bool isCam=false;
const uint8_t peerMac[6]={0xe8,0x6b,0xea,0xca,0xee,0x88};
#endif
constexpr uint32_t magic=0x41493438;
constexpr uint32_t leaseMs=1200;
struct __attribute__((packed)) Packet {
  uint32_t magic, boot, seq;
  uint8_t version, kind, alarm, reserved;
  uint32_t crc;
};
static_assert(sizeof(Packet)==20,"Unexpected radio layout");
QueueHandle_t queue;
std::atomic<uint32_t> commandAt{0}, commandValue{0}, commandValid{0};
std::atomic<uint32_t> received{0}, acked{0}, ackState{0}, ackAt{0};
std::atomic<uint32_t> effective{0}, sendErrors{0}, queueDrops{0};
std::atomic<uint32_t> statusSeq{0};
uint32_t crc32(const void *ptr,size_t n) {
  uint32_t crc=~0U;auto p=(const uint8_t*)ptr;
  while(n--){crc^=*p++;for(int i=0;i<8;i++)crc=(crc>>1)^((crc&1)?0xedb88320U:0);}
  return ~crc;
}
void onReceive(const esp_now_recv_info_t* info,const uint8_t* data,int n){
  if(!info || n!=sizeof(Packet) || memcmp(info->src_addr,peerMac,6))return;
  Packet p;memcpy(&p,data,n);
  if(p.magic!=magic || p.version!=1 || p.alarm>1 || p.reserved ||
     p.crc!=crc32(&p,offsetof(Packet,crc)))return;
  if(xQueueSend(queue,&p,0)!=pdTRUE)queueDrops++;
}
void send(Packet p){
  p.crc=crc32(&p,offsetof(Packet,crc));
  if(esp_now_send(peerMac,(const uint8_t*)&p,sizeof(p))!=ESP_OK)sendErrors++;
}
void command(bool on){commandValue=on;commandAt=millis();commandValid=1;}
void task(void*) {
  const uint32_t boot=esp_random();uint32_t seq=0,lastSend=0,lastRx=0;
  uint32_t peerBoot=0,peerSeq=0;bool hasRx=false,state=false;
  for(;;){
    uint32_t now=millis();Packet p;
    while(xQueueReceive(queue,&p,0)==pdTRUE){
      if(isCam){
        if(p.kind==2 && p.boot==boot && p.seq<=seq && p.seq>acked.load()){
          acked=p.seq;ackState=p.alarm;ackAt=now;
        }
      } else if(p.kind==1 && p.seq &&
               (!hasRx || p.boot!=peerBoot || (int32_t)(p.seq-peerSeq)>0)){
        peerBoot=p.boot;peerSeq=p.seq;lastRx=now;hasRx=true;state=p.alarm;
        received++;statusSeq=p.seq;
        p.kind=2;send(p);
      }
    }
    if(now-lastSend>=200){
      lastSend=now;
      if(isCam){
        bool on=commandValid.load() && now-commandAt.load()<=leaseMs && commandValue.load();
        effective=on;
        Packet out={magic,boot,++seq,1,1,(uint8_t)on,0,0};send(out);
      }else{
        bool on=hasRx && now-lastRx<=leaseMs && state;
        effective=on;
        Serial1.println(on ? "110" : "101");
      }
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
bool begin(){
  queue=xQueueCreate(12,sizeof(Packet));if(!queue)return false;
  if(!isCam)Serial1.begin(9600,SERIAL_8N1,18,17);
  WiFi.mode(WIFI_STA);WiFi.disconnect();
  if(esp_wifi_set_channel(1,WIFI_SECOND_CHAN_NONE)!=ESP_OK)return false;
  esp_wifi_set_ps(WIFI_PS_NONE);
  if(esp_now_init()!=ESP_OK)return false;
  esp_now_peer_info_t peer={};memcpy(peer.peer_addr,peerMac,6);
  peer.channel=1;peer.ifidx=WIFI_IF_STA;peer.encrypt=false;
  if(esp_now_add_peer(&peer)!=ESP_OK || esp_now_register_recv_cb(onReceive)!=ESP_OK)return false;
  return xTaskCreate(task,"alarmRadio",4096,nullptr,2,nullptr)==pdPASS;
}
void status(){
  Serial.printf("BRIDGE role=%s state=%lu rx=%lu seq=%lu ack=%lu ack_state=%lu ack_age_ms=%lu errors=%lu drops=%lu\n",
    isCam?"CAM":"S3",(unsigned long)effective.load(),(unsigned long)received.load(),
    (unsigned long)statusSeq.load(),(unsigned long)acked.load(),(unsigned long)ackState.load(),
    (unsigned long)(millis()-ackAt.load()),(unsigned long)sendErrors.load(),(unsigned long)queueDrops.load());
}
} // namespace bridge
