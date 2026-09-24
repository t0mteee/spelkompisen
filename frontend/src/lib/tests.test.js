import test from 'node:test'
import assert from 'node:assert/strict'
import { statusTone, newsworthy, progressText } from './tests.js'

test('statusfärg följer trappan', () => {
  assert.equal(statusTone('samlar'), 'muted')
  assert.equal(statusTone('underlag klart'), 'amber')
  assert.equal(statusTone('granskad: ej stöd'), 'red')
  assert.equal(statusTone('avslutad'), 'grey')
  assert.equal(statusTone('något nytt'), 'muted')
})

test('Idag visar bara tester som väntar på eller nyss fått beslut', () => {
  const now = new Date('2026-09-13T12:00:00Z')
  const tests = [
    { id: 'ph5', status: 'samlar' },
    { id: 'standard', status: 'underlag klart' },
    { id: 'ph4', status: 'granskad: ej stöd', decision: { date: '2026-09-02' } },
    { id: 'old', status: 'granskad: ej stöd', decision: { date: '2026-07-01' } },
    { id: 'max40', status: 'avslutad', archived: true },
  ]
  assert.deepEqual(newsworthy(tests, { now }).map((t) => t.id), ['standard', 'ph4'])
  assert.equal(progressText({ progress: { n: 29, krav: 40, namn: 'topptipset 180 min' } }), '29/40 · topptipset 180 min')
  assert.equal(progressText({}), '–')
})

test('ett stoppat test syns som rött och som nyhet på Idag', () => {
  assert.equal(statusTone('stoppad'), 'red')
  const now = new Date('2026-09-24T12:00:00Z')
  assert.deepEqual(newsworthy([{ id: 'poolstyrka', status: 'stoppad' }, { id: 'ph5', status: 'samlar' }],
    { now }).map((t) => t.id), ['poolstyrka'])
})
