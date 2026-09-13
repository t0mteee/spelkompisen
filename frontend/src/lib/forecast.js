// Utdelningsprognosen i UI. Den är VÅR skattning om omgången slutar som nu
// (backend pool_played.payout_forecast) — skriv alltid "prognos" och "per rad",
// aldrig "utdelning" rakt av. Ren logik utan React.
export const FORECAST_NOTE = 'Egen prognos om omgången slutar som den står nu: omgångens pott per '
  + 'nivå delat med förväntat antal vinnande rader ur folkets streck, med byggarens '
  + 'medvinnarkorrektion. Inte Svenska Spels siffra — den publiceras först efter omgången.'

// Högsta vinstnivå där kupongen fortfarande har rader vid liv, med prognosen
// för den nivån. null när inget lever eller prognos saknas.
export function topAliveForecast(live) {
  const alive = live?.alive_per_level || {}
  const levels = live?.forecast?.levels || {}
  const top = Object.keys(alive).map(Number)
    .filter((level) => Number(alive[level]) > 0).sort((a, b) => b - a)[0]
  if (top == null || !levels[top]) return null
  return { level: top, ...levels[top] }
}

export function forecastBasisText(forecast) {
  const b = forecast?.basis
  if (!b) return ''
  const parts = []
  if (b.decided) parts.push(`${b.decided} avgjorda`)
  if (b.current) parts.push(`${b.current} pågående som de står`)
  if (b.open) parts.push(`${b.open} ospelade viktade på odds`)
  return parts.join(' · ')
}
