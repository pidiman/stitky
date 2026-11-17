#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
#include <algorithm>
#include <iostream>
class Stream {
 public:
  virtual ~Stream()=default;
  virtual int available()=0;virtual int read()=0;virtual int peek()=0;
  virtual void flush()=0;virtual size_t write(uint8_t)=0;
  virtual size_t readBytes(char* buffer,size_t length)=0;
};
class File {
  std::string data;size_t position=0;
 public:
  unsigned blockReads=0,singleReads=0;
  explicit File(const std::string& d):data(d){}
  int available(){return data.size()-position;}
  int peek(){return available()?uint8_t(data[position]):-1;}
  int read(){++singleReads;return available()?uint8_t(data[position++]):-1;}
  size_t read(uint8_t* out,size_t length){
    ++blockReads;size_t n=std::min(length,data.size()-position);
    std::copy_n(data.data()+position,n,out);position+=n;return n;
  }
};
#include "../src/brother_body_stream.h"
size_t lastDone=0,lastTotal=0,progressCalls=0;
void progress(size_t done,size_t total){assert(done>=lastDone&&done<=total);lastDone=done;lastTotal=total;++progressCalls;}
int main(){
 std::string prefix("\x01\x01\0\x02\0\0\0\x7b",8);
 prefix+=std::string(317,'p');
 std::string payload;for(size_t i=0;i<48900;++i)payload.push_back(char(i%256));
 // HTTPClient calls readBytes through Stream with different buffer boundaries.
 for(size_t chunk: {size_t(1),size_t(64),size_t(325),size_t(326),size_t(1460),size_t(100000)}){
  File file(payload);BrotherBodyStream body(prefix,file);Stream& stream=body;
  assert(stream.peek()==1);std::string actual;std::vector<char> buffer(chunk);
  while(stream.available()){
   size_t before=stream.available();size_t n=stream.readBytes(buffer.data(),buffer.size());
   assert(n>0&&n<=chunk);assert(size_t(stream.available())==before-n);actual.append(buffer.data(),n);
  }
  assert(actual==prefix+payload);assert(file.singleReads==0);
  assert(file.blockReads<=(payload.size()+chunk-1)/chunk+1);
  assert(stream.readBytes(buffer.data(),buffer.size())==0);assert(stream.read()==-1);
 }
 File tracked(payload);BrotherBodyStream monitored(prefix,tracked,progress);std::string copied;char chunk[1460];
 while(monitored.available()){size_t n=monitored.readBytes(chunk,sizeof(chunk));copied.append(chunk,n);}
 assert(copied==prefix+payload&&lastDone==copied.size()&&lastTotal==copied.size()&&progressCalls>1);
 File file(payload);BrotherBodyStream body(prefix,file);
 assert(body.read()==1&&body.read()==1&&body.peek()==0);
 std::cout<<"IPP body byte equality, binary data, prefix/file boundaries and block reads passed\n";
}
