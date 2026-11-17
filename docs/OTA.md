# Aktualizácia ESP32 cez Wi-Fi

[Projekt](../README.md) · [ESP32 firmvér](../firmware/README.md) · [LED](LED.md)

Od servera **0.4.0** a firmvéru **2.0.0** môže správca aktualizovať ESP32 priamo v štúdiu, v časti **Aktualizácie → Aktualizácia ESP32 cez Wi-Fi**. Aktualizuje sa celý most vrátane podpory P15 a Brothera. ESP32 si firmvér sťahuje cez odchádzajúce overené HTTPS; na routeri sa neotvára nový port a miestny webový aktualizačný server nie je potrebný.

## Bežná aktualizácia

1. Dokonči alebo zruš všetky čakajúce tlačové úlohy. ESP32 musí byť online.
2. Otvor **Aktualizácie**, vyber aplikačný súbor `.bin` a zadaj jeho verziu. Pri súbore s verziou v názve sa označenie predvyplní.
3. Stlač **Pripraviť firmvér**. Server overí produkt, dosku, rozloženie pamäte, veľkosť, segmenty a kontrolné súčty. Tento krok ešte nič neinštaluje.
4. Vyber hlavné ESP32 a pripravenú verziu. Stlač **Nainštalovať cez Wi-Fi**. Ak P15 aj Brother zdieľajú jedno ESP32, aktualizujú sa spoločne; na výber je hlavný most s podporou OTA.
5. Nechaj ESP32 zapnuté. Počas sťahovania a zápisu bliká stavová RGB LED bielo, **200 ms svieti / 200 ms nesvieti**. Pri reštarte a opätovnom pripájaní nasleduje bežná žltá indikácia.
6. Počkaj na stav **Aktualizované**. Ten znamená, že ESP32 po reštarte prečítalo a overilo skutočný bežiaci obraz firmvéru a pripojilo sa späť na server. Samotné stiahnutie sa za úspech nepovažuje.

Počas čakajúcej a prebiehajúcej aktualizácie server dočasne blokuje novú tlač a preberanie úloh. Ide o spoločnú krátku prestávku tlače v tomto pracovnom priestore. Zrušiť možno len aktualizáciu, ktorú ESP32 ešte neprevzalo. Už prevzatá aktualizácia sa neprerušuje tlačidlom v aplikácii.

Opätovná inštalácia rovnakej verzie je povolená a vyžaduje rovnaké vedomé spustenie. Zlyhané alebo neisté aktualizácie sa automaticky neopakujú. Po najviac 10 minútach bez potvrdenia aplikácia zobrazí neistý výsledok a uvoľní prestávku; skontroluj online stav a verziu zariadenia pred ďalším pokusom.

## Jednorazový prechod zo starého firmvéru

Firmvér 1.3.x používal jednu 3 MB aplikačnú partíciu a nevedel prijímať aktualizácie. Preto jeho prvý prechod na OTA vyžaduje **ešte jedno nahratie cez dátové USB** vrátane novej tabuľky partícií. Nestačí nahrať iba novú aplikáciu na pôvodnú tabuľku.

Pred migráciou pozastav zariadenia na serveri, over prázdny front aj oba lokálne pending záznamy, zálohuj konfiguráciu/partície a zachovaj pôvodný `.bin`. Nahratie podľa [ESP32 návodu](../firmware/README.md) zachováva NVS na rovnakých adresách; **nepoužívaj vymazanie celej flash**. Brother spool sa premiestni a prvýkrát pripraví len bez rozpracovanej úlohy. Po migrácii over Wi-Fi, obe zariadenia a jednu Wi-Fi aktualizáciu; potom obnov tlač.

| Partícia | Adresa | Veľkosť |
|---|---:|---:|
| NVS konfigurácia a záznamy | `0x9000` | `0x5000` |
| OTA výber spustenia | `0xe000` | `0x2000` |
| Aplikácia 0 | `0x10000` | `0x1D0000` |
| Aplikácia 1 | `0x1E0000` | `0x1D0000` |
| Brother LittleFS spool | `0x3B0000` | `0x40000` |
| Výpis pádu | `0x3F0000` | `0x10000` |

Rozloženie je pre 4 MB profil `esp32dev` a je definované v [partitions_ota.csv](../firmware/partitions_ota.csv). Každý aplikačný súbor smie mať najviac **1 900 544 bajtov** vrátane ESP32 hlavičiek a súčtov. Spool má 256 KiB a podporované Brother štítky do 200 mm sa doň zmestia. Aktualizácia cez Wi-Fi nemení tabuľku partícií, bootloader, Wi-Fi konfiguráciu ani kľúče tlačiarní.

## Ochrana a limity

- Pripraviť a spustiť aktualizáciu môže iba správca. Prihlásená aplikácia používa ochranu CSRF; údržbový prístup zostáva obmedzený na povolenú sieť.
- Každé ESP32 stiahne iba jemu pridelený obraz vlastným kľúčom. Binárny súbor nie je verejne dostupný cez anonymný odkaz.
- Zápis smeruje do neaktívnej aplikačnej partície. Pri neúplnom sťahovaní alebo nesprávnom SHA-256 sa nová aplikácia neaktivuje a pôvodná zostáva spustiteľná.
- Sťahovanie má celkový limit 180 sekúnd a limit nečinnosti 15 sekúnd. Uložený záznam umožní po reštarte nahlásiť prerušenie alebo potvrdiť nový obraz bez opakovania inštalácie.
- Táto Arduino konfigurácia nezapína automatický bootloader rollback ani Secure Boot. SHA-256 a označenie produktu chránia integritu a omyl pri výbere; nenahrádzajú podpis firmvéru. Inštaluj iba dôveryhodné zostavenie projektu. Ak nový program nedokáže ani správne naštartovať, môže byť potrebná obnova cez USB.

## Príprava ďalšej verzie

Zmeň `FPS_VERSION` v [firmware_version.h](../firmware/src/firmware_version.h), zostav `pio run` a použi `.pio/build/esp32dev/firmware.bin`. Tento súbor je aplikačný obraz; zlúčený obraz celej flash ani samotný bootloader nie sú určené pre tento panel. Označenie verzie zadané v aplikácii sa musí zhodovať s označením zabudovaným pri zostavení.

API a vnútorné stavy sú popísané v [API dokumentácii](../api/README.md). Záznamy a binárne obrazy sú uložené v SQLite; sú zahrnuté v bežnej databázovej zálohe. Zachováva sa posledných 20 položiek v zobrazení, uložené obrazy sa automaticky nemažú.

## Overené na zariadení

Dňa 17. 11. 2026 bola po prvotnej USB migrácii úspešne vykonaná Wi-Fi reinštalácia 2.0.0 cez živý server. ESP32 prešlo zo slotu 0 do slotu 1, potvrdilo hash nového bežiaceho obrazu a znovu pripojilo oba mosty. Brother zostal pripravený a nastavenia aj tlačové dáta aplikácie sa zachovali. [Rozsah skúšok](ACCEPTANCE.md#wi-fi-aktualizácia-esp32--server-040-firmvér-200).
