import { Component, Fragment, useCallback, useEffect, useEffectEvent, useRef, useState } from 'react'
import './App.css'
import { summarizeSourceHealth } from './sourceHealth.js'
import { payoutMatchesSelection } from './poolSelection.js'

// Komponentbibliotek: appskalet bor i AppV3.jsx (laddas av main.jsx) och
// importerar alla tunga byggstenar, konstanter och helpers härifrån —
// se exportblocket i slutet av filen.

// Ren presentationskomponent — måste bo på modulnivå, annars skapas en ny
// komponenttyp vid varje render av föräldern.
const InfoDot = ({ text }) => <span className="idot" title={text}>i</span>

const STRATEGIES = ['säker', 'medel', 'tuff']
// strategin sätter en startpunkt på EV-/värdereglaget (samma axel), så de inte krockar
const STRATEGY_EV = { säker: 20, medel: 50, tuff: 80 }
// budgetsteg (tak för insatsen) – slider istället för sifferfält.
// 144 är en exakt Hamming-täckning (R 4-4-144) och ingår i PH3:s
// benchmarkmatris sedan 2026-08-05, så reglaget måste kunna nå den.
const BUDGET_STOPS = [16, 32, 48, 64, 96, 128, 144, 192, 256, 384, 512, 768, 1024, 1536, 2048]
const fmt = (o) => (o === null || o === undefined ? '–' : o.toFixed(2))

function timeAgo(iso) {
  if (!iso) return 'aldrig'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 90) return 'nyss'
  if (s < 3600) return `${Math.round(s / 60)} min sedan`
  if (s < 86400) return `${Math.round(s / 3600)} h sedan`
  return `${Math.round(s / 86400)} dygn sedan`
}

function useStoredBool(key, initial = false) {
  const [value, setValue] = useState(() => {
    try {
      const saved = localStorage.getItem(key)
      return saved == null ? initial : saved === '1'
    } catch { return initial }
  })
  const update = (next) => setValue((previous) => {
    const resolved = typeof next === 'function' ? next(previous) : next
    try { localStorage.setItem(key, resolved ? '1' : '0') } catch { /* ok */ }
    return resolved
  })
  return [value, update]
}

function LoadingState({ label = 'Hämtar data…' }) {
  return <div className="loading-state" role="status"><span className="spinner" aria-hidden="true" />{label}</div>
}

function EmptyState({ title, detail }) {
  return <div className="empty-state"><b>{title}</b>{detail && <span>{detail}</span>}</div>
}

function ErrorState({ message }) {
  return <div className="error state-error" role="alert"><b>Något gick fel</b><span>{message}</span></div>
}

/* ---------- insamling (launchd – körs även när appen är stängd) ---------- */
function Collection() {
  const [st, setSt] = useState(null)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(false)
  const refresh = async () => { try { setSt(await (await fetch('/api/collection/status')).json()) } catch { /* */ } }
  const start = async () => {
    try {
      const r = await (await fetch('/api/collection/start', { method: 'POST' })).json()
      setErr(r.error || (!r.active ? 'gick inte att ladda jobbet — se launchd-loggen' : null))
      setSt(r)
    } catch (e) { setErr(String(e)) }
  }
  const stop = async () => { setErr(null); await fetch('/api/collection/stop', { method: 'POST' }); refresh() }
  useEffect(() => {
    // Första körningen läggs i samma timerslinga som fortsättningen. Effekten
    // installerar då bara synkroniseringen; state ändras först när I/O:t är
    // klart och aldrig synkront under själva React-effekten.
    const first = setTimeout(refresh, 0)
    const id = setInterval(refresh, 10000)
    return () => { clearTimeout(first); clearInterval(id) }
  }, [])

  const active = st?.active
  return (
    <span className="colstat"
      title={`Bakgrundsinsamlingen (launchd var 30:e min, var 5:e nära spelstopp) loggar odds & streck — driver rörelser, steam, 🔥-notiser och CLV-facit.${st ? ` ${st.snapshot_count} mättillfällen totalt.` : ''}`}>
      <span className={`dot ${active ? 'on' : 'off'}`} />
      <span>Data {st?.last_snapshot ? `uppdaterad ${timeAgo(st.last_snapshot)}` : active ? 'samlas in' : 'inte uppdaterad'}</span>
      <button className="collection-more" onClick={() => setOpen(!open)}
        aria-expanded={open}>{open ? 'Dölj' : 'Detaljer'}</button>
      {open && (
        <span className="collection-detail">
          {active ? 'Automatisk insamling aktiv' : 'Automatisk insamling stoppad'}
          {st?.snapshot_count != null ? ` · ${st.snapshot_count} mätningar` : ''}
          {err && !active && <span className="neg"> · {err}</span>}
          <button className="linkbtn" onClick={active ? stop : start}>{active ? 'stoppa' : 'starta'}</button>
        </span>
      )}
    </span>
  )
}

/* ---------- folkfördelning (streck %) som 3-segmentsstapel ---------- */
function Legend() {
  const [open, setOpen] = useStoredBool('svs_ui_pool_legend')
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
          <div><b>Matchbild</b> beskriver matchen enligt marknaden — den är INTE ditt val och kan
            skilja sig från kupongen/förslaget:
            {' '}<span className="badge b-spik">Spik 1</span> stark favorit (kan singlas) ·
            {' '}<span className="badge b-half">Halvspik 1</span> halvstark favorit (singla djärvt eller gardera) ·
            {' '}<span className="badge b-half">Värdespik 1</span> favorit som folket undervärderar ·
            {' '}<span className="badge b-lean">Lutar 1</span> svag favorit ·
            {' '}<span className="badge b-open">Gardera</span> öppen match.</div>
          <div><b>spik-score</b> 0–100 = favoritens styrka · <b>öppen-score</b> 0–100 = hur jämn/öppen
            matchen är (hög = ingen klar favorit — systemen garderar de mest öppna matcherna först).</div>
          <div>Märken: <b>★</b> värdestreck (underspelat av folket) ·
            {' '}<b className="m-sharp">S</b> sharp ser värde folket missat ·
            {' '}<b className="m-edge">▲</b> Svenska Spels odds högre än Pinnacle (felprisat) ·
            {' '}<b className="m-move-down">⇊</b> oddset har stärkts i våra mätningar · ↓ fallande mot startodds.</div>
          <div>RLM (folket och sharp åt olika håll): <b className="m-rlm-go">◆</b> smart pengar —
            folket lämnar tecknet medan sharp köper (dubbelt köpläge) ·
            {' '}<b className="m-rlm-fade">⚠</b> folket strömmar in medan sharp säljer — undvik/fadea.</div>
          <div><b>Grön ram</b> på en odds-cell = tecknet ligger i din kupong.
            {' '}Grön <b>ton + ×N</b> (radläge) = N av förslagets rader använder tecknet — starkare ton, fler rader.</div>
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
            {w >= 13 ? `${v}%` : w >= 8 ? v : ''}
          </div>
        )
      })}
    </div>
  )
}

/* extra värdesignaler ur rekommendationen i klartext (badgens hover) –
   ledtexten (Spik/Lutar …) utelämnas eftersom badgen redan visar den */
function recExtra(rec) {
  return (rec || '').split('. ').slice(1).map((p) => {
    const m = p.match(/([1X2](?:\/[1X2])*)\s*$/)
    const sign = m ? m[1] : ''
    if (p.startsWith('sharp-värde')) return `Pinnacle ser värde på ${sign} som folket missat`
    if (p.startsWith('men värde på')) return `värde (underspelat av folket) på ${sign}`
    if (p.startsWith('värdetecken')) return `värdetecken (underspelat) på ${sign}`
    if (p.startsWith('SS billigt')) return `SS-odds för höga på ${sign} (felprisat)`
    return p
  }).join('. ')
}

