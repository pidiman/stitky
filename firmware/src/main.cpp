#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <BLEDevice.h>
#include <BLEClient.h>
#include <BLEScan.h>
#include <mbedtls/base64.h>
#include <mbedtls/sha256.h>
#include <time.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <esp_system.h>
#include <nvs.h>
#include <Adafruit_NeoPixel.h>
#include "portal_page.h"
#include "printer_info.h"

// Fixed hardware profile proven on this P15: 40x12mm, 96x320, gap stock.
static constexpr const char* FIRMWARE_VERSION="1.3.1";
static constexpr size_t RASTER_SIZE = 3840;
static uint8_t raster[RASTER_SIZE];
static uint8_t bulk[8 + RASTER_SIZE + 6];
Preferences configStore, jobStore;
String ssid, password, apiUrl, agentToken, printerMac, caPem, serialLine;
String pendingId, pendingLease, pendingOutcome, pendingMessage;
String brotherToken,brotherHost;
bool brotherHasPending=false;
bool configured=false, serialOverflow=false, portalActive=false, configNvsReady=false, jobNvsReady=false;
String configError;
WebServer portal(80);DNSServer dns;
String portalNonce;
String portalWifiOptions="<option value='MyWiFi' selected>MyWiFi</option>";
bool portalScanPending=false;
unsigned long portalScanRequested=0;
unsigned long portalStarted=0, bootHeldSince=0;
unsigned long nextPoll=0, lastWiFiAttempt=0;
BLEClient* bleClient=nullptr;
BLERemoteCharacteristic* tx=nullptr;
portMUX_TYPE flowMux=portMUX_INITIALIZER_UNLOCKED;
volatile int credits=0;
volatile bool printerAck=false, printerFault=false, printing=false;
volatile uint8_t lastWiFiDisconnectReason=0;
// Replies are copied by the BLE callback; decoding/logging happens in loop task.
static uint8_t queryReply[256];
volatile size_t queryReplyLength=0;
volatile bool queryActive=false;
volatile unsigned long queryLastData=0;
bool probeRequested=true,probeReportPending=false,probeAttempted=false,lastProbeConnected=false;
unsigned long lastProbeAttempt=0,nextTelemetry=0;
String probeModel,probeFirmware,probeSerial,probeStatus="unknown",probeError;
int probeBattery=-1;

// One external 5V WS2812-compatible RGB status pixel. No extra FreeRTOS task.
#ifndef LED_PIN
#define LED_PIN 18
#endif
#ifndef LED_COUNT
#define LED_COUNT 1
#endif
#ifndef LED_BRIGHTNESS
#define LED_BRIGHTNESS 32
#endif
static_assert(LED_COUNT>=1 && LED_COUNT<=16,"Use 1 to 16 status pixels");
static_assert(LED_BRIGHTNESS>=1 && LED_BRIGHTNESS<=255,"Invalid LED brightness");
Adafruit_NeoPixel statusPixels(LED_COUNT,LED_PIN,NEO_GRB+NEO_KHZ800);
enum class LedMode:uint8_t {Portal,Connecting,Ready,BleConnecting,BleConnected,Printing,Error};
LedMode ledMode=LedMode::Connecting;
bool ledErrorLatched=false,ledSelfTest=false;
unsigned long successUntil=0,ledTestStarted=0;
uint32_t lastLedColor=0xffffffff;
String setupAPName,setupAPPassword;
void ledTick() {
  unsigned long now=millis();LedMode mode=ledErrorLatched?LedMode::Error:ledMode;
  bool success=static_cast<int32_t>(successUntil-now)>0;
  if(ledSelfTest){
    unsigned long elapsed=now-ledTestStarted;
    if(elapsed>=12000){ledSelfTest=false;Serial.println("LED TEST DONE; normal status restored");}
    else{
      const LedMode modes[]={LedMode::Portal,LedMode::Connecting,LedMode::Ready,LedMode::BleConnecting,LedMode::BleConnected,LedMode::Printing,LedMode::Error};
      unsigned stage=elapsed/1500;
      if(stage<7){mode=modes[stage];success=false;}else success=true;
    }
  }
  uint32_t color=0;
  if(success)color=(now%200<100)?statusPixels.Color(0,255,0):0;
  else switch(mode){
    case LedMode::Portal:color=(now%1000<500)?statusPixels.Color(0,0,255):0;break;
    case LedMode::Connecting:color=(now%600<300)?statusPixels.Color(255,160,0):0;break;
    case LedMode::Ready:color=statusPixels.Color(0,80,0);break;
    case LedMode::BleConnecting:color=(now%1000<500)?statusPixels.Color(180,0,255):0;break;
    case LedMode::BleConnected:color=statusPixels.Color(180,0,255);break;
    case LedMode::Printing:color=(now%300<150)?statusPixels.Color(0,255,255):0;break;
    case LedMode::Error:color=(now%500<250)?statusPixels.Color(255,0,0):0;break;
  }
  if(color!=lastLedColor){statusPixels.fill(color);statusPixels.show();lastLedColor=color;}
}
void ledSet(LedMode mode){ledMode=mode;ledTick();}
void ledError(){ledErrorLatched=true;ledTick();}
void ledHeartbeat(){ledErrorLatched=false;ledSet(LedMode::Ready);}
void pauseWithLed(unsigned long duration){
  unsigned long started=millis();do{ledTick();delay(5);}while(millis()-started<duration);
}
void setupInfo(){
  if(!portalActive){Serial.println("SETUP_INFO unavailable: portal is not active; send WIFI_SETUP");return;}
  Serial.println("SETUP_AP_SSID="+setupAPName);Serial.println("SETUP_AP_PASSWORD="+setupAPPassword);
}

