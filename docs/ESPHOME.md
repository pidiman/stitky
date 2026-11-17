# Brother gateway v ESPHome

[Projekt](../README.md) · [Brother](BROTHER.md)

Komponent **esphome-br-0.1.0** pridáva do existujúceho ESPHome zariadenia gateway pre **Brother QL-810W cez Wi-Fi/IPP**. Pôvodná samostatná gateway zostáva nezmenená. Pôvodná verzia 0.1.0 má iba Brother; voliteľné P15/Bluetooth pridáva verzia 0.2.0 popísaná nižšie. ESPHome verzia nemá OLED ani aktualizácie cez aplikáciu štítkov. Aktualizuje sa bežným spôsobom cez ESPHome.

**Overené na zariadení 17. 11. 2026:** ESP32-C3 s LD2410, inštalácia cez ESPHome OTA a jeden správny fyzický výtlačok na 29 mm páske potvrdený používateľom. Prvá verzia zostáva experimentálna pre ostatné formáty a výpadkové scenáre.

## Rozsah prvej verzie

- Cieľové prostredie: ESPHome **2026.10.2**, ESP32-C3, existujúci framework Arduino. Novšiu verziu treba znovu zostaviť a overiť.
- Zachováva existujúce ESPHome API, OTA a senzory vrátane UART radaru LD2410. Nemá vlastné GPIO požiadavky.
- Sieťové operácie vykonáva samostatná úloha FreeRTOS. Hlavná slučka ESPHome prijíma iba stručné stavové správy; dlhé HTTP volanie neblokuje jej obsluhu UART.
- Bez zmeny partícií a bez súborového systému: celý raster sa pred tlačou stiahne do RAM a overí SHA256. Najviac **131072 bajtov**, pri nedostatku pamäte aj menej. Pri dlhom štítku použi kratší formát alebo plnú gateway. Odmietnutá úloha sa neodosiela do tlačiarne.
- Kontrola QL-810W, stavu idle, formátu a presnej rolky pred začatím tlače. Potvrdenie úspechu vyžaduje dokončenie IPP úlohy; odoslanie bajtov samo nestačí.
- Rozpracovaná úloha a výsledok sú uložené v samostatnom NVS priestore. Po reštarte sa obnoví iba zisťovanie výsledku/jeho hlásenie, nikdy automatické opakované odoslanie tlače. Poškodený záznam alebo zlyhanie zápisu zastaví preberanie nových úloh.
- HTTPS k aplikácii overuje certifikát a názov servera; používa systémový CA bundle a platný čas SNTP. Presmerovania sú zakázané. Brother používa miestne IPP cez HTTP/631 rovnako ako overená plná gateway.

Samostatná úloha nezaručuje neobmedzenú pamäť ani nulové oneskorenie senzora. Súbeh treba overiť na konkrétnom zariadení počas reálnej tlače.

## Nastavenie

1. Zálohuj existujúci YAML a v aplikácii štítkov pridaj samostatné zariadenie modelu Brother. Na prvé overenie ho nechaj pozastavené. Každá gateway musí mať vlastný agent token; nepoužívaj token pôvodnej gateway.
2. Pridaj obsah [brother.example.yaml](../esphome/brother.example.yaml) do existujúcej konfigurácie. Existujúce zoznamy `external_components` a `time` zlúč, neduplikuj názvy koreňových sekcií.
3. Do súkromného ESPHome `secrets.yaml` ulož `fajny_brother_agent_token` a `fajny_brother_printer_host`. Nikdy ich necommituj do verejného repozitára. `api_url` je HTTPS adresa aplikácie bez koncovej cesty.
4. Pre opakovateľnú inštaláciu nastav `ref` na konkrétny otestovaný commit namiesto pohyblivej vetvy `main`.
5. Validuj a zostav celý YAML, potom ho nainštaluj cez existujúce ESPHome OTA. **Binárka firmware-v2.x pre esp32dev nie je vhodná pre ESPHome ani ESP32-C3.**
6. Over návrat do HA, údaje LD2410, nový stavový textový senzor a online/pripravený stav Brothera v aplikácii. Až potom povoľ tlač cez nové zariadenie.

Úlohy patria konkrétnej gateway, nepresúvajú sa automaticky medzi zariadeniami. Pri prvých skúškach neposielaj súbežné úlohy z dvoch gateway do jednej tlačiarne.

## Výpadky a obnova

Ak sa po `/start` stratí spojenie alebo napájanie, výsledok môže byť **neistý**. Najprv skontroluj skutočný štítok, potom prípadne vytvor novú úlohu ručne. Komponent nepoužíva automatické opakovanie tlačového prenosu.

Ak server už uzavrel úlohu iným výsledkom, komponent ponechá miestny záznam a hlási `VYSLEDOK CAKA NA APLIKACIU`. Taký konflikt vyžaduje zosúladenie záznamu správcom po kontrole výtlačku; nevynucuj vymazanie celej NVS, lebo obsahuje aj ostatné ESPHome nastavenia.

Počas tlače neinštaluj nový firmvér. Počkajte na dokončenie a prázdny front; aktualizácia môže prerušiť fyzickú tlač, ktorú nemožno bezpečne automaticky zopakovať.

## Kontroly

IPP kodek v komponente je rovnaký ako natívne testovaný kodek samostatnej gateway. Zostavenie musí zahŕňať aj existujúci radar/API/web komponent, nie iba holú gateway. Softvérová kontrola nie je dôkazom fyzického výtlačku; stav skúšok je v [akceptačných kontrolách](ACCEPTANCE.md).

## P15 cez Bluetooth — verzia 0.2.0

