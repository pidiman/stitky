# Fajny Print Studio

Vlastný webový editor štítkov MarkLife P15, API s trvalým tlačovým frontom a ESP32 most cez Wi-Fi → BLE. Profil 40 × 12 mm používa rovnakú rotáciu ako fyzicky overený výtlačok „USB-C -> USB-C“.

## Používanie

1. Otvor https://stitky.pidiman.sk. Pri prvom štarte sa prihlás `admin / admin` a nastav vlastné heslo, e-mail a prezývku. Ďalšie prihlásenie používa e-mail a nové heslo. Registrácia je predvolene vypnutá; správca ju môže zapnúť v účte. `scripts/open-studio.command` otvorí web.
2. ESP32 pri prvom nastavení vytvorí chránenú Wi-Fi sieť `P15-Setup-…`. Názov a náhodné heslo ukáže USB sériový výpis. Pripoj sa k nej, otvor http://192.168.4.1, vyber sieť (predvolene Lemonka_IoT) a zadaj heslo. Je potrebná sieť 2,4 GHz. API nastavenie je oddelené a zostane uložené.
3. ESP32 si každých 10 sekúnd pýta úlohu. Keď sa v editore ukáže online, zadaj text, skontroluj náhľad, vyber počet kópií a klikni Vytlačiť štítok.
4. Stav „Vytlačené“ znamená prijaté potvrdenie AA/OK od tlačiarne. Pri „Neistý výsledok“ fyzicky skontroluj štítok pred vytvorením novej úlohy. Automatické opakovanie po začatí tlače je zámerne zakázané.

Wi-Fi portál znovu otvoríš podržaním tlačidla BOOT na ESP32 približne tri sekundy počas behu (nie pri zapínaní) alebo USB príkazom `WIFI_SETUP`. Portál sa po 10 minútach vypne. Jeho náhodné heslo zostáva uložené aj po reštarte; cez USB príkaz `SETUP_INFO` ho možno vypísať, kým je portál aktívny.

## Obsah projektu

- `web/`: React + TypeScript editor, skutočný serverový náhľad, šablóny, front, zariadenia.
- `api/`: FastAPI, Pillow, SQLite WAL, používateľské relácie, oddelené kľúče údržby a zariadení, transakčné preberanie úloh.
- `firmware/`: PlatformIO/Arduino ESP32, captive portal, overované HTTPS, SHA-256 rastra, NVS ochrana pred duplicitnou tlačou, BLE L11.
- `compose.yaml`: prenosné nasadenie s portom iba na loopback.
- `compose.oracle.yaml`: napojenie na existujúcu Docker sieť `web` a Tailscale port 8094 na tomto VPS.
- `docs/DEPLOY.md`: nasadenie, zálohy a pridanie ďalších zariadení.

## Overenie

API: 19 automatizovaných testov vrátane súbežného claim/start, expirácií pred/po začatí, idempotencie a zhody náhľadu s rastrom. Web: TypeScript a produkčné zostavenie; v prehliadači overené prihlásenie, náhľad, šablóna, vytvorenie a zrušenie úlohy v oddelenom lokálnom fronte. Firmware: úspešné zostavenie a testy USB provisioningu; aktuálny stav fyzického Wi-Fi a serverového spojenia je uvedený v `docs/ACCEPTANCE.md`.

## Rozsah MVP

Text a viac riadkov, automatická alebo pevná veľkosť písma, centrovanie a profil 40 × 12 mm. Náhľad a tlač vychádzajú z rovnakých pixelov; text sa otáča o 90° až pri príprave rastra pre tlačovú hlavu. API nepoužíva generické ESC/POS profily so šírkou 384 bodov. Editor podporuje aj QR kódy z textu alebo odkazu so skutočným náhľadom. Príliš husté QR kódy odmietne. Obrázky, iné čiarové kódy a ďalšie formáty sú mimo tejto verzie.

Každé ďalšie ESP32 má vlastný kľúč a svoju tlačiareň. Zariadenia iniciujú iba odchádzajúce HTTPS spojenia; domáca LAN nepotrebuje pevnú verejnú IP ani presmerovanie portov. DuckDNS domácich služieb zostáva nezmenené.

