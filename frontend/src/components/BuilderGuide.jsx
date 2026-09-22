const profiles = [
  {
    name: 'Standard — utgångsläget',
    why: 'Byggdes för att väga chansen att få rätt mot hur mycket en rad kan betala. En sannolik rad är inte alltid prisvärd om många andra spelar samma rad.',
    how: 'Rankar konkreta rader med odds, streck och beräknad utdelning. Värdereglaget styr balansen mellan träffchans och värde.',
    limit: 'Bra enskilda rader kan ligga nära varandra. Hög värdevikt kan ge sällsynta träffar. Standard är vår referens, inte ett löfte om lönsamhet.',
  },
  {
    name: 'Träffsäkrare — mindre vikt på utdelning',
    why: 'Tillkom efter att kuponger missade rimliga utfall när värdejakten blev för hård.',
    how: 'Samma grundbyggare som Standard, men värdevikten låses till 0. Det är ett inställningsläge, inte en ny matchmodell.',
    limit: 'Gav fler toppträffar i den historiska 256/512-screeningen, men ofta lägre utdelning. Testet använde slutstreck och bevisar inte framtida ROI. Skyddar inte mot varje skrällomgång.',
  },
  {
    name: 'Radform v1 — test av hur många andra som delar vinsten',
    why: 'Tillkom efter kryssrika Topptipsomgångar för att undersöka om prognosen för antalet medvinnare var för grov.',
    how: 'Justerar beräknade medvinnare efter radens antal kryss. Ändrar utdelningsbedömningen, inte matchernas sannolikheter. Det är ingen allmän kryssbonus.',
    limit: 'Liten förbättring i historiskt 384-raderstest, men inte vid 256/512. Därför bara ett manuellt Topptips-test på 384 kr, inte ny standard.',
  },
  {
    name: 'Täckningstest v1 — test av raderna tillsammans',
    why: 'Tillkom när vi såg att en samling högt rankade rader inte nödvändigtvis ger bra samlad täckning för kupongen.',
    how: 'Väljer rader efter hur mycket ny täckning de tillför för full pott och upp till tre färre rätt, med ett golv för beräknat radvärde.',
    limit: 'Kan sänka chansen till full pott och har inte visat bättre lönsamhet. Särskilt viktigt på Topptipset: 7 rätt betalar inget. Separat experiment, en kupong och högst 512 kr. Standardrader används om skyddet slår till.',
  },
]

export function BuilderGuide() {
  return <details className="builder-guide">
    <summary>Vilken byggare är vilken — och varför finns den?</summary>
    <p><b>Tre olika val:</b> Systemtypen bestämmer hur kombinationer tas med.
      Radprofilen ändrar urvalet inom Värderader. Värdereglaget styr avvägningen
      mellan träffchans och utdelningsvärde. De är inte olika versioner av samma sak.</p>
    <h4>Radprofiler inom Värderader</h4>
    {profiles.map(profile => <details key={profile.name}>
      <summary>{profile.name}</summary>
      <p><b>Varför:</b> {profile.why}</p>
      <p><b>Så fungerar den:</b> {profile.how}</p>
      <p><b>Begränsning:</b> {profile.limit}</p>
    </details>)}
    <details>
      <summary>Systemtyper: matematiskt, reducerat, färg och garanti</summary>
      <p><b>Matematiskt:</b> Alla kombinationer av valda tecken. Lätt att överblicka,
        men fler garderingar ökar priset snabbt. Full pott finns med om alla matchutfall täcks.</p>
      <p><b>Värderader:</b> Väljer konkreta rader utifrån beräknat värde och träffchans.
        Det är här de fyra radprofilerna finns.</p>
      <p><b>Reducerat (värde):</b> Den äldre teckenbaserade reduceringen tar bara med
        en del av kombinationerna inom den valda ramen. Inte samma urval som Värderader;
        alla rätta tecken kan finnas i ramen utan att hela rätta raden ingår.</p>
      <p><b>Färgreducering:</b> Begränsar kombinationer med min/max för blå och gula
        tecken. Ger kontroll över radformen, men en felaktig gräns kan utesluta rätt rad.</p>
      <p><b>Egen reducering / Svenska Spel R-system:</b> Prioriterar en viss
        täckningsgaranti inom ramen. Garantin gäller bara när systemets villkor är
        uppfyllda — inte att kupongen säkert vinner eller går med vinst.</p>
    </details>
    <details>
      <summary>Två kuponger och stora tester — är det fler byggare?</summary>
      <p><b>Två kompletterande kuponger:</b> Ett sätt att bygga A och B med olika
        ankare och begränsat radöverlapp, inte en ny matchmodell. Varje kupong kostar
        den valda insatsen: 256 kr blir 512 kr totalt. Stöds inte av de två experimentprofilerna.</p>
      <p><b>5000- och maxtesterna:</b> Separata testserier med egna insatser och
        regler. Beloppet är inte namnet på en bättre modell. Ett manuellt profilval
        ändrar inte redan frysta tester.</p>
    </details>
    <p><b>Se vad du faktiskt får:</b> Efter ”Föreslå rad” visar ”Så är kupongen byggd”
      hur många av dina rader som innehåller 1, X och 2. Det är radfördelning,
      inte prognosen för matchresultatet. Standard förblir förvalt; experiment är frivilliga testval.</p>
  </details>
}
