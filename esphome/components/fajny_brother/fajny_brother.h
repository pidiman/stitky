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
#include "p15_link.h"
#ifdef USE_FPS_P15
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif

namespace esphome::fajny_brother {
// Independent release: never install the standalone esp32dev image on ESPHome.
static constexpr const char *VERSION="esphome-gw-0.2.2";
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
#ifdef USE_FPS_P15
  void set_p15_token(const std::string &v){p15_token_=v;}
  void set_p15_client(ble_client::BLEClient *v){p15_client_=v;}
  void set_p15_ble(esp32_ble::ESP32BLE *v){p15_ble_=v;}
  void set_p15_tracker(esp32_ble_tracker::ESP32BLETracker *v){p15_tracker_=v;}
  void set_p15_status_sensor(text_sensor::TextSensor *v){p15_sensor_=v;}
  void set_p15_battery(sensor::Sensor *v){p15_battery_sensor_=v;}
  void set_p15_printer_available(binary_sensor::BinarySensor *v){p15_available_sensor_=v;}
  void set_p15_printer_status(text_sensor::TextSensor *v){p15_printer_sensor_=v;}
  void set_p15_last_error(text_sensor::TextSensor *v){p15_error_sensor_=v;}
  void set_p15_last_check(text_sensor::TextSensor *v){p15_checked_sensor_=v;}
#endif
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
#ifdef USE_FPS_P15
  // Copy worker-owned diagnostics into the main ESPHome loop before publishing HA entities.
  struct P15Diagnostics {int battery=-1;bool available=false;char status[48]{},error[180]{},checked[24]{};};
  QueueHandle_t p15_diagnostics_=nullptr;
  sensor::Sensor *p15_battery_sensor_=nullptr;
  binary_sensor::BinarySensor *p15_available_sensor_=nullptr;
  text_sensor::TextSensor *p15_printer_sensor_=nullptr,*p15_error_sensor_=nullptr,*p15_checked_sensor_=nullptr;
  void publish_p15_diagnostics_();
  P15Link p15_link_;ble_client::BLEClient *p15_client_=nullptr;esp32_ble::ESP32BLE *p15_ble_=nullptr;
  esp32_ble_tracker::ESP32BLETracker *p15_tracker_=nullptr;QueueHandle_t p15_messages_=nullptr;
  text_sensor::TextSensor *p15_sensor_=nullptr;std::string p15_token_,p15_last_status_;
  Journal p15_job_;nvs_handle_t p15_nvs_=0;bool p15_pending_=false,p15_storage_ok_=false,p15_radio_ok_=true;
  bool p15_connected_=false,p15_dirty_=false,p15_refresh_=false;int p15_battery_=-1;
  std::string p15_printer_status_="unknown",p15_error_;uint32_t p15_probe_at_=0;
  bool load_p15_();bool save_p15_(const char *outcome,const char *message);bool clear_p15_();
  void claim_p15_();void report_p15_();void probe_p15_();void telemetry_p15_();
  bool run_p15_(bool print);void p15_status_(const char *text);
#endif
  bool last_refresh_=false;
  void run_();void cycle_();void telemetry_();void claim_();void report_();
  bool save_(const char *outcome,const char *message,uint32_t ipp_job=0);
  bool load_();bool clear_();void status_(const char *text);
  int api_(const std::string &path,const std::string &body,std::string &response,const std::string &token="");
  int request_(const std::string &url,const char *content_type,const std::string &prefix,
               const uint8_t *payload,size_t size,std::string &response,const std::string &token="");
  bool download_(const std::string &path,uint8_t *data,size_t size,const std::string &sha);
  BrotherIpp::Response ipp_(const std::string &prefix,uint32_t id,const uint8_t *data=nullptr,size_t size=0);
  BrotherIpp::Response printer_status_();
  std::string uri_() const{return "ipp://"+host_+"/ipp/print";}
};
}
