# Brother QL-810W cez existujúce ESP32

[Projekt](../README.md) · [Používanie](USER_GUIDE.md) · [Firmvér](../firmware/README.md)

## Ako je Brother pripojený

```text
Fajny Print Studio / API
           ↕ overované HTTPS
         ESP32
          ├─ BLE → MarkLife P15
          └─ Wi-Fi / IPP → Brother QL-810W
```

Samostatné Raspberry Pi nie je potrebné. ESP32 a Brother musia mať vzájomne dostupné sieťové spojenie. Server môže zostať mimo domácej LAN; tlačiareň sa nevystavuje do internetu. Každá tlačiareň má v štúdiu vlastné zariadenie a vlastný token, hoci obe obsluhuje jedna doska.

Rozšírenie vyžaduje **firmvér ESP32 1.3.2**. Starší firmvér 1.2.1 podporuje len P15 a nemá vzdialenú aktualizáciu. Na prvé nahratie je potrebný dátový USB kábel; potom zariadenie opäť funguje samostatne cez Wi-Fi.

## Aktuálny rozsah

| Médium | Dĺžka | Výstup |
|---|---|---|
| DK 29 mm, súvislá páska | 20–200 mm | 300 × 300 dpi, čiernobielo |
| DK 62 mm, súvislá páska | 20–200 mm | 300 × 300 dpi, čiernobielo |
| DK 29 × 90 mm | Pevná | 300 × 300 dpi, čiernobielo |
| DK 62 × 100 mm | Pevná | 300 × 300 dpi, čiernobielo |

Text, QR s popisom, fonty, štýly a šablóny sú spoločné s P15. Je možné zapnúť alebo vypnúť automatický orez. Dvojfarebná čierno-červená tlač a režim 600 dpi nie sú súčasťou tejto implementácie. Použi vhodnú čiernobielu DK rolku; tlač na dvojfarebnom médiu nebola overená.

Zvolený formát musí zodpovedať založenej rolke. Most pred odoslaním tlače kontroluje identitu QL-810W, dostupnosť IPP, pripravenosť a presnú šírku/dĺžku média. Pri nesúlade sa úloha ukončí chybou bez odoslania tlačových dát.

## Nastavenie

1. Pripoj Brothera k domácej Wi-Fi a v routeri mu rezervuj stabilnú IP adresu.
2. Over, že ESP32 sa z jeho siete dostane na túto adresu a port 631. Hosťovská izolácia medzi zariadeniami môže spojenie blokovať.
3. Správca vytvorí v Zariadeniach nové zariadenie typu **Brother QL-810W · Wi-Fi** a uloží jednorazovo zobrazený token.
4. Nahraj firmvér 1.3.2 podľa [ESP32 návodu](../firmware/README.md). Počas nahrávania nesmie prebiehať tlač ani zostať nevyriešený výsledok.
5. Cez USB nastav len nové Brother polia:

```sh
.venv/bin/python firmware/tools/configure_brother.py \
  --port /dev/cu.SLAB_USBtoUART \
  --host 192.0.2.10
```

Adresa a port v príklade sa musia nahradiť vlastnými. Nástroj si vyžiada token Brother zariadenia skryto. Voliteľné `--token-file` číta súkromný súbor. Existujúci token P15, jej MAC, API, certifikát a Wi-Fi sa zachovajú.

6. Po reštarte skontroluj USB `STATUS` a čítací príkaz `BROTHER_CHECK`. Ten zobrazí odpoveď IPP, pripravenosť, model a založené médium; nič nevytlačí.
7. V štúdiu vyber Brothera a rovnakú rolku, priprav náhľad a po overení mosta povoľ tlač, ak bola administrátorsky pozastavená.
8. Prvý fyzický štítok odošli vedome zo štúdia. Skontroluj orientáciu, dĺžku, orez a načítanie QR.

Kľúč a skutočná IP ostávajú v súkromnej konfigurácii ESP32, nie v zdrojovom kóde. Zmena cieľa alebo tokenu je zakázaná, pokiaľ je na doske nevyriešená úloha.

## Pamäť a prenos

Brother používa podstatne väčšie štítky ako P15. Server vytvorí natívny raster a príkazy podľa Brother Raster Command Reference. ESP32 dostane iba malý manifest a stiahne overený binárny obsah do **LittleFS**, nie ako veľký JSON/base64 reťazec do RAM.

