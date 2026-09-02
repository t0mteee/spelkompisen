// Poolspelens EV-matematik: Poisson-binomial över medvinnare, κ per produkt
// och nivå (MÅSTE vara identisk med builder.KAPPA — låst av
// backend/tests/test_kappa_synk.py), folkets streckgolv och radvärdering.
// Ren logik utan React — testas med node --test. Bruten ur App.jsx 2026-09-02.

export function poissonBinomial(probs) {
  let d = [1]
  for (const p of probs) {
    const nd = Array(d.length + 1).fill(0)
    for (let j = 0; j < d.length; j++) { nd[j] += d[j] * (1 - p); nd[j + 1] += d[j] * p }
    d = nd
  }
  return d
}

/* Värdera en konkret uppsättning rader. Per rad: Poisson-binomial över odds
   (P att raden får k rätt) och över folkets streck (medvinnartäthet). Utdelning
   om rätt = pott_k / (förv. medvinnare + dig själv). Spårar lägsta/medel/högsta
   utdelning per nivå över raderna — utdelningens spann (likt reducering.se). */
// κ-korrektion per produkt och nivå — MÅSTE hållas i synk med KAPPA i
// backend/app/builder.py (PH4-analysen 2026-07-24, 7 754 avgjorda omgångar).
// κ > 1 = folket klumpar ihop sig mer än oberoende-antagandet ⇒ fler
// medvinnare ⇒ lägre utdelning. Korrektionen sänker EV, aldrig tvärtom.
// κ-korrektion per produkt och nivå — MÅSTE hållas i synk med KAPPA i
// backend/app/builder.py (PH4-analysen 2026-07-24, 7 754 avgjorda omgångar).
// κ > 1 = folket klumpar ihop sig mer än oberoende-antagandet ⇒ fler
// medvinnare ⇒ lägre utdelning. Korrektionen sänker EV, aldrig tvärtom.
export const KAPPA = {
  stryktipset: { 13: 1.096, 12: 1.114, 11: 1.102, 10: 1.076 },
  europatipset: { 13: 1.070, 12: 1.064, 11: 1.063, 10: 1.048 },
  topptipset: { 8: 1.038 },
  topptipsetstryk: { 8: 1.040 },
  topptipsetextra: { 8: 1.022 },
}
export const kappaFor = (product, correct) => KAPPA[product]?.[correct] ?? 1.0

