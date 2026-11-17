# ESP32 most pre MarkLife P15

[Projekt](../README.md) · [LED a blikanie](../docs/LED.md) · [Diagnostika](../docs/TROUBLESHOOTING.md)

Firmvér **1.3.0** pre profil `esp32dev`, pôvodný ESP32-D0WDQ6, 4 MB flash. Prepája centrálny server cez Wi-Fi/HTTPS s tlačiarňou P15 cez BLE. Pri štarte nevytvára testové úlohy ani automaticky netlačí.

## Hardvér a sieť

- ESP32 s Wi-Fi a BLE podľa profilu v platformio.ini.
- P15 a štítky 40 × 12 mm; raster servera je 96 × 320 bodov.
- USB dátový kábel a napájanie.
- 2,4 GHz Wi-Fi, odchádzajúce DNS, NTP a HTTPS.
- Voliteľne WS2812/NeoPixel na GPIO18; [zapojenie a všetky LED stavy](../docs/LED.md).

Nejde o generický firmvér pre každú ESP32 variantu. Iné dosky, tlačiarne a formáty treba prispôsobiť. Bežná prevádzka nevyžaduje prichádzajúce spojenie z internetu na ESP32.

## Zostavenie a nahratie

Z koreňa repozitára:

```sh
cd firmware
pio run
pio run -t upload --upload-port /dev/cu.SLAB_USBtoUART
pio device monitor --port /dev/cu.SLAB_USBtoUART --baud 115200
```

Názov portu nahraď podľa svojho systému; môže ísť napríklad o /dev/ttyUSB0 alebo COM port. Monitor pred nahrávaním zatvor, aby neblokoval zariadenie.

| Závislosť / voľba | Hodnota |
|---|---|
| Platforma | espressif32 6.12.0 |
| Framework | Arduino |
| ArduinoJson | 6.21.5 |
| Adafruit NeoPixel | 1.12.3 |
| Partície | huge_app.csv |
| Monitor | 115200 baud |
| LED | GPIO18, 1 RGB pixel, jas 32/255 |

PlatformIO nahráva aj príslušné časti potrebné pre profil. Samostatný aplikačný firmware.bin nie je obraz celej flash. Bežné nahratie aplikácie zachová NVS; mazanie celej flash zničí konfiguráciu aj pending záznamy a nie je rutinný opravný postup.

## Prvotná konfigurácia API a P15

Z koreňa repozitára nainštaluj lokálny provisioningový nástroj:

```sh
python3 -m venv .venv
.venv/bin/pip install -r firmware/tools/requirements.txt
.venv/bin/python firmware/tools/provision.py \
  --port /dev/cu.SLAB_USBtoUART \
  --api-url https://labels.example.com \
  --ca firmware/certs/isrgrootx1.pem \
  --printer-mac 02:00:00:00:00:01
```

**Doména aj MAC sú príklady.** Použi vlastný HTTPS endpoint a skutočnú MAC P15. Pre prvý most zodpovedá token hodnote AGENT_TOKEN servera; ďalšie tokeny vytvára správca v Zariadeniach. Token sa zadáva skryto a nástroj ho nevypisuje.

Prepínač `--token-file` môže čítať existujúci súkromný súbor s tokenom. Voliteľné `--wifi` požiada aj o SSID a skryté heslo Wi-Fi. Bez neho sa existujúce Wi-Fi nastavenie zachová; novú sieť možno nastaviť portálom.

Nástroj odošle lokálny sériový CONFIG záznam s poliami api_url, agent_token, printer_mac, server_ca_pem a prípadne ssid/password. Pri nevyriešenej pending úlohe firmvér odmietne zmenu API, aby výsledok neodišiel na iný server.

Koreňový certifikát musí zodpovedať certifikačnému reťazcu HTTPS servera. Pribalený ISRG Root X1 je verejný certifikát, nie tajný kľúč. Používa sa overované TLS bez insecure režimu. Pred TLS potrebuje ESP32 synchronizovaný čas cez NTP.

## Nastavenie Wi-Fi

Pri chýbajúcom uloženom SSID sa otvorí chránená nastavovacia sieť `P15-Setup-…`. USB monitor ukáže jej názov a náhodné heslo.

1. Pripoj telefón alebo počítač k tejto sieti.
2. Otvor `http://192.168.4.1`, aj keď automatické okno nefunguje.
3. Vyber vlastnú 2,4 GHz sieť a zadaj heslo.
4. Uloženie reštartuje dosku a spustí pripojenie.

MyWiFi v zozname je príkladová predvoľba. Skenovanie beží asynchrónne; formulár sa dá použiť aj pri nedokončenom skene. Portál ukazuje Wi-Fi nastavenie, nie API token. Má kontrolu CSRF a po **10 minútach** sa zavrie.

Portál znovu otvoríš podržaním BOOT približne **3 sekundy počas behu**, alebo USB príkazom WIFI_SETUP. BOOT pri resete môže aktivovať hardvérový bootloader. Nastavovacie heslo sa uchováva v NVS a nemení sa pri bežnom reštarte či nahratí aplikácie.

