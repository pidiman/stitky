# Overenie verejnej kópie

- API a USB provisioning: 188 testov prešlo (181 API + 7 provisioning).
- Web: TypeScript a produkčné zostavenie prešli.
- C++ testy Wi-Fi portálu a dekódovania telemetrie prešli.

Prevádzkové záznamy pôvodného nasadenia nie sú súčasťou verejného repozitára. Na vlastnom hardvéri over Wi-Fi, HTTPS, identitu tlačiarne, náhľad a jednu vedome zadanú tlač. Stav online mosta neznamená trvalé BLE spojenie; neistý výsledok tlače vyžaduje fyzickú kontrolu.

## QR s popisom a ikona účtu

Overené API testami: zachovanie celého QR a bieleho okraja, zhodný raster tlače, fonty a štýly popisu, odmietnutie pretečenia, uloženie do šablón a úloh, reštart a kompatibilita starých idempotentných požiadaviek. Nezávislý dekodér prečítal QR s popisom obsahujúcim diakritiku. Prešlo produkčné zostavenie webu.

V izolovanej miestnej kópii sa v prehliadači overil náhľad, uloženie a obnovenie QR šablóny s popisom a používateľská ikona v navigácii aj karte účtu. Fyzická tlač sa pri tejto zmene neodosielala.

## Brother rozšírenie / ESP32 1.3.2

Overené natívne profily 29/62 mm súvislých pások a 29×90/62×100 mm štítkov, zhodné preview/raster pixely, orez, izolácia tokenov, download iba s platnou rezerváciou a zachovanie P15 cesty. Prešli testy IPP kódovania/parsera, neplatných odpovedí a konfigurácie; zostavenie webu a firmvéru prešlo. QR s popisom prečítal nezávislý dekodér na všetkých štyroch formátoch. V izolovanom prehliadači sa overil výber tlačiarne, formátu, náhľad a šablóny.

Na ESP32-D0WDQ6 bol cez USB overený firmvér 1.3.2: zachovanie Wi-Fi/P15 nastavení, prvotná príprava spoolu, opakovaný štart, prázdne pending záznamy a HTTPS hlásenia oboch zariadení. Priamy príkaz BROTHER_CHECK potvrdil model QL-810W, nečinnú tlačiareň a 29 mm súvislú rolku; server dostal správny názov média a stav ready. Opravené bolo prvé pripojenie úložiska aj životnosť reťazca média pri serializácii telemetrie. Následne bola úspešne overená aj fyzická tlač zo štúdia cez aktualizované ESP32, ako je uvedené nižšie.

## Oprava prvého výtlačku Brother / server 0.3.1, ESP32 1.3.2

Prvá úloha z ESP zostala v tlačiarni v stave job-incoming a spool-area-full-report; server ju správne označil ako neistú a neposlal znovu. Pri kontrolovanej skúške sa použil ten istý štítok so štandardným úvodom (400 nulových bajtov, inicializácia, raster režim) a uzavretým HTTP spojením. Brother potvrdil job-completed-successfully a jeden výtlačok; používateľ potvrdil správny QR aj popis. Táto fyzická skúška išla z počítača cez IPP.

Server teraz používa overené poradie inicializácie. ESP navyše odosiela súbor po blokoch a vypína opakované použitie IPP spojenia. Natívny test preveruje celý binárny obsah a prechody medzi IPP hlavičkou a súborom pri rôznych veľkostiach blokov; 156 API testov a 7 provisioning testov prešlo, firmvér sa zostavil.

Dňa 17. 11. 2026 používateľ následne odoslal ďalší štítok priamo zo štúdia cez aktualizované ESP32 do Brother QL-810W a potvrdil správny fyzický výtlačok. Tým je overená celá cesta **štúdio → server 0.3.1 → ESP32 1.3.2 → Brother QL-810W cez Wi-Fi/IPP**, vrátane QR kódu s popisom na 29 mm súvislej rolke. Tlač cez ESP32 je funkčná; ostatné Brother formáty majú zatiaľ softvérové overenie, nie potvrdenú fyzickú skúšku.

## Wi-Fi aktualizácia ESP32 / server 0.4.0, firmvér 2.0.0

Dňa 17. 11. 2026 bola na 4 MB ESP32-D0WDQ6 dokončená jednorazová USB migrácia z jednej veľkej aplikačnej partície na dva OTA sloty a 256 KiB Brother spool. Pred migráciou sa overil prázdny front aj oba lokálne pending záznamy a zálohovala sa pôvodná konfigurácia aj spool. Wi-Fi, P15/Brother nastavenia a údaje aplikácie zostali zachované; oba mosty sa znovu pripojili a Brother potvrdil pripravenosť s 29 mm rolkou.

