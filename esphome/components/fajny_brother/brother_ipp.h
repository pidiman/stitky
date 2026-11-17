#pragma once
// Small bounded IPP/1.1 codec, RFC 8010. No network or hardware dependencies.
#include <cstdint>
#include <string>
#include <vector>
#include <map>

namespace BrotherIpp {
inline void u16(std::string& s, unsigned n) { s.push_back(char(n>>8)); s.push_back(char(n)); }
inline void u32(std::string& s, uint32_t n) { for(int i=3;i>=0;--i)s.push_back(char(n>>(i*8))); }
inline void attr(std::string& s, uint8_t tag, const std::string& name, const std::string& value) {
  s.push_back(char(tag));u16(s,name.size());s+=name;u16(s,value.size());s+=value;
}
inline std::string number(uint32_t n) { std::string s;u32(s,n);return s; }
inline std::string begin(uint16_t op, uint32_t id, const std::string& uri) {
  std::string s("\x01\x01",2);u16(s,op);u32(s,id);s.push_back(1);
  attr(s,0x47,"attributes-charset","utf-8");attr(s,0x48,"attributes-natural-language","en");
  attr(s,0x45,"printer-uri",uri);return s;
}
inline std::string statusRequest(uint32_t id,const std::string& uri) {
  std::string s=begin(0x0b,id,uri);
  attr(s,0x44,"requested-attributes","printer-state");
  attr(s,0x44,"","printer-state-reasons");attr(s,0x44,"","media-ready");
  attr(s,0x44,"","document-format-supported");attr(s,0x44,"","printer-make-and-model");
  s.push_back(3);return s;
}
inline std::string printRequest(uint32_t id,const std::string& uri,const std::string& job) {
  std::string s=begin(2,id,uri);
  attr(s,0x42,"requesting-user-name","FajnyPrintStudio");
  attr(s,0x42,"job-name",job);attr(s,0x49,"document-format","application/octet-stream");
  s.push_back(3);return s;
}
inline std::string jobRequest(uint32_t id,const std::string& uri,uint32_t job) {
  std::string s=begin(9,id,uri);attr(s,0x21,"job-id",number(job));
  attr(s,0x44,"requested-attributes","job-state");attr(s,0x44,"","job-state-reasons");
  s.push_back(3);return s;
}
struct Response {
  bool valid=false;uint16_t status=0xffff;uint32_t requestId=0;
  std::map<std::string,std::vector<std::string>> values;
  bool ok() const {return valid && status<0x0100;}
  std::string text(const std::string& key) const {
    auto p=values.find(key);return p==values.end()||p->second.empty()?"":p->second[0];
  }
  int integer(const std::string& key) const {
    std::string s=text(key);if(s.size()!=4)return -1;
    uint32_t n=0;for(unsigned char c:s)n=(n<<8)|c;return n>0x7fffffff?-1:int(n);
  }
  bool has(const std::string& key,const std::string& value) const {
    auto p=values.find(key);if(p==values.end())return false;
    for(const auto& v:p->second)if(v==value)return true;return false;
  }
};
inline unsigned read16(const std::string& s,size_t i) {
  return (uint8_t(s[i])<<8)|uint8_t(s[i+1]);
}
inline Response parse(const std::string& s,uint32_t expectedId) {
  Response r;if(expectedId==0||expectedId>0x7fffffffU)return r;
  if(s.size()<9 || s.size()>16384 || (uint8_t(s[0])!=1 && uint8_t(s[0])!=2))return r;
  r.status=read16(s,2);for(size_t i=4;i<8;++i)r.requestId=(r.requestId<<8)|uint8_t(s[i]);
  if(r.requestId!=expectedId)return r;
  size_t i=8;std::string name;unsigned count=0;int collection=0;
  while(i<s.size()) {
    uint8_t tag=uint8_t(s[i++]);if(tag==3){r.valid=collection==0;return r;}
    if(tag<0x10){name.clear();continue;}
    if(i+2>s.size())return r;unsigned n=read16(s,i);i+=2;
    if(i+n+2>s.size())return r;
    std::string next=s.substr(i,n);i+=n;unsigned length=read16(s,i);i+=2;
    if(i+length>s.size() || ++count>256)return r;
    std::string value=s.substr(i,length);i+=length;
    if(tag==0x34){++collection;continue;}
    if(tag==0x37){if(collection<=0)return r;--collection;continue;}
    if(collection)continue;
    if(n)name=next;
    if(name.empty() || name.size()>128 || length>2048)return r;
    r.values[name].push_back(value);
  }
  return r;
}
inline bool mediaMatches(const std::string& media,int width,int length) {
  std::string suffix="_"+std::to_string(width)+"x"+std::to_string(length)+"mm";
  if(media.size()>=suffix.size() && media.compare(media.size()-suffix.size(),suffix.size(),suffix)==0)return true;
  // Continuous media are advertised by QL-810W as roll_current_29x0mm.
  return false;
}
}
