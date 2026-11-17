#include <cassert>
#include <fstream>
#include <iostream>
#include <vector>
#include "../src/oled_driver.h"
struct Bus {
  uint8_t present=0x3c,address=0;bool fail=false,shortWrite=false;int sda=-1,scl=-1,timeout=0;uint32_t frequency=0;
  std::vector<uint8_t> pending;std::vector<std::vector<uint8_t>> writes;
  bool begin(int a,int b,uint32_t hz){sda=a;scl=b;frequency=hz;return true;}
  void setTimeOut(int ms){timeout=ms;}
  void beginTransmission(uint8_t a){address=a;pending.clear();}
  size_t write(uint8_t b){pending.push_back(b);return shortWrite?0:1;}
  int endTransmission(){writes.push_back(pending);return fail||address!=present?2:0;}
};
int main(int argc,char** argv){
  using namespace FpsOled;
  Facts facts;facts.version="2.1.1";facts.wifi=true;facts.ip="192.0.2.10";facts.server=true;facts.rssi=-61;facts.heap=140*1024;facts.uptime=600;
  facts.p15Known=true;facts.p15Connected=false;facts.brotherKnown=true;facts.brotherReachable=true;facts.brotherReady=true;facts.brotherWidth=29;
  Model model;model.set(State::Ready,"",1000);
  auto idle=model.lines(1000,facts);
  assert(idle[0]=="FAJNY PRINT 2.1.1"&&idle[1].empty()&&idle[2]=="PRIPRAVENE"&&idle[3].empty());
  assert(model.lines(6000,facts)==idle&&model.lines(11000,facts)==idle); // No rotating diagnostics.
  model.set(State::BrotherPrint,"CAKAM NA DOKONCENIE",11000);
  model.set(State::Ready,"",11001);assert(model.lines(11001,facts)[3]=="BROTHER");
  model.set(State::P15Print,"",11002);model.set(State::Ready,"",11003);assert(model.lines(11003,facts)[3]=="P15");
  facts.wifi=false;assert(model.lines(11004,facts)[2]=="PRIPAJAM WI-FI");
  facts.portal=true;assert(model.lines(11004,facts)[1].empty());assert(model.lines(11004,facts)[2]=="NASTAVENIE WI-FI");assert(model.lines(11004,facts)[3]=="OTVOR 192.168.4.1");
  facts.portal=false;facts.wifi=true;
  model.set(State::Error,"P15: NEDOSTUPNA",12000,8000);
  assert(!model.set(State::Ready,"",12001));assert(!model.set(State::Server,"KONTROLA",13000));
  assert(model.set(State::BrotherPrint,"ODOSIELAM RASTER",14000)); // New foreground work is never hidden by a previous error.
  model.progress(123,250);assert(model.lines(14000,facts)[3]=="PRENOS: 49%");
  model.progress(500,250);assert(model.lines(14000,facts)[3]=="PRENOS: 100%");
  model.set(State::Result,"BR: POTVRDENE OK",15000,3500);
  assert(!model.set(State::Server,"KONTROLA",17000));assert(model.set(State::Ready,"",18500));
  model.set(State::Error,"NVS",0xfffffff0U,100);
  assert(!model.set(State::Ready,"",20));assert(model.set(State::Ready,"",100));
  for(auto state:{State::Boot,State::Wifi,State::Clock,State::Portal,State::Server,State::Ready,State::P15Connect,State::P15Info,State::P15Print,State::BrotherDownload,State::BrotherCheck,State::BrotherPrint,State::Result,State::Ota,State::Error}){
    model.set(state,std::string(80,'x'),20000);
    auto lines=model.lines(20000,facts);assert(lines[1].empty());for(const auto& line:lines)assert(line.size()<=21);
    auto frame=raster(lines,true);assert(frame.size()==512);
  }
  auto pixels=raster({"A","","",""});
  assert(pixels[0]==0x7e&&pixels[1]==9&&pixels[2]==9&&pixels[3]==9&&pixels[4]==0x7e);
  for(size_t i=5;i<pixels.size();++i)assert(pixels[i]==0);
  auto shifted=raster({"A","","",""},true);assert(shifted[0]==0&&shifted[1]==0xfc);
  Bus bus;bus.present=0x3d;Driver<Bus> driver(bus);assert(driver.begin());
  assert(driver.address()==0x3d&&bus.sda==21&&bus.scl==22&&bus.frequency==100000&&bus.timeout==15);
  assert(bus.writes.back()[0]==0);bool mux=false;
  for(size_t i=1;i+1<bus.writes.back().size();++i)if(bus.writes.back()[i]==0xa8&&bus.writes.back()[i+1]==31)mux=true;
  assert(mux);
  Lines lines={"FAJNY PRINT 2.1.1","","TLACIM NA BROTHER","PRENOS: 42%"};
  size_t before=bus.writes.size();assert(driver.draw(lines));assert(bus.writes.size()==before+33);
  size_t bytes=0;for(size_t i=before+1;i<bus.writes.size();++i){assert(bus.writes[i].size()==17&&bus.writes[i][0]==0x40);bytes+=bus.writes[i].size()-1;}assert(bytes==512);
  before=bus.writes.size();assert(driver.draw(lines));assert(bus.writes.size()==before);
  assert(driver.draw(lines,false,true));assert(bus.writes.size()==before+1&&bus.writes.back()[1]==0x81&&bus.writes.back()[2]==0x10);
  bus.fail=true;assert(!driver.draw(lines,true));assert(!driver.ready());before=bus.writes.size();assert(!driver.draw(lines));assert(bus.writes.size()==before);
  Bus absent;absent.present=0;Driver<Bus> missing(absent);assert(!missing.begin());before=absent.writes.size();assert(!missing.draw(lines));assert(absent.writes.size()==before);
  Bus shortBus;shortBus.shortWrite=true;Driver<Bus> shortDriver(shortBus);assert(!shortDriver.begin());
  if(argc==2){
    std::ofstream out(argv[1]);out<<"P1\n128 32\n";auto frame=raster(lines);
    for(unsigned y=0;y<32;++y){for(unsigned x=0;x<128;++x)out<<((frame[y/8*128+x]>>(y%8))&1)<<' ';out<<'\n';}
  }
  std::cout<<"OLED states, priorities, timer wrap, 128x32 raster, I2C packets and absent/faulty display passed\n";
}
