// Sharp-panelens radtext för matcher UTAN pris. Ren presentation av vad
// insamlingen senast observerade (/api/external-odds är ren läsning sedan
// 2026-09-24) — panelen lovar aldrig en ny hämtning.
const STATUS = {
  no_moneyline: { txt: '1X2 ej öppnad hos Pinnacle', cls: 'st-wait' },
  not_listed: { txt: 'ej listad hos Pinnacle eller namnet matchade inte', cls: 'st-miss' },
  ambiguous: { txt: 'tvetydig: flera Pinnacle-kandidater', cls: 'st-miss' },
  never_observed: { txt: 'inte observerad av insamlingen än', cls: 'st-wait' },
  matched: { txt: 'länkad, men inget pris sparat', cls: 'st-wait' },
  derived: { txt: 'länkad (härledd), men inget pris sparat', cls: 'st-wait' },
}

export function sharpPanelStatus(match, formatTime) {
  const base = STATUS[match.status] || { txt: match.status || 'okänd status', cls: '' }
  const parts = [base.txt]
  const c = match.candidate
  if (c?.home && c?.away) {
    const score = c.score == null ? '' : ` (likhet ${Math.round(c.score * 100)} %)`
    parts.push(`närmaste kandidat: ${c.home} – ${c.away}${score}`)
  }
  if (match.status_at) parts.push(`senast observerad ${formatTime(match.status_at)}`)
  return { txt: parts.join(' · '), cls: base.cls }
}
