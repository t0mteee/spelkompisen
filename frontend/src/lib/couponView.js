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
