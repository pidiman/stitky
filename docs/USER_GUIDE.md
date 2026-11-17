# Používanie Fajny Print Studio

[Späť na projekt](../README.md) · [LED](LED.md) · [Riešenie problémov](TROUBLESHOOTING.md)

## Prihlásenie a prvý účet

Na čerstvej databáze použi **admin / admin**. Pred otvorením štúdia musíš nastaviť e-mail, prezývku a nové heslo s dĺžkou 10–128 znakov. Prezývka môže mať najviac 60 znakov. Po tomto kroku sa prihlasuješ nastaveným e-mailom; úvodný alias admin prestane platiť.

Prihlásenie trvá 12 hodín. Po vypršaní sa prihlás znovu. Po piatich chybných pokusoch pre kombináciu IP adresy a prihlasovacieho mena sa ďalší pokus dočasne obmedzí; rozhranie môže vyžiadať čakanie 15 minút.

Správca zapína registráciu v **Môj účet → Registrácia účtov**. Predvolene je vypnutá aj na serveri. Nové účty majú rolu bežného používateľa. Účty zdieľajú šablóny a front; nejde o súkromné knižnice každého používateľa. Správca navyše môže vytvárať zariadenia a riadiť nastavenie registrácie.

Projekt nemá e-mailové overovanie ani samoobslužný reset zabudnutého hesla. Nestrácaj prístup správcu a zálohuj databázu; jej zmazanie by zmazalo aj front a šablóny.

## Textový štítok

1. V editore vyber textový režim a napíš obsah.
2. Vyber font a automatickú alebo pevnú veľkosť.
3. Uprav zarovnanie a štýl. Sleduj serverový náhľad.
4. Vyber tlačové zariadenie a počet kópií.
5. Použi tlačidlo tlače. Výsledok sleduj medzi poslednými úlohami alebo v celom fronte.

Text má najviac 200 znakov a štyri riadky. Automatická veľkosť sa pokúsi vyplniť dostupný priestor; ručne nastavený text, ktorý sa nezmestí, sa odmietne namiesto orezania. Tlačidlo zostáva neaktívne pri neplatnom náhľade.

| Nastavenie | Rozsah a poznámky |
|---|---|
| TrueType font | Sans, Sans Bold, Serif, Sans Mono; podporujú diakritiku |
| Pixelový font | Autorské 5 × 7, malé ASCII prevedie na veľké; diakritiku odmietne |
| Veľkosť | Auto alebo 6–64; pixelový font používa násobky 7 do 63 |
| Zarovnanie | Vľavo, stred, vpravo |
| Štýl | Tučné, kurzíva, podčiarknutie |
| Medzery písmen | 0–6 bodov |
| Medzery riadkov | 0–16 bodov |
| Ďalšie úpravy | Rámik, inverzia biela na čiernom |

Náhľad je monochromatický obraz zo servera. Rovnaké pixely sa otočia do rastra tlačovej hlavy; rozhranie nekreslí nezávislú približnú napodobeninu.

## Symboly a emotikony

Tlačidlo symbolu ho vloží na miesto kurzora. Podporovaná čiernobiela paleta obsahuje napríklad:

```text
☺ ☹ ♥ ★ ✓ ✕ ⚠ ⚡ → ← ↔ ↑ ↓
```

Vybrané bežné emoji majú monochromatické ekvivalenty. Farebné emoji, zložené sekvencie a ľubovoľné symboly nie sú automaticky podporované. Pri odmietnutí znaku ho odstráň alebo nahraď prvkom z palety. P15 tlačí čiernobielo.

## QR kód z textu alebo odkazu

1. Prepni editor na QR.
2. Vlož text alebo celý odkaz, napríklad `https://example.com`.
3. Voliteľne vyplň **Popis vedľa QR kódu**. QR zostane vľavo, popis sa vytlačí vpravo. Bez popisu je QR na strede.
4. Pre popis môžeš vybrať font, veľkosť, zarovnanie a textový štýl. Počkaj na serverový náhľad.
5. Vyber zariadenie, kópie a odošli do frontu.

QR sa vycentruje na štítku a má biely okraj štyri moduly. Server používa korekciu M a celočíselnú mierku aspoň dva tlačové body na modul. Príliš dlhý alebo hustý obsah odmietne. Skráť ho; nevynucuj menší nečitateľný kód. Písmo a textové štýly sa používajú iba na popis. Inverzia a rámik zostávajú pre QR štítok vypnuté, aby sa zachoval biely okraj. Popis môže mať najviac 120 znakov a štyri riadky; príliš veľký text sa odmietne namiesto orezania.

