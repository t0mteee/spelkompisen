import { forwardTestFilterKey } from './labels.js'

// Samma filter för API:ts kuponger och dess produkt-/versionsbundna grupper.
// Kronor räknas fortfarande bara i backend; här väljs populationen.
export function matchesForwardFilters(item, filters) {
  return (filters.product === 'alla' || item.product === filters.product)
    && (filters.horizon === 'alla' || item.horizon === filters.horizon)
    && (filters.method === 'alla' || forwardTestFilterKey(item) === filters.method)
    && (filters.version === 'alla'
      || (filters.version === 'aldre' ? item.retired === true : item.retired === false))
}

// Dolda armar (`hidden`) fryses och rättas vidare men visas inte.
export function forwardView(data, filters) {
  const tests = (data.tests || []).filter((test) => !test.hidden
    && matchesForwardFilters(test, filters))
  const groups = (data.groups || []).filter((group) => !group.hidden
    && matchesForwardFilters(group, filters))
  const drawKey = (test) => `${test.product}:${test.draw_number}`
  return {
    tests, groups,
    draws: new Set(tests.map(drawKey)).size,
    coupons: tests.length,
    facit: tests.filter((test) => test.correct_max != null).length,
    evaluated: tests.filter((test) => test.timely && test.correct_max != null
      && test.payout_complete === true).length,
  }
}
