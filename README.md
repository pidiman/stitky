# Fajny Print Studio

Webový editor štítkov MarkLife P15: React/TypeScript, FastAPI, trvalý tlačový front SQLite a ESP32 most cez Wi-Fi → BLE. Profil štítku 40 × 12 mm; náhľad aj tlač používajú rovnaký raster.

## Funkcie

- Text, viac riadkov, päť fontov, zarovnanie, tučné, kurzíva, podčiarknutie, rozostupy, rámik, inverzia a čiernobiele symboly.
- QR kódy z textu alebo odkazu s náhľadom a kontrolou čitateľnej veľkosti.
- Šablóny, tlačový front, viac zariadení, údaje tlačiarne a ručné obnovenie telemetrie.
- Prihlásenie e-mailom a heslom, prezývka a správcom riadená registrácia (predvolene vypnutá).
- Prvé prihlásenie `admin / admin` vyžaduje nastavenie nového hesla, e-mailu a prezývky.
- Každé ESP32 má vlastný kľúč. Po začatí tlače sa neistý výsledok automaticky neopakuje.

## Spustenie

1. Skopíruj `.env.example` do `.env`, nastav dva rôzne náhodné kľúče a `PUBLIC_ORIGIN` pre svoj HTTPS web.
2. Spusti `docker compose up -d --build` a nastav HTTPS reverznú proxy podľa `docs/Caddyfile.example`. Zabezpečené prihlasovacie cookie vyžadujú HTTPS.
3. Zostav a nahraj ESP32 firmvér cez PlatformIO. Cez `firmware/tools/provision.py` nastav svoj endpoint, kľúč zariadenia a **MAC adresu vlastnej tlačiarne**. Príkladová MAC nie je skutočné zariadenie.
4. Vo Wi-Fi portáli ESP32 nastav svoju 2,4 GHz sieť a otvor Studio.

Podrobnosti: [nasadenie](docs/DEPLOY.md), [API](api/README.md), [firmvér](firmware/README.md), [LED](docs/LED.md).

## Overenie tejto kópie

129 testov API a provisioningu, TypeScript a produkčné zostavenie webu, C++ testy portálu a telemetrie. Pri prenose do repozitára sa nevykonala nová fyzická tlač ani nasadenie. Firmvér treba po provisioningu overiť na vlastnom zariadení.

Zdrojový stav prevzatý z projektu „Vybuduj MVP tlače štítkov P15“ vrátane QR a účtov. Verejná kópia používa príkladové adresy, SSID a MAC namiesto prevádzkových údajov. Neobsahuje heslá, databázy, logy, záznamy produkčného overovania ani predkompilovaný firmvér.
