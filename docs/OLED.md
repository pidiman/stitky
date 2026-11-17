# OLED 0,91″ pri ESP32

[Projekt](../README.md) · [Wi-Fi aktualizácie](OTA.md) · [RGB LED](LED.md)

Firmvér **2.1.0** pridáva voliteľný **SSD1306 128 × 32, I²C**, typický pre 0,91″ štvorpinové OLED moduly. Samotné označenie dosky „V1.6“ neurčuje radič ani rozlíšenie; tento profil predpokladá uvedený bežný typ. Displej nemení nastavenia Wi-Fi, P15/Brother ani OTA rozloženie pamäte.

## Zapojenie

Najprv odpoj napájanie ESP32 vrátane USB. Riaď sa popismi na doske, nie farbami vodičov alebo poradím konektora.

| Pin OLED | Pin ESP32 | Úloha |
|---|---|---|
| GND | GND | Spoločná zem |
| VCC | **3V3** | Napájanie 3,3 V |
| SCK alebo SCL | **GPIO22** | Hodinový signál I²C |
| SDA | **GPIO21** | Dáta I²C |

V tomto štvorpinovom I²C profile je SCK názov pre hodinový signál SCL. Nezapájaj ho na GPIO18: ten už používa stavová RGB LED. Názvy GPIO21/GPIO22 sú čísla signálov, nie poradové čísla nožičiek konektora. Zvoľ krátke vodiče a 3,3 V napájanie; 5 V na I²C vodičoch ESP32 nie je vhodné a moduly môžu mať pull-up rezistory pripojené na VCC.

Predvolené ESP32 I²C piny potvrdzuje [Espressif](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html). Príklad bežného 0,91″ SSD1306 128 × 32 I²C modulu a napájania je v [dokumentácii Waveshare](https://www.waveshare.com/product/displays/0.91inch-oled-module.htm). Rozhranie a príkazy sú popísané v [SSD1306 datasheete](https://cdn-shop.adafruit.com/datasheets/SSD1306.pdf).

## Čo displej zobrazuje

Štyri riadky po najviac 21 znakov používajú malé pôvodné 5 × 7 písmo projektu, veľké ASCII písmená bez diakritiky. Dlhšie správy sa skrátia s tromi bodkami; nepretečú za okraj.

Od **2.1.1** je rozloženie zjednodušené:

1. **FAJNY PRINT a verzia firmvéru.**
2. **Prázdny riadok**, ktorý oddeľuje hlavičku od obsahu.
3. **Aktuálna činnosť:** štart, Wi-Fi/NTP, nastavovací portál, pripájanie P15, preberanie štítku, tlač, výsledok, aktualizácia alebo chyba.
4. **Podstatný detail:** tlačiareň, konkrétna chyba, čakanie na dokončenie alebo percentá prenesených dát pri P15, Brother a OTA. Percentá znamenajú prenos dát, nie potvrdenie fyzického výtlačku. Bez užitočného detailu riadok zostáva prázdny. Pri pripravenom moste ukazuje poslednú použitú alebo ručne kontrolovanú tlačiareň, ak je známa; nejde o potvrdenie jej aktuálnej dostupnosti.

Bežné kontroly API/frontu a pravidelné čítanie stavu Brothera obrazovku neprepínajú. IP adresa, sila Wi-Fi, pamäť, čas behu ani spoločný prehľad oboch tlačiarní sa už nestriedajú. Výnimkou je adresa nastavovacieho portálu, ktorá je potrebná na jeho otvorenie.

Príklad počas prenosu na Brother:

```text
FAJNY PRINT 2.1.1

TLACIM NA BROTHER
PRENOS: 42%
```

Po prenose nasleduje **CAKAM NA DOKONCENIE** a až potom potvrdený alebo neistý výsledok. Potvrdenie sa podrží asi 3,5 sekundy a chyba aspoň 8 sekúnd, aby ju bežná kontrola frontu hneď neprekryla. Nová skutočná činnosť môže nahradiť staršiu správu. Nevyriešená chyba, pri ktorej firmvér zostane stáť, zostáva zobrazená.

Heslá, API kľúče, prihlasovacie údaje ani obsah tlačeného textu/QR sa na OLED neposielajú.

## Prevádzka a diagnostika

Po štarte sa skúšajú iba bežné OLED adresy **0x3C a 0x3D**. Profil má 128 × 32, internú nábojovú pumpu a I²C 100 kHz. Úspešná I²C odpoveď sama nepotvrdzuje presný typ radiča alebo panelu.

- Displej sa prekreslí len pri zmene obrazu, bežne najviac dvakrát za sekundu; dôležitý nový stav sa zobrazí hneď pred blokujúcou operáciou.
- I²C má krátky timeout. Chýbajúci displej nie je chyba tlačového mosta. Pri chybe zbernice sa ďalšie zápisy vypnú, aby sa tlač alebo OTA neopakovane nezdržiavali nefunkčným periférnym zariadením.
- Všetky I²C zápisy bežia v hlavnej slučke, nie vo Wi-Fi/BLE callbackoch. Pri dlhom volaní knižnice môže obraz na chvíľu zostať stáť na príslušnom stave.
- Po minúte bez dôležitej činnosti sa bežná informačná obrazovka stlmí. Obsah sa každú minútu posunie o jeden pixel, aby sa obmedzilo dlhé nemenné zobrazenie; nie je to záruka proti vypáleniu OLED.

USB príkaz **OLED_STATUS** zobrazí odpoveď displeja, adresu, SDA/SCL a rozlíšenie; nič netlačí. **OLED_SCAN** pri prázdnom lokálnom pending stave zopakuje detekciu a inicializáciu. Nepoužívaj ho počas rozpracovanej tlače. Po fyzickom pripojení pri vypnutom napájaní stačí normálny štart ESP32.

Ak obraz zostane čierny, over 3V3, spoločnú zem a správne GPIO21/GPIO22. Ak displej odpovedá, ale obraz je neúplný, posunutý alebo stále prázdny, treba overiť skutočný radič a rozlíšenie modulu; nevyvodzuj kompatibilitu iba z označenia V1.6.

## Inštalácia a overenie

Po pripojení displeja nainštaluj 2.1.1 cez **Aktualizácie → Skontrolovať GitHub → Nainštalovať verziu 2.1.1**. Existujúci OTA profil 2.0.0 sa nemení a USB migráciu netreba opakovať.

V [platformio.ini](../firmware/platformio.ini) sú piny `OLED_SDA=21`, `OLED_SCL=22`. Pri zmene zapojenia uprav tieto definície a skontroluj konflikt so stavovou LED. Ovládač používa iba dodávanú knižnicu Wire; nepridáva veľkú grafickú knižnicu ani jej fonty, aby zostal priestor v oboch OTA slotoch.

Hostiteľská kontrola stavov, priorít, percent, pretečenia časovača, rastrov a I²C prenosu vrátane neprítomného/pokazeného displeja:

```sh
c++ -std=c++17 firmware/tools/test_oled.cpp -o /tmp/oled-test
/tmp/oled-test
```

Softvérové kontroly nenahrádzajú čítanie skutočného OLED. Stav fyzického overenia je zaznamenaný v [akceptačných kontrolách](ACCEPTANCE.md).
