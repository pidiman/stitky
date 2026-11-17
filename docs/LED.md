# Stavová RGB LED ESP32

[Späť na projekt](../README.md) · [Riešenie problémov](TROUBLESHOOTING.md)

Návod opisuje firmvér **1.3.2**, funkciu `ledTick()` a volania meniace stav v [zdroji](../firmware/src/main.cpp). Indikácia je určená pre **externý adresovateľný RGB pixel WS2812/NeoPixel**, nie pre ľubovoľnú vstavanú LED dosky.

## Zapojenie

| Parameter | Predvolené nastavenie |
|---|---|
| Typ | WS2812/NeoPixel kompatibilná RGB LED |
| Prenos a poradie farieb | 800 kHz, GRB |
| DATA | GPIO18 |
| Počet pixelov | 1; firmvér povoľuje 1–16 s rovnakou indikáciou |
| Jas | 32 z rozsahu 1–255; pripravenosť má navyše slabšiu zelenú |
| Knižnica | Adafruit NeoPixel 1.12.3 |

Zapájaj bez napájania. DIN/DATA pripoj na GPIO18 cez sériový odpor 330–470 Ω. GND modulu a ESP32 musia byť spoločné. Modul určený pre 5 V napájaj z vhodného 5V zdroja. **5 V nepatrí na dátový GPIO.** Na spoľahlivý prenos z 3,3V ESP32 do 5V pixelu použi vhodný prevodník úrovní, napríklad 74AHCT125. Priame krátke prepojenie môže fungovať, ale nie je zaručené. Riaď sa označením konkrétneho modulu, nie farbou vodičov.

```text
ESP32 GPIO18 → prevodník 3,3 V / 5 V → odpor → DIN RGB modulu
ESP32 GND ─────────────────────────────────── GND modulu
5V napájanie ──────────────────────────────── 5V modulu
```

`LED_PIN`, `LED_COUNT` a `LED_BRIGHTNESS` sa menia pri zostavení v [platformio.ini](../firmware/platformio.ini). Iný čip, RGBW pixel alebo iné poradie farieb vyžaduje aj zodpovedajúcu konfiguráciu `Adafruit_NeoPixel`. Tieto nastavenia sa nemenia vo webovom štúdiu.

## Presné farby a intervaly

Časy znamenajú dobu svietenia a zhasnutia jedného cyklu. Fáza blikania sa odvodzuje od času behu ESP32, preto prechod do stavu nemusí začať celým svetelným impulzom.

| Efekt | Svieti | Nesvieti | Kedy a prečo |
|---|---:|---:|---|
| Modrá bliká | 500 ms | 500 ms | Otvorený Wi-Fi portál: chýbajúce SSID, príkaz WIFI_SETUP alebo BOOT počas behu |
| Žltá bliká | 300 ms | 300 ms | Wi-Fi pripojenie, čakanie na čas alebo HTTPS požiadavka API |
| Slabá zelená svieti | Trvalo | — | Posledný autentifikovaný kontakt so serverom bol úspešný; pripravenosť mosta |
| Fialová bliká | 500 ms | 500 ms | Vyhľadávanie P15 a nadväzovanie BLE spojenia |
| Fialová svieti | Počas kroku | — | BLE spojenie a počiatočné prenosové kredity sú pripravené |
| Tyrkysová bliká | 150 ms | 150 ms | Prenos tlačového zadania a čakanie na potvrdenie P15 |
| Jasná zelená bliká | 100 ms | 100 ms | Potvrdený prenos; efekt trvá približne 1 sekundu |
| Červená bliká | 250 ms | 250 ms | Chyba API/TLS, BLE, konfigurácie, NVS alebo neistý výsledok |

Fialový trvalý stav sa po spojení zámerne podrží približne **200 ms**. Pri čítaní údajov tlačiarne môže zostať počas dlhšieho čítania. Pred samotným prenosom tlače ho vystrieda tyrkysová.

Blokujúce Wi-Fi/TLS/BLE volanie môže dočasne podržať poslednú farbu a zastaviť animáciu. Indikácia sa aktualizuje v hlavnej slučke a vo vlastných čakacích slučkách; nie v samostatnej úlohe. Krátke zadržanie farby preto samo osebe nedokazuje zamrznutie ESP32.

## Normálny priebeh

**Zapnutie so správnym nastavením:** žltá pri Wi-Fi, čase a API → zelená. Pri prázdnom fronte môže nasledovať fialová pri úvodnom čítaní údajov P15 → zelená po odoslaní telemetrie.

**Prvé nastavenie Wi-Fi:** modrá počas portálu → po uložení reštart → žltá pri pripájaní → zelená po kontakte so serverom. Po 10 minútach sa portál zavrie. Následné pripájanie je žlté, pokiaľ nemá prioritu zapamätaná chyba.

