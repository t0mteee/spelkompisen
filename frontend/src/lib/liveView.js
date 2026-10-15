// Livesidan för poolspelen (#/live, 2026-10-15): alla pågående omgångar sida
// vid sida ur /api/pool/live (backend/app/pool_live_view.py). Backend räknar
// livebilden i bakgrunden var 20:e s; sidan hämtar bara det färdiga svaret.
// Ren logik utan React så `node --test` når den. LIVEBILD, aldrig facit.

export const POLL_MS = 20000

const pct = (value, digits = 1) => `${(value * 100).toLocaleString('sv-SE', {
  minimumFractionDigits: value > 0 && value < 0.1 ? digits : 0,
  maximumFractionDigits: digits,
})} %`

// Andel som procenttext med vettiga decimaler även för mycket små tal.
export function shareText(value) {
  if (value == null || Number.isNaN(value)) return null
  if (value <= 0) return '0 %'
  if (value < 0.0001) return '< 0,01 %'
  if (value < 0.01) return pct(value, 2)
  return pct(value, 1)
}

// "67'", "Slut", "Förlängning", "Uppskjuten", "15:00" — matchens klocka.
export function matchClock(m, timeZone = 'Europe/Stockholm') {
  if (m.cancelled) return 'Struken'
  if (m.postponed) return 'Uppskjuten'
  if (m.extra_time) return m.final ? 'Slut (förl.)' : 'Förlängning'
  if (m.final) return 'Slut'
  if (m.in_progress) return m.minute != null ? `${m.minute}'` : (m.status_text || 'Pågår')
  if (m.start) {
    const d = new Date(m.start)
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleTimeString('sv-SE', { timeZone, hour: '2-digit', minute: '2-digit' })
    }
  }
  return m.status_text || '–'
}

// Läge för hela omgången, för rubrikchipet.
export function drawPhase(draw) {
  if (draw.error) return { key: 'fel', text: 'Livebilden saknas just nu' }
  const n = draw.matches?.length || 0
  if (!n) return { key: 'vantar', text: 'Inga matcher' }
  if (draw.finished) return { key: 'klar', text: `Alla ${n} klara · väntar på facit` }
  if (!draw.started) return { key: 'vantar', text: 'Inte startad' }
  const live = draw.n_live ? ` · ${draw.n_live} pågår` : ''
  return { key: 'live', text: `${draw.n_decided}/${n} klara${live}` }
}

// Klassen för kupongens tecken i en match: rätt (grön), fel (röd) eller
// pågående (streckad) — samma färgspråk som kupongkortet i Historik.
export function signClass(match, sign) {
  if (!match.sign || match.cancelled) return ''
  if (match.sign !== sign) return match.final ? 'miss' : 'behind'
  if (match.final && !match.sign_provisional) return 'hit'
  return 'leading'
}

// Krav för alla rätt i klartext per öppen match.
//   []          → ingen rad kan längre nå alla rätt
//   ['1']       → "måste bli 1"
//   ['1','X']   → "1 eller X"
//   alla tre    → täckt, matchen avgör inte toppnivån
export function requirementText(signs) {
  if (!signs?.length) return 'ingen rad kvar'
  if (signs.length === 3) return 'alla tecken täckta'
  if (signs.length === 1) return `måste bli ${signs[0]}`
  return `${signs.join(' eller ')}`
}

// Bara de matcher som faktiskt avgör toppnivån (inte alla tre tecken täckta).
export function decisiveRequirements(coupon) {
  return (coupon?.krav || []).filter((k) => (k.signs || []).length < 3)
}

// "13 rätt lever i 4 rader" / "kan inte längre nå 13 rätt" — kupongens rubrik.
export function couponHeadline(coupon) {
  if (!coupon || coupon.error) return 'Livebilden för kupongen saknas'
  const top = coupon.top_level
  if (coupon.all_decided) return `Klar: bäst ${coupon.best_secure} rätt`
  if (coupon.out_of_contention) {
    return `Kan inte nå vinst längre (max ${coupon.max_possible} rätt)`
  }
  if (top && coupon.top_alive > 0) {
    return `${top} rätt lever i ${coupon.top_alive} ${coupon.top_alive === 1 ? 'rad' : 'rader'}`
  }
  return `Max ${coupon.max_possible} rätt möjligt`
}

// Nivåerna under toppen som chips: [{level, alive, span, chance}].
export function levelChips(coupon) {
  const alive = coupon?.alive_per_level || {}
  const lo = coupon?.alive_min_per_level || null
  const hi = coupon?.alive_max_per_level || null
  const chance = coupon?.chance_per_level || null
  return Object.keys(alive).map(Number).sort((a, b) => b - a).map((level) => ({
    level,
    alive: alive[level],
    span: lo && hi && lo[level] !== hi[level] ? [lo[level], hi[level]] : null,
    chance: chance?.[level] ?? null,
  }))
}

// Prognosen per nivå för rubriken: [{level, kr, belowMin}] från högsta nivån.
export function forecastLevels(forecast) {
  const levels = forecast?.levels || {}
  return Object.keys(levels).map(Number).sort((a, b) => b - a).map((level) => ({
    level,
    kr: levels[level].per_row_kr,
    belowMin: Boolean(levels[level].below_min_payout),
  }))
}

// "uppdaterad 15:42:10" + varning när bilden är gammal (bakgrunden har stannat).
export function freshnessText(asOf, now = new Date(), timeZone = 'Europe/Stockholm') {
  const at = asOf ? new Date(asOf) : null
  if (!at || Number.isNaN(at.getTime())) return { text: 'ingen livebild ännu', stale: true }
  const age = Math.max(0, Math.round((now - at) / 1000))
  const clock = at.toLocaleTimeString('sv-SE', { timeZone })
  return { text: `uppdaterad ${clock}`, stale: age > 90, age }
}

// Kortordning: pågående först, sedan inte startade (närmast först), sist klara.
export function sortDraws(draws) {
  const rank = (d) => (d.error ? 3 : d.finished ? 2 : d.started ? 0 : 1)
  return [...(draws || [])].sort((a, b) => rank(a) - rank(b)
    || new Date(a.close || 0) - new Date(b.close || 0))
}

// Idag-kortet: en rad per omgång. Null när inget pågår.
export function liveSummary(payload) {
  const draws = sortDraws(payload?.draws).filter((d) => !d.error && (d.started || d.coupons?.length))
  if (!draws.length) return null
  return draws.map((d) => {
    const own = (d.coupons || []).filter((c) => !c.error)
    const best = own.length
      ? own.map((c) => couponHeadline(c)).join(' · ')
      : (d.folk_alla_ratt != null ? `${shareText(d.folk_alla_ratt)} av folket har allt rätt` : null)
    return { key: `${d.product}-${d.draw_number}`, name: d.name, draw: d.draw_number,
      phase: drawPhase(d), detail: best, mine: own.length }
  })
}
