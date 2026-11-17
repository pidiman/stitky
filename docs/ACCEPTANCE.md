# Overenie verejnej kópie

- API a USB provisioning: 163 testov prešlo.
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
