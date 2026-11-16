#pragma once
#include <string>

// Inputs: a generated alphanumeric CSRF token and already HTML-escaped options.
// Pure host-testable renderer; never invokes Wi-Fi scans or exposes saved secrets.
inline std::string renderPortalHtml(const std::string& csrf,const std::string& options,bool scanning) {
  std::string html=R"HTML(<!doctype html><html lang="sk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>P15 Wi-Fi</title><style>body{font:17px system-ui;max-width:480px;margin:30px auto;padding:20px;background:#f2f6f7;color:#183338}input,select,button{font:inherit;box-sizing:border-box;width:100%;padding:12px;margin:8px 0 18px}button{background:#087f79;color:white;border:0;border-radius:8px}a{color:#087f79}.note{font-size:14px}</style></head><body><h1>Pripojiť P15 k Wi-Fi</h1><p>Vyber 2,4 GHz sieť a zadaj jej heslo. Nastavenie API zostane zachované.</p>)HTML";
  if(scanning)html+="<p class=\"note\">Vyhľadávanie sietí prebieha. MyWiFi môžeš nastaviť ihneď alebo o chvíľu obnoviť stránku.</p>";
  html+="<form method=\"post\" action=\"http://192.168.4.1/save\"><input type=\"hidden\" name=\"csrf\" value=\""+csrf+"\"><label>Wi-Fi sieť<select name=\"ssid\" required>";
  html+=options;
  html+="</select></label><label>Heslo siete<input name=\"password\" type=\"password\" maxlength=\"63\" autocomplete=\"new-password\"></label><button type=\"submit\">Uložiť a pripojiť</button></form><p><a href=\"http://192.168.4.1/\">Obnoviť zoznam</a> · <a href=\"http://192.168.4.1/rescan\">Znovu vyhľadať siete</a></p><p class=\"note\">Portál sa po 10 minútach vypne. Ak sa okno nastavenia zobrazuje nesprávne, otvor http://192.168.4.1 priamo v prehliadači.</p></body></html>";
  return html;
}
