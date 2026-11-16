#include "../src/portal_page.h"
#include <cassert>
#include <iostream>

int main() {
  const std::string options="<option value='MyWiFi' selected>MyWiFi</option><option value='Other &amp; Network'>Other &amp; Network</option>";
  auto pending=renderPortalHtml("CSRF123",options,true);
  assert(pending.find("<!doctype html>")==0);
  assert(pending.find("<body>")!=std::string::npos);
  assert(pending.find("action=\"http://192.168.4.1/save\"")!=std::string::npos);
  assert(pending.find("method=\"post\"")!=std::string::npos);
  assert(pending.find("name=\"csrf\" value=\"CSRF123\"")!=std::string::npos);
  assert(pending.find("name=\"password\" type=\"password\"")!=std::string::npos);
  assert(pending.find("MyWiFi' selected")!=std::string::npos);
  assert(pending.find("http://192.168.4.1/rescan")!=std::string::npos);
  assert(pending.find("Other &amp; Network")!=std::string::npos);
  assert(pending.find("agent_token")==std::string::npos);
  assert(pending.find("server_ca_pem")==std::string::npos);
  auto ready=renderPortalHtml("CSRF123",options,false);
  assert(ready.size()<pending.size());
  assert(ready.find("MyWiFi' selected")!=std::string::npos);
  std::cout<<"Portal HTML checks passed: complete form, absolute action, CSRF, default SSID, cached options, no API secrets\n";
}
