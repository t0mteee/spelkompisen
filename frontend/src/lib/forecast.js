// Utdelningsprognosen i UI. Den är VÅR skattning om omgången slutar som nu
// (backend pool_played.payout_forecast) — skriv alltid "prognos" och "per rad",
// aldrig "utdelning" rakt av. Ren logik utan React.
import { kr } from './format.js'
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

// Under Svenska Spels minimiutdelning betalas nivån inte ut (backend
// pool_played.MIN_PAYOUT_KR, härledd ur settlementlagret): backend skickar då
// per_row_kr = 0, below_min_payout och prognosen före regeln i raw_per_row_kr.
// Tom sträng när nivån inte berörs.
export function minPayoutNote(forecast, entry) {
  if (!entry?.below_min_payout) return ''
  const min = forecast?.min_payout_kr
  const antagen = forecast?.min_payout_basis === 'antagen'
    ? ' Gränsen är belagd för Stryktipset och Europatipset men antagen för Topptipset,'
      + ' där ingen nivå hittills har betalats med 0 kr.'
    : ''
  return `Prognosen ≈ ${kr(entry.raw_per_row_kr)}/rad ligger under Svenska Spels`
    + ` minimiutdelning ${kr(min)} per rad — en sådan nivå betalas inte ut, därför 0 kr.${antagen}`
}

// Visningstext för prognosen per rad: "≈ 1 234 kr", eller "0 kr" när nivån
// hamnar under minimiutdelningen (förklaringen ges av minPayoutNote).
export function perRowText(entry) {
  if (!entry) return '–'
  return entry.below_min_payout ? kr(0) : `≈ ${kr(entry.per_row_kr)}`
}

export const GUARANTEE_NOTE = 'Svenska Spels garanti för omgången. Ingår INTE i prognosen '
  + 'eller i EV — villkoren är inte verifierade mot Svenska Spels regler.'

// Garantier som egna rader, aldrig inräknade i prognosen.
export function guaranteeLines(forecast) {
  return (forecast?.guarantees || [])
    .filter((g) => Number(g?.amount_kr) > 0)
    .map((g) => {
      if (g.sole_winner) return `om du är ensam vinnare på ${g.level} rätt: minst ${kr(g.amount_kr)}`
      const label = g.description || g.type
      return label ? `garanti ${label}: ${kr(g.amount_kr)}` : `garanti: ${kr(g.amount_kr)}`
    })
}