Payload má limit 250 000 bajtov. Overuje sa veľkosť a SHA-256 pred štartom. Súbor sa po potvrdenom nahlásení výsledku odstráni. LittleFS sa pri prvom použití naformátuje ešte pred pripojením; tým sa predíde pádu pri starých dátach pripomínajúcich väčší súborový systém. Rozpracovaná úloha formátovanie blokuje; už použitý poškodený spool sa automaticky neformátuje. NVS záznam rozpracovanej úlohy zostáva oddelený od súboru.

Aktuálny profil huge_app má 3 MB aplikačnú partíciu a samostatnú dátovú partíciu. Nahráva sa aplikácia; pri bežnej aktualizácii nemaž celú flash ani NVS.

## Výsledok tlače a obnova po výpadku

Po kontrole média ESP32 požiada server o začiatok, uloží stav a odošle jednu IPP úlohu. IPP číslo úlohy sa uloží do NVS. Most sleduje jej stav; neoznačí odoslanie bajtov samo osebe za úspech.

`printed` pri Brotheri znamená, že tlačiareň v IPP nahlásila dokončenú úlohu bez hlásených chýb. Nejde o optickú kontrolu fyzického štítku. Správa výsledku odlišuje toto potvrdenie od AA/OK pri P15.

Ak sa stratí odpoveď na odoslanie alebo nastane nejasný výsledok, fyzické zadanie sa **automaticky neposiela znovu**. Po reštarte s uloženým IPP číslom možno dočítať stav úlohy; inak zostane výsledok neistý. Samotné nahlásenie výsledku serveru sa môže opakovať. Ak server už výsledok nemôže prijať, pending záznam sa zachová na posúdenie operátorom.

## Čítanie stavu

IPP Get-Printer-Attributes číta model, stav a `media-ready`, napríklad príkladové `roll_current_29x0mm`. Vo webe sa zobrazí ako „29 mm · súvislá páska“. Tento dotaz nevytvára úlohu ani nehýbe papierom.

Stav sa pri nečinnosti obnovuje približne každých 30 sekúnd a po vyžiadaní z webu. Batéria, sériové číslo či verzia firmvéru Brothera sa nevymýšľajú, ak ich tento spôsob čítania nevracia.

Pri prenose a čakaní sa používa tyrkysová LED. Po potvrdenom dokončení a prijatí výsledku serverom nasleduje zelený efekt. Chybu/neurčitý výsledok signalizuje červená. Fialová je naďalej určená BLE spojeniu P15.

## Overenie a limity

Softvérové kontroly pokrývajú natívne rozmery, raster/preview zhodu, orez, oddelenie tokenov, sťahovanie iba s platnou rezerváciou, staré úlohy P15 a IPP parser vrátane poškodených správ. Nezávislý QR dekodér číta QR s popisom na všetkých štyroch profiloch. Zostavenie firmvéru a webu prešlo.

Firmvér 1.3.2 bol nahratý na ESP32 a overený po opakovanom štarte: zachoval nastavenia P15/Wi-Fi, cez IPP priamo potvrdil QL-810W v stave idle s 29 mm súvislou rolkou a odoslal stav ready aj správne médium na server. Fyzický výtlačok ešte treba vedome vyskúšať zo štúdia; čítanie stavu ho nenahrádza.

## Zdroje protokolu

- [Brother Raster Command Reference v1.01](https://download.brother.com/welcome/docp100278/cv_ql800_eng_raster_101.pdf)
- [IPP/1.1 encoding and transport, RFC 8010](https://www.rfc-editor.org/rfc/rfc8010.html)
- [IPP model and semantics, RFC 8011](https://www.rfc-editor.org/rfc/rfc8011.html)

## Ak prvá tlač zostane zaseknutá

Použi server 0.3.1 a firmvér ESP32 1.3.2 alebo novší. Táto oprava zachováva štandardné poradie úvodných raster príkazov, posiela spool v blokoch a ukončuje IPP spojenie po požiadavke. Staršia kombinácia mohla zostať v stave job-incoming / spool-area-full-report bez výtlačku. Neistú úlohu automaticky neopakuj. Po kontrole štítku zruš iba konkrétnu zaseknutú úlohu alebo reštartuj tlačiareň; po návrate do ready možno vedome vytvoriť novú úlohu. Podrobnosti overenia sú v [akceptačných kontrolách](ACCEPTANCE.md).
