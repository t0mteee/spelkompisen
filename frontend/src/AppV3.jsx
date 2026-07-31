// Appens skal (enda gränssnittet sedan 2026-07-26, då klassiska vyn revs).
// De tunga komponenterna (analys/bygg/kupong/oddset) importeras från App.jsx,
// som är komponentbiblioteket. Eget här: skalet med vyväxlingen samt
// Idag-översikten, Historik-vyn (PH1-settlementlagret) och Labb.
import { useEffect, useRef, useState } from 'react'
import './AppV3.css'
import {
  AnalysisTable, SystemView, CouponPanel, SharpPanel, SteamPanel, ClvPanel,
  BombenView, OddsetView, Legend, Collection, LoadingState, EmptyState,
  ErrorState, ErrBoundary, STRATEGIES, STRATEGY_EV, BUDGET_STOPS,
  SYSTEM_BASE, SYSTEM_SVS, VARIANT, kr, fmtClose, timeAgo, PlayRec,
  PlayedPanel, oddsetBestValue,
} from './App'

const VIEWS = [
  { id: 'idag', label: 'Idag', icon: '☀️' },
  { id: 'pool', label: 'Poolspel', icon: '🎟' },
  { id: 'oddset', label: 'Oddset', icon: '⚡' },
  { id: 'historik', label: 'Historik', icon: '🗄' },
  { id: 'labb', label: 'Labb', icon: '🧪' },
]
const POOL_GAMES = [
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
  { id: 'bomben', label: 'Bomben' },
]
const HIST_PRODUCTS = [
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'topptipsetstryk', label: 'Topptipset Stryk' },
  { id: 'topptipsetextra', label: 'Topptipset Extra' },
]

const get = (url) => fetch(`${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}`,
  { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })

const readState = () => {
  try { return JSON.parse(localStorage.getItem('svs_state') || '{}') || {} } catch { return {} }
}

