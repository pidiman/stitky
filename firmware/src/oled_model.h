#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <string>

namespace FpsOled {
enum class State {Boot,Wifi,Clock,Portal,Server,Ready,P15Connect,P15Info,P15Print,BrotherDownload,BrotherCheck,BrotherPrint,Result,Ota,Error};
using Lines=std::array<std::string,4>;
struct Facts {
  std::string version,ip;
  bool wifi=false,portal=false,server=false,p15Known=false,p15Connected=false,brotherKnown=false,brotherReachable=false,brotherReady=false;
  int rssi=0,brotherWidth=0;uint32_t uptime=0,heap=0;
};
inline std::string fit(std::string value){
  for(char& c:value){if(c>='a'&&c<='z')c-=32;else if(static_cast<unsigned char>(c)<32||static_cast<unsigned char>(c)>126)c='?';}
  if(value.size()>21)value=value.substr(0,18)+"...";return value;
}
inline const char* title(State state){
  switch(state){
    case State::Boot:return "STARTUJEM";case State::Wifi:return "PRIPAJAM WI-FI";
    case State::Clock:return "NASTAVUJEM CAS";case State::Portal:return "NASTAVENIE WI-FI";
    case State::Server:return "KOMUNIKUJEM S API";case State::Ready:return "PRIPRAVENE";
    case State::P15Connect:return "PRIPAJAM P15";case State::P15Info:return "CITAM UDAJE P15";
    case State::P15Print:return "TLACIM NA P15";case State::BrotherDownload:return "PREBERAM STITOK BR";
    case State::BrotherCheck:return "KONTROLUJEM BROTHER";case State::BrotherPrint:return "TLACIM NA BROTHER";
    case State::Result:return "VYSLEDOK TLACE";case State::Ota:return "AKTUALIZUJEM ESP32";
    case State::Error:return "CHYBA";
  }return "";
}
inline bool background(State state){return state==State::Ready||state==State::Server;}
class Model {
  State state_=State::Boot;std::string detail_="KONTROLA NASTAVENI";
  uint32_t changed_=0,hold_=0;int progress_=-1;std::string lastPrinter_;
 public:
  State state()const{return state_;}
  uint32_t changed()const{return changed_;}
  bool set(State state,const std::string& detail,uint32_t now,uint32_t hold=0){
    if(background(state)&&hold_&&uint32_t(now-changed_)<hold_)return false;
    std::string clipped=fit(detail);
    if(state==state_&&detail_==clipped)return false;
    if(state==State::P15Connect||state==State::P15Info||state==State::P15Print)lastPrinter_="P15";
    if(state==State::BrotherDownload||state==State::BrotherCheck||state==State::BrotherPrint)lastPrinter_="BROTHER";
    state_=state;detail_=clipped;changed_=now;hold_=hold;progress_=-1;return true;
  }
  void progress(size_t done,size_t total){progress_=total?int(std::min<uint64_t>(100,uint64_t(done)*100/total)):-1;}
  Lines lines(uint32_t /*now*/,const Facts& f)const{
    State visible=state_;std::string detail=detail_;
    if(f.portal){visible=State::Portal;detail="OTVOR 192.168.4.1";}
    else if(!f.wifi&&background(visible)){visible=State::Wifi;detail="CAKAM NA SIET";}
    // Keep a full blank row between the fixed header and the two essential rows.
    if(visible==State::Ready&&detail.empty())detail=lastPrinter_;
    Lines rows={fit("FAJNY PRINT "+f.version),"",title(visible),detail};
    if(progress_>=0&&(visible==State::Ota||visible==State::P15Print||visible==State::BrotherPrint||visible==State::BrotherDownload)){
      char p[22];std::snprintf(p,sizeof(p),"PRENOS: %d%%",progress_);rows[3]=p;
    }
    for(auto& row:rows)row=fit(row);return rows;
  }
};
}
