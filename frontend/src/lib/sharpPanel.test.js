import test from 'node:test'
import assert from 'node:assert/strict'
import { sharpPanelStatus } from './sharpPanel.js'

const at = (v) => `[${v}]`

test('avvisad match visar närmaste kandidat och observationstid', () => {
  const s = sharpPanelStatus({ status: 'ambiguous', status_at: '2026-09-24T08:47:00Z',
    candidate: { home: 'Hammarby', away: 'AIK', score: 0.623 } }, at)
  assert.equal(s.cls, 'st-miss')
  assert.equal(s.txt, 'tvetydig: flera Pinnacle-kandidater · närmaste kandidat: '
    + 'Hammarby – AIK (likhet 62 %) · senast observerad [2026-09-24T08:47:00Z]')
})

test('ingen ny hämtning utlovas och okänd status visas rått', () => {
  const never = sharpPanelStatus({ status: 'never_observed', status_at: null }, at)
  assert.equal(never.txt, 'inte observerad av insamlingen än')
  assert.doesNotMatch(never.txt, /ompollad|uppdatera|hämtar/i)
  assert.equal(sharpPanelStatus({ status: 'något_nytt' }, at).txt, 'något_nytt')
  const listed = sharpPanelStatus({ status: 'not_listed', candidate: { home: 'A', away: 'B' } }, at)
  assert.equal(listed.txt, 'ej listad hos Pinnacle eller namnet matchade inte · närmaste kandidat: A – B')
})
