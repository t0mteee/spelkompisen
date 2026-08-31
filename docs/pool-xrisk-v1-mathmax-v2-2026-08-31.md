# Poolens X-risk v1 och matematiskt max v2 — förregistrering

Datum: 2026-08-31

Status: fryst innan kod, testrekonstruktion och nästa forwardfrysning. Beslutet
kommer från mänsklig granskning av Europatipset 2603, inte från att något av de
två spanska faciten råkade bli X: båda slutade utan kryss, men konstruktionen
bar ändå en oskäligt koncentrerad gemensam risk.

## Problemet som ska lösas

Matematiskt max v1 tog bort X helt i både Deportivo–Valencia och Celta
Vigo–Athletic. Vid m20 var Pinnacles X-priser 2,99 respektive 3,26 och
huvudtotalerna 2,0 respektive 2,25. Modellen såg 1X2 men premierade
streckvärdet så hårt att ett cirka 30-procentigt utfall fick exakt noll
täckning i två lågmålsmatcher samtidigt.

V1-formen 4 helgarderingar + 9 halvgarderingar gav 41 472 rader men saknade
spikar. Den köpte bred lokal täckning utan tydliga ankare och spred därmed
insatsen över många kombinationer med låg gemensam övertygelse.

## Gemensam draw-risk-regel

Version: `pool-draw-risk-v1`.

Sannolikheten för X tas från komplett, deviggad sharp 1X2 när den finns,
annars från systemanalysens vanliga deviggade 1X2. Pinnacles huvudtotal sparas
point-in-time tillsammans med poolens sharpobservation. En match skyddas när:

- X-sannolikheten är minst 29,5 procent (cirka 30) och huvudtotalen är
  högst 2,25; eller
- X-sannolikheten är minst 32 procent även när en användbar total saknas.

Den ursprungliga förregistreringstexten angav 30,0 procent. Acceptansens
rekonstruktion före driftsättning visade att Celta–Athletics exakta m20-priser
2,74/3,26/2,81 blir 29,765 procent efter samma power-deviggning som byggaren,
trots att prisbilden i granskningen korrekt sammanfattades som cirka 30
procent. Gränsen frystes därför slutligt till **29,5 procent** innan någon ny
forwardkupong skapades. Deportivo–Valencias 2,66/2,99/3,16 ger 32,550 procent.
Detta är en korrigering av en avrundningsklippa i det observerade
problemfallet, inte en justering mot facit; båda matcherna slutade utan X.

En total över 2,25 kan aldrig ensam skapa skydd. Total och X-pris ska inte
räknas som två oberoende sannolikhetskällor; totalen fungerar som ett
strukturellt villkor på den redan deviggade 1X2-bilden.

För automatiskt valda system gäller:

- en halvgardering i en skyddad match måste innehålla X plus den
  sannolikaste av 1 och 2;
- vanliga automatiska matematiska/reducerade system avsätter tillgängliga
  halvgarderingar till skyddade matcher innan resterande budget optimeras;
  räcker budgeten inte till alla prioriteras högst X-sannolikhet;
- EV-/värderadportföljer måste lägga minst
  `min(20 %, max(10 %, X-sannolikhet / 2))` av raderna på X i varje skyddad
  match;
- kandidatuniversumet måste innehålla X i skyddade matcher, så golvet inte
  kan bli omöjligt redan före radrankningen;
- automatisk reducering får inte rensa bort X-golvet efter att grundsystemet
  har byggts;
- skyddade matcher väljs inte som spikankare när tre andra matcher finns;
- flera skyddade matcher behandlas gemensamt: samma rad får uppfylla flera
  X-golv och portföljen fylls deterministiskt med högst rankade sådana rader;
- explicita manuella tecken-/färgval förblir användarens beslut och skrivs
  inte över i det tysta. Automatiken och alla automatiska profiler använder
  däremot skyddet.

Om point-in-time-total saknas används bara 32-procentsregeln. Priser eller
totaler får aldrig bakfyllas historiskt. Frånvaron ska synas i audit/UI, inte
ersättas med dagens modell.

## Matematiskt max v2

Den nya formen är exakt:

- 3 spikar;
- 1 halvgardering;
- 9 helgarderingar;
- `1^3 × 2 × 3^9 = 39 366` unika rader.

Spikarna väljs som de tre tydligaste ankarmatcherna efter sannolikhet och
profilens värdepoäng. Draw-risk-skyddade matcher får inte bli spikar om minst
tre oskyddade matcher finns. Den tydligaste återstående matchen blir
halvgardering; de övriga nio helgarderas. Om halvmatchen är skyddad gäller
X-regeln ovan.

Två forwardarmar behålls: EV medel (0,50) och EV högt (0,80). De får nya
nycklar och startar utan bakfyllning på Stryktipset 4969 och Europatipset
2604. Gamla `mathmax-v1-b41472-*` visas som avslutade historiska kuponger.

Reducerat max får samtidigt nya v2-nycklar eftersom dess radurval ändras av
draw-risk-golvet. Även den gamla v1-serien pensioneras utan omskrivning.

## Övriga system och kohorter

Vanliga kupongförslag får regeln som ny standard. Befintliga frysta benchmark-
och PH5-nycklar ändras aldrig semantiskt: de pensioneras och motsvarande
draw-risk-v1-nycklar startar framåt på samma nästa omgångar som maxtest v2.
Kontrollarmar fortsätter vara kontroller; de ska inte göras om till modellen
de är tänkta att jämföras med.

Topptipsets förregistrerade lokala optimerare v1 behåller sin gamla champion.
Den får inte skrivas om efter pilotresultatet; en senare v2-optimering får i
stället använda den nya standarden som egen förregistrerad champion.

## Acceptans

Före driftsättning krävs:

1. syntetiska tester på båda tröskelgränserna och på saknad total;
2. exakt 39 366 unika matematiska rader, tre spikar, en halv och nio hela;
3. rekonstruktion av Europatipset 2603 där båda spanska matcherna skyddas med
   sina faktiskt observerade m20-priser;
4. oförändrad radmängd när ingen match kvalificerar för draw-risk;
5. nya config-nycklar och inga ändringar av gamla ledger-rader;
6. databasbackup och migreringsrapport innan den nya point-in-time-tabellen
   tas i drift;
7. hela backend- och frontendtestsviten grön.

Detta är en metodisk riskjustering, inte bevis för positiv ROI. Resultaten ska
fortsätta mätas per version och forwardkohort innan ytterligare tröskeländring.