String logSafeSsid(String value){
  if(value.length()>32)value=value.substring(0,32);
  for(unsigned i=0;i<value.length();++i)if((uint8_t)value[i]<32||value[i]=='"'||(uint8_t)value[i]==127)value.setCharAt(i,'?');
  return value;
}
void wifiDiagnosticEvent(arduino_event_id_t event,arduino_event_info_t info){
  if(event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED){
    uint8_t reason=info.wifi_sta_disconnected.reason;lastWiFiDisconnectReason=reason;
    Serial.printf("WIFI DISCONNECTED reason=%u (%s)\n",reason,WiFi.disconnectReasonName(static_cast<wifi_err_reason_t>(reason)));
  }else if(event==ARDUINO_EVENT_WIFI_STA_GOT_IP){
    uint8_t* ip=reinterpret_cast<uint8_t*>(&info.got_ip.ip_info.ip.addr);
    Serial.printf("WIFI GOT_IP %u.%u.%u.%u\n",ip[0],ip[1],ip[2],ip[3]);
  }else if(event==ARDUINO_EVENT_WIFI_STA_CONNECTED)Serial.println("WIFI ASSOCIATED; waiting for IP");
}
bool validMac(const String& s) {
  if(s.length()!=17)return false;
  for(int i=0;i<17;++i){if(i%3==2){if(s[i]!=':')return false;}else if(!isxdigit(s[i]))return false;}
  return true;
}
bool readConfiguration(const String& json, bool save) {
  configError="";
  DynamicJsonDocument d(10000);
  DeserializationError parseError=deserializeJson(d,json);
  if(parseError){configError=String("JSON_")+parseError.c_str()+" bytes="+String(json.length());return false;}
  if(!d.is<JsonObject>()){configError="JSON_NOT_OBJECT";return false;}
  String nextSsid=d["ssid"]|ssid.c_str(), nextPassword=d["password"]|password.c_str();
  String url=d["api_url"]|apiUrl.c_str(), token=d["agent_token"]|agentToken.c_str(), mac=d["printer_mac"]|printerMac.c_str();
  if(!mac.length())mac="02:00:00:00:00:01";
  String ca=d["server_ca_pem"]|caPem.c_str();
  String nextBrotherToken=d["brother_token"]|brotherToken.c_str(), nextBrotherHost=d["brother_host"]|brotherHost.c_str();
  if(nextBrotherToken.length()||nextBrotherHost.length()){
    IPAddress hostAddress;
    if(nextBrotherToken.length()<24||nextBrotherToken.length()>200||!hostAddress.fromString(nextBrotherHost)){
      configError="BROTHER_HOST_OR_TOKEN";return false;
    }
  }
  while(url.endsWith("/"))url.remove(url.length()-1);
  mac.toLowerCase();
  bool serverValid=url.startsWith("https://")&&url.length()<=240&&url.indexOf('@')<0&&
     token.length()>=24&&token.length()<=200&&ca.indexOf("-----BEGIN CERTIFICATE-----")>=0&&ca.length()<=6000;
  bool serverFields=url.length()||token.length()||ca.length();
  if(nextSsid.length()>32){configError="SSID_LENGTH";return false;}
  if(nextPassword.length()>63){configError="WIFI_PASSWORD_LENGTH";return false;}
  if(!validMac(mac)){configError="PRINTER_MAC_FORMAT";return false;}
  if(serverFields&&!serverValid){
    if(!url.startsWith("https://")||url.length()>240||url.indexOf('@')>=0)configError="API_URL_FORMAT";
    else if(token.length()<24||token.length()>200)configError="TOKEN_LENGTH";
    else if(ca.indexOf("-----BEGIN CERTIFICATE-----")<0)configError="CA_PEM_HEADER";
    else if(ca.length()>6000)configError="CA_LENGTH";
    else configError="SERVER_FIELDS";
    return false;
  }
  d["ssid"]=nextSsid;d["password"]=nextPassword;
  d["brother_token"]=nextBrotherToken;d["brother_host"]=nextBrotherHost;
  d["api_url"]=url;d["agent_token"]=token;d["printer_mac"]=mac;d["server_ca_pem"]=ca;
  if(save){
    if(!configNvsReady){configError="NVS_CONFIG_NOT_OPEN";return false;}
    if(d.overflowed()){configError="JSON_CAPACITY";return false;}
    String stored;serializeJson(d,stored);
    size_t written=configStore.putString("settings",stored);
    if(written!=stored.length()){
      nvs_stats_t stats={};nvs_get_stats(nullptr,&stats);
      configError="NVS_WRITE written="+String(written)+" expected="+String(stored.length())+" freeEntries="+String(stats.free_entries);
      return false;
    }
  }
  brotherToken=nextBrotherToken;brotherHost=nextBrotherHost;
  ssid=nextSsid;password=nextPassword;apiUrl=url;agentToken=token;printerMac=mac;caPem=ca;configured=serverValid;
  return true;
}
bool persistPending(const String& id,const String& lease,const String& outcome,const String& message) {
  DynamicJsonDocument d(1600);d["id"]=id;d["lease_token"]=lease;d["outcome"]=outcome;d["message"]=message;
  String record;serializeJson(d,record);
  if(jobStore.putString("pending",record)!=record.length())return false;
  pendingId=id;pendingLease=lease;pendingOutcome=outcome;pendingMessage=message;return true;
}
bool loadPending() {
  String record=jobStore.getString("pending","");if(!record.length())return true;
  DynamicJsonDocument d(1600);if(deserializeJson(d,record)){Serial.println("PENDING CORRUPT: provisioning/operator recovery required; polling stopped");return false;}
  pendingId=d["id"]|"";pendingLease=d["lease_token"]|"";pendingOutcome=d["outcome"]|"unknown";pendingMessage=d["message"]|"";
  return pendingId.length() && pendingLease.length();
}
String escapeHtml(String value) {
  value.replace("&","&amp;");value.replace("<","&lt;");value.replace(">","&gt;");value.replace("\"","&quot;");value.replace("'","&#39;");return value;
}
String randomCode(size_t n) {
  const char alphabet[]="ABCDEFGHJKLMNPQRSTUVWXYZ23456789";String result;result.reserve(n);
  for(size_t i=0;i<n;++i)result+=alphabet[esp_random()%(sizeof(alphabet)-1)];return result;
}
void startPortalScan() {
  if(portalScanPending || (portalScanRequested && millis()-portalScanRequested<3000))return;
  portalScanRequested=millis();WiFi.scanDelete();
  int result=WiFi.scanNetworks(true,false); // Asynchronous: never block an HTTP response.
  portalScanPending=result==WIFI_SCAN_RUNNING || result>=0;
  Serial.println(portalScanPending?"PORTAL SCAN STARTED":"PORTAL SCAN UNAVAILABLE");
}
void updatePortalScanCache() {
  if(!portalScanPending)return;
  int count=WiFi.scanComplete();if(count==WIFI_SCAN_RUNNING)return;
  portalScanPending=false;
  if(count<0){Serial.println("PORTAL SCAN FAILED; default network kept");return;}
  String options="<option value='MyWiFi' selected>MyWiFi</option>";
  // Keep the default available before/after scanning; escape all discovered names.
  for(int i=0;i<count && i<40;++i){
    String name=WiFi.SSID(i);if(!name.length()||name=="MyWiFi")continue;
    options+="<option value='"+escapeHtml(name)+"'>"+escapeHtml(name)+" ("+String(WiFi.RSSI(i))+" dBm)</option>";
  }
  portalWifiOptions=options;WiFi.scanDelete();Serial.printf("PORTAL SCAN CACHED count=%d\n",count);
}
void servePortalPage() {
  updatePortalScanCache();
  String html=renderPortalHtml(portalNonce.c_str(),portalWifiOptions.c_str(),portalScanPending).c_str();
  String path=portal.uri();if(path.length()>96)path=path.substring(0,96);
  path.replace("\r","");path.replace("\n","");
  Serial.printf("PORTAL GET %s HTML bytes=%u\n",path.c_str(),html.length());
  portal.sendHeader("Cache-Control","no-store");portal.sendHeader("Pragma","no-cache");
  portal.sendHeader("Connection","close");portal.setContentLength(html.length());
  portal.send(200,"text/html; charset=utf-8",html);
}
void startPortal() {
  if(portalActive)return;
  WiFi.disconnect();WiFi.mode(WIFI_AP_STA);
  setupAPName="P15-Setup-"+String((uint32_t)(ESP.getEfuseMac()&0xffff),HEX);
  setupAPPassword=configStore.getString("setup-pass","");
  if(setupAPPassword.length()<8||setupAPPassword.length()>63){
    setupAPPassword=randomCode(12);
    if(configStore.putString("setup-pass",setupAPPassword)!=setupAPPassword.length()){
      Serial.println("WIFI SETUP PASSWORD SAVE FAILED; AP not opened");ledError();return;
    }
  }
  portalNonce=randomCode(24);
  if(!WiFi.softAP(setupAPName.c_str(),setupAPPassword.c_str())){Serial.println("WIFI SETUP AP FAILED");ledError();return;}
  dns.start(53,"*",WiFi.softAPIP());portalStarted=millis();portalActive=true;ledSet(LedMode::Portal);
  Serial.println("WIFI SETUP: connect to the protected setup AP, then open http://192.168.4.1");
  setupInfo();
  portal.on("/",HTTP_GET,servePortalPage);
  portal.on("/rescan",HTTP_GET,[](){startPortalScan();servePortalPage();});
  portal.on("/save",HTTP_POST,[](){
    if(portal.arg("csrf")!=portalNonce){portal.send(403,"text/plain","Invalid setup session");return;}
    String nextSsid=portal.arg("ssid"),nextPassword=portal.arg("password");
    if(!nextSsid.length()||nextSsid.length()>32||nextPassword.length()>63){portal.send(400,"text/plain","Invalid Wi-Fi settings");return;}
    DynamicJsonDocument d(10000);d["ssid"]=nextSsid;d["password"]=nextPassword;
    String settings;serializeJson(d,settings);
    if(!readConfiguration(settings,true)){ledError();portal.send(500,"text/plain","Settings not saved");return;}
    portal.sendHeader("Cache-Control","no-store");portal.send(200,"text/html; charset=utf-8","<meta charset='utf-8'><h1>Wi-Fi uložená</h1><p>ESP32 sa teraz reštartuje a pripojí k vybranej sieti. Môžeš sa vrátiť na svoju bežnú Wi-Fi.</p>");
    Serial.println("WIFI CONFIG SAVED; RESTARTING");pauseWithLed(500);ESP.restart();
  });
  portal.onNotFound([](){
    // Captive mini-browsers sometimes ignore empty redirect bodies. Serve the full
    // setup form for every GET probe rather than depending on a redirect chain.
    if(portal.method()==HTTP_GET)servePortalPage();
    else{portal.sendHeader("Connection","close");portal.send(404,"text/plain","Not found");}
  });
  portal.begin();startPortalScan();
}
void servicePortal() {
  if(!portalActive)return;dns.processNextRequest();updatePortalScanCache();portal.handleClient();
  if(millis()-portalStarted>=600000){dns.stop();portal.stop();WiFi.softAPdisconnect(true);portalActive=false;WiFi.mode(WIFI_STA);lastWiFiAttempt=0;Serial.println("WIFI SETUP TIMEOUT; hold BOOT 3s to reopen");ledSet(LedMode::Connecting);}
}
bool readyWiFi() {
  if(portalActive)return false;
  if(!ssid.length()){ledSet(LedMode::Connecting);return false;}
  if(WiFi.status()!=WL_CONNECTED){
    ledSet(LedMode::Connecting);
    if(!lastWiFiAttempt||millis()-lastWiFiAttempt>=15000){
      lastWiFiAttempt=millis();WiFi.mode(WIFI_STA);WiFi.begin(ssid.c_str(),password.c_str());Serial.println("WIFI CONNECTING");
    }
    return false;
  }
  if(time(nullptr)<1700000000){ledSet(LedMode::Connecting);return false;}
  return true;
}
// Each request owns and frees TLS allocations before the BLE stack is started.
int post(const String& path,const String& body,String* response=nullptr,bool* refreshRequested=nullptr,const String& overrideToken="") {
  if(refreshRequested)*refreshRequested=false;
  if(!readyWiFi())return -1;
  ledSet(LedMode::Connecting);
  WiFiClientSecure tls;tls.setCACert(caPem.c_str());tls.setHandshakeTimeout(12);
  HTTPClient http;http.setConnectTimeout(12000);http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);http.useHTTP10(true);
  if(!http.begin(tls,apiUrl+path)){ledError();return -2;}
  const char* responseHeaders[]={"X-Printer-Refresh"};http.collectHeaders(responseHeaders,1);
  http.addHeader("Authorization","Bearer "+(overrideToken.length()?overrideToken:agentToken));http.addHeader("Content-Type","application/json");
  int status=http.POST(body);
  if(refreshRequested)*refreshRequested=http.header("X-Printer-Refresh")=="1";
  if(response && status==200){
    int size=http.getSize();
    if(size<0||size>12000){http.end();tls.stop();ledError();return -3;}
    *response=http.getString();
    if(response->length()!=static_cast<unsigned>(size)){http.end();tls.stop();ledError();return -4;}
  }
  http.end();tls.stop();if(status<200||status>=300)ledError();return status;
}
void notify(BLERemoteCharacteristic* c,uint8_t* d,size_t n,bool) {
  if(!n)return;
  portENTER_CRITICAL(&flowMux);
  bool control=c->getUUID().equals(BLEUUID((uint16_t)0xff03));
  if(control&&n>=2&&d[0]==1)credits+=d[1];
  if(queryActive && (!control || (d[0]!=1 && d[0]!=2))) {
    size_t count=std::min(n,sizeof(queryReply)-queryReplyLength);
    memcpy(queryReply+queryReplyLength,d,count);queryReplyLength+=count;
    queryLastData=millis();
  }
  if(printing&&((n==1&&d[0]==0xaa)||(n==2&&d[0]==0x4f&&d[1]==0x4b)))printerAck=true;
  if(printing&&n>=2&&d[0]==0xff&&d[1]>=1&&d[1]<=4)printerFault=true;
  portEXIT_CRITICAL(&flowMux);
}
bool sendBle(const uint8_t* bytes,size_t length,unsigned long timeoutMs=30000) {
  size_t offset=0;unsigned long started=millis();
  while(offset<length){
    if(!bleClient->isConnected()||printerFault||millis()-started>timeoutMs)return false;
    bool allowed=false;portENTER_CRITICAL(&flowMux);if(credits>0){--credits;allowed=true;}portEXIT_CRITICAL(&flowMux);
    if(!allowed){pauseWithLed(10);continue;}
    size_t count=std::min(static_cast<size_t>(20),length-offset);
    tx->writeValue(const_cast<uint8_t*>(bytes+offset),count,false);offset+=count;pauseWithLed(30);
  }
  return true;
}
bool connectBle() {
  ledSet(LedMode::BleConnecting);
  BLEDevice::init("P15-Hub-Bridge");
  // Swap the callback target before freeing the previous client's service cache.
  BLEClient* previous=bleClient;bleClient=BLEDevice::createClient();delete previous;
  credits=0;printerAck=false;printerFault=false;printing=false;
  BLEScan* scan=BLEDevice::getScan();scan->setActiveScan(true);scan->setInterval(100);scan->setWindow(80);
  auto results=scan->start(10,false);bool connected=false;
  for(int i=0;i<results.getCount();++i){
    auto device=results.getDevice(i);if(device.getAddress().toString()!=printerMac.c_str())continue;
    if(!bleClient->connect(&device))break;
    auto service=bleClient->getService(BLEUUID((uint16_t)0xff00));if(!service)break;
    tx=service->getCharacteristic(BLEUUID((uint16_t)0xff02));
    auto rx=service->getCharacteristic(BLEUUID((uint16_t)0xff01));auto cx=service->getCharacteristic(BLEUUID((uint16_t)0xff03));
    if(!tx||!rx||!cx||!tx->canWriteNoResponse()||!rx->canNotify()||!cx->canNotify())break;
    rx->registerForNotify(notify);cx->registerForNotify(notify);
    auto start=millis();while(credits<=0&&millis()-start<5000)pauseWithLed(20);
    connected=credits>0;break;
  }
  scan->clearResults();if(connected){ledSet(LedMode::BleConnected);pauseWithLed(200);}return connected;
}
void stopBle() {
  printing=false;
  if(bleClient&&bleClient->isConnected()){
    bleClient->disconnect();auto started=millis();while(bleClient->isConnected()&&millis()-started<1000)pauseWithLed(10);
  }
  // Keep the client object alive: Arduino BLEDevice retains its GAP callback pointer.
  tx=nullptr;BLEDevice::deinit(false);
  pauseWithLed(100);
}
// A bounded read-only probe: these are queries, not print/enable/feed commands.
size_t queryPrinter(const char* name,const uint8_t* command,size_t length,uint8_t* reply) {
  portENTER_CRITICAL(&flowMux);
  queryReplyLength=0;queryLastData=0;queryActive=true;
  portEXIT_CRITICAL(&flowMux);
  bool sent=sendBle(command,length,1000);
  unsigned long start=millis();
  while(sent&&bleClient->isConnected()&&millis()-start<3000) {
    size_t available;unsigned long last;
    portENTER_CRITICAL(&flowMux);available=queryReplyLength;last=queryLastData;portEXIT_CRITICAL(&flowMux);
    if(available && millis()-last>=150)break;
    pauseWithLed(10);
  }
  portENTER_CRITICAL(&flowMux);
  queryActive=false;size_t count=queryReplyLength;memcpy(reply,queryReply,count);
  portEXIT_CRITICAL(&flowMux);
  Serial.printf("INFO RAW %s sent=%d bytes=%u hex=",name,sent,static_cast<unsigned>(count));
  for(size_t i=0;i<count;++i)Serial.printf("%02X",reply[i]);
  Serial.println();pauseWithLed(100);
  return count;
}
void probePrinter() {
  if(printing||pendingId.length()||portalActive)return;
  probeRequested=false;probeAttempted=true;lastProbeAttempt=millis();
  probeModel="";probeFirmware="";probeSerial="";probeBattery=-1;probeStatus="unknown";probeError="";
  Serial.println("PRINTER INFO START; read-only query commands; no print data");
  lastProbeConnected=connectBle();
  if(!lastProbeConnected) {
    stopBle();probeError="P15 not reachable over BLE at this check";ledError();
  }else {
    uint8_t reply[256];size_t count;
    const uint8_t model[]={0x10,0xff,0x20,0xf0},firmware[]={0x10,0xff,0x20,0xf1},
      serial[]={0x10,0xff,0x20,0xf2},battery[]={0x10,0xff,0x50,0xf1},status[]={0x10,0xff,0x40};
    count=queryPrinter("model",model,sizeof(model),reply);probeModel=printerIdentity(reply,count).c_str();
    count=queryPrinter("firmware",firmware,sizeof(firmware),reply);probeFirmware=printerIdentity(reply,count).c_str();
    count=queryPrinter("serial",serial,sizeof(serial),reply);probeSerial=printerIdentity(reply,count).c_str();
    count=queryPrinter("battery",battery,sizeof(battery),reply);probeBattery=printerBatteryPercent(reply,count);
    count=queryPrinter("status",status,sizeof(status),reply);probeStatus=printerStatus(reply,count);
    if(!bleClient->isConnected())probeError="BLE disconnected during information queries; missing values are unavailable";
    else if(!probeModel.length()&&!probeFirmware.length()&&!probeSerial.length()&&probeBattery<0&&probeStatus=="unknown")
      probeError="P15 connected but returned no recognized information replies";
    stopBle();ledSet(LedMode::Ready);
  }
  probeReportPending=true;
  Serial.printf("PRINTER INFO DONE connected=%d modelKnown=%d firmwareKnown=%d serialKnown=%d batteryKnown=%d status=%s\n",
    lastProbeConnected,probeModel.length()>0,probeFirmware.length()>0,probeSerial.length()>0,probeBattery>=0,probeStatus.c_str());
}
void serviceTelemetry() {
  if(printing||pendingId.length()||portalActive||!readyWiFi())return;
  if(static_cast<int32_t>(millis()-nextTelemetry)<0)return;
  nextTelemetry=millis()+30000;
  DynamicJsonDocument d(2000);
  d["firmware_version"]=FIRMWARE_VERSION;d["wifi_rssi"]=WiFi.RSSI();
  d["uptime_s"]=static_cast<uint32_t>(esp_timer_get_time()/1000000);d["free_heap"]=ESP.getFreeHeap();
  d["printer_checked"]=probeReportPending;
  if(probeReportPending) {
    d["printer_connected"]=lastProbeConnected;
    if(probeModel.length())d["model"]=probeModel;
    if(probeFirmware.length())d["firmware"]=probeFirmware;
    if(probeSerial.length())d["serial"]=probeSerial;
    if(probeBattery>=0)d["battery_percent"]=probeBattery;
    d["printer_status"]=probeStatus;d["last_error"]=probeError;
  }
  String body;serializeJson(d,body);
  int result=post("/api/agent/telemetry",body);
  Serial.printf("TELEMETRY HTTP %d printer_checked=%d\n",result,probeReportPending);
  if(result==200){probeReportPending=false;ledHeartbeat();}
  else ledError();
}
String printRaster() {
  Serial.printf("BLE START freeHeap=%u\n",ESP.getFreeHeap());
  if(!connectBle()){stopBle();ledError();return "failed";} // No print bytes have been sent.
  uint8_t preamble[19]={0};preamble[15]=0x10;preamble[16]=0xff;preamble[17]=0xf1;preamble[18]=2;
  uint8_t header[]={0x1d,0x76,0x30,0,12,0,0x40,0x01};
  memcpy(bulk,header,8);memcpy(bulk+8,raster,RASTER_SIZE);
  uint8_t end[]={0x1d,0x0c,0x10,0xff,0xf1,0x45};memcpy(bulk+8+RASTER_SIZE,end,6);
  printing=true;printerAck=false;printerFault=false;ledSet(LedMode::Printing);
  bool sent=sendBle(preamble,sizeof(preamble));if(sent){pauseWithLed(300);sent=sendBle(bulk,sizeof(bulk));}
  auto start=millis();while(sent&&!printerAck&&!printerFault&&bleClient->isConnected()&&millis()-start<15000)pauseWithLed(20);
  bool success=sent&&printerAck&&!printerFault;
  Serial.printf("BLE RESULT sent=%d ack=%d fault=%d\n",sent,printerAck,printerFault);
  stopBle();
  if(success){successUntil=millis()+1000;ledSet(LedMode::Ready);pauseWithLed(1000);}else ledError();
  return success?"printed":"unknown";
}
bool reportPending() {
  if(!pendingId.length())return true;
  DynamicJsonDocument d(1200);d["lease_token"]=pendingLease;d["outcome"]=pendingOutcome;d["message"]=pendingMessage;
  String body;serializeJson(d,body);
  int status=post("/api/agent/jobs/"+pendingId+"/complete",body);
  Serial.printf("RESULT REPORT HTTP %d\n",status);
  if(status!=200){ledError();return false;} // Keep unresolved job and stop claiming more work.
  if(!jobStore.remove("pending")){Serial.println("NVS CLEAR FAILED: polling stopped");ledError();return false;}
  pendingId="";pendingLease="";pendingOutcome="";pendingMessage="";ledSet(LedMode::Ready);return true;
}
void poll() {
  if(pendingId.length()){reportPending();return;}
  String payload;bool refresh=false;int status=post("/api/agent/claim","{}",&payload,&refresh);
  if(status==204){
    ledHeartbeat();Serial.println("HEARTBEAT OK; QUEUE EMPTY");
    if(refresh)probeRequested=true;
    if(probeRequested&&!probeReportPending&&(!probeAttempted||millis()-lastProbeAttempt>=60000)) {
      probePrinter();nextTelemetry=0;
    }
    return;
  }
  if(status!=200){ledError();Serial.printf("POLL HTTP %d\n",status);return;}
  ledHeartbeat();
  DynamicJsonDocument d(11000);
  if(deserializeJson(d,payload)){Serial.println("INVALID CLAIM JSON; no print");ledError();return;}
  String id=d["id"]|"",lease=d["lease_token"]|"",expected=d["sha256"]|"";
  const char* encoded=d["raster_base64"]|"";
  if(id.length()<1||id.length()>64||lease.length()<1||lease.length()>200){Serial.println("INVALID CLAIM IDS; no print");ledError();return;}
  // Persist a quarantine marker before any start request, including transport ambiguity.
  if(!persistPending(id,lease,"unknown","Interrupted before result; never automatically reprinted")){
    Serial.println("NVS SAVE FAILED; no print");ledError();return;
  }
  size_t decoded=0;
  bool valid=d["width"].as<int>()==96&&d["height"].as<int>()==320&&strlen(encoded)==5120;
  if(valid)valid=mbedtls_base64_decode(raster,RASTER_SIZE,&decoded,reinterpret_cast<const unsigned char*>(encoded),strlen(encoded))==0&&decoded==RASTER_SIZE;
  unsigned char digest[32];char actual[65]={0};
  if(valid){mbedtls_sha256_ret(raster,RASTER_SIZE,digest,0);for(int i=0;i<32;++i)sprintf(actual+i*2,"%02x",digest[i]);valid=expected==actual;}
  if(!valid){ledError();persistPending(id,lease,"failed","Invalid raster geometry, size or SHA-256; no print bytes sent");reportPending();return;}
  // Free JSON and response buffers before TLS handshake, and TLS before BLE.
  d.clear();d.shrinkToFit();payload=String();
  DynamicJsonDocument startDoc(512);startDoc["lease_token"]=lease;String body;serializeJson(startDoc,body);
  status=post("/api/agent/jobs/"+id+"/start",body);
  if(status!=200){ledError();Serial.printf("START HTTP %d; no print and no retry\n",status);reportPending();return;}
  String outcome=printRaster();
  if(!persistPending(id,lease,outcome,outcome=="printed"?"P15 acknowledged AA/OK; visual result unverified":outcome=="failed"?"BLE unavailable; no print bytes sent":"Print may be partial; no automatic retry")){
    Serial.println("NVS RESULT SAVE FAILED: prior unknown marker retained");ledError();
    pendingOutcome="unknown";pendingMessage="Result persistence failed; no automatic retry";
  }
  reportPending();
}
#include "brother_bridge.h"

