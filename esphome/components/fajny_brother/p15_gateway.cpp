#include "fajny_brother.h"
#ifdef USE_FPS_P15
#include "esphome/components/json/json_util.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "mbedtls/base64.h"
#include "mbedtls/sha256.h"
#include <cstring>
#include <ctime>

namespace esphome::fajny_brother {
static std::string p15_encode(const JsonDocument &d){std::string s;serializeJson(d,s);return s;}
void FajnyBrother::p15_status_(const char *message){char text[96]{};snprintf(text,sizeof(text),"%s",message);xQueueOverwrite(p15_messages_,text);}
bool FajnyBrother::load_p15_(){
  if(nvs_open("fajny-p15",NVS_READWRITE,&p15_nvs_)!=ESP_OK)return false;
  size_t n=sizeof(p15_job_);esp_err_t code=nvs_get_blob(p15_nvs_,"pending",&p15_job_,&n);
  if(code==ESP_ERR_NVS_NOT_FOUND){p15_job_=Journal{};return true;}
  if(code!=ESP_OK||n!=sizeof(p15_job_)||p15_job_.magic!=0x46424a31||!memchr(p15_job_.id,0,sizeof(p15_job_.id))||!memchr(p15_job_.lease,0,sizeof(p15_job_.lease))||!memchr(p15_job_.outcome,0,sizeof(p15_job_.outcome))||!memchr(p15_job_.message,0,sizeof(p15_job_.message))||!p15_job_.id[0]||strlen(p15_job_.lease)<16)return false;
  std::string result=p15_job_.outcome;if(result!="failed"&&result!="printed"&&result!="unknown")return false;
  p15_pending_=true;return true;
}
bool FajnyBrother::save_p15_(const char *outcome,const char *message){
  snprintf(p15_job_.outcome,sizeof(p15_job_.outcome),"%s",outcome);snprintf(p15_job_.message,sizeof(p15_job_.message),"%s",message);p15_pending_=true;
  if(nvs_set_blob(p15_nvs_,"pending",&p15_job_,sizeof(p15_job_))!=ESP_OK||nvs_commit(p15_nvs_)!=ESP_OK){p15_storage_ok_=false;p15_status_("P15: CHYBA PAMATE ULOHY");return false;}return true;
}
bool FajnyBrother::clear_p15_(){
  if(nvs_erase_key(p15_nvs_,"pending")!=ESP_OK||nvs_commit(p15_nvs_)!=ESP_OK){p15_storage_ok_=false;return false;}
  p15_pending_=false;p15_job_=Journal{};return true;
}
bool FajnyBrother::run_p15_(bool print){
  if(!p15_link_.request(print,print?p15_link_.raster_data():nullptr))return false;
  int64_t began=esp_timer_get_time();
  while(p15_link_.busy()&&esp_timer_get_time()-began<85000000&&!stopping_){
    if(ota_active_||!connected_)p15_link_.cancel();vTaskDelay(pdMS_TO_TICKS(25));
  }
  if(p15_link_.busy()){
    p15_link_.cancel();began=esp_timer_get_time();
    while(p15_link_.busy()&&esp_timer_get_time()-began<10000000&&!stopping_)vTaskDelay(pdMS_TO_TICKS(25));
  }
  if(p15_link_.busy()){
    p15_radio_ok_=false;p15_status_("P15: BLUETOOTH NEUKONCENE; RESTARTUJ ESP");return false;
  }
  return true;
}
void FajnyBrother::publish_p15_diagnostics_(){
  P15Diagnostics d;d.available=p15_connected_;d.battery=p15_connected_?p15_battery_:-1;
  const char *state=!p15_connected_?"Nedostupná":p15_printer_status_=="ready"?"Pripravená":
    p15_printer_status_=="out_of_paper"?"Chýba papier":p15_printer_status_=="cover_open"?"Otvorený kryt":
    p15_printer_status_=="overheating"?"Prehriata":p15_printer_status_=="low_battery"?"Slabá batéria":
    p15_printer_status_=="cover_closed"?"Kryt zatvorený":"Nezistený";
  snprintf(d.status,sizeof(d.status),"%s",state);
  snprintf(d.error,sizeof(d.error),"%s",!p15_connected_?"P15 pri kontrole neodpovedala":
    p15_printer_status_=="unknown"?"Nepodporovaná alebo chýbajúca odpoveď stavu":
    p15_printer_status_=="ready"||p15_printer_status_=="cover_closed"?"Žiadna":state);
  time_t now=time(nullptr);struct tm utc{};
  if(now>=1700000000&&gmtime_r(&now,&utc))strftime(d.checked,sizeof(d.checked),"%Y-%m-%dT%H:%M:%SZ",&utc);
  xQueueOverwrite(p15_diagnostics_,&d);
}
void FajnyBrother::probe_p15_(){
  if(ota_active_||stopping_||!p15_storage_ok_)return;
  p15_refresh_=false;p15_probe_at_=uint32_t(esp_timer_get_time()/1000);p15_battery_=-1;p15_printer_status_="unknown";
  bool stopped=run_p15_(false);if(!stopped)return;
  p15_connected_=p15_link_.result()==P15Link::Probed;
  if(p15_connected_){p15_battery_=p15_link_.battery();p15_printer_status_=p15_link_.printer_status();}
  p15_error_=p15_connected_?"":"P15 unavailable at last BLE check";p15_dirty_=true;
  publish_p15_diagnostics_();
  p15_status_(!p15_connected_?"P15: NEDOSTUPNA":p15_printer_status_=="ready"?"P15: PRIPRAVENA":p15_printer_status_=="unknown"?"P15: PRIPOJENA":"P15: SKONTROLUJ TLACIAREN");
  if(!ota_active_&&!stopping_)telemetry_p15_();
}
void FajnyBrother::telemetry_p15_(){
  JsonDocument d;d["firmware_version"]=VERSION;d["ota_supported"]=false;d["uptime_s"]=esp_timer_get_time()/1000000;d["free_heap"]=esp_get_free_heap_size();
  d["model"]="P15";d["printer_checked"]=p15_dirty_;
  if(p15_dirty_){d["printer_connected"]=p15_connected_;d["printer_status"]=p15_printer_status_;d["last_error"]=p15_error_;if(p15_battery_>=0)d["battery_percent"]=p15_battery_;}
  std::string response;if(api_("/api/agent/telemetry",p15_encode(d),response,p15_token_)==200)p15_dirty_=false;
}
void FajnyBrother::report_p15_(){
  JsonDocument d;d["lease_token"]=p15_job_.lease;d["outcome"]=p15_job_.outcome;d["message"]=p15_job_.message;
  std::string response;if(api_("/api/agent/jobs/"+std::string(p15_job_.id)+"/complete",p15_encode(d),response,p15_token_)!=200){p15_status_("P15: VYSLEDOK CAKA NA APLIKACIU");return;}
  bool printed=std::string(p15_job_.outcome)=="printed";bool failed=std::string(p15_job_.outcome)=="failed";
  if(clear_p15_())p15_status_(printed?"P15: TLAC DOKONCENA":failed?"P15: TLAC ZLYHALA":"P15: NEISTY VYSLEDOK; POZRI STITOK");
}
void FajnyBrother::claim_p15_(){
  if(ota_active_||stopping_||!p15_storage_ok_)return;
  std::string response;int code=api_("/api/agent/claim","{}",response,p15_token_);
  if(code==204){if(last_refresh_&&(!p15_probe_at_||uint32_t(esp_timer_get_time()/1000)-p15_probe_at_>=30000))p15_refresh_=true;return;}
  if(code!=200){p15_status_("P15: CHYBA SPOJENIA S APLIKACIOU");return;}
  std::string id,lease;bool valid=false;
  {
    JsonDocument d;if(deserializeJson(d,response)){p15_status_("P15: NEPLATNA ULOHA");return;}
    id=d["id"]|"";lease=d["lease_token"]|"";
    if(id.empty()||id.size()>64||id.find_first_not_of("0123456789abcdef-")!=std::string::npos||lease.size()<16||lease.size()>128){p15_status_("P15: NEPLATNA ULOHA");return;}
    snprintf(p15_job_.id,sizeof(p15_job_.id),"%s",id.c_str());snprintf(p15_job_.lease,sizeof(p15_job_.lease),"%s",lease.c_str());
    if(!save_p15_("unknown","Interrupted P15 attempt; never automatically resend"))return;
    const char *b64=d["raster_base64"]|"";std::string sha=d["sha256"]|"";size_t decoded=0;
    valid=d["width"].is<int>()&&d["width"]==96&&d["height"].is<int>()&&d["height"]==320&&strlen(b64)==5120&&sha.size()==64;
    if(valid)valid=mbedtls_base64_decode(p15_link_.raster_data(),FajnyP15::RASTER_SIZE,&decoded,reinterpret_cast<const uint8_t*>(b64),5120)==0&&decoded==FajnyP15::RASTER_SIZE;
    if(valid){uint8_t digest[32];char actual[65]{};valid=mbedtls_sha256(p15_link_.raster_data(),FajnyP15::RASTER_SIZE,digest,0)==0;for(unsigned i=0;i<32;++i)snprintf(actual+i*2,3,"%02x",digest[i]);valid=valid&&sha==actual;}
  }
  response.clear();response.shrink_to_fit();
  if(!valid){if(save_p15_("failed","Invalid P15 geometry, base64 or SHA256; no print sent"))report_p15_();return;}
  JsonDocument start;start["lease_token"]=lease;
  if(ota_active_||stopping_||api_("/api/agent/jobs/"+id+"/start",p15_encode(start),response,p15_token_)!=200){report_p15_();return;}
  bool stopped=run_p15_(true);if(!stopped)return; // Leave the durable uncertainty marker; do not start TLS while BLE is active.
  auto result=p15_link_.result();p15_connected_=result!=P15Link::Unavailable;p15_battery_=-1;p15_printer_status_="unknown";p15_dirty_=true;
  const char *outcome=result==P15Link::Printed?"printed":result==P15Link::Unavailable?"failed":"unknown";
  p15_error_=result==P15Link::Printed?"":result==P15Link::Unavailable?"P15 BLE unavailable; no print bytes sent":"P15 may have printed partially; inspect label before retrying";
  if(save_p15_(outcome,result==P15Link::Printed?"P15 acknowledged AA/OK after all raster bytes":"P15 BLE attempt failed or uncertain; never automatically resend"))report_p15_();
  if(!ota_active_&&!stopping_)telemetry_p15_();
}
}
#endif
