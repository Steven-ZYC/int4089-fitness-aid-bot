#pragma once
#include <Wire.h>

// Standalone bench logger. Only this task accesses Wire after initialization.
// No UART writes from the sampling task: JPEG export cannot block it on console.
namespace imu {
constexpr uint8_t address=0x68;
constexpr size_t capacity=4096;
constexpr uint8_t expectedConfig[4]={0x27,0x05,0x27,0x02};
struct Sample {
  int64_t readUs;
  uint32_t seq,ticks,request;
  int16_t raw[6]; // ax,ay,az,gx,gy,gz
  uint8_t phase;
};
static Sample *samples=nullptr;
static portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<int> fault{0};
static bool recording=false,overflow=false;
static bool exporting=false;
static uint32_t count=0,traceId=0,readErrors=0,configErrors=0,totalSamples=0;
static uint32_t exportIndex=0,phaseRequest=0;
static uint8_t phase=0;
static int64_t startedUs=0,stoppedUs=0,firstUs=0,lastUs=0,maxGapUs=0,exportStartedUs=0;
static uint8_t cachedConfig[4],cachedPmu=0,cachedError=0,cachedId=0;

static bool read(uint8_t reg,uint8_t *bytes,size_t length) {
  Wire.beginTransmission(address); Wire.write(reg);
  if (Wire.endTransmission(false)!=0) return false;
  if (Wire.requestFrom(address,length,true)!=length) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for(size_t i=0;i<length;++i) bytes[i]=Wire.read();
  return true;
}
static bool write(uint8_t reg,uint8_t value) {
  Wire.beginTransmission(address); Wire.write(reg); Wire.write(value);
  uint8_t result=Wire.endTransmission(true); delay(1); return result==0;
}
static bool checkConfig() {
  uint8_t cfg[4],pmu=0,err=0,id=0;
  return read(0x40,cfg,4) && read(0x03,&pmu,1) && read(0x02,&err,1) &&
      read(0x00,&id,1) && id==0xD1 && (pmu&0x3F)==0x14 && err==0 &&
      memcmp(cfg,expectedConfig,4)==0;
}
static int16_t signed16(const uint8_t *p) {
  int32_t value=p[0]|(static_cast<uint16_t>(p[1])<<8);
  if(value&0x8000) value-=65536;
  return static_cast<int16_t>(value);
}
static void markPhase(uint8_t value,uint32_t request) {
  portENTER_CRITICAL(&mux); phase=value; phaseRequest=request; portEXIT_CRITICAL(&mux);
}
static void task(void *) {
  int64_t lastFresh=esp_timer_get_time(),nextCheck=lastFresh+5000000;
  unsigned consecutive=0;
  for(;;) {
    if(fault.load()) { vTaskDelay(pdMS_TO_TICKS(50)); continue; }
    uint8_t status=0;
    bool ok=read(0x1B,&status,1);
    if(ok && (status&0xC0)==0xC0) {
      Sample sample={}; uint8_t bytes[15];
      sample.readUs=esp_timer_get_time();
      portENTER_CRITICAL(&mux);
      sample.phase=phase; sample.request=phaseRequest;
      portEXIT_CRITICAL(&mux);
      ok=read(0x0C,bytes,sizeof(bytes));
      if(ok) {
        for(unsigned i=0;i<3;++i) {
          sample.raw[i]=signed16(bytes+6+i*2);
          sample.raw[i+3]=signed16(bytes+i*2);
        }
        sample.ticks=bytes[12]|(uint32_t(bytes[13])<<8)|(uint32_t(bytes[14])<<16);
        lastFresh=esp_timer_get_time();
        portENTER_CRITICAL(&mux);
        ++totalSamples;
        if(recording && sample.readUs>=startedUs) {
          if(count>=capacity) { overflow=true; recording=false; stoppedUs=lastFresh; }
          else {
            sample.seq=count+1; samples[count++]=sample;
            if(firstUs==0) firstUs=sample.readUs;
            if(lastUs && sample.readUs-lastUs>maxGapUs) maxGapUs=sample.readUs-lastUs;
            lastUs=sample.readUs;
          }
        }
        portEXIT_CRITICAL(&mux);
      }
    }
    if(!ok) {
      portENTER_CRITICAL(&mux); ++readErrors; portEXIT_CRITICAL(&mux);
      if(++consecutive>=5) fault.store(1);
      vTaskDelay(pdMS_TO_TICKS(20));
    } else consecutive=0;
    int64_t now=esp_timer_get_time();
    if(now-lastFresh>1000000) fault.store(2);
    if(now>=nextCheck) {
      if(!checkConfig()) {
        portENTER_CRITICAL(&mux); ++configErrors; portEXIT_CRITICAL(&mux);
        fault.store(3);
      }
      nextCheck=now+5000000;
    }
    vTaskDelay(1);
  }
}
static bool begin() {
  samples=static_cast<Sample *>(heap_caps_malloc(capacity*sizeof(Sample),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  if(!samples || !Wire.begin(4,5,100000)) return false;
  Wire.setTimeOut(100);
  for(uint8_t probe: {uint8_t(0x68),uint8_t(0x69)}) {
    Wire.beginTransmission(probe); Wire.write(0x00);
    uint8_t ack=Wire.endTransmission(false),id=0;
    bool got=ack==0 && Wire.requestFrom(probe,size_t(1),true)==1;
    if(got) id=Wire.read();
    console.printf("IMU_PROBE address=0x%02X ack=%u read=%u id=0x%02X\n",probe,ack,got,id);
  }
  auto failed=[](const char *stage) { console.printf("IMU_INIT_FAILED stage=%s\n",stage); return false; };
  uint8_t id=0;
  if(!read(0,&id,1) || id!=0xD1) return failed("INITIAL_ID");
  if(!write(0x7E,0xB6)) return failed("SOFT_RESET_WRITE");
  delay(100);
  if(!write(0x7E,0x11)) return failed("ACCEL_WAKE_WRITE");
  delay(10);
  if(!write(0x7E,0x15)) return failed("GYRO_WAKE_WRITE");
  delay(100);
  for(unsigned i=0;i<4;++i) if(!write(0x40+i,expectedConfig[i])) return failed("CONFIG_WRITE");
  delay(200);
  uint8_t discard[15];
  if(!read(0x0C,discard,15)) return failed("DATA_READ");
  if(!read(0x40,cachedConfig,4) || !read(0x03,&cachedPmu,1) ||
      !read(0x02,&cachedError,1) || !read(0,&cachedId,1)) return failed("CONFIG_READ");
  console.printf("IMU_INIT_CHECK id=0x%02X acc_conf=0x%02X acc_range=0x%02X gyr_conf=0x%02X gyr_range=0x%02X pmu=0x%02X err=0x%02X\n",
      cachedId,cachedConfig[0],cachedConfig[1],cachedConfig[2],cachedConfig[3],cachedPmu,cachedError);
  if(!checkConfig()) return failed("CONFIG_VERIFY");
  if(xTaskCreatePinnedToCore(task,"bmi160",4096,nullptr,3,nullptr,1)!=pdPASS) return failed("TASK_ALLOC");
  return true;
}
static void printStatus() {
  uint32_t n,id,errors,cfgErrors,total; int64_t start,stop,first,last,gap; bool active,full;
  portENTER_CRITICAL(&mux);
  n=count; id=traceId; errors=readErrors; cfgErrors=configErrors; total=totalSamples;
  start=startedUs; stop=stoppedUs; first=firstUs; last=lastUs; gap=maxGapUs;
  active=recording; full=overflow;
  portEXIT_CRITICAL(&mux);
  console.printf("IMU_STATUS trace=%lu count=%lu recording=%u overflow=%u read_errors=%lu config_errors=%lu "
      "fault=%d total_samples=%lu started_us=%lld stopped_us=%lld first_us=%lld last_us=%lld max_gap_us=%lld\n",
      (unsigned long)id,(unsigned long)n,active,full,(unsigned long)errors,(unsigned long)cfgErrors,
      fault.load(),(unsigned long)total,start,stop,first,last,gap);
}
static void printConfig() {
  console.printf("IMU_CONFIG chip_id=0x%02X address=0x68 acc_conf=0x%02X acc_range=0x%02X "
      "gyr_conf=0x%02X gyr_range=0x%02X pmu=0x%02X err=0x%02X odr_hz=50 i2c_timeout_ms=100 "
      "accel_lsb_per_g=8192 gyro_lsb_per_dps=65.6 calibrated=NO task_core=1 task_priority=3 capacity=%u\n",
      cachedId,cachedConfig[0],cachedConfig[1],cachedConfig[2],cachedConfig[3],cachedPmu,cachedError,(unsigned)capacity);
}
// Only used when initialization failed before creating the acquisition task.
// Compare the gateway timeout with the earlier working six-axis baseline.
static void diagnoseBus() {
  if(fault.load()!=4) { console.println("ERR_IMU_DIAG_REQUIRES_INIT_FAULT"); return; }
  for(uint16_t timeout: {uint16_t(20),uint16_t(100)}) {
    Wire.setTimeOut(timeout);
    console.printf("IMU_BUS_CASE timeout_ms=%u\n",timeout);
    bool continueCase=true;
    const uint8_t values[3]={0xB6,0x11,0x15};
    const unsigned settle[3]={100,10,120};
    for(unsigned i=0;i<3 && continueCase;++i) {
      Wire.beginTransmission(address); Wire.write(0x7E); Wire.write(values[i]);
      int64_t start=esp_timer_get_time();
      uint8_t code=Wire.endTransmission(true);
      int64_t elapsed=esp_timer_get_time()-start;
      console.printf("IMU_BUS_WRITE timeout_ms=%u value=0x%02X code=%u elapsed_us=%lld\n",
          timeout,values[i],code,elapsed);
      delay(settle[i]);
      // A timeout may still have delivered a command; always inspect after settling.
      if(code && i<2) continueCase=false;
    }
    uint8_t id=0,pmu=0,err=0;
    bool identityRead=read(0,&id,1),powerRead=read(3,&pmu,1),errorRead=read(2,&err,1);
    console.printf("IMU_BUS_STATE timeout_ms=%u id_read=%u id=0x%02X pmu_read=%u pmu=0x%02X err_read=%u err=0x%02X\n",
        timeout,identityRead,id,powerRead,pmu,errorRead,err);
  }
  Wire.setTimeOut(100);
  console.println("IMU_BUS_DONE acquisition=OFF settings=VOLATILE_ONLY");
}
static bool command(const char *text) {
  if(strcmp(text,"IMU_BUS_DIAG")==0) diagnoseBus();
  else if(strcmp(text,"IMU_START")==0) {
    portENTER_CRITICAL(&mux);
    bool busy=recording || exporting;
    if(!busy && !fault.load()) {
      ++traceId; count=0; overflow=false; firstUs=lastUs=maxGapUs=stoppedUs=0;
      startedUs=esp_timer_get_time(); recording=true;
    }
    portEXIT_CRITICAL(&mux);
    if(busy || fault.load()) console.println("ERR_IMU_START"); else printStatus();
  } else if(strcmp(text,"IMU_STOP")==0) {
    portENTER_CRITICAL(&mux);
    if(recording) { recording=false; stoppedUs=esp_timer_get_time(); }
    portEXIT_CRITICAL(&mux); printStatus();
  } else if(strcmp(text,"IMU_STATUS")==0) printStatus();
  else if(strcmp(text,"IMU_DUMP")==0) {
    portENTER_CRITICAL(&mux); bool active=recording; uint32_t n=count; portEXIT_CRITICAL(&mux);
    if(active || exporting || !n) console.println("ERR_IMU_DUMP");
    else {
      exporting=true; exportIndex=0; exportStartedUs=esp_timer_get_time();
      console.printf("IMU_BEGIN trace=%lu count=%lu\n",(unsigned long)traceId,(unsigned long)n);
      console.println("IMU_COLUMNS sample_seq,t_read_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,phase,request");
    }
  } else return false;
  return true;
}
static void advanceDump() {
  if(!exporting) return;
  if(esp_timer_get_time()-exportStartedUs>60000000) {
    exporting=false; console.println("ERR_IMU_EXPORT_TIMEOUT"); return;
  }
  if(exportIndex<count && console.availableForWrite()>=180) {
    const Sample &s=samples[exportIndex++];
    console.printf("IMU_ROW %lu,%lld,%lu,%d,%d,%d,%d,%d,%d,%u,%lu\n",
        (unsigned long)s.seq,s.readUs,(unsigned long)s.ticks,s.raw[0],s.raw[1],s.raw[2],
        s.raw[3],s.raw[4],s.raw[5],s.phase,(unsigned long)s.request);
  }
  if(exportIndex==count) {
    console.printf("IMU_END trace=%lu count=%lu\n",(unsigned long)traceId,(unsigned long)count);
    exporting=false;
  }
}
} // namespace imu
