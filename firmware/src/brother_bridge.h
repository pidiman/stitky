#pragma once
// Included after the P15 HTTP/queue helpers. Shares Wi-Fi, never the BLE session.
#include <LittleFS.h>
#include <esp_littlefs.h>
#include "brother_ipp.h"

Preferences brotherStore;
bool brotherStoreReady=false,brotherStorageReady=false;
String brotherJobId,brotherLease,brotherOutcome,brotherMessage;
uint32_t brotherIppJob=0;
unsigned long nextBrotherPoll=0,nextBrotherProbe=0;
const char* BROTHER_FILE="/brother.job";

#include "brother_body_stream.h"
uint32_t brotherRequestId(){uint32_t id=esp_random()&0x7fffffffU;return id?id:1;}
String brotherUri(){return "ipp://"+brotherHost+"/ipp/print";}
bool brotherPersist(const String& outcome,const String& message,uint32_t ippJob=0) {
  if(!brotherStoreReady)return false;
  DynamicJsonDocument d(1600);d["id"]=brotherJobId;d["lease"]=brotherLease;
  d["outcome"]=outcome;d["message"]=message;d["ipp_job"]=ippJob;
  String record;serializeJson(d,record);
  if(brotherStore.putString("pending",record)!=record.length())return false;
  brotherOutcome=outcome;brotherMessage=message;brotherIppJob=ippJob;
  brotherHasPending=brotherJobId.length()>0;return true;
}
void setupBrother() {
  brotherStoreReady=brotherStore.begin("ql810w-jobs",false);
  if(!brotherStoreReady){Serial.println("BROTHER NVS FAILED");return;}
  String pending=brotherStore.getString("pending","");
  if(pending.length()){
    DynamicJsonDocument d(1600);
    if(deserializeJson(d,pending)){brotherHasPending=true;Serial.println("BROTHER PENDING CORRUPT; manual recovery required");return;}
    brotherJobId=d["id"]|"";brotherLease=d["lease"]|"";
    brotherOutcome=d["outcome"]|"unknown";brotherMessage=d["message"]|"Interrupted Brother attempt";
    brotherIppJob=d["ipp_job"]|0;brotherHasPending=true;
    if(!brotherJobId.length()||!brotherLease.length()){Serial.println("BROTHER PENDING INVALID");return;}
  }
  if(!brotherToken.length()||!brotherHost.length())return;
  // The one-time OTA migration relocates the spool. Only initialise the
  // new layout when there is no outstanding job; NVS/Wi-Fi remain untouched.
  const String storageLayout="ota2-256k-v1";
  bool firstLayout=brotherStore.getString("fs-layout","")!=storageLayout;
  if(!brotherHasPending&&firstLayout) {
    if(esp_littlefs_format("spiffs")!=ESP_OK){Serial.println("BROTHER STORAGE INIT FAILED");return;}
    if(brotherStore.putString("fs-layout",storageLayout)!=storageLayout.length()){Serial.println("BROTHER STORAGE MARKER FAILED");return;}
    brotherStore.putBool("fs-ready",true);
  }
  brotherStorageReady=LittleFS.begin(false);
  Serial.printf("BROTHER READY storage=%d pending=%d\n",brotherStorageReady,brotherHasPending);
}
BrotherIpp::Response brotherRequest(const std::string& prefix,uint32_t requestId,File* data=nullptr) {
  BrotherIpp::Response result;
  if(!readyWiFi()||!brotherHost.length())return result;
  WiFiClient client;HTTPClient http;http.setConnectTimeout(4000);http.setTimeout(12000);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);http.useHTTP10(false);http.setReuse(false);
  if(!http.begin(client,"http://"+brotherHost+":631/ipp/print"))return result;
  http.addHeader("Content-Type","application/ipp");
  int status;
  if(data){BrotherBodyStream body(prefix,*data,oledProgress);status=http.sendRequest("POST",&body,prefix.size()+data->size());}
  else status=http.POST((uint8_t*)prefix.data(),prefix.size());
  if(status==200){
    int size=http.getSize();
    if(size>=0&&size<=16384){
      String response=http.getString();
      if(response.length()==unsigned(size))
        result=BrotherIpp::parse(std::string(response.c_str(),response.length()),requestId);
    }
  }
  if(!result.ok())Serial.printf("BROTHER IPP HTTP=%d valid=%d status=0x%04x\n",status,result.valid,result.status);
  http.end();client.stop();return result;
}
BrotherIpp::Response brotherStatus() {
  uint32_t requestId=brotherRequestId();
  return brotherRequest(BrotherIpp::statusRequest(requestId,brotherUri().c_str()),requestId);
}
bool brotherDownload(const String& path,size_t size,const String& expected) {
  oledShow(FpsOled::State::BrotherDownload,"BROTHER");
  if(!brotherStorageReady||size<400||size>250000||expected.length()!=64||
     path!="/api/agent/jobs/"+brotherJobId+"/payload")return false;
  WiFiClientSecure tls;tls.setCACert(caPem.c_str());tls.setHandshakeTimeout(12);
  HTTPClient http;http.setConnectTimeout(12000);http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);http.useHTTP10(true);
  if(!http.begin(tls,apiUrl+path))return false;
  http.addHeader("Authorization","Bearer "+brotherToken);http.addHeader("X-Lease-Token",brotherLease);
  int status=http.GET();bool valid=false;
  if(status==200&&http.getSize()==int(size)){
    File file=LittleFS.open(BROTHER_FILE,"w");
    if(file){int written=http.writeToStream(&file);file.flush();file.close();valid=written==int(size);}
  }
  http.end();tls.stop();
  if(!valid)return false;
  File file=LittleFS.open(BROTHER_FILE,"r");if(!file||file.size()!=size){if(file)file.close();return false;}
  mbedtls_sha256_context context;mbedtls_sha256_init(&context);mbedtls_sha256_starts_ret(&context,0);
  uint8_t chunk[1024],hash[32];size_t count;
  while((count=file.read(chunk,sizeof(chunk)))>0){mbedtls_sha256_update_ret(&context,chunk,count);ledTick();}
  file.close();mbedtls_sha256_finish_ret(&context,hash);mbedtls_sha256_free(&context);
  char actual[65]={0};for(int i=0;i<32;++i)sprintf(actual+i*2,"%02x",hash[i]);
  return expected==actual;
}
String brotherWaitForJob(uint32_t job) {
  oledShow(FpsOled::State::BrotherPrint,"CAKAM NA DOKONCENIE");
  unsigned long began=millis();
  while(millis()-began<55000){
    uint32_t id=brotherRequestId();auto response=brotherRequest(BrotherIpp::jobRequest(id,brotherUri().c_str(),job),id);
    if(!response.ok())return "unknown";
    int state=response.integer("job-state");
    if(state==9){
      if(response.has("job-state-reasons","job-completed-with-errors")||
         response.has("job-state-reasons","job-completed-with-warnings"))return "unknown";
      return "printed";
    }
    if(state==7||state==8)return "unknown";
    if(state<3||state>6)return "unknown";
    pauseWithLed(1000);
  }
  return "unknown";
}
bool brotherReport() {
  if(!brotherJobId.length()||!brotherLease.length())return false;
  if(brotherOutcome=="pending"&&brotherIppJob){
    String outcome=brotherWaitForJob(brotherIppJob);
    if(!brotherPersist(outcome,outcome=="printed"?"Brother confirmed IPP job completed; inspect physical label":"Brother print result uncertain; do not automatically resend",brotherIppJob)){
      brotherOutcome="unknown";brotherMessage="Result persistence failed; no automatic resend";
    }
  }
  DynamicJsonDocument d(1000);d["lease_token"]=brotherLease;d["outcome"]=brotherOutcome;d["message"]=brotherMessage;
  String body;serializeJson(d,body);
  int status=post("/api/agent/jobs/"+brotherJobId+"/complete",body,nullptr,nullptr,brotherToken);
  if(status!=200){ledError();Serial.printf("BROTHER RESULT HTTP %d; pending retained\n",status);return false;}
  if(!brotherStore.remove("pending")){ledError();return false;}
  bool confirmed=brotherOutcome=="printed";
  oledResult("BR",brotherOutcome);
  brotherJobId="";brotherLease="";brotherOutcome="";brotherMessage="";brotherIppJob=0;brotherHasPending=false;
  if(brotherStorageReady)LittleFS.remove(BROTHER_FILE);
  ledHeartbeat();
  if(confirmed){successUntil=millis()+1000;pauseWithLed(1000);}else ledError();
  return true;
}
void brotherTelemetry(bool force=false) {
  if(!force&&static_cast<int32_t>(millis()-nextBrotherProbe)<0)return;
  nextBrotherProbe=millis()+30000;
  // Background status polling must not interrupt the idle screen or a result.
  auto response=brotherStatus();
  bool found=response.ok()&&response.text("printer-make-and-model").find("QL-810W")!=std::string::npos;
  DynamicJsonDocument d(1400);d["firmware_version"]=FIRMWARE_VERSION;d["wifi_rssi"]=WiFi.RSSI();
  d["uptime_s"]=static_cast<uint32_t>(esp_timer_get_time()/1000000);d["free_heap"]=ESP.getFreeHeap();
  d["printer_checked"]=true;d["printer_connected"]=found;d["model"]="Brother QL-810W";
  // ArduinoJson borrows const char*; keep this storage alive through serialization.
  const std::string mediaReady=found?response.text("media-ready"):"";
  d["media_ready"]=mediaReady.c_str();
  bool idle=found&&response.integer("printer-state")==3&&response.has("printer-state-reasons","none");
  oledBrotherStatus(found,idle,mediaReady);
  d["printer_status"]=idle?"ready":"unknown";
  d["last_error"]=!brotherStorageReady?"Brother spool storage unavailable":!found?"Brother IPP unavailable":idle?"":"Brother is busy or reports a printer condition";
  String body;serializeJson(d,body);
  int status=post("/api/agent/telemetry",body,nullptr,nullptr,brotherToken);
  Serial.printf("BROTHER TELEMETRY HTTP %d reachable=%d\n",status,found);
  if(status==200)ledHeartbeat();else ledError();
}
void pollBrother() {
  if(!brotherToken.length()||!brotherHost.length()||!brotherStoreReady)return;
  if(brotherHasPending){brotherReport();return;}
  if(static_cast<int32_t>(millis()-nextBrotherPoll)<0)return;
  nextBrotherPoll=millis()+10000;
  if(!brotherStorageReady){brotherTelemetry();return;}
  String payload;bool refresh=false;
  int status=post("/api/agent/claim","{}",&payload,&refresh,brotherToken);
  if(status==204){ledHeartbeat();brotherTelemetry(refresh);return;}
  if(status!=200){ledError();Serial.printf("BROTHER POLL HTTP %d\n",status);return;}
  DynamicJsonDocument d(3000);
  if(deserializeJson(d,payload)){ledError();return;}
  String id=d["id"]|"",lease=d["lease_token"]|"",format=d["format"]|"";
  String path=d["payload_path"]|"",hash=d["sha256"]|"";
  size_t size=d["size"]|0;int width=d["media_width_mm"]|0,length=d["media_length_mm"]|0;
  if(id.length()<1||id.length()>64||lease.length()<16||lease.length()>128||format!="brother-raster-v1"||
     d["width"].as<int>()!=720||d["height"].as<int>()<150||d["height"].as<int>()>2400||size>250000){ledError();return;}
  brotherJobId=id;brotherLease=lease;
  if(!brotherPersist("unknown","Interrupted before Brother result; no automatic resend")){
    brotherHasPending=true;Serial.println("BROTHER PENDING SAVE FAILED; no print");ledError();return;
  }
  d.clear();d.shrinkToFit();payload=String();
  if(!brotherDownload(path,size,hash)){
    ledError("BR: STITOK NEOVERENY");brotherPersist("failed","Brother payload download/verification failed; no print sent");brotherReport();return;
  }
  oledShow(FpsOled::State::BrotherCheck,"OVERUJEM ROLKU A STAV");
  auto preflight=brotherStatus();
  if(!preflight.ok()||preflight.text("printer-make-and-model").find("QL-810W")==std::string::npos||
     preflight.integer("printer-state")!=3||!preflight.has("printer-state-reasons","none")||
     !preflight.has("document-format-supported","application/octet-stream")||
     !BrotherIpp::mediaMatches(preflight.text("media-ready"),width,length)){
    ledError("BR: SKONTROLUJ ROLKU");brotherPersist("failed","Brother unavailable, not idle or loaded roll differs from label; no print sent");brotherReport();return;
  }
  DynamicJsonDocument start(300);start["lease_token"]=lease;String body;serializeJson(start,body);
  if(post("/api/agent/jobs/"+id+"/start",body,nullptr,nullptr,brotherToken)!=200){
    brotherReport();return;
  }
  ledSet(LedMode::Printing);
  File file=LittleFS.open(BROTHER_FILE,"r");
  if(!file||file.size()!=size){
    if(file)file.close();brotherPersist("failed","Verified Brother spool unavailable; no print sent");brotherReport();return;
  }
  uint32_t requestId=brotherRequestId();
  auto result=brotherRequest(BrotherIpp::printRequest(requestId,brotherUri().c_str(),id.c_str()),requestId,&file);
  file.close();
  int ippJob=result.ok()?result.integer("job-id"):-1;
  if(ippJob>0){
    if(!brotherPersist("pending","Brother IPP submission accepted",ippJob)){
      brotherOutcome="unknown";brotherMessage="Brother accepted submission but journal failed; inspect label";
    }
  }else{
    brotherPersist("unknown","Brother submission result uncertain; do not automatically resend");
  }
  brotherReport();
}
void brotherCheckOnly() {
  if(!readyWiFi()||!brotherHost.length()){Serial.println("BROTHER CHECK unavailable: configure host and Wi-Fi");return;}
  oledShow(FpsOled::State::BrotherCheck,"CITAM STAV TLACIARNE");
  auto r=brotherStatus();
  bool idle=r.ok()&&r.integer("printer-state")==3&&r.has("printer-state-reasons","none");
  oledBrotherStatus(r.ok(),idle,r.text("media-ready"));
  if(!r.ok())ledError("BR: NEDOSTUPNY");
  else oledShow(FpsOled::State::Ready,idle?"BR: PRIPRAVENY":"BR: SKONTROLUJ STAV",3500);
  Serial.printf("BROTHER CHECK response=%d idle=%d model=%s media=%s\n",r.ok(),r.integer("printer-state")==3,
                r.text("printer-make-and-model").c_str(),r.text("media-ready").c_str());
}