Od **esphome-gw-0.2.0** môže ten istý komponent voliteľne obsluhovať aj P15 cez BLE. Samostatný firmvér esp32dev sa nemení. [Príklad spoločnej konfigurácie](../esphome/p15-brother.example.yaml) dopĺňa sekciu `p15`, jeden `ble_client`, jednu BLE connection slot a netrvalé skenovanie. P15 aj Brother musia mať **rôzne tokeny a samostatné zariadenia** v tlačovej aplikácii. Existujúcu koreňovú sekciu `fajny_brother` rozšír, nevytváraj jej duplikát. MAC P15 ulož do súkromných secrets.

Riadenie siete a tlačových úloh je spoločné: Bluetooth sa zapne až po skončení HTTPS volaní a vypne pred ďalšou komunikáciou s aplikáciou alebo Brotherom. Firmvér čaká na skutočné ukončenie Bluedroid aj BLE controlleru, nie iba na odpojenie tlačiarne. Pri zlyhaní ukončenia zastaví ďalšiu sieťovú prácu a vyžiada reštart. Žiadne trvalé BLE skenovanie ani automatické pripájanie mimo riadenej operácie; kontrola konfigurácie preto vyžaduje `enable_on_boot: false`, `max_connections: 1`, `continuous: false` a `auto_connect: false`.

BLE automat beží bez čakacích slučiek v hlavnej slučke ESPHome. Posiela najviac 20 bajtov na blok, iba s kreditom tlačiarne a s odstupom aspoň 30 ms. Služba FF00, odosielanie FF02 a notifikácie FF01/FF03 zodpovedajú overenej pôvodnej gateway. Úspech vyžaduje AA alebo presné OK **až po odoslaní celého rastra**. Predčasné potvrdenie, samotné odpojenie ani úspešné vloženie bloku do BLE frontu nie sú potvrdením výtlačku. Prerušený pokus zostane neistý a automaticky sa netlačí znova.

P15 má vlastný NVS záznam úlohy; existujúci záznam Brothera zostáva zachovaný. Raster P15 je 96 × 320 bodov (3840 bajtov), overený cez SHA256 pred začatím. Podporuje existujúce textové aj QR úlohy vrátane popisu, ktoré vykreslí server. Prvý probe po štarte a ďalšie kontroly približne každé dve minúty iba čítajú batériu a stav; neposielajú tlačové, posuvné ani zapínacie príkazy. Aplikácia ukazuje výsledok poslednej kontroly, nie trvalé BLE spojenie. Tlačidlo obnovy údajov môže vyžiadať novú kontrolu s odstupom aspoň 30 sekúnd.

Stavový textový senzor P15 v HA ukazuje pripájanie, čítanie, prenos a výsledok; batéria a chyby tlačiarne sa hlásia do tlačovej aplikácie. Aktualizácie sú stále cez ESPHome. BLE zvyšuje obsadenie RAM aj flash a môže znížiť maximálnu praktickú dĺžku Brother štítku; kontrola voľnej pamäte pred tlačou ostáva aktívna.

Natívna kontrola presného rámca, kreditov, časovania, včasného ACK, porúch a pretečenia časovača:

```sh
c++ -std=c++17 esphome/tools/test_p15_protocol.cpp -o /tmp/p15-protocol-test
/tmp/p15-protocol-test
```

Stav reálneho overenia je v [akceptačných kontrolách](ACCEPTANCE.md). Novú podporu treba odlíšiť od staršieho fyzicky overeného Brother-only zostavenia.

### Oprava 0.2.1

Po prenose zostáva BLE spojenie ešte 1,5 sekundy otvorené. Po odpojení klienta nasleduje najmenej 750 ms na spracovanie udalostí; Bluetooth sa nevypína násilne počas odpájania. Neskorá chybová odpoveď zruší úspešný výsledok. Diagnostika uvádza dôvod reštartu, výsledok BLE prenosu a počty prijatých bajtov pri prerušení HTTP bez tokenov či obsahu štítku. Pri prvom pokuse s 0.2.0 vyšiel štítok s oneskorením, čo používateľ potvrdil. Gateway však reštartovala pri ukončovaní Bluetooth a aplikácia bezpečne ponechala výsledok ako neistý bez opakovania. Stabilný návrat po tlači sa musí ešte overiť.

### Údaje P15 priamo v Home Assistante — 0.2.2

Voliteľné položky `battery`, `printer_available`, `printer_status`, `last_error` a `last_check` v sekcii `p15` vytvoria natívne entity ESPHome. Nevyžadujú prístupový kľúč tlačovej aplikácie v HA ani ďalšie HTTP sťahovanie. `status` naďalej ukazuje aktuálnu činnosť a percentá prenosu. [Úplný príklad ESPHome](../esphome/p15-brother.example.yaml), [príklad karty HA](../esphome/home-assistant-p15-card.example.yaml).

Batéria, dostupnosť a stav pochádzajú z poslednej dokončenej BLE kontroly, nie z trvalého spojenia. Kontrola beží po štarte a približne každé dve minúty; pri tlači alebo pomalej sieti sa môže odložiť. Pri neúspešnej kontrole sa batéria zmení na neznámu a dostupnosť na vypnutú; chýbajúca odpoveď sa nevydáva za 0 % ani za pripravenosť. Čas kontroly je presný UTC text ISO 8601, ktorý príklad karty prevádza na miestny čas a ošetruje chýbajúce údaje. Údaje sa medzi pracovnou úlohou a hlavnou slučkou prenášajú kópiou vo fronte; HA entity sa publikujú iba z hlavnej slučky. Priebežná činnosť a údaje poslednej kontroly sú oddelené, aby staré percento batérie nepredstieralo aktuálne BLE spojenie.
