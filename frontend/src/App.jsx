import { Fragment, useEffect, useState } from 'react'
import './App.css'

const STRATEGIES = ['säker', 'medel', 'tuff']
const fmt = (o) => (o === null || o === undefined ? '–' : o.toFixed(2))

function timeAgo(iso) {
  if (!iso) return 'aldrig'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 90) return 'nyss'
  if (s < 3600) return `${Math.round(s / 60)} min sedan`
  if (s < 86400) return `${Math.round(s / 3600)} h sedan`
  return `${Math.round(s / 86400)} dygn sedan`
}

/* ---------- insamling (launchd – körs även när appen är stängd) ---------- */
function Collection() {
  const [st, setSt] = useState(null)
  const refresh = async () => { try { setSt(await (await fetch('/api/collection/status')).json()) } catch { /* */ } }
  const start = async () => { await fetch('/api/collection/start', { method: 'POST' }); refresh() }
  const stop = async () => { await fetch('/api/collection/stop', { method: 'POST' }); refresh() }
  useEffect(() => { refresh(); const id = setInterval(refresh, 10000); return () => clearInterval(id) }, [])

  const active = st?.active
  return (
    <div className="collection">
      <span className={`dot ${active ? 'on' : 'off'}`} />
      <strong>Datainsamling</strong>
      <span className="cstatus">
        {active ? 'aktiv' : 'stoppad'} (launchd, var 30:e min)
        {st ? ` · senaste: ${timeAgo(st.last_snapshot)} · ${st.snapshot_count} mättillfällen` : ''}
      </span>
      {active
        ? <button onClick={stop}>⏹ Stoppa insamling</button>
        : <button className="primary" onClick={start}>▶ Starta insamling</button>}
    </div>
  )
}

/* ---------- folkfördelning (streck %) som 3-segmentsstapel ---------- */
function StreckBar({ outcomes }) {
  const segs = ['1', 'X', '2'].map((s) => outcomes[s].streck || 0)
  const tot = segs.reduce((a, b) => a + b, 0) || 1
  const colors = { 0: '#4aa3df', 1: '#8b97a5', 2: '#e0853b' }
  return (
    <div className="streckbar" title={`Folket: 1=${segs[0]}% X=${segs[1]}% 2=${segs[2]}%`}>
      {segs.map((v, i) => (
        <div key={i} className="seg" style={{ width: `${(v / tot) * 100}%`, background: colors[i] }}>
          {v >= 12 ? `${v}` : ''}
        </div>
      ))}
    </div>
  )
}

/* ---------- förslagsbadge (ersätter de otydliga spik/öppen-staplarna) ---------- */
function Forslag({ m }) {
  const fav = m.favourite
  const map = {
    spik: ['b-spik', `Spik ${fav}`],
    halvspik: ['b-half', `Halvspik ${fav}`],
    gardera: ['b-open', 'Gardera'],
    lutar: ['b-lean', `Lutar ${fav}`],
    avvakta: ['b-lean', 'Avvakta'],
  }
  const [cls, txt] = map[m.speltyp] || ['b-lean', `Lutar ${fav}`]
  return (
    <div className="forslag" title={`favorit ${Math.round((m.favourite_prob || 0) * 100)}% · spik-styrka ${Math.round(m.spik_score)}/100 · öppenhet ${Math.round(m.open_score)}/100`}>
      <span className={`badge ${cls}`}>{txt}</span>
      <div className="rec">{m.recommendation}</div>
    </div>
  )
}