// Folkets sannolikhet för ett tecken, med GOLV. Utan golv gav streck = 0
// (finns på 38 event i databasen) pk = 0 → utdelning = HELA potten, och
// EV-rankaren älskade exakt de tecknen. Backend har haft max(q, 0.001) i
// builder._pq hela tiden; frontend saknade det helt — samma golv måste
// gälla i båda annars visar UI:t en annan EV än den byggaren optimerade.
// Folkets sannolikhet för ett tecken, med GOLV. Utan golv gav streck = 0
// (finns på 38 event i databasen) pk = 0 → utdelning = HELA potten, och
// EV-rankaren älskade exakt de tecknen. Backend har haft max(q, 0.001) i
// builder._pq hela tiden; frontend saknade det helt — samma golv måste
// gälla i båda annars visar UI:t en annan EV än den byggaren optimerade.
export const FOLK_MIN = 0.001
export const folkProb = (o) => {
  if (!o) return FOLK_MIN
  const q = o.streck != null ? o.streck / 100 : (o.fair_prob || 0)
  return Math.max(q, FOLK_MIN)
}
export function evalRows(rowFF, tiers, field, N, minDividend = 0, product = null) {
  const poly = {}, evTiers = {}, divMin = {}, divMax = {}
  let kept = 0, evPayout = 0
  for (const row of rowFF) {
    const pf = poissonBinomial(row.map((o) => o.fair))
    const pk = poissonBinomial(row.map((o) => o.folk))
    const div = {}
    for (const t of tiers) {
      const c = t.correct
      div[c] = Math.min(t.pool, t.pool / (field * (pk[c] || 0) * kappaFor(product, c) + 1))
    }
    if (minDividend > 0 && (div[N] || 0) < minDividend) continue
    kept++
    for (const t of tiers) {
      const c = t.correct
      poly[c] = (poly[c] || 0) + (pf[c] || 0)
      const contrib = (pf[c] || 0) * div[c]
      evPayout += contrib; evTiers[c] = (evTiers[c] || 0) + contrib
      if ((pf[c] || 0) > 0) {
        divMin[c] = divMin[c] == null ? div[c] : Math.min(divMin[c], div[c])
        divMax[c] = divMax[c] == null ? div[c] : Math.max(divMax[c], div[c])
      }
    }
  }
  const dividend = {}
  for (const c in evTiers) dividend[c] = poly[c] ? evTiers[c] / poly[c] : null
  return { poly, evTiers, dividend, divMin, divMax, kept, evPayout }
}
export function couponStats(matches, picks, payouts, minDividend = 0, turnoverOverride = null, jackpot = 0, pickRows = null) {
  const N = matches.length
  const rowPrice = payouts?.row_price || 1
  const ratio = payouts?.ratio || 0
  const turnover = turnoverOverride != null ? turnoverOverride : (payouts?.turnover || 0)

  // RADLÄGE: kupongen är en explicit lista utvalda rader (t.ex. från EV-topp/
  // färgreducering) — värdera exakt de raderna, inte alla teckenkombinationer.
  if (pickRows && pickRows.length && pickRows.every((r) => r.length === N)) {
    const tiers = (payouts?.tiers || []).map((t) => ({
      correct: t.correct,
      pool: turnover * ratio * (t.share || 0) + (t.correct === N ? jackpot : 0),
    }))
    const poolMap = {}; tiers.forEach((t) => { poolMap[t.correct] = t.pool })
    const field = turnover / rowPrice
    const rowFF = pickRows.map((r) => r.map((s, i) => {
      const o = matches[i].outcomes[s] || {}
      return { fair: o.fair_prob || 0, folk: folkProb(o) }
    }))
    const modelOk = field > 0 && tiers.length > 0
    const e = modelOk ? evalRows(rowFF, tiers, field, N, minDividend, payouts?.product)
      : { poly: {}, evTiers: {}, dividend: {}, divMin: {}, divMax: {}, kept: pickRows.length, evPayout: 0 }
    const rows = e.kept
    const cost = rows * rowPrice
    const expectedCorrect = rowFF.reduce((a, r) => a + r.reduce((x, o) => x + o.fair, 0), 0) / (rowFF.length || 1)
    return { N, complete: true, selectedCount: N, fullRows: pickRows.length, kept: e.kept,
      rows, cost, poly: e.poly, evTiers: e.evTiers, dividend: e.dividend,
      divMin: e.divMin, divMax: e.divMax, topDividend: e.dividend[N] ?? null,
      modelOk, reduced: minDividend > 0, poolMap, turnover, expectedCorrect,
      evPayout: e.evPayout, ev: e.evPayout - cost,
      roi: cost ? (e.evPayout - cost) / cost : null, pAll: e.poly[N] || 0, rowMode: true }
  }
  const ps = [], counts = []
  let complete = true
  for (const m of matches) {
    const sel = picks[m.event_number] || []
    if (sel.length === 0) complete = false
    ps.push(sel.reduce((a, s) => a + (m.outcomes[s]?.fair_prob || 0), 0))
    counts.push(sel.length)
  }
  // Generating-function-poly för fulla systemet (fallback om vi inte enumererar)
  let gpoly = [1]
  for (let i = 0; i < N; i++) {
    const p = ps[i], c = counts[i]
    const np = Array(gpoly.length + 1).fill(0)
    for (let j = 0; j < gpoly.length; j++) { np[j] += gpoly[j] * (c - p); np[j + 1] += gpoly[j] * p }
    gpoly = np
  }
  const fullRows = complete ? counts.reduce((a, c) => a * c, 1) : 0
  const expectedCorrect = ps.reduce((a, b) => a + b, 0)
  const selectedCount = counts.filter((c) => c > 0).length
  // potter räknas från (ev. överstyrd) omsättning × andel; jackpot läggs på toppnivån
  const tiers = (payouts?.tiers || []).map((t) => ({
    correct: t.correct,
    pool: turnover * ratio * (t.share || 0) + (t.correct === N ? jackpot : 0),
  }))
  const poolMap = {}; tiers.forEach((t) => { poolMap[t.correct] = t.pool })
  const field = turnover / rowPrice

  // Enumerera kupongens rader och värdera dem. Utdelningsreducering: evalRows
  // hoppar över rader vars toppvinst-utdelning understiger minDividend.
  let modelOk = false, e = null
  if (complete && field > 0 && fullRows > 0 && fullRows <= 20000 && tiers.length) {
    const lists = matches.map((m) => (picks[m.event_number] || []).map((s) => ({
      fair: m.outcomes[s]?.fair_prob || 0,
      folk: folkProb(m.outcomes[s]),
    })))
    const rowFF = []
    const rec = (i, acc) => { if (i === N) { rowFF.push(acc); return } for (const o of lists[i]) rec(i + 1, [...acc, o]) }
    rec(0, [])
    e = evalRows(rowFF, tiers, field, N, minDividend, payouts?.product); modelOk = true
  }

  const poly = modelOk ? e.poly : gpoly.reduce((o, v, i) => { o[i] = v; return o }, {})
  const evTiers = modelOk ? e.evTiers : {}
  const dividend = modelOk ? e.dividend : {}
  const divMin = modelOk ? e.divMin : {}
  const divMax = modelOk ? e.divMax : {}
  const kept = modelOk ? e.kept : fullRows
  const evPayout = modelOk ? e.evPayout : 0
  const rows = modelOk ? kept : fullRows
  const cost = rows * rowPrice
  const pAll = modelOk ? (poly[N] || 0) : (gpoly[N] || 0)
  return { N, complete, selectedCount, fullRows, kept, rows, cost, poly, evTiers,
    dividend, divMin, divMax, topDividend: dividend[N] ?? null, modelOk, reduced: minDividend > 0,
    poolMap, turnover, expectedCorrect, evPayout, ev: evPayout - cost,
    roi: cost ? (evPayout - cost) / cost : null, pAll }
}

