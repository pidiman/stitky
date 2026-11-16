# Nasadenie a správa

[Projekt](../README.md) · [Používanie](USER_GUIDE.md) · [ESP32](../firmware/README.md) · [Diagnostika](TROUBLESHOOTING.md)

## Čerstvá inštalácia

Server potrebuje Docker Engine s Compose, dostupnú HTTPS doménu a reverznú proxy. Zariadenia potrebujú prístup na túto adresu z vlastných sietí.

```sh
git clone https://github.com/pidiman/stitky.git
cd stitky
cp .env.example .env
chmod 600 .env
```

Do `.env` vlož dva samostatne vygenerované náhodné kľúče. Príklad lokálneho generovania jednej hodnoty:

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Spusti ho pre každý kľúč osobitne a hodnoty ulož súkromne. Potom nastav vlastný PUBLIC_ORIGIN a spusti:

```sh
docker compose up -d --build --wait
docker compose ps
curl http://127.0.0.1:8094/api/health
```

Samostatný compose.yaml publikuje službu iba na loopback. `http://127.0.0.1:8094` slúži na lokálnu kontrolu; na používanie štúdia nastav HTTPS. Cookie účtu má príznak Secure.

Ak proxy beží na tom istom hostiteľovi, môže smerovať na 127.0.0.1:8094. Ak beží v Docker kontajneri, jej 127.0.0.1 nie je hostiteľ: pripoj proxy a hub do spoločnej siete podľa voliteľného override a príkladu Caddy. Nahraď doménu aj príkladovú adresu. Verejné DNS musí smerovať na server, ku ktorému sa dostanú prehliadač aj ESP32.

## Premenné prostredia

| Premenná | Význam |
|---|---|
| ADMIN_TOKEN | Náhodný údržbový kľúč, aspoň 24 znakov; nie webové heslo |
| AGENT_TOKEN | Iný náhodný kľúč prvého ESP32, aspoň 24 znakov |
| AGENT_ID | ID prvého mosta, predvolene esp32-01 |
| AGENT_NAME | Zobrazovaný názov prvého mosta |
| PUBLIC_ORIGIN | Presný pôvod webu, napríklad https://labels.example.com |
| MAINTENANCE_CIDRS | Zoznam povolených sietí pre údržbový bearer prístup |
| DB_PATH | Vo vnútri kontajnera /data/p15.sqlite; trvalé dáta vo volume |
| WEB_DIR | Vo vnútri obrazu /app/web/dist |

DB_PATH a WEB_DIR už nastavuje compose. Pri vlastnom spustení mimo Dockera musíš zabezpečiť zapisovateľný dátový adresár, zostavený web a DejaVu fonty. `.env` sa necommituje; `.env.example` zostáva verejná bez reálnych hodnôt.

## Voliteľný profil VPS / Oracle

Príklady používajú `labels.example.com`, Tailscale adresu `100.64.0.1` a adresár `/srv/p15-hub`. Nahraď ich vlastnými hodnotami. Nastav DNS svojho webu a HTTPS reverznú proxy podľa `Caddyfile.example`. Voliteľný `compose.oracle.yaml` pripája existujúcu externú Docker sieť `web` a publikuje port na príkladovej Tailscale adrese; uprav ju pred použitím.

```sh
cd /srv/p15-hub
docker compose -f compose.yaml -f compose.oracle.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.oracle.yaml ps
docker compose -f compose.yaml -f compose.oracle.yaml logs --tail 50
```

Neverejný kontrolný endpoint: http://100.64.0.1:8094/api/health. Priamy port8094 sa publikuje iba na loopback a Tailscale, nie na verejnej IP. Verejný web i API sú prístupné cez HTTPS. Používatelia sa prihlasujú e-mailom a heslom; zariadenia používajú vlastné bearer kľúče. Health a statické prihlasovacie rozhranie sú verejné, dáta a tlač nie.

`.env` na serveri obsahuje ADMIN_TOKEN, AGENT_TOKEN, AGENT_ID a AGENT_NAME; má oprávnenia600. Správcovský a zariadeniový kľúč musia byť rozdielne, náhodné a aspoň24 znakov. Pri prvom štarte na inom serveri skopíruj `.env.example` a nahraď obe vzorové hodnoty náhodnými kľúčmi. Seedované zariadenie sa pri štarte synchronizuje z prostredia; zmena AGENT_TOKEN vyžaduje opätovný provisioning príslušného ESP32.

