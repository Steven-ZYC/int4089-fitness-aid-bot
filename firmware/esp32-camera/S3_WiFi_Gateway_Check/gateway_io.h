#pragma once
#include <NetworkServer.h>
#include <NetworkClient.h>
#include <sys/socket.h>
#include <errno.h>

// One bounded TCP session. AP credentials are supplied over USB into RAM only.
// Binary output stays attached to its TCP session, even if that client drops.
class GatewayIO : public Stream {
  NetworkServer server{IPAddress(192,168,4,1),4089,1};
  NetworkClient client;
  bool ap=false,session=false,writeFailed=false;
  uint32_t accepted=0,disconnected=0;
public:
  using Print::write;
  size_t setTxBufferSize(size_t size) { return Serial.setTxBufferSize(size); }
  void begin(unsigned long baud) { Serial.begin(baud); }
  bool networkSession() const { return session; }
  bool activeAP() const { return ap; }
  int available() override { return session?client.available():Serial.available(); }
  int read() override { return session?client.read():Serial.read(); }
  int peek() override { return session?client.peek():Serial.peek(); }
  int availableForWrite() override {
    if(!session) return Serial.availableForWrite();
    if(!client.connected() || client.fd()<0 || writeFailed) return 0;
    fd_set fds; FD_ZERO(&fds); FD_SET(client.fd(),&fds); timeval wait={0,0};
    return select(client.fd()+1,nullptr,&fds,nullptr,&wait)>0?256:0;
  }
  void flush() override { if(!session) Serial.flush(); }
  size_t write(uint8_t byte) override { return write(&byte,1); }
  size_t write(const uint8_t *bytes,size_t length) override {
    if(!session) return Serial.write(bytes,length);
    if(writeFailed || !client.connected()) { writeFailed=true; return 0; }
    size_t offset=0; int64_t deadline=esp_timer_get_time()+250000;
    while(offset<length && esp_timer_get_time()<deadline) {
      int n=send(client.fd(),bytes+offset,length-offset,MSG_DONTWAIT);
      if(n>0) offset+=n;
      else if(n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK) break;
      else delay(1);
    }
    if(offset!=length) writeFailed=true;
    return offset;
  }
  bool startAP(const char *password) {
    if(ap || session || strlen(password)<12 || strlen(password)>32) return false;
    if(!WiFi.softAPConfig(IPAddress(192,168,4,1),IPAddress(192,168,4,1),IPAddress(255,255,255,0)) ||
        !WiFi.softAP("INT4089-S3-Yuankun",password,1,0,1)) {
      WiFi.softAPdisconnect(true); return false;
    }
    uint8_t channel=0; wifi_second_chan_t second;
    if(esp_wifi_get_channel(&channel,&second)!=ESP_OK || channel!=1) {
      WiFi.softAPdisconnect(true); return false;
    }
    server.begin(); ap=static_cast<bool>(server);
    if(!ap) WiFi.softAPdisconnect(true);
    return ap;
  }
  void stopAP() {
    client.stop(); session=false; writeFailed=false; server.end();
    WiFi.softAPdisconnect(true); ap=false;
  }
  // 1 = accepted; -1 = disconnected/failed write; 0 = unchanged.
  int poll() {
    if(session && (writeFailed || !client.connected())) {
      client.stop(); session=false; writeFailed=false; ++disconnected; return -1;
    }
    if(ap && !session) {
      NetworkClient incoming=server.accept();
      if(incoming) {
        client=incoming; client.setNoDelay(true); session=true; ++accepted; return 1;
      }
    }
    return 0;
  }
  void status() {
    printf("LINK transport=%s ap=%u channel=1 port=4089 sessions=%lu disconnects=%lu\n",
        session?"TCP":"USB",ap,(unsigned long)accepted,(unsigned long)disconnected);
  }
};
static GatewayIO console;
