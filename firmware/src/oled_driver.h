#pragma once
#include <array>
#include <cstdint>
#include <cstring>
#include "oled_model.h"
#include "oled_font.h"

namespace FpsOled {
using Frame=std::array<uint8_t,512>;
inline Frame raster(const Lines& lines,bool shift=false){
  Frame frame={};
  for(unsigned line=0;line<4;++line){
    std::string text=fit(lines[line]);
    for(size_t n=0;n<text.size();++n){
      const uint8_t* rows=glyph(text[n]);
      for(unsigned y=0;y<7;++y)for(unsigned x=0;x<5;++x)if(rows[y]&(1U<<(4-x))){
        unsigned px=unsigned(n)*6+x+(shift?1:0),py=line*8+y+(shift?1:0);
        if(px<128&&py<32)frame[(py/8)*128+px]|=1U<<(py%8);
      }
    }
  }return frame;
}
// Tiny SSD1306 I2C-only driver. A failed/absent display never blocks printing.
template<class Bus> class Driver {
  Bus& bus;uint8_t address_=0;bool ready_=false;int contrast_=-1;
  Frame last_={};bool sent_=false;
  bool send(uint8_t control,const uint8_t* data,size_t length){
    bus.beginTransmission(address_);bool written=bus.write(control)==1;
    for(size_t i=0;i<length;++i)written=(bus.write(data[i])==1)&&written;
    if(bus.endTransmission()!=0||!written){ready_=false;return false;}return true;
  }
 public:
  explicit Driver(Bus& b):bus(b){}
  bool ready()const{return ready_;}uint8_t address()const{return address_;}
  bool begin(int sda=21,int scl=22){
    ready_=false;sent_=false;contrast_=-1;address_=0;
    if(!bus.begin(sda,scl,100000))return false;
    bus.setTimeOut(15);
    for(uint8_t a:{uint8_t(0x3c),uint8_t(0x3d)}){
      bus.beginTransmission(a);if(bus.endTransmission()==0){address_=a;break;}
    }
    if(!address_)return false;
    static const uint8_t init[]={0xae,0xd5,0x80,0xa8,0x1f,0xd3,0x00,0x40,0x8d,0x14,0x20,0x00,0xa1,0xc8,0xda,0x02,0x81,0x40,0xd9,0xf1,0xdb,0x40,0xa4,0xa6,0x2e,0xaf};
    ready_=true;if(!send(0x00,init,sizeof(init)))return false;
    contrast_=0x40;return true;
  }
  bool draw(const Lines& lines,bool shift=false,bool dim=false){
    if(!ready_)return false;
    int contrast=dim?0x10:0x40;
    if(contrast!=contrast_){uint8_t c[]={0x81,uint8_t(contrast)};if(!send(0,c,2))return false;contrast_=contrast;}
    Frame frame=raster(lines,shift);
    if(sent_&&frame==last_)return true;
    static const uint8_t position[]={0x21,0,127,0x22,0,3};
    if(!send(0,position,sizeof(position)))return false;
    for(size_t i=0;i<frame.size();i+=16)if(!send(0x40,frame.data()+i,16))return false;
    last_=frame;sent_=true;return true;
  }
};
}
