# spel-ai-kompisen — plan för en självständig agent (utkast för granskning)

**Datum:** 2026-10-01 · **Skriven av:** Claude, på Samans begäran · **Status:** förslag.
Inget är byggt utom Vakten (fas 0), som pågår i Spelkompisen. Saman rådfrågar Codex
innan han svarar på de öppna frågorna i avsnitt 9.

## 1. Varför

Saman vill att en AI-agent följer upp hela tiden, i stället för att han själv ska upptäcka
fel och be någon kontrollera. Exempel på vad som missats den senaste månaden:

| Vad | Hur länge | Upptäcktes av |
|---|---|---|
| Sofascore svarar 403 i varje källtest | sedan 2026-09-25T10:43Z (6 dygn) | Claude av en slump, 2026-10-01 |
| Kupongdetaljen kraschade (från Claudes driftsättning 24/9) | 24–27/9 | Saman |
| Testsviten röd | ett dygn, 2026-09-02 | i efterhand |
| Stryktipset 4971 frystes med Pinnacle-priser från 15/9 | upptäckt 24/9 | statusauditen 24/9 |

Sofascore-felet är en antibot-utmaning (`"reason": "challenge"` med webbläsarsignatur).
Enligt källgränsen ska vi inte lösa sådana utmaningar. Felet slår mot
resultat för ligor utan football-data, frånvarodata och modellstatistik — inte mot
kupongerna, som bygger på Pinnacle och Svenska Spel.

## 2. Agentens mål

Samans mål:

1. **Pool:** maximera vinstchanserna på Stryktipset, Europatipset och Topptipset — med
   olika strategier för små system (256 kr) och stora system (20 000 kr), mot olika
   rimliga utdelningsspann.
2. **Odds:** en modell som förutser oddsrörelser eller på annat sätt pekar ut spelvärden.
3. **Live:** en modell som förutser spelvärda ögonblick i matcher (över/under eller sida)
   ur liveodds, livestatistik och förväntad matchbild och odds före matchen.
4. **Felsökning:** endpoints som slutar svara, siffror som saknas och liknande.
5. **Mer data:** fler källor eller annat som hjälper det dagliga arbetet.

Claudes förslag på ytterligare mål:

6. **Spelbeslut och insats:** veckobudget, insats per omgång och ett tydligt "avstå" när en
   omgång saknar värde.
7. **Genomgång av Samans egna kuponger:** 77 bokförda, 24 224 kr insatt på rättade
   kuponger, 12 648 kr tillbaka (ROI −47,8 %). Vad kostade mest?
8. **Agentens egen kostnad mot nytta.**

## 3. Två projekt

- **Spelkompisen** (som i dag): den stabila basen med insamlingen och de förregistrerade
  mätningarna. Underhålls som nu av Claude och Codex på begäran. Får Vakten.
- **spel-ai-kompisen** (nytt, privat repo): en gaffel av Spelkompisen där agenten får
  ändra allt — kod, modeller och UI — för att nå målen. Sidan ska fortfarande gå att
  använda för Saman. Agenten fattar egna beslut inom ramarna nedan.

Varför ett sidoprojekt: Spelkompisens mätregler (förregistrering, manifest, ingen
bakfyllning) gör den långsam att ändra men pålitlig. I sidoprojektet kan agenten röra sig
snabbt utan att förstöra pågående mätningar.

## 4. Tre villkor

### 4.1 Agenten får ändra allt utom facitmotorn

En agent som både väljer modell och själv avgör vad som räknas som bra hittar alltid en
"vinnare" i bruset. Spelkompisen har redan varit där: +6,6 % visade sig vara +2,65 % när
räknesättet rättades (2026-07-24).

- Varje modell fryser sina prognoser **före** avspark eller spelstopp i en append-only-
  ledger: tid, modellversion och indata.
- En fast facitmotor räknar utfallet:
  - **odds:** CLV mot Pinnacles stängning, samt logloss mot utfall;
  - **pool:** verkligt utfall och publicerad utdelning, utspädd med egna vinnande rader
    (samma metod som PH3);
  - **live:** förregistrerad regel per signaltyp.
- Gränsen för när en idé blir ett **råd till Saman** står i facitmotorn och sätts inte
  av agenten från fall till fall. Förslag: ärv Spelkompisens gränser (avsnitt 9, fråga 9).
- Agenten får inte ändra facitmotorn, poängreglerna eller historiska rader. Sådana
  ändringar blir ⚖ till Saman.

### 4.2 Sidoprojektet läser Spelkompisens data men kör aldrig en egen kopia av insamlingen

- Databasen är den verkliga tillgången: månader av observationer som aldrig går att
  återskapa. Sidoprojektet läser den read-only (`mode=ro`) och har en egen databas för
  sitt eget.
