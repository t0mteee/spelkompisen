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
function Legend() {
  const [open, setOpen] = useState(false)
  return (
    <div className="legendbox">
      <button className="legend-toggle" onClick={() => setOpen(!open)}>
        ℹ Vad betyder färgerna & symbolerna? {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="legend">
          <div><b>Färgad kvot</b> (under oddset) = <b>värde</b> = oddsens sannolikhet ÷ folkets streck.
            {' '}<span className="vpill v-green">≥1.08</span> marknaden tror mer än folket (köpläge) ·
            {' '}<span className="vpill v-yellow">~1.0</span> rätt streckad ·
            {' '}<span className="vpill v-red">≤0.92</span> överspelad.</div>
          <div><b>P</b> = Pinnacle (sharp bookmaker) odds · <b>P~</b> = härlett från handikapp när 1X2 inte öppnats.</div>
          <div><b>Förslag:</b> <span className="badge b-spik">Spik</span> stark favorit ·
            {' '}<span className="badge b-half">Värdespik</span> kort odds men lågt streck (undervärderad) ·
            {' '}<span className="badge b-open">Gardera</span> öppen match.</div>
          <div>Märken: <b className="m-sharp">S</b> sharp ser värde folket missat ·
            {' '}<b className="m-edge">▲</b> Svenska Spels odds högre än Pinnacle (felprisat) ·
            {' '}<b className="m-move-down">⇊</b> oddset har stärkts i våra mätningar · ↓ fallande mot startodds.</div>
          <div>Rörelse-flaggor (håll muspekaren för detaljer):
            {' '}<span className="mover mv-odds"><b>1X2</b> ↓</span> oddset har sjunkit markant (marknaden tror mer) ·
            {' '}<span className="mover mv-odds mv-late"><b>1X2</b> ↓ 🔥</span> <b>sen oddssänkning nära avspark</b> – ofta ett mycket bra streck ·
            {' '}<span className="mover mv-streck">👥</span> folket har svängt markant.</div>
        </div>
      )}
    </div>
  )
}

