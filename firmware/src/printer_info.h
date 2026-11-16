#pragma once
#include <cstdint>
#include <cstddef>
#include <string>

// Conservative parsers for informational replies. They never infer a battery
// percentage from an undocumented binary frame, ACK, or missing response.
// Physical P15 capture: battery 00 64 = status byte 00 + 100 percent;
// status query 00 = no reported error. Other binary formats remain unknown.
inline std::string printerIdentity(const uint8_t* bytes,size_t length) {
  std::string value;
  for(size_t i=0;i<length;++i) {
    uint8_t c=bytes[i];
    if(c==0)continue;
    if(c=='\r'||c=='\n'||c=='\t')c=' ';
    if(c<32||c>126)return {};
    value.push_back(static_cast<char>(c));
    if(value.size()>80)return {};
  }
  size_t first=value.find_first_not_of(' ');
  if(first==std::string::npos)return {};
  value=value.substr(first,value.find_last_not_of(' ')-first+1);
  if(value=="OK"||value=="O"||value=="K")return {};
  return value;
}
inline int printerBatteryPercent(const uint8_t* bytes,size_t length) {
  if(length==2 && bytes[0]==0x00)return bytes[1]<=100?bytes[1]:-1;
  std::string value=printerIdentity(bytes,length);
  if(value.empty())return -1;
  bool percent=value.back()=='%';
  if(percent)value.pop_back();
  // A lone ASCII digit could just be an undocumented raw binary percentage.
  if(value.empty()||value.size()>3||(!percent&&value.size()<2))return -1;
  int result=0;
  for(char c:value){if(c<'0'||c>'9')return -1;result=result*10+(c-'0');}
  return result<=100?result:-1;
}
inline const char* printerStatus(const uint8_t* bytes,size_t length) {
  if(length==1 && bytes[0]==0x00)return "ready";
  if(length!=2||bytes[0]!=0xff)return "unknown";
  switch(bytes[1]) {
    case 1:return "out_of_paper";
    case 2:return "cover_open";
    case 3:return "overheating";
    case 4:return "low_battery";
    case 5:return "cover_closed";
    default:return "unknown";
  }
}
