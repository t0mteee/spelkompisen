import test from 'node:test'
import assert from 'node:assert/strict'
import { splitPoolIssues, poolIssueLabel, poolNoticeSummary } from './poolHealth.js'

const issues = [
  { level: 'error', product: 'stryktipset', kind: 'stale_snapshots', message: 'gammal' },
  { level: 'warning', product: 'topptipset', kind: 'freeze_incomplete', draw_number: 4274,
    scope: 'history', message: '3 timmar före spelstopp: 0 av 10 testsystem sparades' },
  { level: 'warning', product: 'europatipset', kind: 'sharp_link_coverage', draw_number: 2610,
    message: 'färsk Pinnacle för 5 av 13 matcher' },
  { level: 'warning', product: 'poolstyrka', kind: 'strength_shadow_stopped',
    message: 'styrkeshadowen samlar inte' },
]

test('aktuella varningar hamnar aldrig bland historiska bortfall', () => {
  const { errors, current, history } = splitPoolIssues(issues)
  assert.deepEqual(errors.map((i) => i.kind), ['stale_snapshots'])
  assert.deepEqual(current.map((i) => i.kind), ['sharp_link_coverage', 'strength_shadow_stopped'])
  assert.deepEqual(history.map((i) => i.draw_number), [4274])
  assert.deepEqual(splitPoolIssues(undefined), { errors: [], current: [], history: [] })
})

test('etikett och sammanfattning säger vad som ska ses över', () => {
  assert.equal(poolIssueLabel(issues[2]), 'europatipset omg 2610')
  assert.equal(poolIssueLabel(issues[3]), 'poolstyrka')
  assert.equal(poolNoticeSummary(splitPoolIssues(issues).current),
    'Poolunderlag att se över: för lite färsk Pinnacle · styrkeshadowen står still')
  assert.equal(poolNoticeSummary([]), null)
})