## ESP32 provisioning

Program sa zostavuje v `firmware/` cez PlatformIO. Profil `esp32dev`, ESP32-D0WDQ6, 4MB flash, partície huge_app. Nahratie cez `pio run -t upload` zabezpečí správny bootloader aj partície. PlatformIO vytvorí aplikáciu firmware.bin pre offset0x10000; binárne výstupy nie sú súčasťou repozitára.

API konfigurácia cez USB sa odošle lokálne a bez vypísania tokenu:

```sh
python3 firmware/tools/provision.py --port /dev/cu.SLAB_USBtoUART \
  --api-url https://labels.example.com --ca firmware/certs/isrgrootx1.pem \
  --printer-mac 02:00:00:00:00:01
```

Nástroj sa skryto opýta na kľúč zariadenia. Bez `--wifi` zachová existujúcu sieť a umožní zadanie hesla v captive portáli. `--wifi` ponúka alternatívne skryté zadanie hesla cez USB. Config sa ukladá do NVS; produkčný binárny súbor neobsahuje token ani heslo siete.

Cez sériovú linku115200 je dostupný `STATUS` (bez tajných hodnôt) a `WIFI_SETUP`. Počas nevyriešenej úlohy nemožno meniť API konfiguráciu, aby sa výsledok neposlal inému serveru. Pending záznam sa nemaže automaticky pri409; je potrebné posúdiť stav úlohy a fyzický výtlačok. NVS nemaž pri bežnom reštarte alebo upgrade.

## Pridanie ďalšieho ESP32

V časti Zariadenia vytvor nové zariadenie. Jeho nový kľúč sa ukáže iba raz. Nainštaluj rovnaký firmware, cez USB nastav tento kľúč a MAC adresu jeho P15, potom cez Wi-Fi portál vyber miestnu sieť. V editore vyber cieľové zariadenie. Zariadenie nikdy nedostane úlohy iného zariadenia.

## Záloha

Za behu používaj SQLite backup API, nie jednoduché kopírovanie samotného DB súboru bez WAL. Príklad na VPS:

```sh
docker compose -f compose.yaml -f compose.oracle.yaml exec -T hub python -c \
  "import sqlite3; s=sqlite3.connect('/data/p15.sqlite'); d=sqlite3.connect('/data/p15-backup.sqlite'); s.backup(d); d.close(); s.close()"
docker cp p15-hub-hub-1:/data/p15-backup.sqlite ./p15-backup.sqlite
```

Zálohu aj `.env` chráň ako súkromné údaje. Obnova vyžaduje zastavenie iba P15 služby, obnovu DB do jej volume s vlastníkom UID10001 a opätovný štart. Nepoužívaj `docker compose down -v`, ak chceš front a šablóny zachovať.

## Bezpečnosť a limity

Žiadne `setInsecure`, žiadne presmerovanie domáceho portu. USB setup AP je WPA2 s jednorazovým náhodným heslom; webový formulár beží lokálne iba počas nastavovania. Nie je to šifrované úložisko s ochranou proti fyzickému čítaniu flash. Používateľské relácie používajú Secure/HttpOnly/SameSite cookie a ochranu CSRF. Prvé prihlásenie admin/admin vyžaduje nastavenie e-mailu, prezývky a nového hesla. Registrácia je predvolene vypnutá. ADMIN_TOKEN zostáva pre údržbu, obmedzenú cez MAINTENANCE_CIDRS; nie je súčasťou webového prihlasovania.

Stavy úlohy: queued → leased → printing → printed/failed/unknown. Pred začatím môže expirovaná lease bezpečne vrátiť úlohu do queued. Po začatí už nikdy automaticky späť do queued. Každá kópia je samostatná úloha. Táto konzervatívna politika uprednostňuje ručné posúdenie nejasného výsledku pred duplicitnou tlačou.

## Údržba a telemetria

