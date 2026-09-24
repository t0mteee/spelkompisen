// Poolhälsans issues (/api/health → pools.issues) för Idag. Ren logik utan
// React. Tre slag: fel (insamlingen behöver tillsyn NU), varningar som gäller
// nu (för lite färsk Pinnacle nära spelstopp, stoppat shadowspår) och
// historiska bortfall (`scope: 'history'`: frysningar som missades för redan
// stängda omgångar). Före 2026-09-24 var ALLA varningar historiska och visades
// under "dagens insamling fungerar" — en aktuell varning får aldrig hamna där.
const KIND_LABEL = {
  sharp_link_coverage: 'för lite färsk Pinnacle',
  strength_shadow_stopped: 'styrkeshadowen står still',
  strength_shadow_unreadable: 'styrkeshadowen kunde inte läsas',
}

export function splitPoolIssues(issues) {
  const all = issues || []
  const warnings = all.filter((issue) => issue.level === 'warning')
  return {
    errors: all.filter((issue) => issue.level !== 'warning'),
    current: warnings.filter((issue) => issue.scope !== 'history'),
    history: warnings.filter((issue) => issue.scope === 'history'),
  }
}

export const poolIssueLabel = (issue) =>
  `${issue.product}${issue.draw_number ? ` omg ${issue.draw_number}` : ''}`

export function poolNoticeSummary(current) {
  const kinds = [...new Set((current || []).map((issue) => KIND_LABEL[issue.kind] || issue.kind))]
  return kinds.length ? `Poolunderlag att se över: ${kinds.join(' · ')}` : null
}
