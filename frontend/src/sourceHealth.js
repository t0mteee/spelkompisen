export const SOURCE_HEALTH_STALE_MS = 45 * 60 * 1000

/**
 * Ren summering av källhälsa så att samma regel kan låsas med test.
 *
 * `ok` från backend är huvudsignalen, men ett faktiskt felmeddelande får
 * defensivt aldrig visas grönt även om en äldre backend råkat lämna `ok=true`.
 */
export function summarizeSourceHealth(
  rows,
  nowMs = Date.now(),
  staleAfterMs = SOURCE_HEALTH_STALE_MS,
) {
  if (!rows?.length) {
    return {
      latest: null,
      eventCount: 0,
      issues: [],
      stale: false,
      status: 'missing',
      ok: false,
    }
  }

  const latest = rows.reduce(
    (current, row) => !current || row.checked_at > current
      ? row.checked_at
      : current,
    null,
  )
  const latestMs = Date.parse(latest)
  const stale = !Number.isFinite(latestMs) || nowMs - latestMs > staleAfterMs
  const issues = rows.filter((row) => !row.ok || Boolean(row.error))
  const partial = issues.some(
    (row) => Boolean(row.error) && Number(row.event_count || 0) > 0,
  )
  const status = stale
    ? 'stale'
    : issues.length
      ? partial ? 'partial' : 'bad'
      : 'ok'

  return {
    latest,
    eventCount: rows.reduce((count, row) => count + Number(row.event_count || 0), 0),
    issues,
    stale,
    status,
    ok: status === 'ok',
  }
}