- Egna kopior av insamlarna skulle dubbla trafiken mot Pinnacle och Svenska Spel och öka
  risken att servern spärras. Då faller båda projekten. Sofascore har redan stängt ute oss.
- Nya källor får läggas till, inom källgränsen och med egen hälsologg.

### 4.3 De fasta gränserna gäller även agenten

- Lägg aldrig spel automatiskt — bara deep-link eller fil; Saman laddar upp och betalar.
- Källgränsen: inga lösningar av antibot-utmaningar, ingen återspelning av sessioner,
  cookies eller WAF-token, inga konton eller inloggningar hos källor.
- Rör aldrig `/Users/saman/svs` eller `/Users/saman/vm`.
- Skriv aldrig i Spelkompisens databas. Ändringar i den egna databasen görs med skript,
  backup och rapport.
- Inga hemligheter i repot, och aldrig en databas i ett publikt repo.
- Klicka aldrig i cookie- eller samtyckesrutor.
- Kör aldrig samma insamlare på två ställen.

## 5. Drift

- **Server:** MacBook-servern 192.168.50.100, alltid på.
- **Portar:** backend 8003 och frontend 5176 (båda lediga 2026-10-01). Spelkompisens
  8002/5175/5181 rörs inte.
- **Driftsättning:** bara när testerna och ett prov av appen i headless Chrome på servern
  är gröna. Blir hälsan röd efter en driftsättning rullar agenten tillbaka automatiskt.
- **Resurser:** tunga beräkningar körs med låg prioritet (`nice`), så att Spelkompisens
  insamling aldrig trängs undan.

## 6. Hur agenten körs

- **Claude Code på servern**, inloggad med Samans Claude-konto.
- **En långlivad session** i tmux, bevakad av launchd. Dör den startas den om och
  fortsätter samma samtal.
- **Remote Control:** sessionen syns i Claude-appen på mobilen, på claude.ai och i
  desktopappen som en vanlig chatt. Saman kan skriva till den var han än är.
- **Schema:** sessionen väcker sig själv (avsnitt 7) och väcks av Vakten vid nytt rött larm.
- **Minne i filer** i sidoprojektets repo: `agent/mal.md`, `agent/journal.md`,
  `agent/beslut.md` och en prioriterad forskningskö `agent/ko.md`. Inget viktigt försvinner
  när samtalet komprimeras eller sessionen startas om.
- **Behörigheter:** en lista över tillåtna kommandon i sidoprojektets
  `.claude/settings.json` plus auto-läge. Inga behörighetsfrågor ska behövas.
- **Kommunikation:** en 🤖-vy i sidoprojektet visar vad agenten gjort och beslutat, facit
  per modell, kupongråd och öppna ⚖. Inga push-notiser (Samans regel 2026-09-02).

### Varför inte en molnsession

En molnsession når inte 192.168.50.100 (Claude Codes dokumentation för webbsessioner).
Den skulle sakna databasen, loggarna och tjänsterna, och den kan inte driftsätta.
Alternativen är sämre:

- öppna servern mot internet — en säkerhetsrisk;
- kopiera databasen till molnet varje natt — då arbetar agenten på gårdagens data, och
  livespel, kupongråd 3 h före spelstopp och felsökning i realtid faller bort.

Remote Control ger samma åtkomst från alla enheter, medan agenten körs där datan finns.

### Följder av Remote Control

- Remote Control kräver inloggning med Samans Claude-konto. Det fungerar inte med en
  API-nyckel och enligt dokumentationen inte heller med `claude setup-token`.
- Agenten delar alltså Samans användningskvot. Därför gör Vakten grovjobbet utan AI, och
  agenten vaknar bara enligt schemat och vid larm.

## 7. Schema (förslag)

| Vad | När | AI |
|---|---|---|
| Insamling (Spelkompisen) | som i dag | nej |
| Vakten | var 30:e minut | nej |
| Frysning och facit (sidoprojektet) | vid horisonter och efter avgörande | nej |
| Morgonrunda: larm, felsökning, rättningar, prov av appen, rapport | 07:00 | ja |
| Forskningspass, ett mål i taget enligt kön | 1–2 per dag | ja |
| Kupongråd med motivering | 3 h före spelstopp för valda spel | ja |
| Utredning vid nytt rött larm | vid behov, högst 3 per dygn | ja |
| Genomgång av gränssnittet | söndagar | ja |

Första veckan: morgonrunda, ett forskningspass per dag och kupongråd för Stryktipset och
Europatipset. Därefter skalar vi efter hur kvoten räcker. Fler körningar ger inte mer
kunskap; ny data gör det.

## 8. Faser