Aj QR podlieha limitu obsahu 200 znakov; praktický limit podľa hustoty môže byť nižší. Pred dôležitým použitím skontroluj načítanie fyzického štítku vlastnou čítačkou.

## Šablóny

Rozpracovaný štítok pomenuj a ulož ako šablónu. Ukladá sa obsah, režim text/QR, font aj formátovanie. Kliknutím na šablónu obnovíš nastavenia v editore; samotné načítanie nespúšťa tlač. Šablónu možno zmazať. Úprava šablóny nemení raster už vytvorenej úlohy.

## Výber zariadenia a tlačový front

Každé ESP32 má vlastné ID, názov, token a cieľovú tlačiareň. Server doručuje úlohu len určenému zariadeniu. Offline most môže dostať čakajúcu úlohu; tá sa fyzicky nespracuje, kým sa most nevráti.

| Stav API | Význam | Ďalší krok |
|---|---|---|
| queued | Čaká na prevzatie | Možno zrušiť, prípadne počkať na most |
| leased | Most úlohu rezervoval | Prebieha príprava pred tlačou |
| printing | Server povolil začiatok | Čakaj na výsledok |
| printed | P15 poslala AA/OK | Skontroluj fyzický štítok podľa potreby |
| failed | Hlásené zlyhanie | Pozri správu chyby a zariadenie |
| unknown | Výsledok nie je istý | Fyzicky skontroluj tlač pred novou úlohou |
| cancelled | Zrušená čakajúca úloha | Táto úloha sa už netlačí |

Jedna až desať kópií vytvorí rovnaký počet samostatných úloh. Zrušiť možno iba čakajúcu úlohu. Po začatí sa úloha nevracia automaticky do frontu, aby nevznikali duplicitné výtlačky. Opakované kliknutie rieši aj idempotentný kľúč požiadavky.

## Zariadenia a telemetria

Karta tlačiarne ukazuje dostupný model, verziu, batériu, stav a čas posledného overenia. Detail zariadenia môže obsahovať aj sériové číslo P15, silu Wi-Fi RSSI, čas behu a verziu firmvéru ESP32.

**Online most a pripojená tlačiareň sú rôzne údaje.** Server označí most ako online pri kontakte za posledných 45 sekúnd. BLE sa nedrží stále otvorené. Údaj o batérii patrí k času posledného skutočného čítania; nezaručuje aktuálny stav.

Tlačidlo obnovenia iba požiada o nové čítanie. Most ho vykoná pri prázdnom fronte, mimo tlače a najviac raz za minútu. Údaje staršie ako päť minút rozhranie označuje. Chýbajúca odpoveď neznamená 0 % batérie ani potvrdenú pripravenosť.

## Pridanie ďalšieho miesta tlače

Správca v Zariadeniach vytvorí nový most a uloží jeho jednorazovo zobrazený token. Na druhom ESP32 sa nastaví rovnaké API, nový token a MAC jeho vlastnej P15. Wi-Fi sa nastaví pre danú lokalitu. Potom v editore vyberieš požadované zariadenie. Podrobnosti sú v [nasadení](DEPLOY.md).

## Kde hľadať pomoc

Farby mosta vysvetľuje [LED návod](LED.md). Pri nejasnej tlači, offline stave, chybe náhľadu alebo prihlásenia použi [riešenie problémov](TROUBLESHOOTING.md).

## Brother QL-810W

Najprv v tlačových nastaveniach vyber Brother zariadenie. V editore sa objaví voľba rolky, pri súvislej páske dĺžka 20–200 mm a voľba automatického orezu. Rozmery náhľadu a DPI sa prispôsobia tlačiarni. Šablóny si pamätajú aj formát, dĺžku a orez; pri použití sa vyberie dostupné zariadenie príslušného typu.

Založená rolka v karte tlačiarne je čítaná cez IPP. Musí zodpovedať zvolenému formátu. Pri nesúlade sa tlač neposiela. Pozastavené zariadenie má tlačidlo tlače vypnuté. Po prvom nahratí a nastavení ESP32 je potrebné trvalé spojenie overiť; podrobnosti sú v [Brother návode](BROTHER.md).

Dokončenie Brother IPP úlohy a potvrdenie AA/OK od P15 sú odlišné zdroje stavu printed; oba vyžadujú fyzickú kontrolu, ak potrebuješ potvrdiť kvalitu štítku.
