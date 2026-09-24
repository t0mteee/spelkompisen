import test from 'node:test'
import assert from 'node:assert/strict'
import { isMathematical, coverageResult, visibleResearch, selectionReason, sharpStaleNote } from './couponView.js'

test('matematik visar tecken utan missvisande procentandelar', () => {
  const events = [{ covered: ['1'] }, { covered: ['1','X','2'] }]
  assert.equal(isMathematical(events, 3), true)
  assert.equal(isMathematical(events, 2), false)
  assert.equal(isMathematical([], 1), false)
  assert.equal(isMathematical([{ covered: [] }], 0), false)
})

test('skilj på saknade tecken och bortreducerade kombinationer', () => {
  const events = [{ covered: ['1','X'], outcome: 'X' }, { covered: ['2'], outcome: '1' }]
  assert.deepEqual(coverageResult(events, 1, true), { missing: 1, ceiling: 1, reductionLoss: 0 })
  assert.deepEqual(coverageResult(events, 0, true), { missing: 1, ceiling: 1, reductionLoss: 1 })
  assert.equal(coverageResult(events, 0, false), null)
  assert.equal(coverageResult(events, null, true), null)
})

test('göm bara gamla reducerade 40000, bevara övriga tester och tecken', () => {
  assert.equal(visibleResearch({ config_key: 'max40-v1-b40000-ev50' }), false)
  assert.equal(visibleResearch({ research_family: 'max40' }), false)
  assert.equal(visibleResearch({ config_key: 'mathmax-v2-dr1-b39366-ev50' }), true)
  assert.equal(visibleResearch({ config_key: 'reducedmax-v2-dr1-b20000-ev50' }), true)
  assert.equal(selectionReason('värde X 1.05, X-skydd 30%, total 2.25'), 'värde X 1.05')
  assert.equal(selectionReason('Så valdes raderna. pool-draw-risk-v1: X-golv i 3 lågmåls-/hög-X-match(er).'), 'Så valdes raderna.')
})

test('inaktuellt Pinnacle-pris vid frysningen: användes inte efter regeln, ändå före', () => {
  const at = (v) => `[${v}]`
  assert.equal(sharpStaleNote(null), null)
  assert.equal(sharpStaleNote(undefined), null)
  const after = sharpStaleNote({ reason: 'ambiguous', label: 'tvetydig',
    last_seen: '2026-09-24T15:02:11Z', used: false }, at)
  assert.equal(after.used, false)
  assert.equal(after.title, 'Pinnacle-priset var inaktuellt vid frysningen '
    + '(tvetydig, senast bekräftat [2026-09-24T15:02:11Z]) — användes inte')
  const before = sharpStaleNote({ reason: 'too_old', label: 'för gammal',
    last_seen: '2026-09-15T08:17:00Z', used: true }, at)
  assert.equal(before.used, true)
  assert.match(before.title, /\(äldre än 90 min, senast bekräftat \[2026-09-15T08:17:00Z\]\)/)
  assert.match(before.title, /användes ändå \(före färskhetsregeln 24\/9\)$/)
  // Okänd status utan etikett visas rått, aldrig som tom text.
  assert.match(sharpStaleNote({ reason: 'not_listed', used: false }, at).title,
    /\(ej listad\/namn\) — användes inte$/)
})
