// Små rena grindar för omgångsbundet UI-state. De ligger utanför React så
// sena-svar-regeln kan regressionsprovas utan ett tungt browser-testramverk.
export function beginRequest(sequenceRef) {
  sequenceRef.current += 1
  return sequenceRef.current
}

export function requestIsCurrent(sequenceRef, token) {
  return sequenceRef.current === token
}

export function payoutMatchesSelection(payouts, product, draw) {
  return payouts?.product === product
    && Number(payouts?.draw_number) === Number(draw)
}

export function uniqueDraws(draws) {
  const byIdentity = new Map()
  for (const draw of draws || []) {
    const key = `${draw?.product || ''}|${Number(draw?.draw_number)}`
    const current = byIdentity.get(key)
    // Samma produkt+omgång är samma kupongidentitet. Om backend tillfälligt
    // skickar både en äldre och en öppen variant behåller vi den öppna;
    // annars vinner första observationen och ordningen förblir stabil.
    if (!current || (current.state !== 'Open' && draw?.state === 'Open')) {
      byIdentity.set(key, draw)
    }
  }
  return [...byIdentity.values()]
}
