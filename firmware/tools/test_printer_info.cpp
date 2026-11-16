#include <cassert>
#include <cstring>
#include "../src/printer_info.h"
int main() {
  const uint8_t model[]={'P','1','5',0,'\r','\n'};
  assert(printerIdentity(model,sizeof(model))=="P15");
  const uint8_t firmware[]={'1','.','0','.','1','8'};
  assert(printerIdentity(firmware,sizeof(firmware))=="1.0.18");
  const uint8_t ack[]={0xaa},ok[]={'O','K'},binary[]={64},digit[]={'7'};
  assert(printerIdentity(ack,1).empty());assert(printerIdentity(ok,2).empty());
  assert(printerBatteryPercent(ack,1)==-1);assert(printerBatteryPercent(ok,2)==-1);
  assert(printerBatteryPercent(binary,1)==-1);assert(printerBatteryPercent(digit,1)==-1);
  const uint8_t ascii[]={'8','7'},percent[]={'7','%'},full[]={'1','0','0'},over[]={'1','0','1'};
  assert(printerBatteryPercent(ascii,2)==87);assert(printerBatteryPercent(percent,2)==7);
  assert(printerBatteryPercent(full,3)==100);assert(printerBatteryPercent(over,3)==-1);
  const uint8_t p15full[]={0x00,0x64},p15empty[]={0x00,0x00},p15invalid[]={0x00,0x65},p15other[]={0x01,0x64},p15half[]={0x00,0x32};
  assert(printerBatteryPercent(p15full,2)==100);
  assert(printerBatteryPercent(p15empty,2)==0);
  assert(printerBatteryPercent(p15half,2)==50);
  assert(printerBatteryPercent(p15invalid,2)==-1);
  assert(printerBatteryPercent(p15other,2)==-1);
  const uint8_t p15ready[]={0x00},unverifiedStatus[]={0x01};
  assert(std::strcmp(printerStatus(p15ready,1),"ready")==0);
  assert(std::strcmp(printerStatus(unverifiedStatus,1),"unknown")==0);
  const uint8_t status[]={0xff,2},closed[]={0xff,5},unknown[]={0xff,0};
  assert(std::strcmp(printerStatus(status,2),"cover_open")==0);
  assert(std::strcmp(printerStatus(closed,2),"cover_closed")==0);
  assert(std::strcmp(printerStatus(unknown,2),"unknown")==0);
  assert(std::strcmp(printerStatus(ok,2),"unknown")==0);
}
