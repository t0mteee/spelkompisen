// Byggaren erbjuder sedan 2026-10-18 bara Värderader, Reducerat och Matematiskt
// med värdevikten låst på 50 % (beslut koordinatorn-2026-10-18-stada-byggaren-2,
// val 0). Guiden beskriver bara det som går att välja.
export function BuilderGuide() {
  return <details className="builder-guide">
    <summary>Vilken byggare är vilken — och varför finns den?</summary>
    <p><b>Två val:</b> Systemtypen bestämmer hur kombinationer tas med, och
      strategin och budgeten bestämmer ramen. Värdevikten är låst på 50 %:
      balans mellan träffchans och utdelningsvärde.</p>
    <details>
      <summary>Värderader — utgångsläget</summary>
      <p><b>Varför:</b> Byggdes för att väga chansen att få rätt mot hur mycket en rad
        kan betala. En sannolik rad är inte alltid prisvärd om många andra spelar samma rad.</p>
      <p><b>Så fungerar den:</b> Rankar konkreta rader med odds, streck och beräknad
        utdelning.</p>
      <p><b>Begränsning:</b> Bra enskilda rader kan ligga nära varandra. Värderader är
        vår referens, inte ett löfte om lönsamhet.</p>
    </details>
    <details>
      <summary>Reducerat och matematiskt</summary>
      <p><b>Reducerat (värde):</b> Den äldre teckenbaserade reduceringen tar bara med
        en del av kombinationerna inom den valda ramen. Inte samma urval som Värderader;
        alla rätta tecken kan finnas i ramen utan att hela rätta raden ingår.</p>
      <p><b>Matematiskt:</b> Alla kombinationer av valda tecken. Lätt att överblicka,
        men fler garderingar ökar priset snabbt. Full pott finns med om alla matchutfall täcks.</p>
    </details>
    <details>
      <summary>Stora tester — är det fler byggare?</summary>
      <p><b>5000- och maxtesterna:</b> Separata testserier med egna insatser och
        regler. Beloppet är inte namnet på en bättre modell.</p>
      <p><b>Borttagna val:</b> Träffsäkrare, Radform v1, Täckningstest v1, Två
        kompletterande kuponger, Färgreducering, Egen reducering och Svenska Spels
        R-system erbjuds inte längre. Kuponger som redan byggts med dem visas som förut.</p>
    </details>
    <p><b>Se vad du faktiskt får:</b> Efter ”Föreslå rad” visar ”Så är kupongen byggd”
      hur många av dina rader som innehåller 1, X och 2. Det är radfördelning,
      inte prognosen för matchresultatet.</p>
  </details>
}
