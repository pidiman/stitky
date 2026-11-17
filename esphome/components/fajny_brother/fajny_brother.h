#pragma once
#include "esphome/core/component.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <atomic>
#include <string>
#include "nvs.h"
#include "esphome/components/ota/ota_backend.h"
#include "brother_ipp.h"

namespace esphome::fajny_brother {
// Independent release: never install the standalone esp32dev image on ESPHome.
static constexpr const char *VERSION="esphome-br-0.1.0";
class FajnyBrother : public Component, public ota::OTAGlobalStateListener {
 public:
  void set_api_url(const std::string &v){api_url_=v;}
  void set_agent_token(const std::string &v){token_=v;}
  void set_printer_host(const std::string &v){host_=v;}
  void set_max_payload(size_t v){max_payload_=v;}
  void set_status_sensor(text_sensor::TextSensor *v){sensor_=v;}
  void on_ota_global_state(ota::OTAState state,float,uint8_t,ota::OTAComponent*) override {
    if(state==ota::OTA_STARTED)ota_active_=true;
    else if(state==ota::OTA_ERROR||state==ota::OTA_ABORT)ota_active_=false;
  }
  void setup() override;
  void loop() override;
  void dump_config() override;
  void on_shutdown() override { stopping_=true; }
 protected:
  struct Journal {
    uint32_t magic=0x46424a31,ipp_job=0;
    char id[65]{},lease[129]{},outcome[9]{},message[180]{};
  } job_;
  std::string api_url_,token_,host_,last_status_;
  size_t max_payload_=131072;
  text_sensor::TextSensor *sensor_=nullptr;
  QueueHandle_t messages_=nullptr;TaskHandle_t task_=nullptr;
  std::atomic<bool> connected_{false},stopping_{false},ota_active_{false};
  nvs_handle_t nvs_=0;bool pending_=false,storage_ok_=false;
  static void task_entry_(void *arg);
  void run_();void cycle_();void telemetry_();void claim_();void report_();
  bool save_(const char *outcome,const char *message,uint32_t ipp_job=0);
  bool load_();bool clear_();void status_(const char *text);
  int api_(const std::string &path,const std::string &body,std::string &response);
  int request_(const std::string &url,const char *content_type,const std::string &prefix,
               const uint8_t *payload,size_t size,std::string &response);
  bool download_(const std::string &path,uint8_t *data,size_t size,const std::string &sha);
  BrotherIpp::Response ipp_(const std::string &prefix,uint32_t id,const uint8_t *data=nullptr,size_t size=0);
  BrotherIpp::Response printer_status_();
  std::string uri_() const{return "ipp://"+host_+"/ipp/print";}
};
}
