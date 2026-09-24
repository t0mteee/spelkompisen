// Presentation only: never alters saved selections or settlement.
export function isMathematical(events, nRows) {
  return events.length > 0 && events.every((e) => e.covered?.length > 0)
    && events.reduce((n, e) => n * e.covered.length, 1) === nRows
}

export function coverageResult(events, best, complete) {
  if (!complete || best == null) return null
  const missing = events.filter((e) => !e.covered?.includes(e.outcome)).length
  return { missing, ceiling: events.length - missing,
    reductionLoss: Math.max(0, events.length - missing - best) }
}

export function visibleResearch(test) {
  return test.research_family !== 'max40' && !test.config_key?.startsWith('max40-')
}

export function selectionReason(reason) {
  // Also handles old frozen build notes, without rewriting historical records.
  return (reason || '').replace(/, X-skydd \d+%(?:, total [\d.]+)?/g, '')
    .replace(/\s*pool-draw-risk-v\d+: X-golv[^.]*\./g, '')
}

// pool-sharp-freshness-v1 i efterhand: var Pinnacle-underlaget inaktuellt när
// kupongen frystes? Backend avgör (`sharp_stale_at_freeze`), här bara text.
// Före färskhetsregeln (24/9 14:11Z) användes priset ändå, efter den inte.
const SHARP_STALE_REASON = {
  not_listed: 'ej listad/namn', ambiguous: 'tvetydig', no_moneyline: 'ingen 1X2',
  too_old: 'äldre än 90 min',
}
const localTime = (value) => new Date(value).toLocaleString('sv-SE',
  { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })

export function sharpStaleNote(stale, formatTime = localTime) {
  if (!stale) return null
  const reason = stale.reason === 'too_old' ? SHARP_STALE_REASON.too_old
    : stale.label || SHARP_STALE_REASON[stale.reason] || stale.reason || 'okänd orsak'
  const seen = stale.last_seen ? `, senast bekräftat ${formatTime(stale.last_seen)}` : ''
  const verdict = stale.used ? 'användes ändå (före färskhetsregeln 24/9)' : 'användes inte'
  return { used: !!stale.used,
    title: `Pinnacle-priset var inaktuellt vid frysningen (${reason}${seen}) — ${verdict}` }
}
