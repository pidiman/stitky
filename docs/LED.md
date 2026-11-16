# Stavová LED na GPIO18

Predvolený profil: jedna adresovateľná RGB LED WS2812/NeoPixel, poradie GRB,800kHz; DATA GPIO18. Fotka modulu zodpovedá bežnému RGB modulu, ale presný čip nie je potvrdený. Pri RGBW module alebo inom poradí farieb uprav typ v `firmware/src/main.cpp`.

Zapájaj bez napájania. DATA/DIN (vstup, nie DOUT) naGPIO18 cez odpor330–470ohm, GND spoločná sESP32, +5V na5V napájanie. Nepripájaj5V naGPIO. Pre spoľahlivú5V dátovú úroveň použi74AHCT125 alebo obdobný prevodník vhodný preNeoPixel. Samotný ESP32 generuje3,3V; pri niektorých LED funguje krátke priame spojenie, ale nie je to zaručené. Zapojenie vodičov over podľa označenia modulu, nie iba podľa farby.

| Signalizácia | Stav |
|---|---|
| Modrá bliká | Wi-Fi nastavovací portál |
| Žltá bliká | Pripájanie kWi-Fi/API alebo synchronizácia času |
| Slabá zelená | Pripravené; posledný kontakt so serverom úspešný |
| Fialová bliká | Pripájanie kP15 cezBLE |
| Fialová svieti | P15 pripojená |
| Tyrkysová bliká | Prenos tlačového zadania |
| Zelený záblesk | Tlačiareň potvrdila zadanie |
| Červená bliká | Chyba alebo neistý výsledok |

Zelená pripravenosť neznamená trvaléBLE spojenie. Most sa kP15 pripája až pri úlohe a potom spojenie uvoľní. Vzor blikania sa môže počas blokujúcich sieťových aleboBLE operácií pozastaviť; farba zostane nastavená.

USB príkaz `LED_TEST` spustí krátku farebnú sekvenciu bez tlače. Po fyzickom pripojení používateľ musí potvrdiť, že farby zodpovedajú tabuľke. Jas je zámerne obmedzený.

Referencie:
- https://learn.adafruit.com/adafruit-neopixel-uberguide/basic-connections
- https://documentation.espressif.com/esp32_datasheet_en.html
