import assert from 'node:assert/strict'
import test from 'node:test'

import { summarizeSourceHealth } from './sourceHealth.js'

const NOW = Date.parse('2026-08-01T21:10:00Z')

test('ett partiellt fel kan aldrig visas som rent gront', () => {
  const health = summarizeSourceHealth([{
    source: 'fotmob',
    scope: 'live',
    checked_at: '2026-08-01T21:09:00Z',
    ok: true,
    event_count: 20,
    error: '19 av 20 detaljanrop misslyckades',
  }], NOW)

  assert.equal(health.ok, false)
  assert.equal(health.status, 'partial')
  assert.equal(health.issues[0].error, '19 av 20 detaljanrop misslyckades')
})

test('ett felfritt farskt svar ar gront', () => {
  const health = summarizeSourceHealth([{
    source: 'flashscore',
    scope: 'live',
    checked_at: '2026-08-01T21:09:00Z',
    ok: true,
    event_count: 4,
    error: null,
  }], NOW)

  assert.equal(health.ok, true)
  assert.equal(health.status, 'ok')
  assert.equal(health.eventCount, 4)
})

test('en gammal kontroll ar inte gron trots tidigare ok', () => {
  const health = summarizeSourceHealth([{
    source: 'sofascore',
    scope: 'live',
    checked_at: '2026-08-01T20:00:00Z',
    ok: true,
    event_count: 0,
    error: null,
  }], NOW)

  assert.equal(health.ok, false)
  assert.equal(health.status, 'stale')
})
