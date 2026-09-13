// Historik → Tester: EN rad per experiment ur /api/pool/tests och varje tests
// egen sida. Statusorden är backendens (samma trappa som cli.py gater):
// samlar → underlag klart → granskad → infört/avslutad. Inga riktiga insatser.
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { FORWARD_TEST } from '../lib/labels.js'
import { statusTone, progressText } from '../lib/tests.js'
import { ForwardTestV3 } from './ForwardTestV3.jsx'
import { SystemfacitCard } from './SystemfacitCard.jsx'
import { PoolmodellCard } from './PoolmodellCard.jsx'
import { LoadingState, ErrorState } from '../App.jsx'

export function StatusPill({ status }) {
  return <span className={`v3teststatus ${statusTone(status)}`}>{status || 'samlar'}</span>
}

function TestRow({ test, onOpenTest }) {
  return (
    <article className={`v3testrow${test.archived ? ' archived' : ''}`}>
      <div><h4>{test.icon} {test.title}</h4><p>{test.purpose}</p></div>
      <div className="v3testmeta">
        <span><StatusPill status={test.status} /></span>
        <span>version <b>{test.version || '–'}</b></span>
        <span>underlag <b>{progressText(test)}</b></span>
        {test.open_coupons != null && <span>öppna kuponger <b>{test.open_coupons}</b></span>}
        {test.decision && <span>{test.decision.date} · {test.decision.verdict}</span>}
      </div>
      <button className="v3more" onClick={() => onOpenTest(test.id)}>Följ testet →</button>
    </article>
  )
}

function TestCatalog({ tests, onOpenTest }) {
  const active = tests.filter((test) => !test.archived)
  const archived = tests.filter((test) => test.archived)
  return (
    <div className="v3card">
      <div className="v3cardhead"><h3>🧪 Tester</h3>
        <span className="v3hint">inga riktiga insatser · statusen kommer från varje tests egen förregistrering</span></div>
      <div className="v3testlist">{active.map((test) => <TestRow key={test.id} test={test} onOpenTest={onOpenTest} />)}</div>
      {archived.length > 0 && (
        <details className="v3ph5explain">
          <summary>Arkiv · avslutade experiment ({archived.length})</summary>
          <div className="v3testlist">{archived.map((test) => <TestRow key={test.id} test={test} onOpenTest={onOpenTest} />)}</div>
        </details>
      )}
    </div>
  )
}

function GateCard({ test }) {
  const fraction = (cell) => (cell.n == null ? '–'
    : `${cell.n}${cell.krav != null ? `/${cell.krav}` : ''}`)
  return (
    <div className="v3card">
      <p className="v3hint">{test.purpose}</p>
      <div className="v3ph5kpis">
        <div><span>Version</span><b>{test.version || '–'}</b></div>
        <div><span>Underlag</span><b>{progressText(test)}</b></div>
        {test.open_coupons != null && <div><span>Öppna kuponger</span><b>{test.open_coupons}</b></div>}
        <div><span>Beslutsregel</span><b><code>{test.doc}</code></b></div>
      </div>
      {test.decision && (
        <div className="v3decision">
          <b>{test.decision.date} · {test.decision.verdict}</b>
          <span>{test.decision.text}</span>
          <span className="v3hint"><code>{test.decision.doc}</code></span>
        </div>
      )}
      {test.cells?.length > 0 && (
        <div className="v3histtablewrap"><table className="v3histtable">
          <thead><tr><th>Grind</th><th>Status</th><th>n/krav</th><th>Anmärkning</th></tr></thead>
          <tbody>{test.cells.map((cell, index) => (
            <tr key={index}>
              <td>{cell.namn}</td>
              <td><StatusPill status={cell.status} /></td>
              <td>{fraction(cell)}{cell.dagar != null ? ` · ${cell.dagar}${cell.dagar_krav != null ? `/${cell.dagar_krav}` : ''} dygn` : ''}</td>
              <td className="v3hint">{cell.anm}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      <span className="v3hint">Avläsning av testets egen grind; beslutet fattas i dokumentet, aldrig löpande här.</span>
    </div>
  )
}

export function Tester({ test = null, open = null, onOpenTest, onOpenCoupon, onCloseCoupon }) {
  const [catalog, setCatalog] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let current = true
    get('/api/pool/tests')
      .then((value) => { if (current) setCatalog(value) })
      .catch((reason) => { if (current) setErr(String(reason)) })
    return () => { current = false }
  }, [])
  if (err) return <ErrorState message={err} />
  if (!catalog) return <LoadingState label="Hämtar testkatalogen…" />
  if (!test) return <TestCatalog tests={catalog.tests || []} onOpenTest={onOpenTest} />
  const entry = (catalog.tests || []).find((item) => item.id === test)
  if (!entry) {
    return <div className="v3card"><ErrorState message={`Okänt test: ${test}`} />
      <button className="v3more" onClick={() => onOpenTest(null)}>← Alla tester</button></div>
  }
  return (
    <div className="v3tester">
      <div className="v3testerhead">
        <button className="v3more" onClick={() => onOpenTest(null)}>← Alla tester</button>
        <h2>{entry.icon} {entry.title}</h2>
        <StatusPill status={entry.status} />
      </div>
      <GateCard test={entry} />
      {FORWARD_TEST[test] && (
        <ForwardTestV3 key={test} family={test} open={open}
          onOpenCoupon={onOpenCoupon} onCloseCoupon={onCloseCoupon} />
      )}
      {test === 'standard' && (
        <SystemfacitCard initialOpen={open} onOpenSystem={onOpenCoupon} onCloseSystem={onCloseCoupon} />
      )}
      {test === 'poolstyrka' && <PoolmodellCard />}
    </div>
  )
}