Následne sa cez živý server zadala reinštalácia rovnakého pripraveného obrazu 2.0.0. Táto inštalácia už prebehla cez Wi-Fi, bez USB nahrávania: zariadenie sa presunulo zo slotu 0 do slotu 1, reštartovalo sa, overilo SHA-256 skutočne bežiaceho obrazu a server označil aktualizáciu ako succeeded. Opätovná telemetria potvrdila slot 1, verziu 2.0.0 a obe online zariadenia. Účty, šablóny a história úloh zostali zhodné so zálohou a po kontrole sa obnovila tlač. Pri OTA overovaní sa neposlal fyzický štítok.

Prešlo 164 API testov vrátane oprávnení/CSRF, limitu a integrity obrazu, izolácie sťahovania, potvrdenia až po reštarte, zrušenia čakajúcej aktualizácie, timeoutu a zachovania stavu po reštarte servera. Overilo sa rozloženie partícií aj kapacita pre najväčšie podporované Brother štítky s rezervou pre súborový systém. Sedem provisioning testov, natívny test blokového IPP prenosu, produkčné zostavenie webu a firmvéru prešli. V izolovanom prehliadači bol overený aktualizačný panel, zadanie aktualizácie a jej zrušenie pred prevzatím. [Postup, ochrana a limity OTA](OTA.md).

## Samostatná sekcia aktualizácií

Aktualizácia firmvéru má vlastnú položku **Aktualizácie** v navigácii správcu, oddelenú od zariadení. Príprava súboru a inštalácia majú samostatné odsadené karty; história má vlastnú časť. Produkčné zostavenie webu prešlo. V izolovanom prehliadači sa overilo oddelenie od zoznamu zariadení, vnútorné okraje na počítači aj mobile a rozloženie pri šírke 390 px bez vodorovného pretekania.

## Kontrola a inštalácia firmvéru z GitHubu / server 0.4.1

Prvý workflow ESP32 firmware release úspešne zostavil a zverejnil stabilné vydanie firmware-v2.0.0 s aplikačným .bin súborom a JSON manifestom. Skutočný súbor stiahnutý z GitHubu prešiel overením veľkosti, SHA-256, segmentov ESP32 aj markeru produktu/verzie/OTA rozloženia.

Prešlo 181 API testov a 7 provisioning testov. Kontroly pokrývajú číselné porovnanie stabilných verzií, ignorovanie konceptov/prerelease, nekompatibilné a neúplné vydania, chybné súčty, obmedzené presmerovania a veľkosť, zdieľanú cache a výpadok zdroja. Inštalácia vyžaduje vedomý krok správcu, novšiu verziu a prázdny front; stav sa znovu kontroluje aj po sťahovaní.

V izolovanom prehliadači sa overilo načítanie skutočného vydania 2.0.0 z GitHubu a správny stav Firmvér je aktuálny. So skúšobným starším zariadením tlačidlo Nainštalovať verziu 2.0.0 skutočne stiahlo a overilo obraz z GitHubu a vytvorilo čakajúcu OTA úlohu, ktorá bola potom zrušená pred prevzatím. Skutočné ESP32 sa pri tejto skúške neaktualizovalo a neposlala sa tlač. Mobilná šírka 390 px bola bez vodorovného pretekania; zostavenie webu prešlo.

## Voliteľný OLED / firmvér 2.1.0

Pripravený profil SSD1306 128 × 32 I²C na GPIO21/GPIO22, adresy 0x3C/0x3D. Natívny C++ test overil zobrazované stavy, podržanie chyby/výsledku, neprekrytie novej činnosti starou chybou, percentá, pretečenie millis časovača, orezanie riadkov, 512-bajtový raster, adresovanie a pakety I²C, vynechanie opakovaného obrazu, stlmenie a vypnutie zápisov pri chybe či chýbajúcom displeji. Test IPP prenosu overil aj callback postupu bez zmeny binárnych dát; ostatné natívne kontroly IPP, údajov P15 a Wi-Fi portálu prešli.

Zostavenie firmvéru sa zmestilo do oboch existujúcich OTA slotov bez zmeny partícií. Používateľ následne 17. 11. 2026 potvrdil zobrazenie údajov na fyzickom module V1.6. Wi-Fi aktualizácia na 2.1.0 sa dokončila s overením kontrolného súčtu bežiaceho obrazu a oba tlačové profily sa prihlásili s novou verziou. Táto skúška nepotvrdzuje každý jednotlivý chybový/tlačový stav a neposielala nový skúšobný výtlačok.


