#pragma once
#include <Wire.h>
#include "oled_driver.h"
#ifndef OLED_SDA
#define OLED_SDA 21
#endif
#ifndef OLED_SCL
#define OLED_SCL 22
#endif
static_assert(OLED_SDA!=OLED_SCL&&OLED_SDA!=LED_PIN&&OLED_SCL!=LED_PIN,"OLED pins must not overlap each other or the status LED");
FpsOled::Model oledModel;
FpsOled::Driver<TwoWire> oledDisplay(Wire);
bool oledServerKnown=false,oledBrotherKnown=false,oledBrotherReachable=false,oledBrotherReady=false;
int oledBrotherWidth=0;
unsigned long oledLastDraw=0,oledLastAction=0;
void oledTick(bool force=false){
  if(!oledDisplay.ready())return;
  unsigned long now=millis();if(!force&&uint32_t(now-oledLastDraw)<500)return;oledLastDraw=now;
  FpsOled::Facts f;f.version=FIRMWARE_VERSION;f.portal=portalActive;f.wifi=WiFi.status()==WL_CONNECTED;
  if(f.wifi){f.ip=WiFi.localIP().toString().c_str();f.rssi=WiFi.RSSI();}
  f.server=oledServerKnown;f.p15Known=probeAttempted;f.p15Connected=lastProbeConnected;
  f.brotherKnown=oledBrotherKnown;f.brotherReachable=oledBrotherReachable;f.brotherReady=oledBrotherReady;f.brotherWidth=oledBrotherWidth;
  f.uptime=millis()/1000;f.heap=ESP.getFreeHeap();
  bool background=FpsOled::background(oledModel.state())||oledModel.state()==FpsOled::State::BrotherCheck;
  bool idle=background&&uint32_t(now-oledLastAction)>=60000;
  if(!oledDisplay.draw(oledModel.lines(now,f),(now/60000)%2,idle))Serial.println("OLED OFFLINE; printing continues");
}
void oledShow(FpsOled::State state,const char* detail="",unsigned long hold=0){
  if(oledModel.set(state,detail,millis(),hold)){
    if(!FpsOled::background(state)&&state!=FpsOled::State::BrotherCheck)oledLastAction=millis();
    oledTick(true);
  }
}
void oledProgress(size_t done,size_t total){oledModel.progress(done,total);oledTick();}
void oledResult(const char* printer,const String& outcome){
  if(outcome!="printed"&&oledModel.state()==FpsOled::State::Error)return;
  String text=String(printer)+(outcome=="printed"?": POTVRDENE OK":outcome=="failed"?": TLAC ZLYHALA":": NEISTY VYSLEDOK");
  oledShow(outcome=="printed"?FpsOled::State::Result:FpsOled::State::Error,text.c_str(),outcome=="printed"?3500:8000);
}
void oledStatus(){Serial.printf("OLED STATUS connected=%d address=0x%02x sda=%d scl=%d size=128x32\n",oledDisplay.ready(),oledDisplay.address(),OLED_SDA,OLED_SCL);}
void oledBegin(){oledDisplay.begin(OLED_SDA,OLED_SCL);oledTick(true);oledStatus();}
void oledBrotherStatus(bool reachable,bool idle,const std::string& media){
  oledBrotherKnown=true;oledBrotherReachable=reachable;oledBrotherReady=idle;oledBrotherWidth=0;
  size_t pos=media.rfind('_');if(reachable&&pos!=std::string::npos){int width=atoi(media.c_str()+pos+1);if(width>=12&&width<=62)oledBrotherWidth=width;}
}
