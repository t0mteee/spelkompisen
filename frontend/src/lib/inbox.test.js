import { test } from 'node:test'
import assert from 'node:assert/strict'
import { answerText, deployResultText, implementText, inboxSummary, isDeploy, itemLabel, kindLabel, recommendedIndex, splitInbox } from './inbox.js'

const beslut = (id, status = 'vantar', svar = null) => ({
  id, typ: 'beslut', status, svar, rubrik: `b${id}`,
  alternativ: [{ text: 'Flashscore' , rekommenderas: true }, { text: 'Vänta' }],
})
const forslag = (id, status = 'vantar') => ({
  id, typ: 'forslag_forbattring', status, svar: null, rubrik: `f${id}`, alternativ: [],
})

test('splitInbox delar på väntande beslut, förslag och besvarade', () => {
  const out = splitInbox([beslut(1), forslag(2), beslut(3, 'besvarad'), beslut(4, 'utgangen')])
  assert.deepEqual(out.beslut.map((p) => p.id), [1])
  assert.deepEqual(out.forslag.map((p) => p.id), [2])
  assert.deepEqual(out.besvarade.map((p) => p.id), [3, 4])
})

test('inboxSummary räknar beslut och förslag, null när inget väntar', () => {
  assert.equal(inboxSummary({ tabeller: true, poster: [beslut(1), beslut(2), forslag(3)] }),
    '2 beslut och 1 förslag väntar')
  assert.equal(inboxSummary({ tabeller: true, poster: [beslut(1, 'besvarad')] }), null)
  assert.equal(inboxSummary({ tabeller: false, poster: [] }), null)
  assert.equal(inboxSummary(null), null)
})

test('recommendedIndex hittar rekommendationen', () => {
  assert.equal(recommendedIndex(beslut(1)), 0)
  assert.equal(recommendedIndex({ alternativ: [{ text: 'a' }] }), null)
})

test('answerText visar valt alternativ och utgångna beslut', () => {
  const svarad = beslut(1, 'besvarad', { val: '0', tid: '2026-10-02T08:00:00Z' })
  assert.match(answerText(svarad), /Flashscore$/)
  assert.equal(answerText(beslut(2, 'utgangen')), 'Sista tiden passerade utan svar')
  const f = { ...forslag(3, 'besvarad'), svar: { val: 'kor_nu', tid: '2026-10-02T08:00:00Z' } }
  assert.match(answerText(f), /Kör nu$/)
})

test('kindLabel', () => {
  assert.equal(kindLabel('forslag_spelrad'), 'Spelråd')
  assert.equal(kindLabel('beslut'), 'Beslut')
})

const drift = (status = 'vantar', svar = null, resultat = null) => ({
  id: 9, typ: 'beslut', status, svar, rubrik: 'Ny Live-flik',
  alternativ: [{ text: 'Godkänn: kör stegen' }, { text: 'Avvisa' }],
  driftsattning: { commit: 'a'.repeat(40), steg: ['bygg_app', 'push'], resultat },
})

test('driftsättning känns igen och räknas som beslut', () => {
  assert.equal(isDeploy(drift()), true)
  assert.equal(isDeploy(beslut(1)), false)
  assert.equal(itemLabel(drift()), 'Driftsättning')
  assert.equal(itemLabel(beslut(1)), 'Beslut')
  assert.deepEqual(splitInbox([drift()]).beslut.map((p) => p.id), [9])
})

test('driftsättningens resultat i klartext', () => {
  assert.equal(deployResultText(drift()), null)
  assert.equal(deployResultText(drift('besvarad', null, { status: 'pagar' })), 'Körs nu')
  assert.equal(deployResultText(drift('besvarad', null, { status: 'avbruten', orsak: 'fel commit' })),
    'Avbruten: fel commit')
  const klar = drift('besvarad', { val: '0', tid: '2026-10-14T08:00:00Z' }, { status: 'gron' })
  assert.match(answerText(klar), /Godkänd · Klar, grön hälsa$/)
  const nej = drift('besvarad', { val: '1', tid: '2026-10-14T08:00:00Z' })
  assert.match(answerText(nej), /Avvisad$/)
})

test('implementText visar det automatiska genomförandet', () => {
  const item = (genomforande) => ({ typ: 'beslut', status: 'besvarad', genomforande,
    alternativ: [{ text: 'Lägg aliaset' }], svar: { val: '0', tid: '2026-10-15T08:00:00Z' } })
  assert.equal(implementText(item(null)), null)
  assert.equal(implementText(item({ status: 'pagar' })), 'Genomförs nu')
  assert.equal(implementText(item({ status: 'genomfort', sammanfattning: 'Aliaset ligger i v8.',
    commit: 'abcdef1234' })), 'Genomfört: Aliaset ligger i v8. (commit abcdef1)')
  assert.equal(implementText(item({ status: 'fel', orsak: 'session limit', omforsok: true })),
    'Misslyckades: session limit, nytt försök om en timme')
  assert.match(answerText(item({ status: 'pagar' })), /Lägg aliaset · Genomförs nu$/)
})