function StreckBar({ outcomes }) {
  const signs = ['1', 'X', '2']
  const segs = signs.map((s) => outcomes[s].streck || 0)
  const tot = segs.reduce((a, b) => a + b, 0) || 1
  const cls = ['sb-1', 'sb-x', 'sb-2']
  return (
    <div className="streckbar" title={`Folkets streck: 1 ${segs[0]}% · X ${segs[1]}% · 2 ${segs[2]}%`}>
      {segs.map((v, i) => {
        const w = (v / tot) * 100
        return (
          <div key={i} className={`seg ${cls[i]}`} style={{ width: `${w}%` }}>
            {w >= 16 ? <><b>{signs[i]}</b> {v}%</> : w >= 9 ? `${v}` : ''}
          </div>
        )
      })}
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
  const tips = {
    spik: 'Stark favorit – kan singlas.',
    halvspik: 'Halvfavorit – singla djärvt eller halvgardera.',
    värdespik: 'Kort odds men lågt streck – undervärderad av folket, bra att singla.',
    gardera: 'Öppen match utan klar favorit – ta flera tecken.',
    lutar: 'Svag favorit – luta hit men gardera gärna.',
    avvakta: 'Odds saknas än – avvakta.',
  }
  const badgeTitle = `${tips[m.speltyp] || ''} (favorit ${Math.round((m.favourite_prob || 0) * 100)}%, spik-styrka ${Math.round(m.spik_score)}/100)`
  const mv = m.mover
  return (
    <div className="forslag" title={`spik-styrka ${Math.round(m.spik_score)}/100 · öppenhet ${Math.round(m.open_score)}/100`}>
      <span className={`badge ${cls}`} title={badgeTitle}>{txt}</span>
      {mv && (
        <span className="moverflags">
          {mv.odds_sign && (
            <span className={`mover mv-odds ${mv.late ? 'mv-late' : ''}`}
              title={`Oddsrörelse: ${mv.odds_sign} ${mv.odds_from}→${mv.odds_to} (−${Math.round(mv.odds_drop_pct * 100)}%)`
                + (mv.late ? ' · sen sänkning nära avspark – stark signal' : ' sedan vi började mäta')}>
              <b>1X2</b> {mv.odds_sign}↓{Math.round(mv.odds_drop_pct * 100)}%{mv.late ? ' 🔥' : ''}
            </span>
          )}
          {mv.streck_sign && (
            <span className="mover mv-streck"
              title={`Folkrörelse: strecket på ${mv.streck_sign} har ${mv.streck_move > 0 ? 'ökat' : 'minskat'} `
                + `${Math.abs(mv.streck_move)} procentenheter sedan vi började mäta`}>
              👥 {mv.streck_sign} {mv.streck_move > 0 ? '+' : '−'}{Math.abs(mv.streck_move)}%
            </span>
          )}
        </span>
      )}
      <div className="rec">{m.recommendation}</div>
    </div>
  )
}

function OddsCell({ o, derived, picked, onToggle, valueOk }) {
  const cls = ['cell', 'pickcell']
  if (o.tags?.includes('värdestreck') || o.tags?.includes('sharp_värde')) cls.push('value')
  if (o.tags?.includes('ss_undervärderad')) cls.push('edge')
  if (picked) cls.push('picked')
  // Värde-kvot = fair-sannolikhet / streck. >1 = marknaden tror mer än folket.
  const ratio = (valueOk && o.fair_prob != null && o.streck) ? o.fair_prob / (o.streck / 100) : null
  const rcls = ratio == null ? '' : ratio >= 1.08 ? 'v-green' : ratio <= 0.92 ? 'v-red' : 'v-yellow'
  const ratioTitle = ratio == null ? '' : `Värde ${ratio.toFixed(2)}: oddsens sannolikhet ${Math.round((o.fair_prob || 0) * 100)}% mot folkets ${o.streck}% streck. ` +
    (ratio >= 1.08 ? `Marknaden tror ~${Math.round((ratio - 1) * 100)}% mer än folket — köpläge.`
      : ratio <= 0.92 ? `Folket överspelar (${Math.round((1 - ratio) * 100)}% mindre sannolik än streckad).`
        : 'Ungefär rätt streckad.')
  return (
    <td className={cls.join(' ')} onClick={onToggle} title="klicka för att lägga till/ta bort i kupongen">
      <div className="odds">{fmt(o.odds)}</div>
      {o.sharp_odds != null && (
        <div className="sharpodds" title={derived ? 'Pinnacle, härledd från spread/total' : 'Pinnacle (sharp)'}>
          {derived ? 'P~' : 'P'} {fmt(o.sharp_odds)}
        </div>
      )}
      {ratio != null && <div className={`vpill ${rcls}`} title={ratioTitle}>{ratio.toFixed(2)}</div>}
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

function AnalysisTable({ matches, product, drawNumber, selected, onSelect, picks, onToggleSign }) {
  const isPicked = (ev, s) => (picks[ev] || []).includes(s)
  return (
    <table className="grid">
      <thead>
        <tr><th>#</th><th>Match</th><th>1</th><th>X</th><th>2</th><th>Folket (1·X·2)</th><th>Förslag</th></tr>
      </thead>
      <tbody>
        {matches.map((m) => {
          const derived = (m.sharp_bookmaker || '').includes('härledd')
          const valueOk = m.prob_source === 'odds' || m.prob_source === 'sharp'
          return (
            <Fragment key={m.event_number}>
              <tr className={selected === m.event_number ? 'sel' : ''}>
                <td>{m.event_number}</td>
                <td className="match clickable" title="klicka för oddsgraf"
                  onClick={() => onSelect(selected === m.event_number ? null : m.event_number)}>
                  {m.description}
                  <div className="league">🕑 {fmtStart(m.match_start)} · {m.league}{derived ? ' · sharp härledd' : ''}</div>
                </td>
                {['1', 'X', '2'].map((s) => (
                  <OddsCell key={s} o={m.outcomes[s]} derived={derived} valueOk={valueOk}
                    picked={isPicked(m.event_number, s)}
                    onToggle={() => onToggleSign(m.event_number, s)} />
                ))}
                <td><StreckBar outcomes={m.outcomes} /></td>
                <td><Forslag m={m} /></td>
              </tr>
              {selected === m.event_number && (
                <tr className="chartrow"><td colSpan={7}>
                  <MovementChart product={product} drawNumber={drawNumber} eventNumber={m.event_number} />
                </td></tr>
              )}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}

function MiniChart({ sign, pts, color }) {
  const W = 250, H = 110, padL = 38, padR = 10, padT = 18, padB = 22
  const fmtT = (iso) => new Date(iso).toLocaleString('sv-SE', { hour: '2-digit', minute: '2-digit' })
  const last = pts.length ? pts[pts.length - 1].o : null
  if (pts.length < 2) {
    return (
      <div className="mini">
        <div className="mc-title"><span className="sw" style={{ background: color }} />{sign} {last != null ? last.toFixed(2) : ''}</div>
        <div className="loading sm">för få mätpunkter ännu</div>
      </div>
    )
  }
  const odds = pts.map((p) => p.o)
  let lo = Math.min(...odds), hi = Math.max(...odds)
  if (hi === lo) { hi += 0.05; lo -= 0.05 }
  const xs = (i) => padL + (i / (pts.length - 1)) * (W - padL - padR)
  const ys = (o) => H - padB - ((o - lo) / (hi - lo)) * (H - padT - padB)
  const up = pts[0].o > last  // oddset har gått ned (stärkts)
  return (
    <div className="mini">
      <div className="mc-title">
        <span className="sw" style={{ background: color }} />{sign} {last.toFixed(2)}
        <span className={up ? 'mc-down' : 'mc-up'}>{up ? '↓ stärkts' : pts[0].o < last ? '↑ försvagats' : ''}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`}>
        <text x="2" y={ys(hi) + 4} className="cax">{hi.toFixed(2)}</text>
        <text x="2" y={ys(lo) + 4} className="cax">{lo.toFixed(2)}</text>
        <line x1={padL} y1={padT} x2={padL} y2={H - padB} className="caxis" />
        <polyline fill="none" stroke={color} strokeWidth="2"
          points={pts.map((p, i) => `${xs(i)},${ys(p.o)}`).join(' ')} />
        {pts.map((p, i) => <circle key={i} cx={xs(i)} cy={ys(p.o)} r="2.5" fill={color} />)}
        <text x={padL} y={H - 6} className="cax">{fmtT(pts[0].t)}</text>
        <text x={W - padR} y={H - 6} className="cax" textAnchor="end">{fmtT(pts[pts.length - 1].t)}</text>
      </svg>
    </div>
  )
}

function MovementChart({ product, drawNumber, eventNumber }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let on = true
    fetch(`/api/history?product=${product}&draw=${drawNumber}&event=${eventNumber}`)
      .then((r) => r.json()).then((d) => { if (on) setData(d) })
    return () => { on = false }
  }, [product, drawNumber, eventNumber])

  if (!data) return <div className="loading">Hämtar historik…</div>
  const colors = { '1': '#4aa3df', X: '#aab3bf', '2': '#e0853b' }
  const bySign = { '1': [], X: [], '2': [] }
  ;(data.history || []).filter((r) => r.odds != null).sort((a, b) => a.fetched_at.localeCompare(b.fetched_at))
    .forEach((r) => bySign[r.sign]?.push({ t: r.fetched_at, o: r.odds }))

  return (
    <div>
      <div className="chart-src">Oddsrörelse · källa: {data.source === 'pinnacle' ? 'Pinnacle (sharp)' : 'Svenska Spel'}</div>
      <div className="charts3">
        {['1', 'X', '2'].map((s) => <MiniChart key={s} sign={s} pts={bySign[s]} color={colors[s]} />)}
      </div>
    </div>
  )
}

/* ---------- sharp (Pinnacle, gratis, auto) – kompakt status + manuell uppdatering ---------- */
function SharpPanel({ product, draw, onLoaded }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [show, setShow] = useState(false)
  const STATUS = {
    derived: { txt: 'härledd från spread/total (1X2 ej öppnad)', cls: 'st-wait' },
    no_moneyline: { txt: '1X2 ej öppnad än', cls: 'st-wait' },
    not_listed: { txt: 'ej listad hos Pinnacle ännu', cls: 'st-miss' },
  }
  const fetchSharp = async () => {
    if (!draw) return
    setLoading(true)
    try {
      const d = await (await fetch(`/api/external-odds?product=${product}&draw=${draw}&_t=${Date.now()}`, { cache: 'no-store' })).json()
      if (d && (d.matches || d.enabled === false)) {  // ignorera 404/detail-svar
        setData(d); if (d.cached > 0 && onLoaded) onLoaded()
      }
    } catch (e) { setData({ error: String(e) }) } finally { setLoading(false) }
  }
  useEffect(() => { fetchSharp() }, [product, draw])  // hämta direkt (gratis) vid byte

  const matched = data?.matches?.filter((m) => m.external) || []
  const uncovered = data?.matches?.filter((m) => !m.external) || []
  return (
    <div className="sharp">
      <div className="sharp-head">
        <strong>Sharp-odds (Pinnacle, gratis)</strong>
        <span className="cstatus">{data?.matches ? `${matched.length}/${data.matches.length} matcher` : (loading ? '…' : '')}</span>
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

const GAMES = [
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
]
// kort variantnamn i omgångsväljaren (Topptipset-gruppen består av flera produkter)
const VARIANT = {
  topptipset: 'Dagens', topptipsetstryk: 'Stryk', topptipsetextra: 'Extra',
}
// djuplänk till rätt omgång på Svenska Spel (du fyller i/lämnar in själv där)
const SVS_PID = { topptipset: 25, topptipsetstryk: 23, topptipsetextra: 24 }
function svsUrl(product, draw) {
  if (product === 'stryktipset' || product === 'europatipset') {
    return `https://spela.svenskaspel.se/${product}?draw=${draw}`
  }
  return `https://spela.svenskaspel.se/topptipset/?draw=${draw}&product=${SVS_PID[product] || 25}`
}

const SYSTEM_BASE = [
  { id: 'math', label: 'Matematiskt (alla kombinationer)', q: 'reduced=false' },
  { id: 'red', label: 'Reducerat (värde)', q: 'reduced=true' },
  { id: 'g', label: 'Egen reducering (garanti)', q: 'reduced=true&guarantee=', dynamic: true },
]
const SYSTEM_SVS = [
  { id: 'svs_r409', label: 'Svenska Spel R 4-0-9 (12 rätt, 9 rad)', q: `sv_rsystem=${encodeURIComponent('R 4-0-9')}` },
  { id: 'svs_r0716', label: 'Svenska Spel R 0-7-16 (12 rätt, 16 rad)', q: `sv_rsystem=${encodeURIComponent('R 0-7-16')}` },
  { id: 'svs_r3324', label: 'Svenska Spel R 3-3-24 (12 rätt, 24 rad)', q: `sv_rsystem=${encodeURIComponent('R 3-3-24')}` },
  { id: 'svs_r44144', label: 'Svenska Spel R 4-4-144 (12 rätt, 144 rad)', q: `sv_rsystem=${encodeURIComponent('R 4-4-144')}` },
]

function fmtClose(iso) {
  return iso ? iso.slice(5, 16).replace('T', ' ') : ''
}
function fmtFetched(iso) {
  if (!iso) return '–'
  try {
    return new Date(iso).toLocaleString('sv-SE', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return '–' }
}
function fmtStart(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('sv-SE', {
      weekday: 'short', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return '' }
}

const kr = (v) => (v == null ? '–' : Math.round(v).toLocaleString('sv-SE') + ' kr')
const pct = (v) => (v == null ? '–' : (v * 100 < 0.1 ? (v * 100).toFixed(3) : (v * 100).toFixed(v < 0.1 ? 2 : 1)) + ' %')

/* Räkna kupongens nyckeltal från analysens fair-sannolikheter.
   poly = ∏(pᵢ·x + (|Sᵢ|−pᵢ)) ger förväntat antal vinstrader per nivå.
   dp   = Poisson-binomial över pᵢ ger sannolikheten för bästa radens antal rätt. */
function poissonBinomial(probs) {
  let d = [1]
  for (const p of probs) {
    const nd = Array(d.length + 1).fill(0)
    for (let j = 0; j < d.length; j++) { nd[j] += d[j] * (1 - p); nd[j + 1] += d[j] * p }
    d = nd
  }
  return d
}

function couponStats(matches, picks, payouts, minDividend = 0, turnoverOverride = null, jackpot = 0) {
  const N = matches.length
  const rowPrice = payouts?.row_price || 1
  const ratio = payouts?.ratio || 0
  const turnover = turnoverOverride != null ? turnoverOverride : (payouts?.turnover || 0)
  const ps = [], counts = []
  let complete = true
  for (const m of matches) {
    const sel = picks[m.event_number] || []
    if (sel.length === 0) complete = false
    ps.push(sel.reduce((a, s) => a + (m.outcomes[s]?.fair_prob || 0), 0))
    counts.push(sel.length)
  }
  // Generating-function-poly för fulla systemet (fallback om vi inte enumererar)
  let gpoly = [1]
  for (let i = 0; i < N; i++) {
    const p = ps[i], c = counts[i]
    const np = Array(gpoly.length + 1).fill(0)
    for (let j = 0; j < gpoly.length; j++) { np[j] += gpoly[j] * (c - p); np[j + 1] += gpoly[j] * p }
    gpoly = np
  }
  const fullRows = complete ? counts.reduce((a, c) => a * c, 1) : 0
  const expectedCorrect = ps.reduce((a, b) => a + b, 0)
  const selectedCount = counts.filter((c) => c > 0).length
  // potter räknas från (ev. överstyrd) omsättning × andel; jackpot läggs på toppnivån
  const tiers = (payouts?.tiers || []).map((t) => ({
    correct: t.correct,
    pool: turnover * ratio * (t.share || 0) + (t.correct === N ? jackpot : 0),
  }))
  const poolMap = {}; tiers.forEach((t) => { poolMap[t.correct] = t.pool })
  const field = turnover / rowPrice

  // Enumerera kupongens rader. Per rad: Poisson-binomial över odds (P att raden
  // får k rätt) och över folkets streck (medvinnartäthet). kr/vinnare =
  // pott_k / (förv. medvinnare + dig själv). Utdelningsreducering: hoppa över
  // rader vars toppvinst-utdelning understiger minDividend.
  const poly = {}, evTiers = {}
  let kept = 0, evPayout = 0, modelOk = false
  if (complete && field > 0 && fullRows > 0 && fullRows <= 20000 && tiers.length) {
    const sel = matches.map((m) => (picks[m.event_number] || []).map((s) => ({
      fair: m.outcomes[s]?.fair_prob || 0,
      folk: m.outcomes[s]?.streck != null ? m.outcomes[s].streck / 100 : (m.outcomes[s]?.fair_prob || 0),
    })))
    const rec = (i, fairArr, folkArr) => {
      if (i === N) {
        const pf = poissonBinomial(fairArr)
        const pk = poissonBinomial(folkArr)
        const div = {}
        for (const t of tiers) {
          const c = t.correct
          div[c] = Math.min(t.pool, t.pool / (field * (pk[c] || 0) + 1))
        }
        if (minDividend > 0 && (div[N] || 0) < minDividend) return   // bort med raden
        kept++
        for (const t of tiers) {
          const c = t.correct
          poly[c] = (poly[c] || 0) + (pf[c] || 0)
          const contrib = (pf[c] || 0) * div[c]
          evPayout += contrib
          evTiers[c] = (evTiers[c] || 0) + contrib
        }
        return
      }
      for (const o of sel[i]) rec(i + 1, [...fairArr, o.fair], [...folkArr, o.folk])
    }
    rec(0, [], [])
    modelOk = true
  }

  const rows = modelOk ? kept : fullRows
  const cost = rows * rowPrice
  // Utdelning OM raden vinner nivån = EV-bidrag / förv. antal vinstrader på nivån.
  const dividend = {}
  for (const c in evTiers) dividend[c] = poly[c] ? evTiers[c] / poly[c] : null
  const polyOut = modelOk ? poly : gpoly.reduce((o, v, i) => { o[i] = v; return o }, {})
  const pAll = modelOk ? (poly[N] || 0) : (gpoly[N] || 0)
  return { N, complete, selectedCount, fullRows, kept, rows, cost, poly: polyOut, evTiers,
    dividend, topDividend: dividend[N] ?? null, modelOk, reduced: minDividend > 0,
    poolMap, turnover, expectedCorrect, evPayout, ev: evPayout - cost,
    roi: cost ? (evPayout - cost) / cost : null, pAll }
}

function CouponPanel({ matches, picks, payouts, product, draw, onFill, onClear }) {
  const [redOn, setRedOn] = useState(false)
  const [minDiv, setMinDiv] = useState(50)
  const [turnover, setTurnover] = useState(null)   // null = använd live-omsättning
  const [jackpot, setJackpot] = useState(0)
  const [copied, setCopied] = useState(false)
  const copyCoupon = () => {
    const txt = matches.map((m) => `${m.event_number}. ${m.description}: ${(picks[m.event_number] || []).join('')}`).join('\n')
    navigator.clipboard?.writeText(txt); setCopied(true); setTimeout(() => setCopied(false), 2000)
  }
  const effTurnover = turnover != null ? turnover : (payouts?.turnover || 0)
  const s = couponStats(matches, picks, payouts, redOn ? minDiv : 0, turnover, jackpot)
  const payTiers = (payouts?.tiers || []).filter((t) => t.correct != null).sort((a, b) => b.correct - a.correct)
  return (
    <div className="coupon">
      <div className="coupon-actions">
        <button className="primary" onClick={onFill}>Fyll från förslag</button>
        <button onClick={onClear}>Rensa</button>
        <span className="cstatus">{s.selectedCount}/{s.N} matcher valda{!s.complete ? ' – klicka tecken i tabellen ovan' : ''}</span>
      </div>
      {s.complete && (
        <>
          {payouts?.available && (
            <>
              <div className="reducer">
                <label>Omsättning (mkr)
                  <input type="number" min="0" step="0.5" value={(effTurnover / 1e6).toFixed(2)}
                    onChange={(e) => setTurnover(Number(e.target.value) * 1e6)} />
                </label>
                <label>Jackpot (mkr)
                  <input type="number" min="0" step="0.5" value={(jackpot / 1e6)}
                    onChange={(e) => setJackpot(Number(e.target.value) * 1e6)} />
                </label>
                {turnover != null && <button onClick={() => setTurnover(null)}>↺ live</button>}
              </div>
              <label className="reducer">
                <input type="checkbox" checked={redOn} onChange={(e) => setRedOn(e.target.checked)} />
                Utdelningsreducering: ta bort rader med utdelning under
                <input type="number" min="0" step="10" value={minDiv} disabled={!redOn}
                  onChange={(e) => setMinDiv(Number(e.target.value))} /> kr
                {redOn && s.modelOk && <span className="cstatus"> · behåller {s.kept} av {s.fullRows} rader</span>}
              </label>
            </>
          )}
          <div className="coupon-kpis">
            <div className="kpi"><span>{s.rows}</span>rader{s.reduced ? ` (av ${s.fullRows})` : ''}</div>
            <div className="kpi"><span>{kr(s.cost)}</span>insats</div>
            <div className="kpi"><span>{s.expectedCorrect.toFixed(2)}</span>förv. antal rätt</div>
            <div className="kpi"><span>{pct(s.pAll)}</span>chans alla rätt</div>
            <div className="kpi" title="Vad du får om hela raden är rätt: prispotten för toppnivån delad på förväntat antal medvinnare (uppskattat från folkets streck).">
              <span>{kr(s.topDividend)}</span>utdelning om alla rätt</div>
            <div className="kpi" title="EV netto = förväntad utdelning − insats. Förväntad utdelning = summan över alla vinstnivåer av (sannolikhet att raden träffar nivån × utdelning per vinnare på den nivån). Positivt = lönsamt i längden.">
              <span className={s.ev >= 0 ? 'pos' : 'neg'}>{s.ev >= 0 ? '+' : ''}{kr(s.ev)}</span>EV (netto)</div>
            <div className="kpi" title="ROI = EV netto ÷ insats, i procent. T.ex. +20% betyder att du i snitt får tillbaka 1,20 kr per satsad krona.">
              <span className={s.roi >= 0 ? 'pos' : 'neg'}>{s.roi == null ? '–' : (s.roi * 100).toFixed(0) + ' %'}</span>ROI</div>
          </div>
          {payouts?.available && (
            <table className="grid compact paytable">
              <thead><tr><th>Nivå</th><th>Prispott*</th><th>Förv. vinstrader</th><th>Utdelning om rätt</th><th>EV-bidrag</th></tr></thead>
              <tbody>
                {payTiers.map((t) => (
                  <tr key={t.correct}>
                    <td>{t.correct} rätt</td>
                    <td>{kr(s.poolMap?.[t.correct])}</td>
                    <td>{(s.poly[t.correct] || 0).toFixed(3)}</td>
                    <td>{kr(s.dividend?.[t.correct])}</td>
                    <td>{kr(s.evTiers[t.correct] || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="hint">*Prispott = omsättning ({kr(effTurnover)}{turnover != null ? ', justerad' : ', live'})
            × Svenska Spels vinstplan{jackpot ? ` + jackpot ${kr(jackpot)}` : ''}. Antal vinnare uppskattas
            från nuvarande streck. "Utdelning om rätt" = vad du får om raden vinner nivån; EV är sannolikhetsviktat.</p>
          <div className="svs-row">
            <a className="svs-link" href={svsUrl(product, draw)} target="_blank" rel="noreferrer">▶ Öppna omgången på Svenska Spel ↗</a>
            <button onClick={copyCoupon}>{copied ? '✓ Kopierad' : 'Kopiera kupong'}</button>
            <span className="hint">Fyll i/lämna in själv där — av säkerhetsskäl skickas inga spel automatiskt.</span>
          </div>
        </>
      )}
    </div>
  )
}

export default function App() {
  const [group, setGroup] = useState('topptipset')   // flik (kan samla flera produkter)
  const [product, setProduct] = useState('topptipset')  // vald omgångs faktiska produkt (slug)
  const [draws, setDraws] = useState([])
  const [draw, setDraw] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [sys, setSys] = useState(null)
  const [strategy, setStrategy] = useState('medel')
  const [budget, setBudget] = useState(100)
  const [sysType, setSysType] = useState('math')
  const [valueWeight, setValueWeight] = useState(50)  // EV-/värdeskala 0..100
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [picks, setPicks] = useState({})
  const [payouts, setPayouts] = useState(null)

  const toggleSign = (ev, sign) => setPicks((prev) => {
    const cur = prev[ev] || []
    const next = cur.includes(sign) ? cur.filter((s) => s !== sign) : [...cur, sign]
    const copy = { ...prev }
    if (next.length) copy[ev] = next; else delete copy[ev]
    return copy
  })
  const clearCoupon = () => setPicks({})
  const fillFromTips = () => {
    if (!analysis) return
    const p = {}
    if (sys?.picks) {                       // använd senaste föreslagna systemet om det finns
      sys.picks.forEach((pk) => { p[pk.event_number] = pk.signs })
    } else {
      for (const m of analysis.matches) {
        const order = ['1', 'X', '2'].sort((a, b) => (m.outcomes[b].fair_prob || 0) - (m.outcomes[a].fair_prob || 0))
        const k = m.speltyp === 'avvakta' ? 3 : (m.speltyp === 'halvspik' || m.speltyp === 'gardera') ? 2 : 1
        p[m.event_number] = order.slice(0, k)
      }
    }
    setPicks(p)
  }

  const nMatches = analysis?.matches?.length || 0
  const systemTypes = nMatches === 13 ? [...SYSTEM_BASE, ...SYSTEM_SVS] : SYSTEM_BASE

  const loadAnalysis = async (p = product, dn = draw) => {
    if (!dn) return
    setLoading(true); setErr(null); setSelected(null)
    try {
      const r = await fetch(`/api/analysis?product=${p}&draw=${dn}&_t=${Date.now()}`, { cache: 'no-store' })
      if (!r.ok) throw new Error(`Analys ${r.status}`)
      setAnalysis(await r.json())
    } catch (e) { setErr(String(e)) } finally { setLoading(false) }
  }

  // byt spel: hämta omgångar, välj första öppna, ladda analys
  const loadPayouts = (p = product, dn = draw) => {
    if (!dn) return
    setPayouts(null)
    fetch(`/api/payouts?product=${p}&draw=${dn}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then(setPayouts).catch(() => setPayouts(null))
  }

  const refresh = () => { loadAnalysis(); loadPayouts() }

  const switchGame = async (g) => {
    setGroup(g); setSys(null); setAnalysis(null); setErr(null); setSysType('math'); setPicks({}); setLoading(true)
    try {
      const d = await (await fetch(`/api/draws?product=${g}&_t=${Date.now()}`, { cache: 'no-store' })).json()
      const list = d.open?.length ? d.open : d.draws
      setDraws(list)
      const first = list[0]
      if (first) {
        setProduct(first.product); setDraw(first.draw_number)
        loadAnalysis(first.product, first.draw_number); loadPayouts(first.product, first.draw_number)
      } else { setLoading(false); setErr('Inga öppna omgångar just nu.') }
    } catch (e) { setErr(String(e)); setLoading(false) }
  }

  const changeDraw = (slug, dn) => {
    setProduct(slug); setDraw(dn); setSys(null); setPicks({})
    loadAnalysis(slug, dn); loadPayouts(slug, dn)
  }

  const loadSystem = async () => {
    setErr(null)
    try {
      let q = (systemTypes.find((t) => t.id === sysType) || SYSTEM_BASE[0]).q
      if (q.endsWith('guarantee=')) q += Math.max(1, nMatches - 1)  // garanti = n-1
      const vw = valueWeight / 100
      const r = await fetch(`/api/system?product=${product}&draw=${draw}&strategy=${encodeURIComponent(strategy)}&budget=${budget}&value_weight=${vw}&${q}&_t=${Date.now()}`, { cache: 'no-store' })
      if (!r.ok) throw new Error((await r.json()).detail || `System ${r.status}`)
      setSys(await r.json())
    } catch (e) { setErr(String(e)) }
  }

  useEffect(() => { switchGame('topptipset') }, [])  // eslint-disable-line

  return (
    <div className="app">
      <header>
        <h1>⚽ SvS kompisen</h1>
        <div className="games">
          {GAMES.map((g) => (
            <button key={g.id} className={group === g.id ? 'game active' : 'game'}
              onClick={() => switchGame(g.id)}>{g.label}</button>
          ))}
        </div>
        {draws.length > 0 && (
          <select className="drawsel" value={`${product}|${draw}`}
            onChange={(e) => { const [sl, dn] = e.target.value.split('|'); changeDraw(sl, Number(dn)) }}>
            {draws.map((d) => (
              <option key={`${d.product}|${d.draw_number}`} value={`${d.product}|${d.draw_number}`}>
                {VARIANT[d.product] ? `${VARIANT[d.product]} · ` : ''}stänger {fmtClose(d.reg_close_time)}
                {d.state !== 'Open' ? ` (${d.state})` : ''} · omg {d.draw_number}
              </option>
            ))}
          </select>
        )}
        <button onClick={refresh}>↻ Uppdatera</button>
      </header>

      {analysis && (
        <div className="topinfo">
          <span>Omsättning <b>{analysis.turnover ? kr(analysis.turnover) : '–'}</b></span>
          <span>odds, streck & omsättning hämtade <b>{fmtFetched(analysis.fetched_at)}</b></span>
          {payouts?.available && <span>prispott (alla rätt) <b>{kr(payouts.tiers?.[0]?.pool)}</b></span>}
        </div>
      )}

      <Collection />
      {err && <div className="error">{err}</div>}
      {loading && <div className="loading">Hämtar…</div>}

      <section>
        <div className="analys-head">
          <h2>Analys</h2>
          <span className="hovertip">💡 håll muspekaren över en siffra eller badge för förklaring</span>
        </div>
        <Legend />
        {analysis && (
          <AnalysisTable matches={analysis.matches} product={product} drawNumber={analysis.draw_number}
            selected={selected} onSelect={setSelected} picks={picks} onToggleSign={toggleSign} />
        )}
      </section>

      <section>
        <h2>Din kupong</h2>
        {analysis && (
          <CouponPanel matches={analysis.matches} picks={picks} payouts={payouts}
            product={product} draw={draw} onFill={fillFromTips} onClear={clearCoupon} />
        )}
      </section>

      <section>
        <h2>Sharp-odds</h2>
        <SharpPanel product={product} draw={draw} onLoaded={() => loadAnalysis()} />
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
            {systemTypes.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <button className="primary" onClick={loadSystem}>Föreslå rad</button>
        </div>
        <div className="evscale" title="Lågt = lågoddsare/favoriter (hög träffchans, lägre EV). Högt = värde/skräll (lägre chans, högre EV långsiktigt).">
          <span>Träffchans</span>
          <input type="range" min="0" max="100" step="5" value={valueWeight}
            onChange={(e) => setValueWeight(Number(e.target.value))} />
          <span>Värde/EV</span>
          <span className="evval">{valueWeight}%</span>
        </div>
        <SystemView sys={sys} />
      </section>

      <footer>Lokal data från Svenska Spel + Pinnacle · personligt verktyg</footer>
    </div>
  )
}
