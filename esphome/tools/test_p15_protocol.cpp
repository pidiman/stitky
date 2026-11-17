#include <cassert>
#include <iostream>
#include <vector>
#include "../components/fajny_brother/p15_protocol.h"
int main(){
 using FajnyP15::Transfer;
 uint8_t raster[FajnyP15::RASTER_SIZE];for(size_t i=0;i<sizeof(raster);++i)raster[i]=i%251;
 Transfer t;t.reset(raster,100);uint8_t packet[20],credits[]={1,255},aa[]={0xaa},ok[]={'O','K'};
 assert(t.packet(100,packet)==0); // No data without printer credits.
 t.notify(true,credits,2);t.notify(false,aa,1);assert(t.phase()!=Transfer::Phase::Done);
 assert(t.packet(100,packet)==19);std::vector<uint8_t> actual(packet,packet+19);t.accepted(100);
 assert(t.packet(399,packet)==0);assert(t.packet(400,packet)==20); // Initialization settling time.
 for(uint32_t now=400;t.phase()!=Transfer::Phase::Ack;now+=30){
  size_t n=t.packet(now,packet);assert(n>0&&n<=20);actual.insert(actual.end(),packet,packet+n);t.accepted(now);
  assert(t.packet(now+29,packet)==0);
 }
 assert(actual.size()==19+8+sizeof(raster)+6);
 for(size_t i=0;i<15;++i)assert(actual[i]==0);
 assert(actual[15]==0x10&&actual[16]==0xff&&actual[17]==0xf1&&actual[18]==2);
 const std::vector<uint8_t> header={0x1d,0x76,0x30,0,12,0,0x40,1};
 assert(std::vector<uint8_t>(actual.begin()+19,actual.begin()+27)==header);
 assert(std::vector<uint8_t>(actual.begin()+27,actual.begin()+27+sizeof(raster))==std::vector<uint8_t>(raster,raster+sizeof(raster)));
 assert(std::vector<uint8_t>(actual.end()-6,actual.end())==std::vector<uint8_t>({0x1d,0x0c,0x10,0xff,0xf1,0x45}));
 assert(t.phase()==Transfer::Phase::Ack&&t.percent()==100);t.notify(false,ok,2);assert(t.phase()==Transfer::Phase::Done);
 uint8_t late_fault[]={0xff,2};t.notify(false,late_fault,2);assert(t.phase()==Transfer::Phase::Failed);
 t.reset(raster,100);t.notify(true,credits,2);t.notify(false,(const uint8_t*)"BAD",3);assert(t.phase()!=Transfer::Phase::Done);
 uint8_t fault[]={0xff,2};t.notify(false,fault,2);assert(t.phase()==Transfer::Phase::Failed&&!t.sent());
 t.reset(raster,0xfffffff0);t.tick(20);assert(t.phase()!=Transfer::Phase::Failed);t.tick(50000);assert(t.phase()==Transfer::Phase::Failed);
 t.reset(raster,100);uint8_t one[]={1,1};t.notify(true,one,2);assert(t.take_credit());assert(!t.take_credit());
 std::cout<<"P15 exact frame, credits, 20-byte chunks, pacing, ACK gating, faults and timer wrap passed\n";
}
