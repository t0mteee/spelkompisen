import { Fragment, useCallback, useEffect, useEffectEvent, useRef, useState } from 'react'
import './App.css'
import { payoutMatchesSelection } from './poolSelection.js'
import { kompaktKr, playRecommendation, projectionBasisText } from './playRec.js'
import { fmt, timeAgo, fmtTs, fmtClose, fmtFetched, fmtStart, kr, pct } from './lib/format.js'
import { VARIANT, FAMILY } from './lib/families.js'
import { folkProb, couponStats, systemStats } from './lib/poolEv.js'
import { useStoredBool, LoadingState, EmptyState, ErrorState, ErrBoundary } from './components/ui.jsx'
import { useSortedRows, SortableTable } from './components/SortableTable.jsx'
import { StreckBar, changePoints, MovementChart } from './components/charts.jsx'
import { oddsetBestValue, OddsetView } from './oddset/OddsetView.jsx'

const STRATEGIES = ['säker', 'medel', 'tuff']
// strategin sätter en startpunkt på EV-/värdereglaget (samma axel), så de inte krockar
const STRATEGY_EV = { säker: 20, medel: 50, tuff: 80 }
// budgetsteg (tak för insatsen) – slider istället för sifferfält.
// 144 är en exakt Hamming-täckning (R 4-4-144) och ingår i PH3:s
// benchmarkmatris sedan 2026-08-05, så reglaget måste kunna nå den.
const BUDGET_STOPS = [16, 32, 48, 64, 96, 128, 144, 192, 256, 384, 512, 768, 1024, 1536, 2048]
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
        ℹ️ Vad betyder färgerna & symbolerna? {open ? '▲' : '▼'}
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
            {' '}<b className="m-rlm-fade">⚠️</b> folket strömmar in medan sharp säljer — undvik/fadea.</div>
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
        {o.tags?.includes('rlm_fade') && <span className="m-rlm-fade" title={`Varning (RLM): folket strömmar in (+${o.streck_move} pp) medan sharp säljer (${o.steam_pp} pp devigad) — undvik/fadea`}>⚠️</span>}
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

