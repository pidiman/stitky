#pragma once
#include <algorithm>
#include <cstring>
#include <string>

// Stream and File are provided by Arduino/FS (or the native transport test).
class BrotherBodyStream: public Stream {
  const std::string& prefix;File& file;size_t position=0,delivered=0,total;
  void (*progress)(size_t,size_t);
  void report(size_t count){delivered+=count;if(count&&progress)progress(delivered,total);}
 public:
  BrotherBodyStream(const std::string& p,File& f,void (*callback)(size_t,size_t)=nullptr):prefix(p),file(f),total(p.size()+std::max(0,f.available())),progress(callback){}
  int available() override {return int(prefix.size()-position)+file.available();}
  int read() override {int value=position<prefix.size()?int(uint8_t(prefix[position++])):file.read();if(value>=0)report(1);return value;}
  int peek() override {return position<prefix.size()?uint8_t(prefix[position]):file.peek();}
  void flush() override {}
  size_t write(uint8_t) override {return 0;}
  size_t readBytes(char* buffer,size_t length) override {
    size_t count=std::min(length,prefix.size()-position);
    if(count){std::memcpy(buffer,prefix.data()+position,count);position+=count;}
    // Read the spool in blocks, not one filesystem operation per byte. This
    // keeps the IPP upload within the printer's receive timeout.
    if(count<length){
      int remaining=file.available();
      if(remaining>0)count+=file.read(reinterpret_cast<uint8_t*>(buffer+count),std::min(length-count,size_t(remaining)));
    }
    report(count);return count;
  }
};
