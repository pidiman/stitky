# Nasadenie a správa

## Oracle Free VPS

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
