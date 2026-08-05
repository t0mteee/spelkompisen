// Appens skal (enda gränssnittet sedan 2026-07-26, då klassiska vyn revs).
// De tunga komponenterna (analys/bygg/kupong/oddset) importeras från App.jsx,
// som är komponentbiblioteket. Eget här: skalet med vyväxlingen samt
// Idag-översikten, Historik-vyn (PH1-settlementlagret) och Labb.
import { useEffect, useState } from 'react'
import './AppV3.css'
import {
  AnalysisTable, SystemView, CouponPanel, SharpPanel, SteamPanel, ClvPanel,
  BombenView, OddsetView, Legend, Collection, LoadingState, EmptyState,
  ErrorState, ErrBoundary, STRATEGIES, STRATEGY_EV, BUDGET_STOPS,
  SYSTEM_BASE, SYSTEM_SVS, VARIANT, kr, fmtClose, PlayRec,
  PlayedPanel, oddsetBestValue, SortableTable,
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

// Som get(), men lyfter fram backendens detail-text. Bor på modulnivå:
// cache-busterns Date.now() får inte ligga i en komponentkropp.
const getDetail = (url, label) => fetch(`${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}`,
  { cache: 'no-store' }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json()).detail || `${label} ${r.status}`)
    return r.json()
  })

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
  // Läs localStorage exakt en gång vid mount. Lat useState-init i stället för
  // useRef(...).current, som annars läses under render.
  const [saved] = useState(readState)
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
  // 256 = PH3:s champion (`b256-medel`). Standarden MÅSTE spegla championen,
  // annars mäter systemfacit en byggare som inte är den du faktiskt kör: fram
  // till 2026-08-05 stod reglaget på 128 medan championen var registrerad som
  // 50 kr, så etiketten "champion = dagens byggare" var osann.
  const [budget, setBudget] = useState(saved.budget || 256)
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
      setSys(await getDetail(
        `/api/system?product=${product}&draw=${draw}&strategy=${encodeURIComponent(strategy)}&budget=${budget}&value_weight=${vw}&${q}${jp}`,
        'System'))
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
              {/* Byggarens inställningar följer med till bokföringen. Utan dem
                  gick det inte att i efterhand se VILKET slags förslag en
                  spelad kupong byggde på — alla rader före 2026-08-05 har
                  därför okänd förslagstyp, och de bakfylls aldrig. */}
              <CouponPanel matches={analysis.matches} picks={picks} pickRows={pickRows}
                payouts={payouts} product={product} draw={draw} onClear={clearCoupon}
                buildConfig={{ strategy, budget, value_weight: valueWeight / 100,
                  source: sys ? 'byggare' : 'manuell' }} />
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
// Historik är 100 % POOL (Labb är 100 % odds — se CLAUDE.md). Ombyggd
// 2026-08-05: se docs/historik-ui-2026-08-05.md för före/efter-mätningarna.
//
// Bärande principer efter ombyggnaden:
//  * EN produktväljare överst styr HELA sidan. Tidigare styrde knapparna bara
//    omsättningstabellen 1 400 px längre ner, vilket läste som att de var
//    trasiga.
//  * Ingen parameter göms i en nyckelsträng. `ev50-tuff-vw80` blir tre
//    kolumner: budget, strategi, värdevikt.
//  * Insats och ackumulerat satsat är olika saker och står aldrig i samma
//    kolumn.

const PRODUCT_LABEL = Object.fromEntries(
  HIST_PRODUCTS.map((p) => [p.id, p.label]))
const STRATEGY_LABEL = { säker: 'Säker', medel: 'Medel', tuff: 'Tuff' }

// Horisonten är minuter före spelstopp. Nyckeln (`h3`/`m20`) är ett internt
// id som aldrig ska nå användaren — brödtexten sa T−3 h medan tabellen sa h3.
const horizonLabel = (row) => (row?.horizon_minutes != null
  ? `${row.horizon_minutes} min` : row?.horizon || '–')

const pctSigned = (v) => (v == null ? '–'
  : `${v >= 0 ? '+' : ''}${Math.round(v * 100)} %`)
const roiCls = (v) => (v == null ? '' : v >= 0 ? 'v3pos' : 'v3neg')

/* Förslagstypen bakom en bokförd kupong. Kuponger före 2026-08-05 saknar den
   — de var aldrig observerade och bakfylls aldrig. */
function BuildBadge({ row }) {
  if (!row?.strategy && row?.budget == null) {
    return <span className="v3hint" title="Bokförd innan förslagstyp började
      sparas (2026-08-05). Uppgiften fanns aldrig och bakfylls inte.">okänd</span>
  }
  const parts = [
    row.budget != null ? `${Math.round(row.budget)} kr` : null,
    STRATEGY_LABEL[row.strategy] || row.strategy,
    row.value_weight != null ? `värde ${Math.round(row.value_weight * 100)} %` : null,
  ].filter(Boolean)
  return <span className="v3buildbadge">{parts.join(' · ')}</span>
}

/* Ett fryst system match för match: täckte vi tecknet som gick in, och hur
   stod folkets streck vid frysningen mot vid spelstopp? */
