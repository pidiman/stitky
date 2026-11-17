#pragma once
#include <Update.h>
#include <esp_ota_ops.h>

Preferences otaStore;
bool otaStoreReady=false,otaCapable=false;
unsigned long nextOtaCheck=0;
String otaResultId,otaBootSha,otaError;

String otaHash(const esp_partition_t* partition,size_t length){
  if(!partition||!length||length>partition->size)return "";
  mbedtls_sha256_context context;mbedtls_sha256_init(&context);mbedtls_sha256_starts_ret(&context,0);
  uint8_t buffer[1024],hash[32];bool ok=true;
  for(size_t pos=0;pos<length;){
    size_t n=std::min(sizeof(buffer),length-pos);
    if(esp_partition_read(partition,pos,buffer,n)!=ESP_OK){ok=false;break;}
    mbedtls_sha256_update_ret(&context,buffer,n);pos+=n;ledTick();delay(0);
  }
  mbedtls_sha256_finish_ret(&context,hash);mbedtls_sha256_free(&context);
  if(!ok)return "";
  char hex[65]={0};for(unsigned i=0;i<32;++i)sprintf(hex+i*2,"%02x",hash[i]);return hex;
}
void otaStatus(){
  const auto* running=esp_ota_get_running_partition();
  Serial.printf("OTA STATUS capable=%d slot=%d pending=%d max_size=%u layout=%s\n",otaCapable,running?int(running->subtype)-ESP_PARTITION_SUBTYPE_APP_OTA_0:-1,otaResultId.length()>0,0x1D0000,FPS_OTA_LAYOUT);
}
void setupOta(){
  otaStoreReady=otaStore.begin("fps-ota",false);
  const auto* running=esp_ota_get_running_partition();const auto* next=esp_ota_get_next_update_partition(nullptr);
  otaCapable=otaStoreReady&&running&&next&&next->address!=running->address&&running->size==0x1D0000&&next->size==0x1D0000;
  otaResultId=otaStore.getString("id","");otaError=otaStore.getString("error","");
  if(otaResultId.length()&&!otaError.length()){
    if(!running||running->address==otaStore.getUInt("from",0))otaError="Aktualizacia bola prerusena; povodny firmver zostal aktivny.";
    else{
      otaBootSha=otaHash(running,otaStore.getUInt("size",0));
      if(otaBootSha!=otaStore.getString("sha",""))otaError="Kontrola beziaceho firmveru zlyhala.";
    }
  }
  // The product/layout/version marker is embedded and validated by the server.
  Serial.println(FIRMWARE_OTA_TAG);otaStatus();
}
bool otaDownload(const String& path,size_t size,const String& expected){
  WiFiClientSecure tls;tls.setCACert(caPem.c_str());tls.setHandshakeTimeout(12);
  HTTPClient http;http.setConnectTimeout(12000);http.setTimeout(15000);http.useHTTP10(true);http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if(!http.begin(tls,apiUrl+path))return false;
  http.addHeader("Authorization","Bearer "+agentToken);
  int status=http.GET();bool ok=status==200&&http.getSize()==int(size);
  if(ok)ok=Update.begin(size,U_FLASH);
  mbedtls_sha256_context context;mbedtls_sha256_init(&context);mbedtls_sha256_starts_ret(&context,0);
  uint8_t buffer[1024],hash[32];size_t received=0;unsigned long began=millis(),lastData=began;
  WiFiClient* stream=http.getStreamPtr();
  while(ok&&received<size){
    if(millis()-began>180000||millis()-lastData>15000){ok=false;break;}
    int available=stream->available();
    if(available>0){
      size_t count=std::min(size-received,std::min(sizeof(buffer),size_t(available)));
      int n=stream->read(buffer,count);
      if(n<=0){ok=false;break;}
      mbedtls_sha256_update_ret(&context,buffer,n);
      if(Update.write(buffer,n)!=size_t(n)){ok=false;break;}
      received+=n;lastData=millis();oledProgress(received,size);
    }else if(!http.connected()){ok=false;break;}
    ledTick();delay(1);
  }
  mbedtls_sha256_finish_ret(&context,hash);mbedtls_sha256_free(&context);
  char actual[65]={0};for(unsigned i=0;i<32;++i)sprintf(actual+i*2,"%02x",hash[i]);
  oledShow(FpsOled::State::Ota,"OVERUJEM SHA256");
  ok=ok&&received==size&&expected==actual;
  http.end();tls.stop();
  // Only a complete, hash-verified image may become bootable.
  if(ok)ok=Update.end();else Update.abort();
  return ok;
}
void serviceOta(){
  if(!otaCapable||printing||pendingId.length()||brotherHasPending||portalActive||!readyWiFi()||static_cast<int32_t>(millis()-nextOtaCheck)<0)return;
  nextOtaCheck=millis()+20000;
  DynamicJsonDocument d(1100);d["version"]=FIRMWARE_VERSION;d["layout"]=FPS_OTA_LAYOUT;
  if(otaResultId.length()){
    d["result_id"]=otaResultId;
    if(otaError.length())d["error"]=otaError;else d["boot_sha256"]=otaBootSha;
  }
  String body,response;serializeJson(d,body);
  if(post("/api/agent/firmware/check",body,&response)!=200)return;
  d.clear();if(deserializeJson(d,response))return;
  if(d["acknowledged"]==true&&otaResultId.length()){
    if(!otaStore.remove("id")){ledError();return;}
    otaResultId="";otaBootSha="";otaError="";
  }
  if(otaResultId.length()){oledShow(FpsOled::State::Error,"OTA: CAKAM NA API",8000);return;}
  if(d["update"].isNull()){oledShow(FpsOled::State::Ready);return;}
  String id=d["update"]["id"]|"",path=d["update"]["path"]|"",sha=d["update"]["sha256"]|"";
  size_t size=d["update"]["size"]|0;
  if(id.length()!=36||path!="/api/agent/firmware/"+id+"/image"||sha.length()!=64||size<1024||size>0x1D0000)return;
  const auto* running=esp_ota_get_running_partition();
  bool saved=otaStore.putString("sha",sha)==sha.length()&&otaStore.putUInt("size",size)==4&&otaStore.putUInt("from",running->address)==4;
  otaStore.remove("error");
  if(!saved||otaStore.putString("id",id)!=id.length()){ledError();return;}
  otaResultId=id;stopBle();ledErrorLatched=false;ledSet(LedMode::Updating);
  Serial.println("OTA DOWNLOAD START; no print jobs will be processed");
  if(otaDownload(path,size,sha)){
    oledShow(FpsOled::State::Ota,"RESTARTUJEM ESP32");Serial.println("OTA VERIFIED; RESTARTING");pauseWithLed(200);ESP.restart();
  }else{
    otaError="Stiahnutie alebo overenie firmveru zlyhalo; povodny firmver zostal aktivny.";
    otaStore.putString("error",otaError);ledError("AKTUALIZACIA ZLYHALA");nextOtaCheck=0;Serial.println("OTA FAILED; original firmware retained");
  }
}