## Zjednodušený OLED / firmvér 2.1.1

Hlavička zostáva, druhý riadok je prázdny a činnosť s detailom sú na spodných dvoch riadkoch. Diagnostické údaje sa nestriedajú; pravidelné API a Brother kontroly neprepínajú displej. Natívna kontrola overuje aj nemennú pripravenú obrazovku, prázdny druhý riadok vo všetkých stavoch, poslednú použitú tlačiareň a zachovanie percent a priorít výsledkov/chýb. Fyzické overenie nového rozloženia sa vykonáva až po nainštalovaní tejto verzie.


## ESPHome Brother gateway 0.1.0

Zostavenie pre ESP32-C3 DevKitM-1 s Arduino frameworkom, ESPHome 2026.10.2, LD2410 UART, Home Assistant API, OTA, web_server a SNTP prešlo. Overené odmietnutie nevhodných API adries a neplatných tokenov/hostov; IPP kodek je zhodný s natívne testovanou plnou gateway. Žiadna zmena partícií ani samostatného firmvéru. Prvá verzia je experimentálna; dlhodobú stabilitu a všetky výpadkové scenáre treba ďalej sledovať.


Dňa **17. 11. 2026** sa komponent nainštaloval cez existujúce ESPHome OTA do fyzického ESP32-C3 so zachovaným YAML radaru a šifrovaným Home Assistant API. Pôvodná konfigurácia sa pred zmenou zálohovala. LD2410 po štarte odpovedal a poskytol svoju verziu firmvéru; SNTP sa zosynchronizovalo. Nová gateway sa cez vlastný token prihlásila do aplikácie, správne rozpoznala QL-810W a súvislú 29 mm rolku.

**Fyzická tlač je overená:** aplikácia → ESPHome ESP32-C3 → Brother QL-810W. Odoslal sa jediný schválený 40 × 29 mm skúšobný štítok s textom „ESPHome / Brother OK“. Gateway overila raster, Brother potvrdil dokončenie IPP úlohy a používateľ potvrdil jeden správny výtlačok. Gateway potom znovu hlásila pripravenosť. Táto skúška nepotvrdzuje každý formát, maximálnu dĺžku štítku, dlhodobú stabilitu ani obnovu po skutočnom výpadku napájania.


## ESPHome P15 BLE / gateway 0.2.0

Lokálne zostavenie kompletnej konfigurácie ESP32-C3 vrátane LD2410, šifrovaného HA API/OTA, webu, SNTP, Brothera a P15 BLE prešlo. Overené presné bajty P15 rámca, bloky 20 bajtov, kredity, 30 ms odstup, 300 ms inicializačná pauza, odmietnutie predčasného AA, platné OK po celom prenose, chybové notifikácie a pretečenie časovača. Zostavenie sa zmestilo do existujúceho OTA slotu bez zmeny partícií. Táto softvérová kontrola sama nepotvrdzuje fyzickú tlač; reálne výsledky sa doplnia po nahratí a skúške zariadenia.

Dňa 17. 11. 2026 bola verzia 0.2.0 nahratá cez šifrované ESPHome OTA na existujúcu ESP32-C3 gateway. Reálna P15 odpovedala na čítanie batérie a stavu. Jediný schválený štítok „ESPHome / P15 OK“ (40 × 12 mm) dosiahol úplný BLE prenos a používateľ následne potvrdil, že vyšiel. Gateway počas ukončovania BLE reštartovala; server eviduje pokus ako neistý a automaticky ho neopakoval. **Fyzický výstup P15 cez ESPHome je potvrdený, spoľahlivé potvrdenie výsledku a stabilita však ešte nie sú uzavreté.** Oprava 0.2.1 pridáva dobehnutie prenosu, čakanie po odpojení a diagnostiku; nevytvára ďalší skúšobný výtlačok.

Oprava **esphome-gw-0.2.1** následne prešla lokálnym aj skutočným ESPHome zostavením, nahratím cez šifrované OTA a dvomi po sebe idúcimi reálnymi cyklami P15: pripojenie → batéria/stav → odpojenie → vypnutie BLE → návrat do pripravenosti. Pri týchto cykloch zariadenie nereštartovalo. Obe gateway sa po údržbe znovu povolili. Druhý fyzický štítok sa neposielal, takže potvrdenie tlače po tejto oprave ešte nebolo samostatne fyzicky zopakované. Počas skúšky sa vyskytli aj občasné HTTPS timeouty; automatické ďalšie pokusy o spojenie obnovili komunikáciu bez duplikácie štítku.