| Fas | Innehåll | Förutsättning |
|---|---|---|
| 0 (pågår) | Vakten i Spelkompisen: källor, jobb, backendfel, driftläge, nattliga tester, disk, avläsningspunkter. Larm i Idag. | — |
| 1 (1–2 dagar) | Privat repo, gaffel, egen port och databas, facitmotor v1 (återanvänder PH3- och WP5-ledgerns logik), session med tmux, launchd och Remote Control, behörighetslista, 🤖-vy, morgonrunda. | Saman loggar in Claude på servern och svarar på avsnitt 9. |
| 2 (vecka 1) | Forskningspass enligt kön, första kupongråden, genomgång av Samans kuponger. | Fas 1 klar. |
| 3 (efter vecka 1) | Utvärdering: kvot, kvalitet, fel. Beslut om att skala upp eller ned. | — |

**Avbrottsregel:** Bryter agenten något i Spelkompisen, eller tar kvoten slut så att Saman
inte kan arbeta, pausas agenten tills reglerna ändrats.

## 9. Öppna frågor till Saman

1. **De tre villkoren:** godkänns fast facitmotor, ingen dubbel insamling och de fasta gränserna?
2. **Kvoten:** är det OK att agenten delar din prenumeration (Remote Control kräver det)?
   Vilket tak för antal körningar per dag?
3. **Repo:** privat `t0mteee/spel-ai-kompisen`?
4. **Självständighet i sidoprojektet:** får agenten driftsätta allt själv efter gröna tester
   och prov av appen? Eller vill du godkänna vissa slag av ändringar först, till exempel
   sådant som ändrar kupongråden?
5. **Tillbaka till Spelkompisen:** vem flyttar en idé som bevisat sig i sidoprojektet till
   Spelkompisen? Förslag: bara du, via ⚖, efter facit.
6. **Kupongråden:** ska de synas även i Spelkompisen eller bara i sidoprojektet?
   Vilka spel ska få kupongråd 3 h före spelstopp — Stryktipset, Europatipset och vilka
   Topptipset-varianter?
7. **Din spelbudget:** ska agenten föreslå veckobudget och insats per omgång?
8. **Codex roll:** förslag — Codex fortsätter i Spelkompisen och agenten arbetar ensam i
   sidoprojektet. Två agenter i samma repo krockar lätt.
9. **Gränserna i facitmotorn:** förslag — ärv Spelkompisens:
   - pool: minst 40 parade omgångar och BH-FDR 10 %;
   - odds: CLV-grönt v2 (minst 50 stängda och undre bootstrap-KI-gräns > 0);
   - live: minst 200 matcher, minst 60 dagar och undre KI90 > 0.
10. **Resurser:** får agenten köra tunga beräkningar på servern med låg prioritet?
    Tak för disk och CPU?
11. **Sofascore:** ersätta den med Flashscore och FotMob i Spelkompisen nu (⚖ — påverkar
    V2.2:s fingeravtryck, där SOFA_UT ingår), eller låta agenten ta det i sidoprojektet?

## 10. Frågor till Codex

1. Risker med att läsa Spelkompisens SQLite-databas read-only från en annan process
   medan insamlingen och det nattliga `.backup`-jobbet skriver (WAL, lås)?
2. Bör delad kod — till exempel `svenskaspel.py`, `pinnacle.py` och poolens
   settlementlogik — brytas ut till ett gemensamt bibliotek i stället för att gafflas?
   Annars glider rättningar isär mellan projekten.
3. Krockar planen med något du har pågående eller planerat (till exempel
   navigationsplanen från 2026-09-13)?
4. Saknas något mål, eller är något av målen orealistiskt med gratiskällor?

## 11. Inte verifierat ännu

- Hur länge en självväckande loop får pågå i en Remote Control-session. launchd vakar
  därför över sessionen och startar om den vid behov; det provas i fas 1.
- Om behörighetsfrågor verkligen visas i mobilappen via Remote Control. Saman ser inte
  desktopappens frågor på mobilen i dag. Målet är att inga frågor ska behövas alls.

## 12. Realistiska förväntningar

- **Pool:** spelen behåller 30–40 % av insatserna (Stryktipset betalar tillbaka 59,8 %,
  Europatipset 63,7 %, Topptipset 70 %). Överskott uppstår bara när folket streckar fel
  eller när det finns rullpott. Ett av agentens viktigaste råd blir när Saman ska avstå.
- **Facit tar tid:** ett system behöver cirka 40 omgångar. För Topptipset tar det ungefär
  en månad, för Stryktipset och Europatipset 20–40 veckor. I dag har standardjämförelsen
  68 parade omgångar på Topptipset, 8 på Europatipset och 4 på Stryktipset. Agenten bör
  börja där facit kommer snabbt: Topptipset, värdeflaggorna i Oddset och historiska
  omgångar.
- **Live:** Saman lägger spelen själv, så ett spelvärt läge måste hålla i minst en minut.
- **De första månaderna** handlar troligen mest om att visa vad som inte fungerar. Det är
  också värt något.