function SystemView({ sys, matches, payouts, onRecalc, onUse, label = null,
  actionLabel = '⬇ Lägg i kupongen', showHonesty = true }) {
  const [mfCopied, setMfCopied] = useState(false)
  // Ärlig byggartext för 13-matchsspelen (PH5-radvalsablationen) — bara text,
  // ingen logikändring. Produkt ur payouts; 13 matcher = Stryk/Europa som fallback.
  const honest13 = showHonesty && (payouts?.product
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
        {label && <span className="system-variant">{label}</span>}
        <strong>{sys.system_type}</strong> · {sys.strategy} ·
        <span className="rows"> {sys.num_rows} rader = {sys.cost} kr</span>
        <button className="primary useb" onClick={onUse}>{actionLabel}</button>
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
            Poisson kring utfallets faktiska streckkombination;
            {mc.top_tier_kappa_by_x
              ? ' Radform v1 använder separat κ för 0, 1, 2, 3 och 4+ X.'
              : ` κ=${mc.kappa.toFixed(2)} är fortsatt konservativt.`}
            {' '}Percentiler beskriver risk, inte en garanterad utdelning.
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
            <div className="rule" title={`Potterna växer mot spelstopp men det gör medvinnarna också.${payouts.projection_basis ? `\nPrognosgrund: ${projectionBasisText(payouts.projection_basis)}.` : ''}`}>
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
function egnaRaderFilename(product, draw) {
  const safeProduct = String(product || 'poolspel').replace(/[^a-z0-9_-]/gi, '-')
  return `svs_${safeProduct}_omg${draw}_egnarader.txt`
}
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
  const [svsHandoff, setSvsHandoff] = useState(null)
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
          label: `${product} ${draw}${buildConfig?.label ? ` · ${buildConfig.label}` : ''}`,
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
  const egnaFilename = egnaRaderFilename(product, draw)
  const svsHandoffStatus = svsHandoff?.pickRows === pickRows && svsHandoff?.picks === picks
    ? svsHandoff.status : null
  const downloadEgna = () => {
    if (nRows > 50000) {
      alert(`Systemet är för stort (${nRows} rader) för filexport.`)
      return false
    }
    const rows = rowMode ? pickRows : cartesianRows(couponGroups)
    downloadText(egnaFilename, egnaRaderText(product, draw, rows))
    return true
  }
  const continueAtSvs = (event) => {
    if (!egnaUrl || !downloadEgna()) {
      event.preventDefault()
      return
    }
    // Länken öppnar SvS som ett vanligt användarklick (inte som en popup),
    // samtidigt som rätt fil skapas. Användaren väljer fil, granskar och
    // betalar alltid själv där.
    setSvsHandoff({ status: 'prepared', pickRows, picks })
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
            {egnaUrl ? (
              <a className="svs-handoff" href={egnaUrl} target="_blank" rel="noreferrer"
                onClick={continueAtSvs}
                title="Skapar rätt Egna rader-fil och öppnar Svenska Spels uppladdning. Du väljer filen, granskar och betalar själv där.">
                🎟 Fortsätt hos Svenska Spel
              </a>
            ) : (
              <a className="svs-link" href={svsUrl(product, draw)} target="_blank" rel="noreferrer">▶ Öppna omgången på Svenska Spel ↗</a>
            )}
            {egnaUrl && <button onClick={downloadEgna}
              title={`Laddar bara ner ${nRows} rader som .txt i Svenska Spels Egna rader-format`}>
              ⬇ Bara filen ({nRows} rad{nRows === 1 ? '' : 'er'})
            </button>}
            <button onClick={copyCoupon} title={rowMode ? 'Kopierar alla rader, en per rad' : 'Kopierar valda tecken per match'}>
              {copied ? '✓ Kopierad' : rowMode ? `Kopiera ${nRows} rader` : 'Kopiera kupong'}</button>
            {rowMode && pickRows.length > 0 && (
              <button className={playedStatus ? 'playedbtn on' : 'playedbtn'}
                onClick={markPlayed} disabled={playedStatus === 'sparar'}
                title="Bokför att DU har lämnat in den här kupongen hos Svenska Spel. Inget spel läggs härifrån — knappen ger facit per kupong och livestatus för reducerade system under omgången.">
                {playedStatus === true ? '✓ Bokförd som spelad'
                  : playedStatus === 'sparar' ? 'Sparar…' : '🎟️ Markera som spelad'}</button>
            )}
          </div>
          {svsHandoffStatus && (
            <div className="svs-ready">
              <b>Filen är klar:</b> <code>{egnaFilename}</code>
              <span>På Svenska Spel: tryck <b>Ladda upp</b> och välj den senaste filen.
                Granska sedan spelet och betala själv.</span>
            </div>
          )}
          {egnaUrl ? (
            <p className="hint"><b>Fortast:</b> knappen ovan skapar filen och öppnar{' '}
              <a className="extlink" href={egnaUrl} target="_blank" rel="noreferrer">Svenska Spel · Externa systemspel ↗</a>
              {' '}i samma tryck. Svenska Spel kräver fortfarande att du väljer filen och
              bekräftar betalningen; inget spel lämnas automatiskt.</p>
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
  // Ingen variantetikett: Topptipset är Topptipset. Dagens/Stryk/Extra är
  // omgångsserier hos Svenska Spel, inte olika spel — omgångsnumret skiljer
  // dem åt där det behövs.
  return `${PRODUCT_LABEL[c.product] || c.product} · omgång ${c.draw_number}`
}
function couponDate(c) {
  if (!c?.draw_close) return 'datum saknas'
  const date = new Date(c.draw_close)
  if (Number.isNaN(date.getTime())) return 'datum saknas'
  return date.toLocaleDateString('sv-SE', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}
function couponKindLabel(c) {
  if (c?.build_kind === 'byggare-komplement-a') return 'Kupong A'
  if (c?.build_kind === 'byggare-komplement-b') return 'Kupong B'
  const suffix = String(c?.label || '').split('·').map((part) => part.trim()).at(-1)
  if (suffix && suffix !== c.label && !/^omgång\s/i.test(suffix)) return suffix
  if (c?.build_kind === 'byggare') return 'Förslag'
  return c?.build_kind || null
}
function couponTitle(c) {
  const kind = couponKindLabel(c)
  return `${couponLabel(c)}${kind ? ` · ${kind}` : ''}`
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

/* VILKA rader som lever. Nivåtabellen säger "2 rader kvar till 8 rätt" men
   pekar inte ut någon av dem — på en kupong med hundratals rader är det inte
   handlingsbart. Här står radnumret, hur många rätt raden har säkrat och,
   det som faktiskt betyder något, vilket tecken den behöver i varje match som
   ÄR KVAR.

   Listan hänger på en VALD NIVÅ, inte på "kan nå något". Topptipset har åtta
   matcher men bara 8 rätt delar potten, så "lever mot golvnivån" var 184 av
   256 rader och sa ingenting. Nivåknapparna bär `alive_per_level`, som är
   räknad på hela kupongen och därför sann även när radlistan är kapad.

   En struken match och ett obelagt förlängningstecken räknas som kvarvarande,
   så raden visas med det tecken den BEHÖVER — aldrig med ett tecken vi gissat
   åt Svenska Spel. */
function AliveRowsTable({ live }) {
  const [open, setOpen] = useState(false)
  const [level, setLevel] = useState(null)
  const rows = live?.alive_rows || []
  const cols = live?.alive_rows_open_cols || []
  const perLevel = live?.alive_per_level || {}
  const levels = Object.keys(perLevel).map(Number)
    .filter((l) => perLevel[l] > 0).sort((a, b) => b - a)
  if (!rows.length || !cols.length || !levels.length) return null
  const shownLevel = level != null && perLevel[level] ? level : levels[0]
  const held = rows.filter((r) => r.possible >= shownLevel)
  const truth = perLevel[shownLevel]
  const byCol = Object.fromEntries((live.matches || []).map((m) => [m.col, m]))
  const label = (col) => {
    const m = byCol[col]
    if (!m) return `M${col}`
    return m.home || (m.description || '').split(/\s+[–-]\s+/)[0] || `M${col}`
  }
  const full = (col) => {
    const m = byCol[col]
    return m ? (m.description || [m.home, m.away].filter(Boolean).join(' – ')) : `Match ${col}`
  }
  return (
    <div className="aliverows">
      <button className="linkbtn" onClick={() => setOpen(!open)}
        title="Radnummer, säkrade rätt och vilket tecken varje överlevande rad behöver i matcherna som är kvar.">
        {open ? 'Dölj vilka rader' : 'Visa vilka rader'}
      </button>
      {open && (
        <>
          <div className="aliverows-levels">
            {levels.map((l) => (
              <button key={l} type="button"
                className={l === shownLevel ? 'on' : ''}
                onClick={() => setLevel(l)}
                title={`${perLevel[l]} rader kan fortfarande nå ${l} rätt`}>
                {l} rätt<i>{perLevel[l]}</i>
              </button>
            ))}
          </div>
          <div className="tablewrap">
            <table className="grid compact aliverows-table">
              <thead>
                <tr>
                  <th title="Radens nummer i kupongen, i samma ordning som filen du lämnade in.">rad</th>
                  <th title="Rätt som redan står fast.">rätt nu</th>
                  {/* `max` är `rätt nu` plus antalet kvarvarande matcher —
                      samma konstant för varje rad. Bekvämt på desktop, men
                      det är den kolumn som får stryka på foten när tre
                      matchkolumner ska rymmas på 375 px. */}
                  <th className="ar-max"
                    title="Bästa antal rätt raden fortfarande kan nå.">max</th>
                  {cols.map((col) => (
                    <th key={col} title={full(col)}>
                      {/* Matchnumret binder kolumnen till liverättningen
                          ovanför. Lagnamnet kortas på mobil, numret aldrig. */}
                      <i>{col}</i><span>{label(col)}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {held.map((r) => (
                  <tr key={r.n}>
                    <td className="hint">{r.n}</td>
                    <td><b>{r.secure}</b></td>
                    <td className="ar-max">{r.possible}</td>
                    {r.open.map((o) => (
                      <td key={o.col} className="ar-sign">{o.sign}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Radlistan är kapad; nivåräknaren är det inte. Säg vilket tal som
              är hela sanningen i stället för att låta tabellhöjden ljuga. */}
          {truth > held.length && (
            <p className="hint">Visar {held.length} av {truth} rader som kan nå
              {' '}{shownLevel} rätt — de med flest säkrade rätt.</p>
          )}
        </>
      )}
    </div>
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
  const liveSourceNames = { svenskaspel: 'SvS', ninja: 'Ninja', pinnacle: 'Pinnacle' }
  const liveSourceText = Object.entries(live?.chance_live_source_counts || {})
    .map(([source, count]) => `${liveSourceNames[source] || source} ${count}`)
    .join(', ')
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
            <span title="Rätt i matcher vars resultat redan står fast.">
              fastställt bäst <b>{live.best_secure}</b> rätt
            </span>
            {live.current_known > 0 && live.current_best != null && (
              <span className={live.current_best === live.n_events ? 'pos' : ''}
                title="Bästa radens rätt om alla aktuella ställningar blir slutresultat. Pågående matcher kan fortfarande ändras.">
                om det slutar som nu <b>{live.current_best}</b>/{live.current_known}
                {live.current_best_rows > 0
                  ? ` · ${live.current_best_rows} rad${live.current_best_rows === 1 ? '' : 'er'}`
                  : ''}
              </span>
            )}
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
            <thead><tr><th>nivå</th><th>rader kvar</th>
              <th title="Oddsbaserad sannolikhet att kupongen når nivån när alla pågående matcher är slut. Inte andelen rätt just nu.">chans att nå</th>
            </tr></thead>
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
          {!live.out_of_contention && <AliveRowsTable live={live} />}
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
                  ställningen är alltså inräknad
                  {liveSourceText && <> ({liveSourceText})</>}.</>}
                {/* Modellskattningen är inget marknadspris och får aldrig läsas
                    som ett. Den syns bara på kupongen, aldrig i värde/CLV. */}
                {live.chance_modelled_matches > 0 && <> <b>{live.chance_modelled_matches}</b>
                  {live.chance_modelled_matches === 1 ? ' match saknar' : ' matcher saknar'} öppen
                  livemarknad och är <b>skattad</b> ur ställning och tid kvar, ankrad i
                  spelbolagets prematchpris. Det är en uppskattning — inget marknadspris —
                  och den påverkar aldrig värdespel eller facit.</>}
              </>}
          </p>
        </>
      )}
    </div>
  )
}

/* Ett avgjort systems exakta rader mot settlementkanonens facit. Hämtas
   först när användaren öppnar kupongen: 5 000-raderstester ska inte göra den
   vanliga Historik-vyn tung. */
function PlayedCouponDetail({ coupon, onClose }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)
  const [showAll, setShowAll] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/pool/played/${coupon.id}`, {
      cache: 'no-store', signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    }).then(setDetail).catch((reason) => {
      if (reason?.name !== 'AbortError') setError(reason?.message || 'Okänt fel')
    })
    return () => controller.abort()
  }, [coupon.id])
  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const events = detail?.events || []
  const rows = detail?.rows || []
  const shownRows = showAll ? rows : rows.slice(0, 30)
  const distribution = Object.entries(detail?.correct_dist || {})
    .map(([correct, count]) => [Number(correct), Number(count)])
    .sort((a, b) => b[0] - a[0])
  const eventName = (event) => [event.home, event.away].filter(Boolean).join(' – ')
    || event.description
    || `Match ${event.column}`
  return (
    <div className="played-detail-backdrop" onMouseDown={onClose}>
      <section className="played-detail" role="dialog" aria-modal="true"
        aria-labelledby="played-detail-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="played-detail-head">
          <div>
            <span>Rättad testkupong</span>
            <h3 id="played-detail-title">{couponTitle(coupon)}</h3>
            <p>{couponDate(coupon)} · {coupon.n_rows} rader · {kr(coupon.cost_kr)}</p>
          </div>
          <button onClick={onClose} aria-label="Stäng kupongdetaljen">✕</button>
        </header>
        {error && <ErrorState message={`Kupongen kunde inte hämtas: ${error}`} />}
        {!detail && !error && <LoadingState label="Hämtar rader och facit…" />}
        {detail && (
          <div className="played-detail-body">
            <div className="played-detail-kpis">
              <span><b>{coupon.correct_max}</b> bäst rätt</span>
              <span><b>{coupon.payout_complete ? kr(coupon.payout_kr) : 'ofullständigt'}</b> utdelning</span>
              <span><b className={coupon.roi == null ? '' : coupon.roi >= 0 ? 'pos' : 'neg'}>
                {coupon.roi == null ? '–' : `${coupon.roi >= 0 ? '+' : ''}${Math.round(coupon.roi * 100)} %`}
              </b> ROI</span>
            </div>
            {!detail.audit_matches_stored && (
              <p className="played-detail-warning">Varning: den omräknade
                radfördelningen avviker från det sparade facitet.</p>
            )}
            <section>
              <h4>Officiellt facit, match för match</h4>
              <div className="played-facit-grid">
                {events.map((event) => (
                  <div key={event.column} className="played-facit-match">
                    <span>{event.column}</span>
                    <b>{eventName(event)}</b>
                    <em className={event.outcome ? 'known' : ''}>{event.outcome || '?'}</em>
                    {event.cancelled && <small>struken · fastställt tecken</small>}
                  </div>
                ))}
              </div>
            </section>
            <section>
              <h4>Så fördelades raderna</h4>
              <div className="played-dist">
                {distribution.map(([correct, count]) => (
                  <span key={correct}><b>{count}</b> {count === 1 ? 'rad' : 'rader'} med {correct} rätt</span>
                ))}
              </div>
            </section>
            <section>
              <div className="played-rows-head">
                <div><h4>Raderna, bäst först</h4>
                  <p>Grönt tecken är rätt, rött är fel. # är radens plats i den sparade filen.</p></div>
                <b>{showAll ? rows.length : Math.min(30, rows.length)} av {rows.length}</b>
              </div>
              <div className="played-row-results">
                {shownRows.map((row) => (
                  <div className={`played-row-result${row.payout_kr > 0 ? ' prize' : ''}`}
                    key={row.index}>
                    <span className="played-row-number">#{row.index}</span>
                    <div className="played-row-signs"
                      style={{ '--played-cols': Math.max(1, events.length) }}>
                      {[...row.signs].map((sign, index) => {
                        const outcome = events[index]?.outcome
                        return <span key={index}
                          className={!outcome ? '' : sign === outcome ? 'hit' : 'miss'}
                          title={`${eventName(events[index] || { column: index + 1 })}: ${sign}, facit ${outcome || '?'}`}>
                          {sign}
                        </span>
                      })}
                    </div>
                    <b>{row.correct == null ? '–' : `${row.correct}/${events.length}`}</b>
                    {row.payout_kr > 0
                      ? <em>+{kr(row.payout_kr)}</em>
                      : row.prize_level && row.payout_kr == null
                        ? <em>belopp saknas</em> : null}
                  </div>
                ))}
              </div>
              {rows.length > 30 && (
                <button className="played-show-all" onClick={() => setShowAll((value) => !value)}>
                  {showAll ? 'Visa bara de 30 bästa' : `Visa samtliga ${rows.length} rader`}
                </button>
              )}
            </section>
          </div>
        )}
      </section>
    </div>
  )
}

function PlayedFileImport({ onImported }) {
  const [savedFile, setSavedFile] = useState(null)
  const [manualProduct, setManualProduct] = useState('')
  const [manualDraw, setManualDraw] = useState('')
  const [preview, setPreview] = useState(null)
  const [checkedPayload, setCheckedPayload] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const inputRef = useRef(null)
  const inspectRef = useRef(0)

  const changeOverride = (setter, value) => {
    ++inspectRef.current
    setter(value); setBusy(false); setPreview(null); setCheckedPayload(null)
    setError(''); setMessage('')
  }

  const payload = (file = savedFile) => ({
    filename: file?.name || '', text: file?.text || '',
    product: manualProduct || undefined,
    draw_number: manualDraw || undefined,
  })
  const inspect = async (file = savedFile, requestId = null) => {
    if (!file) return
    const id = requestId ?? ++inspectRef.current
    const checked = payload(file)
    setBusy(true); setError(''); setMessage(''); setPreview(null); setCheckedPayload(null)
    try {
      const response = await fetch('/api/pool/played/import/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(checked),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
      if (inspectRef.current === id) {
        setCheckedPayload(checked)
        setPreview(result.preview)
      }
    } catch (caught) {
      if (inspectRef.current === id) {
        setError(caught.message || 'Filen kunde inte kontrolleras')
      }
    } finally {
      if (inspectRef.current === id) setBusy(false)
    }
  }
  const chooseFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    const requestId = ++inspectRef.current
    setBusy(true); setError(''); setMessage(''); setPreview(null); setCheckedPayload(null)
    try {
      const saved = { name: file.name, text: await file.text() }
      if (inspectRef.current !== requestId) return
      setSavedFile(saved)
      await inspect(saved, requestId)
    } catch {
      if (inspectRef.current === requestId) {
        setBusy(false)
        setError('Filen kunde inte läsas på den här enheten')
      }
    }
  }
  const confirm = async () => {
    if (!checkedPayload || !preview || preview.duplicate) return
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch('/api/pool/played/import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(checkedPayload),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
      setMessage(result.created
        ? `✓ ${preview.n_rows.toLocaleString('sv-SE')} rader bokförda och följs nu.`
        : 'Kupongen var redan bokförd.')
      setPreview(null); setCheckedPayload(null); setSavedFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onImported?.()
    } catch (caught) {
      setError(caught.message || 'Kupongen kunde inte bokföras')
    } finally { setBusy(false) }
  }

  return (
    <section className="played-import">
      <div className="played-import-head">
        <div><b>Glömde du ”Spelad kupong”?</b>
          <span>Läs in den sparade Egna rader-filen och bokför spelet i efterhand.</span></div>
        <label className="played-import-file">
          <span>{busy ? 'Kontrollerar…' : 'Välj radfil'}</span>
          <input ref={inputRef} type="file" accept=".txt,text/plain"
            disabled={busy} onChange={chooseFile} />
        </label>
      </div>
      <p className="hint">Filen läses och kontrolleras här, men skickas aldrig till
        Svenska Spel och lägger inget nytt spel. Bekräfta bara kuponger du faktiskt betalade.</p>
      <details className="played-import-manual">
        <summary>Har filen döpts om och saknar omgång?</summary>
        <div>
          <label>Spel<select value={manualProduct}
            onChange={(event) => changeOverride(setManualProduct, event.target.value)}>
            <option value="">Läs från filen</option>
            <option value="stryktipset">Stryktipset</option>
            <option value="europatipset">Europatipset</option>
            <option value="topptipset">Topptipset · Dagens</option>
            <option value="topptipsetstryk">Topptipset · Stryk</option>
            <option value="topptipsetextra">Topptipset · Extra</option>
          </select></label>
          <label>Omgång<input type="number" min="1" inputMode="numeric"
            value={manualDraw} placeholder="t.ex. 4968"
            onChange={(event) => changeOverride(setManualDraw, event.target.value)} /></label>
          <button disabled={!savedFile || busy} onClick={() => inspect()}>
            Kontrollera igen</button>
        </div>
      </details>
      {error && <div className="played-import-status bad">⚠️ {error}</div>}
      {message && <div className="played-import-status good">{message}</div>}
      {preview && (
        <div className="played-import-preview">
          <div><b>{PRODUCT_LABEL[preview.product] || preview.product} · omgång {preview.draw_number}</b>
            <span>{preview.n_rows.toLocaleString('sv-SE')} rader · {preview.n_events} matcher
              {' · '}{kr(preview.cost_kr)}</span></div>
          {!preview.draw_known && <span className="played-import-warn">Omgången finns inte
            lokalt ännu. Den börjar samlas in och följas efter bokföringen.</span>}
          {preview.duplicate
            ? <span className="played-import-ok">✓ Exakt den här kupongen är redan bokförd.</span>
            : <button disabled={busy} onClick={confirm}>Bokför och följ kupongen</button>}
        </div>
      )}
    </section>
  )
}

// `product` = null visar alla spel; annars filtreras allt till ett. Summeringen
// räknas om på det filtrerade urvalet — en ROI som gäller alla spel får inte
// stå kvar som rubrik när tabellen bara visar ett.
function PlayedPanel({ product = null }) {
  const [data, setData] = useState(null)
  const [detailCoupon, setDetailCoupon] = useState(null)
  const requestRef = useRef(0)
  const abortRef = useRef(null)
  const load = useCallback(async () => {
    const requestId = ++requestRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const stamp = Date.now()
    const current = () => requestRef.current === requestId && !controller.signal.aborted
    const read = async (url) => {
      const response = await fetch(url, { cache: 'no-store', signal: controller.signal })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    }
    try {
      const local = await read(`/api/pool/played?live=false&_t=${stamp}`)
      if (!current()) return
      const hasOpen = (local.coupons || []).some((coupon) => !coupon.settled_at)
      // BEHÅLL föregående livestatus medan den nya hämtas. Utan det blir
      // kortet tomt varje minut och allt öppet detaljtillstånd nollställs.
      setData((previousData) => {
        if (!current()) return previousData
        const previous = Object.fromEntries(
          (previousData?.coupons || []).filter((c) => c.live).map((c) => [c.id, c.live]))
        return {
          ...local,
          coupons: (local.coupons || []).map((coupon) => (
            !coupon.settled_at && hasOpen
              ? { ...coupon, live_pending: true, live: previous[coupon.id] }
              : coupon
          )),
        }
      })
      if (!hasOpen) return

      // TRE steg. Chansen över hela utfallsrummet är dyr, men den snabba
      // liverättningen och fullsvaret återanvänder nu exakt samma kortlivade
      // livebild på servern — inga dubbla bokanrop och inget blandat ögonblick.
      try {
        const quick = await read(`/api/pool/played?chance=false&_t=${stamp}`)
        if (current()) setData({
          ...quick,
          coupons: (quick.coupons || []).map((coupon) => (
            coupon.settled_at ? coupon : { ...coupon, live_pending: true }
          )),
        })
      } catch (error) {
        if (error?.name === 'AbortError' || !current()) return
        // Fullsvaret kan fortfarande lyckas; snabbvägens fel är inte slutligt.
      }
      if (!current()) return
      try {
        const full = await read(`/api/pool/played?_t=${stamp}`)
        if (current()) setData(full)
      } catch (error) {
        if (error?.name === 'AbortError' || !current()) return
        setData((previousData) => previousData ? {
          ...previousData,
          coupons: (previousData.coupons || []).map((coupon) => (
            coupon.settled_at ? coupon : {
              ...coupon,
              live_pending: false,
              live_error: error?.name || 'FetchError',
            }
          )),
        } : previousData)
      }
    } catch (error) {
      if (error?.name !== 'AbortError' && current()) {
        setData((previousData) => previousData || { coupons: [] })
      }
    }
  }, [])
  useEffect(() => {
    load()
    const timer = window.setInterval(load, 60_000)
    return () => {
      window.clearInterval(timer)
      abortRef.current?.abort()
    }
  }, [load])
  if (!data) return <LoadingState label="Hämtar spelade kuponger…" />
  const all = data.coupons || []
  // Familjejämförelse: väljs Topptipset ska Dagens, Stryk och Extra alla med.
  // Varje kupong visar sin variant i etiketten, så inget går förlorat.
  const coupons = product ? all.filter((c) => FAMILY(c.product) === FAMILY(product)) : all
  const settled = coupons.filter((c) => c.settled_at)
  const spent = settled.reduce((a, c) => a + (c.cost_kr || 0), 0)
  const won = settled.reduce((a, c) => a + (c.payout_kr || 0), 0)
  const s = product
    ? { n_coupons: coupons.length, n_settled: settled.length,
        n_open: coupons.length - settled.length, spent_kr: spent, won_kr: won,
        roi: spent > 0 ? won / spent - 1 : null }
    : (data.summary || {})
  const forget = async (id) => {
    await fetch(`/api/pool/played/${id}`, { method: 'DELETE' }); load()
  }
  // Pågående kuponger är det man faktiskt följer — de får egna kort överst.
  // Avgjorda är arkiv och komprimeras till en rad var.
  const open_ = coupons.filter((c) => !c.settled_at)
  const done = settled
  return (
    <div className="playedbox">
      <PlayedFileImport onImported={load} />
      {!coupons.length ? <p className="hint">{all.length
        ? 'Inga bokförda kuponger för det här spelet.'
        : <>Inga bokförda kuponger än. Markera kupongen som spelad när du lämnar
          in den, eller importera den sparade radfilen ovan i efterhand.</>}</p> : <>
      <p className="hint played-summary" title={s.note}>
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
                value: (c) => PRODUCT_LABEL[c.product] || c.product },
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
              { key: 'detail', label: '', sortable: false },
            ]}
            renderRow={(c) => (
              <tr key={c.id}>
                <td><b>{PRODUCT_LABEL[c.product] || c.product}</b>
                  {couponKindLabel(c) && <span className="played-kind">{couponKindLabel(c)}</span>}</td>
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
                <td><button onClick={() => setDetailCoupon(c)}>Visa kupong</button></td>
              </tr>
            )}
            renderCard={(c) => (
              <article className="played-done-card" key={c.id}>
                <header><div><b>{couponTitle(c)}</b><span>{couponDate(c)}</span></div>
                  <strong className={c.roi == null ? '' : c.roi >= 0 ? 'pos' : 'neg'}>
                    {c.roi == null ? '–'
                      : `${c.roi >= 0 ? '+' : ''}${Math.round(c.roi * 100)} %`}</strong></header>
                <div><span><b>{c.n_rows}</b> rader</span><span><b>{kr(c.cost_kr)}</b> kostnad</span>
                  <span><b>{c.correct_max}</b> bäst rätt</span>
                  <span><b>{c.payout_complete ? kr(c.payout_kr) : 'ofullständig'}</b> utdelning</span></div>
                <button onClick={() => setDetailCoupon(c)}>Visa rader och facit</button>
              </article>
            )} />
        </>
      )}
      {detailCoupon && (
        <PlayedCouponDetail key={detailCoupon.id} coupon={detailCoupon}
          onClose={() => setDetailCoupon(null)} />
      )}
      </>}
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
            omgången: rullpott — spela</span>
          : <span className="playrec skip"
            title="Bomben återbetalar ~65 % — utan rullpott äter uttaget edgen; Poisson-modellens EV är modellhärledd och ingår inte i CLV-facitet.">
            omgången: avstå</span>)}
        <span>Omsättning <b>{kr(data.turnover)}</b></span>
        <span>{data.match_count} matcher · tippa exakt resultat</span>
        {data.jackpot > 0 && <span className="jackpot">💰 <b>Jackpot {kr(data.jackpot)}</b></span>}
        {!data.sharp_available && <span className="st-wait">⚠️ Pinnacle nere – ingen värdemodell, bara folkets streck</span>}
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
// Etiketten gäller OMGÅNGEN, aldrig kupongen bredvid den. Spelvärdet är
// payout_ratio (en KONSTANT per produkt: 0,598/0,637/0,700) + jackpot/omsättning,
// så utan extern subvention är utfallet alltid "avstå" — det är aritmetik, inte
// en bedömning av raderna. En etikett som bara kan anta ett värde bär noll
// information, så chipet visar i stället AVSTÅNDET till nästa tröskel: hur stor
// jackpot som saknas. Prefixet säger "omgången" av samma skäl — den tittar inte
// på ditt system, din EV eller κ.
function PlayRec({ payouts, product }) {
  const { sv, proj, level, gap } = playRecommendation(payouts)
  const thirteen = product === 'stryktipset' || product === 'europatipset'
  const label = level === 'go' ? 'jackpot — spela' : level === 'thin' ? 'tunt' : 'avstå'
  const need = gap != null ? kompaktKr(gap) : null
  // Pillret och avståndet är SKILDA element: poolkorten är 159 px breda på
  // mobil, så en enda nowrap-rad klipptes mitt i beloppet. Nu wrappar de i
  // stället till två rader och hela summan går att läsa.
  return (
    <span className="playrec-wrap" title={`Gäller OMGÅNGEN, inte din kupong — den tittar varken på ditt system, din EV eller κ. Prognostiserat spelvärde ${Math.round(sv * 100)} % = produktens återbetalning (${Math.round((payouts.payout_ratio || 0) * 100)} %, konstant) plus jackpot delat med omsättningen. Utan jackpot kan svaret därför inte bli något annat än avstå.${need ? ` Det krävs ${need} mer i jackpot för att nå ${sv >= 0.8 ? 'spelläge (100 %)' : 'tunt läge (80 %)'} vid ${proj ? 'prognostiserad' : 'nuvarande'} omsättning.` : ''} Under 80 %: uttaget äter mer än någon uppmätt radvalsfördel — avstå eller spela symboliskt. 80–100 %: tunt, spela smått; kräver att slå break-even-hurdlen på ${payouts.hurdle != null ? `+${Math.round(payouts.hurdle * 100)} %` : 'radvalet'} mot fältet. ≥100 %: jackpot/rullpott subventionerar fältet — det är då poolspel kan bära positiv EV.${thirteen ? ' OBS 13-matchsspel: radvalet har ingen påvisad fördel (PH5 2026-07-26) — spelvärdet är hela caset.' : ' Topptipset-spelen: radvalsfördel uppmätt +7–15 pp mot folk-/favoritrad (PH5, 3 976 omgångar), men vinst kommer i en minoritet av omgångarna — variansen är stor.'} Eventuella garantier (t.ex. ensamvinnargaranti) ingår medvetet INTE — villkoren är overifierade mot SvS regler.`}>
      <span className={`playrec ${level}`}>omgången: {label}</span>
      {need && <span className="playrec-gap">{level === 'thin' ? 'spela' : 'tunt'} vid +{need}</span>}
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
// Den här filen ÄR komponentbiblioteket (se CLAUDE.md): AppV3.jsx hämtar både
// komponenter, konstanter och helpers härifrån. Blandade exporter är alltså
// arkitekturen, inte ett misstag — priset är att fast refresh laddar om hela
// modulen i stället för att bevara state.
/* eslint-disable react-refresh/only-export-components */
export {
  AnalysisTable, SystemView, CouponPanel, SharpPanel, SteamPanel, ClvPanel,
  BombenView, OddsetView, Legend, Collection, LoadingState, EmptyState,
  ErrorState, ErrBoundary, STRATEGIES, STRATEGY_EV, BUDGET_STOPS,
  SYSTEM_BASE, SYSTEM_SVS, VARIANT, FAMILY, GAMES, kr, fmtClose, fmtFetched, timeAgo,
  PlayRec, PlayedPanel, oddsetBestValue, SortableTable, useSortedRows,
}