## Stavová RGB LED

Voliteľná jedna WS2812/NeoPixel RGB LED: DATA na GPIO18, spoločná GND a 5V napájanie. Farebné stavy, zapojenie a lokálny LED_TEST sú v `docs/LED.md`. Dodaný firmvér1.1.2 uchováva API a Wi-Fi konfiguráciu vNVS a nevytvára vlastné skúšobné úlohy.

## Výber písma

Editor ponúka DejaVu Sans, Sans Bold, Serif, Sans Mono a pôvodné pixelové písmo5×7. Font sa ukladá do šablón a každej novej úlohy. Staršie záznamy ostávajú pri pôvodnom Sans; ich uložený raster sa nemení. Pixelové písmo používa celé násobky7 bodov, veľkosť21 reprodukuje prijatý test USB-C -> USB-C bitovo identicky. Podporuje A–Z, číslice a bežné symboly; malé ASCII písmená zobrazuje ako veľké, diakritiku explicitne odmietne namiesto tichého odstránenia. Ostatné fonty podporujú diakritiku.

Rozšírenie overené27APItestami, produkčným zostavením a kontrolou všetkýchfontov na serveri aj pixelového výberu vprehliadači. Pri tejto aktualizácii nebola odoslaná nová tlač. Pred migráciou je databáza zálohovaná naVPS vpriečinku backups/before-fonts.sqlite.

## Rozšírený editor a údaje tlačiarne

Studio obsahuje zarovnanie vľavo/stred/vpravo, tučné, kurzívu, podčiarknutie, medzery znakov a riadkov, rámik a inverziu. Nastavenia sa ukladajú do šablón a úloh; staršie záznamy dostanú pôvodné predvolené hodnoty bez zmeny uložených rastrov. Symboly sa vkladajú na miesto kurzora. Podporované sú čiernobiele ☺ ☹ ♥ ★ ✓ ✕ ⚠ ⚡ → ← ↔ ↑ ↓ a bežné ekvivalenty🙂😊😀🙁❤⭐✅❌; nepodporované zložené emoji sa odmietnu namiesto prázdneho štvorca.

Karta tlačiarne zobrazuje skutočne načítaný model, verziu, batériu, stav a čas overenia. V Zariadeniach je aj sériové číslo, signál Wi-Fi a verzia/čas behu ESP32. Most online neznamená stále BLE spojenie. Informácie sa čítajú pri štarte a ručnom obnovení, iba mimo tlače a najviac raz za minútu. Údaje staršie ako5minút sú označené; nedostupné hodnoty sa nevymýšľajú.

Na tejto P15 bol fyzicky overený modelP15, firmware1.0.18, sériové číslo a odpovede batérie0064(hlásených100%) a stavu00(bez hlásenej chyby). ESP32 má nahraný firmware1.2.1. Čítacie dotazy neodosielajú tlač, posun ani nastavenia.

## GitHub snapshot

Zdrojový stav prevzatý z projektu „Vybuduj MVP tlače štítkov P15“ vrátane QR kódov a účtov. Overenie tejto kópie: 129 testov API/provisioningu, TypeScript a produkčné zostavenie webu, C++ testy portálu a telemetrie. Pri prenose nebola vykonaná nová fyzická tlač ani nasadenie. Staršie počty testov vyššie opisujú jednotlivé historické aktualizácie.

Repo obsahuje zdroje, zámok webových závislostí a návody. Neobsahuje produkčné heslá, databázy, prevádzkové logy ani predkompilovaný firmvér. Firmvér sa zostavuje zo zdrojov cez PlatformIO.

Rýchly štart: skopíruj `.env.example` do `.env`, nahraď oba kľúče náhodnými hodnotami, nastav `PUBLIC_ORIGIN` pre svoj HTTPS web a spusti `docker compose up -d --build`. HTTPS reverzná proxy je potrebná aj pre zabezpečenú prihlasovaciu cookie; príklad je v `docs/Caddyfile.example`. Podrobnosti sú v `docs/DEPLOY.md`.