## USB príkazy

Príkazy odošli ako riadok pri 115200 baud.

| Príkaz | Účinok |
|---|---|
| STATUS | Stav konfigurácie, Wi-Fi, uložené SSID, pending a voľná pamäť |
| WIFI_SETUP | Otvorí Wi-Fi portál |
| SETUP_INFO | Pri aktívnom portáli vypíše jeho názov a heslo |
| PRINTER_INFO | Vyžiada čítanie P15 mimo tlače a s obmedzením frekvencie |
| LED_TEST | 12-sekundový test farieb bez vytvorenia tlačovej úlohy |
| CONFIG … | Konfigurácia; používaj cez maskovaný nástroj |

Konfigurácia aj pending úlohy používajú oddelené NVS priestory. Štart vypíše stav ich otvorenia. Chyba NVS zastaví spracovanie úloh. Nastavenia v tejto verzii nie sú chránené šifrovaním flash; fyzický prístup k zariadeniu je potrebné považovať za dôveryhodný.

## Ako prebieha tlač

Most kontroluje front približne každých 10 sekúnd. Overí 3840-bajtový raster, rozmery a SHA-256, zapíše pending a požiada API o začiatok. Bez úspešného start neposiela tlačové dáta.

BLE používa FF00, odosielanie FF02, odpovede FF01 a kredity FF03. Bloky majú najviac 20 bajtov s odstupom aspoň 30 ms a riadením kreditmi. Prenáša sa raster profilu L11, posun medzery a stop. Na úspech treba AA alebo presné OK; samotné odpojenie nie je úspech.

Výsledok sa uloží pred nahlásením API. Ak sieť zlyhá, opakuje sa iba nahlásenie výsledku. Pending blokuje ďalšie úlohy. Neistý výtlačok sa automaticky neopakuje ani po reštarte. Pri 409/404 je potrebné posúdenie operátora; NVS sa nemaže naslepo.

## Údaje P15 a telemetria

Most posiela svoju verziu, Wi-Fi RSSI, čas behu a voľnú pamäť približne každých 30 sekúnd. Tento heartbeat nepredstiera nové čítanie tlačiarne.

Čítanie P15 prebehne po štarte na prázdnom fronte a pri požiadavke webu alebo PRINTER_INFO, najviac raz za minútu. Posiela dotazy na model, verziu, sériové číslo, batériu a stav; neposiela tlač, posun ani kalibráciu. Mimo podporovanej odpovede je hodnota nedostupná, nie odhadnutá.

Po BLE operácii sa spojenie uvoľní pred ďalším HTTPS volaním kvôli pamäti ESP32. Online most neznamená trvalé spojenie P15. Fialová LED sa preto objaví aj pri čítaní bez tlačovej úlohy.

## Hostiteľské kontroly

Z adresára firmware:

```sh
python3 -m unittest discover -s tools -p test_provision.py
c++ -std=c++17 tools/test_portal_page.cpp -o /tmp/p15-portal-test
/tmp/p15-portal-test
c++ -std=c++17 tools/test_printer_info.cpp -o /tmp/p15-info-test
/tmp/p15-info-test
```

Kontroly overujú provisioning, HTML portálu a parsovanie odpovedí. Nenahrádzajú skúšku Wi-Fi, TLS, LED zapojenia a fyzickej P15 na konkrétnom hardvéri.

Pri probléme pokračuj podľa [diagnostiky](../docs/TROUBLESHOOTING.md). Presné LED intervaly, priority a testovacia sekvencia sú v [LED návode](../docs/LED.md).

## Brother QL-810W na tej istej doske

Firmvér 1.3.0 zachováva P15 cez BLE a dopĺňa Brother cez sieťové IPP. Nové CONFIG polia sú brother_host (IPv4 tlačiarne) a brother_token (token samostatného zariadenia). Použi nástroj configure_brother.py; pôvodné P15/Wi-Fi/API nastavenia ostávajú uložené.

Brother payload sa po HTTPS overí a uloží do LittleFS, aby celý raster nezaberal RAM. Pri prvom použití sa pripraví nepoužitá dátová partícia; predtým používaný poškodený spool sa sám nevymaže. Žurnál rozpracovanej úlohy a číslo IPP úlohy sú v NVS. BROTHER_CHECK číta identitu a médium bez tlače. Po reštarte sa tlačové dáta automaticky neodosielajú znovu.

Kompletné nastavenie, médiá a potvrdenia sú v [Brother návode](../docs/BROTHER.md). Starý firmvér 1.2.1 nemá aktualizáciu cez Wi-Fi; prvé rozšírenie vyžaduje USB. Kontrolu IPP parsera spustíš cez `c++ -std=c++17 tools/test_brother_ipp.cpp -o /tmp/brother-ipp-test` a potom `/tmp/brother-ipp-test`.