**Tlač:** krátka žltá pri API → fialová blikajúca → fialová svietiaca → tyrkysová → sekunda jasných zelených zábleskov po potvrdení → žltá pri hlásení výsledku → pripravenosť.

**Obnovenie údajov P15 bez tlače:** fialová pri spojení a čítaní → žltá pri odosielaní výsledku → zelená. Nejde o tlač a nespustí sa úspechový efekt tlače.

Kontrola frontu je plánovaná približne každých **10 s** a telemetria každých **30 s**, keď nie je most zaneprázdnený. Krátka žltá počas nečinnosti preto býva normálna. Dlhšia operácia môže tieto intervaly predĺžiť.

## Priorita a zrušenie chyby

1. Počas LED_TEST sa ukazuje testovacia sekvencia.
2. Efekt potvrdenej tlače má pri vyhodnotení farby prednosť pred bežným aj chybovým stavom.
3. Mimo testu a úspechového efektu má zapamätaná chyba prednosť pred bežnou farbou.
4. Inak sa zobrazuje aktuálny krok portálu, siete, BLE alebo tlače.

Červená sa po chybe **zapamätá**. Samotné nastavenie normálneho stavu ju nevymaže. Vymaže ju `ledHeartbeat()` po úspešnej autentifikovanej kontrole/prevzatí frontu alebo po úspešnom odoslaní telemetrie.

Červená teda môže po obnovení komunikácie zmiznúť, aj keď staršia úloha zostala vo webe neistá. Zelená farba neopravuje históriu úloh: ich stav skontroluj osobitne. Pri chybe otvorenia alebo poškodení NVS môže firmvér zostať v chybovej slučke bez spracovania úloh.

## Čo zelená nepotvrdzuje

- Slabá zelená neznamená trvalé BLE spojenie. ESP32 ho vytvára pri tlači alebo čítaní a potom uvoľní.
- Nezaručuje zapnutú tlačiareň, papier ani čerstvú batériu. Pozri čas posledného overenia vo webe.
- Jasná zelená potvrdzuje AA/OK od P15, nie čitateľnosť a zarovnanie fyzického výtlačku.

## LED_TEST cez USB

V sériovom monitore **115200 baud** odošli samostatný riadok:

```text
LED_TEST
```

| Čas od spustenia | Efekt |
|---|---|
| 0–1,5 s | Modrá bliká |
| 1,5–3 s | Žltá bliká |
| 3–4,5 s | Slabá zelená svieti |
| 4,5–6 s | Fialová bliká |
| 6–7,5 s | Fialová svieti |
| 7,5–9 s | Tyrkysová bliká |
| 9–10,5 s | Červená bliká |
| 10,5–12 s | Jasná zelená bliká |

Test trvá **12 sekúnd**, nevytvára tlačovú úlohu a počas sekvencie pozastaví polling aj odosielanie telemetrie. Končí výpisom `LED TEST DONE; normal status restored`. Vráti normálny stav vrátane prípadnej zapamätanej chyby; chybu sám nemaže. Spúšťaj ho počas nečinnosti.

## Diagnostika LED

| Príznak | Čo overiť |
|---|---|
| Nesvieti nič | Napájanie, spoločnú GND, DIN namiesto DOUT, GPIO18 a typ pixelu |
| Zamenené farby | Poradie RGB/GRB a prípadnú RGBW konfiguráciu |
| Náhodné farby | Dátovú úroveň, GND, vodiče a napájanie |
| Trvalá červená indikácia | USB STATUS, chybu API, pending úlohu a [diagnostický návod](TROUBLESHOOTING.md) |
| Modrá po chvíli zmizne | Portál má limit 10 minút; otvor ho BOOT alebo WIFI_SETUP |
| Fialová bez tlače | Môže ísť o čítanie údajov P15 |
| Animácia sa na chvíľu zastaví | Knižničné blokujúce sieťové alebo BLE volanie |

Podklady k zapojeniu: [Adafruit NeoPixel](https://learn.adafruit.com/adafruit-neopixel-uberguide/basic-connections). Rozhodujúce správanie tejto verzie je v [zdroji firmvéru](../firmware/src/main.cpp) a [nastavení zostavenia](../firmware/platformio.ini).

## Brother v rozšírení 1.3.2

Fialová naďalej patrí BLE/P15. Brother používa pri prenose a sledovaní IPP úlohy tyrkysovú, po potvrdenom dokončení a prijatí výsledku serverom zelený úspechový efekt. Chyba alebo neistý výsledok sa signalizuje červenou. Zelená v tomto prípade znamená dokončenú IPP úlohu, nie optické overenie výtlačku. Čítanie stavu a rolky cez IPP nič netlačí. Časy samotných efektov zostávajú nezmenené.