Admin POST `/api/agents/{id}/pause` s `{"paused":true}` pozastaví nové prevzatia; už vydané lease môžu dokončiť start/completion. Pred flash počkaj na ukončenie leased/printing úloh a potom most znovu zapni paused=false.

Admin POST `/api/agents/{id}/refresh` vyžiada čítanie. Agent dostane X-Printer-Refresh pri prázdnom fronte, výsledok hlási cez POST `/api/agent/telemetry`. Obnovovanie je obmedzené na raz za60sekúnd a nikdy nesmie prerušiť tlač. Pre samotný most sa posiela metadátový heartbeat každých30sekúnd. USB PRINTER_INFO vyžiada rovnaké čítanie bez motorových/tlačových príkazov.

## Účty a QR

Pri prázdnej tabuľke users sa vytvorí jednorazový účet admin/admin. Pred použitím štúdia musí používateľ zadať svoj e-mail, prezývku a nové heslo. Po nastavení prestane alias admin platiť. Registrácia je uložená v SQLite, predvolene false; prepínač je v Môj účet → Registrácia účtov a mení ho iba správca. Používatelia zdieľajú front a šablóny. Záloha databázy obsahuje aj účty a relácie.

Web neukladá prihlasovacie tajomstvá do localStorage ani sessionStorage. Relácia používa Secure/HttpOnly/SameSite=Lax cookie s platnosťou 12 hodín.

`PUBLIC_ORIGIN=https://labels.example.com` nahraď vlastnou HTTPS adresou; určuje povolený pôvod požiadaviek za proxy. `MAINTENANCE_CIDRS` obmedzuje pôvodný ADMIN_TOKEN na povolené spojenia; nepovoľuj sieť verejnej reverznej proxy. Kľúč neslúži na webové prihlasovanie. Údržbu možno vykonať zvnútra kontajnera cez http://127.0.0.1:8000 s ADMIN_TOKEN z jeho prostredia. Kontroluje sa skutočná IP spojenia, nie X-Forwarded-For.

QR používa korekciu M, biely okraj štyri moduly a celočíselnú mierku najmenej dva body na modul; nevyhovujúci obsah dostane 422. Pred aktualizáciou vytvor online zálohu databázy. QR a účty nevyžadujú zmenu firmvéru ESP32.

## Aktualizácia existujúceho servera

1. Skontroluj prebiehajúce úlohy a naplánuj krátky výpadok servera. Nevytváraj ďalšie tlače počas údržby.
2. Vytvor online zálohu databázy podľa návodu vyššie a bezpečne uchovaj aktuálnu `.env`.
3. V pracovnej kópii skontroluj vlastné úpravy a načítaj novú verziu:

```sh
git status --short
git pull --ff-only
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail 100 hub
```

Pri použití override pridaj rovnaké `-f compose.yaml -f compose.oracle.yaml` ku všetkým compose príkazom. Zachovaj názov projektu a dátový volume, aby sa omylom nevytvorila prázdna databáza pod iným projektom. Nesťahuj vzorovú `.env` cez súkromné nastavenia.

Skontroluj health, prihlásenie, existujúce šablóny, front a návrat mosta online. Aktualizácia webu/API nevyžaduje automatické nahratie ESP32; firmvér aktualizuj len vtedy, keď sa zmenil a zariadenie nemá rozpracovanú tlač. Pred nahratím firmvéru pozastav nové preberanie cez administrátorské API a počkaj na ukončenie leased/printing úloh. Potom most znovu povoľ.

## Obnova zo zálohy

Zastav službu hub, obnov databázu do pôvodného dátového volume a nastav vlastníctvo pre UID 10001. Pri obnove nesmú vedľa obnovenej databázy zostať nesúvisiace staré WAL/SHM súbory. Tento zásah rob nad overenou zálohou a pri zastavenej službe. Potom službu spusti a over účty, šablóny, zariadenia aj front.

Serverová databáza a NVS mosta tvoria stav rozpracovaných úloh. Návrat k staršej zálohe môže byť v rozpore s pending záznamom na ESP32; pred pokračovaním posúď históriu a fyzické výtlačky. Obnova nie je pokyn na opakované vytlačenie starých úloh.
