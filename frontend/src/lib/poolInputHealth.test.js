import test from 'node:test'
import assert from 'node:assert/strict'
import { poolInputTitle, poolReviewText, sourceLabel, xSkyddText } from './poolInputHealth.js'

const health = { version: 'pool-input-health-v1', product: 'topptipsetstryk', draw_number: 981,
  analysis_fetched_at: '2026-09-21T10:00:00Z', n_matches: 8, level: 'warning',
  missing_all: 0, missing_sharp: 2, missing_svs: 0, missing_total: 3,
  issues: [{ event_number: 3, description: 'Everton – Ipswich', missing: ['Pinnacle 1X2'], prob_source: 'odds' }] }

test('prioritera odds från båda källorna, sedan sharp, SvS och Ö/U', () => {
  assert.equal(poolInputTitle(null), null)
  assert.equal(poolInputTitle({ ...health, level: 'ok' }), null)
  assert.match(poolInputTitle(health), /Pinnacle 1X2 saknas i 2\/8/)
  assert.match(poolInputTitle({ ...health, missing_all: 1 }), /båda källorna i 1\/8/)
  assert.match(poolInputTitle({ ...health, missing_sharp: 0, missing_svs: 1 }), /SvS 1X2/)
  assert.match(poolInputTitle({ ...health, missing_sharp: 0 }), /Ö\/U-underlag/)
})

test('granskningsunderlaget bevarar exakt produkt, omgång, tid och matcher', () => {
  const text = poolReviewText(health, 'Systembygget')
  assert.match(text, /topptipsetstryk · omgång 981 · Systembygget/)
  assert.match(text, /2026-09-21T10:00:00Z/)
  assert.match(text, /3\. Everton – Ipswich: saknar Pinnacle 1X2/)
  assert.match(text, /Sannolikhetsbas: SvS-odds/)
  assert.match(text, /inte bevis på färskhet/)
  assert.match(text, /Bakfyll inte odds/)
  assert.equal(sourceLabel('streck'), 'folkets streck')
})

test('inaktuella Pinnacle-priser syns i rubriken och orsaken följer med underlaget', () => {
  const stale = { ...health, stale_sharp: 1, freshness_version: 'pool-sharp-freshness-v1',
    issues: [{ ...health.issues[0], reason: 'Pinnacle-länken tappad (tvetydig) sedan 10:47' }] }
  assert.match(poolInputTitle(stale), /Pinnacle 1X2 saknas i 2\/8 matcher \(1 med inaktuellt pris\)/)
  assert.doesNotMatch(poolInputTitle(health), /inaktuellt/)
  const text = poolReviewText(stale)
  assert.match(text, /pool-input-health-v1 \+ pool-sharp-freshness-v1/)
  assert.match(text, /varav 1 med inaktuellt cachat pris/)
  assert.match(text, /3\. Everton – Ipswich: saknar Pinnacle 1X2\. Sannolikhetsbas: SvS-odds\. Orsak: Pinnacle-länken tappad \(tvetydig\) sedan 10:47\./)
  assert.match(text, /högst 90 min gammalt/)
})

test('pool-reference-v1: info-rubrik när Smarkets/SBOBET täcker varje match utan Pinnacle', () => {
  const info = { ...health, level: 'info', missing_sharp: 8, reference_1x2: 8 }
  assert.match(poolInputTitle(info), /Pinnacle spärrad — Smarkets\/SBOBET som referens i 8\/8 matcher/)
  assert.match(poolReviewText(info), /varav 8 med referens \(Smarkets\/SBOBET, bara visning\)/)
  assert.match(poolInputTitle({ ...info, level: 'warning', reference_1x2: 7 }), /Pinnacle 1X2 saknas i 8\/8/)
})

test('pool-draw-risk-v2: X-skyddets text säger var Kambis Ö/U-lina används', () => {
  assert.match(xSkyddText({ n_matches: 8, total_kambi: 8, missing_total: 0 }), /Svenska Spels Ö\/U-lina \(Kambi\) i 8\/8 matcher\.$/)
  assert.match(xSkyddText({ n_matches: 8, total_kambi: 6, missing_total: 2 }), /i 6\/8 matcher; 2 saknar Ö\/U och får 32 %-gränsen/)
  assert.match(xSkyddText({ n_matches: 8, total_kambi: 0, missing_total: 3 }), /Ö\/U saknas i 3\/8 matcher/)
  assert.equal(xSkyddText({ n_matches: 8, total_kambi: 0, missing_total: 0 }), '')
})
