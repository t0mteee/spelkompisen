# Överlämning — importera en glömd spelad kupong

Datum: 2026-08-29
Status: implementerad, testad och avsedd för drift. Inga spel läggs.

## Användarflödet

Under **Historik → Dina spelade kuponger** finns nu **Välj radfil**. Den är
avsedd för fallet där Saman faktiskt lämnade in och betalade en kupong hos
Svenska Spel men glömde trycka ”Spelad kupong” i Spelkompisen.

1. Välj den `.txt`-fil som kupongbyggaren skapade för **Egna rader**.
2. Appen visar spel, omgång, antal rader, antal matcher och kostnad utan att
   skriva i databasen.
3. Bekräfta med **Bokför och följ kupongen**.
4. Kupongen hamnar i samma ledger och får samma liverättning/facit som om den
   märkts spelad direkt. Är omgången redan settlad lokalt sätts facit direkt.

Har filen döpts om kan produkt och omgång anges manuellt under den utfällbara
hjälpen. Det är främst omgången som behövs: Stryktipsets och Europatipsets
rubrikrad innehåller inget `Omg=`. Våra ordinarie filnamn
`svs_<produkt>_omg<nummer>_egnarader.txt` bär därför identiteten.

## Säkerhets- och datakontrakt

- Importen lägger, laddar upp eller betalar aldrig ett spel. Filinnehållet
  skickas bara till Spelkompisens egen backend för validering/bokföring.
- Förhandsgranskningen är helt läsande. Skrivning sker först efter en separat
  uttrycklig bekräftelse.
- Produkt i rubrik, filnamn och manuellt val samt omgång i rubrik, filnamn och
  manuellt val måste vara identiska när flera av dem finns. Konflikt avvisas.
- Endast `E`-rader med `1/X/2` stöds. Bredden måste vara 13 för
  Stryktipset/Europatipset och 8 för Topptipset. Dubblettrader och fler än
  20 000 rader avvisas. Bomben stöds inte av denna ledger.
- Samma produkt + omgång + exakta raduppsättning är idempotent. UI säger att
  kupongen redan finns i stället för att dubbla satsad kostnad.
- En import lagras som `build_kind=egna-rader-import`, med not om att faktisk
  speltidpunkt är okänd och att filen inte är ett betalningskvitto.
- En okänd men explicit omgång får bokföras: spelade kuponger ingår redan i
  `pool_settlement.settle_recent`-kandidatlistan och kommer därför att hämtas
  och rättas av ordinarie insamlingsvarv.
- Ingen schemändring, migration eller bakfyllning gjordes.

## Kod och API

- `backend/app/pool_played.py`: strikt parser, read-only-preview,
  dubblettkontroll, bokföring och direkt settlement mot redan lokalt facit.
- `POST /api/pool/played/import/preview`: JSON med `filename`, `text` och
  valfria `product`/`draw_number`; returnerar en liten förhandsgranskning.
- `POST /api/pool/played/import`: validerar samma underlag igen och bokför
  idempotent.
- `frontend/src/App.jsx`: mobilanpassad välj/preview/bekräfta-UI i
  `PlayedPanel`. Importen syns även när historiken ännu är tom.
- `frontend/src/AppV3.jsx` och `frontend/src/App.css`: korrekt hjälptext och
  responsiv presentation.

## Test och fortsatt kontroll

Backendtesten täcker Strykfil utan skrivning, omdöpt fil med manuellt val,
Topptipsvariant och Insats, identitetskonflikt, trasiga tecken, idempotens och
omedelbart facit. Frontendtest, lint och produktionsbygge ska vara gröna före
drift.

Första verkliga importen bör verifieras i Historik genom att kontrollera att
produkt, omgång, kostnad och exakta rader är samma som på den betalda
kupongen. Funktionen bevisar avsiktligt inte betalning; användaren är den enda
källan till att kupongen faktiskt spelades.