function OddsCell({ o, derived }) {
  const cls = ['cell']
  if (o.tags?.includes('värdestreck') || o.tags?.includes('sharp_värde')) cls.push('value')
  if (o.tags?.includes('ss_undervärderad')) cls.push('edge')
  return (
    <td className={cls.join(' ')}>
      <div className="odds">{fmt(o.odds)}</div>
      <div className="streck">{o.streck != null ? `${o.streck}%` : '–'}</div>
      {o.sharp_odds != null && (
        <div className="sharpodds" title={derived ? 'härledd från spread/total' : 'sharp (Pinnacle)'}>
          {derived ? 'P~' : 'P'} {fmt(o.sharp_odds)}
        </div>
      )}
      <div className="marks">
        {o.tags?.includes('värdestreck') && <span title="värdestreck (SS)">★</span>}
        {o.tags?.includes('sharp_värde') && <span className="m-sharp" title="sharp ser värde vs folket">S</span>}
        {o.tags?.includes('ss_undervärderad') && <span className="m-edge" title="SS-odds för höga vs sharp">▲</span>}
        {o.tags?.includes('rörelse_ner') && <span className="m-move-down" title={`stärks i snapshots: ${o.move_from}→${o.move_to}`}>⇊</span>}
        {o.tags?.includes('rörelse_upp') && <span className="m-move-up" title={`försvagas: ${o.move_from}→${o.move_to}`}>⇈</span>}
        {o.tags?.includes('fallande_odds') && <span title="fallande vs startodds">↓</span>}
      </div>
    </td>
  )
}

