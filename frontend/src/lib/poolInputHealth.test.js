import test from 'node:test'
import assert from 'node:assert/strict'
import { poolInputTitle, poolReviewText, sourceLabel } from './poolInputHealth.js'

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