function SystemDetail({ product, draw, horizon, config, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    setD(null); setErr(null)
    get(`/api/pool/systems/detail?product=${product}&draw=${draw}`
      + `&horizon=${horizon}&config=${encodeURIComponent(config)}`)
      .then(setD).catch((e) => setErr(String(e)))
  }, [product, draw, horizon, config])
  const move = (e, sign) => {
    const a = e.streck_at_freeze?.[sign], b = e.streck_at_close?.[sign]
    if (a == null || b == null || a === b) return null
    const diff = b - a
    return <span className={diff > 0 ? 'v3neg' : 'v3pos'}> ({diff > 0 ? '+' : ''}{diff})</span>
  }
  return (
    <div className="v3sysdetail">
      <div className="v3sysdetailhead">
        <b>{PRODUCT_LABEL[product] || product} · omgång {draw} · {config}</b>
        <button className="v3more" onClick={onClose}>stäng ✕</button>
      </div>
      {err && <ErrorState message={err} />}
      {!d && !err && <LoadingState label="Hämtar systemet…" />}
      {d && !d.available && <EmptyState title="Systemet finns inte i ledgern" />}
      {d?.available && (
        <>
          <div className="v3sysdetailmeta">
            <span>{d.n_rows} rader · {kr(d.cost_kr)}</span>
            <span>fryst {horizonLabel(d)} före stopp{d.timely ? '' : ' (sen)'}</span>
            <span>bäst <b>{d.correct_max ?? '–'}</b> rätt</span>
            {d.n_missed > 0 && (
              <span className="v3neg" title="Matcher där inget av systemets tecken
                gick in. Varje sådan match sänker takresultatet med ett rätt.">
                missade {d.n_missed} {d.n_missed === 1 ? 'match' : 'matcher'}</span>
            )}
            <span className={roiCls(d.roi)}>{d.payout_complete === false
              ? 'utdelning okänd' : `${kr(d.payout_kr)} · ${pctSigned(d.roi)}`}</span>
          </div>
          <div className="v3histtablewrap">
            <table className="v3histtable v3sysfacit">
              <thead><tr>
                <th>#</th><th>Match</th><th>Facit</th><th>Vi spelade</th>
                <th title="Folkets procent när systemet frystes, och förändringen
                  fram till spelstopp.">Streck vid frysning → stopp</th>
              </tr></thead>
              <tbody>
                {d.events.map((e) => (
                  <tr key={e.event_number}
                    className={e.hit === false ? 'v3sysmiss' : ''}>
                    <td>{e.event_number}</td>
                    <td>{e.home && e.away ? `${e.home} – ${e.away}` : e.description}</td>
                    <td className="v3outcome">
                      {e.cancelled ? '⚠' : e.outcome || '–'}</td>
                    <td>{e.covered.join('')}{e.hit === false
                      ? <span className="v3neg" title="Systemet spelade inte det
                        tecken som gick in — inget av raderna kunde bli rätt här."> ✗</span>
                      : e.hit ? ' ✓' : ''}</td>
                    <td className="v3hint">
                      {['1', 'X', '2'].map((s) => (
                        <span key={s} className={e.outcome === s ? 'v3streckhit' : ''}>
                          {s} {e.streck_at_freeze?.[s] ?? '–'}{move(e, s)}{' '}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <span className="v3hint">"Vi spelade" är alla tecken systemet täcker på
            matchen — en enskild rad har förstås bara ett. Ett ✗ betyder att ingen
            rad kunde bli rätt där, vilket kapar hela systemets takresultat.
            Strecksiffran är folkets procent vid frysningen; talet inom parentes är
            rörelsen fram till spelstopp.</span>
        </>
      )}
    </div>
  )
}

function HistorikV3({ initialProduct, focus }) {
  const [product, setProduct] = useState(initialProduct || 'alla')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [detail, setDetail] = useState({})
  const [systems, setSystems] = useState(null)
  const [halsa, setHalsa] = useState(null)
  const [overview, setOverview] = useState(null)
  const [openSystem, setOpenSystem] = useState(null)
  const [showAllDraws, setShowAllDraws] = useState(false)
  const [showAllFreezes, setShowAllFreezes] = useState(false)
  const [showAllGroups, setShowAllGroups] = useState(false)
  // Pensionerade konfigurationer visas som standard. Att dölja dem gjorde
  // sidan tom trots 33 frysta omgångar i databasen — historik som finns ska
  // synas, tydligt märkt, och kunna döljas aktivt i stället för tvärtom.
  const [showRetired, setShowRetired] = useState(true)

  // ETT filter styr hela sidan. `alla` visar tvärsnittet; en produkt filtrerar
  // kuponger, systemfacit OCH omsättning samtidigt.
  const single = product !== 'alla'

  useEffect(() => {
    if (!single) { setData(null); setErr(null); return }
    setData(null); setErr(null); setExpanded(null)
    get(`/api/pool/history?product=${product}&limit=400`)
      .then(setData).catch((e) => setErr(String(e)))
  }, [product, single])
  useEffect(() => {
    get('/api/pool/systems').then(setSystems).catch(() => setSystems(null))
    get('/api/pool/turnover-prognos').then(setHalsa).catch(() => setHalsa(null))
  }, [])
  useEffect(() => {
    Promise.all(HIST_PRODUCTS.map((p) => get(`/api/pool/history?product=${p.id}&limit=1`)
      .then((j) => [p.id, j]).catch(() => [p.id, null])))
      .then((pairs) => setOverview(Object.fromEntries(pairs)))
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
  const shownDraws = showAllDraws ? draws : draws.slice(0, 20)
  const sparkVals = [...draws].reverse().map((d) => d.turnover)
  const inScope = (row) => !single || row.product === product

  const groups = (systems?.groups || [])
    .filter(inScope).filter((g) => showRetired || !g.retired)
  const champRows = (systems?.champion_report?.rows || []).filter(inScope)
  const recent = (systems?.recent || [])
    .filter(inScope).filter((r) => showRetired || !r.retired)

  return (
    <div className="v3hist">
      <div className="v3histbar">
        <nav className="v3subnav" aria-label="Spel">
          <button className={product === 'alla' ? 'on' : ''}
            onClick={() => setProduct('alla')}>Alla spel</button>
          {HIST_PRODUCTS.map((p) => (
            <button key={p.id} className={product === p.id ? 'on' : ''}
              onClick={() => setProduct(p.id)}>{p.label}</button>
          ))}
        </nav>
        <span className="v3hint">Filtret styr hela sidan — kuponger, systemfacit
          och omsättning.</span>
      </div>

      {/* ---------------------------- kuponger ---------------------------- */}
      <div className="v3card">
        <div className="v3cardhead"><h3>🎟 Dina spelade kuponger</h3></div>
        <PlayedPanel product={single ? product : null} />
      </div>

      {/* --------------------------- systemfacit -------------------------- */}
      <div className="v3card v3systembox" id="hist-system">
        <div className="v3cardhead"><h3>📋 Systemfacit</h3>
          {systems?.champion_key && (
            <span className="v3hint">champion: {systems.champion_key}</span>)}
        </div>
        <span className="v3hint">
          Före varje spelstopp fryser varvet vad radbyggaren föreslår — vid
          180 min och vid 20 min — och rättar sedan raderna mot riktigt utfall.
          <b> Championen är appens egen standardinställning</b>; övriga är
          utmanare. Ingen inställning byts förrän en utmanare slår championen på
          data som samlats EFTER att den registrerades, med minst{' '}
          {systems?.champion_report?.gate_min_draws ?? 40} omgångar och
          FDR-korrigering över hela utmanarfamiljen. Utdelningen är en
          kontrafaktisk uppskattning: den publicerade nivån späds med våra egna
          vinnande rader.
        </span>

        {!champRows.length && (
          <div className="v3note">
            <b>Champion mot utmanare startar om.</b> Matrisen byttes 2026-08-05
            till fyra insatser (144/256/512/1024 kr) × tre riskprofiler, med
            256 kr medel som champion — samma inställning som appens byggare
            använder. Jämförelsen fylls på från nästa frysning. Historiken
            nedan tillhör den gamla matrisen och är jämförbar bara med sig
            själv.
          </div>
        )}
        {champRows.length > 0 && (
          <>
            <h4 className="v3subhead">Champion mot bästa utmanare</h4>
            <div className="v3histtablewrap">
              <table className="v3histtable">
                <thead><tr>
                  <th>Spel</th><th title="Minuter före spelstopp">Fryst</th>
                  <th>Champion</th><th>Bästa utmanare</th><th>Skillnad</th>
                  <th title="Antal omgångar där BÅDA har facit — jämförelsen är
                    parad, annars jämförs olika omgångar.">Parade omgångar</th>
                  <th>Läge</th>
                </tr></thead>
                <tbody>
                  {champRows.map((r) => {
                    const b = r.best_challenger
                    return (
                      <tr key={`${r.product}-${r.horizon}`}>
                        <td>{PRODUCT_LABEL[r.product] || r.product}</td>
                        <td>{horizonLabel(r)}</td>
                        <td className={roiCls(r.champion_roi)}>
                          {pctSigned(r.champion_roi)}
                          <span className="v3hint"> ({r.champion_n} omg)</span></td>
                        <td>{b ? <>{b.config_key}{' '}
                          <span className={roiCls(b.roi)}>{pctSigned(b.roi)}</span></>
                          : '–'}</td>
                        <td className={b ? roiCls(b.delta_roi) : ''}>
                          {b ? pctSigned(b.delta_roi) : '–'}</td>
                        <td>{b ? b.n_paired : '–'}</td>
                        <td>{r.promotable
                          ? <b className="v3pos">utmanare slår championen</b>
                          : <span className="v3hint">samlar underlag</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <span className="v3hint">Skillnaden räknas parat över omgångar där
              båda har facit. "Samlar underlag" betyder att skillnaden ännu inte
              går att skilja från slump — inte att championen är bäst.</span>
          </>
        )}

        {!groups.length && (
          <EmptyState title={showRetired ? 'Inga frysta system ännu'
            : 'Inga frysta system i nuvarande matris'}
            detail={showRetired
              ? 'Första frysningen sker automatiskt när nästa omgång går in i sitt 180-minutersfönster.'
              : 'Historiken nedan tillhör den pensionerade matrisen — kryssa i rutan för att visa den.'} />
        )}
        {groups.length > 0 && (
          <>
            <h4 className="v3subhead">Alla konfigurationer</h4>
            {/* Nya matrisen ger 12 konfigurationer × 2 horisonter per spel —
                120 rader över alla spel. Kapad som omsättningstabellen, annars
                äger den sidan igen. Sorteringen gäller HELA urvalet, så
                topplistan är de faktiskt bästa och inte de 20 första. */}
            <SortableTable id="hist-systemgroups" className="v3histtable"
              wrapperClassName="v3histtablewrap"
              defaultSort={{ key: 'roi', dir: 'desc' }}
              rows={groups} limit={showAllGroups ? null : 20}
              columns={[
                { key: 'product', label: 'Spel', defaultDir: 'asc',
                  value: (g) => PRODUCT_LABEL[g.product] || g.product },
                { key: 'budget', label: 'Insats/omgång',
                  title: 'Budgeten per omgång. Radpriset är 1 kr, så beloppet är också antalet rader.' },
                { key: 'strategy', label: 'Strategi', defaultDir: 'asc',
                  value: (g) => STRATEGY_LABEL[g.strategy] || g.strategy || '' },
                { key: 'value_weight', label: 'Värdevikt' },
                { key: 'horizon_minutes', label: 'Fryst',
                  title: 'Minuter före spelstopp' },
                { key: 'n_frozen', label: 'Bokförda',
                  title: 'Antal frysta förslag för gruppen.' },
                { key: 'n_evaluable', label: 'Med facit',
                  title: 'Frysta i tid, med känt resultat OCH känd utdelning — de enda ROI räknas på.' },
                { key: 'cost_kr', label: 'Totalt satsat',
                  title: 'Ackumulerat över omgångarna med facit — inte insatsen.' },
                { key: 'payout_kr', label: 'Utdelning est.' },
                { key: 'roi', label: 'ROI' },
                { key: 'best_correct', label: 'Bäst' },
              ]}
              renderRow={(g) => (
                <tr key={`${g.product}-${g.config_key}-${g.horizon}`}
                  className={g.retired ? 'v3retired' : ''}>
                  <td>{PRODUCT_LABEL[g.product] || g.product}</td>
                  <td>{g.primary ? '★ ' : ''}{g.budget != null ? kr(g.budget) : '–'}
                    {g.retired && <span className="v3hint" title="Pensionerad
                      konfiguration — ingår inte i nuvarande matris."> (gammal)</span>}</td>
                  <td>{STRATEGY_LABEL[g.strategy] || g.strategy || '–'}</td>
                  <td>{g.value_weight != null ? `${Math.round(g.value_weight * 100)} %` : '–'}</td>
                  <td>{horizonLabel(g)}</td>
                  <td>{g.n_frozen}{g.n_timely < g.n_frozen
                    ? <span className="v3hint"> ({g.n_frozen - g.n_timely} sena)</span> : ''}</td>
                  <td>{g.n_evaluable}{g.n_payout_incomplete
                    ? <span className="v3hint"> ({g.n_payout_incomplete} okänd utd.)</span> : ''}</td>
                  <td>{g.n_evaluable ? kr(g.cost_kr) : '–'}</td>
                  <td>{g.n_evaluable ? kr(g.payout_kr) : '–'}</td>
                  <td className={roiCls(g.roi)}>{pctSigned(g.roi)}</td>
                  <td>{g.best_correct ?? '–'}</td>
                </tr>
              )} />
            {groups.length > 20 && (
              <button className="v3more"
                onClick={() => setShowAllGroups(!showAllGroups)}>
                {showAllGroups ? 'visa topp 20 ▲'
                  : `visa alla ${groups.length} konfigurationer ▼`}</button>
            )}
          </>
        )}

        {(systems?.retired_keys || []).length > 0 && (
          <label className="v3toggle">
            <input type="checkbox" checked={showRetired}
              onChange={(e) => setShowRetired(e.target.checked)} />
            Visa den pensionerade matrisen ({systems.retired_keys.join(', ')}) —
            mätt före 2026-08-05 och jämförbar bara med sig själv
          </label>
        )}

        {recent.length > 0 && (
          <details className="v3recent">
            <summary className="v3hint">Enskilda frysningar ({recent.length}) —
              klicka en rad för att se systemet mot facit</summary>
            <div className="v3histtablewrap">
              <table className="v3histtable">
                <thead><tr><th>Spel</th><th>Omgång</th><th>Spelstopp</th>
                  <th>Fryst</th><th>Insats</th><th>Rader</th><th>Facit</th></tr></thead>
                <tbody>
                  {recent.slice(0, showAllFreezes ? recent.length : 20).map((r, i) => (
                    <tr key={i} className="v3histrowline" role="button" tabIndex={0}
                      onClick={() => setOpenSystem(r)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault(); setOpenSystem(r)
                        }
                      }}>
                      <td>{PRODUCT_LABEL[r.product] || r.product}</td>
                      <td>#{r.draw_number}</td>
                      <td>{r.close ? fmtDay(r.close) : '–'}</td>
                      <td>{horizonLabel(r)}{r.timely ? '' : ' (sen)'}</td>
                      <td><BuildBadge row={r} /></td>
                      <td>{r.n_rows} ({kr(r.cost_kr)})</td>
                      <td>{r.correct_max == null ? (r.settle_note || 'väntar')
                        : r.payout_complete === false
                          ? `${r.correct_max} rätt · utdelning okänd`
                          : `${r.correct_max} rätt · ${kr(r.payout_kr)} (${pctSigned(r.roi)})`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {recent.length > 20 && (
              <button className="v3more"
                onClick={() => setShowAllFreezes(!showAllFreezes)}>
                {showAllFreezes ? 'visa färre ▲' : `visa alla ${recent.length} ▼`}</button>
            )}
          </details>
        )}
        {openSystem && (
          <SystemDetail product={openSystem.product} draw={openSystem.draw_number}
            horizon={openSystem.horizon} config={openSystem.config_key}
            onClose={() => setOpenSystem(null)} />
        )}
      </div>

      {/* -------------------------- prognosträff -------------------------- */}
      {halsa && (
        <div className="v3card">
          <div className="v3cardhead"><h3>🧬 Prognosträff och κ-fönster</h3></div>
          <span className="v3hint">Slutomsättningen driver hela EV-räkningen, så
            prognosfelet hör hemma i poolens facit — det låg tidigare i Labb bland
            oddsmätningarna. Rullande backtest: medianabsolutfel, räknat enbart på
            data som fanns FÖRE respektive omgång. Veckodagsmetoden ska ligga under
            den gamla blandade medianen.</span>
          <div className="v3histtablewrap">
            <table className="v3histtable">
              <thead><tr><th>Spel</th><th>Prognosfel (veckodag)</th>
                <th>Gammal metod</th>
                <th title="Avgjorda omgångar efter 2026-07-24. Krävs innan nya
                  κ-varianter får föreslås.">PH4-fönster</th></tr></thead>
              <tbody>
                {Object.entries(halsa)
                  .filter(([p]) => !single || p === product)
                  .map(([p, h]) => (
                    <tr key={p}>
                      <td>{PRODUCT_LABEL[p] || p}</td>
                      <td>{h.medianfel_veckodag == null ? '–'
                        : `${(h.medianfel_veckodag * 100).toFixed(0)} %`}</td>
                      <td className="v3hint">{h.medianfel_blandad == null ? '–'
                        : `${(h.medianfel_blandad * 100).toFixed(0)} %`}</td>
                      <td>{h.ph4_oot}/{h.ph4_oot_krav}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* --------------------- omsättning och utdelning -------------------- */}
      {!single && overview && (
        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Omsättning och utdelning</h3></div>
          <span className="v3hint">Välj ett spel ovan för hela historiken.</span>
          <div className="v3histtablewrap">
            <table className="v3histtable">
              <thead><tr><th>Spel</th><th>Omgångar</th><th>Median toppvinst</th>
                <th>Utan toppvinnare</th><th>Medelomsättning</th></tr></thead>
              <tbody>
                {HIST_PRODUCTS.map((p) => {
                  const o = overview[p.id]
                  return (
                    <tr key={p.id} className="v3histrowline" role="button" tabIndex={0}
                      onClick={() => setProduct(p.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault(); setProduct(p.id)
                        }
                      }}>
                      <td>{p.label}</td>
                      <td>{o?.total ?? '–'}</td>
                      <td>{o?.stats?.median_top_amount ? kr(o.stats.median_top_amount) : '–'}</td>
                      <td>{o?.stats?.rollover_rate != null
                        ? `${Math.round(100 * o.stats.rollover_rate)} %` : '–'}</td>
                      <td>{o?.stats?.mean_turnover ? kr(o.stats.mean_turnover) : '–'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {single && (
        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Omsättning och utdelning ·{' '}
            {PRODUCT_LABEL[product] || product}</h3></div>
          {err && <ErrorState message={err} />}
          {!data && !err && <LoadingState label="Hämtar historik…" />}
          {data && !data.available && (
            <EmptyState title="Inga settlade omgångar ännu för detta spel"
              detail="Backfillen fyller på bakåt och snapshot-varvet settlar nya omgångar löpande." />
          )}
          {data?.available && (
            <>
              <div className="v3histkpis">
                <div className="v3kpi"><b>{data.total}</b><span>omgångar</span></div>
                <div className="v3kpi"><b>{String(data.first_close || '').slice(0, 4)}–{String(data.last_close || '').slice(0, 4)}</b><span>tidsspann</span></div>
                <div className="v3kpi"><b>{data.stats?.median_top_amount ? kr(data.stats.median_top_amount) : '–'}</b><span>median toppvinst</span></div>
                <div className="v3kpi"><b>{data.stats?.rollover_rate != null ? Math.round(100 * data.stats.rollover_rate) : 0} %</b><span>utan toppvinnare</span></div>
                <div className="v3kpi"><b>{data.stats?.mean_turnover ? kr(data.stats.mean_turnover) : '–'}</b><span>medelomsättning</span></div>
              </div>
              {sparkVals.filter(Boolean).length > 2 && (
                <div className="v3sparkbox">
                  <span className="v3hint">Omsättning, äldst → nyast ({draws.length} omgångar)</span>
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
                    {shownDraws.map((d) => {
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
              {draws.length > 20 && (
                <button className="v3more"
                  onClick={() => setShowAllDraws(!showAllDraws)}>
                  {showAllDraws ? 'visa senaste 20 ▲'
                    : `visa alla ${draws.length} omgångar ▼`}</button>
              )}
            </>
          )}
        </div>
      )}

      {/* ------------------- forskningsspår (pool) ------------------------ */}
      {/* Flyttade från Labb 2026-08-05: ytgränsen säger Historik = pool,
          Labb = odds — och pit-v4 är ett AKTIVT poolspår, inte ett arkivkort. */}
      <div className="v3card">
        <div className="v3cardhead"><h3>🔬 Forskningsspår (pool)</h3></div>
        <div className="v3histresearch">
          {HISTORIK_RESEARCH.map((c) => (
            <div key={c.title} className="v3histresearchrow">
              <div className="v3histresearchhead">
                <b>{c.icon} {c.title}</b>
                <LabbPill s={c.status} />
              </div>
              <span>{c.text}</span>
              <span className="v3hint">{c.date ? `${c.date} · ` : ''}<code>{c.doc}</code></span>
            </div>
          ))}
        </div>
        <span className="v3hint">Mätspår, inga tips. Statusarna beslutas enligt
          respektive dokuments förregistrerade regel — aldrig löpande.</span>
      </div>

      <div className="v3note">
        Historiskt <b>facit</b> ur settlementlagret (PH1): utfall, slutstreck,
        slutomsättning och utdelning per nivå. Kohorten är <code>final_only</code>
        {' '}— odds- och streckrörelser finns bara för lokalt observerade omgångar
        och kan aldrig bakfyllas.
      </div>
    </div>
  )
}


/* ================================= Labb =================================== */
// Bevisytan (konsolideringen "ett UI, två ytor", backlog punkt 7): ETT
// statuskort per mät-/shadowspår. Labb visar mätningar — Idag/Poolspel/Oddset
// är beslutsytan, Historik är facityta. Ingenting här är ett tips.
//
// Ombyggd 2026-08-05 (docs/labb-ui-nulage-2026-08-05.md): öppet läge visar
// bara AKTIVA versioner — allt synligt CLV-facit var historiska hashar utan
// markering. Historik per version ligger bakom togglar med datumintervall;
// ROI/KI visas aldrig under ROI_MIN_N; poolens forskningsspår renderas i
// Historik (ytgränsen: Historik = pool, Labb = odds).

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
  // sekundära/utforskande grupper — bara läsbara etiketter, ingen statuseffekt
  bestadeild: 'Besta deild', friendlies: 'Träningsmatcher',
  champions_league: 'Champions League', europa_league: 'Europa League',
  conference_league: 'Conference League',
  premier_league: 'Premier League', serie_a: 'Serie A',
  la_liga: 'La Liga', bundesliga: 'Bundesliga',
}
const LABB_MARKET = {
  '1x2': '1X2', ah: 'AH', ou: 'Ö/U', cor: 'Hörnor',
}
const LABB_BOOK = {
  svenskaspel: 'SvS', expekt: 'Expekt', ninjacasino: 'Ninja/Altenar',
  pinnacle: 'Pinnacle', smarkets: 'Smarkets',
}

// Avslutade/pågående forskningsspår utan eget API — daterade kort med källdok.
// Ytgränsen (2026-08-05) gäller även dessa: odds-spåren bor här, pool-spåren
// (pit-v4, PH5, startOdds) renderas i Historik via HISTORIK_RESEARCH nedan.
const LABB_RESEARCH = [
  { icon: '🧮', title: 'Devig-ablation', date: '2026-07-26', status: 'pass',
    text: 'Konsensusflaggor +4,40 % [+2,54..+6,14] mot bara-power −0,49 % — devig-tvetydighet är en äkta filtersignal.',
    doc: 'docs/devig-ablation-2026-07-26.md' },
  { icon: '🔮', title: 'Close-drift v1', date: '2026-07-26', status: 'fals',
    text: 'Momentum FALSIFIERAD; tidiga AH/Ö/U-skift reverserar.',
    doc: 'docs/close-drift-facit-2026-07-26.md' },
  { icon: '🔬', title: 'V2.2 flerliga-shadow', status: 'samlar',
    text: 'Ren shadow, manifest v4 från 2026-08-01 21:20Z — inga tips, notiser eller CLV.',
    doc: 'docs/model-v2.2-multileague-forward-manifest-v4.json' },
]

// Poolens forskningsspår — visas i Historik (Historik = pool, Labb = odds).
const HISTORIK_RESEARCH = [
  { icon: '📐', title: 'pit-v4 (pool-streckmove-v3)', status: 'samlar',
    text: 'Forward samlar, gate ≥40 out-of-time-omgångar per produkt.',
    doc: 'docs/pool-ph4-forward-manifest-v3.json' },
  { icon: '🎟', title: 'PH5 256/512 rader', date: '2026-07-26', status: 'fals',
    text: 'Värderader ger ingen påvisad fördel på 13-matchsspel ens vid 512 rader.',
    doc: 'docs/ph5-radvalsablation-512rader-2026-07-26.json' },
  { icon: '🔓', title: 'startOdds', date: '2026-07-26', status: 'pass',
    text: 'Upplåst som omgångs-kovariat (final_only) — aldrig som PIT-observation.',
    doc: 'docs/startodds-semantik-2026-07-26.md' },
]

function LabbV3() {
  const [clv, setClv] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [radar, setRadar] = useState(null)
  const [err, setErr] = useState(null)
  // Ombyggt 2026-08-05 (docs/labb-ui-nulage-2026-08-05.md): öppet läge visar
  // bara AKTIVA versioner — 26 av 26 synliga CLV-rader var historiska hashar
  // utan markering. Historik finns kvar bakom egna togglar, aldrig raderad.
  const [showClvHistory, setShowClvHistory] = useState(false)
  const [showOldModels, setShowOldModels] = useState(false)
  const [showLedger, setShowLedger] = useState(false)
  const [ledgerOld, setLedgerOld] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [logLimit, setLogLimit] = useState(200)
  const [logLeague, setLogLeague] = useState('alla')
  const [logStatus, setLogStatus] = useState('alla')

  useEffect(() => {
    // engångsläsning — mätserierna rör sig på varv-/veckoskala, ingen poll
    get('/api/oddset/clv').then(setClv).catch((e) => { setClv(null); setErr(String(e)) })
    get('/api/oddset/predictions').then(setLedger).catch(() => setLedger(null))
    get('/api/oddset/radar-facit').then(setRadar).catch(() => setRadar(null))
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
    suspended: 'Ö/U var suspenderat vid signalen',
  }[row.odds_status] || (row.odds_status?.startsWith('source_error')
    ? 'oddsfel vid signalen' : 'liveodds saknas'))
  const radarOverResult = (v) => ({
    win: 'vinst', half_win: 'halvvinst', push: 'återbetald',
    half_loss: 'halvförlust', loss: 'förlust',
  }[v] || v)

  const dShort = (ts) => ts ? new Date(ts).toLocaleDateString('sv-SE', {
    day: 'numeric', month: 'short',
  }) : null
  const verSpan = (g) => g.first_at_min
    ? `${dShort(g.first_at_min)} – ${dShort(g.first_at_max)}` : '–'
  const dayWord = (n) => (n === 1 ? 'dag' : 'dagar')

  const primaryClv = (clv?.groups || []).filter((g) =>
    g.tier === 'sharp' && g.market === '1x2' && LABB_PRIMARY.includes(g.league))
  const activeSharp = clv?.active_versions?.sharp
  const activePrimaryClv = primaryClv.filter((g) => g.active)
  const historicPrimaryClv = primaryClv.filter((g) => !g.active)
  const a2 = clv?.anchor2
  const candidateReq = ledger?.criteria?.candidate || {
    n_resolved: 50, n_matches: 30, span_days: 28,
  }
  const modelCloseRows = ledger?.model_close?.summary || []
  const modelCloseCurrent = modelCloseRows.filter((g) => g.active_version)
  const modelCloseOld = modelCloseRows.filter((g) => !g.active_version)
  const ledgerGroups = ledger?.groups || []
  const ledgerActive = ledgerGroups.filter((g) => g.active_version)
  const ledgerShown = ledgerOld ? ledgerGroups : ledgerActive
  const activePrimaryGroups = (ledger?.groups || []).filter(
    (g) => g.primary && g.active_version)

  // Signalloggen filtreras FÖRE kapningen — annars blir "200 första" en
  // godtycklig blandning i stället för de 200 senaste inom filtret.
  const logRows = clv?.rows || []
  const logLeagues = [...new Set(logRows.map((r) => r.league).filter(Boolean))].sort()
  const logFiltered = logRows.filter((r) =>
    (logLeague === 'alla' || r.league === logLeague)
    && (logStatus === 'alla'
      || (logStatus === 'stangda' ? r.closing_fair != null : r.closing_fair == null)))

  // Under denna gräns visas ingen ROI/KI — bara den ärliga räknaren. n=2 gav
  // "Över-ROI −100 %" i rött, vilket läses som facit i stället för brus.
  const gate = radar?.signal_ledger?.blind_gate
  const gateN = gate?.n_priced_settled ?? 0
  const ROI_MIN_N = 10
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

  const clvHistCols = [
    { key: 'league', label: 'Liga', defaultDir: 'asc',
      value: (r) => LABB_LEAGUE[r.league] || r.league },
    { key: 'period', label: 'Period', value: (r) => r.first_at_max || '',
      title: 'Första till sista flaggan i gruppen' },
    { key: 'version', label: 'Version',
      title: 'Processens fingeravtryck — varje ändring av urval, parametrar eller databehandling byter version' },
    { key: 'n_resolved', label: 'Stängda' },
    { key: 'avg_close_ev', label: 'Close-EV' },
    { key: 'ci', label: '90 % KI', sortable: false },
  ]

  return (
    <div className="v3labb">
      <h2 className="v3labbtitle">Mätningar och skuggspår — INGET här är tips.</h2>
      <p className="v3hint v3labblegend">
        Status: <b>SAMLAR</b> serien växer · <b>CANDIDATE</b> mängdkrav nått,
        beslut tas enligt förregistrerad regel · <b>GATE-PASS</b> grinden
        passerad · <b>FALSIFIERAD</b> föll mot facit. En version är processens
        fingeravtryck — varje processändring byter version och börjar om
        räkningen; historiken ligger kvar bakom togglar.
      </p>
      {err && !clv && <ErrorState message={err} />}
      <div className="v3grid">

        {/* Sammanslaget 2026-08-05: Signal-facit + Utfalls-facit läste samma
            API och utfallskortet hade 1 datarad i ett grid-sträckt 1800px-kort.
            Öppet läge = aktiva versionen; historiska versioner bakom toggle. */}
        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Sharp-facit (CLV och utfall)</h3>
            <LabbPill s={activePrimaryClv.some((g) => g.green_ready) ? 'pass' : 'samlar'} /></div>
          {!clv && !err && <LoadingState label="Hämtar facit…" />}
          {clv && (
            <>
              <div className="v3row">
                <b>Aktiv version</b>
                <span className="v3hint"><code>{activeSharp || '–'}</code></span>
                {!activePrimaryClv.length && <span>inga stängda flaggor ännu</span>}
              </div>
              {activePrimaryClv.map((g) => (
                <div key={`${g.league}-${g.version}`} className="v3row">
                  <b>{LABB_LEAGUE[g.league] || g.league}</b>
                  <span>{g.n_resolved}/{g.n} stängda</span>
                  <span className={evCls(g.avg_close_ev)}>{evPct(g.avg_close_ev)}</span>
                  <span className="v3hint">KI {ciStr(g.ci)}</span>
                </div>
              ))}
              {clv.sharp && (
                <div className="v3row">
                  <b>Alla versioner sedan start</b>
                  <span>{clv.sharp.n_resolved}/{clv.sharp.n} stängda</span>
                  <span className={evCls(clv.sharp.avg_close_ev)}>{evPct(clv.sharp.avg_close_ev)}</span>
                  <span className="v3hint">KI {ciStr(clv.sharp.ci)}</span>
                </div>
              )}
              {clv.sharp?.n_outcomes > 0 && (
                <div className="v3row" title="Resultatbaserad ROI till first-odds på settlade 1X2-flaggor, alla versioner. Display — grönt beslutas av close-EV-grinden.">
                  <b>1X2-utfall (display)</b>
                  <span>{clv.sharp.n_outcomes} settlade</span>
                  <span className={evCls(clv.sharp.result_roi)}>{evPct(clv.sharp.result_roi)} ROI</span>
                  <span className="v3hint">träff {rate(clv.sharp.hit_rate)}</span>
                </div>
              )}
              {historicPrimaryClv.length > 0 && (
                <button className="v3evidence-toggle"
                  onClick={() => setShowClvHistory(!showClvHistory)}
                  aria-expanded={showClvHistory}>
                  {showClvHistory ? 'Dölj historiska versioner ▲'
                    : `Visa ${historicPrimaryClv.length} historiska versionsgrupper ▼`}
                </button>
              )}
              {showClvHistory && (
                <SortableTable id="labb-clv-history" columns={clvHistCols}
                  rows={historicPrimaryClv}
                  defaultSort={{ key: 'period', dir: 'desc' }}
                  className="logtable" wrapperClassName="v3evidence-table"
                  renderRow={(g) => (
                    <tr key={`${g.league}-${g.version}`} className="historical-version">
                      <td>{LABB_LEAGUE[g.league] || g.league}</td>
                      <td>{verSpan(g)}</td>
                      <td><code>{g.version}</code></td>
                      <td>{g.n_resolved}/{g.n}</td>
                      <td className={g.avg_close_ev == null ? ''
                        : g.avg_close_ev >= 0 ? 'v3pos' : 'v3neg'}>{evPct(g.avg_close_ev)}</td>
                      <td>{ciStr(g.ci)}</td>
                    </tr>
                  )} />
              )}
            </>
          )}
          <span className="v3hint">Close-EV mot devigad Pinnacle-stängning,
            winsoriserad ±20 %. Utfalls-ROI är brusig vid låga n och ändrar inga
            grindar — close-EV äger beslutet. Grönt beslutas per liga × marknad ×
            version på veckokadens; aggregat ändrar aldrig gruppstatus.</span>
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
          {modelCloseCurrent.length > 0 && (
            <div className="model-close-wrap">
              <div className="model-close-title">
                <b>🧪 Modell mot Pinnacle-close</b>
                <span className="v3hint">nuvarande modellversion, alla frysta
                  prediktioner även oflaggade · M = modellens snittfel, P =
                  Pinnacles, i procentenheter — lägre är bättre</span>
              </div>
              <div className="model-close-grid">
                {modelCloseCurrent.map((g) => (
                  <div className={`model-close-card ${g.status}`}
                    key={`${g.market}-${g.version}`}
                    title={`Parad log-score mot Pinnacle vid samma horisont. Positivt KI helt över noll krävs.\nVersion ${g.version}`}>
                    <div><b>{LABB_MARKET[g.market] || g.market}</b>
                      <span className={`model-close-status ${g.status}`}>
                        {modelCloseLabel(g.status)}</span></div>
                    <div className="model-close-mae">
                      M <b>{g.model_mae_pp?.toFixed(2) ?? '–'} pp</b>
                      {' '}· P <b>{g.sharp_mae_pp?.toFixed(2) ?? '–'} pp</b>
                    </div>
                    <div className="v3hint">{g.n_cases} fall · {g.n_matches} matcher ·
                      {' '}{g.span_days} {dayWord(g.span_days)} · <code>{g.version}</code></div>
                    {g.logscore_gain_ci && (
                      <div className="v3hint">log-score Δ {g.logscore_gain >= 0 ? '+' : ''}
                        {g.logscore_gain.toFixed(4)} · KI [{g.logscore_gain_ci[0].toFixed(4)}
                        ..{g.logscore_gain_ci[1].toFixed(4)}]</div>
                    )}
                  </div>
                ))}
              </div>
              {modelCloseOld.length > 0 && (
                <button className="v3evidence-toggle"
                  onClick={() => setShowOldModels(!showOldModels)}
                  aria-expanded={showOldModels}>
                  {showOldModels ? 'Dölj äldre modellversioner ▲'
                    : `Visa ${modelCloseOld.length} äldre versionsmätningar ▼`}
                </button>
              )}
              {showOldModels && (
                <div className="v3evidence-table">
                  <table className="logtable">
                    <thead><tr><th>Marknad</th><th>Version</th><th>Status</th>
                      <th title="Modellens snittfel i procentenheter">M pp</th>
                      <th title="Pinnacles snittfel i procentenheter">P pp</th>
                      <th>Fall</th><th>Dagar</th><th>log-score Δ</th></tr></thead>
                    <tbody>{modelCloseOld.map((g) => (
                      <tr key={`${g.market}-${g.version}`} className="historical-version">
                        <td>{LABB_MARKET[g.market] || g.market}</td>
                        <td><code>{g.version}</code></td>
                        <td>{modelCloseLabel(g.status)}</td>
                        <td>{g.model_mae_pp?.toFixed(2) ?? '–'}</td>
                        <td>{g.sharp_mae_pp?.toFixed(2) ?? '–'}</td>
                        <td>{g.n_cases}</td>
                        <td>{g.span_days}</td>
                        <td>{g.logscore_gain != null
                          ? `${g.logscore_gain >= 0 ? '+' : ''}${g.logscore_gain.toFixed(4)}`
                          : '–'}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
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
              {showLedger ? 'Dölj signalgrupperna ▲'
                : `Visa ${ledgerActive.length} aktiva signalgrupper ▼`}
            </button>
          )}
          {showLedger && (
            <>
              {ledgerGroups.length > ledgerActive.length && (
                <label className="v3checkline">
                  <input type="checkbox" checked={ledgerOld}
                    onChange={(e) => setLedgerOld(e.target.checked)} />
                  visa även {ledgerGroups.length - ledgerActive.length} grupper
                  från äldre versioner
                </label>
              )}
              <div className="v3evidence-table">
                <table className="logtable">
                  <thead><tr><th>Status</th><th>Grupp</th><th>Pred/kontroll</th>
                    <th>Flaggor</th><th>Bredd</th><th>Close-EV</th><th>90 % KI</th></tr></thead>
                  <tbody>{ledgerShown.map((g) => (
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
            </>
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
                <span className="v3hint"
                  title="Temperatur ur senaste oddsetcalibrate-körningen mot football-data-backtesten. t över 1 = modellen var översäker och plattas till; under 1 = försiktig och skärps. Display — ändrar inga grindar.">
                  🌡 Modelltemperatur: {Object.entries(clv.calibration)
                    .map(([lg, c]) => `${LABB_LEAGUE[lg] || lg} t=${c.t?.toFixed?.(2) ?? c.t} (n=${c.n})`)
                    .join(' · ')}</span>
              )}
              <button className="v3evidence-toggle" onClick={() => {
                if (!showLog) setLogLimit(200)
                setShowLog(!showLog)
              }}
                aria-expanded={showLog}>
                {showLog ? 'Dölj signalloggen ▲' : `Visa ${logRows.length} flaggade signaler ▼`}
              </button>
              {showLog && (
                <div className="v3logfilter">
                  <label>Liga{' '}
                    <select value={logLeague}
                      onChange={(e) => { setLogLeague(e.target.value); setLogLimit(200) }}>
                      <option value="alla">alla</option>
                      {logLeagues.map((lg) => (
                        <option key={lg} value={lg}>{LABB_LEAGUE[lg] || lg}</option>
                      ))}
                    </select></label>
                  <label>Status{' '}
                    <select value={logStatus}
                      onChange={(e) => { setLogStatus(e.target.value); setLogLimit(200) }}>
                      <option value="alla">alla</option>
                      <option value="stangda">stängda</option>
                      <option value="ostangda">ej stängda</option>
                    </select></label>
                  <span className="v3hint">{logFiltered.length} av {logRows.length} flaggor</span>
                </div>
              )}
              {showLog && (
                <div className="v3evidence-table">
                  <table className="logtable">
                    <thead><tr><th>Flagga</th><th>Match</th><th>Bok</th><th>Odds</th>
                      <th>Edge</th><th>Bäst</th><th>Stängning</th><th>Tier</th></tr></thead>
                    <tbody>{logFiltered.slice(0, logLimit).map((r, i) => {
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
              {showLog && logFiltered.length > logLimit && (
                <button className="v3evidence-toggle"
                  onClick={() => setLogLimit((n) => n + 200)}>
                  Visa {Math.min(200, logFiltered.length - logLimit)} till
                  {' '}({logLimit} av {logFiltered.length})
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
          {radar?.signal_version && (
            <span className="v3hint">Kohort <code>{radar.signal_version}</code>
              {radar.signal_version_started_at
                ? ` sedan ${dShort(radar.signal_version_started_at)}` : ''} —
              räknarna nedan nollställdes vid versionsbytet (kohortregeln);
              äldre kohorter ligger kvar i journalen.</span>
          )}

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
            Informationsläget före Följer är ingen signal. Skottmåttet har ingen Stark-nivå
            i den aktuella {radar?.signal_version || 'radarversionen'}.
            Första gången en nivå nås sparas; samma nivå varannan minut räknas inte som nya spel.</span>

          <div className="v3radar-gate">
            <b>Blindtest: första aktiva signalen per match</b>
            <span>{gateN} av{' '}
              {gate?.required_priced_settled ?? 200} oddssatta och avgjorda</span>
            <span>{gate?.span_days ?? 0} av{' '}
              {gate?.required_span_days ?? 60} dagar</span>
            {gateN >= ROI_MIN_N ? (
              <span>Över-ROI <b className={evCls(gate?.roi_over)}>
                {evPct(gate?.roi_over)}</b>{' '}
                KI90 {ciStr(gate?.roi_ci90)}</span>
            ) : (
              <span className="v3hint"
                title={`ROI och KI visas först vid ${ROI_MIN_N} oddssatta och avgjorda signalmatcher — enstaka utfall är brus, inte facit.`}>
                Över-ROI: för tidigt att mäta (n={gateN})</span>
            )}
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
                  <span>Över-ROI {g.n_settled >= ROI_MIN_N
                    ? <b className={evCls(g.roi_over)}>{evPct(g.roi_over)}</b>
                    : <span className="v3hint">för tidigt (n={g.n_settled})</span>}</span>
                </div>
              ))}
            </div>
          )}

          <details className="v3radar-old">
            <summary>Diagnostiskt rå-providerfacit utan liveodds</summary>
            <span className="v3hint">Detta jämför varje källas egna ögonblick och
              lånar inte klocka eller ställning från en annan källa. Signaljournalen
              ovan är facitet för det som faktiskt visades.</span>
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
                        ? `${row.final_home_score}–${row.final_away_score} · ${row.goals_after_signal} mål efter · Över ${row.over_result ? radarOverResult(row.over_result) : 'ej prissatt'}${row.over_profit == null ? '' : ` (${row.over_profit >= 0 ? '+' : ''}${row.over_profit.toFixed(2)} u)`}`
                        : 'väntar på slutresultat'}</span></div>
                  </div>
                ))}
              </div>
            </details>
          )}
          <span className="v3hint">Shadow: detta påverkar inga tips, Kelly, notiser eller
            systemförslag. Metod: <code>docs/live-radar-2026-07-25.md</code>.</span>
        </div>

        {/* PH3-systemledgern togs bort härifrån 2026-08-05. Den visade samma
            siffror som Historikens Systemfacit, fast grundare — och PH3 är
            pool, inte odds. Historik äger den nu, med champion-jämförelse och
            klick-in mot facit. */}

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
        {/* PlayedPanel monteras numera INNE i HistorikV3 så produktfiltret
            styr även kupongerna — den låg tidigare utanför och kunde därför
            inte filtreras. */}
        {view === 'historik' && <ErrBoundary>
          <HistorikV3 initialProduct={histProduct} focus={histFocus} />
        </ErrBoundary>}
        {view === 'labb' && <ErrBoundary><LabbV3 /></ErrBoundary>}
      </main>
      <footer className="v3foot">Lokal data från Svenska Spel + Pinnacle · personligt verktyg</footer>
    </div>
  )
}
