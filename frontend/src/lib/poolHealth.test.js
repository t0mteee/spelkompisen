import test from 'node:test'
import assert from 'node:assert/strict'
import {
  splitPoolIssues, poolIssueLabel, poolNoticeSummary, splitServerIssues, kindLabel,
  sinceText, serverIssueText, serverNoticeSummary, vaktNotesSummary,
} from './poolHealth.js'

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

// Driftvakten (backend/app/vakt.py): product "server" är driften, inte
// poolunderlaget, och info-noteringar kommer aldrig som issues.
const server = [
  { level: 'error', product: 'server', kind: 'kalla_nere', key: 'sofa_model',
    since: '2026-09-25T10:43:18Z', message: 'sofa_model har fallerat i 25 källprov i rad: status 403' },
  { level: 'warning', product: 'server', kind: 'backend_5xx', key: 'access', held: true,
    since: '2026-10-01T12:00:00Z', message: '6 serverfel (5xx) i API:t sedan förra kontrollen' },
  { level: 'warning', product: 'server', kind: 'backup_stale', message: 'gammal backup' },
]

test('driftens issues hålls isär från poolunderlaget', () => {
  const pool = splitPoolIssues([...issues, ...server])
  assert.deepEqual(pool.errors.map((i) => i.kind), ['stale_snapshots'])
  assert.ok(![...pool.current, ...pool.history].some((i) => i.product === 'server'))
  const { errors, warnings } = splitServerIssues([...issues, ...server])
  assert.deepEqual(errors.map((i) => i.key), ['sofa_model'])
  assert.deepEqual(warnings.map((i) => i.kind), ['backend_5xx', 'backup_stale'])
  assert.deepEqual(splitServerIssues(undefined), { errors: [], warnings: [] })
})

test('driftfynd har svenska etiketter, svensk tid och egen rubrik', () => {
  assert.equal(kindLabel('kalla_nere'), 'datakälla svarar inte')
  assert.equal(kindLabel('okänd_sort'), 'okänd_sort')
  assert.equal(sinceText('2026-09-25T10:43:18Z'), 'sedan 25/9 12:43')
  assert.equal(sinceText(null), '')
  assert.equal(sinceText('inte en tid'), '')
  assert.equal(serverIssueText(server[0]),
    'sofa_model har fallerat i 25 källprov i rad: status 403 · sedan 25/9 12:43')
  assert.match(serverIssueText(server[1]), /senaste kända läge$/)
  assert.equal(serverNoticeSummary(splitServerIssues(server).warnings),
    'Drift att se över: serverfel i API:t · databasbackupen är gammal')
  assert.equal(serverNoticeSummary([]), null)
})

test('vaktens noteringar sammanfattas utan att bli larm', () => {
  const vakt = { checked_at: '2026-10-01T14:00:00Z', notes: [
    { kind: 'test_status_andrad', message: 'Poolstyrka: samlar → underlag klart' },
    { kind: 'avlasningspunkt_nadd', message: 'Ö/U-totalen: 40/40' },
  ] }
  assert.equal(vaktNotesSummary(vakt),
    'Vakten noterade senaste 7 dygnen: test bytte status · avläsningspunkt nådd')
  assert.equal(vaktNotesSummary({ notes: [] }), null)
  assert.equal(vaktNotesSummary(null), null)
})
