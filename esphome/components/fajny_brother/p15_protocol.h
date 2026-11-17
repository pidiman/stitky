#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>

namespace FajnyP15 {
constexpr size_t RASTER_SIZE=3840;
// Pure transport policy shared by the ESPHome state machine and host tests.
class Transfer {
 public:
  enum class Phase {Preamble,Gap,Data,Ack,Done,Failed};
  void reset(const uint8_t *raster,uint32_t now){raster_=raster;phase_=Phase::Preamble;credits_=0;offset_=0;pending_=0;began_=now;last_=now-30;sent_=false;fault_=false;}
  void start_clock(uint32_t now){began_=now;}
  void notify(bool control,const uint8_t *data,size_t n){
    if(!n)return;
    if(control&&n>=2&&data[0]==1)credits_=std::min(256,credits_+int(data[1]));
    if(n>=2&&data[0]==0xff&&data[1]>=1&&data[1]<=4){fault_=true;phase_=Phase::Failed;}
    if(phase_==Phase::Ack&&((n==1&&data[0]==0xaa)||(n==2&&data[0]=='O'&&data[1]=='K')))phase_=Phase::Done;
  }
  bool take_credit(){if(credits_<=0)return false;--credits_;return true;}
  bool has_credit()const{return credits_>0;}
  size_t packet(uint32_t now,uint8_t out[20]){
    if(phase_==Phase::Gap&&uint32_t(now-last_)>=300){phase_=Phase::Data;offset_=0;}
    if((phase_!=Phase::Preamble&&phase_!=Phase::Data)||!has_credit()||uint32_t(now-last_)<30)return 0;
    const size_t total=phase_==Phase::Preamble?19:RASTER_SIZE+14;
    pending_=std::min(size_t(20),total-offset_);
    for(size_t i=0;i<pending_;++i)out[i]=byte_(offset_+i);return pending_;
  }
  void accepted(uint32_t now){
    if(!pending_||!take_credit())return;
    offset_+=pending_;pending_=0;last_=now;sent_=true;
    if(phase_==Phase::Preamble){phase_=Phase::Gap;offset_=0;}
    else if(phase_==Phase::Data&&offset_==RASTER_SIZE+14)phase_=Phase::Ack;
  }
  void tick(uint32_t now){if(phase_!=Phase::Done&&(fault_||uint32_t(now-began_)>45000||(phase_==Phase::Ack&&uint32_t(now-last_)>15000)))phase_=Phase::Failed;}
  void fail(){phase_=Phase::Failed;}
  Phase phase()const{return phase_;}bool sent()const{return sent_;}
  unsigned percent()const{return phase_==Phase::Data?unsigned(offset_*100/(RASTER_SIZE+14)):(phase_==Phase::Ack||phase_==Phase::Done)?100:0;}
 private:
  uint8_t byte_(size_t n)const{
    static constexpr uint8_t header[]={0x1d,0x76,0x30,0,12,0,0x40,0x01};
    static constexpr uint8_t ending[]={0x1d,0x0c,0x10,0xff,0xf1,0x45};
    if(phase_==Phase::Preamble)return n==15?0x10:n==16?0xff:n==17?0xf1:n==18?2:0;
    return n<8?header[n]:n<8+RASTER_SIZE?raster_[n-8]:ending[n-8-RASTER_SIZE];
  }
  const uint8_t *raster_=nullptr;Phase phase_=Phase::Failed;int credits_=0;
  size_t offset_=0,pending_=0;uint32_t began_=0,last_=0;bool sent_=false,fault_=false;
};
}