function hoursTo(iso) {
  if (!iso) return null
  const h = (new Date(iso).getTime() - Date.now()) / 3600000
  return Number.isFinite(h) ? h : null
}
function closesIn(iso) {
  const h = hoursTo(iso)
  if (h == null) return ''
  if (h < 0) return 'stängd'
  if (h < 1) return `stänger om ${Math.max(1, Math.round(h * 60))} min`
  if (h < 48) return `stänger om ${Math.round(h)} h`
  return `stänger ${fmtClose(iso)}`
}
function fmtDay(iso) {
  if (!iso) return '–'
  try {
    return new Date(iso).toLocaleDateString('sv-SE', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch { return '–' }
}
const selLabel3 = (m, mk, sg, line) => {
  if (mk === '1x2') return sg === '1' ? `1 · ${m.home}` : sg === '2' ? `2 · ${m.away}` : 'X · Kryss'
  if (mk === 'ah') return `${sg === 'H' ? m.home : m.away} ${line > 0 && sg === 'H' ? '+' : ''}${sg === 'H' ? line : -line} AH`
  if (mk === 'ou') return `${sg === 'O' ? 'Över' : 'Under'} ${line} mål`
  return `${sg === 'O' ? 'Över' : 'Under'} ${line} hörnor`
}

function MiniSpark({ values, width = 220, height = 44 }) {
  const vals = (values || []).filter((v) => v != null)
  if (vals.length < 2) return null
  const min = Math.min(...vals), max = Math.max(...vals)
  const span = max - min || 1
  const pts = vals.map((v, i) =>
    `${(i / (vals.length - 1)) * width},${height - 4 - ((v - min) / span) * (height - 8)}`).join(' ')
  return (
    <svg className="v3spark" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

/* ================================ Idag ==================================== */

function DashboardV3({ openPool, openOddset, openHistorik, openLabb }) {
  const [pool, setPool] = useState(null)
  const [oddset, setOddset] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [hist, setHist] = useState(null)
  const [systems, setSystems] = useState(null)
  const [played, setPlayed] = useState(null)
  const [err, setErr] = useState(null)

  const load = () => {
    Promise.all(POOL_GAMES.map(async (g) => {
      try {
        const d = await get(`/api/draws?product=${g.id}`)
        const list = d.open?.length ? d.open : d.draws || []
        // NÄSTA spelstopp = tidigaste framtida stängning bland öppna omgångar
        // (listan kan innehålla passerade/sena poster — lita inte på list[0])
        const upcoming = list
          .filter((x) => x.reg_close_time && new Date(x.reg_close_time) > new Date())
          .sort((a, b) => new Date(a.reg_close_time) - new Date(b.reg_close_time))
        const first = upcoming[0]
        if (!first) return { ...g, none: true }
        let pay = null
        if (g.id !== 'bomben') {
          pay = await get(`/api/payouts?product=${first.product}&draw=${first.draw_number}`).catch(() => null)
        }
        return { ...g, draw: first, pay, count: upcoming.length }
      } catch { return { ...g, none: true } }
    })).then(setPool).catch((e) => setErr(String(e)))
    get('/api/oddset/matches').then(setOddset).catch(() => setOddset(null))
    get('/api/oddset/predictions').then(setLedger).catch(() => setLedger(null))
    get('/api/pool/systems').then(setSystems).catch(() => setSystems(null))
    get('/api/pool/played').then(setPlayed).catch(() => setPlayed(null))
    Promise.all(HIST_PRODUCTS.map((p) =>
      get(`/api/pool/history?product=${p.id}&limit=1`).then((j) => [p.id, j]).catch(() => [p.id, null])
    )).then((pairs) => setHist(Object.fromEntries(pairs)))
  }
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') load()
    }
    load()
    const id = setInterval(tick, 120000)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [])  // eslint-disable-line

  // värdespel + rörelser ur samma payload som Oddset-vyn (sanerad: research bär inga).
  // Urvalet ligger i delade oddsetBestValue (App.jsx) — samma som 💰-korten/Rek.
  const signals = []
  const movers = []
  for (const m of oddset?.matches || []) {
    if (m.start && new Date(m.start) < new Date()) continue
    const best = oddsetBestValue(m)
    if (best) signals.push({ m, ...best })
    let move = null
    for (const [sg, sh] of Object.entries(m.steam || {})) {
      const pp = Math.max(sh.h6 ?? -99, sh.h24 ?? -99)
      if (pp >= 1.5 && (!move || pp > move.pp)) move = { m, sg, pp }
    }
    if (move) movers.push(move)
  }
  signals.sort((a, b) => (b.v.q ?? 0) - (a.v.q ?? 0))
  movers.sort((a, b) => b.pp - a.pp)

  const research = (oddset?.leagues || []).filter((l) => l.research)
  const researchMatches = (oddset?.matches || []).filter((m) => m.research)
  const nextResearch = researchMatches.map((m) => m.start).filter(Boolean).sort()[0]
  const primaryGroups = (ledger?.groups || []).filter((g) => g.primary && g.active_version)
  const statusIcon = (s) => s === 'green' ? '✓' : s === 'candidate' ? '◐' : '●'
  const histRows = HIST_PRODUCTS
    .map((p) => ({ ...p, sum: hist?.[p.id] }))
    .filter((r) => r.sum?.available)

  return (
    <div className="v3dash">
      {err && <ErrorState message={err} />}
      <div className="v3grid">
        <div className="v3card v3span2">
          <div className="v3cardhead"><h3>🎟 Nästa spelstopp</h3>
            <span className="v3hint">poolspelen just nu</span></div>
          {!pool && <LoadingState label="Hämtar omgångar…" />}
          <div className="v3stops">
            {(pool || []).map((g) => (
              <button key={g.id} className="v3stop" onClick={() => openPool(g.id)}>
                <b>{g.label}</b>
                {g.none ? <span className="v3hint">ingen öppen omgång</span> : (
                  <>
                    <span className={hoursTo(g.draw.reg_close_time) < 2 ? 'v3close soon' : 'v3close'}>
                      {closesIn(g.draw.reg_close_time)}</span>
                    <span className="v3hint">
                      {VARIANT[g.draw.product] ? `${VARIANT[g.draw.product]} · ` : ''}omg {g.draw.draw_number}
                      {g.count > 1 ? ` · +${g.count - 1} till` : ''}
                    </span>
                    {g.pay?.available && (
                      <span className="v3kpis">
                        <span title="Spelvärde vid spelstopp (prognos): total återbetalning inkl. jackpot mot prognostiserad omsättning">
                          spelvärde <b className={(g.pay.spelvarde_proj || g.pay.spelvarde || 0) >= 1 ? 'pos' : ''}>
                            {Math.round(((g.pay.spelvarde_proj ?? g.pay.spelvarde) || 0) * 100)}%</b></span>
                        {g.pay.jackpot > 0 && <span className="v3jackpot">💰 {kr(g.pay.jackpot)}</span>}
                      </span>
                    )}
                    {g.pay?.available && <PlayRec payouts={g.pay} product={g.id} />}
                  </>
                )}
              </button>
            ))}
          </div>
        </div>

        {(played?.coupons || []).some((c) => !c.settled_at) && (
          <div className="v3card">
            <div className="v3cardhead"><h3>🎟 Dina kuponger</h3>
              <button className="v3more" onClick={() => openHistorik()}>facit →</button></div>
            {played.coupons.filter((c) => !c.settled_at).slice(0, 4).map((c) => {
              const live = c.live || {}
              const alive = Object.entries(live.alive_per_level || {})
                .map(([lvl, n]) => [Number(lvl), n])
                .filter(([, n]) => n > 0).sort((a, b) => b[0] - a[0])[0]
              return (
                <div key={`${c.product}-${c.draw_number}-${c.rows_hash}`} className="v3row">
                  <b>{VARIANT[c.product] ? `Topptipset ${VARIANT[c.product]}` : c.product} {c.draw_number}</b>
                  <span className="v3hint">
                    {c.n_rows} rader ({kr(c.cost_kr)}) · {live.n_decided ?? '–'}/{live.n_events ?? '–'} avgjorda
                    · bäst {live.best_secure ?? '–'} rätt
                    {alive ? ` · ${alive[1]} rad${alive[1] > 1 ? 'er' : ''} vid liv för ${alive[0]}` : ''}
                  </span>
                </div>)
            })}
            {played?.summary?.n_settled > 0 && (
              <span className="v3hint">
                Facit hittills: {played.summary.n_settled} settlade · insats {kr(played.summary.spent_kr)} ·
                utdelning {kr(played.summary.won_kr)}
                {played.summary.roi != null ? ` · ROI ${Math.round(played.summary.roi * 100)} %` : ''}
              </span>
            )}
          </div>
        )}

        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Värdespel</h3>
            <button className="v3more" onClick={() => openOddset('varde')}>alla →</button></div>
          {!signals.length && <span className="v3hint">Inga sharp-ankrade edges ≥ 2 % just nu.</span>}
          {signals.slice(0, 3).map(({ m, mk, sg, v }, i) => (
            <div key={i} className="v3row">
              <b>{selLabel3(m, mk, sg, v.line)}</b>
              <span className="v3edge">+{(v.edge * 100).toFixed(1)}%</span>
              <span className="v3hint">{m.home} – {m.away} · {v.book} @ {v.odds?.toFixed(2)}</span>
            </div>
          ))}
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>📈 Rörelser</h3>
            <button className="v3more" onClick={() => openOddset('radar')}>radar →</button></div>
          {!movers.length && <span className="v3hint">Inga devigade skift ≥ 1,5 pp senaste dygnet.</span>}
          {movers.slice(0, 3).map(({ m, sg, pp }, i) => (
            <div key={i} className="v3row">
              <b>{selLabel3(m, '1x2', sg)}</b>
              <span className="v3steam">🔥 +{pp} pp</span>
              <span className="v3hint">{m.home} – {m.away}{m.research ? ' · 🔬' : ''}</span>
            </div>
          ))}
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>🔬 Forskningsligor</h3>
            <button className="v3more" onClick={() => openOddset(null)}>visa matcher →</button></div>
          {!research.length && <span className="v3hint">Inga forskningsligor aktiva.</span>}
          {research.length > 0 && (
            <>
              <div className="v3row"><span className="v3hint">
                {research.map((l) => l.name).join(' · ')}</span></div>
              <div className="v3row">
                <b>{researchMatches.length} matcher insamlade</b>
                {nextResearch && <span className="v3hint">premiärer från {fmtDay(nextResearch)}</span>}
              </div>
              <span className="v3hint">V2.2 samlar data — odds och rörelser visas,
                inga signaler/Kelly/notiser förrän forwarddomen är klar.</span>
            </>
          )}
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>🧭 Signal-facit</h3>
            <button className="v3more" onClick={openLabb}>detaljer i Labb →</button></div>
          {!primaryGroups.length && <span className="v3hint">Inga primära signalgrupper ännu.</span>}
          {primaryGroups.map((g) => (
            <div key={`${g.league}-${g.market}`} className="v3row">
              <span className={`v3status ${g.status}`}>{statusIcon(g.status)}</span>
              <b>{g.league} · {g.market?.toUpperCase()}</b>
              <span className="v3hint">{g.n_resolved} stängda flaggor</span>
            </div>
          ))}
          {ledger && <span className="v3hint">{ledger.n_predictions} frysta prediktioner ·
            {' '}{ledger.n_captures} fångster · grönt kräver KI &gt; 0 out-of-time</span>}
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>📋 Systemfacit</h3>
            <button className="v3more" onClick={() => openHistorik(null, 'system')}>följ →</button></div>
          {(() => {
            const groups = systems?.groups || []
            const frozen = groups.reduce((s, g) => s + g.n_frozen, 0)
            const settled = groups.reduce((s, g) => s + g.n_settled, 0)
            if (!frozen) {
              return <span className="v3hint">Byggarens förslag (50 kr Värderader m.fl.)
                fryses automatiskt vid T−3 h och T−20 min före varje spelstopp och
                rättas mot utfall och utspädd utdelningsestimering. Väntar på
                första frysningen.</span>
            }
            const primary = groups.filter((g) => g.primary)
            return (
              <>
                {primary.map((g) => (
                  <div key={`${g.product}-${g.config_key}-${g.horizon}`} className="v3row">
                    <b>{g.product} · {g.config_key} · {g.horizon}</b>
                    <span className="v3hint">{g.n_evaluable}/{g.n_frozen} jämförbara</span>
                    {g.n_evaluable > 0 && g.roi != null &&
                      <span className={g.roi >= 0 ? 'v3edge' : 'v3steam'}>
                        {g.roi >= 0 ? '+' : ''}{Math.round(g.roi * 100)}%</span>}
                  </div>
                ))}
                <span className="v3hint">{frozen} frysta system · {settled} rättade ·
                  champion = dagens byggare</span>
              </>
            )
          })()}
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>🗄 Historikfacit</h3>
            <button className="v3more" onClick={() => openHistorik()}>utforska →</button></div>
          {!histRows.length && <span className="v3hint">Settlementlagret fylls på — kör backfillen eller vänta in nästa varv.</span>}
          {histRows.map((r) => (
            <div key={r.id} className="v3row v3histrow" role="button" tabIndex={0}
              onClick={() => openHistorik(r.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault(); openHistorik(r.id)
                }
              }}>
              <b>{r.label}</b>
              <span className="v3hint">{r.sum.total} omgångar sedan {String(r.sum.first_close || '').slice(0, 4)}</span>
            </div>
          ))}
          <span className="v3hint">Slutstreck, omsättning och full utdelning per omgång —
            facit, aldrig prematch-input.</span>
        </div>
      </div>
    </div>
  )
}

/* =============================== Poolspel ================================= */

function PoolV3() {
  const saved = useRef(readState()).current
  const [game, setGame] = useState(
    POOL_GAMES.some((g) => g.id === saved.group) ? saved.group : 'topptipset')
  const [draws, setDraws] = useState([])
  const [product, setProduct] = useState(saved.product || game)
  const [draw, setDraw] = useState(saved.draw || null)
  const [analysis, setAnalysis] = useState(null)
  const [movement, setMovement] = useState(null)
  const [payouts, setPayouts] = useState(null)
  const [sys, setSys] = useState(null)
  const [strategy, setStrategy] = useState(saved.strategy || 'medel')
  const [budget, setBudget] = useState(saved.budget || 128)
  const [sysType, setSysType] = useState(saved.sysType || 'ev')
  const [valueWeight, setValueWeight] = useState(saved.valueWeight ?? 50)
  const [picks, setPicks] = useState(saved.picks || {})
  const [pickRows, setPickRows] = useState(saved.pickRows || null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [bombenNonce, setBombenNonce] = useState(0)

  const loadAnalysis = async (p = product, dn = draw, silent = false) => {
    if (!dn) return
    if (!silent) { setLoading(true); setErr(null); setSelected(null) }
    try {
      const a = await get(`/api/analysis?product=${p}&draw=${dn}`)
      setAnalysis(a)
      get(`/api/movement?product=${p}&draw=${dn}`).then(setMovement).catch(() => setMovement(null))
      get(`/api/payouts?product=${p}&draw=${dn}`).then(setPayouts).catch(() => setPayouts(null))
    } catch (e) { if (!silent) setErr(String(e)) } finally { if (!silent) setLoading(false) }
  }

  const pickDraws = async (g, restore = false) => {
    setLoading(true); setErr(null); setSys(null); setAnalysis(null)
    if (!restore) { setPicks({}); setPickRows(null) }
    try {
      const d = await get(`/api/draws?product=${g}`)
      const raw = d.open?.length ? d.open : d.draws || []
      const list = [...raw].sort((a, b) => {
        const at = a.reg_close_time ? new Date(a.reg_close_time).getTime() : Infinity
        const bt = b.reg_close_time ? new Date(b.reg_close_time).getTime() : Infinity
        return at - bt
      })
      setDraws(list)
      const restored = restore && list.find((x) => x.product === saved.product && x.draw_number === saved.draw)
      const chosen = restored || list[0]
      if (!chosen) { setLoading(false); setErr('Inga öppna omgångar just nu.'); return }
      if (restore && !restored) { setPicks({}); setPickRows(null) }
      setProduct(chosen.product); setDraw(chosen.draw_number)
      if (g !== 'bomben') await loadAnalysis(chosen.product, chosen.draw_number)
      else setLoading(false)
    } catch (e) { setErr(String(e)); setLoading(false) }
  }
  useEffect(() => { pickDraws(game, true) }, [])  // eslint-disable-line

  const switchGame = (g) => { setGame(g); pickDraws(g) }
  const changeDraw = (slug, dn) => {
    setProduct(slug); setDraw(dn); setSys(null); setPicks({}); setPickRows(null)
    if (game !== 'bomben') loadAnalysis(slug, dn)
  }

  // tyst auto-uppdatering (bakgrundsjobbet skriver till DB:n var 5–30:e min)
  useEffect(() => {
    if (!draw || game === 'bomben') return
    const tick = () => {
      if (document.visibilityState !== 'visible') return
      loadAnalysis(product, draw, true)
    }
    const id = setInterval(tick, 120000)
    document.addEventListener('visibilitychange', tick)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', tick) }
  }, [product, draw, game])  // eslint-disable-line

  // tillståndet sparas löpande i svs_state så iOS-omladdningen kan återställa det
  useEffect(() => {
    try {
      localStorage.setItem('svs_state', JSON.stringify({
        group: game, product, draw, picks, strategy, budget, sysType, valueWeight,
        pickRows: pickRows && pickRows.length <= 2048 ? pickRows : null,
      }))
    } catch { /* ok */ }
  }, [game, product, draw, picks, pickRows, strategy, budget, sysType, valueWeight])

  const toggleSign = (ev, sign) => {
    setPickRows(null)
    setPicks((prev) => {
      const cur = prev[ev] || []
      const next = cur.includes(sign) ? cur.filter((s) => s !== sign) : [...cur, sign]
      const copy = { ...prev }
      if (next.length) copy[ev] = next; else delete copy[ev]
      return copy
    })
  }
  const clearCoupon = () => { setPicks({}); setPickRows(null) }
  const useSystem = () => {
    if (!analysis || !sys?.picks) return
    const p = {}
    sys.picks.forEach((pk) => { p[pk.event_number] = pk.signs })
    setPickRows(sys.rows && sys.rows.length ? sys.rows.map((r) => [...r]) : null)
    setPicks(p)
    setTimeout(() => document.getElementById('kupong')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }

  const nMatches = analysis?.matches?.length || 0
  const systemTypes = nMatches === 13 ? [...SYSTEM_BASE, ...SYSTEM_SVS] : SYSTEM_BASE
  const budgetIdx = BUDGET_STOPS.reduce((best, v, i) =>
    Math.abs(v - budget) < Math.abs(BUDGET_STOPS[best] - budget) ? i : best, 0)
  const rowShares = (pickRows?.length && analysis?.matches?.length === pickRows[0]?.length) ? (() => {
    const counts = {}
    pickRows.forEach((r) => r.forEach((s, i) => {
      const k = `${analysis.matches[i].event_number}:${s}`
      counts[k] = (counts[k] || 0) + 1
    }))
    return { counts, total: pickRows.length }
  })() : null

  const loadSystem = async () => {
    setErr(null)
    try {
      let q = (systemTypes.find((t) => t.id === sysType) || SYSTEM_BASE[0]).q
      if (q.endsWith('guarantee=')) q += Math.max(1, nMatches - 1)
      const vw = valueWeight / 100
      const jp = payouts?.jackpot != null ? `&jackpot=${encodeURIComponent(payouts.jackpot)}` : ''
      const r = await fetch(`/api/system?product=${product}&draw=${draw}&strategy=${encodeURIComponent(strategy)}&budget=${budget}&value_weight=${vw}&${q}${jp}&_t=${Date.now()}`, { cache: 'no-store' })
      if (!r.ok) throw new Error((await r.json()).detail || `System ${r.status}`)
      setSys(await r.json())
    } catch (e) { setErr(String(e)) }
  }

  return (
    <div className="v3pool">
      <div className="v3poolbar">
        <nav className="v3subnav" aria-label="Spelform">
          {POOL_GAMES.map((g) => (
            <button key={g.id} className={game === g.id ? 'on' : ''}
              onClick={() => switchGame(g.id)}>{g.label}</button>
          ))}
        </nav>
        {draws.length > 0 && game !== 'bomben' && (
          <select className="v3drawsel" value={`${product}|${draw}`}
            onChange={(e) => { const [sl, dn] = e.target.value.split('|'); changeDraw(sl, Number(dn)) }}>
            {draws.map((d) => (
              <option key={`${d.product}|${d.draw_number}`} value={`${d.product}|${d.draw_number}`}>
                {VARIANT[d.product] ? `${VARIANT[d.product]} · ` : ''}stänger {fmtClose(d.reg_close_time)}
                {d.state !== 'Open' ? ` (${d.state})` : ''} · omg {d.draw_number}
              </option>
            ))}
          </select>
        )}
        {analysis && game !== 'bomben' && (
          <span className="v3poolkpi">
            oms <b>{analysis.turnover ? kr(analysis.turnover) : '–'}</b>
            {payouts?.available && <> · spelvärde <b className={((payouts.spelvarde_proj ?? payouts.spelvarde) || 0) >= 1 ? 'pos' : ''}>
              {Math.round(((payouts.spelvarde_proj ?? payouts.spelvarde) || 0) * 100)}%</b></>}
            {payouts?.jackpot > 0 && <> · 💰 {kr(payouts.jackpot)}</>}
            {payouts?.available && <PlayRec payouts={payouts} product={game} />}
          </span>
        )}
        <span className="v3steps">
          <a href="#analys">1 Analys</a><a href="#bygg">2 Bygg</a><a href="#kupong">3 Kupong</a>
        </span>
      </div>

      {err && <ErrorState message={err} />}
      {loading && <LoadingState label="Hämtar omgång och analys…" />}

      {game === 'bomben' && (
        <ErrBoundary>
          <div className="v3bombenbar">
            <button onClick={() => setBombenNonce((n) => n + 1)}>↻ Uppdatera Bomben</button>
          </div>
          <BombenView draw={draw} nonce={bombenNonce} />
        </ErrBoundary>
      )}

      {game !== 'bomben' && analysis && (
        <>
          <section id="analys">
            <div className="analys-head"><h2>Analysera kupongen</h2></div>
            <Legend />
            {(Object.keys(picks).length > 0 || pickRows) && (
              <div className="restored">
                🔁 Grönmarkeringarna är din <b>sparade kupong</b>
                {pickRows ? ` (${pickRows.length} rader)` : ` (${Object.keys(picks).length} matcher)`}
                — sparas så en omladdning inte tappar den.
                <button onClick={clearCoupon}>Rensa</button>
              </div>
            )}
            <AnalysisTable matches={analysis.matches} product={product} drawNumber={analysis.draw_number}
              selected={selected} onSelect={setSelected} picks={picks} onToggleSign={toggleSign}
              movement={movement} rowShares={rowShares} />
          </section>

          <div className="v3cols">
            <section id="bygg" className="buildbar">
              <h2>Bygg förslag</h2>
              <div className="controls">
                {STRATEGIES.map((s) => (
                  <label key={s} className={strategy === s ? 'active' : ''}>
                    <input type="radio" name="v3strategy" checked={strategy === s}
                      onChange={() => { setStrategy(s); setValueWeight(STRATEGY_EV[s]) }} />{s}
                  </label>
                ))}
                <label className="budget">
                  Max budget <b>{budget} kr</b>
                  <input type="range" min="0" max={BUDGET_STOPS.length - 1} step="1" value={budgetIdx}
                    onChange={(e) => setBudget(BUDGET_STOPS[Number(e.target.value)])} />
                </label>
                <select value={sysType} onChange={(e) => setSysType(e.target.value)}>
                  {systemTypes.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                </select>
                <button className="primary" onClick={loadSystem}>Föreslå rad</button>
              </div>
              <div className="evscale">
                <span>Träffbart</span>
                <input type="range" min="0" max="100" step="5" value={valueWeight}
                  onChange={(e) => setValueWeight(Number(e.target.value))} />
                <span>Max EV</span>
                <span className="evval">{valueWeight}%</span>
              </div>
              <SystemView sys={sys} matches={analysis?.matches} payouts={payouts}
                onRecalc={loadSystem} onUse={useSystem} />
            </section>

            <section id="kupong">
              <h2>Din kupong — granska &amp; lämna in</h2>
              <CouponPanel matches={analysis.matches} picks={picks} pickRows={pickRows}
                payouts={payouts} product={product} draw={draw} onClear={clearCoupon} />
            </section>
          </div>

          <details className="v3extras">
            <summary>Sharp-odds, steam &amp; signal-facit</summary>
            <div className="v3cols">
              <section>
                <h2>Sharp-odds &amp; steam</h2>
                <SharpPanel product={product} draw={draw} onLoaded={() => loadAnalysis()} />
                <SteamPanel product={product} draw={draw} matches={analysis?.matches} />
              </section>
              <section>
                <h2>Signal-facit (CLV)</h2>
                <ClvPanel group={game} />
              </section>
            </div>
          </details>
        </>
      )}
    </div>
  )
}

/* =============================== Historik ================================= */

function HistorikV3({ initialProduct, focus }) {
  const [product, setProduct] = useState(initialProduct || 'stryktipset')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [detail, setDetail] = useState({})
  const [systems, setSystems] = useState(null)

  useEffect(() => {
    setData(null); setErr(null); setExpanded(null)
    get(`/api/pool/history?product=${product}&limit=400`)
      .then(setData).catch((e) => setErr(String(e)))
  }, [product])
  useEffect(() => {
    get('/api/pool/systems').then(setSystems).catch(() => setSystems(null))
  }, [])
  // djuplänk från Idag-kortet: landa på Systemfacit-panelen
  useEffect(() => {
    if (focus !== 'system' || !systems) return
    const jump = () => document.getElementById('hist-system')
      ?.scrollIntoView({ behavior: 'auto', block: 'start' })
    jump()
    const t = setTimeout(jump, 400)
    return () => clearTimeout(t)
  }, [focus, !!systems])  // eslint-disable-line

  const toggle = (n) => {
    const next = expanded === n ? null : n
    setExpanded(next)
    if (next != null && !detail[next]) {
      get(`/api/pool/history?product=${product}&draw=${next}`)
        .then((j) => setDetail((d) => ({ ...d, [next]: j })))
        .catch(() => { /* raden visar ändå nivåerna */ })
    }
  }

  const draws = data?.draws || []
  const medianTop = data?.stats?.median_top_amount
  const rolloverRate = data?.stats?.rollover_rate
  const meanTurnover = data?.stats?.mean_turnover
  const sparkVals = [...draws].reverse().map((d) => d.turnover)

  return (
    <div className="v3hist">
      <div className="v3histbar">
        <nav className="v3subnav" aria-label="Produkt">
          {HIST_PRODUCTS.map((p) => (
            <button key={p.id} className={product === p.id ? 'on' : ''}
              onClick={() => setProduct(p.id)}>{p.label}</button>
          ))}
        </nav>
      </div>
      <div className="v3note">
        Historiskt <b>facit</b> ur settlementlagret (PH1): utfall, slutstreck, slutomsättning
        och utdelning per nivå. Kohorten är <code>final_only</code> — odds- och streckrörelser
        finns bara för lokalt observerade omgångar och kan aldrig bakfyllas.
      </div>

      <div className="v3card v3systembox" id="hist-system">
        <div className="v3cardhead"><h3>📋 Systemfacit — frysta förslag mot observerat facit</h3></div>
        <span className="v3hint">
          Vid T−3 h och T−20 min före varje spelstopp fryser snapshotvarvet vad
          radbyggaren faktiskt föreslår (förregistrerad matris: {(systems?.benchmarks || [])
            .map((b) => b.key + (b.primary ? ' ★' : '')).join(' · ') || '…'}) och
          rättar sedan raderna mot riktigt utfall. Utdelningen är en
          kontrafaktisk uppskattning: den publicerade nivån späds med våra egna
          vinnande rader. Rullpott med noll officiella vinnare lämnas okänd,
          aldrig som nollvinst.
          Champion = dagens byggare — inga inställningar ändras utan att slå den
          out-of-time. Sena frysningar flaggas och räknas separat.
        </span>
        {!systems?.groups?.length && (
          <EmptyState title="Inga frysta system ännu"
            detail="Första frysningen sker automatiskt när nästa omgång går in i sitt T−3h-fönster." />
        )}
        {systems?.groups?.length > 0 && (
          <div className="v3histtablewrap">
            <table className="v3histtable">
              <thead><tr><th>Produkt</th><th>Konfig</th><th>Horisont</th><th>Frysta</th>
                <th>Jämförbara</th><th>Insats</th><th>Utdelningsest.</th><th>ROI</th><th>Bäst</th></tr></thead>
              <tbody>
                {systems.groups.map((g) => (
                  <tr key={`${g.product}-${g.config_key}-${g.horizon}`}>
                    <td>{g.product}</td>
                    <td>{g.primary ? '★ ' : ''}{g.config_key}</td>
                    <td>{g.horizon}</td>
                    <td>{g.n_frozen}{g.n_timely < g.n_frozen ? ` (${g.n_frozen - g.n_timely} sena)` : ''}</td>
                    <td>{g.n_evaluable}{g.n_payout_incomplete ? ` (${g.n_payout_incomplete} okänd utd.)` : ''}</td>
                    <td>{g.n_evaluable ? kr(g.cost_kr) : '–'}</td>
                    <td>{g.n_evaluable ? kr(g.payout_kr) : '–'}</td>
                    <td className={g.roi == null ? '' : g.roi >= 0 ? 'v3pos' : 'v3neg'}>
                      {g.roi == null ? '–' : `${g.roi >= 0 ? '+' : ''}${Math.round(g.roi * 100)}%`}</td>
                    <td>{g.best_correct ?? '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {systems?.recent?.length > 0 && (
          <details className="v3recent">
            <summary className="v3hint">Senaste frysningarna ({systems.recent.length})</summary>
            <div className="v3histtablewrap">
              <table className="v3histtable">
                <thead><tr><th>Omgång</th><th>Horisont</th><th>Konfig</th>
                  <th>Rader</th><th>Facit</th></tr></thead>
                <tbody>
                  {systems.recent.map((r, i) => (
                    <tr key={i}>
                      <td>{r.product} #{r.draw_number}</td>
                      <td>{r.horizon}{r.timely ? '' : ' (sen)'}</td>
                      <td>{r.config_key}</td>
                      <td>{r.n_rows} ({kr(r.cost_kr)})</td>
                      <td>{r.correct_max == null ? (r.settle_note || 'väntar')
                        : r.payout_complete === false
                          ? `${r.correct_max} rätt · utdelning okänd`
                          : `${r.correct_max} rätt · est. ${kr(r.payout_kr)} (${r.roi >= 0 ? '+' : ''}${Math.round((r.roi || 0) * 100)}%)`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </div>
      {err && <ErrorState message={err} />}
      {!data && !err && <LoadingState label="Hämtar historik…" />}
      {data && !data.available && (
        <EmptyState title="Inga settlade omgångar ännu för denna produkt"
          detail="Backfillen fyller på bakåt och snapshot-varvet settlar nya omgångar löpande." />
      )}
      {data?.available && (
        <>
          <div className="v3histkpis">
            <div className="v3kpi"><b>{data.total}</b><span>omgångar</span></div>
            <div className="v3kpi"><b>{String(data.first_close || '').slice(0, 4)}–{String(data.last_close || '').slice(0, 4)}</b><span>tidsspann</span></div>
            <div className="v3kpi"><b>{medianTop ? kr(medianTop) : '–'}</b><span>median toppvinst<br />(hela historiken)</span></div>
            <div className="v3kpi"><b>{rolloverRate != null ? Math.round(100 * rolloverRate) : 0}%</b><span>utan toppvinnare<br />(hela historiken)</span></div>
            <div className="v3kpi"><b>{meanTurnover ? kr(meanTurnover) : '–'}</b><span>medelomsättning<br />(hela historiken)</span></div>
          </div>
          {sparkVals.filter(Boolean).length > 2 && (
            <div className="v3sparkbox">
              <span className="v3hint">Omsättning, äldst → nyast (senaste {draws.length} omgångarna)</span>
              <MiniSpark values={sparkVals} width={640} height={60} />
            </div>
          )}
          <div className="v3histtablewrap">
            <table className="v3histtable">
              <thead><tr>
                <th>Omg</th><th>Stängde</th><th>Omsättning</th>
                <th>Toppnivå</th><th>Utdelning</th><th></th>
              </tr></thead>
              <tbody>
                {draws.map((d) => {
                  const top = d.tiers?.[0]
                  return [
                    <tr key={d.draw_number} className="v3histrowline"
                      role="button" tabIndex={0}
                      onClick={() => toggle(d.draw_number)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault(); toggle(d.draw_number)
                        }
                      }}>
                      <td>{d.draw_number}</td>
                      <td>{fmtDay(d.close)}</td>
                      <td>{d.turnover ? kr(d.turnover) : '–'}</td>
                      <td>{top ? `${top.name}: ${top.winners ?? '–'} st` : '–'}
                        {d.top_winners === 0 && <span className="v3roll" title="Ingen vinnare på toppnivån — potten rullar">🎰</span>}
                        {d.n_cancelled > 0 && <span className="v3cancel" title={`${d.n_cancelled} struken/strukna matcher`}>⚠</span>}</td>
                      <td>{top?.amount ? kr(top.amount) : '–'}</td>
                      <td className="v3expand">{expanded === d.draw_number ? '▲' : '▼'}</td>
                    </tr>,
                    expanded === d.draw_number && (
                      <tr key={`${d.draw_number}-x`} className="v3histdetail"><td colSpan="6">
                        <div className="v3tiers">
                          {(d.tiers || []).map((t) => (
                            <span key={t.name} className="v3tier">
                              {t.name}: <b>{t.winners ?? '–'}</b> à <b>{t.amount ? kr(t.amount) : '–'}</b>
                            </span>
                          ))}
                        </div>
                        {!detail[d.draw_number] && <LoadingState label="Hämtar matchfacit…" />}
                        {detail[d.draw_number]?.available && (
                          <table className="v3facit">
                            <tbody>
                              {detail[d.draw_number].draw.events.map((e) => (
                                <tr key={e.event_number} className={e.cancelled ? 'cancelled' : ''}>
                                  <td>{e.event_number}</td>
                                  <td>{e.home && e.away ? `${e.home} – ${e.away}` : e.description}</td>
                                  <td className="v3outcome">{e.cancelled ? '⚠ struken' : e.outcome || '–'}</td>
                                  <td className="v3hint">
                                    {e.streck?.['1'] != null
                                      ? `folket ${e.streck['1']}/${e.streck['X']}/${e.streck['2']} %` : ''}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td></tr>
                    ),
                  ]
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

/* ================================= Labb =================================== */
// Bevisytan (konsolideringen "ett UI, två ytor", backlog punkt 7): ETT
// statuskort per mät-/shadowspår. Labb visar mätningar — Idag/Poolspel/Oddset
// är beslutsytan, Historik är facityta. Ingenting här är ett tips.

const LABB_STATUS = {
  samlar: ['SAMLAR', 'Serien växer och utvärderas bara på sin förregistrerade kadens — inga beslut i förtid.'],
  candidate: ['CANDIDATE', 'Mängdkravet är nått — beslut tas enligt den förregistrerade regeln, inte löpande.'],
  pass: ['GATE-PASS', 'Den förregistrerade grinden är passerad — se dokumentet för hela beslutet.'],
  fals: ['FALSIFIERAD', 'Hypotesen föll mot facit — spåret byggs inte vidare som tips.'],
}
function LabbPill({ s }) {
  const [label, tip] = LABB_STATUS[s] || LABB_STATUS.samlar
  return <span className={`v3labbpill ${s}`} title={tip}>{label}</span>
}

// Primärgrupperna för sharp-CLV (speglar backend PRIMARY_LEAGUES × 1X2 × sharp)
const LABB_PRIMARY = ['allsvenskan', 'superettan', 'eliteserien', 'obosligaen', 'mls']
const LABB_LEAGUE = {
  allsvenskan: 'Allsvenskan', superettan: 'Superettan', eliteserien: 'Eliteserien',
  obosligaen: 'OBOS-ligaen', mls: 'MLS',
}
const LABB_MARKET = {
  '1x2': '1X2', ah: 'AH', ou: 'Ö/U', cor: 'Hörnor',
}
const LABB_BOOK = {
  svenskaspel: 'SvS', expekt: 'Expekt', ninjacasino: 'Ninja/Altenar',
  pinnacle: 'Pinnacle', smarkets: 'Smarkets',
}

// Avslutade/pågående forskningsspår utan eget API — daterade kort med källdok.
const LABB_RESEARCH = [
  { icon: '🧮', title: 'Devig-ablation', date: '2026-07-26', status: 'pass',
    text: 'Konsensusflaggor +4,40 % [+2,54..+6,14] mot bara-power −0,49 % — devig-tvetydighet är en äkta filtersignal.',
    doc: 'docs/devig-ablation-2026-07-26.md' },
  { icon: '🔮', title: 'Close-drift v1', date: '2026-07-26', status: 'fals',
    text: 'Momentum FALSIFIERAD; tidiga AH/Ö/U-skift reverserar.',
    doc: 'docs/close-drift-facit-2026-07-26.md' },
  { icon: '🎟', title: 'PH5 256/512 rader', date: '2026-07-26', status: 'fals',
    text: 'Värderader ger ingen påvisad fördel på 13-matchsspel ens vid 512 rader.',
    doc: 'docs/ph5-radvalsablation-512rader-2026-07-26.json' },
  { icon: '📐', title: 'pit-v4 (pool-streckmove-v3)', status: 'samlar',
    text: 'Forward samlar, gate ≥40 out-of-time-omgångar per produkt.',
    doc: 'docs/pool-ph4-forward-manifest-v3.json' },
  { icon: '🔬', title: 'V2.2 flerliga-shadow', status: 'samlar',
    text: 'Shadow, manifest v2 2026-07-26 — inga tips, notiser eller CLV.',
    doc: 'docs/model-v2.2-multileague-forward-manifest-v2.json' },
  { icon: '🔓', title: 'startOdds', date: '2026-07-26', status: 'pass',
    text: 'Upplåst som omgångs-kovariat (final_only) — aldrig som PIT-observation.',
    doc: 'docs/startodds-semantik-2026-07-26.md' },
]

function LabbV3() {
  const [clv, setClv] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [radar, setRadar] = useState(null)
  const [systems, setSystems] = useState(null)
  const [err, setErr] = useState(null)
  const [showLedger, setShowLedger] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [logLimit, setLogLimit] = useState(200)

  const [halsa, setHalsa] = useState(null)
  useEffect(() => {
    // engångsläsning — mätserierna rör sig på varv-/veckoskala, ingen poll
    get('/api/oddset/clv').then(setClv).catch((e) => { setClv(null); setErr(String(e)) })
    get('/api/oddset/predictions').then(setLedger).catch(() => setLedger(null))
    get('/api/oddset/radar-facit').then(setRadar).catch(() => setRadar(null))
    get('/api/pool/systems').then(setSystems).catch(() => setSystems(null))
    get('/api/pool/turnover-prognos').then(setHalsa).catch(() => setHalsa(null))
  }, [])

  const evPct = (v) => v == null ? '–' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)} %`
  const evCls = (v) => v == null ? 'v3hint' : v >= 0 ? 'v3pos' : 'v3neg'
  const ciStr = (ci) => ci ? `[${(ci[0] * 100).toFixed(1)}..${(ci[1] * 100).toFixed(1)}]` : '–'
  const rate = (v) => v == null ? '–' : `${Math.round(v * 100)} %`
  const radarLevel = (level) => level === 'strong' ? 'Stark' : 'Följer'
  const radarType = (kind) => kind === 'xg' ? 'xG' : 'Skottbaserad'
  const radarTime = (value) => value
    ? new Date(value).toLocaleString('sv-SE', {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    }) : '–'
  const radarOddsStatus = (row) => ({
    no_canonical_match: 'matchen saknade oddskoppling',
    no_svenskaspel_id: 'SvS-id saknades',
    not_offered: 'Ö/U erbjöds inte just då',
  }[row.odds_status] || (row.odds_status?.startsWith('source_error')
    ? 'oddsfel vid signalen' : 'liveodds saknas'))

  const primaryClv = (clv?.groups || []).filter((g) =>
    g.tier === 'sharp' && g.market === '1x2' && LABB_PRIMARY.includes(g.league))
  const a2 = clv?.anchor2
  const candidateReq = ledger?.criteria?.candidate || {
    n_resolved: 50, n_matches: 30, span_days: 28,
  }
  const modelCloseRows = ledger?.model_close?.summary || []
  const activePrimaryGroups = (ledger?.groups || []).filter(
    (g) => g.primary && g.active_version)
  const ledgerTiming = Object.values(ledger?.capture_quality || {}).reduce(
    (sum, h) => ({ n: sum.n + (h.n || 0), timely: sum.timely + (h.n_timely || 0) }),
    { n: 0, timely: 0 })
  const modelCloseLabel = (status) => ({
    better: '✓ slår sharp', worse: '✕ sämre än sharp',
    inconclusive: '◐ oklart', collecting: '● samlar',
  }[status] || status)
  const statusLabel = (status) => status === 'green'
    ? '✓ grön' : status === 'candidate' ? '◐ kandidat' : '● samlar'
  const candidateText = (g) => {
    if (g.status === 'green') {
      return g.green_at
        ? `Grön sedan ${new Date(g.green_at).toLocaleDateString('sv-SE')}` : 'Grön'
    }
    if (g.status === 'candidate') {
      return g.candidate_at
        ? `Kandidat sedan ${new Date(g.candidate_at).toLocaleDateString('sv-SE')}` : 'Kandidat'
    }
    if (g.candidate_eta_at) {
      return `Tidigast ~${new Date(g.candidate_eta_at).toLocaleDateString(
        'sv-SE', { day: 'numeric', month: 'short' })} vid nuvarande takt`
    }
    return 'För lite data för ett rimligt datum'
  }
  const clvLine = (market, line) => market?.endsWith('ah') && line > 0 ? `+${line}` : line
  const closeEv = (r) => r.closing_fair == null
    ? null : r.closing_fair * r.first_odds - 1

  const perProduct = {}
  for (const g of systems?.groups || []) {
    const p = perProduct[g.product] || (perProduct[g.product] = { frozen: 0, settled: 0 })
    p.frozen += g.n_frozen || 0
    p.settled += g.n_settled || 0
  }
  const products = Object.entries(perProduct)

  return (
    <div className="v3labb">
      <h2 className="v3labbtitle">Mätningar och skuggspår — INGET här är tips.</h2>
      {err && !clv && <ErrorState message={err} />}
      <div className="v3grid">

        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Signal-facit (sharp-CLV)</h3>
            <LabbPill s={primaryClv.some((g) => g.green_ready) ? 'pass' : 'samlar'} /></div>
          {!clv && !err && <LoadingState label="Hämtar facit…" />}
          {primaryClv.map((g) => (
            <div key={`${g.league}-${g.version}`} className="v3row">
              <b>{LABB_LEAGUE[g.league] || g.league}</b>
              <span className="v3hint">{g.version}</span>
              <span>{g.n_resolved}/{g.n} stängda</span>
              <span className={evCls(g.avg_close_ev)}>{evPct(g.avg_close_ev)}</span>
              <span className="v3hint">KI {ciStr(g.ci)}</span>
            </div>
          ))}
          {clv && !primaryClv.length && (
            <span className="v3hint">Inga stängda flaggor i primärgrupperna ännu —
              ny aktiv signalversion börjar om räkningen.</span>
          )}
          {clv?.sharp && (
            <div className="v3row">
              <b>Aggregat (alla sharp)</b>
              <span>{clv.sharp.n_resolved}/{clv.sharp.n} stängda</span>
              <span className={evCls(clv.sharp.avg_close_ev)}>{evPct(clv.sharp.avg_close_ev)}</span>
              <span className="v3hint">KI {ciStr(clv.sharp.ci)}</span>
            </div>
          )}
          <span className="v3hint">Close-EV mot devigad Pinnacle-stängning, winsoriserad ±20 %.
            Grönt beslutas per liga × marknad × version på veckokadens — aggregatet ändrar aldrig gruppstatus.</span>
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>🧬 Modellhälsa</h3>
            <LabbPill s="samlar" /></div>
          {clv?.sharp?.n_outcomes > 0 && (
            <div className="v3row" title="Resultatbaserad ROI till first-odds på settlade 1X2-flaggor. Display — grönt beslutas fortfarande av close-EV-grinden.">
              <b>🎯 Utfalls-facit (sharp)</b>
              <span>{clv.sharp.n_outcomes} settlade</span>
              <span className={evCls(clv.sharp.result_roi)}>{evPct(clv.sharp.result_roi)} ROI</span>
              <span className="v3hint">träff {rate(clv.sharp.hit_rate)}</span>
            </div>
          )}
          {halsa && Object.entries(halsa).map(([p, h]) => (
            <div key={p} className="v3row" title="Rullande backtest: medianabsolutfel för slutomsättningsprognosen, räknad enbart på data som fanns före respektive omgång. Veckodagsmetoden ska ligga under den gamla blandade medianen.">
              <b>{p}</b>
              <span>prognosfel {h.medianfel_veckodag == null ? '–' : `${(h.medianfel_veckodag * 100).toFixed(0)} %`}
                {h.medianfel_blandad != null && <span className="v3hint"> (blandad {(h.medianfel_blandad * 100).toFixed(0)} %)</span>}</span>
              <span className="v3hint">PH4-OOT {h.ph4_oot}/{h.ph4_oot_krav}</span>
            </div>
          ))}
          <span className="v3hint">Utfalls-ROI är brusig vid låga n och ändrar inga grindar.
            PH4-räknaren visar out-of-time-fönstret som krävs innan nya κ-varianter får föreslås.</span>
        </div>

        <div className="v3card v3wide v3evidence">
          <div className="v3cardhead">
            <h3>🧭 Modell mot close och full signallogg</h3>
            <span className="v3hint">bevisyta — inte tips</span>
          </div>
          {!ledger && !clv && !err && <LoadingState label="Hämtar valideringen…" />}
          {ledger && (
            <div className="v3evidence-summary">
              <span><b>{ledger.n_predictions}</b> frysta prediktioner</span>
              <span><b>{ledger.n_captures}</b> fångster</span>
              <span>{ledger.horizons?.h24 || 0}×24 h · {ledger.horizons?.h3 || 0}×3 h ·
                {' '}{ledger.horizons?.m20 || 0}×20 min</span>
              {ledgerTiming.n > 0 && <span><b>{ledgerTiming.timely}/{ledgerTiming.n}</b> i tid</span>}
              {ledger.n_empty_captures > 0 &&
                <span>{ledger.n_empty_captures} utan tillgänglig prognos</span>}
            </div>
          )}
          {modelCloseRows.length > 0 && (
            <div className="model-close-wrap">
              <div className="model-close-title">
                <b>🧪 Modell mot Pinnacle-close</b>
                <span className="v3hint">alla frysta prediktioner, även oflaggade</span>
              </div>
              <div className="model-close-grid">
                {modelCloseRows.map((g) => (
                  <div className={`model-close-card ${g.status}`}
                    key={`${g.market}-${g.version}`}
                    title={`Parad log-score mot Pinnacle vid samma horisont. Positivt KI helt över noll krävs.\nVersion ${g.version}${g.active_version ? ' (nuvarande)' : ' (äldre)'}`}>
                    <div><b>{LABB_MARKET[g.market] || g.market}</b>
                      <span className={`model-close-status ${g.status}`}>
                        {modelCloseLabel(g.status)}</span></div>
                    <div className="model-close-mae">
                      M <b>{g.model_mae_pp?.toFixed(2) ?? '–'} pp</b>
                      {' '}· P <b>{g.sharp_mae_pp?.toFixed(2) ?? '–'} pp</b>
                    </div>
                    <div className="v3hint">{g.n_cases} fall · {g.n_matches} matcher ·
                      {' '}{g.span_days} dagar · {g.active_version ? 'nuvarande' : 'äldre'} {g.version}</div>
                    {g.logscore_gain_ci && (
                      <div className="v3hint">log-score Δ {g.logscore_gain >= 0 ? '+' : ''}
                        {g.logscore_gain.toFixed(4)} · KI [{g.logscore_gain_ci[0].toFixed(4)}
                        ..{g.logscore_gain_ci[1].toFixed(4)}]</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {activePrimaryGroups.length > 0 && (
            <div className="validation-grid">
              {activePrimaryGroups.map((g) => (
                <div className={`validation-card ${g.status}`}
                  key={`${g.league}-${g.market}-${g.version}`}
                  title="Kandidat kräver mängdkraven och positiv undre 90 %-KI-gräns. Datumet uppskattar bara mängd och tid.">
                  <div className="validation-head">
                    <b>{LABB_LEAGUE[g.league] || g.league} ·
                      {' '}{LABB_MARKET[g.market] || g.market}</b>
                    <span className={`ledgerstatus ${g.status}`}>{statusLabel(g.status)}</span>
                  </div>
                  <div className="validation-progress">
                    <span><b>{g.n_resolved}</b>/{candidateReq.n_resolved} stängda</span>
                    <span><b>{g.n_matches}</b>/{candidateReq.n_matches} matcher</span>
                    <span><b>{g.span_days}</b>/{candidateReq.span_days} dagar</span>
                  </div>
                  <div className="validation-eta">{candidateText(g)}</div>
                  <div className="validation-ci">90 % KI {g.ci
                    ? `[${(g.ci[0] * 100).toFixed(1)}..${(g.ci[1] * 100).toFixed(1)}]`
                    : '–'}{!g.ci_stable && g.ci ? ' · instabilt' : ''}</div>
                </div>
              ))}
            </div>
          )}
          {ledger && (
            <button className="v3evidence-toggle" onClick={() => setShowLedger(!showLedger)}
              aria-expanded={showLedger}>
              {showLedger ? 'Dölj alla signalgrupper ▲' : `Visa alla ${ledger.groups?.length || 0} signalgrupper ▼`}
            </button>
          )}
          {showLedger && (
            <div className="v3evidence-table">
              <table className="logtable">
                <thead><tr><th>Status</th><th>Grupp</th><th>Pred/kontroll</th>
                  <th>Flaggor</th><th>Bredd</th><th>Close-EV</th><th>90 % KI</th></tr></thead>
                <tbody>{(ledger?.groups || []).map((g) => (
                  <tr className={g.active_version ? '' : 'historical-version'}
                    key={`${g.tier}-${g.league}-${g.market}-${g.version}`}>
                    <td className={`ledgerstatus ${g.status}`}>{statusLabel(g.status)}</td>
                    <td>{g.tier === 'model' ? '🧪' : '💰'} {LABB_LEAGUE[g.league] || g.league}
                      {' '}· {LABB_MARKET[g.market] || g.market}{g.primary ? ' · primär' : ''}
                      <span className="v3hint"> · {g.active_version ? 'nuvarande' : 'äldre'} {g.version}</span></td>
                    <td>{g.n_timely}/{g.n_controls}{g.n_late > 0 ? ` · ${g.n_late} sena` : ''}</td>
                    <td>{g.n_resolved}/{g.n_flags} stängda</td>
                    <td>{g.n_matches} matcher · {g.n_weeks} v · {g.span_days} d</td>
                    <td className={g.avg_close_ev == null ? '' : g.avg_close_ev >= 0 ? 'v3pos' : 'v3neg'}>
                      {g.avg_close_ev == null ? '–'
                        : `${g.avg_close_ev >= 0 ? '+' : ''}${(g.avg_close_ev * 100).toFixed(1)} %`}</td>
                    <td>{g.ci ? `[${(g.ci[0] * 100).toFixed(1)}..${(g.ci[1] * 100).toFixed(1)}]${g.ci_stable ? '' : ' · instabilt'}` : '–'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          {clv && (clv.sharp?.n > 0 || clv.model?.n > 0) && (
            <>
              <div className="v3evidence-summary">
                <b>📒 Faktiskt flaggade signaler</b>
                <span>sharp: {clv.sharp?.n ?? 0} · {clv.sharp?.n_resolved ?? 0} stängda
                  {clv.sharp?.avg_close_ev != null &&
                    <> · snitt <b className={evCls(clv.sharp.avg_close_ev)}>{evPct(clv.sharp.avg_close_ev)}</b></>}</span>
                {clv.model?.n > 0 && <span>modell: {clv.model.n} ·
                  {' '}{clv.model.n_resolved} stängda
                  {clv.model.avg_close_ev != null &&
                    <> · snitt <b className={evCls(clv.model.avg_close_ev)}>{evPct(clv.model.avg_close_ev)}</b></>}</span>}
              </div>
              {clv.calibration && (
                <span className="v3hint">🌡 Kalibrering: {Object.entries(clv.calibration)
                  .map(([lg, c]) => `${lg} t=${c.t?.toFixed?.(2) ?? c.t} (n=${c.n})`).join(' · ')}</span>
              )}
              <button className="v3evidence-toggle" onClick={() => {
                if (!showLog) setLogLimit(200)
                setShowLog(!showLog)
              }}
                aria-expanded={showLog}>
                {showLog ? 'Dölj signalloggen ▲' : `Visa ${clv.rows?.length || 0} flaggade signaler ▼`}
              </button>
              {showLog && (
                <div className="v3evidence-table">
                  <table className="logtable">
                    <thead><tr><th>Flagga</th><th>Match</th><th>Bok</th><th>Odds</th>
                      <th>Edge</th><th>Bäst</th><th>Stängning</th><th>Tier</th></tr></thead>
                    <tbody>{(clv.rows || []).slice(0, logLimit).map((r, i) => {
                      const cev = closeEv(r)
                      return (
                        <tr key={i}>
                          <td>{r.market} {r.sign}
                            {r.line != null ? ` (${clvLine(r.market, r.line)})` : ''}</td>
                          <td>{r.description}</td>
                          <td>{LABB_BOOK[r.book] || r.book || 'SvS'}</td>
                          <td>{r.first_odds}</td>
                          <td>{r.first_edge > 0 ? '+' : ''}{(r.first_edge * 100).toFixed(1)} %</td>
                          <td>{r.best_edge > 0 ? '+' : ''}{(r.best_edge * 100).toFixed(1)} %</td>
                          <td className={cev == null ? '' : cev >= 0 ? 'v3pos' : 'v3neg'}>
                            {cev == null ? r.closing_note || 'öppen'
                              : `${cev >= 0 ? '+' : ''}${(cev * 100).toFixed(1)} %`}
                            {r.closing_line != null && r.line !== r.closing_line &&
                              <span className="v3hint"> · lina {clvLine(r.market, r.line)}
                                →{clvLine(r.market, r.closing_line)}</span>}
                          </td>
                          <td>{r.tier === 'model' ? '🧪' : '💰'}</td>
                        </tr>
                      )
                    })}</tbody>
                  </table>
                </div>
              )}
              {showLog && (clv.rows?.length || 0) > logLimit && (
                <button className="v3evidence-toggle"
                  onClick={() => setLogLimit((n) => n + 200)}>
                  Visa {Math.min(200, clv.rows.length - logLimit)} till
                  {' '}({logLimit} av {clv.rows.length})
                </button>
              )}
            </>
          )}
          <span className="v3hint">Grönt beslutas per liga × marknad × version.
            Aggregat, utfalls-ROI och känsla får aldrig ändra gruppstatus.</span>
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>⚓ Två ankare (Pinnacle ↔ {a2?.source || 'Smarkets'})</h3>
            <LabbPill s={(a2?.n_measured ?? 0) >= 50 ? 'candidate' : 'samlar'} /></div>
          {!clv && !err && <LoadingState label="Hämtar ankarmätning…" />}
          {a2 && (
            <div className="v3row">
              <b>{a2.n_measured ?? 0} mätta</b>
              <span>oenighet median {a2.median_disagree_pp ?? '–'} pp</span>
              <span>håller mot båda: <b className={evCls(a2.avg_close_ev_survives_both)}>
                {evPct(a2.avg_close_ev_survives_both)}</b></span>
              <span>endast Pinnacle: <b className={evCls(a2.avg_close_ev_pinnacle_only)}>
                {evPct(a2.avg_close_ev_pinnacle_only)}</b></span>
            </div>
          )}
          <span className="v3hint">Skuggmätning på varje flagga — ändrar aldrig urval, edge eller
            notiser. Beslut vid n ≥ 50 mätta+stängda (veckokadens) — <code>docs/tva-ankare-2026-07-25.md</code>.</span>
        </div>

        <div className="v3card v3radar-facit">
          <div className="v3cardhead"><h3>⚡ Radar-facit och signaljournal</h3>
            <LabbPill s={radar?.signal_ledger?.blind_gate?.status === 'pass'
              ? 'pass' : radar?.signal_ledger?.blind_gate?.status === 'no_support'
                ? 'fals' : 'samlar'} /></div>

          <div className="v3radar-rules" aria-label="Radarns signalregler">
            <div><b>Följer · xG</b>
              <span>{radar?.signal_ledger?.thresholds?.xg_watch?.minute
                || 'Minut 15–78, minst 12 minuter kvar'}</span>
              <span>{radar?.signal_ledger?.thresholds?.xg_watch?.rule
                || 'Lagets xG−mål ≥ 0,65 eller matchens xG−mål ≥ 1,00'}</span></div>
            <div className="strong"><b>Stark · xG</b>
              <span>{radar?.signal_ledger?.thresholds?.xg_strong?.minute
                || 'Samma tidsfönster som Följer'}</span>
              <span>{radar?.signal_ledger?.thresholds?.xg_strong?.rule
                || 'Lagets xG−mål ≥ 1,15 eller matchens xG−mål ≥ 1,65'}</span></div>
            <div><b>Följer · skott</b>
              <span>{radar?.signal_ledger?.thresholds?.proxy_watch?.minute
                || 'Minut 20–78, minst 12 minuter kvar'}</span>
              <span>{radar?.signal_ledger?.thresholds?.proxy_watch?.rule
                || 'Stora chanser−mål ≥ 1,5, eller skott på mål−mål ≥ 5 och minst 8 skott i box'}</span></div>
          </div>
          <span className="v3hint">Det finns två aktiva nivåer: <b>Följer</b> och <b>Stark</b>.
            Informationsläget före Följer är ingen signal. Skottmåttet har ingen Stark-nivå i v2.
            Första gången en nivå nås sparas; samma nivå varannan minut räknas inte som nya spel.</span>

          <div className="v3radar-gate">
            <b>Blindtest: första aktiva signalen per match</b>
            <span>{radar?.signal_ledger?.blind_gate?.n_priced_settled ?? 0} av{' '}
              {radar?.signal_ledger?.blind_gate?.required_priced_settled ?? 200} oddssatta och avgjorda</span>
            <span>{radar?.signal_ledger?.blind_gate?.span_days ?? 0} av{' '}
              {radar?.signal_ledger?.blind_gate?.required_span_days ?? 60} dagar</span>
            <span>Över-ROI <b className={evCls(radar?.signal_ledger?.blind_gate?.roi_over)}>
              {evPct(radar?.signal_ledger?.blind_gate?.roi_over)}</b>{' '}
              KI90 {ciStr(radar?.signal_ledger?.blind_gate?.roi_ci90)}</span>
          </div>
          <span className="v3hint">Ingen rekommendation om att rygga blint före minst 200
            framåtriktade signalmatcher med observerat livepris, minst 60 dagar och positiv
            undre 90 %-KI-gräns. Saknat livepris räknas öppet som saknat — det bakfylls aldrig.</span>

          {!!radar?.signal_ledger?.groups?.length && (
            <div className="v3radar-groups">
              {radar.signal_ledger.groups.map((g) => (
                <div key={`${g.signal_type}-${g.signal_level}`}>
                  <b>{radarLevel(g.signal_level)} · {radarType(g.signal_type)}</b>
                  <span>{g.n_settled}/{g.n_signals} avgjorda</span>
                  <span>mål ≤15 min {rate(g.goal_15min_rate)}</span>
                  <span>snitt mål efter {g.avg_goals_after ?? '–'}</span>
                  <span>Över-ROI <b className={evCls(g.roi_over)}>{evPct(g.roi_over)}</b></span>
                </div>
              ))}
            </div>
          )}

          <details className="v3radar-old">
            <summary>Tidigare momentfacit utan liveodds</summary>
            {['xg', 'proxy'].map((k) => {
              const g = radar?.groups?.[k]
              const a = g?.outcomes?.outcome_15min
              return (
                <div key={k} className="v3row">
                  <b>{k === 'xg' ? 'xG' : 'Skottbaserad'}</b>
                  {!g && <span className="v3hint">väntar på settlade ögonblick</span>}
                  {g && <>
                    <span>{g.n_signal_moments} ögonblick i {g.n_signal_matches} matcher</span>
                    <span>mål ≤15 min {a?.n_resolved
                      ? <>{a.hits}/{a.n_resolved} = <b>{rate(a.rate)}</b> mot bas {rate(a.base_rate)}</>
                      : '–'}</span>
                  </>}
                </div>
              )
            })}
          </details>

          {!!radar?.signal_ledger?.rows?.length && (
            <details className="v3radar-log" open>
              <summary>Signaljournal · senaste {radar.signal_ledger.rows.length}</summary>
              <div className="v3radar-logrows">
                {radar.signal_ledger.rows.map((row) => (
                  <div className="v3radar-logrow" key={row.id}>
                    <div><b>{row.home} – {row.away}</b>
                      <span>{radarTime(row.captured_at)} · {row.minute ?? '–'}′ ·{' '}
                        {row.home_score ?? '–'}–{row.away_score ?? '–'}</span></div>
                    <div><b className={row.signal_level === 'strong' ? 'v3neg' : ''}>
                      {radarLevel(row.signal_level)} · {radarType(row.signal_type)}</b>
                      <span>{row.reason}</span></div>
                    <div><b>Live Ö/U</b>
                      <span>{row.odds_status === 'captured'
                        ? `Ö ${row.ou_line} @ ${Number(row.over_odds).toFixed(2)} · U @ ${Number(row.under_odds).toFixed(2)} · läst ${radarTime(row.odds_observed_at)}`
                        : radarOddsStatus(row)}</span></div>
                    <div><b>Facit</b>
                      <span>{row.settled_at
                        ? `${row.final_home_score}–${row.final_away_score} · ${row.goals_after_signal} mål efter · Över ${row.over_result || 'ej prissatt'}${row.over_profit == null ? '' : ` (${row.over_profit >= 0 ? '+' : ''}${row.over_profit.toFixed(2)} u)`}`
                        : 'väntar på slutresultat'}</span></div>
                  </div>
                ))}
              </div>
            </details>
          )}
          <span className="v3hint">Shadow: detta påverkar inga tips, Kelly, notiser eller
            systemförslag. Metod: <code>docs/live-radar-2026-07-25.md</code>.</span>
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>📋 PH3-systemledger</h3>
            <LabbPill s="samlar" /></div>
          {!systems && <span className="v3hint">väntar på ledgerdata</span>}
          {products.map(([product, p]) => (
            <div key={product} className="v3row">
              <b>{product}</b>
              <span>{p.frozen} frysta</span>
              <span>{p.settled} rättade</span>
            </div>
          ))}
          {systems && !products.length && (
            <span className="v3hint">Inga frysta system ännu — första frysningen sker
              automatiskt i nästa T−3h-fönster.</span>
          )}
          <span className="v3hint">Kontrafaktiskt facit för förregistrerade benchmarksystem.
            Gate: ≥40 omgångar, ≥60 dagar, KI&gt;0 — <code>docs/ph3-gate-2026-07-26.md</code>.</span>
        </div>

        {LABB_RESEARCH.map((c) => (
          <div key={c.title} className="v3card">
            <div className="v3cardhead"><h3>{c.icon} {c.title}</h3><LabbPill s={c.status} /></div>
            <div className="v3row"><span>{c.text}</span></div>
            <span className="v3hint">{c.date ? `${c.date} · ` : ''}<code>{c.doc}</code></span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ================================= Skal =================================== */

export default function AppV3() {
  const [view, setView] = useState(() => {
    try { return localStorage.getItem('svs_v3_view') || 'idag' } catch { return 'idag' }
  })
  const [histProduct, setHistProduct] = useState(null)
  const [histFocus, setHistFocus] = useState(null)
  const [oddsetFocus, setOddsetFocus] = useState(null)
  const go = (v) => {
    if (v !== 'oddset') setOddsetFocus(null)
    setView(v)
    try { localStorage.setItem('svs_v3_view', v) } catch { /* ok */ }
    window.scrollTo({ top: 0 })
  }
  const openOddset = (target = null) => { setOddsetFocus(target); go('oddset') }
  const openPool = (g) => {
    // PoolV3 läser svs_state vid mount — peka den på valt spel innan bytet
    try {
      const s = readState(); s.group = g
      localStorage.setItem('svs_state', JSON.stringify(s))
    } catch { /* ok */ }
    go('pool')
  }
  const openHistorik = (p, focus = null) => {
    setHistProduct(p || null); setHistFocus(focus); go('historik')
  }

  return (
    <div className="v3">
      <header className="v3top">
        <button type="button" className="v3brand" onClick={() => go('idag')}>
          ⚽ Spelkompisen
        </button>
        <nav className="v3nav" aria-label="Vy">
          {VIEWS.map((v) => (
            <button key={v.id} className={view === v.id ? 'on' : ''}
              onClick={() => (v.id === 'oddset' ? openOddset(null) : go(v.id))}>
              <span aria-hidden="true">{v.icon}</span> {v.label}
            </button>
          ))}
        </nav>
        <div className="v3right">
          <Collection />
        </div>
      </header>
      <main className="v3main">
        {view === 'idag' && <ErrBoundary>
          <DashboardV3 openPool={openPool} openOddset={openOddset}
            openHistorik={openHistorik} openLabb={() => go('labb')} />
        </ErrBoundary>}
        {view === 'pool' && <ErrBoundary><PoolV3 /></ErrBoundary>}
        {view === 'oddset' && <ErrBoundary><OddsetView focus={oddsetFocus} /></ErrBoundary>}
        {view === 'historik' && <ErrBoundary>
          <PlayedPanel />
          <HistorikV3 initialProduct={histProduct} focus={histFocus} />
        </ErrBoundary>}
        {view === 'labb' && <ErrBoundary><LabbV3 /></ErrBoundary>}
      </main>
      <footer className="v3foot">Lokal data från Svenska Spel + Pinnacle · personligt verktyg</footer>
    </div>
  )
}
