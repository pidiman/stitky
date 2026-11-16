# Riešenie problémov

[Späť na projekt](../README.md) · [LED](LED.md) · [Používanie](USER_GUIDE.md)

Najprv rozlíš stav webu/servera, Wi-Fi mosta a samotnej P15. Online ESP32 neznamená trvalé BLE spojenie. Pri neistom výsledku skontroluj fyzický štítok pred vytvorením ďalšej úlohy.

## Rýchla orientácia

| Problém | Kontrola |
|---|---|
| LED bliká modro | Je otvorený Wi-Fi portál; pripoj sa a nastav 2,4 GHz sieť |
| LED zostáva žltá | Wi-Fi, DNS, čas NTP, HTTPS adresa a spojenie na API |
| LED bliká červeno | USB výpis, chyby API, BLE a pending úloha |
| LED bliká fialovo a tlač nepokračuje | Zapnutá P15, správna MAC, dosah a odpojenie od mobilnej aplikácie |
| Most je zelený, ale P15 nedostupná | Zelená potvrdzuje server; obnov údaje tlačiarne a over BLE |
| Úloha je queued | Cieľový most je offline, pozastavený alebo má nevyriešenú predchádzajúcu úlohu |
| Úloha je unknown | Skontroluj fyzický výsledok; automatický opakovaný výtlačok sa nevykoná |
| QR sa nezmestí | Skráť obsah; minimálnu veľkosť modulov neobchádzaj |
| Prihlásenie sa neudrží | HTTPS, správny PUBLIC_ORIGIN a cookie, prípadne vypršaná relácia |

## Wi-Fi nastavenie a modrá LED

1. Podrž BOOT približne tri sekundy **počas behu** alebo pošli cez USB `WIFI_SETUP`.
2. Pripoj sa k `P15-Setup-…`; názov a náhodné heslo ukáže USB.
3. Ak sa malé prihlasovacie okno neotvorí správne, použi normálny prehliadač a `http://192.168.4.1`.
4. Vyber vlastnú 2,4 GHz sieť a zadaj heslo. Príklad MyWiFi nie je povinný názov siete.
5. Po uložení sa doska reštartuje. Pri chybe hesla portál otvor znova.

Portál sa po 10 minútach zavrie. BOOT pri zapínaní môže prepnúť dosku do hardvérového bootloadera; nie je to rovnaké ako podržanie počas behu. Počas aktívneho portálu netečie normálny polling frontu.

## USB diagnostika

Použi monitor na **115200 baud**. Príkaz musí končiť novým riadkom.

| Príkaz | Účel |
|---|---|
| STATUS | Nastavenie, Wi-Fi, uložené SSID, pending stav a pamäť |
| WIFI_SETUP | Otvorenie miestneho portálu |
| SETUP_INFO | Názov a heslo nastavovacej siete, iba pri aktívnom portáli |
| PRINTER_INFO | Vyžiadanie čítania údajov P15 mimo tlače |
| LED_TEST | 12-sekundový test indikácie bez vytvorenia tlačovej úlohy |

Heslo z SETUP_INFO ani kompletné diagnostické výpisy s identifikátormi nezverejňuj. Príkaz CONFIG používaj cez [maskovaný provisioningový nástroj](../firmware/tools/provision.py), nie v zdieľanom texte s tokenom.

## Žltá alebo červená pri serveri

Over presný názov SSID vrátane veľkosti písmen, heslo a 2,4 GHz dostupnosť. USB diagnostika môže ukázať dôvod odpojenia. Pri fungujúcej Wi-Fi skontroluj:

- správny HTTPS endpoint a platný certifikát,
- koreňový certifikát uložený v ESP32,
- dostupné DNS a NTP; nesprávny čas bráni bezpečnému TLS,
- token príslušného zariadenia a zhodu po jeho prípadnej rotácii,
- dostupnosť servera a logy kontajnera.

Krátka žltá pri pravidelnej požiadavke je bežná. Červená sa zapamätá a zmizne až po úspešnej kontrole frontu alebo telemetrii. Nespoliehaj sa na zmenu farby pri posudzovaní staršej neistej úlohy.

## P15 sa nepripojí

Zapni P15, skontroluj napájanie a dosah BLE. Odpoj ju od mobilnej aplikácie alebo iného klienta. V provisioningu musí byť MAC tvojej tlačiarne, nie príklad `02:00:00:00:00:01`.

Ručná obnova údajov sa môže odložiť do prázdneho frontu alebo do konca 60-sekundového obmedzenia. Pri vypnutej tlačiarni môžu staršie identifikačné údaje zostať viditeľné; rozhoduje čas overenia a dostupnosť novej batérie/stavu.

## Úloha čaká alebo má neistý výsledok

Pri queued over cieľové zariadenie, online stav, prípadné pozastavenie a pending záznam na ESP32. Úloha sa nepresmeruje automaticky na iný most.

Pri unknown alebo prerušení po štarte skontroluj, či štítok nevytlačila P15 celý alebo čiastočne. Po obnovení siete most opakuje odoslanie výsledku, nie fyzickú tlač. HTTP 409/404 pri hlásení výsledku potrebuje posúdenie operátora. Nemaž pending/NVS iba preto, aby sa front rozbehol.

Ani printed neznamená optické overenie kvality. Ak chceš po kontrole ďalší kus, vytvor vedome novú úlohu.

## Chybný náhľad alebo QR

Pri chybe 422 skontroluj dĺžku, počet riadkov, znaky a veľkosť písma. Pre diakritiku nepoužívaj pixelový font. Zložené emoji nahraď podporovaným symbolom.

Dlhé QR skráť. Papier má pevný rozmer; znižovanie modulov pod overovaný limit nie je riešenie. Na serveri majú byť fonty DejaVu; Docker obraz ich inštaluje.

## Prihlásenie a registrácia

Admin/admin platí iba pred prvým nastavením účtu. Po nastavení použi uložený e-mail a nové heslo. Pri opakovaných chybných pokusoch môže API odpovedať 429; počkaj podľa hlásenia.

Pri prihlasovacej slučke over HTTPS a PUBLIC_ORIGIN vrátane schémy a domény. Cookie je Secure a na obyčajnej HTTP adrese nemusí fungovať. Pri chybe CSRF obnov stránku a prihlásenie. Po 12 hodinách treba novú reláciu.

Ak nie je registrácia dostupná, správca ju musí povoliť. Vypnutú registráciu nepovolíš iba odkrytím tlačidla v prehliadači; kontroluje ju server.

## Serverové kontroly

V adresári s compose.yaml:

```sh
docker compose ps
docker compose logs --tail 100 hub
curl http://127.0.0.1:8094/api/health
```

Health má vrátiť `{"ok":true}`. Je to kontrola API a databázy, nie fyzickej tlačiarne. Pri nasadení s dodatočným compose súborom použi tie isté `-f` voľby ako pri spustení.

Pred zásahom do databázy alebo aktualizáciou si urob [zálohu](DEPLOY.md). Nepoužívaj `docker compose down -v` ani vymazanie flash ako bežný opravný krok; zničili by uložené dáta alebo ochranné záznamy.
