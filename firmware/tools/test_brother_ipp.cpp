#include "../src/brother_ipp.h"
#include <cassert>
#include <iostream>
using namespace BrotherIpp;
std::string response(uint32_t id){
 std::string s("\x01\x01\0\0",4);u32(s,id);s.push_back(1);
 attr(s,0x47,"attributes-charset","utf-8");s.push_back(4);return s;
}
int main(){
 auto s=response(7);attr(s,0x23,"printer-state",number(3));
 attr(s,0x44,"media-ready","roll_current_29x0mm");
 attr(s,0x44,"document-format-supported","image/urf");
 attr(s,0x44,"","application/octet-stream");s.push_back(3);
 auto r=parse(s,7);assert(r.ok());assert(r.integer("printer-state")==3);
 assert(r.has("document-format-supported","application/octet-stream"));
 assert(mediaMatches(r.text("media-ready"),29,0));assert(!mediaMatches(r.text("media-ready"),62,0));
 assert(mediaMatches("om_brother-label-29x90mm_29x90mm",29,90));
 assert(!mediaMatches("roll_current_29x0mm",29,90));
 assert(!parse(s,8).valid);assert(!parse(s,0).valid);assert(!parse(s,0xffffffff).valid);
 for(size_t n=0;n<s.size();++n)assert(!parse(s.substr(0,n),7).valid);
 auto job=response(9);attr(job,0x21,"job-id",number(101));attr(job,0x23,"job-state",number(9));job.push_back(3);
 assert(parse(job,9).integer("job-id")==101);assert(parse(job,9).integer("job-state")==9);
 auto request=statusRequest(11,"ipp://192.0.2.10/ipp/print");
 assert(uint8_t(request[2])==0&&uint8_t(request[3])==11);
 assert(request.find("requested-attributes")!=std::string::npos);
 auto print=printRequest(12,"ipp://192.0.2.10/ipp/print","test");
 assert(uint8_t(print[3])==2&&print.back()==3);
 assert(print.find("application/octet-stream")!=std::string::npos);
 assert(print.find("job-name")!=std::string::npos);
 auto poll=jobRequest(13,"ipp://192.0.2.10/ipp/print",101);
 assert(uint8_t(poll[3])==9&&poll.find("job-id")!=std::string::npos);
 std::cout<<"IPP codec, request IDs, media checks, malformed/truncated packets passed\n";
}
