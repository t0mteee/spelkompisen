import { Component, Fragment, useEffect, useState } from 'react'
import './App.css'

const STRATEGIES = ['säker', 'medel', 'tuff']
// strategin sätter en startpunkt på EV-/värdereglaget (samma axel), så de inte krockar
const STRATEGY_EV = { säker: 20, medel: 50, tuff: 80 }
// budgetsteg (tak för insatsen) – slider istället för sifferfält
const BUDGET_STOPS = [16, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048]
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
  const [err, setErr] = useState(null)
  const refresh = async () => { try { setSt(await (await fetch('/api/collection/status')).json()) } catch { /* */ } }
  const start = async () => {
    try {
      const r = await (await fetch('/api/collection/start', { method: 'POST' })).json()
      setErr(r.error || (!r.active ? 'gick inte att ladda jobbet — se launchd-loggen' : null))
      setSt(r)
    } catch (e) { setErr(String(e)) }
  }
  const stop = async () => { setErr(null); await fetch('/api/collection/stop', { method: 'POST' }); refresh() }
  useEffect(() => { refresh(); const id = setInterval(refresh, 10000); return () => clearInterval(id) }, [])

  const active = st?.active
  return (
    <span className="colstat"
      title={`Bakgrundsinsamlingen (launchd var 30:e min, var 5:e nära spelstopp) loggar odds & streck — driver rörelser, steam, 🔥-notiser och CLV-facit.${st ? ` ${st.snapshot_count} mättillfällen totalt.` : ''}`}>
      <span className={`dot ${active ? 'on' : 'off'}`} />
      insamling {active ? 'aktiv' : 'stoppad'}{st?.last_snapshot ? ` · ${timeAgo(st.last_snapshot)}` : ''}
      {err && !active && <span className="neg"> {err}</span>}
      <button className="linkbtn" onClick={active ? stop : start}>{active ? 'stoppa' : 'starta'}</button>
    </span>
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
  if (!sys) return null
  const roleClass = { spik: 'r-spik', halvgardering: 'r-half', helgardering: 'r-full' }
  const st = systemStats(sys, matches, payouts)
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
          {payouts?.projected_turnover > payouts?.turnover && (() => {
            const stP = systemStats(sys, matches, { ...payouts, turnover: payouts.projected_turnover })
            if (!stP || stP.tooBig) return null
            return (
              <div className="rule" title="Potterna växer mot spelstopp men det gör medvinnarna också — detta är EV räknat mot medianen av senaste omgångarnas slutomsättning.">
                Vid förväntad slutomsättning ({kr(payouts.projected_turnover)}): förv. utdelning {kr(stP.evPayout)}
                {' '}· EV <b className={stP.ev >= 0 ? 'pos' : 'neg'}>{stP.ev >= 0 ? '+' : ''}{kr(stP.ev)}</b>
                {' '}· ROI {stP.roi == null ? '–' : (stP.roi * 100).toFixed(0) + ' %'} — den ärliga siffran tidigt i veckan.
              </div>
            )
          })()}
          {payouts?.available && (
            <PayoutTable s={st} tiers={payTiers} effTurnover={payouts.turnover || 0}
              turnoverOverridden={false} jackpot={sys.jackpot ?? payouts.jackpot ?? 0} />
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
  const [open, setOpen] = useState(false)
  return (
    <div className="legendbox">
      <button className="legend-toggle" onClick={() => setOpen(!open)}>
        ℹ Vad betyder siffrorna — och vad är värde? {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="legend">
          <div><b>Raderna i varje oddscell</b> — <b>stort odds</b> = Svenska Spel (det du kan
            spela på) · <b>P</b> = Pinnacle, världens skarpaste bok = vår referens för
            "sant" pris (<b>P~</b> = härlett ur handikapp när 1X2 inte öppnats) ·
            <b> E</b> = Expekt · <b>B</b> = Betinia · <b>M</b> = vår egen modell (amber, se nedan).</div>
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
            grupp. <b>📒 Signal-loggen</b> under den visar i stället vad som faktiskt
            flaggades. Lita på ledgerfacitet, inte på känsla.</div>
        </div>
      )}
    </div>
  )
}

function OddsetView() {
  const [data, setData] = useState(null)
  const [clv, setClv] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [notices, setNotices] = useState(null)
  const [showNotices, setShowNotices] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [showLedger, setShowLedger] = useState(false)
  const [expanded, setExpanded] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [hidden, setHidden] = useState(() => {
    try { return JSON.parse(localStorage.getItem(ODDSET_HIDDEN_KEY)) || [] } catch { return [] }
  })
  const [showModel, setShowModel] = useState(() => {
    try { return localStorage.getItem('svs_oddset_model') === '1' } catch { return false }
  })
  const [onlySignals, setOnlySignals] = useState(() => {
    try { return localStorage.getItem('svs_oddset_only') === '1' } catch { return false }
  })
  const [bank, setBank] = useState(() => {
    try { return Number(localStorage.getItem('svs_oddset_bank')) || 1000 } catch { return 1000 }
  })
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

  const load = () =>
    Promise.all([
      fetch(`/api/oddset/matches?_t=${Date.now()}`, { cache: 'no-store' }).then((r) => r.json()),
      fetch(`/api/oddset/clv?_t=${Date.now()}`, { cache: 'no-store' }).then((r) => r.json()).catch(() => null),
      fetch(`/api/oddset/notices?_t=${Date.now()}`, { cache: 'no-store' }).then((r) => r.json()).catch(() => null),
      fetch(`/api/oddset/predictions?_t=${Date.now()}`, { cache: 'no-store' }).then((r) => r.json()).catch(() => null),
    ]).then(([d, c, n, l]) => { setData(d); setClv(c); setNotices(n?.notices || []); setLedger(l); setErr(null) })
      .catch((e) => setErr(String(e)))
  useEffect(() => { load() }, [])  // eslint-disable-line

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
  const InfoDot = ({ text }) => <span className="idot" title={text}>i</span>

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
  const clvLine = (market, line) => market?.endsWith('ah') ? fmtAh(line) : line
  const ledgerTiming = Object.values(ledger?.capture_quality || {}).reduce(
    (sum, h) => ({ n: sum.n + (h.n || 0), timely: sum.timely + (h.n_timely || 0) }),
    { n: 0, timely: 0 })
  const clvMoveText = (r) => {
    if (r.line_delta == null || Math.abs(r.line_delta) < 0.0001) return ''
    const direction = r.line_move_score > 0 ? 'med' : r.line_move_score < 0 ? 'emot' : 'neutralt'
    return `lina ${clvLine(r.market, r.line)}→${clvLine(r.market, r.closing_line)} · ${direction} spelet ${r.line_move_score > 0 ? '+' : ''}${r.line_move_score}`
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
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
          {series.map((s, i) => (s.pts?.length > 1
            ? <polyline key={i} fill="none" stroke={s.color} strokeWidth="1.5"
              points={s.pts.map((p) => `${X(new Date(p.t).getTime()).toFixed(1)},${Y(p.o).toFixed(1)}`).join(' ')} />
            : null))}
        </svg>
      </div>
    )
  }

  // mini-graf över sharp-seriens väg (röd = oddset ner = sannolikheten upp)
  const Spark = ({ pts }) => {
    if (!pts || pts.length < 2) return null
    const os = pts.map((p) => p.o)
    const min = Math.min(...os), max = Math.max(...os)
    const W = 64, H = 16
    const xy = os.map((o, i) =>
      `${(i / (os.length - 1) * W).toFixed(1)},${(max === min ? H / 2 : H - 1 - (o - min) / (max - min) * (H - 2)).toFixed(1)}`)
    const falling = os[os.length - 1] < os[0]
    return (
      <svg className="spark" width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <polyline points={xy.join(' ')} fill="none"
          stroke={falling ? '#e06b6b' : 'var(--green)'} strokeWidth="1.5" />
      </svg>
    )
  }

  // grön edge-pill: devigad Pinnacle säger att bok-oddset är för högt.
  // Kräver även kvalitet (edge/(odds−1)) — högoddsar-edges under kvalitetsgolvet
  // visas inte som pills (för sköra), men loggas ändå i facitet.
  const edgePill = (v) => v && v.edge >= 0.02 && (v.q ?? 0) >= 0.0075 && (
    <span className="epill" title={`Devigad Pinnacle: ${(v.fair * 100).toFixed(1)}% (fair odds ${(1 / v.fair).toFixed(2)})\nBoken betalar ${v.odds.toFixed(2)} → ${(v.edge * 100).toFixed(1)}% övervärde\nKvalitet (Kelly-andel): ${((v.q ?? 0) * 100).toFixed(1)}% — samma edge är skörare ju högre odds${v.derived ? '\n(P~ = härlett ur handikapp — ta med en nypa salt)' : ''}`}>
      +{Math.round(v.edge * 100)}%{v.derived ? '°' : ''}
    </span>
  )

  const absLine = (p) => `${p.name} (${p.reason}${p.apps != null ? `, ${p.apps} matcher${p.rating ? `, ${p.rating}` : ''}` : ''})${p.apps != null && p.apps < 5 ? ' — marginell' : ''}`
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

  const cell1x2 = (m, sign) => {
    const svs = m.odds?.svenskaspel?.['1x2']
    const pin = m.odds?.pinnacle?.['1x2']
    const mv = m.movement?.svenskaspel?.['1x2']?.[sign]
    const mvP = m.movement?.pinnacle?.['1x2']?.[sign]
    const v = m.value?.['1x2']?.[sign]
    const md = m.model
    const mEdge = md?.edges?.[sign]
    return (
      <td className="oc" key={sign}>
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
        {[['expekt', 'E', 'Expekt'], ['betinia', 'B', 'Betinia']].map(([bk, tag, label]) => {
          const bo = m.odds?.[bk]?.['1x2']
          const mvB = m.movement?.[bk]?.['1x2']?.[sign]
          if (bo?.[sign] && bo[sign] === svs?.[sign]) return null  // identiskt med SvS = brus
          return bo?.[sign] ? (
            <div className={quoteClass('p', bo)} key={bk} title={mvB?.pts?.length > 1 ? `${label}:\n${serie(mvB)}` : label}>
              {tag} {bo[sign].toFixed(2)}{arrow(mvB)}{v?.book === bk && edgePill(v)}{priceStamp(bo)}
            </div>
          ) : null
        })}
        {showModel && md?.fair?.[sign] && (
          <div className="m"
            title={`Egen modell (xG-viktad Poisson-styrkefit; DC-korrektion i prediktionen): ${(md.p[sign] * 100).toFixed(1)}%\nμ ${md.mu[0]}–${md.mu[1]} · T=${md.cal_t || 1}${md.anchored ? ' · totalnivå ankrad mot sharp Ö/U' : ' · OANKRAD (ingen sharp-linje ännu)'}${md.prior ? '\n⚠ Elo-prior: minst ett lag har tunn historik — styrka skattad ur ClubElo' : ''}\nT valdes på samma historiska backtestmaterial; ledgern är oberoende forward-facit.\nAmber-tier: experimentell`}>
            M {md.fair[sign].toFixed(2)}
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
    const mp = market !== 'cor' && showModel ? m.model?.[market] : null
    const mpBest = mp && Object.entries(mp.edges || {})
      .filter(([, e]) => e >= 0.05).sort((a, b) => b[1] - a[1])[0]
    return (
      <td className="oc pair">
        <div className={quoteClass('o', svs)}>
          {svs?.[k1] && svs?.[k2] ? <>{fmtL(svs.line)} · {svs[k1].toFixed(2)}{arrowAtLine(mvS1, svs.line)} / {svs[k2].toFixed(2)}{arrowAtLine(mvS2, svs.line)}{shiftBadge(mvS1, 'SvS')}{priceStamp(svs)}</> : '–'}
          {edgePill(v1) || edgePill(v2)}
        </div>
        {pin?.[k1] && pin?.[k2] && <div className={quoteClass('p', pin)}>P {fmtL(pin.line)} · {pin[k1].toFixed(2)}{arrowAtLine(mvP1, pin.line)} / {pin[k2].toFixed(2)}{arrowAtLine(mvP2, pin.line)}{shiftBadge(mvP1, 'Pinnacle')}{priceStamp(pin)}</div>}
        {mp && (
          <div className="m"
            title={`Modellens fair vid SvS-linjen ${fmtL(mp.line)} (push/kvartslinjer hanterade).${market === 'ou' && m.model?.anchored ? '\nÖU: totalen är ankrad mot sharp — fairen ligger nära Pinnacle per konstruktion; edgen mäter mest SvS marginal.' : ''}${market === 'ah' ? '\nAH bär modellens EGEN styrkebedömning (supremacy) — här kan modellen avvika på riktigt.' : ''}\nAmber: experimentell — forward-loggas i 📒-facitet, spela inte blint.`}>
            M {mp[k1] ? mp[k1].toFixed(2) : '–'} / {mp[k2] ? mp[k2].toFixed(2) : '–'}
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
  const BOOK_NAME = { svenskaspel: 'SvS', expekt: 'Expekt', betinia: 'Betinia' }

  if (err) return <section><h2>Oddset</h2><div className="error">{err}</div></section>
  if (!data) return <section><h2>Oddset</h2><div className="loading">Hämtar…</div></section>

  const leagueName = Object.fromEntries(data.leagues.map((l) => [l.key, l.name]))
  const healthDefs = [
    ['pinnacle', 'markets', 'P'], ['svenskaspel', '1x2', 'SvS'],
    ['svenskaspel', 'deep', 'SvS djup'], ['expekt', '1x2', 'E'],
    ['betinia', '1x2', 'B'],
  ]
  const sourceHealth = healthDefs.flatMap(([source, scope, label]) => {
    const rows = (data.source_health || []).filter((r) => r.source === source && r.scope === scope)
    if (!rows.length) return []
    const latest = rows.reduce((a, r) => !a || r.checked_at > a ? r.checked_at : a, null)
    const failed = rows.filter((r) => !r.ok)
    const stale = Date.now() - new Date(latest).getTime() > 45 * 60 * 1000
    const details = failed.length
      ? failed.map((r) => `${leagueName?.[r.league] || r.league}: ${r.error || 'källfel'}`).join('\n')
      : `${rows.reduce((n, r) => n + (r.event_count || 0), 0)} events · kontrollerad ${timeAgo(latest)}`
    return [{ source, scope, label, latest, ok: !failed.length && !stale, details }]
  })

  const counts = {}
  for (const m of data.matches) counts[m.league] = (counts[m.league] || 0) + 1
  const visible = data.matches.filter((m) => !hidden.includes(m.league))
  const hasSignal = (m) => {
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

  const days = []
  for (const m of listed) {
    const key = (m.start || '').slice(0, 10)
    const d = days[days.length - 1]
    if (d && d.key === key) d.matches.push(m)
    else days.push({ key, label: fmtDay(m.start), matches: [m] })
  }

  // kvalitet q = edge/(odds−1) = Kelly-andelen: straffar högoddsare — samma edge
  // är mycket skörare på odds 15 än på 1.5 (litet fel i fair blåser upp den)
  const signals = []
  for (const m of visible) {
    for (const [mk, per] of Object.entries(m.value || {})) {
      for (const [sg, v] of Object.entries(per)) {
        if (v.edge >= 0.02 && (v.q ?? 0) >= 0.0075) signals.push({ m, mk, sg, v })
      }
    }
  }
  signals.sort((a, b) => (b.v.q ?? 0) - (a.v.q ?? 0))

  // 📈 Rörelse-radarn: största devigade sharp-skiften — går över ALLA ligor
  // (även dolda flikar: träningsmatch-caset får inte missas för att fliken är av)
  const movers = []
  for (const m of data.matches) {
    if (m.start && new Date(m.start) < new Date()) continue
    for (const [sg, sh] of Object.entries(m.steam || {})) {
      const cands2 = [['6h', sh.h6], ['24h', sh.h24]].filter(([, v]) => v != null)
      if (!cands2.length) continue
      const [win, pp] = cands2.reduce((a, b) => (Math.abs(b[1]) > Math.abs(a[1]) ? b : a))
      if (Math.abs(pp) < 1.5) continue
      movers.push({ m, sg, pp, win })
    }
  }
  movers.sort((a, b) => Math.abs(b.pp) - Math.abs(a.pp))

  return (
    <section className="oddset">
      <div className="analys-head">
        <h2>Oddset — enskilda matcher</h2>
      </div>
      <OddsetLegend />
      <div className="oddset-bar">
        {data.leagues.map((l) => (
          <button key={l.key} className={hidden.includes(l.key) ? 'lg off' : 'lg'}
            onClick={() => toggleLeague(l.key)}
            title={hidden.includes(l.key) ? 'Visa ligan' : 'Dölj ligan'}>
            {l.name} {counts[l.key] ? `(${counts[l.key]})` : '(0)'}
          </button>
        ))}
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
        {sourceHealth.map((h) => (
          <span key={`${h.source}:${h.scope}`} className={`sourcehealth ${h.ok ? 'ok' : 'bad'}`}
            title={`${h.label}: ${h.ok ? `frisk · ${timeAgo(h.latest)}` : 'fel eller för gammal'}\n${h.details}`}>
            {h.ok ? '●' : '▲'} {h.label}
          </span>
        ))}
        <span className="spacer" />
        <span className="hint">
          {data.last_run ? `hämtat ${new Date(data.last_run).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' })}` : 'inga odds hämtade ännu'}
        </span>
        <button onClick={refresh} disabled={busy}>{busy ? 'Hämtar…' : '↻ Hämta färska odds'}</button>
      </div>
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
      {signals.length > 0 && (
        <div className="valuelist">
          <div className="valhead"><b>💰 Värdespel just nu</b>
            <InfoDot text={'Bok-odds över devigad Pinnacle (sharp-ankrat = den spelbara signalen).\n° = härlett sharp-pris · ★ = flera oberoende signaler pekar åt samma håll.\n¼-Kelly räknas på fair-sannolikheten och din bank.'} />
            <span className="spacer" />
            <span className="hint">bank</span>
            <input className="bankin" type="number" value={bank} min="0"
              onChange={(e) => saveBank(Number(e.target.value) || 0)} /> <span className="hint">kr</span>
          </div>
          <div className="tipgrid">
            {signals.slice(0, 8).map(({ m, mk, sg, v }, i) => {
              const q = v.q ?? 0
              const tier = q >= 0.04 ? ['STARK EDGE', 't3'] : q >= 0.02 ? ['EDGE', 't2'] : ['SVAG EDGE', 't1']
              const mvP = m.movement?.pinnacle?.[mk]?.[sg]
              const support = []
              if (mk === '1x2') {
                const st = m.steam?.[sg]
                const stpp = st && ((Math.abs(st.h6 ?? 0) >= Math.abs(st.h24 ?? 0)) ? st.h6 : st.h24)
                if (stpp != null && stpp >= 1.5) support.push(['⚡ sharpen kortar', `Pinnacle har flyttat ${sg} ${stpp > 0 ? '+' : ''}${stpp} pp åt spelets håll — edgen är färsk, inte gammal skåpmat`])
                const me = m.model?.edges?.[sg]
                if (me != null && me >= 0.02) support.push(['🧪 modellen håller med', `Egen modell ser också värde här (+${(me * 100).toFixed(1)}%) — oberoende av sharp-jämförelsen`])
              } else {
                const me = m.model?.[mk]?.edges?.[sg]
                if (me != null && me >= 0.02) support.push(['🧪 modellen håller med', `Egen modell ser också värde här (+${(me * 100).toFixed(1)}%)`])
                const sh = lineShift(mvP)
                if (sh) support.push(['⇄ sharp-linjen flyttad', `Pinnacle har flyttat linjen ${sh.from} → ${sh.to}`])
              }
              return (
                <div key={i} className={`tipcard ${tier[1]}`}>
                  <div className="tiphead">
                    <b className="tipsel">{selLabel(m, mk, sg, v.line)} @ {v.odds.toFixed(2)}</b>
                    {v.book !== 'svenskaspel' && <span className="tipbook">hos {BOOK_NAME[v.book] || v.book}</span>}
                    <span className={`edgechip ${tier[1]}`}>{tier[0]} +{(v.edge * 100).toFixed(1)}%{v.derived ? '°' : ''}</span>
                  </div>
                  <div className="tipmatch">
                    <span className="lgtag">{(leagueName[m.league] || m.league).slice(0, 1)}</span>
                    {m.home} – {m.away}
                    <span className="hint">{fmtDay(m.start)} {fmtTime(m.start)}</span>
                    <Spark pts={mvP?.pts} />
                  </div>
                  <div className="tipwhy hint">
                    Devigad Pinnacle: {(v.fair * 100).toFixed(1)} % (fair {(1 / v.fair).toFixed(2)}) —
                    {' '}{BOOK_NAME[v.book] || v.book} betalar {v.odds.toFixed(2)} ·
                    {' '}¼-Kelly: <b>{kelly(v)} kr</b>
                  </div>
                  {support.length > 0 && (
                    <div className="tipsupport">
                      {support.map(([lbl, tip], j) => <span key={j} className="schip" title={tip}>{lbl}</span>)}
                      {support.length >= 2 && <span className="schip star" title="Sharp-edge + flera oberoende medhåll — starkast stödda spelet just nu">★ starkast stödd</span>}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
      {movers.length > 0 && (
        <div className="valuelist moverlist">
          <div className="valhead"><b>📈 Största rörelserna</b>
            <InfoDot text={'Pinnacles devigade sannolikhet, skift i procentenheter (6/24 h), alla ligor oavsett flikfilter.\nGrönt till höger = en bok står kvar på gamla priset — det är läget att agera (träningsmatch-caset).'} /></div>
          {movers.slice(0, 8).map(({ m, sg, pp, win }, i) => {
            const mvP = m.movement?.pinnacle?.['1x2']?.[sg]
            const v = m.value?.['1x2']?.[sg]
            return (
              <div key={i} className="valrow">
                <span className={Math.abs(pp) >= 3.5 ? 'steam strong' : 'steam'}>🔥</span>
                <b className={pp > 0 ? 'mv down' : 'mv up'}>{pp > 0 ? '+' : ''}{pp} pp/{win}</b>
                <b>{selLabel(m, '1x2', sg)}</b>
                <span className="hint">{mvP ? `P ${mvP.first.toFixed(2)} → ${mvP.last.toFixed(2)}` : ''}</span>
                <span className="vteams">
                  <span className="lgtag">{(leagueName[m.league] || m.league).slice(0, 1)}</span>
                  {m.home} – {m.away}
                </span>
                <span className="hint">{fmtDay(m.start)} {fmtTime(m.start)}</span>
                {v && v.edge >= 0.02 && pp > 0
                  ? <span className="epill">{BOOK_NAME[v.book] || v.book} kvar på {v.odds.toFixed(2)} (+{Math.round(v.edge * 100)}%)</span>
                  : <span className="hint">böckerna har hängt med</span>}
              </div>
            )
          })}
        </div>
      )}
      {showModel && (() => {
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
            {msig.slice(0, 8).map(({ m, label, e, p, fair }, i) => (
              <div key={i} className="valrow">
                <span className="apill big">+{(e * 100).toFixed(1)}%</span>
                <b>{label}</b>
                <span className="hint">modell {(p * 100).toFixed(0)}% (fair {fair?.toFixed(2)})</span>
                <span className="vteams">{m.home} – {m.away}</span>
                <span className="hint">{fmtDay(m.start)} {fmtTime(m.start)}</span>
              </div>
            ))}
          </div>
        )
      })()}
      {days.length === 0 && <p className="hint">Inga kommande matcher i synliga ligor.</p>}
      <table className="oddset-table">
        <thead>
          <tr><th>Tid</th><th>Match</th><th>1</th><th>X</th><th>2</th>
            <th title="Asian handicap (hemmalinje) · odds hemma / borta">AH</th>
            <th title="Asiatisk total (mål) · odds över / under">Ö/U</th>
            <th title="Totala hörnor · odds över / under. Pinnacle prissätter hörnor först nära avspark — saknas P-rad finns inget sharp-ankare.">Hörnor</th></tr>
        </thead>
        {days.map((d) => (
          <tbody key={d.key}>
            <tr className="dayrow"><td colSpan={8}>{d.label}</td></tr>
            {d.matches.map((m) => (
              <Fragment key={m.id}>
                <tr className={m.start && new Date(m.start) < new Date() ? 'started' : ''}>
                  <td className="time">{fmtTime(m.start)}</td>
                  <td className="teams clickable"
                    onClick={() => setExpanded(expanded === m.id ? null : m.id)}
                    title={[`Klicka för detaljvy (grafer, serier, flaggor)`,
                      m.elo && `ClubElo: ${m.elo.h ?? '?'} vs ${m.elo.a ?? '?'}`,
                      m.model && `Modell-μ: ${m.model.mu[0]}–${m.model.mu[1]}${m.model.anchored ? ' (ankrad mot sharp)' : ''}`]
                      .filter(Boolean).join('\n')}>
                    <span className="lgtag">{(leagueName[m.league] || m.league).slice(0, 1)}</span>
                    {m.home} – {m.away}{steamBadge(m)}{absBadge(m)}
                  </td>
                  {['1', 'X', '2'].map((s) => cell1x2(m, s))}
                  {cellPair(m, 'ah', 'H', 'A', fmtAh)}
                  {cellPair(m, 'ou', 'O', 'U', (l) => l)}
                  {cellPair(m, 'cor', 'O', 'U', (l) => l)}
                </tr>
                {expanded === m.id && (
                  <tr className="detailrow"><td colSpan={8}>
                    <div className="dcharts">
                      {['1', 'X', '2'].map((sg) => (
                        <DetailChart key={sg}
                          label={sg === '1' ? `1 · ${m.home}` : sg === '2' ? `2 · ${m.away}` : 'X · Kryss'}
                          series={[
                            { color: 'var(--green)', pts: m.movement?.svenskaspel?.['1x2']?.[sg]?.pts },
                            { color: '#5b9bd5', pts: m.movement?.pinnacle?.['1x2']?.[sg]?.pts },
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
                      {(clv?.rows || []).filter((r) => r.match_id === m.id).map((r, j) => (
                        <span key={j} className={r.tier === 'model' ? 'apill' : 'epill'}>
                          {r.market} {r.sign}{r.line != null ? ` (${clvLine(r.market, r.line)})` : ''} @{r.first_odds} {r.first_edge > 0 ? '+' : ''}{Math.round(r.first_edge * 100)}%
                          {r.closing_fair != null ? ` → close-EV ${((r.closing_fair * r.first_odds - 1) * 100).toFixed(0)}%` : ''}
                          {clvMoveText(r) ? ` · ${clvMoveText(r)}` : r.closing_fair == null ? ` · ${r.closing_note || 'öppen'}` : ''}
                        </span>
                      ))}
                    </div>
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        ))}
      </table>
      {ledger?.n_captures > 0 && (
        <div className="clvbox ledgerbox">
          <p className="hint clvline clickable" onClick={() => setShowLedger(!showLedger)}
            title="Alla tillgängliga sharp- och modellprediktioner fryses en gång vid T−24 h, T−3 h och T−20 min. Även oflaggade selektioner sparas som kontrollgrupp. Status avgörs per liga × marknad × tier × semantisk version, aldrig av ett tier-aggregat.">
            🧭 Prognosledger — {ledger.n_predictions} prediktioner · {ledger.n_captures} fångster
            {' '}({ledger.horizons?.h24 || 0}×24h · {ledger.horizons?.h3 || 0}×3h · {ledger.horizons?.m20 || 0}×20m)
            {ledgerTiming.n > 0 && <> · {ledgerTiming.timely}/{ledgerTiming.n} i tid</>}
            {ledger.n_empty_captures > 0 && <> · {ledger.n_empty_captures} utan tillgänglig prognos</>}
            {' '}{showLedger ? '▲' : '▼'}
          </p>
          {showLedger && <div className="tablewrap"><table className="logtable">
            <thead><tr><th>status</th><th>grupp</th><th>pred/kontroll</th><th>flaggor</th><th>bredd</th><th>close-EV</th><th>90 % KI</th></tr></thead>
            <tbody>{(ledger.groups || []).map((g) => (
              <tr key={`${g.tier}-${g.league}-${g.market}-${g.version}`}>
                <td className={`ledgerstatus ${g.status}`}>{g.status === 'green' ? '✓ grön' : g.status === 'candidate' ? '◐ kandidat' : '● amber'}</td>
                <td>{g.tier === 'model' ? '🧪' : '💰'} {g.league} · {g.market}{g.primary ? ' · primär' : ''}<span className="hint"> · {g.version}</span></td>
                <td>{g.n_timely}/{g.n_controls}{g.n_late > 0 ? ` · ${g.n_late} sena` : ''}</td>
                <td>{g.n_resolved}/{g.n_flags} stängda</td>
                <td>{g.n_matches} matcher · {g.n_weeks} v · {g.span_days} d</td>
                <td className={g.avg_close_ev == null ? '' : g.avg_close_ev >= 0 ? 'pos' : 'neg'}>{g.avg_close_ev == null ? '–' : `${g.avg_close_ev >= 0 ? '+' : ''}${(g.avg_close_ev * 100).toFixed(1)}%`}</td>
                <td>{g.ci ? `[${(g.ci[0] * 100).toFixed(1)}..${(g.ci[1] * 100).toFixed(1)}]${g.ci_stable ? '' : ' · instabilt'}` : '–'}</td>
              </tr>
            ))}</tbody>
          </table></div>}
        </div>
      )}
      {clv && (clv.sharp?.n > 0 || clv.model?.n > 0) && (
        <div className="clvbox">
          <p className="hint clvline clickable" onClick={() => setShowLog(!showLog)}
            title="Varje flagga loggas (först/bäst per marknad) och jämförs efter avspark med devigad Pinnacle-stängning. Grönt-krav (v2): minst 50 stängda OCH undre 90%-KI-gränsen över noll (bootstrap per match, EV capped ±20%) — positivt snitt ensamt räcker inte. Klicka för hela tabellen.">
            📒 Signal-logg — sharp: {clv.sharp?.n ?? 0} flaggor · {clv.sharp?.n_resolved ?? 0} stängda
            {clv.sharp?.n_line_moved > 0 && <> · {clv.sharp.n_line_moved} linjeflytt{clv.sharp.n_line_moved === 1 ? '' : 'ar'}</>}
            {clv.sharp?.avg_close_ev != null && <> · snitt <b className={clv.sharp.avg_close_ev >= 0 ? 'pos' : 'neg'}>{(clv.sharp.avg_close_ev * 100).toFixed(1)}%</b></>}
            {clv.sharp?.ci && <> · KI [{(clv.sharp.ci[0] * 100).toFixed(1)}..{(clv.sharp.ci[1] * 100).toFixed(1)}]{clv.sharp.green_ready ? ' ✓' : ''}</>}
            {clv.model?.n > 0 && <> &nbsp;|&nbsp; 🧪 modell: {clv.model.n} flaggor · {clv.model.n_resolved} stängda
              {clv.model.n_line_moved > 0 && <> · {clv.model.n_line_moved} linjeflytt{clv.model.n_line_moved === 1 ? '' : 'ar'}</>}
              {clv.model.avg_close_ev != null && <> · snitt <b className={clv.model.avg_close_ev >= 0 ? 'pos' : 'neg'}>{(clv.model.avg_close_ev * 100).toFixed(1)}%</b></>}
              {clv.model?.ci && <> · KI [{(clv.model.ci[0] * 100).toFixed(1)}..{(clv.model.ci[1] * 100).toFixed(1)}]{clv.model.green_ready ? ' ✓' : ''}</>}</>}
            {' '}{showLog ? '▲' : '▼'}
          </p>
          {showLog && (
            <table className="logtable">
              <thead><tr><th>flagga</th><th>match</th><th>bok</th><th>odds</th><th>edge</th><th>bäst</th><th>stängning</th><th>tier</th></tr></thead>
              <tbody>
                {(clv.rows || []).map((r, i) => (
                  <tr key={i}>
                    <td>{r.market} {r.sign}{r.line != null ? ` (${clvLine(r.market, r.line)})` : ''}</td>
                    <td>{r.description}</td>
                    <td>{BOOK_NAME[r.book] || r.book || 'SvS'}</td>
                    <td>{r.first_odds}</td>
                    <td>{r.first_edge > 0 ? '+' : ''}{(r.first_edge * 100).toFixed(1)}%</td>
                    <td>{r.best_edge > 0 ? '+' : ''}{(r.best_edge * 100).toFixed(1)}%</td>
                    <td>{r.closing_fair != null
                      ? <><b className={(r.closing_fair * r.first_odds - 1) >= 0 ? 'pos' : 'neg'}>
                        {((r.closing_fair * r.first_odds - 1) * 100).toFixed(1)}%</b>
                        {clvMoveText(r) && <span className="hint"> · {clvMoveText(r)}</span>}</>
                      : (clvMoveText(r) || r.closing_note || 'öppen')}</td>
                    <td>{r.tier === 'model' ? '🧪' : '💰'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
function evalRows(rowFF, tiers, field, N, minDividend = 0) {
  const poly = {}, evTiers = {}, divMin = {}, divMax = {}
  let kept = 0, evPayout = 0
  for (const row of rowFF) {
    const pf = poissonBinomial(row.map((o) => o.fair))
    const pk = poissonBinomial(row.map((o) => o.folk))
    const div = {}
    for (const t of tiers) { const c = t.correct; div[c] = Math.min(t.pool, t.pool / (field * (pk[c] || 0) + 1)) }
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
      return { fair: o.fair_prob || 0, folk: o.streck != null ? o.streck / 100 : (o.fair_prob || 0) }
    }))
    const modelOk = field > 0 && tiers.length > 0
    const e = modelOk ? evalRows(rowFF, tiers, field, N, minDividend)
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
      folk: m.outcomes[s]?.streck != null ? m.outcomes[s].streck / 100 : (m.outcomes[s]?.fair_prob || 0),
    })))
    const rowFF = []
    const rec = (i, acc) => { if (i === N) { rowFF.push(acc); return } for (const o of lists[i]) rec(i + 1, [...acc, o]) }
    rec(0, [])
    e = evalRows(rowFF, tiers, field, N, minDividend); modelOk = true
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
  const turnover = payouts.turnover || 0
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
    return { fair: o.fair_prob || 0, folk: o.streck != null ? o.streck / 100 : (o.fair_prob || 0) }
  }))
  const e = evalRows(rowFF, tiers, field, N, 0)
  const cost = rowsSigns.length * rowPrice
  const poolMap = {}; tiers.forEach((t) => { poolMap[t.correct] = t.pool })
  return { ...e, N, rows: rowsSigns.length, cost, poolMap, turnover,
    ev: e.evPayout - cost, roi: cost ? (e.evPayout - cost) / cost : null, pAll: e.poly[N] || 0 }
}

/* Liten tabell: lägsta/medel/högsta förväntad utdelning per vinstnivå. */
function PayoutTable({ s, tiers, effTurnover, turnoverOverridden, jackpot }) {
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
      <p className="hint">*Prispott = omsättning ({kr(effTurnover)}{turnoverOverridden ? ', justerad' : ', live'})
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
      q *= o.streck != null ? o.streck / 100 : (o.fair_prob || 0)
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

function CouponPanel({ matches, picks, pickRows, payouts, product, draw, onClear }) {
  const [redOn, setRedOn] = useState(false)
  const [minDiv, setMinDiv] = useState(50)
  const [turnover, setTurnover] = useState(null)   // null = använd live-omsättning
  const [jackpot, setJackpot] = useState(0)
  const [copied, setCopied] = useState(false)
  const [bankroll, setBankroll] = useState(() => {
    try { return Number(localStorage.getItem('svs_bankroll')) || 5000 } catch { return 5000 }
  })
  useEffect(() => { try { localStorage.setItem('svs_bankroll', String(bankroll)) } catch { /* ok */ } }, [bankroll])
  // jackpot/rullpott hämtas numera ur API:t — förifyll när omgången har en
  useEffect(() => {
    if (payouts?.jackpot > 0) setJackpot(payouts.jackpot)
  }, [payouts?.jackpot])  // eslint-disable-line
  const copyCoupon = () => {
    // radläge: kopiera de faktiska raderna (en per rad) — teckenunionen per
    // match säger inget om vilka rader som faktiskt spelas
    const txt = (pickRows && pickRows.length)
      ? pickRows.map((r) => r.join('')).join('\n')
      : matches.map((m) => `${m.event_number}. ${m.description}: ${(picks[m.event_number] || []).join('')}`).join('\n')
    navigator.clipboard?.writeText(txt); setCopied(true); setTimeout(() => setCopied(false), 2000)
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
                    onChange={(e) => setJackpot(Number(e.target.value) * 1e6)} />
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
            <PayoutTable s={s} tiers={payTiers} effTurnover={effTurnover}
              turnoverOverridden={turnover != null} jackpot={jackpot} />
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

/* Steam: devigade sannolikhetsskift (procentenheter) över 6/24/72 h.
   Jämförbart mellan favoriter och skrällar — det rå oddsrörelse inte är. */
function SteamPanel({ product, draw, matches }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    if (!draw) return
    setData(null)
    fetch(`/api/steam?product=${product}&draw=${draw}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then(setData).catch(() => setData(null))
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
    setData(null)
    fetch(`/api/clv?product=${group}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then(setData).catch(() => setData(null))
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
    if (g.ratio >= 1.05) return `rgba(61,220,132,${Math.min(0.55, (g.ratio - 1) * 0.5).toFixed(2)})`
    if (g.ratio <= 0.95) return `rgba(224,107,107,${Math.min(0.55, (1 - g.ratio) * 0.6).toFixed(2)})`
    return undefined
  }
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
                        ? <span className="bratio">{g.ratio}</span>
                        : <span className="bfolk">{((g.folk || 0) * 100).toFixed(0)}%</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {m.has_model && m.top_value.length > 0 && (
        <div className="bvalue">Mest underspelade resultat:
          {m.top_value.slice(0, 4).map((g) => (
            <span key={g.score} className="bchip" title={`modell ${(g.model * 100).toFixed(1)} % vs folk ${(g.folk * 100).toFixed(1)} %`}>
              {g.score} <b>{g.ratio}×</b></span>
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
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    if (!draw) return
    setLoading(true)
    fetch(`/api/bomben?draw=${draw}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then((d) => { setData(d); setLoading(false) })
      .catch(() => { setData(null); setLoading(false) })
  }, [draw, nonce])
  if (!data || !Array.isArray(data.matches)) return <div className="loading">{loading ? 'Hämtar Bomben…' : 'Ingen Bomben-data för vald omgång.'}</div>
  return (
    <section>
      <div className="topinfo">
        <span>Omsättning <b>{kr(data.turnover)}</b></span>
        <span>{data.match_count} matcher · tippa exakt resultat</span>
        {data.jackpot > 0 && <span className="jackpot">💰 <b>Jackpot {kr(data.jackpot)}</b></span>}
        {!data.sharp_available && <span className="st-wait">⚠ Pinnacle nere – ingen värdemodell, bara folkets streck</span>}
      </div>
      <p className="hint">Bomben saknar SvS-odds, så värdet = vår <b>Poisson-målmodell</b> (Pinnacles förväntade
        mål) mot <b>folkets resultatfördelning</b>. Rutan visar värdekvoten (modell ÷ folk):
        {' '}<span className="sg-bla">grönt = underspelat</span> (modellen tror mer än folket = köpläge),
        rött = överspelat. Rader = hemmamål, kolumner = bortamål. Håll muspekaren för folk-/modell-%.
        Modellen är sharp-ankrad men modell-härledd — använd som vägledning, inte facit.</p>
      {data.matches.map((m) => <BombenMatch key={m.event_number} m={m} />)}
      <h2>Bygg rader & export</h2>
      <p className="hint">Rangordnar konkreta resultat-rader efter popularitetsjusterad EV
        (modellens sannolikhet vs hur många du delar potten med) och tar budgetens bästa.</p>
      <BombenBuilder draw={data.draw_number} />
    </section>
  )
}

// sparat tillstånd (iOS slänger hemskärms-appen ur minnet och laddar om vid
// återkomst – vi återställer val/kupong/inställningar så omladdningen blir osynlig)
const SAVED = (() => {
  try { return JSON.parse(localStorage.getItem('svs_state') || '{}') || {} } catch { return {} }
})()

export default function App() {
  const [group, setGroup] = useState(SAVED.group || 'topptipset')   // flik (kan samla flera produkter)
  const [product, setProduct] = useState(SAVED.product || 'topptipset')  // vald omgångs faktiska produkt (slug)
  const [draws, setDraws] = useState([])
  const [draw, setDraw] = useState(SAVED.draw || null)
  const [analysis, setAnalysis] = useState(null)
  const [movement, setMovement] = useState(null)
  const [sys, setSys] = useState(null)
  const [strategy, setStrategy] = useState(SAVED.strategy || 'medel')
  const [budget, setBudget] = useState(SAVED.budget || 128)
  const [sysType, setSysType] = useState(SAVED.sysType || 'ev')
  const [valueWeight, setValueWeight] = useState(SAVED.valueWeight ?? 50)  // EV-/värdeskala 0..100
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [picks, setPicks] = useState(SAVED.picks || {})
  const [pickRows, setPickRows] = useState(SAVED.pickRows || null)  // radläge: exakta rader från förslaget
  const [payouts, setPayouts] = useState(null)
  const [bombenNonce, setBombenNonce] = useState(0)  // ↻ Uppdatera för Bomben-vyn

  const toggleSign = (ev, sign) => {
    setPickRows(null)   // manuell ändring -> tillbaka till kombinationsläge
    setPicks((prev) => {
      const cur = prev[ev] || []
      const next = cur.includes(sign) ? cur.filter((s) => s !== sign) : [...cur, sign]
      const copy = { ...prev }
      if (next.length) copy[ev] = next; else delete copy[ev]
      return copy
    })
  }
  const clearCoupon = () => { setPicks({}); setPickRows(null) }
  const useSystem = () => {   // "Lägg i kupongen" från förslagsvyn
    fillFromTips()
    setTimeout(() => document.getElementById('kupong')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }
  const fillFromTips = () => {
    if (!analysis) return
    const p = {}
    if (sys?.picks) {                       // använd senaste föreslagna systemet om det finns
      sys.picks.forEach((pk) => { p[pk.event_number] = pk.signs })
      // system med utvalda rader (EV-topp/färg/reducerat): kupongen ärver
      // exakt de raderna i stället för att explodera till alla kombinationer
      setPickRows(sys.rows && sys.rows.length ? sys.rows.map((r) => [...r]) : null)
    } else {
      for (const m of analysis.matches) {
        const order = ['1', 'X', '2'].sort((a, b) => (m.outcomes[b].fair_prob || 0) - (m.outcomes[a].fair_prob || 0))
        const k = m.speltyp === 'avvakta' ? 3 : (m.speltyp === 'halvspik' || m.speltyp === 'gardera') ? 2 : 1
        p[m.event_number] = order.slice(0, k)
      }
      setPickRows(null)
    }
    setPicks(p)
  }

  const nMatches = analysis?.matches?.length || 0
  const systemTypes = nMatches === 13 ? [...SYSTEM_BASE, ...SYSTEM_SVS] : SYSTEM_BASE
  const budgetIdx = BUDGET_STOPS.reduce((best, v, i) =>
    Math.abs(v - budget) < Math.abs(BUDGET_STOPS[best] - budget) ? i : best, 0)
  // radläge: hur många överlevande rader använder varje tecken (färgar stora kupongen)
  const rowShares = (pickRows?.length && analysis?.matches?.length === pickRows[0]?.length) ? (() => {
    const counts = {}
    pickRows.forEach((r) => r.forEach((s, i) => {
      const k = `${analysis.matches[i].event_number}:${s}`
      counts[k] = (counts[k] || 0) + 1
    }))
    return { counts, total: pickRows.length }
  })() : null

  // silent = tyst auto-uppdatering: rör inte spinner/öppen graf/felruta
  const loadAnalysis = async (p = product, dn = draw, silent = false) => {
    if (!dn) return
    if (!silent) { setLoading(true); setErr(null); setSelected(null) }
    try {
      const r = await fetch(`/api/analysis?product=${p}&draw=${dn}&_t=${Date.now()}`, { cache: 'no-store' })
      if (!r.ok) throw new Error(`Analys ${r.status}`)
      setAnalysis(await r.json())
      fetch(`/api/movement?product=${p}&draw=${dn}&_t=${Date.now()}`, { cache: 'no-store' })
        .then((x) => x.json()).then(setMovement).catch(() => setMovement(null))
    } catch (e) { if (!silent) setErr(String(e)) } finally { if (!silent) setLoading(false) }
  }

  // byt spel: hämta omgångar, välj första öppna, ladda analys
  const loadPayouts = (p = product, dn = draw, silent = false) => {
    if (!dn) return
    if (!silent) setPayouts(null)
    fetch(`/api/payouts?product=${p}&draw=${dn}&_t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json()).then(setPayouts).catch(() => { if (!silent) setPayouts(null) })
  }

  const refresh = () => {
    if (group === 'oddset') return
    if (group === 'bomben') { setBombenNonce((n) => n + 1); return }
    loadAnalysis(); loadPayouts()
  }

  // tyst auto-uppdatering: bakgrundsjobbet skriver till DB:n var 5–30:e min, men
  // den öppna sidan visade gammal data tills man tryckte Uppdatera. Polla var 2:a
  // min + när man kommer tillbaka till fliken/appen (utan att störa kupong/graf).
  useEffect(() => {
    if (!draw) return
    const tick = () => {
      if (group === 'bomben' || group === 'oddset' || document.visibilityState !== 'visible') return
      loadAnalysis(product, draw, true)
      loadPayouts(product, draw, true)
    }
    const id = setInterval(tick, 120000)
    document.addEventListener('visibilitychange', tick)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', tick) }
  }, [product, draw])  // eslint-disable-line

  const switchGame = async (g) => {
    setGroup(g); setSys(null); setAnalysis(null); setMovement(null); setErr(null); setSysType('ev'); setPicks({}); setLoading(true)
    if (g === 'oddset') { setDraws([]); setLoading(false); return }  // egen vy, inga omgångar
    try {
      const d = await (await fetch(`/api/draws?product=${g}&_t=${Date.now()}`, { cache: 'no-store' })).json()
      const list = d.open?.length ? d.open : d.draws
      setDraws(list)
      const first = list[0]
      if (first) {
        setProduct(first.product); setDraw(first.draw_number)
        if (g !== 'bomben') { loadAnalysis(first.product, first.draw_number); loadPayouts(first.product, first.draw_number) }
        else setLoading(false)   // Bomben har egen vy som hämtar själv
      } else { setLoading(false); setErr('Inga öppna omgångar just nu.') }
    } catch (e) { setErr(String(e)); setLoading(false) }
  }

  const changeDraw = (slug, dn) => {
    setProduct(slug); setDraw(dn); setSys(null); setPicks({}); setPickRows(null)
    if (slug !== 'bomben') { loadAnalysis(slug, dn); loadPayouts(slug, dn) }
  }

  const loadSystem = async (extra = '') => {
    if (typeof extra !== 'string') extra = ''   // knappen skickar klick-eventet hit
    setErr(null)
    try {
      let q = (systemTypes.find((t) => t.id === sysType) || SYSTEM_BASE[0]).q
      if (q.endsWith('guarantee=')) q += Math.max(1, nMatches - 1)  // garanti = n-1
      const vw = valueWeight / 100
      const jp = payouts?.jackpot != null ? `&jackpot=${encodeURIComponent(payouts.jackpot)}` : ''
      const r = await fetch(`/api/system?product=${product}&draw=${draw}&strategy=${encodeURIComponent(strategy)}&budget=${budget}&value_weight=${vw}&${q}${jp}${extra}&_t=${Date.now()}`, { cache: 'no-store' })
      if (!r.ok) throw new Error((await r.json()).detail || `System ${r.status}`)
      setSys(await r.json())
    } catch (e) { setErr(String(e)) }
  }

  // Förstagångsladdning: återställ sparad omgång + kupong om den fortfarande
  // finns kvar i listan (annars första öppna). Gör iOS-omladdningen osynlig.
  const bootstrap = async () => {
    const g = SAVED.group || 'topptipset'
    if (g === 'oddset') return  // egen vy, inga omgångar att hämta
    setLoading(true); setErr(null)
    try {
      const d = await (await fetch(`/api/draws?product=${g}&_t=${Date.now()}`, { cache: 'no-store' })).json()
      const list = d.open?.length ? d.open : d.draws
      setDraws(list)
      const restored = list.find((x) => x.product === SAVED.product && x.draw_number === SAVED.draw)
      const chosen = restored || list[0]
      if (chosen) {
        setProduct(chosen.product); setDraw(chosen.draw_number)
        if (!restored) { setPicks({}); setPickRows(null) }   // annan omgång -> börja om med tom kupong
        if (g !== 'bomben') {
          loadAnalysis(chosen.product, chosen.draw_number)
          loadPayouts(chosen.product, chosen.draw_number)
        } else setLoading(false)
      } else { setLoading(false); setErr('Inga öppna omgångar just nu.') }
    } catch (e) { setErr(String(e)); setLoading(false) }
  }

  useEffect(() => { bootstrap() }, [])  // eslint-disable-line

  // spara tillståndet löpande så iOS-omladdningen kan återställa det
  useEffect(() => {
    try {
      localStorage.setItem('svs_state', JSON.stringify({
        group, product, draw, picks, strategy, budget, sysType, valueWeight,
        // radläget kan vara stort — spara bara rimliga storlekar
        pickRows: pickRows && pickRows.length <= 2048 ? pickRows : null,
      }))
    } catch { /* lagring kan vara avstängd – strunta */ }
  }, [group, product, draw, picks, pickRows, strategy, budget, sysType, valueWeight])

  return (
    <div className="app">
      <header>
        <h1>⚽ Spelkompisen</h1>
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

      <div className="topinfo statusbar">
        {analysis && group !== 'bomben' && (
          <>
            <span>Omsättning <b>{analysis.turnover ? kr(analysis.turnover) : '–'}</b></span>
            <span>hämtat <b>{fmtFetched(analysis.fetched_at)}</b></span>
            {payouts?.available && <span>prispott <b>{kr(payouts.tiers?.[0]?.pool)}</b></span>}
            {payouts?.available && (
              <span title="Andel av omsättningen som betalas tillbaka, inkl. ev. jackpot. 'Nu' räknar mot nuvarande omsättning; prognosen mot medianen av senaste omgångarnas slutomsättning — den siffran är den ärliga.">
                spelvärde <b>{Math.round((payouts.spelvarde || payouts.ratio || 0) * 100)} %</b>
                {payouts.projected_turnover > payouts.turnover && (
                  <> → <b>{Math.round((payouts.spelvarde_proj || 0) * 100)} %</b> vid slutoms. {kr(payouts.projected_turnover)}</>
                )}
              </span>
            )}
            {payouts?.jackpot > 0 && (
              <span className="jackpot" title={payouts.extra_info || 'Jackpot/rullpott läggs på toppvinsten'}>
                💰 <b>Jackpot {kr(payouts.jackpot)}</b>
              </span>
            )}
          </>
        )}
        <Collection />
      </div>
      {err && <div className="error">{err}</div>}
      {loading && <div className="loading">Hämtar…</div>}

      {group === 'bomben' && <ErrBoundary><BombenView draw={draw} nonce={bombenNonce} /></ErrBoundary>}

      {group === 'oddset' && <ErrBoundary><OddsetView /></ErrBoundary>}

      {group !== 'bomben' && group !== 'oddset' && (<>
      <div className="cols main-cols">
      <section>
        <div className="analys-head">
          <h2>Analys — klicka tecken för kupong</h2>
          <span className="hovertip">💡 håll muspekaren över ett odds för hela rörelsen (SvS + Pinnacle), eller över en badge för förklaring</span>
        </div>
        <Legend />
        {analysis && (Object.keys(picks).length > 0 || pickRows) && (
          <div className="restored">
            🔁 Grönmarkeringarna är din <b>sparade kupong</b> sedan förra besöket
            {pickRows ? ` (${pickRows.length} rader)` : ` (${Object.keys(picks).length} matcher)`}
            {' '}— sparas så en omladdning inte tappar den.
            <button onClick={clearCoupon}>Rensa</button>
          </div>
        )}
        {analysis && (
          <AnalysisTable matches={analysis.matches} product={product} drawNumber={analysis.draw_number}
            selected={selected} onSelect={setSelected} picks={picks} onToggleSign={toggleSign} movement={movement}
            rowShares={rowShares} />
        )}
      </section>

        <section className="buildbar">
          <h2>Bygg förslag</h2>
          <div className="controls">
            {STRATEGIES.map((s) => (
              <label key={s} className={strategy === s ? 'active' : ''}>
                <input type="radio" name="strategy" checked={strategy === s}
                  onChange={() => { setStrategy(s); setValueWeight(STRATEGY_EV[s]) }} />{s}
              </label>
            ))}
            <label className="budget" title="Tak för insatsen. Systemet fylls upp mot taket; exakt belopp går inte alltid att träffa eftersom rader är produkter av 2 och 3.">
              Max budget <b>{budget} kr</b>
              <input type="range" min="0" max={BUDGET_STOPS.length - 1} step="1"
                value={budgetIdx}
                onChange={(e) => setBudget(BUDGET_STOPS[Number(e.target.value)])} />
            </label>
            <select value={sysType} onChange={(e) => setSysType(e.target.value)}>
              {systemTypes.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
            <button className="primary" onClick={loadSystem}>Föreslå rad</button>
          </div>
          <div className="evscale" title="Risk-axeln. I Värderader rankas raderna på träffchans^k × EV: lågt reglage = träffsäkra värderader (spelbart för 100–500 kr), mitten = balans (≈ max P×EV), högt = max EV (skrälltungt, sällan träff). I övriga system styr reglaget teckenvalet. Strategin sätter startpunkten – dra för att finjustera.">
            <span>Träffbart <em>(säker)</em></span>
            <input type="range" min="0" max="100" step="5" value={valueWeight}
              onChange={(e) => setValueWeight(Number(e.target.value))} />
            <span><em>(tuff)</em> Max EV</span>
            <span className="evval">{valueWeight}%</span>
            {valueWeight !== STRATEGY_EV[strategy] && (
              <button className="evreset" title={`Återställ till ${strategy} (${STRATEGY_EV[strategy]}%)`}
                onClick={() => setValueWeight(STRATEGY_EV[strategy])}>↺ följ {strategy}</button>
            )}
          </div>
          <SystemView sys={sys} matches={analysis?.matches} payouts={payouts}
            onRecalc={loadSystem} onUse={useSystem} />
        </section>
      </div>

      <section id="kupong">
        <h2>Din kupong — granska & lämna in</h2>
        {analysis && (
          <CouponPanel matches={analysis.matches} picks={picks} pickRows={pickRows} payouts={payouts}
            product={product} draw={draw} onClear={clearCoupon} />
        )}
      </section>

      <div className="cols">
        <section>
          <h2>Sharp-odds & steam</h2>
          <SharpPanel product={product} draw={draw} onLoaded={() => loadAnalysis()} />
          <SteamPanel product={product} draw={draw} matches={analysis?.matches} />
        </section>

        <section>
          <h2>Signal-facit (CLV)</h2>
          <ClvPanel group={group} />
        </section>
      </div>
      </>)}

      <footer>Lokal data från Svenska Spel + Pinnacle · personligt verktyg</footer>
    </div>
  )
}