/* ---------- förslagsbadge (ersätter de otydliga spik/öppen-staplarna) ---------- */
function Forslag({ m }) {
  const fav = m.favourite
  const map = {
    spik: ['b-spik', `Spik ${fav}`],
    värdespik: ['b-half', `Värdespik ${fav}`],
    halvspik: ['b-half', `Halvspik ${fav}`],
    gardera: ['b-open', 'Gardera'],
    lutar: ['b-lean', `Lutar ${fav}`],
    avvakta: ['b-lean', 'Avvakta'],
  }
  const [cls, txt] = map[m.speltyp] || ['b-lean', `Lutar ${fav}`]
  const tips = {
    spik: 'Stark favorit – kan singlas.',
    värdespik: 'Kort odds men lågt streck – undervärderad av folket, bra att singla.',
    halvspik: 'Halvfavorit – singla djärvt eller halvgardera.',
    gardera: 'Öppen match utan klar favorit – ta flera tecken.',
    lutar: 'Svag favorit – luta hit men gardera gärna.',
    avvakta: 'Odds saknas än – avvakta.',
  }
  const extra = recExtra(m.recommendation)
  const badgeTitle = `${tips[m.speltyp] || ''}${extra ? ' · ' + extra : ''}`
    + ` (favorit ${Math.round((m.favourite_prob || 0) * 100)}%, spik-styrka ${Math.round(m.spik_score)}/100)`
  const mv = m.mover
  return (
    <div className="forslag">
      <span className={`badge ${cls}`} title={badgeTitle}>{txt}</span>
      {mv && (
        <span className="moverflags">
          {mv.odds_sign && (
            <span className={`mover mv-odds ${mv.late ? 'mv-late' : ''}`}
              title={mv.label + (mv.late ? ' · sen rörelse nära avspark – stark signal' : '')}>
              <b>1X2</b> {mv.odds_sign}{mv.steam_pp != null
                ? ` +${mv.steam_pp}pp`
                : `↓${Math.round((mv.odds_drop_pct || 0) * 100)}%`}{mv.late ? ' 🔥' : ''}
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
    </div>
  )
}

/* ---------- rörelse-tooltip (hela serien per utfall, SvS + Pinnacle) ---------- */
function fmtTs(t) {
  const d = new Date(t); const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`
}
// behåll bara förändringspunkter (hoppa över upprepade identiska odds)
function changePoints(pts) {
  const out = []
  for (const p of pts || []) if (!out.length || out[out.length - 1].odds !== p.odds) out.push(p)
  return out
}
function TipSection({ label, pts }) {
  const c = changePoints(pts)
  if (!c.length) return null
  const first = c[0].odds, last = c[c.length - 1].odds
  const delta = +(last - first).toFixed(2)
  const dir = delta < 0 ? 'NED' : delta > 0 ? 'UPP' : '—'
  const dcls = delta < 0 ? 't-down' : delta > 0 ? 't-up' : ''
  const vals = (pts || []).map((p) => p.odds)
  const mn = Math.min(...vals), mx = Math.max(...vals)
  return (
    <div className="tip-sec">
      <div className="tip-h"><b>{label}</b>: {fmt(last)} · {fmt(first)}→{fmt(last)}{' '}
        <span className={dcls}>({delta > 0 ? '+' : ''}{delta.toFixed(2)}, {dir})</span></div>
      {c.map((p, i) => (
        <div key={i} className="tip-row"><span>{fmtTs(p.t)}</span><b>{fmt(p.odds)}</b></div>
      ))}
      <div className="tip-f">min {fmt(mn)} / max {fmt(mx)} · {c.length} mätpunkter</div>
    </div>
  )
}
function OddsTip({ sign, series, x, y }) {
  return (
    <div className="oddstip" style={{ left: x, top: y }}>
      <TipSection label={`SvS ${sign}`} pts={series.svs} />
      <TipSection label={`Pinnacle ${sign}`} pts={series.pinnacle} />
    </div>
  )
}

function OddsCell({ o, derived, picked, onToggle, valueOk, series, rowCount, rowTotal }) {
  const [tipPos, setTipPos] = useState(null)
  const hasSeries = !!series && (changePoints(series.svs).length > 0 || changePoints(series.pinnacle).length > 0)
  const cls = ['cell', 'pickcell']
  // radläge: visa hur stor del av de överlevande raderna som använder tecknet
  const inRowMode = rowTotal > 0
  const share = inRowMode ? (rowCount || 0) / rowTotal : 0
  // (inga bakgrundstoner för värde/edge — kvot-pillret + märkena ★/S/▲ bär den infon)
  if (picked) cls.push('picked')
  // Värde-kvot = fair-sannolikhet / streck. >1 = marknaden tror mer än folket.
  const ratio = (valueOk && o.fair_prob != null && o.streck) ? o.fair_prob / (o.streck / 100) : null
  const rcls = ratio == null ? '' : ratio >= 1.08 ? 'v-green' : ratio <= 0.92 ? 'v-red' : 'v-yellow'
  const ratioTitle = ratio == null ? '' : `Värde ${ratio.toFixed(2)}: oddsens sannolikhet ${Math.round((o.fair_prob || 0) * 100)}% mot folkets ${o.streck}% streck. ` +
    (ratio >= 1.08 ? `Marknaden tror ~${Math.round((ratio - 1) * 100)}% mer än folket — köpläge.`
      : ratio <= 0.92 ? `Folket överspelar (${Math.round((1 - ratio) * 100)}% mindre sannolik än streckad).`
        : 'Ungefär rätt streckad.')
  const showTip = (e) => {
    if (!hasSeries) return
    const r = e.currentTarget.getBoundingClientRect()
    setTipPos({ x: Math.min(r.left, window.innerWidth - 280), y: r.bottom + 4 })
  }
  return (
    <td className={cls.join(' ')} data-sign={o.sign} onClick={onToggle}
      onMouseEnter={showTip} onMouseLeave={() => setTipPos(null)}
      style={inRowMode ? { background: rowCount > 0 ? `rgba(61,220,132,${(0.07 + 0.38 * share).toFixed(3)})` : undefined } : undefined}
      title={inRowMode ? `${rowCount || 0} av ${rowTotal} överlevande rader använder ${o.sign}` + (hasSeries ? '' : ' · klicka för att bygga om manuellt')
        : hasSeries ? undefined : 'Klicka för att lägga till/ta bort i kupongen'}>
      {tipPos && <OddsTip sign={o.sign} series={series} x={tipPos.x} y={tipPos.y} />}
      {inRowMode && rowCount > 0 && <div className="rowshare">×{rowCount}</div>}
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
        {o.tags?.includes('rlm_go') && <span className="m-rlm-go" title={`Smart pengar (RLM): folket lämnar (${o.streck_move} pp) medan sharp köper (+${o.steam_pp} pp devigad) — dubbelt köpläge`}>◆</span>}
        {o.tags?.includes('rlm_fade') && <span className="m-rlm-fade" title={`Varning (RLM): folket strömmar in (+${o.streck_move} pp) medan sharp säljer (${o.steam_pp} pp devigad) — undvik/fadea`}>⚠</span>}
      </div>
    </td>
  )
}

function AnalysisTable({ matches, product, drawNumber, selected, onSelect, picks, onToggleSign, movement, rowShares }) {
  const isPicked = (ev, s) => (picks[ev] || []).includes(s)
  return (
    <table className="grid analysis">
      <thead>
        <tr><th>#</th><th>Match</th><th>1</th><th>X</th><th>2</th><th className="th-folk">Folket (1·X·2)</th>
          <th title="Matchbild = favoritens styrka enligt marknaden. Beskriver matchen, inte ditt val — kan skilja sig från kupongen.">Matchbild</th></tr>
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
                    series={movement?.events?.[m.event_number]?.[s]}
                    rowCount={rowShares?.counts?.[`${m.event_number}:${s}`]}
                    rowTotal={rowShares?.total}
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
  const [loading, setLoading] = useState(!!draw)
  const [show, setShow] = useState(false)
  const notifyLoaded = useEffectEvent(() => {
    if (onLoaded) onLoaded()
  })
  const STATUS = {
    derived: { txt: 'härledd från spread/total (1X2 ej öppnad)', cls: 'st-wait' },
    no_moneyline: { txt: '1X2 ej öppnad än', cls: 'st-wait' },
    not_listed: { txt: 'ej listad hos Pinnacle ännu', cls: 'st-miss' },
    'ej ompollad': { txt: 'ej ompollad detta varv (dubbeltrafikspärr) — cachat pris gäller',
                     cls: 'st-wait' },
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
  useEffect(() => {
    if (!draw) return undefined
    let current = true
    fetch(`/api/external-odds?product=${product}&draw=${draw}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        if (!current || !d || (!d.matches && d.enabled !== false)) return
        setData(d)
        if (d.cached > 0) notifyLoaded()
      })
      .catch((e) => { if (current) setData({ error: String(e) }) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [product, draw])

  const matched = data?.matches?.filter((m) => m.external) || []
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
/* manuell överstyrning av färgreduceringen: klicka tecken (ofärgad→blå→gul),
   sätt egna min/max-gränser och räkna om. */
function ColorLab({ sys, onRecalc }) {
  const init = {}
  sys.picks.forEach((p) => Object.entries(p.colors || {}).forEach(([s, c]) => { init[`${p.event_number}:${s}`] = c }))
  const [cols, setCols] = useState(init)
  const b = sys.color_bounds
  const [blo, setBlo] = useState(b.blo); const [bhi, setBhi] = useState(b.bhi)
  const [glo, setGlo] = useState(b.glo); const [ghi, setGhi] = useState(b.ghi)
  const cycle = (ev, s) => setCols((prev) => {
    const k = `${ev}:${s}`
    const next = prev[k] == null ? 'blå' : prev[k] === 'blå' ? 'gul' : null
    const c = { ...prev }
    if (next) c[k] = next; else delete c[k]
    return c
  })
  const apply = () => {
    const cstr = Object.entries(cols)
      .map(([k, v]) => { const [ev, s] = k.split(':'); return `${ev}:${s}:${v === 'blå' ? 'b' : 'g'}` })
      .join(',')
    onRecalc(`&colors=${encodeURIComponent(cstr)}&bounds=${blo}-${bhi},${glo}-${ghi}`)
  }
  const num = (v, set, max) => (
    <input type="number" min="0" max={max} value={v}
      onChange={(e) => set(Math.max(0, Number(e.target.value)))} />
  )
  return (
    <div className="colorlab">
      <div className="cl-title">🎨 Justera färgerna själv (klicka tecken: ofärgad → <span className="sg-bla">blå</span> → <span className="sg-gul">gul</span>):</div>
      <div className="cl-chips">
        {sys.picks.filter((p) => p.signs.length >= 2).map((p) => (
          <span key={p.event_number} className="cl-match">
            <em>{p.event_number}</em>
            {p.signs.map((s) => {
              const c = cols[`${p.event_number}:${s}`]
              return (
                <button key={s} className={`cl-sign ${c === 'blå' ? 'sg-bla' : c === 'gul' ? 'sg-gul' : ''}`}
                  onClick={() => cycle(p.event_number, s)}>{s}</button>
              )
            })}
          </span>
        ))}
      </div>
      <div className="cl-bounds">
        <span className="sg-bla">Blå rätt:</span> min {num(blo, setBlo, b.nb_max)} max {num(bhi, setBhi, b.nb_max)}
        <span className="sg-gul">Gula rätt:</span> min {num(glo, setGlo, b.ng_max)} max {num(ghi, setGhi, b.ng_max)}
        <button className="primary" onClick={apply}>Räkna om med mina färger</button>
        <button onClick={() => onRecalc('')}>↺ Auto</button>
      </div>
    </div>
  )
}

function SystemView({ sys, matches, payouts, onRecalc, onUse }) {
  const [mfCopied, setMfCopied] = useState(false)
  // Ärlig byggartext för 13-matchsspelen (PH5-radvalsablationen) — bara text,
  // ingen logikändring. Produkt ur payouts; 13 matcher = Stryk/Europa som fallback.
  const honest13 = (payouts?.product
    ? payouts.product === 'stryktipset' || payouts.product === 'europatipset'
    : matches?.length === 13) && (
    <p className="hint build-honesty">
      PH5-ablation (3 976 omgångar, 2026-07-26): radvalsmetoden ger ingen påvisad
      fördel mot folk-/favoritrad på 13-matchsspel vid budgetar upp till 512 rader
      — täckningen är för gles. På Topptipset-spelen är fördelen bevisad (+7–15 pp).
    </p>
  )
  if (!sys) return honest13 || null
  const roleClass = { spik: 'r-spik', halvgardering: 'r-half', helgardering: 'r-full' }
  const st = systemStats(sys, matches, payouts)
  const mc = sys.portfolio_mc?.available ? sys.portfolio_mc : null
  const payTiers = (payouts?.tiers || []).filter((t) => t.correct != null).sort((a, b) => b.correct - a.correct)
  // rad-system (EV-topp/färg/reducerat): tecknen i tabellen är ett URVAL av rader,
  // inte ett kombinationssystem — visa per tecken hur många rader som använder det
  const rowsList = (sys.rows && sys.rows.length) ? sys.rows : null
  const signCounts = rowsList ? sys.picks.map((p, i) => {
    const c = {}
    rowsList.forEach((r) => { c[r[i]] = (c[r[i]] || 0) + 1 })
    return c
  }) : null
  const fullCombos = sys.picks.reduce((a, p) => a * p.signs.length, 1)
  return (
    <div className="system">
      {honest13}
      <div className="system-head">
        <strong>{sys.system_type}</strong> · {sys.strategy} ·
        <span className="rows"> {sys.num_rows} rader = {sys.cost} kr</span>
        <button className="primary useb" onClick={onUse}>⬇ Lägg i kupongen</button>
        <span className="note"> {sys.note}</span>
      </div>
      {sys.rule && <div className="rule">{sys.rule}</div>}
      {sys.system_type === 'färgreducerat' && sys.color_bounds && onRecalc && (
        <ColorLab key={sys.rule} sys={sys} onRecalc={onRecalc} />
      )}
      {mc && (
        <div className="portfolio-card">
          <div className="portfolio-head">
            <div>
              <strong>WP6 · Simulerad portfölj</strong>
              <span>{mc.method === 'exhaustive'
                ? `Alla ${mc.iterations.toLocaleString('sv-SE')} möjliga utfall viktade`
                : `${mc.iterations.toLocaleString('sv-SE')} reproducerbara utfall`}</span>
            </div>
            <span className="portfolio-turnover">
              {mc.turnover_basis === 'projected' ? 'slutomsättning' : 'omsättning nu'} {kr(mc.turnover)}
            </span>
          </div>
          <div className="portfolio-kpis">
            <div className="portfolio-kpi"><span>{kr(mc.mean_return)}</span>förv. utdelning</div>
            <div className="portfolio-kpi"><span className={mc.net_ev >= 0 ? 'pos' : 'neg'}>
              {mc.net_ev >= 0 ? '+' : ''}{kr(mc.net_ev)}</span>EV · {(mc.roi * 100).toFixed(0)} % ROI</div>
            <div className="portfolio-kpi"><span>{pct(mc.probability_profit)}</span>chans att gå plus</div>
            <div className="portfolio-kpi"><span>{pct(mc.probability_zero)}</span>risk för 0 kr</div>
            <div className="portfolio-kpi"><span>{kr(mc.percentiles?.p50)}</span>medianutfall</div>
            <div className="portfolio-kpi"><span>{kr(mc.percentiles?.p90)}</span>90:e percentil</div>
          </div>
          <div className="portfolio-note">
            Snabbformeln ger {kr(mc.analytical_return)}; portföljen ger {kr(mc.mean_return)}
            {mc.difference_vs_analytical != null
              ? ` (${mc.difference_vs_analytical >= 0 ? '+' : ''}${(mc.difference_vs_analytical * 100).toFixed(1)} %)` : ''}.
            {' '}Egna rader delar samma lägre potter och minskar här utdelningen med
            {' '}{kr(mc.own_competition_drag)} ({(mc.own_competition_drag_pct * 100).toFixed(1)} %).
            {mc.method === 'monte_carlo' && mc.mc_error_90 > 0
              ? ` Simuleringsosäkerhet för medelutdelningen: cirka ±${kr(mc.mc_error_90)} (90 %).` : ''}
          </div>
          <div className="portfolio-note muted">
            Matchutfall dras från fair-sannolikheterna. Medvinnare beräknas som
            Poisson kring utfallets faktiska streckkombination; κ={mc.kappa.toFixed(2)} är
            fortsatt konservativt. Percentiler beskriver risk, inte en garanterad utdelning.
          </div>
        </div>
      )}
      {sys.portfolio_mc && !sys.portfolio_mc.available && (
        <div className="rule">Portföljsimulering ej tillgänglig: {sys.portfolio_mc.reason}</div>
      )}
      {st && !st.tooBig && (
        <>
          <div className="coupon-kpis">
            <div className="kpi"><span>{kr(st.cost)}</span>insats</div>
            <div className="kpi"><span>{pct(st.pAll)}</span>chans alla rätt</div>
            <div className="kpi" title="Sannolikhetsviktad förväntad utdelning (brutto, före insats) över systemets rader.">
              <span>{kr(st.evPayout)}</span>förv. utdelning</div>
            <div className="kpi" title="EV netto = förväntad utdelning − insats. Positivt = lönsamt i längden.">
              <span className={st.ev >= 0 ? 'pos' : 'neg'}>{st.ev >= 0 ? '+' : ''}{kr(st.ev)}</span>EV (netto)</div>
            <div className="kpi" title="ROI = EV netto ÷ insats.">
              <span className={st.roi >= 0 ? 'pos' : 'neg'}>{st.roi == null ? '–' : (st.roi * 100).toFixed(0) + ' %'}</span>ROI</div>
          </div>
          {/* Var tidigare en andra beräkning "vid förväntad slutomsättning", men
              systemStats läser projected_turnover FÖRST och ignorerade därför den
              överskrivna omsättningen — raden kunde aldrig visa annat än KPI:erna
              ovanför. Byggaren värderar alltid mot prognosen (glädjesiffror annars,
              särskilt vid jackpot); raden säger nu det, och förklarar varför
              kupongen till höger kan visa andra tal. */}
          {payouts?.projected_turnover > payouts?.turnover && (
            <div className="rule" title={`Potterna växer mot spelstopp men det gör medvinnarna också.${payouts.projection_basis ? `\nPrognosgrund: ${payouts.projection_basis.mode === 'weekday' ? `median av ${payouts.projection_basis.n} senaste omgångarna med samma spelstoppsveckodag (${['mån', 'tis', 'ons', 'tors', 'fre', 'lör', 'sön'][payouts.projection_basis.weekday] ?? '?'})` : `median av senaste ${payouts.projection_basis.n} omgångarna oavsett veckodag (backtestet visar att den träffar bättre för produkten, eller för få jämförbara)`}.` : ''}`}>
              Talen ovan är räknade mot <b>förväntad slutomsättning {kr(payouts.projected_turnover)}</b>
              {' '}— den ärliga horisonten tidigt i veckan. Kupongen till höger står som
              standard på dagens omsättning ({kr(payouts.turnover)}) och visar därför
              mindre potter; tryck <b>→ prognos</b> där för att jämföra samma sak.
            </div>
          )}
          {payouts?.available && (
            <>
              {mc && <p className="hint">Detaljtabellen nedan är den snabba radvisa approximationen.
                Portföljkortet ovan är huvudvärderingen för det genererade systemet.</p>}
              <PayoutTable s={st} tiers={payTiers} payouts={payouts}
                jackpot={sys.jackpot ?? payouts.jackpot ?? 0} />
            </>
          )}
        </>
      )}
      {st?.tooBig && <div className="rule">Systemet är för stort ({st.rows} rader) för att räkna ut utdelningsspann här.</div>}
      {rowsList && fullCombos > sys.num_rows && (
        <div className="rule">
          Urval, inte kombinationssystem: {sys.num_rows} utvalda rader av {fullCombos.toLocaleString('sv-SE')} möjliga
          — som fullt system hade tecknen nedan kostat {kr(fullCombos * (sys.row_price || 1))}.
          Siffran vid varje tecken visar hur många av raderna som använder det.
        </div>
      )}
      <table className="grid compact">
        <thead><tr><th>#</th><th>Match</th><th>Roll</th><th>Tecken</th><th>Motivering</th></tr></thead>
        <tbody>
          {sys.picks.map((p, pi) => (
            <tr key={p.event_number} className={roleClass[p.role]}>
              <td>{p.event_number}</td><td className="match">{p.description}</td>
              <td>{rowsList ? (p.signs.length === 1 ? 'spik' : `${p.signs.length} tecken`) : p.role}</td>
              <td className="signs">
                {p.signs.map((s, i) => (
                  <Fragment key={s}>
                    {i > 0 ? '  ' : ''}
                    <span className={p.colors?.[s] === 'blå' ? 'sg-bla' : p.colors?.[s] === 'gul' ? 'sg-gul' : ''}
                      title={p.colors?.[s] ? `${p.colors[s]} färg i färgregeln` : undefined}>{s}</span>
                    {signCounts && p.signs.length > 1 && signCounts[pi]?.[s] != null
                      && <em className="signcnt" title={`${s} spelas i ${signCounts[pi][s]} av ${sys.num_rows} rader`}>×{signCounts[pi][s]}</em>}
                  </Fragment>
                ))}
              </td>
              <td className="rec">{p.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="manualfill">
        <b>Fyll i så här på Svenska Spel:</b>
        <span className="mf-rows">{sys.picks.map((p) => (
          <span key={p.event_number} className="mf-m">
            <em>{p.event_number}</em> {p.signs.join('')}</span>
        ))}</span>
        <button onClick={() => {
          navigator.clipboard?.writeText(sys.picks.map((p) => `${p.event_number}: ${p.signs.join('')}`).join('\n'))
          setMfCopied(true); setTimeout(() => setMfCopied(false), 2000)
        }}>{mfCopied ? '✓ Kopierad' : 'Kopiera'}</button>
        {rowsList && fullCombos > sys.num_rows && (
          <span className="hint"> · OBS: markerar du alla dessa tecken spelar du hela systemet
            ({fullCombos} rader). För den reducerade ({sys.num_rows} rader) – använd Egna rader-filen i kupongen.</span>
        )}
      </div>
      {sys.system_type?.includes('Svenska Spel-system') && (
        <p className="hint">Tips: namngivna R-system kan också spelas direkt på Svenska Spels
          systemkupong (markera hel-/halvgarderingarna och välj R-systemet) – ibland billigare.</p>
      )}
    </div>
  )
}

const GAMES = [
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
  { id: 'bomben', label: 'Bomben' },
  { id: 'oddset', label: 'Oddset' },
]

// Oddset-delen (Etapp 1 i docs/plan.md): matchlista i tidsordning med Svenska Spel-odds
// (Kambi) + sharp (Pinnacle) för Allsvenskan, Eliteserien och träningsmatcher.
// Rörelse-konvention (från vm): röd ↓ = oddset NER (ökad vinstchans), grön ↑ = UPP.
const ODDSET_HIDDEN_KEY = 'svs_oddset_hidden'

function OddsetLegend() {
  const [open, setOpen] = useStoredBool('svs_ui_oddset_legend')
  return (
    <div className="legendbox">
      <button className="legend-toggle" onClick={() => setOpen(!open)}>
        ℹ Vad betyder siffrorna — och vad är värde? {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="legend">
          <div><b>Raderna i varje oddscell</b> — <b>stort odds</b> = Svenska Spels primärrad ·
            <b> P</b> = Pinnacle, världens skarpaste bok = vår referens för
            "sant" pris (<b>P~</b> = härlett ur handikapp när 1X2 inte öppnats) ·
            <b> E</b> = Expekt ·
            <b> N</b> = Ninja/Altenar (1X2, Ö/U och hörnor när de finns) ·
            <b> M</b> = vår egen modell (amber, se nedan). Slå på <b>+ Fler odds</b>
            för att visa de spelbara sidoböckerna.</div>
          <div><b>Värde</b> = när en spelbar bok betalar MER än det sharpa priset.
            Vi räknar bort Pinnacles marginal (power-devig) och får en "fair" sannolikhet;
            edge = fair sannolikhet × bokens odds − 1.
            {' '}<span className="epill">+5%</span> = grön pill = <b>sharp-ankrat värde ≥2 %</b> —
            den starkaste signalen härinne, loggas i facitet. Samlas även i 💰-listan.
            {' '}<b>Men edge väger olika:</b> korten sorteras och nivåsätts på
            <b> kvalitet = edge/(odds−1)</b> (Kelly-andelen) — samma edge är mycket
            skörare på odds 15 än på 1.5 (ett halvt procentenhets fel i fair blåser
            upp högoddsar-edges). Högoddsare kräver därför mycket större edge för
            samma nivå, och notiser triggar på kvalitet, inte rå edge.</div>
          <div><b>kvar +5%</b> på en bokrad betyder mer än att priset bara är gammalt:
            samma bokpris har återbekräftats efter Pinnacles senaste prisändring.
            Överstrukna eller för gamla priser visas som historisk information men
            räknas aldrig som värde, facit eller notis.</div>
          <div><b>AH / Ö/U / Hörnor</b> visas som <i>linje · odds/odds</i> (t.ex. −0.5 · 1.79/1.89 =
            hemmalaget −0,5 mål). Pilar = prisrörelse på NUVARANDE linje;
            {' '}<span className="lshift">⇄↑</span> = själva LINJEN har flyttats (ofta starkare signal
            än priset — hovra för hela serien med linjer). Värde räknas ENDAST när boken och
            Pinnacle har samma linje. Hörnor prissätts av Pinnacle först nära avspark.
            Med modellen på visas <b>M-rad</b> även här: fair vid SvS-linjen (push/kvartslinjer
            hanterade) — AH bär modellens egen styrkebedömning, ÖU ligger nära sharpen när
            totalen är ankrad. Amber-pillsen forward-loggas per marknad i facitet.</div>
          <div><b>Pilar</b> = oddsrörelse sedan första notering: <span className="mv down">↓5%</span> =
            oddset har SJUNKIT (marknaden tror mer på utfallet — hann du före är det bra tecken) ·
            <span className="mv up"> ↑5%</span> = stigit. Hovra för hela serien med tidsstämplar.
            {' '}<b>🔥</b> = steam: Pinnacles devigade sannolikhet har flyttat ≥3,5 procentenheter
            på 6/24 h — typiskt lineup-nyheter. Kolla då direkt om någon spelbar bok står kvar
            på gamla oddset (det är träningsmatch-caset).</div>
          <div><b>M-raden (modellen)</b> — xG-viktad Poisson-styrkefit per liga, med
            DC-korrektion (ρ) i prediktionen: lagstyrkor ur resultat sedan 2024,
            xG-viktade (Sofascore, ~1000 matcher), totalnivå ankrad mot sharp Ö/U.
            Backtest v2 mot två års Pinnacle-stängningar: xG lyfte modellen i båda ligorna;
            Allsvenskan +10 % ROI vid låga trösklar men inom bruset (n=326), Eliteserien −17 %.
            Temperatur T valdes på samma historiska backtestmaterial; den oberoende
            forward-valideringen sker därför i prognosledgern.
            Därför <b>amber</b>: <span className="apill">+8%</span> = "modellen avviker — kolla
            varför", INTE "spela". Prognosledgern loggar alla modellprediktioner och
            kontrollutfall vid tre fasta horisonter. Candidate kräver ≥50 stängda
            flaggor, ≥30 matcher, ≥28 dagar och positiv undre KI-gräns; grönt kräver
            dessutom 15 nya out-of-time-matcher. Störst nytta idag:
            prisuppfattning för matcher där Pinnacle inte öppnat än.</div>
          <div><b>🧭 Prognosledgern</b> är forskningsdomaren: alla prediktioner, även
            oflaggade kontroller, jämförs med Pinnacles stängningslinje per version och
            grupp. <b>📒 Signal-loggen</b> visar i stället vad som faktiskt flaggades.
            Båda faciten finns samlade i <b>Labb</b>. Lita på ledgerfacitet, inte på känsla.</div>
          <div><b>🔬 Forskningsliga</b> (Premier League, Serie A, La Liga, Bundesliga) —
            visas med odds, prisålder och rörelser medan V2.2-experimentet samlar sitt
            forwardunderlag. Inga värdesignaler, Kelly-förslag, notiser eller
            facit-loggning här ännu: synlig liga är inte samma sak som spelbar signal.</div>
        </div>
      )}
    </div>
  )
}

// ---------- Delad värdenivå-logik (💰-korten + Rek-kolumnen) ----------
// Rek-cellen är ren VISNING av värdemotorns output — samma urval och samma
// nivåtrösklar som 💰-korten. Båda ytorna (och v3-dashboardens värdekort)
// MÅSTE läsa dessa helpers, aldrig egna kopior, så att de inte kan glida isär.
// Urval: bästa selektionen per match = högst kvalitet q = edge/(odds−1),
// bakom spelgrinden edge ≥ 2 % och q ≥ 0,75 % (högoddsar-edges är för sköra).
function oddsetBestValue(m) {
  let best = null
  for (const [mk, per] of Object.entries(m.value || {})) {
    for (const [sg, v] of Object.entries(per)) {
      if (v.edge < 0.02 || (v.q ?? 0) < 0.0075) continue
      if (!best || (v.q ?? 0) > (best.v.q ?? 0)) best = { mk, sg, v }
    }
  }
  return best
}
// Nivå: OMTVISTAD när andra sharp-ankaret (Smarkets) värderar samma bokodds
// negativt; annars STARK/EDGE/SVAG på kvalitet q — inte på rå edge.
function oddsetValueTier(v) {
  const q = v.q ?? 0
  const disputed = v.anchor2?.fair != null && v.anchor2.edge <= 0
  if (disputed) return { cls: 't1', label: 'OMTVISTAD EDGE', short: 'OMTVISTAD', disputed }
  if (q >= 0.04) return { cls: 't3', label: 'STARK EDGE', short: 'STARK', disputed }
  if (q >= 0.02) return { cls: 't2', label: 'EDGE', short: 'EDGE', disputed }
  return { cls: 't1', label: 'SVAG EDGE', short: 'SVAG', disputed }
}


/* ---------- Lagstyrka (powerrank + xPts) — AMBER, aldrig beslutsunderlag ----
   Styrkorna har alltid funnits som en intern biprodukt av modellens fit; det
   som saknades var att kunna SE dem. Saman 2026-08-07: syndikat rankar lag
   och justerar mot stats under säsongen, så överpresterande lag dippar.
   Mekanismen fanns redan (xG väger 0,65 mot måls 0,35) — men det som inte
   syns går inte att ifrågasätta.

   Uppmätt förutsäger modellen INTE marknadens rörelse mot stängning
   (r = −0,120, 90 % KI [−0,252, +0,034]), därför är panelen märkt amber och
   får inte påverka edge, urval eller notiser. */
function PowerRankPanel({ leagues }) {
  const [league, setLeague] = useState('allsvenskan')
  // '' = hela historiken. Säsongen nollställs vid ligabyte: etiketterna är
  // ligans egna (kalenderår vs 2025/26) och en kvarhängande säsong från
  // förra ligan skulle tyst filtrera bort allt.
  const [season, setSeason] = useState('')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let current = true
    fetch(`/api/oddset/powerrank?league=${league}`
      + `${season ? `&season=${encodeURIComponent(season)}` : ''}`
      + `&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { if (current) { setData(d); setErr(null) } })
      .catch((e) => { if (current) setErr(String(e)) })
    return () => { current = false }
  }, [league, season])

  const cols = [
    { key: 'rank', label: '#', defaultDir: 'asc',
      title: 'Styrkerank — INTE tabellplacering. Listan är sorterad på anfall ÷ försvar ur modellens fit. Att den avviker från tabellen är hela poängen: tabellen säger vad som hänt, styrkan vad modellen tror om laget.' },
    { key: 'name', label: 'Lag', defaultDir: 'asc' },
    { key: 'played_matches', label: 'Spelade',
      title: 'Alla registrerade ligamatcher i valt säsongsurval' },
    { key: 'matches', label: 'Med xG',
      title: 'Matcher som faktiskt ingår i poäng/xPoäng-jämförelsen' },
    { key: 'ratio', label: 'Styrka', title: 'Anfall ÷ försvar ur modellens egen fit. 1,00 = ligasnitt.' },
    { key: 'att', label: 'Anfall', title: 'Målfaktor i anfall mot ett genomsnittligt försvar. 1,20 = gör 20 % fler mål än snittlaget.' },
    { key: 'def', label: 'Försvar', defaultDir: 'asc',
      title: 'Målfaktor i försvar. LÄGRE är bättre: 0,80 = släpper in 20 % färre mål än snittlaget.' },
    { key: 'points', label: 'Poäng' },
    { key: 'xpts', label: 'xPoäng', title: 'Förväntade poäng ur matchernas xG' },
    { key: 'overperformance', label: 'Över/under',
      title: 'Poäng minus xPoäng. Positivt = laget har tagit fler poäng än chanserna motiverar och är kandidat för nedgång.' },
  ]
  const num = (v, d = 2) => (v == null ? '–' : Number(v).toFixed(d))
  return (
    <div className="tab-panel powerrank">
      <div className="valhead">
        <b>🏋 Lagstyrka och xPoäng</b>
        <span className="rchip amber">amber · påverkar inga tips</span>
        <select value={league} onChange={(e) => {
          setLeague(e.target.value); setSeason(''); setData(null); setErr(null)
        }}>
          {(leagues || []).map((l) => (
            <option key={l.key} value={l.key}>{l.name}</option>
          ))}
        </select>
        {data?.seasons?.length > 0 && (
          <select value={season} onChange={(e) => {
            setSeason(e.target.value); setData(null); setErr(null)
          }}
            title="Fitten bakom styrkan tidsviktar alltid hela historiken. Säsongsvalet gäller de räknade kolumnerna: poäng, xPoäng och över/under.">
            <option value="">Alla säsonger</option>
            {data.seasons.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        )}
      </div>
      {err && <ErrorState message={err} />}
      {!data && !err && <LoadingState label="Räknar styrkor…" />}
      {data && !data.teams?.length && (
        <EmptyState title="Ingen styrkeskattning för den här ligan"
          detail="Tabellen räknar bara på matcher med observerad xG, och kräver tillräckligt många per lag. xG bakfylls aldrig — den samlas framåt." />
      )}
      {data?.teams?.length > 0 && (
        <>
          <p className="hint">
            Styrka = anfall ÷ försvar ur samma fit som modellens prognoser
            använder. <b>Över/under</b> är poäng minus förväntade poäng: ett
            positivt tal betyder att laget tagit mer än chanserna motiverar,
            alltså en kandidat för nedgång — och tvärtom.
            {data.pool?.length > 1 && (
              <> Fitten poolar {data.pool.join(' + ')} så upp- och
                nedflyttare länkar populationerna.</>
            )}
          </p>
          <p className="hint">
            Poäng och xPoäng räknas på <b>samma matcher</b>: de som har
            observerad xG{data.season ? ` under ${data.season}` : ''}. Lag utan
            xG-matcher visas inte — det finns inget att jämföra deras poäng
            mot. Kolumnen <b>m</b> är alltså antal xG-täckta matcher, inte
            antal spelade.
          </p>
          <details className="powerrank-method">
            <summary>Så räknas styrka, anfall och försvar</summary>
            <p>
              Modellen skattar två tal per lag genom att upprepat justera dem
              tills de förväntade målen matchar de observerade
              (<code>fit_league</code>
              {data.params?.iters ? `, ${data.params.iters} iterationer` : ''}):
            </p>
            <pre>{`λ_hemma = base_liga × hemmafördel_liga × anfall_hemma × försvar_borta
λ_borta = base_liga × anfall_borta × försvar_hemma`}</pre>
            <ul>
              <li><b>Anfall</b> och <b>försvar</b> är målfaktorer normaliserade
                så ligasnittet är 1,00. Anfall 1,20 = gör 20 % fler mål än
                snittlaget; försvar 0,80 = släpper in 20 % färre. <b>Lägre
                försvar är alltså bättre.</b></li>
              <li><b>Styrka</b> = anfall ÷ försvar. Ett enda tal att sortera
                på, men det döljer profilen: 1,50 kan vara ett målrikt lag
                med läckande försvar eller ett defensivt lag som gör få mål.</li>
              <li><b>Mål räknas xG-viktat</b>: effektiva mål ={' '}
                {(data.params?.xg_weight ?? 0.65).toString().replace('.', ',')} × xG
                + {(1 - (data.params?.xg_weight ?? 0.65)).toFixed(2).replace('.', ',')} ×
                faktiska mål. Det är därför en tursam vinst inte lyfter
                styrkan lika mycket som en dominant match.</li>
              <li><b>Äldre matcher väger mindre</b> (exponentiell tidsvikt,
                halveringstid {data.params?.half_life_d ?? 166} dagar), och
                fitten går över hela poolen och alla säsonger — säsongsvalet
                ovan gäller bara de räknade kolumnerna, aldrig styrkan.</li>
            </ul>
            <p>
              <b>#-kolumnen är styrkerank, inte tabellplacering.</b> Att de två
              skiljer sig är hela poängen: tabellen säger vad som har hänt,
              styrkan vad modellen tror om laget. Över/under-kolumnen är
              avståndet mellan dem.
            </p>
          </details>
          <SortableTable id="oddset-powerrank" columns={cols} rows={data.teams}
            defaultSort={{ key: 'rank', dir: 'asc' }}
            className="grid compact"
            renderRow={(t) => (
              <tr key={t.team}>
                <td>{t.rank}</td>
                <td className="match-name"><b>{t.name || t.team}</b></td>
                <td>{t.played_matches ?? t.matches}</td>
                <td>{t.matches}</td>
                <td><b>{num(t.ratio)}</b></td>
                <td>{num(t.att)}</td>
                <td>{num(t.def)}</td>
                <td>{t.points}</td>
                <td>{t.xpts}</td>
                <td className={t.overperformance > 0 ? 'neg' : 'pos'}>
                  {`${t.overperformance > 0 ? '+' : ''}${t.overperformance}`}
                </td>
              </tr>
            )}
            renderCard={(t) => (
              <div key={t.team} className="live-radar-card">
                <div className="live-radar-teams">
                  <b>{t.rank}. {t.name || t.team}</b>
                  <span className="hint">{t.matches} m</span>
                </div>
                <div className="live-radar-stats">
                  <span>styrka <b>{num(t.ratio)}</b></span>
                  <span>poäng <b>{t.points}</b> · xP <b>{t.xpts}</b></span>
                  <span className={t.overperformance > 0 ? 'neg' : 'pos'}>
                    {`${t.overperformance > 0 ? '+' : ''}${t.overperformance} mot xP`}
                  </span>
                </div>
              </div>
            )} />
          <p className="hint">{data.disclaimer}</p>
        </>
      )}
    </div>
  )
}

function OddsetView({ focus = null } = {}) {
  const [data, setData] = useState(null)
  const [notices, setNotices] = useState(null)
  const [liveRadar, setLiveRadar] = useState(null)
  const [showNotices, setShowNotices] = useState(false)
  const [showSources, setShowSources] = useStoredBool('svs_ui_oddset_sources')
  const [showAllModel, setShowAllModel] = useStoredBool('svs_ui_oddset_model_list')
  const [showBooks, setShowBooks] = useStoredBool('svs_ui_oddset_books')
  const [showAllMatches, setShowAllMatches] = useState(false)
  const [expanded, setExpanded] = useState(null)
  // 📒 Rek-historiken för EN öppnad matchdetalj: { id, rows } | { id, error }
  const [matchFlags, setMatchFlags] = useState(null)
  const [movementDetail, setMovementDetail] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const loadSeq = useRef(0)
  const [hidden, setHidden] = useState(() => {
    try { return JSON.parse(localStorage.getItem(ODDSET_HIDDEN_KEY)) || [] } catch { return [] }
  })
  const [showModel, setShowModel] = useState(() => {
    try { return localStorage.getItem('svs_oddset_model') === '1' } catch { return false }
  })
  const [onlySignals, setOnlySignals] = useState(() => {
    try { return localStorage.getItem('svs_oddset_only') === '1' } catch { return false }
  })
  const [hideStarted, setHideStarted] = useState(() => {
    try { return localStorage.getItem('svs_oddset_hide_started') === '1' } catch { return false }
  })
  const [bank, setBank] = useState(() => {
    try { return Number(localStorage.getItem('svs_oddset_bank')) || 1000 } catch { return 1000 }
  })
  // Sub-tabbar (UI-passet 2026-07-29): sidan delas i Matcher/Live/Värdespel/
  // Rörelser — räknarraden på tabbraden är alltid synlig så tabbarna aldrig
  // döljer brådskande info. Valet persisteras som övriga Oddset-inställningar.
  // AMBER-kontext, hämtas en gång per sidöppning. Fel här får aldrig fälla
  // oddsvyn — utan rank visas matchraden precis som förut.
  const [powerRank, setPowerRank] = useState(null)
  useEffect(() => {
    fetch(`/api/oddset/powerrank?league=all&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then(setPowerRank).catch(() => setPowerRank(null))
  }, [])
  const [oddsetTab, setOddsetTab] = useState(() => {
    const focusTab = { varde: 'varde', radar: 'rorelser' }[focus]
    if (focusTab) return focusTab
    try {
      const saved = localStorage.getItem('svs_oddset_tab')
      return ['matcher', 'live', 'varde', 'rorelser', 'styrka'].includes(saved) ? saved : 'matcher'
    } catch { return 'matcher' }
  })
  const pickTab = (t) => {
    setOddsetTab(t)
    try { localStorage.setItem('svs_oddset_tab', t) } catch { /* ok */ }
  }
  const toggleModel = () => {
    setShowModel(!showModel)
    try { localStorage.setItem('svs_oddset_model', showModel ? '0' : '1') } catch { /* ok */ }
  }
  const toggleOnly = () => {
    setOnlySignals(!onlySignals)
    try { localStorage.setItem('svs_oddset_only', onlySignals ? '0' : '1') } catch { /* ok */ }
  }
  const saveBank = (v) => {
    setBank(v)
    try { localStorage.setItem('svs_oddset_bank', String(v)) } catch { /* ok */ }
  }
  const toggleStarted = () => {
    setHideStarted(!hideStarted)
    try {
      localStorage.setItem('svs_oddset_hide_started', hideStarted ? '0' : '1')
    } catch { /* ok */ }
  }

  const load = () => {
    const seq = ++loadSeq.current
    const stamp = Date.now()
    let quickLoaded = false
    // Första svaret hoppar den dyra amber-modellen/frånvaron och skickar
    // inga historiska punkter. Det räcker för hela beslutsytan: aktuella odds,
    // värde, steam och linjeskift. Detaljerna berikar samma rader efter första
    // paint utan att hålla sidan i laddningsläge.
    const quick = fetch(`/api/oddset/matches?light=true&compact=true&movement=false&limit=40&_t=${stamp}`,
      { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        quickLoaded = true
        if (loadSeq.current === seq) { setData(d); setErr(null) }
      })
      .catch((e) => {
        if (loadSeq.current === seq) setErr(String(e))
      })
    const detailed = quick.then(() => new Promise((resolve) => setTimeout(resolve, 1200)))
      .then(() => {
        if (loadSeq.current !== seq) return null
        return fetch(`/api/oddset/matches?compact=true&_t=${stamp}`,
          { cache: 'no-store' })
      })
      .then((r) => r ? r.json() : null)
      .then((d) => {
        if (d && loadSeq.current === seq) { setData(d); setErr(null) }
      })
      .catch((e) => {
        if (loadSeq.current === seq && !quickLoaded) setErr(String(e))
      })
    fetch(`/api/oddset/notices?_t=${stamp}`, { cache: 'no-store' })
      .then((r) => r.json()).then((n) => {
        if (loadSeq.current === seq) setNotices(n?.notices || [])
      }).catch(() => {})
    fetch(`/api/oddset/live-radar?_t=${stamp}`, { cache: 'no-store' })
      .then((r) => r.json()).then((live) => {
        if (loadSeq.current === seq) setLiveRadar(live)
      }).catch(() => {})
    return detailed
  }
  useEffect(() => {
    load()
    return () => { loadSeq.current += 1 }
  }, [])
  useEffect(() => {
    const poll = () => fetch(`/api/oddset/live-radar?_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then(setLiveRadar).catch(() => {})
    const id = setInterval(poll, 60_000)
    return () => clearInterval(id)
  }, [])

  // Djuplänkar från v3-dashboarden: landa på rätt sektion och öppna den
  // (v2 skickar ingen focus-prop — effekten är då en no-op). Synkron
  // direktscroll i effekten: DOM:en är committad här, och timers/smooth
  // throttlas i bakgrundade vyer — instant är pålitligt överallt.
  // Sektionen expanderar nedåt efter state-sättningen, så toppositionen håller.
  useEffect(() => {
    if (!focus || !data) return
    // djuplänkar hoppar till rätt SUB-TABB först (UI-passet 2026-07-29)
    const id = { varde: 'oddset-varde', radar: 'oddset-radar' }[focus]
    const jump = () => document.getElementById(id)
      ?.scrollIntoView({ behavior: 'auto', block: 'start' })
    jump()                              // synkront: landar direkt även throttlat
    const t = setTimeout(jump, 400)     // korrigeringspass efter sen reflow
    return () => clearTimeout(t)
  }, [focus, data])

  // Rek-historiken hämtas BARA när en matchdetalj öppnas — aldrig för alla
  // rader. Endpointen läser value_log; ett GET skapar inga nya flaggor.
  // Ingen synkron "loading"-setState behövs: renderingen visar "hämtar…"
  // så länge matchFlags.id inte matchar den öppnade matchen.
  useEffect(() => {
    if (!expanded) return undefined
    let alive = true
    fetch(`/api/oddset/match-flags?match_id=${encodeURIComponent(expanded)}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { if (alive) setMatchFlags({ id: expanded, rows: d.flags || [] }) })
      .catch(() => { if (alive) setMatchFlags({ id: expanded, error: true }) })
    fetch(`/api/oddset/movement?match_id=${encodeURIComponent(expanded)}&_t=${Date.now()}`,
      { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { if (alive) setMovementDetail({ id: expanded, movement: d.movement || {} }) })
      .catch(() => { if (alive) setMovementDetail({ id: expanded, movement: {} }) })
    return () => { alive = false }
  }, [expanded])

  const refresh = async () => {
    setBusy(true)
    try {
      const r = await fetch(`/api/oddset/refresh?_t=${Date.now()}`, { method: 'POST', cache: 'no-store' })
      if (!r.ok) throw new Error(`Hämtning ${r.status}`)
      await load()
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const toggleLeague = (k) => {
    const h = hidden.includes(k) ? hidden.filter((x) => x !== k) : [...hidden, k]
    setHidden(h)
    try { localStorage.setItem(ODDSET_HIDDEN_KEY, JSON.stringify(h)) } catch { /* ok */ }
  }

  const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' }) : ''
  const fmtDay = (iso) => iso ? new Date(iso).toLocaleDateString('sv-SE', { weekday: 'long', day: 'numeric', month: 'numeric' }) : '?'
  const serie = (mv) => (mv?.pts || []).map((p) => `${new Date(p.t).toLocaleString('sv-SE', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })}  ${p.o.toFixed(2)}`).join('\n')

  const arrow = (mv) => {
    if (!mv || mv.n < 2 || Math.abs(mv.last - mv.first) < 0.01) return null
    const down = mv.last < mv.first
    const pct = Math.round(Math.abs(mv.last / mv.first - 1) * 100)
    return <span className={down ? 'mv down' : 'mv up'}
      title={`${down ? 'Oddset har sjunkit' : 'Oddset har stigit'} ${mv.first.toFixed(2)} → ${mv.last.toFixed(2)}\n${serie(mv)}`}>
      {down ? '↓' : '↑'}{pct >= 1 ? `${pct}%` : ''}</span>
  }

  const fmtAh = (l) => (l > 0 ? `+${l}` : `${l}`)

  // Matchdetaljen (grafer/serier/flaggor) öppnas från matchraden OCH från
  // 💰-värdekorten — samma handler och samma expanded-state. Kortet ligger
  // ovanför tabellen, så det scrollar dessutom fram raden vars detalj öppnas.
  const toggleDetail = (id, scroll = false) => {
    const next = expanded === id ? null : id
    setExpanded(next)
    if (scroll && next != null) {
      pickTab('matcher')
      setTimeout(() => document.getElementById(`oddsrow-${id}`)
        ?.scrollIntoView({ behavior: 'auto', block: 'center' }), 60)
    }
  }

  // parmarknader: serie med linje per punkt, pil på NUVARANDE linje, ⇄ vid linjeflytt
  const serieL = (mv) => (mv?.pts || []).map((p) =>
    `${new Date(p.t).toLocaleString('sv-SE', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })}  ${p.l != null ? `[${p.l}] ` : ''}${p.o.toFixed(2)}`).join('\n')
  const arrowAtLine = (mv, line) => {
    const pts = (mv?.pts || []).filter((p) => p.l === line)
    if (pts.length < 2) return null
    const first = pts[0].o, last = pts[pts.length - 1].o
    if (Math.abs(last - first) < 0.01) return null
    const down = last < first
    const pct = Math.round(Math.abs(last / first - 1) * 100)
    return <span className={down ? 'mv down' : 'mv up'}
      title={`${down ? 'Sjunkit' : 'Stigit'} på linje ${line}: ${first.toFixed(2)} → ${last.toFixed(2)}\n${serieL(mv)}`}>
      {down ? '↓' : '↑'}{pct >= 1 ? `${pct}%` : ''}</span>
  }
  const lineShift = (mv) => {
    const ls = (mv?.pts || []).map((p) => p.l).filter((l) => l != null)
    return ls.length > 1 && ls[0] !== ls[ls.length - 1]
      ? { from: ls[0], to: ls[ls.length - 1] } : null
  }
  const shiftBadge = (mv, who) => {
    const sh = lineShift(mv)
    return sh && <span className="lshift"
      title={`${who}-linjen har FLYTTATS ${sh.from} → ${sh.to} — linjeflytt är ofta en starkare signal än prisjusteringen (hela serien i pilens tooltip)`}>⇄{sh.to > sh.from ? '↑' : '↓'}</span>
  }

  // mänsklig spel-etikett: "2 · Halmstads BK", "Degerfors +0.5 AH", "Under 3.5"
  const selLabel = (m, mk, sg, line) => {
    if (mk === '1x2') return sg === '1' ? `1 · ${m.home}` : sg === '2' ? `2 · ${m.away}` : 'X · Kryss'
    if (mk === 'ah') return `${sg === 'H' ? m.home : m.away} ${fmtAh(sg === 'H' ? line : -line)} AH`
    if (mk === 'ou') return `${sg === 'O' ? 'Över' : 'Under'} ${line} mål`
    return `${sg === 'O' ? 'Över' : 'Under'} ${line} hörnor`
  }
  const kelly = (v) => {
    const f = Math.max(0, (v.fair * v.odds - 1) / (v.odds - 1)) / 4
    return Math.round(bank * f)
  }
  const quoteClass = (base, market) => `${base}${market && !market.fresh ? ' quote-stale' : ''}`
  const priceStamp = (market) => {
    if (!market) return null
    const age = market.age_minutes
    const label = !market.available ? 'pausad'
      : age == null ? 'okänd'
        : age < 1.5 ? 'nu'
          : age < 60 ? `${Math.round(age)}m`
            : `${Math.round(age / 60)}h`
    const title = !market.available
      ? `Priset saknades i källans senaste lyckade svar och räknas inte som spelbart. Senast sett ${timeAgo(market.last_seen_at)}.`
      : market.fresh
        ? `Priset bekräftades ${timeAgo(market.last_seen_at)}.`
        : `Priset bekräftades senast ${timeAgo(market.last_seen_at)} och är för gammalt för värdesignaler/facit.`
    return <span className={`priceage ${market.fresh ? '' : 'stale'}`} title={title}>· {label}</span>
  }
  const DetailChart = ({ label, series }) => {
    const all = series.flatMap((s) => s.pts || [])
    if (all.length < 2) return null
    const ts = all.map((p) => new Date(p.t).getTime())
    const os = all.map((p) => p.o)
    const t0 = Math.min(...ts), t1 = Math.max(...ts)
    const o0 = Math.min(...os), o1 = Math.max(...os)
    const W = 250, H = 64, PAD = 5
    const X = (t) => t1 === t0 ? W / 2 : PAD + (t - t0) / (t1 - t0) * (W - 2 * PAD)
    const Y = (o) => o1 === o0 ? H / 2 : H - PAD - (o - o0) / (o1 - o0) * (H - 2 * PAD)
    return (
      <div className="dchart">
        <div className="hint">{label} <span className="drange">{o0.toFixed(2)}–{o1.toFixed(2)}</span></div>
        <svg className="detail-chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Oddsrörelse för ${label}`}>
          {series.map((s, i) => (s.pts?.length > 1
            ? <polyline key={i} fill="none" stroke={s.color} strokeWidth="1.5"
              points={s.pts.map((p) => `${X(new Date(p.t).getTime()).toFixed(1)},${Y(p.o).toFixed(1)}`).join(' ')} />
            : null))}
        </svg>
      </div>
    )
  }

  // mini-graf över sharp-seriens väg (röd = oddset ner = sannolikheten upp)

  // grön edge-pill: devigad Pinnacle säger att bok-oddset är för högt.
  // Kräver även kvalitet (edge/(odds−1)) — högoddsar-edges under kvalitetsgolvet
  // visas inte som pills (för sköra), men loggas ändå i facitet.
  const edgePill = (v, prefix = '') => {
    if (!v || v.edge < 0.02 || (v.q ?? 0) < 0.0075) return null
    const disputed = v.anchor2?.fair != null && v.anchor2.edge <= 0
    return (
      <span className={disputed ? 'epill disputed' : 'epill'}
        title={`Devigad Pinnacle: ${(v.fair * 100).toFixed(1)}% (fair odds ${(1 / v.fair).toFixed(2)})\nBoken betalar ${v.odds.toFixed(2)} → ${(v.edge * 100).toFixed(1)}% övervärde\nKvalitet (Kelly-andel): ${((v.q ?? 0) * 100).toFixed(1)}% — samma edge är skörare ju högre odds${v.derived ? '\n(P~ = härlett ur handikapp — ta med en nypa salt)' : ''}${disputed ? `\n⚓ Smarkets motsäger signalen: ${(v.anchor2.edge * 100).toFixed(1)}% mot samma bokodds. Tvåankarmätningen är ännu shadow och ändrar inte urvalet.` : ''}`}>
        {disputed ? '⚓ ' : ''}{prefix && `${prefix} `}+{Math.round(v.edge * 100)}%{v.derived ? '°' : ''}
      </span>
    )
  }

  const absPos = { G: 'MV', D: 'B', M: 'MF', F: 'A' }
  const absLine = (p) => `${p.name}${p.position ? ` · ${absPos[p.position] || p.position}` : ''} (${p.reason}${p.apps != null ? `, ${p.apps} matcher${p.rating ? `, ${p.rating}` : ''}` : ''})${p.apps != null && p.apps < 5 ? ' — marginell' : ''}`
  const absBadge = (m) => {
    const ab = m.absences
    if (!ab) return null
    const all = [...(ab.home || []), ...(ab.away || [])]
    // räkna bara spelare med etablerad roll (≥5 säsongsmatcher, eller okänd status)
    const heavy = all.filter((p) => p.apps == null || p.apps >= 5).length
    if (!all.length && !ab.confirmed) return null
    const lines = []
    for (const [side, team] of [['home', m.home], ['away', m.away]]) {
      for (const p of ab[side] || []) lines.push(`${team}: ${absLine(p)}`)
    }
    return <span className="absb"
      title={`${ab.confirmed ? 'Elvorna är BEKRÄFTADE — kolla radarn för sen sharp-rörelse\n' : ''}${lines.join('\n') || 'Inga rapporterade frånvaron'}${all.length > heavy ? `\n(${all.length - heavy} marginell(a) räknas inte i siffran)` : ''}`}>
      {ab.confirmed ? '✓XI' : ''}{heavy ? `🚑${heavy}` : ''}</span>
  }

  const steamBadge = (m) => {
    const st = m.steam
    if (!st) return null
    const parts = Object.entries(st).flatMap(([sg, sh]) =>
      [['6h', sh.h6], ['24h', sh.h24]].filter(([, pp]) => pp != null && Math.abs(pp) >= 3.5)
        .map(([w, pp]) => `${sg}: ${pp > 0 ? '+' : ''}${pp} pp/${w}`))
    if (!parts.length) return null
    const strong = Object.values(st).some((sh) =>
      Math.abs(sh.h6 || 0) >= 6 || Math.abs(sh.h24 || 0) >= 6)
    return <span className={strong ? 'steam strong' : 'steam'}
      title={`Sharp-steam (devigad Pinnacle-sannolikhet):\n${parts.join('\n')}\nPositivt = tecknet kortas — kolla om SvS hängt med`}>🔥</span>
  }

  const pct = (value) => value == null ? '–' : (value * 100).toFixed(1)
  const pp = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${value.toFixed(1)}`
  const ModelCompare = ({ cmp, sign, label = '' }) => {
    if (!cmp?.model?.[sign]) return null
    const title = [
      `Sannolikheter på samma marknad${cmp.line != null ? ` och lina ${cmp.line}` : ''}, marginalrensade för P/SvS.`,
      `Modell ${pct(cmp.model?.[sign])} %`,
      `Pinnacle ${pct(cmp.sharp?.[sign])} %${cmp.sharp_source === 'pinnacle_alt' ? ' (exakt alt-lina)' : ''}`,
      `SvS ${pct(cmp.svs?.[sign])} %`,
      cmp.sharp_note, cmp.svs_note,
    ].filter(Boolean).join('\n')
    return (
      <span className="modelcompare" title={title}>
        <span>{label ? `${label} ` : ''}M {pct(cmp.model?.[sign])}</span>
        <span>P {pct(cmp.sharp?.[sign])}</span>
        <span>SvS {pct(cmp.svs?.[sign])} %</span>
        <small>ΔP {pp(cmp.model_vs_sharp_pp?.[sign])} · ΔSvS {pp(cmp.model_vs_svs_pp?.[sign])} pp</small>
      </span>
    )
  }

  const cell1x2 = (m, sign) => {
    const svs = m.odds?.svenskaspel?.['1x2']
    const pin = m.odds?.pinnacle?.['1x2']
    const mv = m.movement?.svenskaspel?.['1x2']?.[sign]
    const mvP = m.movement?.pinnacle?.['1x2']?.[sign]
    const v = m.value?.['1x2']?.[sign]
    const md = m.model
    const cmp = md?.comparison?.['1x2']
    const mEdge = md?.edges?.[sign]
    return (
      <td className="oc" data-market={sign} key={sign}>
        <div className={quoteClass('o', svs)} title={mv?.pts?.length > 1 ? serie(mv) : undefined}>
          {svs?.[sign] ? svs[sign].toFixed(2) : '–'}{arrow(mv)}
          {(v?.book ?? 'svenskaspel') === 'svenskaspel' && edgePill(v)}
          {priceStamp(svs)}
        </div>
        {pin?.[sign] && (
          <div className={quoteClass('p', pin)} title={mvP?.pts?.length > 1 ? `Pinnacle:\n${serie(mvP)}` : 'Pinnacle (sharp)'}>
            P{pin.derived ? '~' : ''} {pin[sign].toFixed(2)}{arrow(mvP)}{priceStamp(pin)}
          </div>
        )}
        {showBooks && [['expekt', 'E', 'Expekt'], ['ninjacasino', 'N', 'Ninja/Altenar']].map(([bk, tag, label]) => {
          const bo = m.odds?.[bk]?.['1x2']
          const mvB = m.movement?.[bk]?.['1x2']?.[sign]
          // Expekt delar Kambi-feed med SvS och identiska priser är brus.
          // Altenar är en oberoende prismotor och ska alltid vara synlig.
          if (bk === 'expekt' && bo?.[sign] && bo[sign] === svs?.[sign]) return null
          return bo?.[sign] ? (
            <div className={quoteClass(`p bookquote ${bk === 'ninjacasino' ? 'ninjaquote' : ''}`, bo)}
              key={bk} title={mvB?.pts?.length > 1 ? `${label}:\n${serie(mvB)}` : label}>
              {tag} {bo[sign].toFixed(2)}{arrow(mvB)}
              {v?.book === bk && edgePill(v, v.held_after_sharp ? 'kvar' : '')}{priceStamp(bo)}
            </div>
          ) : null
        })}
        {showModel && cmp?.model?.[sign] && (
          <div className="m"
            title={`Egen modell (xG-viktad Poisson-styrkefit; DC-korrektion i prediktionen): ${(md.p[sign] * 100).toFixed(1)}%\nμ ${md.mu[0]}–${md.mu[1]} · T=${md.cal_t || 1}${md.anchored ? ' · totalnivå ankrad mot sharp Ö/U' : ' · OANKRAD (ingen sharp-linje ännu)'}${md.prior ? '\n⚠ Elo-prior: minst ett lag har tunn historik — styrka skattad ur ClubElo' : ''}\nT valdes på samma historiska backtestmaterial; ledgern är oberoende forward-facit.\nAmber-tier: experimentell`}>
            <ModelCompare cmp={cmp} sign={sign} />
            {mEdge >= 0.05 && <span className="apill"
              title={`Modellen tror ${(md.p[sign] * 100).toFixed(1)}% — SvS betalar ${(m.odds?.svenskaspel?.['1x2']?.[sign] || 0).toFixed(2)} = ${(mEdge * 100).toFixed(1)}% modell-edge.\nAmber = okalibrerad signal, spela inte blint på den.`}>
              +{Math.round(mEdge * 100)}%</span>}
          </div>
        )}
      </td>
    )
  }

  const cellPair = (m, market, k1, k2, fmtL) => {
    const svs = m.odds?.svenskaspel?.[market]
    const pin = m.odds?.pinnacle?.[market]
    const v1 = m.value?.[market]?.[k1], v2 = m.value?.[market]?.[k2]
    const mvS1 = m.movement?.svenskaspel?.[market]?.[k1]
    const mvS2 = m.movement?.svenskaspel?.[market]?.[k2]
    const mvP1 = m.movement?.pinnacle?.[market]?.[k1]
    const mvP2 = m.movement?.pinnacle?.[market]?.[k2]
    const mc = market === 'cor' && showModel ? m.model?.corners : null
    const mp = showModel ? m.model?.[market] : null
    const cmp = m.model?.comparison?.[market]
    const mpBest = mp && Object.entries(mp.edges || {})
      .filter(([, e]) => e >= 0.05).sort((a, b) => b[1] - a[1])[0]
    return (
      <td className="oc pair" data-market={MARKET_LABEL[market]}>
        <div className={quoteClass('o', svs)}>
          {svs?.[k1] && svs?.[k2] ? <>{fmtL(svs.line)} · {svs[k1].toFixed(2)}{arrowAtLine(mvS1, svs.line)} / {svs[k2].toFixed(2)}{arrowAtLine(mvS2, svs.line)}{shiftBadge(mvS1, 'SvS')}{priceStamp(svs)}</> : '–'}
          {edgePill(v1?.book === 'svenskaspel' ? v1 : null)
            || edgePill(v2?.book === 'svenskaspel' ? v2 : null)}
        </div>
        {pin?.[k1] && pin?.[k2] && <div className={quoteClass('p', pin)}>P {fmtL(pin.line)} · {pin[k1].toFixed(2)}{arrowAtLine(mvP1, pin.line)} / {pin[k2].toFixed(2)}{arrowAtLine(mvP2, pin.line)}{shiftBadge(mvP1, 'Pinnacle')}{priceStamp(pin)}</div>}
        {showBooks && [['expekt', 'E', 'Expekt'], ['ninjacasino', 'N', 'Ninja/Altenar']].map(([bk, tag, label]) => {
          const bo = m.odds?.[bk]?.[market]
          if (!bo?.[k1] || !bo?.[k2]) return null
          const mvB1 = m.movement?.[bk]?.[market]?.[k1]
          const mvB2 = m.movement?.[bk]?.[market]?.[k2]
          const sameAsSvs = bo.line === svs?.line
            && bo[k1] === svs?.[k1] && bo[k2] === svs?.[k2]
          if (bk === 'expekt' && sameAsSvs) return null
          const bv = v1?.book === bk ? v1 : v2?.book === bk ? v2 : null
          return (
            <div className={quoteClass(`p bookquote ${bk === 'ninjacasino' ? 'ninjaquote' : ''}`, bo)}
              key={bk} title={`${label} · ${MARKET_LABEL[market]}${bv?.held_after_sharp ? '\nPriset är färskt och återbekräftat efter Pinnacles senaste prisändring.' : ''}`}>
              {tag} {fmtL(bo.line)} · {bo[k1].toFixed(2)}{arrowAtLine(mvB1, bo.line)}
              {' '}/ {bo[k2].toFixed(2)}{arrowAtLine(mvB2, bo.line)}
              {shiftBadge(mvB1, label)}
              {edgePill(bv, bv?.held_after_sharp ? 'kvar' : '')}{priceStamp(bo)}
            </div>
          )
        })}
        {mp && (
          <div className="m"
            title={`${market === 'cor' ? 'Hörnmodellens Poisson-baslinje på Pinnacles lina' : 'Modellens fair på SvS-lina'} ${fmtL(mp.line)} (push/kvartslinjer hanterade).${market === 'ou' && m.model?.anchored ? '\nÖU: totalen är ankrad mot sharp — fairen ligger nära Pinnacle per konstruktion; edgen mäter mest SvS marginal.' : ''}${market === 'ah' ? '\nAH bär modellens EGEN styrkebedömning (supremacy) — här kan modellen avvika på riktigt.' : ''}${market === 'cor' ? '\nHörnkalibreringen samlar forwarddata med samma modell-mot-close-grind; ingen historik bakfylls.' : ''}\nAmber: experimentell — forward-loggas i 📒-facitet, spela inte blint.`}>
            <ModelCompare cmp={cmp} sign={k1} label={k1} />
            {mpBest && <span className="apill">{mpBest[0]} +{Math.round(mpBest[1] * 100)}%</span>}
          </div>
        )}
        {mc && (
          <div className="m"
            title={'Förväntade hörnor ur egen liga-data (Sofascore): liga-snitt + favoritskap via modell-μ.\nENDAST förväntan — hörn-VÄRDE kräver sharp linje (vm-lärdomen: modell-hörnedges blev +120% okalibrerat).'}>
            M {mc.tot} · {mc.h}/{mc.a}
          </div>
        )}
      </td>
    )
  }

  const MARKET_LABEL = { '1x2': '1X2', ah: 'AH', ou: 'Ö/U', cor: 'Hörnor' }
  const BOOK_NAME = {
    svenskaspel: 'SvS', expekt: 'Expekt',
    betinia: 'Betinia', ninjacasino: 'Ninja/Altenar', // Betinia kvar för historiken
  }
  // value_log prefixar modell-flaggornas marknad med m (m1x2/mah/mou/mcor)
  const FLAG_MARKET = { m1x2: '1x2', mah: 'ah', mou: 'ou', mcor: 'cor' }

  // Rek-kolumnen: ren VISNING av värdemotorns bästa selektion per match via
  // de delade helprarna oddsetBestValue/oddsetValueTier (exakt 💰-kortens
  // urval och nivåer — ingen egen urvalslogik, ingen loggning).
  // Träningsmatcher och forskningsligor är utanför rek-scopet: cellen lämnas
  // helt tom (inte ens "avstå").
  const rekCell = (m) => {
    if (m.league === 'friendlies' || m.research) return <td className="rek" />
    const best = oddsetBestValue(m)
    if (!best) {
      return (
        <td className="rek">
          <span className="rekpill none"
            title={'Ingen selektion i matchen når spelgrinden just nu (sharp-ankrad edge ≥ 2 % och kvalitet ≥ 0,75 %) — rekommendationen är att avstå matchen.'}>
            avstå
          </span>
        </td>
      )
    }
    const { mk, sg, v } = best
    const tier = oddsetValueTier(v)
    return (
      <td className="rek">
        <span className={`rekpill ${tier.cls}${tier.disputed ? ' disputed' : ''}`}
          title={[
            `${tier.label} — matchens bästa värdeselektion (samma motor och nivåer som 💰-korten; ren visning, loggar inget).`,
            `Devigad Pinnacle: ${(v.fair * 100).toFixed(1)} % (fair ${(1 / v.fair).toFixed(2)}) — ${BOOK_NAME[v.book] || v.book} betalar ${v.odds.toFixed(2)} = +${(v.edge * 100).toFixed(1)} % övervärde.`,
            `Kvalitet (Kelly-andel): ${((v.q ?? 0) * 100).toFixed(1)} % — nivån sätts på kvalitet, inte rå edge.`,
            v.derived ? '° = sharp-priset är härlett ur handikapp — ta med en nypa salt.' : null,
            tier.disputed ? `⚓ Smarkets (andra sharp-ankaret) motsäger signalen: ${(v.anchor2.edge * 100).toFixed(1)} % mot samma bokodds — edgen är omtvistad. Tvåankarmätningen är shadow och ändrar inte urvalet.` : null,
          ].filter(Boolean).join('\n')}>
          {tier.disputed ? '⚓ ' : ''}{tier.short} +{(v.edge * 100).toFixed(1)}%{v.derived ? '°' : ''}
        </span>
        <span className="reksel">{selLabel(m, mk, sg, v.line)}{v.book !== 'svenskaspel' ? ` · ${BOOK_NAME[v.book] || v.book}` : ''}</span>
      </td>
    )
  }

  if (err) return <section><h2>Oddset</h2><ErrorState message={err} /></section>
  if (!data) return <section><h2>Oddset</h2><LoadingState label="Hämtar matcher och odds…" /></section>

  const leagueName = Object.fromEntries(data.leagues.map((l) => [l.key, l.name]))
  // Etiketter för de källor vi KAN visa. Vilka som faktiskt räknas avgörs av
  // backendens `active_sources` — listan här är bara namn och ordning.
  // Utan den kopplingen syntetiserade UI:t en "saknas"-rad (ok:false) för
  // varje källa backend slutat skicka, så en urkopplad källa gick från
  // "gammal" till FEL i stället för att försvinna (Sofascore 2026-08-06).
  const activeSources = data.active_sources
  const healthDefs = [
    ['pinnacle', 'markets', 'P'], ['svenskaspel', '1x2', 'SvS'],
    ['svenskaspel', 'deep', 'SvS djup'], ['expekt', '1x2', 'E'],
    ['ninjacasino', '1x2', 'Ninja'], ['ninjacasino', 'deep', 'Ninja djup'],
    ['smarkets', '1x2', 'Smarkets'],
    ['flashscore', 'live', 'Live Flashscore'],
    ['fotmob', 'live', 'Live FotMob'],
    ['sofascore', 'live', 'Live Sofascore'],
  ].filter(([source]) => !activeSources || activeSources.includes(source))
  // Live-radarn pollas varje minut medan den stora Oddset-payloaden bara
  // laddas vid sidöppning. Använd därför live-endpointens färska hälsorader
  // för backendens aktiva livekällor, med den stora payloaden som reserv.
  const currentHealth = [
    ...(data.source_health || []).filter((r) => r.scope !== 'live'),
    ...((liveRadar?.source_health?.length
      ? liveRadar.source_health
      : (data.source_health || []).filter((r) => r.scope === 'live'))),
  ]
  const sourceHealth = healthDefs.flatMap(([source, scope, label]) => {
    const rows = currentHealth.filter((r) => r.source === source && r.scope === scope)
    if (!rows.length) return scope === 'live'
      ? [{ source, scope, label, latest: null, ok: false, status: 'missing',
          details: 'Ingen lyckad eller misslyckad kontroll registrerad ännu.' }]
      : []
    const summary = summarizeSourceHealth(rows)
    const details = summary.issues.length
      ? summary.issues.map((r) => `${leagueName?.[r.league] || r.league}: ${r.error || 'källfel'}`).join('\n')
      : `${summary.eventCount} events · kontrollerad ${timeAgo(summary.latest)}`
    // Passiv källa = samlas men matar inget beslut. Ett fel där kräver ingen
    // åtgärd, så den får aldrig visa samma varning som en bärande källa.
    const passive = (data.passive_sources || []).includes(source)
    return [{ source, scope, label, ...summary, details, passive }]
  })

  const counts = data.league_counts || data.matches.reduce((all, m) => ({
    ...all, [m.league]: (all[m.league] || 0) + 1,
  }), {})
  const visible = data.matches.filter((m) => !hidden.includes(m.league))
  const hasSignal = (m) => {
    if (m.research || m.data_conflict) return false
    if (Object.values(m.value || {}).some((per) => Object.values(per).some((v) => v.edge >= 0.02))) return true
    if (Object.values(m.steam || {}).some((sh) => Math.abs(sh.h6 ?? 0) >= 1.5 || Math.abs(sh.h24 ?? 0) >= 1.5)) return true
    if (Object.values(m.model?.edges || {}).some((e) => e >= 0.05)) return true
    for (const mk of ['ah', 'ou']) {
      if (Object.values(m.model?.[mk]?.edges || {}).some((e) => e >= 0.05)) return true
    }
    for (const mk of ['ah', 'ou', 'cor']) {
      const mv = m.movement?.pinnacle?.[mk]
      if (mv && lineShift(mv.H || mv.O)) return true
    }
    return false
  }
  const listed = onlySignals ? visible.filter(hasSignal) : visible
  const startedCount = listed.filter(
    (m) => m.start && new Date(m.start) < new Date()).length
  const matchRows = hideStarted
    ? listed.filter((m) => !m.start || new Date(m.start) >= new Date())
    : listed
  const completeMatchList = data.matches.length >= (data.total_matches || data.matches.length)
  const unfilteredInitialList = !completeMatchList && hidden.length === 0
    && !onlySignals && !hideStarted
  const matchRowTotal = unfilteredInitialList ? data.total_matches : matchRows.length
  const showCorners = listed.some((m) => {
    const priced = Object.values(m.odds || {}).some((book) => book?.cor?.O && book?.cor?.U)
    return priced || (showModel && m.model?.corners)
  })

  // kvalitet q = edge/(odds−1) = Kelly-andelen: straffar högoddsare — samma edge
  // är mycket skörare på odds 15 än på 1.5 (litet fel i fair blåser upp den)
  // En match = ett kort: bara den bästa selektionen (högst q) per match visas.
  // Urvalet ligger i delade oddsetBestValue — samma som Rek-kolumnen läser.
  const signals = []
  for (const m of visible) {
    if (m.research) continue   // aldrig spelkort/Kelly för forskningsligor
    const best = oddsetBestValue(m)
    if (best) signals.push({ m, ...best })
  }
  // 📈 Rörelse-radarn: största devigade sharp-skiften — går över ALLA ligor
  // (även dolda flikar: träningsmatch-caset får inte missas för att fliken är av)
  // En match = en rad, och bara sidan vars odds SÄNKTS (positiv devigad pp) visas:
  // att motsatt tecken drivit ut är samma rörelse, inte en egen signal
  const movers = []
  for (const m of data.matches) {
    if (m.start && new Date(m.start) < new Date()) continue
    let best = null
    for (const [sg, sh] of Object.entries(m.steam || {})) {
      const cands2 = [['6h', sh.h6], ['24h', sh.h24]].filter(([, v]) => v != null && v >= 1.5)
      if (!cands2.length) continue
      const [win, pp] = cands2.reduce((a, b) => (b[1] > a[1] ? b : a))
      if (!best || pp > best.pp) best = { m, sg, pp, win }
    }
    if (best) movers.push(best)
  }

  const liveMatches = liveRadar?.matches || []
  // Källan som BÄR signalen läser sina egna siffror — providrar blandas
  // aldrig i visningen heller. Flashscore är primär sedan 2026-08-01.
  const liveSourceName = {
    flashscore: 'Flashscore', fotmob: 'FotMob', sofascore: 'Sofascore',
  }
  const liveView = (m) => {
    const signal = m.signal || {}
    const own = m[signal.stats_source]
    const stats = own || m
    const basis = signal.basis || {}
    const explicitBasis = signal.basis != null
    const minute = explicitBasis ? basis.minute : (stats.minute ?? m.minute)
    const homeScore = explicitBasis
      ? basis.home_score : (stats.home_score ?? m.home_score)
    const awayScore = explicitBasis
      ? basis.away_score : (stats.away_score ?? m.away_score)
    const minuteSource = explicitBasis
      ? basis.minute_source : (signal.stats_source || 'sofascore')
    const homeScoreSource = explicitBasis
      ? basis.home_score_source : (signal.stats_source || 'sofascore')
    const awayScoreSource = explicitBasis
      ? basis.away_score_source : (signal.stats_source || 'sofascore')
    return {
      signal,
      stats,
      source: liveSourceName[signal.stats_source] || 'Sofascore',
      minute,
      // Tre lägen, i den här ordningen:
      //  * `stage` (fryst klocka, t.ex. Paus) VINNER över minuten — "45′"
      //    antyder att spelet pågår.
      //  * annars minuten, när den går.
      //  * annars `stageName` som reserv: koherensvakten kan nollställa
      //    stadieklockan, och då vet vi fortfarande VAR matchen är.
      // Matchminuten ska aldrig bara "saknas" (Samans krav 2026-08-06).
      stage: stats.stage_label || m.stage_label || null,
      stageName: stats.stage_name || m.stage_name || null,
      homeScore,
      awayScore,
      // "saknas" är fel ord om klockan: providern VET alltid var matchen är
      // — i paus står den bara stilla. Utan källa faller vi tillbaka på
      // stadiet, aldrig på ett påstående om att uppgiften fattas.
      minuteSource: liveSourceName[minuteSource] || minuteSource || null,
      homeScoreSource: liveSourceName[homeScoreSource] || homeScoreSource || 'saknas',
      awayScoreSource: liveSourceName[awayScoreSource] || awayScoreSource || 'saknas',
      home: stats.home || m.home,
      away: stats.away || m.away,
      hasXg: stats.xg_home != null && stats.xg_away != null,
    }
  }
  const liveLevel = (m) => ({ strong: 3, watch: 2, info: 1 }[m.signal?.level] || 0)
  const liveColumns = [
    { key: 'signal', label: 'Signal', value: (m) => liveLevel(m) * 1000 + Number(m.signal?.score || 0) },
    { key: 'minute', label: 'Min', value: (m) => liveView(m).minute },
    { key: 'score', label: 'Ställning', value: (m) => {
      const { homeScore, awayScore } = liveView(m)
      return (homeScore ?? 0) + (awayScore ?? 0)
    } },
    { key: 'league', label: 'Liga', value: (m) => leagueName[m.league] || m.tournament || m.league },
    { key: 'match', label: 'Match', value: (m) => {
      const { home, away } = liveView(m)
      return `${home} ${away}`
    } },
    { key: 'xg', label: 'xG h–b', value: (m) => {
      const { stats } = liveView(m)
      return stats.xg_home != null && stats.xg_away != null
        ? Number(stats.xg_home) + Number(stats.xg_away) : null
    } },
    { key: 'gap', label: 'Chansgap', value: (m) => m.signal?.chance_gap ?? m.signal?.proxy_index ?? null },
    { key: 'big', label: 'Stora chanser', value: (m) => {
      const { stats } = liveView(m)
      return stats.big_chances_home != null && stats.big_chances_away != null
        ? Number(stats.big_chances_home) + Number(stats.big_chances_away) : null
    } },
    { key: 'shots', label: 'Skott på mål', value: (m) => {
      const { stats } = liveView(m)
      return stats.shots_on_home != null && stats.shots_on_away != null
        ? Number(stats.shots_on_home) + Number(stats.shots_on_away) : null
    } },
    { key: 'source', label: 'Källa', value: (m) => liveView(m).source },
  ]
  const renderLiveRow = (m) => {
    const { signal, stats, source, hasXg, minute, stage, stageName,
      homeScore, awayScore,
      minuteSource, homeScoreSource, awayScoreSource, home, away } = liveView(m)
    const levelLabel = signal.level === 'strong' ? 'STARKT'
      : signal.level === 'watch' ? 'GRANSKA' : 'FÖLJER'
    return (
      <tr key={m.event_id} className={signal.level || 'info'}>
        <td><span className={`radar-table-level ${signal.level || 'info'}`}
          title={signal.reason}>{levelLabel}</span></td>
        <td className="live-minute" title={stage
          ? `${stage} — klockan står stilla; ${minute ?? 45} spelade minuter`
          : minute != null ? `Minut från ${minuteSource}`
            : stageName ? `${stageName} — stadieklockan saknas i den här hämtningen`
              : stageName ? `${stageName} — stadieklockan saknas i den här hämtningen`
            : 'Matchen pågår; stadiet är inte rapporterat i den här hämtningen'}>
          {stage || (minute != null ? `${minute}′` : stageName || 'LIVE')}</td>
        <td title={`Hemmamål från ${homeScoreSource} · bortamål från ${awayScoreSource}`}>
          <b>{homeScore ?? '–'}–{awayScore ?? '–'}</b></td>
        <td>{leagueName[m.league] || m.tournament || m.league}</td>
        <td className="match-name"><b>{home}</b> – {away}</td>
        <td>{hasXg
          ? <b>{Number(stats.xg_home).toFixed(2)}–{Number(stats.xg_away).toFixed(2)}</b>
          : <span className="hint">saknas</span>}</td>
        <td>{signal.chance_gap != null
          ? Number(signal.chance_gap).toFixed(2)
          : signal.proxy_index != null ? `${Number(signal.proxy_index).toFixed(2)} proxy` : '–'}</td>
        <td>{stats.big_chances_home ?? '–'}–{stats.big_chances_away ?? '–'}</td>
        <td>{stats.shots_on_home ?? '–'}–{stats.shots_on_away ?? '–'}</td>
        <td><span className="rchip">{source}</span></td>
      </tr>
    )
  }
  const renderLiveCard = (m) => {
    const { signal, stats, source, hasXg, minute, stage, stageName,
      homeScore, awayScore,
      minuteSource, homeScoreSource, awayScoreSource, home, away } = liveView(m)
    const fallbackParts = []
    if (minuteSource && minuteSource !== source) {
      fallbackParts.push(`minut ${minuteSource}`)
    }
    if (homeScoreSource !== source || awayScoreSource !== source) {
      fallbackParts.push(`resultat ${homeScoreSource === awayScoreSource ? homeScoreSource : `${homeScoreSource}/${awayScoreSource}`}`)
    }
    return (
      <div key={m.event_id} className={`live-radar-card ${signal.level || 'info'}`}>
        <div className="live-radar-score">
          <span className="live-minute" title={stage
            ? `${stage} — klockan står stilla; ${minute ?? 45} spelade minuter`
            : minute != null ? `Minut från ${minuteSource}`
              : stageName ? `${stageName} — stadieklockan saknas i den här hämtningen`
              : stageName ? `${stageName} — stadieklockan saknas i den här hämtningen`
            : 'Matchen pågår; stadiet är inte rapporterat i den här hämtningen'}>
            {stage || (minute != null ? `${minute}′` : stageName || 'LIVE')}</span>
          <b title={`Hemmamål från ${homeScoreSource} · bortamål från ${awayScoreSource}`}>
            {homeScore ?? '–'}–{awayScore ?? '–'}</b>
          <span className="rchip">{leagueName[m.league] || m.tournament || m.league}</span>
        </div>
        <div className="live-radar-teams"><b>{home}</b><span>–</span><b>{away}</b></div>
        <div className="live-radar-stats">
          {hasXg
            ? <span title={`Hela signalen räknas med ${source}s egen statistikserie; providrar blandas aldrig.`}>
                xG <b>{Number(stats.xg_home).toFixed(2)}–{Number(stats.xg_away).toFixed(2)}</b>
                {stats.xgot_home != null && <> · xGOT {Number(stats.xgot_home).toFixed(2)}–{Number(stats.xgot_away).toFixed(2)}</>}
              </span>
            : <span title={`${source} saknar xG; samma källas skott och stora chanser används.`}>xG saknas</span>}
          <span>stora chanser {stats.big_chances_home ?? '–'}–{stats.big_chances_away ?? '–'}</span>
          <span>skott på mål {stats.shots_on_home ?? '–'}–{stats.shots_on_away ?? '–'}</span>
          <span className="rchip" title={`Chansmått: ${source}${fallbackParts.length ? ` · fallback: ${fallbackParts.join(', ')}` : ''}`}>
            {source}{fallbackParts.length ? ` · ${fallbackParts.join(' · ')}` : ''}</span>
        </div>
        {(signal.level === 'watch' || signal.level === 'strong') &&
          <div className="live-radar-reason">{signal.reason}</div>}
        <span className={`live-radar-level ${signal.level || 'info'}`}>
          {signal.level === 'strong' ? 'STARKT CHANSGAP' : signal.level === 'watch' ? 'GRANSKA LIVE' : 'FÖLJER'}
        </span>
      </div>
    )
  }

  const valueColumns = [
    { key: 'start', label: 'Tid', defaultDir: 'asc', value: (r) => r.m.start ? new Date(r.m.start).getTime() : null },
    { key: 'league', label: 'Liga', value: (r) => leagueName[r.m.league] || r.m.league },
    { key: 'match', label: 'Match', value: (r) => `${r.m.home} ${r.m.away}` },
    { key: 'selection', label: 'Tecken', value: (r) => selLabel(r.m, r.mk, r.sg, r.v.line) },
    { key: 'odds', label: 'Odds', value: (r) => r.v.odds },
    { key: 'edge', label: 'Edge', value: (r) => r.v.edge },
    { key: 'kelly', label: '¼-Kelly', value: (r) => kelly(r.v) },
    { key: 'tier', label: 'Nivå', value: (r) => r.v.q ?? 0 },
    { key: 'anchor', label: 'Andra ankaret', value: (r) => r.v.anchor2?.edge ?? null },
  ]
  const valueSupport = ({ m, mk, sg }) => {
    const support = []
    if (mk === '1x2') {
      const st = m.steam?.[sg]
      const stpp = st && (Math.abs(st.h6 ?? 0) >= Math.abs(st.h24 ?? 0) ? st.h6 : st.h24)
      if (stpp != null && stpp >= 1.5) support.push([
        '⚡ sharpen kortar',
        `Pinnacle har flyttat ${sg} ${stpp > 0 ? '+' : ''}${stpp} pp åt spelets håll`,
      ])
    } else {
      const sh = lineShift(m.movement?.pinnacle?.[mk]?.[sg])
      if (sh) support.push(['⇄ sharp-linjen flyttad', `Pinnacle har flyttat linjen ${sh.from} → ${sh.to}`])
    }
    return support
  }
  const renderValueRow = (row) => {
    const { m, mk, sg, v } = row
    const tier = oddsetValueTier(v)
    return (
      <tr key={`${m.id}-${mk}-${sg}`} className="clickable"
        onClick={() => toggleDetail(m.id, true)} title="Öppna matchdetaljen">
        <td>{fmtDay(m.start)} <b>{fmtTime(m.start)}</b></td>
        <td>{leagueName[m.league] || m.league}</td>
        <td className="match-name"><b>{m.home}</b> – {m.away}</td>
        <td><b>{selLabel(m, mk, sg, v.line)}</b>
          {v.book !== 'svenskaspel' && <span className="tipbook"> · {BOOK_NAME[v.book] || v.book}</span>}</td>
        <td><b>{v.odds.toFixed(2)}</b></td>
        <td className="pos"><b>+{(v.edge * 100).toFixed(1)} %</b>{v.derived ? '°' : ''}</td>
        <td>{kelly(v)} kr</td>
        <td><span className={`rekpill ${tier.cls}${tier.disputed ? ' disputed' : ''}`}>
          {tier.disputed ? '⚓ ' : ''}{tier.short}</span></td>
        <td>{v.anchor2?.edge != null
          ? <span className={v.anchor2.edge >= 0 ? 'pos' : 'neg'}>
              {v.anchor2.edge >= 0 ? '+' : ''}{(v.anchor2.edge * 100).toFixed(1)} %
            </span>
          : '–'}</td>
      </tr>
    )
  }
  const renderValueCard = (row) => {
    const { m, mk, sg, v } = row
    const tier = oddsetValueTier(v)
    const support = valueSupport(row)
    return (
      <div key={`${m.id}-${mk}-${sg}`} className={`tipcard ${tier.cls} clickable`}
        title="Visa matchdetalj" onClick={() => toggleDetail(m.id, true)}>
        <div className="tiphead">
          <b className="tipsel">{selLabel(m, mk, sg, v.line)} @ {v.odds.toFixed(2)}</b>
          {v.book !== 'svenskaspel' && <span className="tipbook">hos {BOOK_NAME[v.book] || v.book}</span>}
          <span className={`edgechip ${tier.cls}`}>{tier.label} +{(v.edge * 100).toFixed(1)}%{v.derived ? '°' : ''}</span>
        </div>
        <div className="tipmatch">
          <span className="lgtag">{(leagueName[m.league] || m.league).slice(0, 1)}</span>
          {m.home} – {m.away}
          <span className="hint">{fmtDay(m.start)} {fmtTime(m.start)}</span>
        </div>
        <div className="tipwhy hint">
          Devigad Pinnacle {(v.fair * 100).toFixed(1)} % · ¼-Kelly <b>{kelly(v)} kr</b>
          {v.held_after_sharp && <span className="heldchip">bekräftat kvar</span>}
          {tier.disputed && <span className="anchorwarn">⚓ Smarkets {(v.anchor2.edge * 100).toFixed(1)} %</span>}
        </div>
        {support.length > 0 && <div className="tipsupport">
          {support.map(([label, title]) => <span key={label} className="schip" title={title}>{label}</span>)}
        </div>}
      </div>
    )
  }

  const moverColumns = [
    { key: 'start', label: 'Tid', defaultDir: 'asc', value: (r) => r.m.start ? new Date(r.m.start).getTime() : null },
    { key: 'league', label: 'Liga', value: (r) => leagueName[r.m.league] || r.m.league },
    { key: 'match', label: 'Match', value: (r) => `${r.m.home} ${r.m.away}` },
    { key: 'selection', label: 'Tecken', value: (r) => selLabel(r.m, '1x2', r.sg) },
    { key: 'movement', label: 'Rörelse', value: (r) => r.pp },
    { key: 'window', label: 'Fönster', value: (r) => r.win },
    { key: 'edge', label: 'Edge', value: (r) => r.m.value?.['1x2']?.[r.sg]?.edge ?? null },
    { key: 'price', label: 'Pinnacle', value: (r) => r.m.movement?.pinnacle?.['1x2']?.[r.sg]?.last ?? null },
    { key: 'book', label: 'Bokstatus', value: (r) => r.m.value?.['1x2']?.[r.sg]?.held_after_sharp ? 2 : 1 },
  ]
  const moverStatus = ({ m, sg, pp: movement }) => {
    const v = m.value?.['1x2']?.[sg]
    if (m.research) return <span className="rchip">🔬 forskning</span>
    if (v?.edge >= 0.02 && movement > 0 && v.held_after_sharp) {
      return <span className="epill">{BOOK_NAME[v.book] || v.book} kvar {v.odds.toFixed(2)}</span>
    }
    if (v?.edge >= 0.02 && movement > 0) return <span className="hint">värde, ej återbekräftat</span>
    return <span className="hint">böckerna har hängt med</span>
  }
  const renderMoverRow = (row) => {
    const { m, sg, pp: movement, win } = row
    const mvP = m.movement?.pinnacle?.['1x2']?.[sg]
    const v = m.value?.['1x2']?.[sg]
    return (
      <tr key={`${m.id}-${sg}`} className="clickable"
        onClick={() => toggleDetail(m.id, true)} title="Öppna matchdetaljen">
        <td>{fmtDay(m.start)} <b>{fmtTime(m.start)}</b></td>
        <td>{leagueName[m.league] || m.league}</td>
        <td className="match-name"><b>{m.home}</b> – {m.away}</td>
        <td><b>{selLabel(m, '1x2', sg)}</b></td>
        <td className="neg"><b>+{movement} pp</b></td>
        <td>{win}</td>
        <td>{v?.edge != null ? `${v.edge >= 0 ? '+' : ''}${(v.edge * 100).toFixed(1)} %` : '–'}</td>
        <td>{mvP ? `${mvP.first.toFixed(2)} → ${mvP.last.toFixed(2)}` : '–'}</td>
        <td>{moverStatus(row)}</td>
      </tr>
    )
  }
  const renderMoverCard = (row) => {
    const { m, sg, pp: movement, win } = row
    const mvP = m.movement?.pinnacle?.['1x2']?.[sg]
    return (
      <div key={`${m.id}-${sg}`} className="mover-card clickable"
        onClick={() => toggleDetail(m.id, true)}>
        <div><span className={Math.abs(movement) >= 3.5 ? 'steam strong' : 'steam'}>🔥</span>
          <b className="mv down">+{movement} pp/{win}</b>
          <span className="hint">{fmtDay(m.start)} {fmtTime(m.start)}</span></div>
        <b>{selLabel(m, '1x2', sg)}</b>
        <span>{m.home} – {m.away}</span>
        <span className="hint">{mvP ? `P ${mvP.first.toFixed(2)} → ${mvP.last.toFixed(2)}` : ''}</span>
        <div>{moverStatus(row)}</div>
      </div>
    )
  }

  const maxMatchMovement = (m) => {
    const values = Object.values(m.steam || {}).flatMap((sh) =>
      [sh.h6, sh.h24].filter((v) => v != null).map(Math.abs))
    return values.length ? Math.max(...values) : null
  }
  const detailedMovement = (m) => movementDetail?.id === m.id
    ? movementDetail.movement : m.movement
  const svsPrice = (m, market, sign) =>
    m.odds?.svenskaspel?.[market]?.[sign] ??
    m.odds?.pinnacle?.[market]?.[sign] ?? null
  const matchColumns = [
    { key: 'start', label: 'Datum/tid', defaultDir: 'asc',
      value: (m) => m.start ? new Date(m.start).getTime() : null },
    { key: 'league', label: 'Liga', value: (m) => leagueName[m.league] || m.league },
    { key: 'match', label: 'Match', value: (m) => `${m.home} ${m.away}` },
    { key: 'edge', label: 'Rek/edge', value: (m) => oddsetBestValue(m)?.v.edge ?? null,
      title: 'Matchens bästa värdeselektion ur samma motor som Värdespel.' },
    { key: 'movement', label: 'Rörelse', value: maxMatchMovement,
      title: 'Största absoluta devigade sharp-rörelse i 6/24 h.' },
    { key: '1', label: '1', value: (m) => svsPrice(m, '1x2', '1') },
    { key: 'X', label: 'X', value: (m) => svsPrice(m, '1x2', 'X') },
    { key: '2', label: '2', value: (m) => svsPrice(m, '1x2', '2') },
    { key: 'ah', label: 'AH', value: (m) => svsPrice(m, 'ah', 'H'),
      title: 'Asian handicap (hemmalinje) · odds hemma/borta.' },
    { key: 'ou', label: 'Ö/U', value: (m) => svsPrice(m, 'ou', 'O'),
      title: 'Asiatisk total · odds över/under.' },
    ...(showCorners ? [{
      key: 'cor', label: 'Hörnor', value: (m) => svsPrice(m, 'cor', 'O'),
      title: 'Totala hörnor · odds över/under.',
    }] : []),
  ]
  // Powerrank per match (AMBER). Hämtas i ETT anrop för alla ligor — uppmätt
  // 0,5 s i backend — och slås upp på normaliserat lagnamn. Visas som ren
  // kontext bredvid lagnamnen; den påverkar inte edge, urval eller notiser,
  // och får därför aldrig färgsättas som en signal.
  const rankFor = (league, team) => {
    const table = powerRank?.by_league?.[league]
    if (!table || !team) return null
    // Exakt aliasträff först — powerrank bär de RÅA namnen providern skrev.
    // Substrängsfallbacken finns kvar för lag vars alias vi inte sett ännu,
    // men den får aldrig gå före en exakt träff.
    const key = String(team).trim().toLowerCase()
    const exact = table.find((t) =>
      (t.aliases || []).some((a) => a.trim().toLowerCase() === key))
    if (exact) return exact
    return table.find((t) => key.includes(t.team) || t.team.includes(key)) || null
  }
  const rankPair = (m) => {
    const h = rankFor(m.league, m.home), a = rankFor(m.league, m.away)
    if (!h && !a) return null
    const label = (r) => (r ? `#${r.rank}` : '–')
    const over = (r) => (r?.overperformance == null ? ''
      : ` (${r.overperformance > 0 ? '+' : ''}${r.overperformance} mot xP)`)
    return {
      text: `${label(h)}/${label(a)}`,
      title: [
        h && `${m.home}: rank ${h.rank}, styrka ${h.ratio}${over(h)}`,
        a && `${m.away}: rank ${a.rank}, styrka ${a.ratio}${over(a)}`,
        'Modellens egen styrkeskattning (amber) — påverkar inga signaler.',
      ].filter(Boolean).join('\n'),
    }
  }

  const renderMatchRow = (m) => (
    <Fragment key={m.id}>
      <tr id={`oddsrow-${m.id}`} className={[
        m.start && new Date(m.start) < new Date() ? 'started' : '',
        m.data_conflict ? 'data-conflict' : '',
      ].filter(Boolean).join(' ')}>
        <td className="time"><span>{fmtDay(m.start)}</span><b>{fmtTime(m.start)}</b></td>
        <td className="league-cell"><span className="rchip">{leagueName[m.league] || m.league}</span></td>
        <td className="teams clickable"
          onClick={() => toggleDetail(m.id)}
          title={[`Klicka för detaljvy (grafer, serier, flaggor)`,
            m.elo && `ClubElo: ${m.elo.h ?? '?'} vs ${m.elo.a ?? '?'}`,
            m.model && `Modell-μ: ${m.model.mu[0]}–${m.model.mu[1]}${m.model.anchored ? ' (ankrad mot sharp)' : ''}`]
            .filter(Boolean).join('\n')}>
          {m.home} – {m.away}{steamBadge(m)}{absBadge(m)}
          {(() => {
            const r = rankPair(m)
            return r ? <span className="rchip rankchip" title={r.title}>🏋 {r.text}</span> : null
          })()}
          {m.research && <span className="rchip" title="Forskningsliga — odds och rörelser visas, men inga spelbara signaler.">🔬</span>}
          {m.data_conflict && (
            <span className="conflictchip"
              title={`${m.data_conflict.message}\n${(m.data_conflict.reasons || []).join('\n')}`}>
              ⚠ datakrock · inga signaler
            </span>
          )}
        </td>
        {rekCell(m)}
        <td className="movement-cell">{maxMatchMovement(m) != null
          ? <b>{maxMatchMovement(m).toFixed(1)} pp</b> : '–'}</td>
        {['1', 'X', '2'].map((s) => cell1x2(m, s))}
        {cellPair(m, 'ah', 'H', 'A', fmtAh)}
        {cellPair(m, 'ou', 'O', 'U', (l) => l)}
        {showCorners && cellPair(m, 'cor', 'O', 'U', (l) => l)}
      </tr>
      {expanded === m.id && (
        <tr className="detailrow"><td colSpan={matchColumns.length}>
          <div className="dcharts">
            {['1', 'X', '2'].map((sg) => (
              <DetailChart key={sg}
                label={sg === '1' ? `1 · ${m.home}` : sg === '2' ? `2 · ${m.away}` : 'X · Kryss'}
                series={[
                  { color: 'var(--green)', pts: detailedMovement(m)?.svenskaspel?.['1x2']?.[sg]?.pts },
                  { color: '#5b9bd5', pts: detailedMovement(m)?.pinnacle?.['1x2']?.[sg]?.pts },
                ]} />
            ))}
          </div>
          <div className="dmeta hint">
            <span><b style={{ color: 'var(--green)' }}>●</b> SvS · <b style={{ color: '#5b9bd5' }}>●</b> Pinnacle</span>
            {['ah', 'ou', 'cor'].map((mk) => {
              const mv = m.movement?.pinnacle?.[mk]
              const sgn = mk === 'ah' ? 'H' : 'O'
              const a = mv?.[sgn]
              if (!a) return null
              return <span key={mk}>{MARKET_LABEL[mk]} (P): [{a.first_l}] {a.first.toFixed(2)} → [{a.last_l}] {a.last.toFixed(2)} ({a.n} punkter)</span>
            })}
            {m.model && <span>Modell: μ {m.model.mu[0]}–{m.model.mu[1]} · fair {m.model.fair['1']}/{m.model.fair['X']}/{m.model.fair['2']}{m.model.cal_t ? ` · T=${m.model.cal_t}` : ''}{m.model.prior ? ' · Elo-prior' : ''}</span>}
            {m.elo && <span>Elo {m.elo.h ?? '?'}–{m.elo.a ?? '?'}</span>}
            {m.absences?.confirmed && <span>✓ elvor bekräftade</span>}
            {m.absences && ['home', 'away'].map((side) => (
              m.absences[side]?.length
                ? <span key={side}>🚑 {side === 'home' ? m.home : m.away}: {m.absences[side].map(absLine).join(', ')}</span>
                : null))}
          </div>
          <div className="matchflags">
            <b>📒 Våra rekar i matchen</b>
            {matchFlags?.id !== m.id
              ? <span className="hint">hämtar…</span>
              : matchFlags.error
                ? <span className="hint">Kunde inte hämta rek-historiken.</span>
                : matchFlags.rows.length === 0
                  ? <span className="hint">Inga rekar loggade i matchen.</span>
                  : matchFlags.rows.map((r, j) => (
                    <div key={j} className="flagrow">
                      <span className="hint">{r.first_at ? new Date(r.first_at).toLocaleString('sv-SE', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                      <span>{r.tier === 'model' ? '🧪' : '💰'}</span>
                      <b>{selLabel(m, FLAG_MARKET[r.market] || r.market, r.sign, r.line)}</b>
                      <span>{BOOK_NAME[r.book] || r.book || 'SvS'} @ {r.first_odds}</span>
                      <span className="hint">edge {(r.first_edge * 100).toFixed(1)}% → {(r.best_edge * 100).toFixed(1)}%</span>
                      {r.anchor2_edge != null && r.anchor2_edge <= 0 && <span className="anchorwarn">⚓</span>}
                      {r.close_ev != null
                        ? <span className={`evpill ${r.close_ev >= 0 ? 'pos' : 'neg'}`}>
                            {r.close_ev >= 0 ? '+' : ''}{(r.close_ev * 100).toFixed(1)}%</span>
                        : <span className="hint">{r.closing_note || 'öppen'}</span>}
                    </div>
                  ))}
          </div>
        </td></tr>
      )}
    </Fragment>
  )

  return (
    <section className="oddset">
      <div className="analys-head">
        <h2>Oddset — enskilda matcher</h2>
      </div>
      <OddsetLegend />
      <div className="oddset-bar">
        <div className="league-filter" aria-label="Ligafilter">
          {data.leagues.map((l) => (
            <button key={l.key}
              className={`${hidden.includes(l.key) ? 'lg off' : 'lg'}${l.research ? ' research' : ''}`}
              onClick={() => toggleLeague(l.key)}
              title={`${l.research ? 'Forskningsliga — V2.2 samlar data. Odds, prisålder och rörelser visas, men inga värdesignaler, Kelly, notiser eller facit ännu.\n' : ''}${hidden.includes(l.key) ? 'Visa ligan' : 'Dölj ligan'}`}>
              {l.research ? '🔬 ' : ''}{l.name} {counts[l.key] ? `(${counts[l.key]})` : '(0)'}
            </button>
          ))}
        </div>
        <div className="oddset-tools">
          <button className={showModel ? 'lg model on' : 'lg model'} onClick={toggleModel}
            title="XG-viktad Poisson-styrkefit per liga med DC-korrektion i prediktionen. Temperatur T valdes på historiska backtestmaterialet; prognosledgern är oberoende forward-facit. Amber-tier tills ledgern godkänt den.">
            🧪 Modell {showModel ? 'på' : 'av'}
          </button>
          <button className={onlySignals ? 'lg on' : 'lg'} onClick={toggleOnly}
            title="Visa bara matcher med någon signal: sharp-värde, steam, linjeflytt eller modellavvikelse. Snabbkollen på mobilen.">
            🎯 Bara signaler
          </button>
          <button className={showNotices ? 'lg on' : 'lg'} onClick={() => setShowNotices(!showNotices)}
            title="Historik över triggade larm (värde ≥3 % / steam ≥5 pp) — även de som INTE pushades för att NTFY_TOPIC saknas.">
            🔔 {notices?.length || 0}
          </button>
          <button className={showSources ? 'lg on' : 'lg'} onClick={() => setShowSources(!showSources)}
            aria-expanded={showSources}>
            Datakällor {sourceHealth.filter((h) => h.ok).length}/{sourceHealth.length}
          </button>
          <button className={showBooks ? 'lg on' : 'lg'} onClick={() => setShowBooks(!showBooks)}
            aria-pressed={showBooks} title="Visa eller dölj spelbara sidoböcker. Ninja/Altenar visas för 1X2, Ö/U och hörnor; Smarkets visas alltid som sharp-ankare.">
            {showBooks ? '− Färre odds' : '+ Fler odds'}
          </button>
          <span className="hint odds-fetched">
            {data.last_run ? `hämtat ${new Date(data.last_run).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' })}` : 'inga odds ännu'}
          </span>
          <button onClick={refresh} disabled={busy}>{busy ? 'Hämtar…' : '↻ Färska odds'}</button>
        </div>
      </div>
      <div className="oddset-tabs" role="tablist" aria-label="Oddset-vy">
        {[['matcher', '📋 Matcher'], ['live', '⚡ Live'],
          ['varde', '💰 Värdespel'], ['rorelser', '📈 Rörelser'],
          ['styrka', '🏋 Lagstyrka']].map(([t, label]) => (
          <button key={t} className={`oddset-tab ${oddsetTab === t ? 'active' : ''}`}
            role="tab" aria-selected={oddsetTab === t}
            onClick={() => pickTab(t)}>{label}</button>
        ))}
        <span className="oddset-tabcount hint">
          ⚡ {liveRadar?.matches?.length ?? 0} live{liveRadar?.signal_count ? ` · ${liveRadar.signal_count} att granska` : ''}
          {' '}· 💰 {signals.length} värdespel · 📈 {movers.length} rörelser
        </span>
      </div>
      {showSources && (
        <div className="source-health-list">
          {sourceHealth.map((h) => {
            const stateText = h.ok
              ? timeAgo(h.latest)
              : h.passive
                ? 'samlas · matar inget'
                : h.status === 'partial'
                  ? 'delvis svar'
                  : h.status === 'stale'
                    ? 'för gammal'
                    : h.status === 'missing'
                      ? 'ingen kontroll'
                      : 'behöver tillsyn'
            const titleState = h.ok
              ? `frisk · ${timeAgo(h.latest)}`
              : h.passive
                ? 'passiv källa — samlas men matar inget beslut, så ett fel här kräver ingen åtgärd'
                : h.status === 'partial' ? 'ofullständig kontroll' : 'fel eller för gammal'
            return (
              <span key={`${h.source}:${h.scope}`}
                className={`sourcehealth ${h.passive && !h.ok ? 'passive'
                  : h.status || (h.ok ? 'ok' : 'bad')}`}
                title={`${h.label}: ${titleState}\n${h.details}`}>
                {h.ok ? '●' : h.passive ? '○' : h.status === 'partial' ? '◐' : '▲'} {h.label} · {stateText}
              </span>
            )
          })}
        </div>
      )}
      {showNotices && notices && (
        <div className="valuelist noticelist">
          <div className="valhead"><b>🔔 Larm-historik</b>
            <InfoDot text={'Alla triggade larm (värde ≥3 % / steam ≥5 pp, dedup per selektion).\n"ej pushad" = NTFY_TOPIC saknas i backend/.env — sätt den + prenumerera i ntfy-appen för pushar till mobilen.'} /></div>
          {notices.length === 0 && <div className="hint">Inga larm triggade ännu.</div>}
          {notices.slice(0, 20).map((n, i) => (
            <div key={i} className="valrow">
              <span className="hint">{n.at ? new Date(n.at).toLocaleString('sv-SE', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
              <b>{n.title}</b>
              <span className="hint">{n.msg}</span>
              <span className={n.sent ? 'epill' : 'schip'} title={n.sent ? 'Skickad via ntfy' : 'Inte skickad — NTFY_TOPIC saknas'}>
                {n.sent ? 'pushad' : 'ej pushad'}</span>
            </div>
          ))}
        </div>
      )}
      {oddsetTab === 'live' && liveRadar && (
        <div className={`tab-panel live-radar ${liveRadar.signal_count ? 'active' : ''}`} id="oddset-live-radar">
          <div className="live-radar-head">
            <div>
              <b>⚡ Live-radar</b>
              <span className="live-shadow">shadow · inga automatiska spel</span>
            </div>
            <span className="hint">
              {liveMatches.length
                ? `${liveMatches.length} live · ${liveRadar.signal_count} att granska`
                : 'inga matcher med chansdata live'}
              {liveRadar.hidden_no_stats > 0 && (
                <span title={`Källan rapporterar inga skott- eller chansmått för dessa: ${liveRadar.hidden_by_league}. En tidig match med MÄTTA nollor döljs inte — skillnaden är saknat värde mot noll.`}>
                  {' '}· {liveRadar.hidden_no_stats} dolda utan chansdata
                </span>
              )}
              {liveRadar.last_run
                ? ` · kollad ${timeAgo(liveRadar.last_run)}`
                : <span title={`Gemensam tid visas först när ${(liveRadar.sources?.length
                  ? liveRadar.sources : ['flashscore', 'fotmob'])
                  .map((s) => ({ flashscore: 'Flashscore', fotmob: 'FotMob', sofascore: 'Sofascore' })[s] || s)
                  .join(' och ')} har kontrollerats.`}>
                    {' '}· inväntar {liveRadar.sources?.length || 2} livekällor
                  </span>}
            </span>
          </div>
          {liveMatches.length > 0
            ? <SortableTable id="oddset-live" columns={liveColumns}
                rows={liveMatches} renderRow={renderLiveRow}
                renderCard={renderLiveCard}
                defaultSort={{ key: 'signal', dir: 'desc' }}
                className="oddset-list-table live-list-table" />
            : <EmptyState title="Inga matcher med chansdata live"
                detail="Matcher utan rapporterade skott eller chanser döljs, men räknas i statusraden ovan." />}
          <div className="live-radar-foot">
            Chansgap mäter skapade chanser mot faktiska mål medan tid återstår.
            Saknas xG räknas skott och stora chanser i stället — den varianten
            har ännu inte visat sig förutsäga mål i vår historik. Inget av detta
            påverkar värdesignaler, Kelly, facit eller pushnotiser.
            {liveRadar.dropped ? ` Urval: ${liveRadar.dropped}.` : ''}
          </div>
        </div>
      )}
      {oddsetTab === 'varde' && (
        <div className="tab-panel valuelist" id="oddset-varde">
          <div className="valhead"><b>💰 Värdespel just nu</b>
            <InfoDot text={'Bok-odds över devigad Pinnacle (sharp-ankrat = den spelbara signalen).\n° = härlett sharp-pris · ★ = flera oberoende signaler pekar åt samma håll.\n¼-Kelly räknas på fair-sannolikheten och din bank.\nEtt kort per match: den bästa selektionen (högst kvalitetsviktad edge).'} />
            <span className="spacer" />
            <span className="hint">bank</span>
            <input className="bankin" type="number" value={bank} min="0"
              onChange={(e) => saveBank(Number(e.target.value) || 0)} /> <span className="hint">kr</span>
          </div>
          {signals.length > 0
            ? <SortableTable id="oddset-values" columns={valueColumns}
                rows={signals} renderRow={renderValueRow}
                renderCard={renderValueCard}
                defaultSort={{ key: 'edge', dir: 'desc' }}
                className="oddset-list-table value-list-table" />
            : <EmptyState title="Inga värdespel just nu"
                detail="Inga synliga matcher når spelgrinden: sharp-ankrad edge ≥2 % och kvalitetsgolvet." />}
        </div>
      )}
      {oddsetTab === 'styrka' && <PowerRankPanel leagues={data.leagues} />}

      {oddsetTab === 'rorelser' && (
        <div className="tab-panel valuelist moverlist" id="oddset-radar">
          <div className="valhead"><b>📈 Marknadsradar</b>
            <span className="hint">{movers.length} större devigade sharp-rörelser</span></div>
          {movers.length > 0
            ? <SortableTable id="oddset-movers" columns={moverColumns}
                rows={movers} renderRow={renderMoverRow}
                renderCard={renderMoverCard}
                defaultSort={{ key: 'movement', dir: 'desc' }}
                className="oddset-list-table mover-list-table" />
            : <EmptyState title="Inga större rörelser"
                detail="Ingen kommande match har flyttat minst 1,5 procentenheter i 6- eller 24-timmarsfönstret." />}
        </div>
      )}
      {oddsetTab === 'rorelser' && showModel && (() => {
        const msig = []
        for (const m of visible) {
          if (m.start && new Date(m.start) < new Date()) continue
          for (const [sg, e] of Object.entries(m.model?.edges || {})) {
            if (e >= 0.05) msig.push({ m, label: selLabel(m, '1x2', sg), e, p: m.model.p[sg], fair: m.model.fair[sg] })
          }
          for (const mk of ['ah', 'ou']) {
            const mp = m.model?.[mk]
            for (const [sd, e] of Object.entries(mp?.edges || {})) {
              if (e >= 0.05) msig.push({
                m, label: selLabel(m, mk, sd, mp.line), e, p: mp[`p${sd}`], fair: mp[sd],
              })
            }
          }
        }
        msig.sort((a, b) => b.e - a.e)
        return msig.length > 0 && (
          <div className="valuelist amberlist">
            <div className="valhead"><b>🧪 Modell-avvikelser (amber)</b>
              <InfoDot text={'XG-viktad Poisson-styrkefit med DC-korrektion i prediktionen vs SvS-odds, inkl. AH/Ö-U.\nTemperatur T valdes och utvärderades på samma historiska backtestmaterial. EXPERIMENTELLT: +10 % ROI i Allsvenskan vid låga trösklar (inom bruset, n=326), −17 % i Eliteserien; AH/Ö-U obacktestade.\nPrognosledgern är oberoende forward-facit — signalspaning, inte spelrekommendation.'} /></div>
            {msig.slice(0, showAllModel ? 8 : 3).map(({ m, label, e, p, fair }, i) => (
              <div key={i} className="valrow">
                <span className="apill big">+{(e * 100).toFixed(1)}%</span>
                <b>{label}</b>
                <span className="hint">modell {(p * 100).toFixed(0)}% (fair {fair?.toFixed(2)})</span>
                <span className="vteams">{m.home} – {m.away}</span>
                <span className="hint">{fmtDay(m.start)} {fmtTime(m.start)}</span>
              </div>
            ))}
            {msig.length > 3 && (
              <button className="show-more" onClick={() => setShowAllModel(!showAllModel)}>
                {showAllModel ? 'Visa färre modellavvikelser' : `Visa ${Math.min(5, msig.length - 3)} till`}
              </button>
            )}
          </div>
        )
      })()}
      {oddsetTab === 'matcher' && (
        <div className="tab-panel" id="oddset-matches">
          <div className="match-list-toolbar">
            <span className="hint">{showAllMatches || matchRowTotal <= 40
              ? `${matchRows.length} matcher visas`
              : `40 av ${matchRowTotal} matcher visas`}</span>
            <button className={hideStarted ? 'lg on' : 'lg'}
              onClick={toggleStarted} aria-pressed={hideStarted}
              disabled={startedCount === 0}>
              {hideStarted ? 'Visa startade' : 'Dölj startade'}
              {startedCount > 0 ? ` (${startedCount})` : ''}
            </button>
          </div>
          {matchRows.length > 0
            ? <>
                <SortableTable id="oddset-matches" columns={matchColumns}
                  rows={matchRows} renderRow={renderMatchRow}
                  defaultSort={{ key: 'start', dir: 'asc' }}
                  className="oddset-table" limit={showAllMatches ? null : 40}
                  wrapperClassName="oddset-table-wrap" />
                {completeMatchList && matchRows.length > 40 && (
                  <button className="show-more" onClick={() => setShowAllMatches(!showAllMatches)}>
                    {showAllMatches ? 'Visa de första 40 matcherna'
                      : `Visa alla ${matchRows.length} matcher`}
                  </button>
                )}
              </>
            : <EmptyState title="Inga matcher att visa"
                detail={hideStarted && startedCount > 0
                  ? 'Alla matcher i urvalet har startat. Visa startade för att ta fram dem igen.'
                  : onlySignals
                  ? 'Inga synliga matcher har en aktuell signal. Stäng av Bara signaler för att se alla.'
                  : 'Välj fler ligor eller hämta färska odds.'} />}
        </div>
      )}
    </section>
  )
}
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
  { id: 'ev', label: 'Värderader (EV × träffchans)', q: 'ev=true' },
  { id: 'farg', label: 'Färgreducering (min/max per färg)', q: 'color=true' },
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

/* ---------- Svenska Spel "Egna rader"-export (filuppladdning) ----------
   Tjänsten finns på .../externa-systemspel (Stryktipset, Europatipset och
   Topptipset — alla varianter laddas upp via topptipset-sidan).
   Filformat: en rad per spelad rad, "E,<tecken>,<tecken>,..." i matchordning.
   Vi enumererar konkreta rader (E) – korrekt även för reducerade system där
   vi måste behålla exakt de raderna (ett M-system skulle spela hela produkten). */
function egnaRaderUrl(product) {
  if (product === 'stryktipset' || product === 'europatipset' || product === 'bomben') {
    return `https://spela.svenskaspel.se/${product}/externa-systemspel`
  }
  if (product?.startsWith('topptipset')) {
    return 'https://spela.svenskaspel.se/topptipset/externa-systemspel'
  }
  return null
}
// Bomben Egna rader: rubrikrad + en rad per spelrad med exakt resultat per match.
// OBS: Bombens filspec är inloggningsskyddad — rubrik/format här är rekonstruerat
// efter SvS mönster och bör verifieras vid första uppladdningen.
function egnaRaderBombenText(rows) {
  return 'Bomben\r\n' + rows.map((r) => 'E,' + r.join(',')).join('\r\n') + '\r\n'
}
function cartesianRows(groups) {
  let rows = [[]]
  for (const g of groups) {
    const next = []
    for (const r of rows) for (const s of g) next.push([...r, s])
    rows = next
  }
  return rows
}
// Obligatorisk rubrikrad (enligt SvS filspecifikation): produktnamn först,
// Topptipset kräver dessutom variant + Omg= + Insats= (1–10 kr/rad).
function egnaRaderHeader(product, draw) {
  if (product === 'stryktipset') return 'Stryktipset'
  if (product === 'europatipset') return 'Europatipset'
  if (product === 'topptipset') return `Topptipset,Omg=${draw},Insats=1`
  if (product === 'topptipsetstryk') return `Topptipset,Stryk,Omg=${draw},Insats=1`
  if (product === 'topptipsetextra') return `Topptipset,Europa,Omg=${draw},Insats=1`
  return null
}
function egnaRaderText(product, draw, rows) {
  return egnaRaderHeader(product, draw) + '\r\n'
    + rows.map((r) => 'E,' + r.join(',')).join('\r\n') + '\r\n'
}
function downloadText(filename, text) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
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

/* Värdera en konkret uppsättning rader. Per rad: Poisson-binomial över odds
   (P att raden får k rätt) och över folkets streck (medvinnartäthet). Utdelning
   om rätt = pott_k / (förv. medvinnare + dig själv). Spårar lägsta/medel/högsta
   utdelning per nivå över raderna — utdelningens spann (likt reducering.se). */
// κ-korrektion per produkt och nivå — MÅSTE hållas i synk med KAPPA i
// backend/app/builder.py (PH4-analysen 2026-07-24, 7 754 avgjorda omgångar).
// κ > 1 = folket klumpar ihop sig mer än oberoende-antagandet ⇒ fler
// medvinnare ⇒ lägre utdelning. Korrektionen sänker EV, aldrig tvärtom.
const KAPPA = {
  stryktipset: { 13: 1.096, 12: 1.114, 11: 1.102, 10: 1.076 },
  europatipset: { 13: 1.070, 12: 1.064, 11: 1.063, 10: 1.048 },
  topptipset: { 8: 1.038 },
  topptipsetstryk: { 8: 1.040 },
  topptipsetextra: { 8: 1.022 },
}
const kappaFor = (product, correct) => KAPPA[product]?.[correct] ?? 1.0

// Folkets sannolikhet för ett tecken, med GOLV. Utan golv gav streck = 0
// (finns på 38 event i databasen) pk = 0 → utdelning = HELA potten, och
// EV-rankaren älskade exakt de tecknen. Backend har haft max(q, 0.001) i
// builder._pq hela tiden; frontend saknade det helt — samma golv måste
// gälla i båda annars visar UI:t en annan EV än den byggaren optimerade.
const FOLK_MIN = 0.001
const folkProb = (o) => {
  if (!o) return FOLK_MIN
  const q = o.streck != null ? o.streck / 100 : (o.fair_prob || 0)
  return Math.max(q, FOLK_MIN)
}

function evalRows(rowFF, tiers, field, N, minDividend = 0, product = null) {
  const poly = {}, evTiers = {}, divMin = {}, divMax = {}
  let kept = 0, evPayout = 0
  for (const row of rowFF) {
    const pf = poissonBinomial(row.map((o) => o.fair))
    const pk = poissonBinomial(row.map((o) => o.folk))
    const div = {}
    for (const t of tiers) {
      const c = t.correct
      div[c] = Math.min(t.pool, t.pool / (field * (pk[c] || 0) * kappaFor(product, c) + 1))
    }
    if (minDividend > 0 && (div[N] || 0) < minDividend) continue
    kept++
    for (const t of tiers) {
      const c = t.correct
      poly[c] = (poly[c] || 0) + (pf[c] || 0)
      const contrib = (pf[c] || 0) * div[c]
      evPayout += contrib; evTiers[c] = (evTiers[c] || 0) + contrib
      if ((pf[c] || 0) > 0) {
        divMin[c] = divMin[c] == null ? div[c] : Math.min(divMin[c], div[c])
        divMax[c] = divMax[c] == null ? div[c] : Math.max(divMax[c], div[c])
      }
    }
  }
  const dividend = {}
  for (const c in evTiers) dividend[c] = poly[c] ? evTiers[c] / poly[c] : null
  return { poly, evTiers, dividend, divMin, divMax, kept, evPayout }
}

function couponStats(matches, picks, payouts, minDividend = 0, turnoverOverride = null, jackpot = 0, pickRows = null) {
  const N = matches.length
  const rowPrice = payouts?.row_price || 1
  const ratio = payouts?.ratio || 0
  const turnover = turnoverOverride != null ? turnoverOverride : (payouts?.turnover || 0)

  // RADLÄGE: kupongen är en explicit lista utvalda rader (t.ex. från EV-topp/
  // färgreducering) — värdera exakt de raderna, inte alla teckenkombinationer.
  if (pickRows && pickRows.length && pickRows.every((r) => r.length === N)) {
    const tiers = (payouts?.tiers || []).map((t) => ({
      correct: t.correct,
      pool: turnover * ratio * (t.share || 0) + (t.correct === N ? jackpot : 0),
    }))
    const poolMap = {}; tiers.forEach((t) => { poolMap[t.correct] = t.pool })
    const field = turnover / rowPrice
    const rowFF = pickRows.map((r) => r.map((s, i) => {
      const o = matches[i].outcomes[s] || {}
      return { fair: o.fair_prob || 0, folk: folkProb(o) }
    }))
    const modelOk = field > 0 && tiers.length > 0
    const e = modelOk ? evalRows(rowFF, tiers, field, N, minDividend, payouts?.product)
      : { poly: {}, evTiers: {}, dividend: {}, divMin: {}, divMax: {}, kept: pickRows.length, evPayout: 0 }
    const rows = e.kept
    const cost = rows * rowPrice
    const expectedCorrect = rowFF.reduce((a, r) => a + r.reduce((x, o) => x + o.fair, 0), 0) / (rowFF.length || 1)
    return { N, complete: true, selectedCount: N, fullRows: pickRows.length, kept: e.kept,
      rows, cost, poly: e.poly, evTiers: e.evTiers, dividend: e.dividend,
      divMin: e.divMin, divMax: e.divMax, topDividend: e.dividend[N] ?? null,
      modelOk, reduced: minDividend > 0, poolMap, turnover, expectedCorrect,
      evPayout: e.evPayout, ev: e.evPayout - cost,
      roi: cost ? (e.evPayout - cost) / cost : null, pAll: e.poly[N] || 0, rowMode: true }
  }
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

  // Enumerera kupongens rader och värdera dem. Utdelningsreducering: evalRows
  // hoppar över rader vars toppvinst-utdelning understiger minDividend.
  let modelOk = false, e = null
  if (complete && field > 0 && fullRows > 0 && fullRows <= 20000 && tiers.length) {
    const lists = matches.map((m) => (picks[m.event_number] || []).map((s) => ({
      fair: m.outcomes[s]?.fair_prob || 0,
      folk: folkProb(m.outcomes[s]),
    })))
    const rowFF = []
    const rec = (i, acc) => { if (i === N) { rowFF.push(acc); return } for (const o of lists[i]) rec(i + 1, [...acc, o]) }
    rec(0, [])
    e = evalRows(rowFF, tiers, field, N, minDividend, payouts?.product); modelOk = true
  }

  const poly = modelOk ? e.poly : gpoly.reduce((o, v, i) => { o[i] = v; return o }, {})
  const evTiers = modelOk ? e.evTiers : {}
  const dividend = modelOk ? e.dividend : {}
  const divMin = modelOk ? e.divMin : {}
  const divMax = modelOk ? e.divMax : {}
  const kept = modelOk ? e.kept : fullRows
  const evPayout = modelOk ? e.evPayout : 0
  const rows = modelOk ? kept : fullRows
  const cost = rows * rowPrice
  const pAll = modelOk ? (poly[N] || 0) : (gpoly[N] || 0)
  return { N, complete, selectedCount, fullRows, kept, rows, cost, poly, evTiers,
    dividend, divMin, divMax, topDividend: dividend[N] ?? null, modelOk, reduced: minDividend > 0,
    poolMap, turnover, expectedCorrect, evPayout, ev: evPayout - cost,
    roi: cost ? (evPayout - cost) / cost : null, pAll }
}

/* Värdera ett genererat system (matematiskt eller reducerat) över dess faktiska
   rader, så vi kan visa EV/ROI och utdelningens spann per strategi. */
function systemStats(sys, matches, payouts) {
  if (!sys || !matches?.length || !payouts?.available) return null
  const N = matches.length
  const rowPrice = payouts.row_price || sys.row_price || 1
  const ratio = payouts.ratio || 0
  // Samma värderingshorisont som byggaren använder i backend: prognostiserad
  // SLUTomsättning. Med live-omsättning tidigt i veckan blir både potter och
  // medvinnare för små, och den EV som visas blir glädjekalkyl.
  const turnover = payouts.projected_turnover || payouts.turnover || 0
  const field = turnover / rowPrice
  const jackpot = sys.jackpot ?? payouts.jackpot ?? 0
  const tiers = (payouts.tiers || []).map((t) => ({
    correct: t.correct,
    pool: turnover * ratio * (t.share || 0) + (t.correct === N ? jackpot : 0),
  }))
  if (!tiers.length || field <= 0) return null
  const byEv = {}; matches.forEach((m) => { byEv[m.event_number] = m })
  const picks = sys.picks || []
  let rowsSigns = sys.rows && sys.rows.length ? sys.rows : null
  if (!rowsSigns) {
    const lists = picks.map((p) => p.signs)
    const total = lists.reduce((a, l) => a * l.length, 1)
    if (total > 50000) return { tooBig: true, rows: sys.num_rows }
    rowsSigns = []
    const rec = (i, acc) => { if (i === lists.length) { rowsSigns.push(acc); return } for (const s of lists[i]) rec(i + 1, [...acc, s]) }
    rec(0, [])
  } else if (rowsSigns.length > 50000) {
    return { tooBig: true, rows: sys.num_rows }
  }
  const rowFF = rowsSigns.map((r) => r.map((s, i) => {
    const o = byEv[picks[i]?.event_number]?.outcomes?.[s] || {}
    return { fair: o.fair_prob || 0, folk: folkProb(o) }
  }))
  const e = evalRows(rowFF, tiers, field, N, 0, payouts?.product)
  const cost = rowsSigns.length * rowPrice
  const poolMap = {}; tiers.forEach((t) => { poolMap[t.correct] = t.pool })
  return { ...e, N, rows: rowsSigns.length, cost, poolMap, turnover,
    ev: e.evPayout - cost, roi: cost ? (e.evPayout - cost) / cost : null, pAll: e.poly[N] || 0 }
}

/* Liten tabell: lägsta/medel/högsta förväntad utdelning per vinstnivå. */
/* Omsättningen läses ur `s.turnover` — den som potterna FAKTISKT byggdes med.
   Tidigare skickades den in separat, och byggaren skickade live-omsättningen
   till en tabell vars potter kom ur prognosen: fottexten beskrev alltså ett
   annat underlag än raderna ovanför den. Basen härleds nu i stället genom att
   jämföra mot de två kända ankarna, så texten och talen inte kan gå isär. */
function PayoutTable({ s, tiers, payouts, jackpot }) {
  const effTurnover = s.turnover || 0
  const basis = effTurnover === payouts?.turnover ? 'live'
    : effTurnover === payouts?.projected_turnover ? 'prognostiserad slutomsättning'
      : 'justerad'
  return (
    <>
      <table className="grid compact paytable">
        <thead><tr>
          <th>Nivå</th><th>Prispott*</th><th>Förv. vinstrader</th>
          <th title="Om en av de mest spelade (favorit-tunga) raderna vinner — då delar flest på potten">Lägsta utd.</th>
          <th title="Sannolikhetsviktat snitt över systemets rader">Medel utd.</th>
          <th title="Om en av de minst spelade (skräll-)raderna vinner — då delar få på potten">Högsta utd.</th>
          <th>EV-bidrag</th>
        </tr></thead>
        <tbody>
          {tiers.map((t) => {
            const c = t.correct
            return (
              <tr key={c}>
                <td>{c} rätt</td>
                <td>{kr(s.poolMap?.[c])}</td>
                <td>{(s.poly?.[c] || 0).toFixed(3)}</td>
                <td>{kr(s.divMin?.[c])}</td>
                <td><b>{kr(s.dividend?.[c])}</b></td>
                <td>{kr(s.divMax?.[c])}</td>
                <td>{kr(s.evTiers?.[c] || 0)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="hint">*Prispott = omsättning ({kr(effTurnover)}, {basis})
        × Svenska Spels vinstplan{jackpot ? ` + jackpot ${kr(jackpot)}` : ''}. Lägsta/högsta = utdelningens
        spann beroende på om en favorit-tung eller skräll-rad vinner; medel är sannolikhetsviktat.
        Toppnivån bygger på radens exakta streckprodukt. Lägre nivåers medvinnare är en
        oberoende-streck-approximation och kan avvika när det faktiska matchutfallet är känt.</p>
    </>
  )
}

/* listar de överlevande raderna i radläget: exakta kombinationer, färgade efter
   teckenrang (favorit/utmanare/skräll), med sannolikhet + utdelning per rad och
   en sammanfattning av hur reduceringen slog per antal avvikelser från favoritraden. */
function RowExplorer({ rows, matches, payouts, turnover, jackpot }) {
  const [open, setOpen] = useState(false)
  const [showAll, setShowAll] = useState(false)
  if (!rows?.length || rows[0].length !== matches.length) return null
  const N = matches.length
  // teckenrang per match (0 = favorit, 1 = utmanare, 2 = skräll) för färgning
  const rank = matches.map((m) => {
    const order = ['1', 'X', '2'].sort((a, b) => (m.outcomes[b].fair_prob || 0) - (m.outcomes[a].fair_prob || 0))
    return { [order[0]]: 0, [order[1]]: 1, [order[2]]: 2 }
  })
  const rowPrice = payouts?.row_price || 1
  const field = turnover > 0 ? turnover / rowPrice : 0
  const ratio = payouts?.ratio || 0
  const topShare = payouts?.tiers?.find((t) => t.correct === N)?.share || 0
  const pool = turnover * ratio * topShare + (jackpot || 0)
  const data = rows.map((r) => {
    let p = 1, q = 1, dev = 0
    r.forEach((s, i) => {
      const o = matches[i].outcomes[s] || {}
      p *= o.fair_prob || 0
      q *= folkProb(o)
      if (rank[i][s] !== 0) dev++
    })
    const div = field > 0 ? Math.min(pool, pool / (field * q + 1)) : null
    return { r, p, dev, div }
  }).sort((a, b) => b.p - a.p)
  // sammanfattning: överlevande rader per antal avvikelser från favoritraden
  const byDev = {}
  data.forEach((d) => { byDev[d.dev] = (byDev[d.dev] || 0) + 1 })
  const shown = showAll ? data.slice(0, 512) : data.slice(0, 60)
  return (
    <div className="rowx">
      <button className="legend-toggle" onClick={() => setOpen(!open)}>
        🔍 Visa de {rows.length} överlevande raderna {open ? '▲' : '▼'}
      </button>
      {open && (
        <>
          <div className="rowx-sum">
            Så slog reduceringen — rader kvar per antal avvikelser från favoritraden:{' '}
            {Object.keys(byDev).sort((a, b) => a - b).map((d, i) => (
              <span key={d} className="rowx-dev">{i > 0 ? ' · ' : ''}{d} avv: <b>{byDev[d]}</b> rader</span>
            ))}
          </div>
          <div className="rowx-grid">
            <div className="rowx-row rowx-head">
              <span className="rowx-signs">rad (sorterad efter sannolikhet)</span>
              <span>chans alla rätt</span><span>utd. om rätt</span>
            </div>
            {shown.map((d, i) => (
              <div key={i} className="rowx-row">
                <span className="rowx-signs">
                  {d.r.map((s, j) => <em key={j} className={`rx-${rank[j][s]}`}>{s}</em>)}
                </span>
                <span>{pct(d.p)}</span>
                <span>{d.div != null ? kr(d.div) : '–'}</span>
              </div>
            ))}
          </div>
          {data.length > shown.length && (
            <button className="legend-toggle" onClick={() => setShowAll(true)}>
              … visa fler ({data.length - shown.length} till, max 512)
            </button>
          )}
          <p className="hint">Färger: <em className="rx-0">favorittecken</em> ·{' '}
            <em className="rx-1">utmanare</em> · <em className="rx-2">skräll</em>. Samma
            färglogik tonas in i analystabellen ovan (×N = antal rader som använder tecknet).</p>
        </>
      )}
    </div>
  )
}

function CouponPanel({ matches, picks, pickRows, payouts, product, draw, onClear,
  buildConfig = null }) {
  const [redOn, setRedOn] = useState(false)
  const [minDiv, setMinDiv] = useState(50)
  const [turnover, setTurnover] = useState(null)   // null = använd live-omsättning
  const [jackpotOverride, setJackpotOverride] = useState(null)
  const [copied, setCopied] = useState(false)
  const [bankroll, setBankroll] = useState(() => {
    try { return Number(localStorage.getItem('svs_bankroll')) || 5000 } catch { return 5000 }
  })
  useEffect(() => { try { localStorage.setItem('svs_bankroll', String(bankroll)) } catch { /* ok */ } }, [bankroll])
  // Jackpott och omsättningsöverstyrning hör till OMGÅNGEN, inte till panelen.
  //
  // Effekten synkade tidigare bara UPPÅT (`if (payouts?.jackpot > 0)`), så ett
  // byte till ett spel utan jackpott lämnade föregående spels rullpott kvar i
  // state: Europatipsets 2,5 Mkr följde med in i Topptipset, vars hela
  // omsättning är 42 563 kr — toppotten blåstes upp ~59 gånger och tog
  // EV/ROI-prognosen med sig. `turnover` bar exakt samma fel: en `→ prognos`
  // på Europatipset (4,3 Mkr) värderade sedan Topptipsetkupongen mot den.
  //
  // Nyckeln är omgången, inte värdet. Matchar inte payloaden produkten vi
  // står på är den ännu inte omhämtad, och då är noll rätt svar — ett
  // kvarhängande belopp från förra spelet är farligare än en sekund utan.
  // En manuell justering inom samma omgång står kvar tills omgången byts.
  const payoutsMatchSelection = payoutMatchesSelection(payouts, product, draw)
  // Panelen är key:ad på produkt+omgång i AppV3 och remountas vid byte. Då
  // behövs inga setState-effekter för återställning: grundvärdet följer det
  // verifierade svaret och manuella overrides lever bara i denna omgång.
  const jackpot = jackpotOverride ?? (
    payoutsMatchSelection && payouts?.jackpot > 0 ? payouts.jackpot : 0)
  const copyCoupon = () => {
    // radläge: kopiera de faktiska raderna (en per rad) — teckenunionen per
    // match säger inget om vilka rader som faktiskt spelas
    const txt = (pickRows && pickRows.length)
      ? pickRows.map((r) => r.join('')).join('\n')
      : matches.map((m) => `${m.event_number}. ${m.description}: ${(picks[m.event_number] || []).join('')}`).join('\n')
    navigator.clipboard?.writeText(txt); setCopied(true); setTimeout(() => setCopied(false), 2000)
  }
  // Bokför att ANVÄNDAREN själv lämnat in kupongen. Lägger inga spel — den ger
  // facit per kupong (mot publicerad utdelning, inte kontrafaktisk utspädning)
  // och livestatus för reducerade system medan omgången pågår.
  const [played, setPlayed] = useState(null)
  const playedStatus = played?.rows === pickRows ? played.status : false
  const markPlayed = async () => {
    const submittedRows = pickRows
    setPlayed({ rows: submittedRows, status: 'sparar' })
    try {
      const res = await fetch('/api/pool/played', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product, draw_number: draw,
          rows: pickRows.map((r) => r.join('')),
          row_price: payouts?.row_price || 1,
          events_order: matches.map((m) => m.event_number),
          // build_kind var förr hårdkodat 'kupong' och strategy/budget/vikt
          // skickades aldrig, trots att kolumnerna fanns — bokförda kuponger
          // gick därför inte att koppla till förslaget de byggde på.
          build_kind: buildConfig?.source || 'kupong',
          strategy: buildConfig?.strategy ?? null,
          budget: buildConfig?.budget ?? null,
          value_weight: buildConfig?.value_weight ?? null,
          label: `${product} ${draw}`,
        }),
      })
      setPlayed({ rows: submittedRows, status: res.ok })
      if (!res.ok) alert('Kunde inte bokföra kupongen — se backend-loggen.')
    } catch {
      setPlayed({ rows: submittedRows, status: false })
      alert('Kunde inte nå backend.')
    }
  }
  const egnaUrl = egnaRaderUrl(product)
  const rowMode = !!(pickRows && pickRows.length)
  const couponGroups = matches.map((m) => picks[m.event_number] || [])
  const nRows = rowMode ? pickRows.length
    : couponGroups.reduce((a, g) => a * (g.length || 1), 1)
  const downloadEgna = () => {
    if (nRows > 50000) { alert(`Systemet är för stort (${nRows} rader) för filexport.`); return }
    const rows = rowMode ? pickRows : cartesianRows(couponGroups)
    downloadText(`${product}_omg${draw}_egnarader.txt`, egnaRaderText(product, draw, rows))
  }
  const effTurnover = turnover != null ? turnover : (payouts?.turnover || 0)
  const s = couponStats(matches, picks, payouts, redOn ? minDiv : 0, turnover, jackpot, pickRows)
  const payTiers = (payouts?.tiers || []).filter((t) => t.correct != null).sort((a, b) => b.correct - a.correct)
  return (
    <div className="coupon">
      <div className="coupon-actions">
        <button onClick={onClear}>Rensa</button>
        <span className="cstatus">
          {s.rowMode
            ? `${s.fullRows} utvalda rader från förslaget (inte alla kombinationer) — klicka tecken i tabellen för att bygga om manuellt`
            : `${s.selectedCount}/${s.N} matcher valda${!s.complete
              ? ' — klicka tecken i analystabellen, eller bygg ett förslag och tryck "Lägg i kupongen"' : ''}`}
        </span>
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
                    onChange={(e) => setJackpotOverride(Number(e.target.value) * 1e6)} />
                </label>
                {payouts?.projected_turnover > (payouts?.turnover || 0) && turnover !== payouts.projected_turnover && (
                  <button onClick={() => setTurnover(payouts.projected_turnover)}
                    title="Räkna EV/utdelning mot förväntad slutomsättning (median av senaste omgångarna) i stället för nuvarande — den ärliga siffran tidigt i veckan.">
                    → prognos ({kr(payouts.projected_turnover)})</button>
                )}
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
          {s.modelOk && (() => {
            // Kelly via mean-variance-approximation över ALLA vinstnivåer:
            // f* ≈ (E[R] − 1) / Var(R), R = utbetalning/insats. (Binär topp-
            // vinst-Kelly gav ~0 % — den ignorerade 10/11/12-rätt-nivåerna.)
            const C = s.cost
            const ER = C > 0 ? s.evPayout / C : 0
            const varR = C > 0 ? Object.keys(s.evTiers || {}).reduce((a, c) => {
              const p = s.poly?.[c] || 0
              const d = s.dividend?.[c] || 0
              return a + p * Math.pow(d / C, 2)
            }, 0) - Math.pow(ER, 2) : 0
            const f = ER > 1 && varR > 0 ? Math.min(0.5, (ER - 1) / varR) : -1
            return (
              <div className="kellybox" title="Kelly-kriteriet: andel av bankrullen som maximerar långsiktig tillväxt. Approximation över alla vinstnivåer (f ≈ överavkastning ÷ varians). Kvarts-Kelly rekommenderas — full Kelly är väldigt volatil. Tips: tryck '→ prognos' ovan så räknas det mot förväntad slutomsättning.">
                <span>📐 Kelly:</span>
                {f > 0 ? (
                  <>
                    kvarts-Kelly <b>{(f / 4 * 100) >= 0.1 ? (f / 4 * 100).toFixed(2) : (f / 4 * 100).toPrecision(2)} %</b> av bankrullen
                    <label> bankrulle <input type="number" min="0" step="500" value={bankroll}
                      onChange={(e) => setBankroll(Math.max(0, Number(e.target.value)))} /> kr</label>
                    → insats ≈ <b className={f / 4 * bankroll >= s.cost ? 'pos' : 'neg'}>
                      {f / 4 * bankroll < 10 ? (f / 4 * bankroll).toFixed(2) + ' kr' : kr(f / 4 * bankroll)}</b>
                    <span className="hint"> (kupongen kostar {kr(s.cost)}). OBS: jackpott-utdelningar är
                      extremvarians — Kelly blir alltid en liten andel i poolspel; använd den som
                      relativ mätare mellan omgångar snarare än exakt insats.</span>
                  </>
                ) : (
                  <span className="hint"> negativ förväntad avkastning vid dessa siffror — Kelly säger avstå/minska. Prova "→ prognos" för ärligare omsättning.</span>
                )}
              </div>
            )
          })()}
          {payouts?.available && s.modelOk && (
            <PayoutTable s={s} tiers={payTiers} payouts={payouts} jackpot={jackpot} />
          )}
          {s.rowMode && (
            <RowExplorer rows={pickRows} matches={matches} payouts={payouts}
              turnover={effTurnover} jackpot={jackpot} />
          )}
          <div className="svs-row">
            <a className="svs-link" href={svsUrl(product, draw)} target="_blank" rel="noreferrer">▶ Öppna omgången på Svenska Spel ↗</a>
            {egnaUrl && <button onClick={downloadEgna} title={`Laddar ner ${nRows} rader som .txt i Svenska Spels Egna rader-format`}>⬇ Egna rader-fil ({nRows} rad{nRows === 1 ? '' : 'er'})</button>}
            <button onClick={copyCoupon} title={rowMode ? 'Kopierar alla rader, en per rad' : 'Kopierar valda tecken per match'}>
              {copied ? '✓ Kopierad' : rowMode ? `Kopiera ${nRows} rader` : 'Kopiera kupong'}</button>
            {rowMode && pickRows.length > 0 && (
              <button className={playedStatus ? 'playedbtn on' : 'playedbtn'}
                onClick={markPlayed} disabled={playedStatus === 'sparar'}
                title="Bokför att DU har lämnat in den här kupongen hos Svenska Spel. Inget spel läggs härifrån — knappen ger facit per kupong och livestatus för reducerade system under omgången.">
                {playedStatus === true ? '✓ Bokförd som spelad'
                  : playedStatus === 'sparar' ? 'Sparar…' : '🎟 Markera som spelad'}</button>
            )}
          </div>
          {egnaUrl ? (
            <p className="hint">Ladda ner filen och ladda upp den hos{' '}
              <a className="extlink" href={egnaUrl} target="_blank" rel="noreferrer">Svenska Spel · Externa systemspel ↗</a>
              {' '}(Egna rader). Du väljer omgång och betalar själv där — av säkerhetsskäl lämnas inga spel automatiskt.</p>
          ) : (
            <p className="hint">Egna rader-filuppladdning stödjer inte {product}. Öppna omgången, klistra in{' '}
              <button className="linkbtn" onClick={copyCoupon}>{copied ? '✓ kopierad' : 'kopierad kupong'}</button> och fyll i själv.</p>
          )}
        </>
      )}
    </div>
  )
}

/* Spelade kuponger: facit per kupong + LIVESTATUS för reducerade system.
   Facitet räknas mot PUBLICERAD utdelning (kupongen låg i potten, så beloppen
   inkluderar den) — inte mot PH3:s kontrafaktiska utspädning. */
// "topptipsetstryk 974" säger ingenting. Produktnamn + variant + omgång gör.
const PRODUCT_LABEL = {
  stryktipset: 'Stryktipset', europatipset: 'Europatipset',
  topptipset: 'Topptipset', topptipsetstryk: 'Topptipset',
  topptipsetextra: 'Topptipset', bomben: 'Bomben',
}
function couponLabel(c) {
  const base = PRODUCT_LABEL[c.product] || c.product
  const variant = VARIANT[c.product]
  return `${base}${variant ? ` ${variant}` : ''} · omgång ${c.draw_number}`
}
function couponDate(c) {
  if (!c?.draw_close) return 'datum saknas'
  const date = new Date(c.draw_close)
  if (Number.isNaN(date.getTime())) return 'datum saknas'
  return date.toLocaleDateString('sv-SE', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}

/* Liverättningen: matcherna i kupongordning med ställning, mitt tecken och —
   för de som är kvar — vilket resultat som håller flest rader vid liv.
   Aggregaten under (bäst X rätt, chans per nivå) säger VAD som hänt men aldrig
   VILKEN match det gäller, och utan den kopplingen gick kupongen inte att följa
   medan omgången pågick. */
function LiveScorecard({ live }) {
  const matches = live?.matches || []
  if (!matches.length) return null
  const cheerByCol = Object.fromEntries((live.cheer || []).map((c) => [c.col, c]))
  const topLevel = live.cheer?.[0]?.top_level ?? live.n_events

  return (
    <table className="grid compact liverattning">
      <thead>
        <tr>
          <th>#</th><th>Match</th><th>Ställning</th>
          <th title="Kupongens tecken i den här matchen och hur många rader som har vardera.">Mina rader</th>
          <th title={`Hur många rader som fortfarande kan nå ${topLevel} rätt om matchen slutar så.`}>Heja på</th>
        </tr>
      </thead>
      <tbody>
        {matches.map((m) => {
          const cheer = cheerByCol[m.col]
          const label = m.description || `${m.home || '?'} – ${m.away || '?'}`
          /* Struken match: SvS fastställer tecknet i settlementet, så den
             håller alla tecken öppna tills dess — aldrig "rätt för alla". */
          /* Poolen fastställs på ordinarie 90 min, så en match i förlängning
             är klar för kupongen men inte klar som match. Båda ska sägas. */
          const status = m.cancelled ? 'struken'
            : m.extra_time ? `ordinarie klar · ${m.status_text || 'förlängning'}`
              : m.final ? 'slut'
                : m.in_progress ? (m.status_text || 'spelas')
                  : 'ej start'
          return (
            <tr key={m.col} className={m.final ? 'decided' : ''}>
              <td className="hint">{m.col}</td>
              <td>
                <span className="lr-team">{label}</span>
                <span className={`lr-status${m.extra_time ? ' warn' : ''}`}>{status}</span>
              </td>
              <td>
                <b>{m.score || '–'}</b>
                {m.sign && (
                  <span className={`lr-sign${m.final ? ' final' : ''}`}>{m.sign}</span>
                )}
                {/* Matchen är avgjord för kupongen, men utan Fulltime eller
                    Overtime går ordinarie tid inte att skilja från Current. */}
                {m.sign_provisional && (
                  <span className="lr-prov" title="Matchen är i förlängning och räknas som klar — poolen fastställs på ordinarie 90 minuter. Svenska Spel har dock inte publicerat ordinarie tids resultat än, så ställningen här kan innehålla förlängningsmål. Tecknet rättas automatiskt när slutresultatet kommer.">*</span>
                )}
              </td>
              <td className="lr-mine">
                {['1', 'X', '2'].map((s) => {
                  const n = m.row_signs?.[s]
                  if (!n) return null
                  // Rätt så långt = grönt, fällt = utgråat. Under pågående
                  // match är det preliminärt och får inte se ut som facit.
                  const tone = !m.sign ? '' : s === m.sign
                    ? (m.final ? ' hit' : ' leading') : (m.final ? ' miss' : '')
                  return (
                    <span key={s} className={`lr-chip${tone}`}
                      title={`${n} rader har ${s}`}>{s}<i>{n}</i></span>
                  )
                })}
              </td>
              <td>
                {cheer?.best
                  ? <span className="lr-cheer" title={`1: ${cheer.signs['1'].top} · X: ${cheer.signs.X.top} · 2: ${cheer.signs['2'].top} rader kvar till ${topLevel} rätt`}>
                      <b>{cheer.best}</b><i>{cheer.signs[cheer.best].top}</i>
                    </span>
                  : cheer
                    ? <span className="hint" title="Alla tre utfallen lämnar lika många rader med chans — matchen avgör ingenting för den här kupongen.">spelar ingen roll</span>
                    : <span className="hint">–</span>}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/* Ett pågående system i siffror: hur långt raderna kommit och vad oddsen på
   de kvarvarande matcherna säger om chansen per vinstnivå. Sannolikheterna
   räknas i backend över HELA utfallsrummet — raderna delar ju matcher, så en
   produkt av per-rad-chanser hade varit fel. */
function PlayedLiveCard({ c, onForget }) {
  const live = c.live
  /* Exakt noll är noll. "<0,1%" om ett utfall som är uteslutet läste som en
     liten men verklig chans, och gjorde intervallets underkant obegriplig. */
  const pct = (p) => p === 0 ? '0%'
    : p >= 0.1 ? `${(p * 100).toFixed(0)}%`
      : p >= 0.001 ? `${(p * 100).toFixed(1)}%` : '<0,1%'
  const levels = live ? Object.keys(live.alive_per_level)
    .map(Number).sort((a, b) => b - a) : []
  return (
    <div className="playedcard">
      <div className="playedcard-head">
        <b>{couponLabel(c)}</b>
        <span className="hint" title="Omgångens spelstopp">{couponDate(c)}</span>
        {/* "pågår" på en omgång där varje match är spelad är osant — den
            väntar bara på att SvS publicerar utdelningen. Gårdagens
            Topptipset låg kvar som aktiv av precis det skälet. */}
        {live?.all_decided
          ? <span className="epill" title="Alla matcher är avgjorda. Kupongen får facit när Svenska Spel publicerar utdelningen.">
              avgjord · väntar på utdelning</span>
          : <span className="epill live">pågår</span>}
        <span className="hint">{c.n_rows} rader · {kr(c.cost_kr)}</span>
        <button className="linkbtn" onClick={onForget}
          title="Ta bort felaktigt bokförd kupong (går bara innan facit satts)">✕</button>
      </div>
      {!live && (
        <p className="hint">{c.live_pending
          ? 'Hämtar livestatus…'
          : c.live_error
          ? <span title={c.live_error}>Livestatus tillfälligt otillgänglig — försöker igen automatiskt inom en minut.</span>
          : 'Väntar på omgångens första resultat.'}</p>
      )}
      {live && (
        <>
          <div className="playedcard-sum">
            <span><b>{live.n_decided}</b>/{live.n_events} avgjorda</span>
            <span>bäst <b>{live.best_secure}</b> rätt</span>
            {/* Max nåbart är ren aritmetik och finns även när en livemarknad
                är avstängd — det är ofta den enda siffra som betyder något. */}
            {live.max_possible != null && (
              <span className={live.out_of_contention ? 'neg' : ''}
                title="Bästa antal rätt någon rad fortfarande kan nå: säkrade rätt plus alla oavgjorda matcher.">
                max <b>{live.max_possible}</b> möjligt
              </span>
            )}
            {live.chance_open_matches != null && (
              <span className="hint">{live.chance_open_matches} matcher kvar</span>
            )}
          </div>
          <LiveScorecard live={live} />
          {live.out_of_contention && (
            <p className="playedcard-dead">
              Kupongen kan inte längre nå någon vinstnivå — bästa raden kan som
              mest få <b>{live.max_possible}</b> rätt och lägsta redovisade
              nivå är {Math.min(...levels)}.
            </p>
          )}
          {!live.out_of_contention && <table className="grid compact playedlevels">
            <thead><tr><th>nivå</th><th>rader kvar</th><th>chans</th></tr></thead>
            <tbody>
              {levels.map((lvl) => {
                const alive = live.alive_per_level[lvl]
                /* En förlängningsmatch utan publicerad ordinarie tid gör
                   radantalet till ett spann, inte ett faktum. */
                const aLo = live.alive_min_per_level?.[lvl]
                const aHi = live.alive_max_per_level?.[lvl]
                const aliveText = aLo != null && aLo !== aHi
                  ? `${aLo}–${aHi}` : (alive || '–')
                const p = live.chance_per_level?.[lvl]
                // Saknar en match pris finns ingen punktskattning, bara ett
                // intervall betingat på hur den matchen går.
                const lo = live.chance_min_per_level?.[lvl]
                const hi = live.chance_max_per_level?.[lvl]
                const text = !alive ? '0%'
                  : p != null ? pct(p)
                    : lo != null ? (lo === hi ? pct(lo) : `${pct(lo)}–${pct(hi)}`)
                      : '–'
                return (
                  <tr key={lvl} className={(aHi ?? alive) ? '' : 'dead'}>
                    <td><b>{lvl} rätt</b></td>
                    <td title={aLo != null && aLo !== aHi
                      ? `Beror på hur ordinarie tid slutade i ${live.alive_unproven?.join(', ')}. Svenska Spel har inte publicerat den än.`
                      : undefined}>{aliveText}</td>
                    <td className={(p ?? lo) >= 0.5 ? 'pos' : ''}
                      title={p == null && lo != null
                        ? 'Intervall: chansen beroende på hur de oprissatta matcherna går. Ingen sannolikhet gissas åt dem.'
                        : undefined}>{text}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>}
          <p className="hint">
            {live.chance_note ? `Ingen chans visas: ${live.chance_note}.`
              : live.chance_unpriced?.length
                ? <>Chansen visas som <b>intervall</b>: {live.chance_unpriced.join(', ')} saknar
                  öppet pris, så siffran ges för alla utfall den matchen kan få —
                  <b> underkanten förutsätter att den går emot dina rader</b>, även
                  när ställningen säger annat. Ingen sannolikhet gissas åt den;
                  bedöm ställningen själv.</>
              : <>
                {live.chance_basis === 'simulerad'
                  ? 'Chans simulerad ur oddsen på kvarvarande matcher (för många kombinationer för exakt uppräkning).'
                  : 'Chans räknad exakt ur oddsen på kvarvarande matcher.'}
                {live.chance_live_matches > 0 && <> <b>{live.chance_live_matches} pågående
                  {live.chance_live_matches === 1 ? ' match' : ' matcher'} prissatta live</b> —
                  ställningen är alltså inräknad.</>}
              </>}
          </p>
        </>
      )}
    </div>
  )
}

// `product` = null visar alla spel; annars filtreras allt till ett. Summeringen
// räknas om på det filtrerade urvalet — en ROI som gäller alla spel får inte
// stå kvar som rubrik när tabellen bara visar ett.
function PlayedPanel({ product = null }) {
  const [data, setData] = useState(null)
  const load = useCallback(() => {
    const stamp = Date.now()
    fetch(`/api/pool/played?live=false&_t=${stamp}`, { cache: 'no-store' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((local) => {
        const hasOpen = (local.coupons || []).some((coupon) => !coupon.settled_at)
        setData({
          ...local,
          coupons: (local.coupons || []).map((coupon) => (
            !coupon.settled_at && hasOpen ? { ...coupon, live_pending: true } : coupon
          )),
        })
        if (hasOpen) {
          fetch(`/api/pool/played?_t=${stamp}`, { cache: 'no-store' })
            .then((r) => {
              if (!r.ok) throw new Error(`HTTP ${r.status}`)
              return r.json()
            })
            .then(setData)
            .catch((error) => setData((current) => current ? {
              ...current,
              coupons: (current.coupons || []).map((coupon) => (
                coupon.settled_at ? coupon : {
                  ...coupon,
                  live_pending: false,
                  live_error: error?.name || 'FetchError',
                }
              )),
            } : current))
        }
      })
      .catch(() => setData((current) => current || { coupons: [] }))
  }, [])
  useEffect(() => {
    load()
    const timer = window.setInterval(load, 60_000)
    return () => window.clearInterval(timer)
  }, [load])
  if (!data) return <LoadingState label="Hämtar spelade kuponger…" />
  const all = data.coupons || []
  const coupons = product ? all.filter((c) => c.product === product) : all
  const settled = coupons.filter((c) => c.settled_at)
  const spent = settled.reduce((a, c) => a + (c.cost_kr || 0), 0)
  const won = settled.reduce((a, c) => a + (c.payout_kr || 0), 0)
  const s = product
    ? { n_coupons: coupons.length, n_settled: settled.length,
        n_open: coupons.length - settled.length, spent_kr: spent, won_kr: won,
        roi: spent > 0 ? won / spent - 1 : null }
    : (data.summary || {})
  if (!coupons.length) {
    return <p className="hint">{all.length
      ? 'Inga bokförda kuponger för det här spelet.'
      : <>Inga bokförda kuponger än. Bygg ett förslag, lämna in det
        hos Svenska Spel och tryck <b>🎟 Markera som spelad</b> i kupongen — då följs
        reducerade system live och får riktigt facit när omgången är klar.</>}</p>
  }
  const forget = async (id) => {
    await fetch(`/api/pool/played/${id}`, { method: 'DELETE' }); load()
  }
  // Pågående kuponger är det man faktiskt följer — de får egna kort överst.
  // Avgjorda är arkiv och komprimeras till en rad var.
  const open_ = coupons.filter((c) => !c.settled_at)
  const done = settled
  return (
    <div className="playedbox">
      <p className="hint" title={s.note}>
        {s.n_coupons} kuponger · {s.n_settled} med facit · {s.n_open} öppna
        {s.n_settled > 0 && <> · satsat {kr(s.spent_kr)} · tillbaka {kr(s.won_kr)}
          {s.roi != null && <> · ROI <b className={s.roi >= 0 ? 'pos' : 'neg'}>
            {(s.roi * 100).toFixed(1)}%</b></>}</>}
      </p>
      {open_.length > 0 && (
        <div className="playedlive">
          {open_.map((c) => (
            <PlayedLiveCard key={c.id} c={c} onForget={() => forget(c.id)} />
          ))}
        </div>
      )}
      {done.length > 0 && (
        <>
          {open_.length > 0 && <div className="playeddivider">avgjorda</div>}
          <SortableTable id="played-done" className="grid compact playeddone"
            wrapperClassName="tablewrap"
            defaultSort={{ key: 'draw_close', dir: 'desc' }}
            rows={done}
            columns={[
              { key: 'product', label: 'Spel', defaultDir: 'asc',
                value: (c) => `${PRODUCT_LABEL[c.product] || c.product}`
                  + `${VARIANT[c.product] ? ` ${VARIANT[c.product]}` : ''}` },
              { key: 'draw_number', label: 'Omgång' },
              { key: 'draw_close', label: 'Datum',
                title: 'Datum för omgångens spelstopp' },
              { key: 'build', label: 'Förslagstyp', defaultDir: 'asc',
                title: 'Byggarens inställningar när kupongen bokfördes. Kuponger före 2026-08-05 saknar uppgiften.',
                value: (c) => (c.budget != null
                  ? `${c.strategy || ''} ${c.budget}` : '') },
              { key: 'n_rows', label: 'Rader' },
              { key: 'cost_kr', label: 'Kostnad' },
              { key: 'correct_max', label: 'Bäst rätt' },
              { key: 'payout_kr', label: 'Utdelning' },
              { key: 'roi', label: 'ROI' },
            ]}
            renderRow={(c) => (
              <tr key={c.id}>
                <td>{PRODUCT_LABEL[c.product] || c.product}
                  {VARIANT[c.product] ? ` ${VARIANT[c.product]}` : ''}</td>
                <td>{c.draw_number}</td>
                <td>{couponDate(c)}</td>
                <td>{c.budget != null
                  ? <span className="buildbadge">{[
                    `${Math.round(c.budget)} kr`,
                    c.strategy,
                    c.value_weight != null
                      ? `värde ${Math.round(c.value_weight * 100)} %` : null,
                  ].filter(Boolean).join(' · ')}</span>
                  : <span className="hint" title="Budget, strategi och
                    värdevikt började sparas på kupongen 2026-08-05. Äldre
                    kuponger bär dem inte, och uppgiften bakfylls aldrig —
                    den fanns helt enkelt inte när kupongen bokfördes.">
                    ej sparad före 2026-08-05</span>}</td>
                <td>{c.n_rows}</td>
                <td>{kr(c.cost_kr)}</td>
                <td>bäst {c.correct_max} rätt</td>
                <td>{c.payout_complete ? kr(c.payout_kr) : 'ofullständig'}</td>
                <td className={c.roi == null ? '' : c.roi >= 0 ? 'pos' : 'neg'}>
                  {c.roi == null ? '–'
                    : `${c.roi >= 0 ? '+' : ''}${Math.round(c.roi * 100)} %`}</td>
              </tr>
            )} />
        </>
      )}
    </div>
  )
}

/* Steam: devigade sannolikhetsskift (procentenheter) över 6/24/72 h.
   Jämförbart mellan favoriter och skrällar — det rå oddsrörelse inte är. */
function SteamPanel({ product, draw, matches }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    if (!draw) return undefined
    let current = true
    fetch(`/api/steam?product=${product}&draw=${draw}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { if (current) setData(d) })
      .catch(() => { if (current) setData(null) })
    return () => { current = false }
  }, [product, draw])
  const desc = {}
  ;(matches || []).forEach((m) => { desc[m.event_number] = m.description })
  const rows = (data?.rows || []).filter((r) => r.primary != null && Math.abs(r.primary) >= 1).slice(0, 10)
  const cell = (v) => v == null ? <td>–</td>
    : <td className={v > 0 ? 'pos' : v < 0 ? 'neg' : ''}>{v > 0 ? '+' : ''}{v} pp</td>
  if (!data) return <div className="loading sm">Hämtar steam…</div>
  if (!rows.length) return <p className="hint">Inga devigade skift ≥ 1 pp ännu — fylls på när sharp-serien växer.</p>
  return (
    <div className="steam">
      <p className="hint">Devigad Pinnacle-sannolikhet nu jämfört med för 6/24/72 h sedan.
        Stora positiva skift = marknaden backar tecknet på riktigt (🔥-flaggan triggas på +{'3,5'} pp).</p>
      <table className="grid compact steam-table">
        <thead><tr><th>Match</th><th>Tecken</th><th>Sannolikhet nu</th><th>Δ 6 h</th><th>Δ 24 h</th><th>Δ 72 h</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="match">{desc[r.event_number] || `Match ${r.event_number}`}</td>
              <td className="signs">{r.sign}</td>
              <td>{Math.round(r.p_now * 100)} %</td>
              {cell(r.pp['6'])}{cell(r.pp['24'])}{cell(r.pp['72'])}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* Signal-facit: visar om våra flaggade värdetecken slår stängningslinjen (CLV)
   och hur ofta de går in. Fylls på automatiskt av bakgrundsinsamlingen. */
function ClvPanel({ group }) {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    let current = true
    fetch(`/api/clv?product=${group}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { if (current) setData(d) })
      .catch(() => { if (current) setData(null) })
    return () => { current = false }
  }, [group])
  if (!data) return <div className="loading sm">Hämtar facit…</div>
  const p100 = (v) => (v == null ? '–' : Math.round(v * 100) + ' %')
  const clvCls = data.avg_clv_pp > 0 ? 'pos' : data.avg_clv_pp < 0 ? 'neg' : ''
  return (
    <div className="clv">
      <div className="clv-sum">
        <span>flaggade tecken <b>{data.n_flagged}</b></span>
        <span title="Closing Line Value: devigad Pinnacle-stängning minus sannolikheten när vi flaggade. Positivt över många flaggor = vi hittar värdet före marknaden.">
          snitt-CLV <b className={clvCls}>{data.avg_clv_pp == null ? '–' : (data.avg_clv_pp > 0 ? '+' : '') + data.avg_clv_pp + ' pp'}</b></span>
        <span>slog stängningen <b>{p100(data.beat_pct)}</b>{data.n_scored ? ` (n=${data.n_scored})` : ''}</span>
        <span>gick in <b>{p100(data.hit_pct)}</b>{data.n_judged ? ` (n=${data.n_judged})` : ''}</span>
      </div>
      {data.n_flagged === 0 ? (
        <p className="hint">Inga flaggor loggade än — bakgrundsinsamlingen börjar logga gröna
          värdetecken och sharp-edges från och med nu, och facit fylls på när matcherna avgörs.</p>
      ) : (
        <>
          <button className="legend-toggle" onClick={() => setOpen(!open)}>
            {open ? '▲ Dölj' : '▼ Visa'} flaggorna
          </button>
          {open && (
            <table className="grid compact clv-table">
              <thead><tr><th>Match</th><th>Tecken</th><th>Typ</th><th>Flagg-P</th><th>Stängning</th><th>CLV</th><th>Utfall</th></tr></thead>
              <tbody>
                {data.rows.slice(0, 40).map((r, i) => (
                  <tr key={i}>
                    <td className="match">{r.description}
                      <div className="league">{r.product} omg {r.draw_number}</div></td>
                    <td className="signs">{r.sign}</td>
                    <td>{r.flag_type}</td>
                    <td>{r.first_prob != null ? Math.round(r.first_prob * 100) + ' %' : '–'}</td>
                    <td>{r.closing_prob != null ? Math.round(r.closing_prob * 100) + ' %' : (r.closing_note || 'väntar…')}</td>
                    <td className={r.clv_pp > 0 ? 'pos' : r.clv_pp < 0 ? 'neg' : ''}>
                      {r.clv_pp != null ? (r.clv_pp > 0 ? '+' : '') + r.clv_pp + ' pp' : '–'}</td>
                    <td>{r.outcome == null ? '–' : r.outcome ? '✓' : '✗'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

/* Bomben: exakt-resultat-spel utan SvS-odds. En match = en resultat-heatmap där
   värde = vår Poisson-målmodell (Pinnacle förv. mål) mot folkets fördelning. */
function BombenMatch({ m }) {
  const G = 5   // visa 0..5 mål per lag (svansen är försumbar)
  const at = (h, a) => m.grid.find((g) => g.h === h && g.a === a) || {}
  const tint = (g) => {
    if (g.ratio == null) return undefined
    // Extrem kvot på ett nästan omöjligt resultat ska inte lysa starkare än ett
    // spelbart utfall. Sannolikheten dämpar bara färgen; kvoten visas oförändrad.
    const probabilityWeight = Math.min(1, Math.sqrt((g.model || 0) / 0.05))
    if (g.ratio >= 1.05) return `rgba(61,220,132,${(Math.min(0.55, (g.ratio - 1) * 0.5) * (0.25 + probabilityWeight * 0.75)).toFixed(2)})`
    if (g.ratio <= 0.95) return `rgba(224,107,107,${(Math.min(0.55, (1 - g.ratio) * 0.6) * (0.25 + probabilityWeight * 0.75)).toFixed(2)})`
    return undefined
  }
  const practical = [...(m.top_value || [])]
    .sort((a, b) => (b.model || 0) * Math.max(0, (b.ratio || 1) - 1)
      - (a.model || 0) * Math.max(0, (a.ratio || 1) - 1))
    .slice(0, 4)
  return (
    <div className="bmatch">
      <div className="bmatch-head">
        <strong>{m.description}</strong>
        {m.has_model
          ? <span className="muted"> · förv. mål {m.home_xg?.toFixed(2)}–{m.away_xg?.toFixed(2)}{m.matched ? ` · Pinnacle: ${m.matched}` : ''}</span>
          : <span className="st-miss"> · ingen sharp-modell – visar bara folket</span>}
      </div>
      <div className="bgrid-wrap">
        <table className="bgrid">
          <thead><tr><th className="corner">H\B</th>{Array.from({ length: G + 1 }, (_, a) => <th key={a}>{a}</th>)}</tr></thead>
          <tbody>
            {Array.from({ length: G + 1 }, (_, h) => (
              <tr key={h}><th>{h}</th>
                {Array.from({ length: G + 1 }, (_, a) => {
                  const g = at(h, a)
                  return (
                    <td key={a} style={{ background: tint(g) }}
                      title={`${h}–${a}: folk ${((g.folk || 0) * 100).toFixed(1)} %`
                        + (g.model != null ? ` · modell ${(g.model * 100).toFixed(1)} % · värdekvot ${g.ratio}` : '')}>
                      {m.has_model && g.ratio != null
                        ? <><span className="bratio">{g.ratio}</span>
                          <span className="bprob">{((g.model || 0) * 100).toFixed((g.model || 0) < 0.01 ? 1 : 0)}%</span></>
                        : <span className="bfolk">{((g.folk || 0) * 100).toFixed(0)}%</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {m.has_model && practical.length > 0 && (
        <div className="bvalue">Praktiskt intressanta resultat:
          {practical.map((g) => (
            <span key={g.score} className={`bchip ${g.model < 0.01 ? 'rare' : ''}`}
              title={`modell ${(g.model * 100).toFixed(1)} % vs folk ${(g.folk * 100).toFixed(1)} %`}>
              {g.score} <b>{g.ratio}×</b> <small>{(g.model * 100).toFixed(1)}%</small>
              {g.model < 0.01 && <em>sällsynt</em>}
            </span>
          ))}</div>
      )}
    </div>
  )
}

class ErrBoundary extends Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  render() {
    if (this.state.err) return <div className="error">Fel: {String(this.state.err?.stack || this.state.err).slice(0, 600)}</div>
    return this.props.children
  }
}

function BombenBuilder({ draw }) {
  const [budget, setBudget] = useState(50)
  const [sys, setSys] = useState(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [mfCopied, setMfCopied] = useState(false)
  const build = () => {
    setBusy(true)
    fetch(`/api/bomben/system?draw=${draw}&budget=${budget}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then((s) => { setSys(s); setBusy(false) })
      .catch(() => { setSys(null); setBusy(false) })
  }
  const download = () => downloadText(`bomben_omg${draw}_egnarader.txt`, egnaRaderBombenText(sys.rows))
  const copy = () => {
    navigator.clipboard?.writeText(sys.rows.map((r) => r.join(' ')).join('\n'))
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }
  return (
    <div className="bbuild">
      <div className="controls">
        <label className="budget">Max budget <b>{budget} kr</b>
          <input type="range" min="0" max={BUDGET_STOPS.length - 1}
            value={BUDGET_STOPS.reduce((b, v, i) => Math.abs(v - budget) < Math.abs(BUDGET_STOPS[b] - budget) ? i : b, 0)}
            onChange={(e) => setBudget(BUDGET_STOPS[Number(e.target.value)])} /></label>
        <button className="primary" onClick={build} disabled={busy}>{busy ? 'Bygger…' : 'Föreslå rader'}</button>
      </div>
      {sys && sys.rows?.length > 0 && (
        <>
          <div className="coupon-kpis">
            <div className="kpi"><span>{sys.num_rows}</span>rader</div>
            <div className="kpi"><span>{kr(sys.cost)}</span>insats (1 kr/rad)</div>
            <div className="kpi"><span>{pct(sys.p_all)}</span>chans alla rätt</div>
            <div className="kpi" title="Sannolikhetsviktad förväntad utdelning över de valda raderna (pott = omsättning×andel + rullpott).">
              <span>{kr(sys.ev_payout)}</span>förv. utdelning</div>
            <div className="kpi"><span className={sys.ev >= 0 ? 'pos' : 'neg'}>{sys.ev >= 0 ? '+' : ''}{kr(sys.ev)}</span>EV (netto)</div>
          </div>
          <div className="manualfill bfill">
            <b>Fyll i så här på Svenska Spel-kupongen:</b> markera målkolumnerna per match
            <span className="mf-rows">{sys.used.map((u) => (
              <span key={u.event_number} className="bfill-m">
                <em>{u.description}</em> hemma <b>{u.home_goals.join(' ')}</b> · borta <b>{u.away_goals.join(' ')}</b></span>
            ))}</span>
            <button onClick={() => {
              navigator.clipboard?.writeText(sys.used.map((u) => `${u.description}: hemmamål ${u.home_goals.join(' ')} | bortamål ${u.away_goals.join(' ')}`).join('\n'))
              setMfCopied(true); setTimeout(() => setMfCopied(false), 2000)
            }}>{mfCopied ? '✓ Kopierad' : 'Kopiera ifyllning'}</button>
            <span className="hint"> · Detta ger exakt {sys.num_rows} rader = {kr(sys.cost)} —
              samma som Egna rader-filen. (Bomben-kupongen markeras kolumnvis, så systemet är kolumnval.)</span>
          </div>
          <div className="svs-row">
            <a className="svs-link" href={egnaRaderUrl('bomben')} target="_blank" rel="noreferrer">▶ Externa systemspel ↗</a>
            <button onClick={download}>⬇ Egna rader-fil ({sys.num_rows} rader)</button>
            <button onClick={copy}>{copied ? '✓ Kopierad' : 'Kopiera raderna'}</button>
          </div>
          <p className="hint">{sys.note} · OBS: Bombens filformat är inloggningsskyddat och kunde inte
            verifieras — rubriken är "Bomben" och raderna "E,2-1,1-1,0-2". Stämmer det inte vid uppladdning,
            använd "Kopiera rader" och fyll i manuellt. EV-nivån antar 65 % återbetalning (skalar bara siffran).</p>
          <table className="grid compact"><thead><tr><th>#</th>
            {sys.used.map((u) => <th key={u.event_number}>{u.description}</th>)}
            <th>chans</th><th>utd. om rätt</th></tr></thead>
            <tbody>
              {sys.detail.slice(0, 40).map((row, i) => (
                <tr key={i}><td>{i + 1}</td>
                  {row.scores.map((s, j) => <td key={j} className="signs">{s}</td>)}
                  <td>{pct(row.p)}</td><td>{kr(row.dividend)}</td></tr>
              ))}
            </tbody></table>
          {sys.num_rows > 40 && <p className="hint">Visar 40 av {sys.num_rows} rader (filen/kopian innehåller alla).</p>}
        </>
      )}
      {sys && !sys.rows?.length && <p className="hint">Kunde inte bygga rader för omgången.</p>}
    </div>
  )
}

function BombenView({ draw, nonce }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(!!draw)
  const [showHelp, setShowHelp] = useStoredBool('svs_ui_bomben_help')
  useEffect(() => {
    if (!draw) return undefined
    let current = true
    fetch(`/api/bomben?draw=${draw}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { if (current) { setData(d); setLoading(false) } })
      .catch(() => { if (current) { setData(null); setLoading(false) } })
    return () => { current = false }
  }, [draw, nonce])
  if (!data || !Array.isArray(data.matches)) return loading
    ? <LoadingState label="Hämtar Bomben…" />
    : <EmptyState title="Ingen Bomben-data" detail="Det finns ingen analys för den valda omgången ännu." />
  return (
    <section className="bomben-section">
      <div className="topinfo">
        {/* Spelläge (samma logik som poolens PlayRec-tänk): utan extern
            subvention äter Bombens uttag edgen — rullpotten är hela caset. */}
        {data.rullpott != null && (data.rullpott > 0
          ? <span className="playrec go"
            title={`Rullpott ${kr(data.rullpott)} ligger kvar i potten från tidigare omgångar — extern subvention är det som kan lyfta Bomben över uttaget (~65 % återbetalning). OBS: Poisson-modellens EV är modellhärledd och ingår inte i CLV-facitet.`}>
            spelläge: rullpott — spela</span>
          : <span className="playrec skip"
            title="Bomben återbetalar ~65 % — utan rullpott äter uttaget edgen; Poisson-modellens EV är modellhärledd och ingår inte i CLV-facitet.">
            spelläge: avstå</span>)}
        <span>Omsättning <b>{kr(data.turnover)}</b></span>
        <span>{data.match_count} matcher · tippa exakt resultat</span>
        {data.jackpot > 0 && <span className="jackpot">💰 <b>Jackpot {kr(data.jackpot)}</b></span>}
        {!data.sharp_available && <span className="st-wait">⚠ Pinnacle nere – ingen värdemodell, bara folkets streck</span>}
      </div>
      <div className="bomben-intro">
        <span><b>Kvoten</b> visar modellens chans jämfört med folkets. Procentsiffran visar hur troligt resultatet faktiskt är.</span>
        <button className="legend-toggle" onClick={() => setShowHelp(!showHelp)} aria-expanded={showHelp}>
          {showHelp ? 'Dölj förklaring ▲' : 'Så fungerar värdet ▼'}
        </button>
        {showHelp && <p className="hint">Bomben saknar SvS-odds, så värdet = vår <b>Poisson-målmodell</b>
          {' '}(Pinnacles förväntade mål) mot <b>folkets resultatfördelning</b>. Grönt betyder att modellen
          tror mer på resultatet än folket; rött betyder överspelat. Färgens styrka tar även hänsyn till faktisk
          sannolikhet, så ett extremt men nästan omöjligt resultat inte ser ut som ett huvudval. Modellen är
          sharp-ankrad men modell-härledd — använd som vägledning, inte facit.</p>}
      </div>
      <div className="bomben-layout">
        <div className="bomben-matches">
          {data.matches.map((m) => <BombenMatch key={m.event_number} m={m} />)}
        </div>
        <aside className="bomben-builder" id="bomben-bygg">
          <h2>Bygg rader & export</h2>
          <p className="hint">Väljer budgetens bästa konkreta resultatrader efter sannolikhet och förväntat värde.</p>
          <BombenBuilder draw={data.draw_number} />
        </aside>
      </div>
      <nav className="mobile-actionbar bomben-action" aria-label="Snabbåtgärd för Bomben">
        <span><b>{data.match_count} matcher</b></span>
        <a className="primary-link" href="#bomben-bygg">Bygg rader</a>
      </nav>
    </section>
  )
}

// SPELLÄGE (2026-07-26, Samans "förbättra allt"): uttaget är 30–40 %, så
// VILKA omgångar man spelar styr EV mer än radvalet. Ren syntes av befintliga
// tal (prognostiserat spelvärde + PH5-domen) — ingen ny signal, inget facit.
function PlayRec({ payouts, product }) {
  const sv = payouts.projected_turnover > payouts.turnover
    ? (payouts.spelvarde_proj || 0)
    : (payouts.spelvarde || payouts.payout_ratio || 0)
  const thirteen = product === 'stryktipset' || product === 'europatipset'
  const [label, cls] = sv >= 1 ? ['spelläge: jackpot — spela', 'go']
    : sv >= 0.8 ? ['spelläge: tunt — spela smått', 'thin']
      : ['spelläge: avstå', 'skip']
  return (
    <span className={`playrec ${cls}`} title={`Rekommendation ur prognostiserat spelvärde (${Math.round(sv * 100)} %). Under 80 %: uttaget äter mer än någon uppmätt radvalsfördel — avstå eller spela symboliskt. 80–100 %: tunt; kräver att slå break-even-hurdlen. ≥100 %: jackpot/rullpott subventionerar fältet — det är då poolspel kan bära positiv EV.${thirteen ? ' OBS 13-matchsspel: radvalet har ingen påvisad fördel (PH5 2026-07-26) — spelvärdet är hela caset.' : ' Topptipset-spelen: radvalsfördel uppmätt +7–15 pp mot folk-/favoritrad (PH5, 3 976 omgångar), men vinst kommer i en minoritet av omgångarna — variansen är stor.'}`}>
      {label}
    </span>)
}

// Byggstenar som appskalet (AppV3.jsx) använder
/* ---------- Sorterbar tabell (UI-passet 2026-07-29) ----------
   EN delad komponent för Oddset-sidans listor — rubrikklick växlar
   fallande/stigande, null-värden sist OAVSETT riktning (en match utan xG
   ska aldrig toppa en xG-sortering), valet persisteras per tabell-id.
   useSortedRows är separat så mobilens kortvyer kan återanvända samma
   sortering utan tabellmarkup — kortordning och tabellordning får aldrig
   glida isär. */
function useSortedRows(id, rows, columns, defaultSort) {
  const [sort, setSort] = useState(() => {
    try { return JSON.parse(localStorage.getItem(`svs_sort_${id}`)) || defaultSort } catch { return defaultSort }
  })
  const saveSort = (next) => {
    try { localStorage.setItem(`svs_sort_${id}`, JSON.stringify(next)) } catch { /* ok */ }
    return next
  }
  const toggle = (key) => setSort((s) => saveSort({
    key,
    dir: s?.key === key && s?.dir === 'desc'
      ? 'asc'
      : s?.key === key ? 'desc'
        : columns.find((c) => c.key === key)?.defaultDir || 'desc',
  }))
  const choose = (key) => setSort((s) => saveSort({
    key,
    dir: s?.key === key ? s.dir : columns.find((c) => c.key === key)?.defaultDir || 'desc',
  }))
  const activeSort = columns.some((c) => c.key === sort?.key)
    ? sort
    : defaultSort || { key: columns[0]?.key, dir: columns[0]?.defaultDir || 'desc' }
  const col = columns.find((c) => c.key === activeSort?.key)
  const sorted = [...rows]
  if (col) {
    const val = col.value || ((r) => r[col.key])
    sorted.sort((a, b) => {
      const va = val(a), vb = val(b)
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb, 'sv') : va - vb
      return activeSort.dir === 'desc' ? -cmp : cmp
    })
  }
  return { sorted, sort: activeSort, toggle, choose }
}

// `limit` kapar EFTER sorteringen — annars visas godtyckliga rader som råkar
// ligga först i indata, prydligt sorterade, vilket ser ut som en topplista utan
// att vara det. null = ingen kapning.
function SortableTable({
  id, columns, rows, renderRow, renderCard, defaultSort, className,
  wrapperClassName = 'tablewrap', limit = null,
}) {
  const { sorted: allSorted, sort, toggle, choose } = useSortedRows(
    id, rows, columns, defaultSort)
  const sorted = limit == null ? allSorted : allSorted.slice(0, limit)
  const sortableColumns = columns.filter((c) => c.sortable !== false)
  return (
    <>
      <div className="mobile-sortbar mobile-only">
        <label htmlFor={`sort-${id}`}>Sortera</label>
        <select id={`sort-${id}`} value={sort?.key || ''}
          onChange={(e) => choose(e.target.value)}>
          {sortableColumns.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        <button onClick={() => toggle(sort?.key || sortableColumns[0]?.key)}
          title="Växla sorteringsriktning">
          {sort?.dir === 'desc' ? 'Fallande ↓' : 'Stigande ↑'}
        </button>
      </div>
      <div className={`${wrapperClassName}${renderCard ? ' desktop-only' : ''}`}>
        <table className={`sorttable ${className || ''}`}>
          <thead><tr>{columns.map((c) => (
            <th key={c.key} title={c.title}
              className={c.sortable === false ? '' : 'sortable'}
              onClick={c.sortable === false ? undefined : () => toggle(c.key)}>
              {c.label}{sort?.key === c.key ? (sort.dir === 'desc' ? ' ▼' : ' ▲') : ''}
            </th>))}
          </tr></thead>
          <tbody>{sorted.map(renderRow)}</tbody>
        </table>
      </div>
      {renderCard && (
        <div className="sortcards mobile-only">{sorted.map(renderCard)}</div>
      )}
    </>
  )
}


// Den här filen ÄR komponentbiblioteket (se CLAUDE.md): AppV3.jsx hämtar både
// komponenter, konstanter och helpers härifrån. Blandade exporter är alltså
// arkitekturen, inte ett misstag — priset är att fast refresh laddar om hela
// modulen i stället för att bevara state.
/* eslint-disable react-refresh/only-export-components */
export {
  AnalysisTable, SystemView, CouponPanel, SharpPanel, SteamPanel, ClvPanel,
  BombenView, OddsetView, Legend, Collection, LoadingState, EmptyState,
  ErrorState, ErrBoundary, STRATEGIES, STRATEGY_EV, BUDGET_STOPS,
  SYSTEM_BASE, SYSTEM_SVS, VARIANT, GAMES, kr, fmtClose, fmtFetched, timeAgo,
  PlayRec, PlayedPanel, oddsetBestValue, SortableTable, useSortedRows,
}
