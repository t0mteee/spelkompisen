// Poolmodell · Pinnacle + lagstyrka (pool-strength-blend-v1). Bruten ur
// HistorikV3.jsx 2026-09-13 (Historik → Tester → Poolstyrka).
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { IS_FAMILY } from '../lib/labels.js'
import { LabbPill } from '../components/badges.jsx'

export function PoolmodellCard({ product = 'alla' }) {
  const single = product !== 'alla'
  const [strength, setStrength] = useState(null)
  useEffect(() => {
    let current = true
    const query = single ? `?product=${product}${IS_FAMILY(product) ? '&family=1' : ''}` : ''
    get(`/api/pool/strength-shadow${query}`)
      .then((value) => { if (current) setStrength(value) })
      .catch(() => { if (current) setStrength(null) })
    return () => { current = false }
  }, [product, single])
  return (
    <>
      {/* ---------------------- styrkemodell-shadow ---------------------- */}
      <div className="v3card">
        <div className="v3cardhead">
          <h3>🧬 Poolmodell · Pinnacle + lagstyrka</h3>
          <LabbPill s={strength?.status || 'samlar'} />
        </div>
        <span className="v3hint">
          Här provar vi om den xG-viktade styrketabellen förbättrar Pinnacles
          1X2-prognos. Kandidaten väger <b>90 % Pinnacle och 10 % lagstyrka</b>;
          80/20 visas som ett känslighetstest. Det här ändrar inga system eller
          spel medan mätningen pågår.
        </span>
        {strength?.stopped && (
          // Spårets egen spärr (capture_due) vägrar samla när modellens
          // signalversion inte längre är manifestets. Det ska synas här i
          // stället för att kortet ser ut att växa.
          <div className="v3note" role="status" style={{ marginTop: 12 }}>
            <b>Insamlingen står still:</b> {strength.stopped.text}. Nya matcher
            sparas inte förrän ett nytt manifest frysts (manifestets
            change_policy); redan insamlade rader räknas som förut.
          </div>
        )}

        <div className="v3histkpis" style={{ marginTop: 12 }}>
          <div className="v3kpi"><b>{strength?.captured ?? 0}</b>
            <span>matcher observerade</span></div>
          <div className="v3kpi"><b>{strength?.eligible ?? 0}</b>
            <span>med både sharp och styrka</span></div>
          <div className="v3kpi"><b>{strength?.settled ?? 0}</b>
            <span>med riktigt facit</span></div>
          <div className="v3kpi"><b>{strength?.coverage != null
            ? `${Math.round(strength.coverage * 100)} %` : '–'}</b>
            <span>datatäckning</span></div>
          <div className="v3kpi"><b>{strength?.decay_half_life_days ?? 166} d</b>
            <span>halveringstid · färska matcher väger mest</span></div>
        </div>

        {strength && (
          <div className="v3histtablewrap">
            <table className="v3histtable">
              <thead><tr>
                <th>Mätt före stopp</th><th>Med facit</th><th>90/10 mot Pinnacle</th>
                <th>90 % KI</th><th>80/20 test</th><th>Läge</th>
              </tr></thead>
              <tbody>
                {['h24', 'h3', 'm20'].map((horizon) => {
                  const row = strength.horizons?.[horizon] || {}
                  const metrics = Object.fromEntries((row.metrics || [])
                    .map((metric) => [metric.candidate, metric]))
                  const primary = metrics.blend10 || {}
                  const diagnostic = metrics.blend20 || {}
                  const delta = (value) => value == null ? '–'
                    : `${value > 0 ? '+' : ''}${value.toFixed(4)}`
                  return (
                    <tr key={horizon}>
                      <td>{{ h24: '24 timmar', h3: '3 timmar', m20: '20 minuter' }[horizon]}</td>
                      <td>{row.settled || 0} / {strength.gate?.minimum_settled_events_per_horizon || 300}</td>
                      <td className={primary.mean_delta_logloss > 0 ? 'v3pos'
                        : primary.mean_delta_logloss < 0 ? 'v3neg' : ''}>
                        {delta(primary.mean_delta_logloss)}</td>
                      <td>{primary.ci90
                        ? `${delta(primary.ci90[0])} … ${delta(primary.ci90[1])}` : '–'}</td>
                      <td className={diagnostic.mean_delta_logloss > 0 ? 'v3pos'
                        : diagnostic.mean_delta_logloss < 0 ? 'v3neg' : ''}>
                        {delta(diagnostic.mean_delta_logloss)}</td>
                      <td>{row.data_ready
                        ? <b className="v3pos">mängdkrav nått</b>
                        : <span className="v3hint">{strength.stopped ? 'stoppad' : 'samlar'}</span>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {!strength?.captured && (
          <div className="v3note" style={{ marginTop: 12 }}>
            Första datapunkterna sparas automatiskt när en kommande kupong når
            24 timmar, 3 timmar eller 20 minuter före spelstopp och Pinnacle är
            tillgängligt. Äldre sannolikheter fylls aldrig i efterhand.
          </div>
        )}
        {!!strength && Object.keys(strength.issues || {}).length > 0 && (
          <span className="v3hint">Bortfall: {Object.entries(strength.issues)
            .map(([issue, n]) => `${{
              unsupported_league: 'liga utan styrkemodell', missing_sharp: 'sharp saknas',
              unlinked_team: 'lag ej säkert länkat', thin_history: 'för tunn historik',
              missing_fit: 'styrkefit saknas', missing_prediction: 'prognos saknas',
              cancelled: 'struken match',
            }[issue] || issue} ${n}`).join(' · ')}</span>
        )}
        <span className="v3hint">Positiv skillnad betyder att blandningen
          träffar bättre än Pinnacle. Ett beslut kräver minst{' '}
          {strength?.gate?.minimum_settled_events_per_horizon ?? 300} avgjorda
          matcher per beslutstid, minst{' '}
          {strength?.gate?.minimum_settled_per_league ?? 30} per liga och{' '}
          {strength?.gate?.minimum_span_days ?? 42} dagar. Därefter krävs en
          separat systemmätning innan poolbyggaren ens kan övervägas.</span>
      </div>
    </>
  )
}