/* Värdera ett genererat system (matematiskt eller reducerat) över dess faktiska
   rader, så vi kan visa EV/ROI och utdelningens spann per strategi. */
export function systemStats(sys, matches, payouts) {
  if (!sys || !matches?.length || !payouts?.available) return null
  const N = matches.length
  const rowPrice = payouts.row_price || sys.row_price || 1
  const ratio = payouts.ratio || 0
  // Samma värderingshorisont som byggaren använder i backend: prognostiserad
  // SLUTomsättning. Med live-omsättning tidigt i veckan blir både potter och
  // medvinnare för små, och den EV som visas blir glädjekalkyl.
  const turnover = payouts.projected_turnover || payouts.turnover || 0
  const field = turnover / rowPrice
  const jackpot = sys.jackpot ?? payouts.jackpot ?? 0
  const tiers = (payouts.tiers || []).map((t) => ({
    correct: t.correct,
    pool: turnover * ratio * (t.share || 0) + (t.correct === N ? jackpot : 0),
  }))
  if (!tiers.length || field <= 0) return null
  const byEv = {}; matches.forEach((m) => { byEv[m.event_number] = m })
  const picks = sys.picks || []
  let rowsSigns = sys.rows && sys.rows.length ? sys.rows : null
  if (!rowsSigns) {
    const lists = picks.map((p) => p.signs)
    const total = lists.reduce((a, l) => a * l.length, 1)
    if (total > 50000) return { tooBig: true, rows: sys.num_rows }
    rowsSigns = []
    const rec = (i, acc) => { if (i === lists.length) { rowsSigns.push(acc); return } for (const s of lists[i]) rec(i + 1, [...acc, s]) }
    rec(0, [])
  } else if (rowsSigns.length > 50000) {
    return { tooBig: true, rows: sys.num_rows }
  }
  const rowFF = rowsSigns.map((r) => r.map((s, i) => {
    const o = byEv[picks[i]?.event_number]?.outcomes?.[s] || {}
    return { fair: o.fair_prob || 0, folk: folkProb(o) }
  }))
  const e = evalRows(rowFF, tiers, field, N, 0, payouts?.product)
  const cost = rowsSigns.length * rowPrice
  const poolMap = {}; tiers.forEach((t) => { poolMap[t.correct] = t.pool })
  return { ...e, N, rows: rowsSigns.length, cost, poolMap, turnover,
    ev: e.evPayout - cost, roi: cost ? (e.evPayout - cost) / cost : null, pAll: e.poly[N] || 0 }
}

/* Liten tabell: lägsta/medel/högsta förväntad utdelning per vinstnivå. */
/* Omsättningen läses ur `s.turnover` — den som potterna FAKTISKT byggdes med.
   Tidigare skickades den in separat, och byggaren skickade live-omsättningen
   till en tabell vars potter kom ur prognosen: fottexten beskrev alltså ett
   annat underlag än raderna ovanför den. Basen härleds nu i stället genom att
   jämföra mot de två kända ankarna, så texten och talen inte kan gå isär. */
