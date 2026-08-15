# Kompletterande kuponger — 2026-08-15

## Aktuellt kontrakt (v2)

Poolbyggaren har ett frivilligt läge **Två kompletterande kuponger** för
Värderader. Samma strategi, reglage och insats används för båda förslagen,
men A och B optimeras tillsammans som två olika scenarier:

- varje kupong får egna spikankare på andra matcher än den andra kupongen;
- varje kupong får använda den andras ankartecken på högst 50 procent av
  raderna;
- högst 10 procent av de exakta raderna får finnas i båda kupongerna;
- vardera kupongen måste behålla minst 75 procent av det vanliga
  singelförslagets interna `träffchans^k × EV`-summa;
- A och B har samma radantal och kostnad, och kan läggas i kupongen var för sig.

På 13-matchsspel med högst 512 rader försöker byggaren ge två ankare per
kupong. På åttamatchsspel och tätare system används minst ett ankare per
kupong. Om den striktare varianten inte går provar den färre ankare, men aldrig
gemensamma ankarmatcher eller ett lägre kvalitetsgolv.

Detta är två fullstora spelalternativ, inte två delar av samma budget. En vald
insats på 256 kr betyder 256 + 256 kr om båda spelas. Läget är avstängt som
standard och lägger aldrig in eller lämnar in något automatiskt. Vill
användaren ha byggarens ordinarie system stängs dubbelkupongsläget av.

Kvalitetsprocenten är ett relativt byggarmått, inte vinstsannolikhet eller
historiskt bevisad avkastning. Det lägre golvet än i v1 är avsiktligt: en andra
kupong som tvingas till 90 procent blev i praktiken en nästan identisk kopia
och gav därför ingen meningsfull riskspridning.

## Varför v1 ersattes samma dag

Det första produktionsförsöket behöll A exakt som singelförslaget och krävde
90 procents kvalitet av B, men garderade A:s spikar i bara 10 procent av
B-raderna. Samans sparade Stryktips 4966, kupong-id 27 och 28, visade felet:

- 146 av 256 exakta rader var gemensamma, alltså 57,0 procent;
- A:s spikar i match 4 och 9 följdes fortfarande i 230 av 256 B-rader;
- B:s bärande favoriter följdes redan i 89–93 procent av A-raderna;
- flera övriga matcher skilde bara 0–8 procentenheter i teckenvikt.

Topptipset Stryk 976 visade det andra felet. Singelförslagets 256 rader hade
ingen helt fast match, varpå v1 gav upp med texten att A saknade spikar. V2
kräver inte längre att singelförslaget råkar ha en spik: den skapar A:s och
B:s ankare själv ur samma rankade universum.

## Teknisk utformning

`GET /api/system` accepterar `complementary=true` tillsammans med `ev=true`.
Svaret på toppnivån är Kupong A; `complementary.system` är Kupong B och
metadatafältet redovisar ankare, faktisk radöverlapp, båda kvalitetskvoterna,
korstaket och kostnaderna. Befintliga anrop utan flaggan är oförändrade.

Standardbyggaren fullrankar ett begränsat toppurval precis som förut.
Dubbelkupongsläget fullrankar hela det redan begränsade kandidatuniversumet
(högst 60 000 rader), söker disjunkta ankargrupper och väljer de bästa raderna
under korstaken. Därefter byts exakta dubblettrader bort så långt
75-procentsgolvet medger. Sökningen är deterministisk.

Ingen databas eller ordinarie modellversion ändrades. De redan sparade
kupongerna 27 och 28 ska självklart ligga kvar som faktiskt spelad historik;
de skrivs inte om i efterhand.

## Acceptanstester

- Enkelbyggaren ska ge exakt samma rader före och efter ett dubbelanrop.
- En 256-raders Topptipsbas utan spikar ska ändå ge två kuponger.
- A och B ska ha disjunkta ankarmatcher, samma radantal och samma kostnad.
- Den andra kupongens ankartecken får finnas på högst hälften av raderna.
- Exakt radöverlapp får vara högst 10 procent.
- Båda kvalitetskvoterna ska vara minst 75 procent av singelförslaget.
- Upprepade anrop med samma data ska ge identiska rader och metadata.
- Backendens fulla testsvit, frontendtesterna, produktionsbygget och riktiga
  torrtest mot både Stryktips 4966 och Topptipset Stryk 976 ska vara gröna före
  drift.

## Slutverifiering av v2

Med respektive omgångs riktiga analysdata och 256 kr gav den nya byggaren:

- **Stryktipset 4966:** två ankare per sida, 84,4/85,5 procents relativ
  kvalitet, 0 exakta dubblettrader och 2,1 sekunders lokal byggtid före
  portföljsimulering. Den andra kupongen använde varje A-ankare på exakt 128
  av 256 rader; A använde B-ankarna på 102 respektive 104 rader.
- **Topptipset Stryk 976:** ankare 4–1 mot 2–2, 82,4/83,3 procents relativ
  kvalitet, 0 exakta dubblettrader och 0,23 sekunders lokal byggtid. Detta är
  samma underlag där v1 inte kunde skapa B alls.

Verifiering före commit: 714 backendtester, 12 frontendtester,
produktionsbygge och syntax-/diffkontroll gröna.
