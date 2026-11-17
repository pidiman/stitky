#include "p15_link.h"
#ifdef USE_FPS_P15
#include "printer_info.h"
#include "esphome/core/hal.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include <cstdio>

namespace esphome::fajny_brother {
void P15Link::configure(ble_client::BLEClient *client,esp32_ble::ESP32BLE *ble,esp32_ble_tracker::ESP32BLETracker *tracker,QueueHandle_t messages){
  set_ble_client_parent(client);client->register_ble_node(this);client->set_auto_connect(false);ble_=ble;tracker_=tracker;messages_=messages;
}
void P15Link::status_(const char *message){char text[96]{};snprintf(text,sizeof(text),"%s",message);xQueueOverwrite(messages_,text);}
bool P15Link::request(bool print,const uint8_t *raster){
  if(busy())return false;if(print&&raster==nullptr)return false;
  if(print&&raster!=raster_.data())memcpy(raster_.data(),raster,raster_.size());
  cancel_=false;done_.store(false,std::memory_order_release);command_.store(print?2:1,std::memory_order_release);return true;
}
void P15Link::finish_(Result result){
  if(stage_==Disconnect||stage_==Disable||stage_==Idle)return;
  result_=result;parent()->set_auto_connect(false);tracker_->stop_scan();parent()->set_enabled(false);
  stage_=Disconnect;stage_at_=millis();
}
bool P15Link::query_(const uint8_t *data,size_t size){
  if(!transfer_.take_credit())return false;
  reply_size_=0;query_data_at_=millis();
  if(esp_ble_gattc_write_char(parent()->get_gattc_if(),parent()->get_conn_id(),tx_,size,const_cast<uint8_t*>(data),ESP_GATT_WRITE_TYPE_NO_RSP,ESP_GATT_AUTH_REQ_NONE)!=ESP_OK){link_error_=true;return false;}return true;
}
void P15Link::tick(bool cancel){
  uint32_t now=millis();int command=command_.exchange(0,std::memory_order_acquire);
  if(command){
    printing_=command==2;battery_=-1;printer_status_="unknown";result_=Unavailable;link_error_=false;disconnected_=false;
    tx_=rx_=cx_=rx_desc_=cx_desc_=0;registrations_=descriptors_=0;last_percent_=101;
    transfer_.reset(raster_.data(),now);began_=stage_at_=now;stage_=Enable;ble_->enable();status_("P15: ZAPINAM BLUETOOTH");
  }
  if(stage_==Idle)return;
  if(stage_!=Disconnect&&stage_!=Disable&&(cancel||cancel_||link_error_||disconnected_||uint32_t(now-began_)>70000)){
    finish_(printing_&&transfer_.sent()?Uncertain:Unavailable);
  }
  switch(stage_){
    case Enable:
      if(ble_->is_active()&&parent()->get_gattc_if()!=ESP_GATT_IF_NONE){
        parent()->set_enabled(true);parent()->set_auto_connect(true);tracker_->start_scan();stage_=Connect;stage_at_=now;status_("P15: HLADAM TLACIAREN");
      }else if(uint32_t(now-stage_at_)>10000)finish_(Unavailable);
      break;
    case Connect:
      if(registrations_==3&&descriptors_==3&&transfer_.has_credit()){
        tracker_->stop_scan();stage_=printing_?Print:QueryBattery;stage_at_=now;transfer_.start_clock(now);status_(printing_?"P15: TLACIM":"P15: CITAM STAV A BATERIU");
      }else if(uint32_t(now-stage_at_)>18000)finish_(Unavailable);
      break;
    case Print: {
      transfer_.tick(now);uint8_t data[20];size_t size=transfer_.packet(now,data);
      if(size){
        esp_err_t sent=esp_ble_gattc_write_char(parent()->get_gattc_if(),parent()->get_conn_id(),tx_,size,data,ESP_GATT_WRITE_TYPE_NO_RSP,ESP_GATT_AUTH_REQ_NONE);
        if(sent==ESP_OK)transfer_.accepted(now);else transfer_.fail();
        unsigned percent=transfer_.percent()/10*10;
        if(percent!=last_percent_){char text[64];snprintf(text,sizeof(text),"P15: PRENOS %u%%",percent);status_(text);last_percent_=percent;}
      }
      if(transfer_.phase()==FajnyP15::Transfer::Phase::Done)finish_(Printed);
      else if(transfer_.phase()==FajnyP15::Transfer::Phase::Failed)finish_(transfer_.sent()?Uncertain:Unavailable);
      break;
    }
    case QueryBattery:{const uint8_t cmd[]={0x10,0xff,0x50,0xf1};if(query_(cmd,sizeof(cmd))){stage_=WaitBattery;stage_at_=now;}else if(uint32_t(now-stage_at_)>2000)stage_=QueryStatus;break;}
    case WaitBattery:
      if((reply_size_&&uint32_t(now-query_data_at_)>=150)||uint32_t(now-stage_at_)>2000){battery_=printerBatteryPercent(reply_,reply_size_);stage_=QueryStatus;stage_at_=now;}
      break;
    case QueryStatus:{const uint8_t cmd[]={0x10,0xff,0x40};if(query_(cmd,sizeof(cmd))){stage_=WaitStatus;stage_at_=now;}else if(uint32_t(now-stage_at_)>2000)finish_(Probed);break;}
    case WaitStatus:
      if((reply_size_&&uint32_t(now-query_data_at_)>=150)||uint32_t(now-stage_at_)>2000){printer_status_=printerStatus(reply_,reply_size_);finish_(Probed);}
      break;
    case Disconnect:
      if(parent()->state()==esp32_ble_tracker::ClientState::IDLE||uint32_t(now-stage_at_)>1500){ble_->disable();stage_=Disable;stage_at_=now;}
      break;
    case Disable:
      // is_active() becomes false before teardown; wait for actual heap-owning stacks to stop.
      if(esp_bluedroid_get_status()==ESP_BLUEDROID_STATUS_UNINITIALIZED&&esp_bt_controller_get_status()==ESP_BT_CONTROLLER_STATUS_IDLE){stage_=Idle;done_.store(true,std::memory_order_release);}
      break;
    default:break;
  }
}
void P15Link::gattc_event_handler(esp_gattc_cb_event_t event,esp_gatt_if_t,esp_ble_gattc_cb_param_t *p){
  if(stage_==Idle||stage_==Disable)return;
  switch(event){
    case ESP_GATTC_SEARCH_CMPL_EVT:{
      auto *tx=parent()->get_characteristic(0xff00,0xff02),*rx=parent()->get_characteristic(0xff00,0xff01),*cx=parent()->get_characteristic(0xff00,0xff03);
      if(p->search_cmpl.status!=ESP_GATT_OK||!tx||!rx||!cx||!(tx->properties&ESP_GATT_CHAR_PROP_BIT_WRITE_NR)||!(rx->properties&ESP_GATT_CHAR_PROP_BIT_NOTIFY)||!(cx->properties&ESP_GATT_CHAR_PROP_BIT_NOTIFY)){link_error_=true;break;}
      tx_=tx->handle;rx_=rx->handle;cx_=cx->handle;
      auto *rd=parent()->get_config_descriptor(rx_),*cd=parent()->get_config_descriptor(cx_);
      if(!rd||!cd){link_error_=true;break;}rx_desc_=rd->handle;cx_desc_=cd->handle;
      if(parent()->register_for_notify(rx_)!=ESP_OK||parent()->register_for_notify(cx_)!=ESP_OK)link_error_=true;
      break;
    }
    case ESP_GATTC_REG_FOR_NOTIFY_EVT:
      if(p->reg_for_notify.status!=ESP_GATT_OK){link_error_=true;break;}
      if(p->reg_for_notify.handle==rx_)registrations_|=1;if(p->reg_for_notify.handle==cx_)registrations_|=2;
      if(registrations_==3)node_state=esp32_ble_tracker::ClientState::ESTABLISHED;
      break;
    case ESP_GATTC_WRITE_DESCR_EVT:
      if(p->write.status!=ESP_GATT_OK){link_error_=true;break;}
      if(p->write.handle==rx_desc_)descriptors_|=1;if(p->write.handle==cx_desc_)descriptors_|=2;
      break;
    case ESP_GATTC_NOTIFY_EVT:{
      if(p->notify.handle!=rx_&&p->notify.handle!=cx_)break;
      bool control=p->notify.handle==cx_;const uint8_t *data=p->notify.value;size_t n=p->notify.value_len;
      transfer_.notify(control,data,n);
      if((stage_==WaitBattery||stage_==WaitStatus)&&n&&!(control&&n>=2&&(data[0]==1||data[0]==2))){
        size_t copy=std::min(n,sizeof(reply_)-reply_size_);memcpy(reply_+reply_size_,data,copy);reply_size_+=copy;query_data_at_=millis();
      }
      break;
    }
    case ESP_GATTC_CLOSE_EVT:case ESP_GATTC_DISCONNECT_EVT:disconnected_=true;break;
    default:break;
  }
}
}
#endif