function AnalysisTable({ matches, drawNumber, selected, onSelect }) {
  return (
    <table className="grid">
      <thead>
        <tr><th>#</th><th>Match</th><th>1</th><th>X</th><th>2</th><th>Folket (1·X·2)</th><th>Förslag</th></tr>
      </thead>
      <tbody>
        {matches.map((m) => {
          const derived = (m.sharp_bookmaker || '').includes('härledd')
          return (
            <Fragment key={m.event_number}>
              <tr className={selected === m.event_number ? 'sel' : ''}>
                <td>{m.event_number}</td>
                <td className="match clickable" onClick={() => onSelect(selected === m.event_number ? null : m.event_number)}>
                  {m.description}
                  <div className="league">{m.league}{derived ? ' · sharp härledd' : ''} · klicka för graf</div>
                </td>
                <OddsCell o={m.outcomes['1']} derived={derived} />
                <OddsCell o={m.outcomes['X']} derived={derived} />
                <OddsCell o={m.outcomes['2']} derived={derived} />
                <td><StreckBar outcomes={m.outcomes} /></td>
                <td><Forslag m={m} /></td>
              </tr>
              {selected === m.event_number && (
                <tr className="chartrow"><td colSpan={7}>
                  <MovementChart drawNumber={drawNumber} eventNumber={m.event_number} />
                </td></tr>
              )}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}

function MovementChart({ drawNumber, eventNumber }) {
  const [hist, setHist] = useState(null)
  useEffect(() => {
    let on = true
    fetch(`/api/history?draw=${drawNumber}&event=${eventNumber}`)
      .then((r) => r.json()).then((d) => { if (on) setHist(d.history || []) })
    return () => { on = false }
  }, [drawNumber, eventNumber])

  if (!hist) return <div className="loading">Hämtar historik…</div>
  if (hist.length < 2) return <div className="loading">För få mätpunkter ännu – insamlingen bygger upp detta över tid.</div>

  const colors = { '1': '#4aa3df', X: '#8b97a5', '2': '#e0853b' }
  const W = 520, H = 160, pad = 28
  const times = [...new Set(hist.map((r) => r.fetched_at))].sort()
  const xs = (t) => pad + (times.indexOf(t) / (times.length - 1)) * (W - 2 * pad)
  const odds = hist.map((r) => r.odds).filter((v) => v != null)
  const lo = Math.min(...odds), hi = Math.max(...odds)
  const ys = (v) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - 2 * pad)
  const bySign = { '1': [], X: [], '2': [] }
  hist.forEach((r) => { if (r.odds != null) bySign[r.sign]?.push(r) })

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`}>
      <text x={pad} y={14} className="cax">{hi.toFixed(2)}</text>
      <text x={pad} y={H - pad + 12} className="cax">{lo.toFixed(2)}</text>
      {Object.entries(bySign).map(([sign, rows]) => (
        <g key={sign}>
          <polyline fill="none" stroke={colors[sign]} strokeWidth="2"
            points={rows.map((r) => `${xs(r.fetched_at)},${ys(r.odds)}`).join(' ')} />
          {rows.map((r, i) => <circle key={i} cx={xs(r.fetched_at)} cy={ys(r.odds)} r="2.5" fill={colors[sign]} />)}
        </g>
      ))}
      {Object.entries(colors).map(([sign, c], i) => (
        <g key={sign}>
          <rect x={W - 80 + i * 26} y={8} width="10" height="10" fill={c} />
          <text x={W - 67 + i * 26} y={17} className="cleg">{sign}</text>
        </g>
      ))}
    </svg>
  )
}

/* ---------- sharp (Pinnacle, gratis, auto) – kompakt status + manuell uppdatering ---------- */
function SharpPanel({ onLoaded }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [show, setShow] = useState(false)
  const STATUS = {
    derived: { txt: 'härledd från spread/total (1X2 ej öppnad)', cls: 'st-wait' },
    no_moneyline: { txt: '1X2 ej öppnad än', cls: 'st-wait' },
    not_listed: { txt: 'ej listad hos Pinnacle ännu', cls: 'st-miss' },
  }
  const fetchSharp = async () => {
    setLoading(true)
    try {
      const d = await (await fetch('/api/external-odds?use_oddsapi=false')).json()
      setData(d); if (d.cached > 0 && onLoaded) onLoaded()
    } catch (e) { setData({ error: String(e) }) } finally { setLoading(false) }
  }
  useEffect(() => { fetchSharp() }, [])  // hämta direkt (gratis)

  const matched = data?.matches?.filter((m) => m.external) || []
  const uncovered = data?.matches?.filter((m) => !m.external) || []
  return (
    <div className="sharp">
      <div className="sharp-head">
        <strong>Sharp-odds (Pinnacle, gratis)</strong>
        <span className="cstatus">{data ? `${matched.length}/${data.matches.length} matcher` : '…'}</span>
        <button onClick={fetchSharp} disabled={loading}>{loading ? 'Hämtar…' : '↻ Uppdatera nu'}</button>
        <button onClick={() => setShow(!show)}>{show ? 'Dölj detaljer' : 'Visa detaljer'}</button>
      </div>
      <p className="hint">Hämtas automatiskt och vävs in i tabellen ovan (P = sharp, P~ = härledd från spread). Uppdateras även av bakgrundsinsamlingen.</p>
      {show && data?.matches && (
        <table className="grid compact">
          <tbody>
            {data.matches.map((m) => {
              const e = m.external
              if (e) return (
                <tr key={m.event_number}>
                  <td>{m.event_number}</td><td className="match">{m.description}</td>
                  <td className="rec">{e.matched}{e.swapped ? ' (omvänd)' : ''}{m.status === 'derived' ? ' · härledd' : ''}</td>
                  <td>{e.odds?.['1'] ?? '–'}</td><td>{e.odds?.['X'] ?? '–'}</td><td>{e.odds?.['2'] ?? '–'}</td>
                </tr>
              )
              const s = STATUS[m.status] || { txt: m.status, cls: '' }
              return (
                <tr key={m.event_number} className="norow">
                  <td>{m.event_number}</td><td className="match">{m.description}</td>
                  <td className={`rec ${s.cls}`} colSpan={4}>{s.txt}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

/* ---------- system / radbyggare ---------- */
function SystemView({ sys }) {
  if (!sys) return null
  const roleClass = { spik: 'r-spik', halvgardering: 'r-half', helgardering: 'r-full' }
  return (
    <div className="system">
      <div className="system-head">
        <strong>{sys.system_type}</strong> · {sys.strategy} ·
        <span className="rows"> {sys.num_rows} rader = {sys.cost} kr</span>
        <span className="note"> {sys.note}</span>
      </div>
      {sys.rule && <div className="rule">{sys.rule}</div>}
      <table className="grid compact">
        <thead><tr><th>#</th><th>Match</th><th>Roll</th><th>Tecken</th><th>Motivering</th></tr></thead>
        <tbody>
          {sys.picks.map((p) => (
            <tr key={p.event_number} className={roleClass[p.role]}>
              <td>{p.event_number}</td><td className="match">{p.description}</td>
              <td>{p.role}</td><td className="signs">{p.signs.join('  ')}</td>
              <td className="rec">{p.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const SYSTEM_TYPES = [
  { id: 'math', label: 'Matematiskt (alla kombinationer)', q: 'reduced=false' },
  { id: 'red', label: 'Reducerat (värde)', q: 'reduced=true' },
  { id: 'g12', label: 'Egen reducering: minst 12 rätt', q: 'reduced=true&guarantee=12' },
  { id: 'svs_r409', label: 'Svenska Spel R 4-0-9 (12 rätt, 9 rad)', q: `sv_rsystem=${encodeURIComponent('R 4-0-9')}` },
  { id: 'svs_r0716', label: 'Svenska Spel R 0-7-16 (12 rätt, 16 rad)', q: `sv_rsystem=${encodeURIComponent('R 0-7-16')}` },
  { id: 'svs_r3324', label: 'Svenska Spel R 3-3-24 (12 rätt, 24 rad)', q: `sv_rsystem=${encodeURIComponent('R 3-3-24')}` },
  { id: 'svs_r44144', label: 'Svenska Spel R 4-4-144 (12 rätt, 144 rad)', q: `sv_rsystem=${encodeURIComponent('R 4-4-144')}` },
]

export default function App() {
  const [analysis, setAnalysis] = useState(null)
  const [sys, setSys] = useState(null)
  const [strategy, setStrategy] = useState('medel')
  const [budget, setBudget] = useState(100)
  const [sysType, setSysType] = useState('math')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)

  const loadAnalysis = async () => {
    setLoading(true); setErr(null)
    try {
      const r = await fetch('/api/analysis')
      if (!r.ok) throw new Error(`Analys ${r.status}`)
      setAnalysis(await r.json())
    } catch (e) { setErr(String(e)) } finally { setLoading(false) }
  }
  const loadSystem = async () => {
    setErr(null)
    try {
      const q = SYSTEM_TYPES.find((t) => t.id === sysType).q
      const r = await fetch(`/api/system?strategy=${encodeURIComponent(strategy)}&budget=${budget}&${q}`)
      if (!r.ok) throw new Error(`System ${r.status}`)
      setSys(await r.json())
    } catch (e) { setErr(String(e)) }
  }
  useEffect(() => { loadAnalysis() }, [])

  return (
    <div className="app">
      <header>
        <h1>⚽ Stryktips-hjälpen</h1>
        {analysis && <span className="draw">Omgång {analysis.draw_number} · stänger {analysis.reg_close_time?.slice(0, 16).replace('T', ' ')}</span>}
        <button onClick={loadAnalysis}>↻ Uppdatera</button>
      </header>

      <Collection />
      {err && <div className="error">{err}</div>}
      {loading && <div className="loading">Hämtar…</div>}

      <section>
        <h2>Analys</h2>
        <p className="legend">
          <b>Förslag:</b> <span className="badge b-spik">Spik</span> stark favorit ·
          <span className="badge b-open">Gardera</span> öppen match ·&nbsp;
          <b>★</b> värdestreck · <b className="m-sharp">S</b> sharp ser värde ·
          <b className="m-edge">▲</b> SS-odds höga vs sharp · <b className="m-move-down">⇊</b> stärks i snapshots ·
          P = sharp-odds, P~ = härledd
        </p>
        {analysis && (
          <AnalysisTable matches={analysis.matches} drawNumber={analysis.draw_number}
            selected={selected} onSelect={setSelected} />
        )}
      </section>

      <section>
        <h2>Sharp-odds</h2>
        <SharpPanel onLoaded={loadAnalysis} />
      </section>

      <section>
        <h2>Bygg rad</h2>
        <div className="controls">
          {STRATEGIES.map((s) => (
            <label key={s} className={strategy === s ? 'active' : ''}>
              <input type="radio" name="strategy" checked={strategy === s} onChange={() => setStrategy(s)} />{s}
            </label>
          ))}
          <label className="budget">Budget (kr)
            <input type="number" min="1" value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </label>
          <select value={sysType} onChange={(e) => setSysType(e.target.value)}>
            {SYSTEM_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <button className="primary" onClick={loadSystem}>Föreslå rad</button>
        </div>
        <SystemView sys={sys} />
      </section>

      <footer>Lokal data från Svenska Spel + Pinnacle · personligt verktyg</footer>
    </div>
  )
}