void serialInput() {
  while(Serial.available()){
    char c=Serial.read();if(c=='\r')continue;
    if(c=='\n'){
      if(serialOverflow){Serial.println("CONFIG REJECTED: input too long");}
      else if(serialLine.startsWith("CONFIG ")){
        if(pendingId.length()||brotherHasPending)Serial.println("CONFIG REJECTED: pending job must be resolved first");
        else if(readConfiguration(serialLine.substring(7),true)){Serial.println("CONFIG SAVED; RESTARTING");pauseWithLed(150);ESP.restart();}
        else{Serial.println("CONFIG REJECTED: "+configError);ledError();}
      }else if(serialLine=="WIFI_SETUP"){startPortal();
      }else if(serialLine=="SETUP_INFO"){setupInfo();
      }else if(serialLine=="LED_TEST"){ledSelfTest=true;ledTestStarted=millis();ledTick();Serial.println("LED TEST START: blue/yellow/green/purple blink/purple/cyan/red/green flash; no printer commands");
      }else if(serialLine=="BROTHER_CHECK"){brotherCheckOnly();
      }else if(serialLine=="PRINTER_INFO"){probeRequested=true;Serial.println("PRINTER INFO REQUESTED; waits for empty queue and 60s probe cooldown");
      }else if(serialLine=="STATUS"){
        Serial.printf("STATUS configured=%d wifi=%d wifi_status=%d pending=%d configNvs=%d jobNvs=%d lastDisconnect=%u saved_ssid=\"%s\" freeHeap=%u\n",configured,WiFi.status()==WL_CONNECTED,(int)WiFi.status(),pendingId.length()>0,configNvsReady,jobNvsReady,lastWiFiDisconnectReason,logSafeSsid(ssid).c_str(),ESP.getFreeHeap());
        Serial.printf("BROTHER STATUS configured=%d pending=%d\n",brotherToken.length()>0&&brotherHost.length()>0,brotherHasPending);
        Serial.printf("INFO STATUS requested=%d reportPending=%d lastProbeConnected=%d batteryKnown=%d\n",probeRequested,probeReportPending,lastProbeConnected,probeBattery>=0);
      }
      serialLine="";serialOverflow=false;
    }else if(!serialOverflow){if(serialLine.length()<8192)serialLine+=c;else{serialOverflow=true;serialLine="";}}
  }
}
void setup() {
  statusPixels.begin();statusPixels.setBrightness(LED_BRIGHTNESS);statusPixels.clear();statusPixels.show();ledTick();
  Serial.setRxBufferSize(8192);Serial.begin(115200);pinMode(0,INPUT_PULLUP);pauseWithLed(1000);Serial.println("FAJNY PRINT BRIDGE 1.3.1; NO BUILT-IN TEST PRINTS");
  configNvsReady=configStore.begin("p15-hub-config",false);jobNvsReady=jobStore.begin("p15-hub-jobs",false);
  Serial.printf("NVS OPEN config=%d jobs=%d\n",configNvsReady,jobNvsReady);
  if(!configNvsReady||!jobNvsReady){Serial.println("NVS OPEN FAILED; no print jobs will be processed");ledError();while(true){pauseWithLed(1000);}}
  if(!loadPending()){ledError();while(true){pauseWithLed(1000);}}
  readConfiguration(configStore.getString("settings",""),false);
  setupBrother();
  WiFi.onEvent(wifiDiagnosticEvent);
  WiFi.persistent(false);
  if(!configured)Serial.println("API PROVISION REQUIRED: send CONFIG via local masked tool");
  if(!ssid.length())startPortal();
  else{WiFi.mode(WIFI_STA);WiFi.begin(ssid.c_str(),password.c_str());lastWiFiAttempt=millis();}
  configTime(0,0,"pool.ntp.org","time.cloudflare.com");
}
void loop() {
  ledTick();serialInput();servicePortal();
  if(digitalRead(0)==LOW){if(!bootHeldSince)bootHeldSince=millis();if(millis()-bootHeldSince>=3000){startPortal();bootHeldSince=millis();}}else bootHeldSince=0;
  if(!ledSelfTest&&configured&&!brotherHasPending&&readyWiFi()&&static_cast<int32_t>(millis()-nextPoll)>=0){nextPoll=millis()+10000;poll();}
  if(!ledSelfTest&&configured&&!pendingId.length()&&readyWiFi())pollBrother();
  if(!ledSelfTest&&configured&&!brotherHasPending)serviceTelemetry();
  pauseWithLed(10);
}
