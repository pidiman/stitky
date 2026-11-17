#include "fajny_brother.h"
#include "esphome/components/network/util.h"
#include "esphome/components/json/json_util.h"
#include "esphome/core/log.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include <algorithm>
#include <cstring>
#include <ctime>
#include <memory>

namespace esphome::fajny_brother {
static const char *const TAG="fajny_brother";
static uint32_t request_id(){uint32_t n=esp_random()&0x7fffffff;return n?n:1;}
static std::string encode(const JsonDocument &d){std::string s;serializeJson(d,s);return s;}
static bool write_all(esp_http_client_handle_t h,const uint8_t *p,size_t n){
  while(n){int k=esp_http_client_write(h,reinterpret_cast<const char*>(p),std::min(n,size_t(1024)));if(k<=0)return false;p+=k;n-=k;vTaskDelay(1);}return true;
}
struct Http {
  esp_http_client_handle_t h=nullptr;
  explicit Http(const std::string &url){
    esp_http_client_config_t c{};c.url=url.c_str();c.timeout_ms=12000;c.disable_auto_redirect=true;c.buffer_size=1024;c.buffer_size_tx=1024;
    c.crt_bundle_attach=esp_crt_bundle_attach;h=esp_http_client_init(&c);
    if(h)esp_http_client_set_header(h,"Connection","close");
  }
  ~Http(){if(h){esp_http_client_close(h);esp_http_client_cleanup(h);}}
};
void FajnyBrother::setup(){
  ota::get_global_ota_callback()->add_global_state_listener(this);
  messages_=xQueueCreate(1,96);
  if(!messages_||xTaskCreate(task_entry_,"fajny-brother",8192,this,1,&task_)!=pdPASS){mark_failed();return;}
}
void FajnyBrother::loop(){
  connected_=network::is_connected();char text[96];
  if(messages_&&xQueueReceive(messages_,text,0)==pdTRUE&&last_status_!=text){
    last_status_=text;ESP_LOGI(TAG,"%s",text);if(sensor_)sensor_->publish_state(text);
  }
}
void FajnyBrother::dump_config(){ESP_LOGCONFIG(TAG,"Brother gateway %s; max payload %u bytes; updates via ESPHome",VERSION,unsigned(max_payload_));}
void FajnyBrother::status_(const char *text){char message[96]{};snprintf(message,sizeof(message),"%s",text);xQueueOverwrite(messages_,message);}
void FajnyBrother::task_entry_(void *arg){static_cast<FajnyBrother*>(arg)->run_();vTaskDelete(nullptr);}
bool FajnyBrother::load_(){
  if(nvs_open("fajny-brother",NVS_READWRITE,&nvs_)!=ESP_OK)return false;
  size_t length=sizeof(job_);esp_err_t r=nvs_get_blob(nvs_,"pending",&job_,&length);
  if(r==ESP_ERR_NVS_NOT_FOUND){job_=Journal{};pending_=false;return true;}
  if(r!=ESP_OK||length!=sizeof(job_)||job_.magic!=0x46424a31||
     !memchr(job_.id,0,sizeof(job_.id))||!memchr(job_.lease,0,sizeof(job_.lease))||
     !memchr(job_.outcome,0,sizeof(job_.outcome))||!memchr(job_.message,0,sizeof(job_.message))||
     !job_.id[0]||strlen(job_.lease)<16)return false;
  std::string outcome=job_.outcome;
  if(outcome!="printed"&&outcome!="failed"&&outcome!="unknown"&&outcome!="pending")return false;
  pending_=true;return true;
}
bool FajnyBrother::save_(const char *outcome,const char *message,uint32_t ipp_job){
  snprintf(job_.outcome,sizeof(job_.outcome),"%s",outcome);snprintf(job_.message,sizeof(job_.message),"%s",message);job_.ipp_job=ipp_job;
  pending_=true;
  if(nvs_set_blob(nvs_,"pending",&job_,sizeof(job_))!=ESP_OK||nvs_commit(nvs_)!=ESP_OK){storage_ok_=false;status_("CHYBA: PAMAT ULOHY");return false;}return true;
}
bool FajnyBrother::clear_(){
  if(nvs_erase_key(nvs_,"pending")!=ESP_OK||nvs_commit(nvs_)!=ESP_OK){storage_ok_=false;return false;}
  pending_=false;job_=Journal{};return true;
}
void FajnyBrother::run_(){
  storage_ok_=load_();if(!storage_ok_)status_("CHYBA: PAMAT ULOHY");
  uint32_t telemetry_at=0;
  while(!stopping_){
    if(!connected_)status_("CAKAM NA WI-FI");
    else if(time(nullptr)<1700000000)status_("CAKAM NA CAS / SNTP");
    else if(storage_ok_&&!ota_active_){
      uint32_t now=esp_timer_get_time()/1000;
      if(!telemetry_at||uint32_t(now-telemetry_at)>=30000){telemetry_();telemetry_at=now;}
      if(!stopping_)cycle_();
    }
    for(int i=0;i<100&&!stopping_;++i)vTaskDelay(pdMS_TO_TICKS(100));
  }
  if(nvs_)nvs_close(nvs_);
}
int FajnyBrother::request_(const std::string &url,const char *type,const std::string &prefix,const uint8_t *payload,size_t size,std::string &response){
  Http client(url);auto h=client.h;response.clear();if(!h)return -1;
  bool api=url.compare(0,api_url_.size()+1,api_url_+"/")==0;
  if(api)esp_http_client_set_header(h,"Authorization",("Bearer "+token_).c_str());
  esp_http_client_set_method(h,HTTP_METHOD_POST);esp_http_client_set_header(h,"Content-Type",type);
  if(esp_http_client_open(h,prefix.size()+size)!=ESP_OK||!write_all(h,reinterpret_cast<const uint8_t*>(prefix.data()),prefix.size())||
     (size&&!write_all(h,payload,size)))return -1;
  int64_t length=esp_http_client_fetch_headers(h);int code=esp_http_client_get_status_code(h);
  if(code==204)return code;
  // No chunked/unbounded bodies or redirects; neither API tokens nor labels follow redirects.
  if(length<0||length>16384||esp_http_client_is_chunked_response(h))return -2;
  response.resize(length);size_t done=0;
  while(done<response.size()){int n=esp_http_client_read(h,&response[done],response.size()-done);if(n<=0)return -2;done+=n;vTaskDelay(1);}
  if(!esp_http_client_is_complete_data_received(h))return -2;
  return code;
}
int FajnyBrother::api_(const std::string &path,const std::string &body,std::string &response){return request_(api_url_+path,"application/json",body,nullptr,0,response);}
BrotherIpp::Response FajnyBrother::ipp_(const std::string &prefix,uint32_t id,const uint8_t *data,size_t size){
  std::string response;int code=request_("http://"+host_+":631/ipp/print","application/ipp",prefix,data,size,response);
  return code==200?BrotherIpp::parse(response,id):BrotherIpp::Response{};
}
BrotherIpp::Response FajnyBrother::printer_status_(){auto id=request_id();return ipp_(BrotherIpp::statusRequest(id,uri_()),id);}
void FajnyBrother::telemetry_(){
  auto r=printer_status_();bool found=r.ok()&&r.text("printer-make-and-model").find("QL-810W")!=std::string::npos;
  bool ready=found&&r.integer("printer-state")==3&&r.has("printer-state-reasons","none");
  JsonDocument d;d["firmware_version"]=VERSION;d["ota_supported"]=false;d["uptime_s"]=esp_timer_get_time()/1000000;
  d["free_heap"]=esp_get_free_heap_size();d["printer_checked"]=true;d["printer_connected"]=found;d["model"]="Brother QL-810W";
  d["printer_status"]=ready?"ready":"unknown";d["media_ready"]=found?r.text("media-ready"):"";
  d["last_error"]=!found?"Brother IPP unavailable":ready?"":"Brother busy or reports a printer condition";
  std::string response;int code=api_("/api/agent/telemetry",encode(d),response);
  if(!pending_)status_(code!=200?"CHYBA: SPOJENIE S APLIKACIOU":ready?"BROTHER PRIPRAVENY":found?"BROTHER: SKONTROLUJ STAV":"BROTHER NEDOSTUPNY");
}
bool FajnyBrother::download_(const std::string &path,uint8_t *data,size_t size,const std::string &sha){
  Http client(api_url_+path);auto h=client.h;if(!h)return false;
  esp_http_client_set_header(h,"Authorization",("Bearer "+token_).c_str());esp_http_client_set_header(h,"X-Lease-Token",job_.lease);
  esp_http_client_set_method(h,HTTP_METHOD_GET);
  if(esp_http_client_open(h,0)!=ESP_OK||esp_http_client_fetch_headers(h)!=int64_t(size)||esp_http_client_get_status_code(h)!=200||esp_http_client_is_chunked_response(h))return false;
  size_t done=0;int64_t began=esp_timer_get_time();
  while(done<size&&!stopping_&&!ota_active_){
    if(esp_timer_get_time()-began>90000000)return false;
    int n=esp_http_client_read(h,reinterpret_cast<char*>(data+done),std::min(size-done,size_t(1024)));if(n<=0)return false;done+=n;vTaskDelay(1);
  }
  if(done!=size||!esp_http_client_is_complete_data_received(h))return false;
  uint8_t digest[32];if(mbedtls_sha256(data,size,digest,0)!=0)return false;
  char actual[65]{};for(unsigned i=0;i<32;++i)snprintf(actual+i*2,3,"%02x",digest[i]);return sha==actual;
}
void FajnyBrother::cycle_(){if(ota_active_||stopping_)return;if(pending_)report_();else claim_();}
void FajnyBrother::claim_(){
  std::string response;int code=api_("/api/agent/claim","{}",response);if(code==204)return;
  if(code!=200){status_("CHYBA: SPOJENIE S APLIKACIOU");return;}
  JsonDocument d;if(deserializeJson(d,response)){status_("CHYBA: NEPLATNA ULOHA");return;}
  std::string id=d["id"]|"",lease=d["lease_token"]|"",path=d["payload_path"]|"",sha=d["sha256"]|"";
  size_t size=d["size"]|0;int width=d["media_width_mm"]|0,length=d["media_length_mm"]|0;
  if(id.empty()||id.size()>64||id.find_first_not_of("0123456789abcdef-")!=std::string::npos||lease.size()<16||lease.size()>128){status_("CHYBA: NEPLATNA ULOHA");return;}
  snprintf(job_.id,sizeof(job_.id),"%s",id.c_str());snprintf(job_.lease,sizeof(job_.lease),"%s",lease.c_str());
  if(!save_("failed","Interrupted before sending any print data"))return;
  if(d["format"]!="brother-raster-v1"||d["width"]!=720||path!="/api/agent/jobs/"+id+"/payload"||sha.size()!=64||size<400||size>max_payload_){save_("failed","Label exceeds this lightweight gateway's limit or format is invalid");report_();return;}
  // Reserve RAM before opening TLS. Large labels fail without starting a printer job.
  if(esp_get_free_heap_size()<size+90000){save_("failed","Not enough free RAM for this label; use a shorter label or the full gateway");report_();return;}
  std::unique_ptr<uint8_t,decltype(&free)> data(static_cast<uint8_t*>(heap_caps_malloc(size,MALLOC_CAP_8BIT)),free);
  if(!data){save_("failed","No contiguous memory for label");report_();return;}
  status_("PREBERAM A OVERUJEM STITOK");
  if(!download_(path,data.get(),size,sha)){data.reset();save_("failed","Label download or SHA256 verification failed; no print sent");report_();return;}
  auto preflight=printer_status_();
  if(!preflight.ok()||preflight.text("printer-make-and-model").find("QL-810W")==std::string::npos||preflight.integer("printer-state")!=3||
     !preflight.has("printer-state-reasons","none")||!preflight.has("document-format-supported","application/octet-stream")||!BrotherIpp::mediaMatches(preflight.text("media-ready"),width,length)){
    data.reset();save_("failed","Brother unavailable, busy or wrong loaded roll; no print sent");report_();return;
  }
  // Persist uncertainty BEFORE consuming /start. Never automatically resend this attempt.
  if(!save_("unknown","Interrupted print attempt; inspect label before retrying"))return;
  JsonDocument start;start["lease_token"]=lease;
  if(stopping_||ota_active_||api_("/api/agent/jobs/"+id+"/start",encode(start),response)!=200){data.reset();report_();return;}
  if(ota_active_||stopping_)return;
  status_("TLACIM NA BROTHER");uint32_t request=request_id();auto r=ipp_(BrotherIpp::printRequest(request,uri_(),id),request,data.get(),size);data.reset();
  int ipp_job=r.ok()?r.integer("job-id"):-1;
  if(ipp_job>0)save_("pending","Brother accepted job; waiting for completion",ipp_job);
  else save_("unknown","Brother submission result uncertain; no automatic resend");
  if(storage_ok_)report_();
}
void FajnyBrother::report_(){
  if(std::string(job_.outcome)=="pending"){
    status_("CAKAM NA DOKONCENIE TLACE");
    int64_t began=esp_timer_get_time();bool printed=false;
    while(job_.ipp_job&&esp_timer_get_time()-began<55000000&&!stopping_){
      auto id=request_id();auto r=ipp_(BrotherIpp::jobRequest(id,uri_(),job_.ipp_job),id);
      int state=r.integer("job-state");
      if(!r.ok())break;
      if(state==9){printed=!r.has("job-state-reasons","job-completed-with-errors")&&!r.has("job-state-reasons","job-completed-with-warnings");break;}
      if(state<3||state>6)break;vTaskDelay(pdMS_TO_TICKS(1000));
    }
    if(!save_(printed?"printed":"unknown",printed?"Brother confirmed IPP completion; inspect physical label":"Brother result uncertain; no automatic resend",job_.ipp_job))return;
  }
  JsonDocument d;d["lease_token"]=job_.lease;d["outcome"]=job_.outcome;d["message"]=job_.message;
  std::string response;int code=api_("/api/agent/jobs/"+std::string(job_.id)+"/complete",encode(d),response);
  if(code!=200){status_("VYSLEDOK CAKA NA APLIKACIU");return;}
  bool ok=std::string(job_.outcome)=="printed";
  if(clear_())status_(ok?"TLAC DOKONCENA":"TLAC NEPOTVRDENA: POZRI APLIKACIU");
}
}
