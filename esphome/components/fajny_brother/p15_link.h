#pragma once
#include "esphome/core/defines.h"
#ifdef USE_FPS_P15
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/esp32_ble/ble.h"
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"
#include "freertos/queue.h"
#include "p15_protocol.h"
#include <atomic>

namespace esphome::fajny_brother {
class P15Link : public ble_client::BLEClientNode {
 public:
  enum Result {Unavailable=1,Uncertain=2,Printed=3,Probed=4};
  void configure(ble_client::BLEClient *client,esp32_ble::ESP32BLE *ble,esp32_ble_tracker::ESP32BLETracker *tracker,QueueHandle_t messages);
  bool request(bool print,const uint8_t *raster=nullptr);
  uint8_t *raster_data(){return raster_.data();}
  void tick(bool cancel);
  bool busy()const{return !done_.load(std::memory_order_acquire);}
  Result result()const{return result_;}
  void cancel(){cancel_=true;}
  int battery()const{return battery_;}
  const char *printer_status()const{return printer_status_;}
  void gattc_event_handler(esp_gattc_cb_event_t event,esp_gatt_if_t gattc_if,esp_ble_gattc_cb_param_t *param) override;
 protected:
  enum Stage {Idle,Enable,Connect,Print,QueryBattery,WaitBattery,QueryStatus,WaitStatus,Settle,Disconnect,Disable};
  Stage stage_=Idle;esp32_ble::ESP32BLE *ble_=nullptr;esp32_ble_tracker::ESP32BLETracker *tracker_=nullptr;QueueHandle_t messages_=nullptr;
  std::atomic<bool> done_{true},cancel_{false};std::atomic<int> command_{0};
  Result result_=Unavailable;bool printing_=false,link_error_=false,disconnected_=false;
  uint32_t began_=0,stage_at_=0,query_data_at_=0;unsigned last_percent_=101;
  uint16_t tx_=0,rx_=0,cx_=0,rx_desc_=0,cx_desc_=0;uint8_t registrations_=0,descriptors_=0;
  std::array<uint8_t,FajnyP15::RASTER_SIZE> raster_{};FajnyP15::Transfer transfer_;
  uint8_t reply_[32]{};size_t reply_size_=0;int battery_=-1;const char *printer_status_="unknown";
  void finish_(Result result);void status_(const char *message);bool query_(const uint8_t *data,size_t size);
};
}
#endif
