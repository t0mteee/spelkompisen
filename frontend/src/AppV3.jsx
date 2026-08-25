// Appens skal (enda gränssnittet sedan 2026-07-26, då klassiska vyn revs).
// De tunga komponenterna (analys/bygg/kupong/oddset) importeras från App.jsx,
// som är komponentbiblioteket. Eget här: skalet med vyväxlingen samt
// Idag-översikten, Historik-vyn (PH1-settlementlagret) och Labb.
import { useEffect, useRef, useState } from 'react'
import './AppV3.css'
import {
  beginRequest, payoutMatchesSelection, requestIsCurrent, uniqueDraws,
} from './poolSelection.js'
import {
  AnalysisTable, SystemView, CouponPanel, SharpPanel, SteamPanel, ClvPanel,
  BombenView, OddsetView, Legend, Collection, LoadingState, EmptyState,
  ErrorState, ErrBoundary, STRATEGIES, STRATEGY_EV, BUDGET_STOPS,
  SYSTEM_BASE, SYSTEM_SVS, FAMILY, kr, fmtClose, PlayRec,
  PlayedPanel, oddsetBestValue, SortableTable,
} from './App'
import { projectionBasisText } from './playRec.js'

const VIEWS = [
  { id: 'idag', label: 'Idag', icon: '☀️' },
  { id: 'pool', label: 'Poolspel', icon: '🎟️' },
  { id: 'oddset', label: 'Oddset', icon: '⚡' },
  { id: 'historik', label: 'Historik', icon: '🗄' },
  { id: 'ph5', label: '5 000-test', icon: '🧪' },
  { id: 'labb', label: 'Labb', icon: '🔬' },
]
const POOL_GAMES = [
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
  { id: 'bomben', label: 'Bomben' },
]
const ROW_MODELS = [
  {
    id: 'standard', label: 'Standard',
    note: 'Nuvarande modell. Reglaget kan väga mellan träffchans och högre värde.',
  },
  {
    id: 'hit', label: 'Träffsäkrare',
    note: 'Värdevikt 0. Fler topprätt i historiska 256/512-test, men oftare folkligare rader och lägre utdelning per träff. Inte ett X-skydd.',
  },
  {
    id: 'row_shape_v1', label: 'Radform v1 · test',
    note: 'Topptips-test som justerar väntade medvinnare efter antal X. Endast valbar vid 384 kr; fördelen höll inte vid 256/512.',
  },
]
const ROW_MODEL_LABEL = Object.fromEntries(ROW_MODELS.map((model) => [model.id, model.label]))
const HIST_PRODUCTS = [
  { id: 'stryktipset', label: 'Stryktipset' },
  { id: 'europatipset', label: 'Europatipset' },
  { id: 'topptipset', label: 'Topptipset' },
  { id: 'topptipsetstryk', label: 'Topptipset Stryk' },
  { id: 'topptipsetextra', label: 'Topptipset Extra' },
]
const PRODUCT_LABEL = Object.fromEntries(
  [...POOL_GAMES, ...HIST_PRODUCTS].map((p) => [p.id, p.label]))
/* Topptipset Dagens/Stryk/Extra är SAMMA spel hos Svenska Spel: åtta matcher,
   samma vinstplan (70 %), bara olika omgångar under olika namn (pid 25/23/24).
   På facit-korten räknas de därför som EN produkt.

   Detta är enbart en VISNINGSgruppering. Produktslug, settlementidentitet,
   PH3:s config_key och `benchmarks_for(product)` är oförändrade — en nyckel
   får aldrig byta betydelse i efterhand, och de tre har egna omgångsserier. */
const FAMILY_LABEL = { ...PRODUCT_LABEL, topptipset: 'Topptipset' }
// Väljarens poster: en per familj, i HIST_PRODUCTS ordning. Backend expanderar
// familjenyckeln via svenskaspel.GAME_GROUPS när `family=1` skickas med.
const HIST_FAMILIES = HIST_PRODUCTS
  .filter((p, i, all) => all.findIndex((q) => FAMILY(q.id) === FAMILY(p.id)) === i)
  .map((p) => ({ id: FAMILY(p.id), label: FAMILY_LABEL[FAMILY(p.id)] || p.label }))
const IS_FAMILY = (id) => HIST_PRODUCTS.filter((p) => FAMILY(p.id) === id).length > 1
// Under så här många utvärderingsbara observationer visas ingen ROI någonstans
// i appen — ett par rättade omgångar ger tresiffriga procenttal som är brus.
const ROI_MIN_N = 10

// Ett svar som inte är JSON betyder nästan alltid att backend är nere eller
// startar om: vite-proxyn svarar då med något annat än vårt API. Rått blir
// det "SyntaxError: The string did not match the expected pattern" i Safari
// — ett meddelande som inte säger användaren någonting alls (observerat i
// drift 2026-08-06 mitt under en omstart av :8002). Säg vad som hänt i
// stället; felet i sig är övergående och ett omladdat anrop löser det.
const OFFLINE = 'Backend svarade inte med data — servern kan vara nere eller '
  + 'starta om. Prova att ladda om om en liten stund.'

const asJson = async (r) => {
  try {
    return await r.json()
  } catch {
    throw new Error(OFFLINE)
  }
}

const get = (url, options = {}) => fetch(
  `${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}`,
  { cache: 'no-store', ...options }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`)
    return asJson(r)
  })

// Som get(), men lyfter fram backendens detail-text. Bor på modulnivå:
// cache-busterns Date.now() får inte ligga i en komponentkropp.
const getDetail = (url, label) => fetch(`${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}`,
  { cache: 'no-store' }).then(async (r) => {
    if (!r.ok) {
      // Felkroppen kan själv vara icke-JSON (proxyfel, gateway-sida).
      let detail = null
      try { detail = (await r.json()).detail } catch { /* ingen detail */ }
      throw new Error(detail || `${label} ${r.status}`)
    }
    return asJson(r)
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
// Avspark på Idag-korten: "idag 20:00" säger mer än ett datum, och nästan allt
// som ligger i värde-/rörelselistan spelas inom ett dygn.
function fmtKickoff(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const tid = d.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' })
  const dygn = Math.round(
    (new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000)
  if (dygn === 0) return `idag ${tid}`
  if (dygn === 1) return `imorgon ${tid}`
  return `${d.toLocaleDateString('sv-SE', { weekday: 'short', day: 'numeric', month: 'numeric' })} ${tid}`
}

/* Rörelsen i ODDS i stället för bara procentenheter: "1.92 → 1.68".

   `steam` och `value.fair` mäter SAMMA storhet — Pinnacles devigade
   1X2-sannolikhet (attach_steam respektive attach_value) — så skiftet kan
   uttryckas i odds utan någon ny insamling: sannolikheten då är den nu minus
   pp, och odds är inversen. Det är alltså den DEVIGADE kvoten, inte Pinnacles
   noterade pris (som ligger under sin marginal). Saknas fair för tecknet visas
   inget par alls hellre än ett påhittat. */
const oddsSkift = (m, sg, pp) => {
  const nu = m.value?.['1x2']?.[sg]?.fair
  if (nu == null || pp == null) return null
  const da = nu - pp / 100
  if (!(nu > 0 && nu < 1) || !(da > 0 && da < 1)) return null
  return `${(1 / da).toFixed(2)} → ${(1 / nu).toFixed(2)}`
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
  const [health, setHealth] = useState(null)
  const loadSeq = useRef(0)
  const abortRef = useRef(null)
  const deferredRef = useRef(new Set())

  const clearDeferred = () => {
    for (const id of deferredRef.current) window.clearTimeout(id)
    deferredRef.current.clear()
  }

  const load = () => {
    abortRef.current?.abort()
    clearDeferred()
    const controller = new AbortController()
    abortRef.current = controller
    const request = (url) => get(url, { signal: controller.signal })
    const seq = ++loadSeq.current
    const current = () => loadSeq.current === seq
    const defer = (fn, delay = 550) => {
      const id = window.setTimeout(() => {
        deferredRef.current.delete(id)
        if (current()) fn()
      }, delay)
      deferredRef.current.add(id)
    }
    const guarded = (promise, setter, fallback = null) => promise
      .then((value) => { if (current()) setter(value) })
      .catch((e) => {
        if (current() && e?.name !== 'AbortError') setter(fallback)
      })
    const mergePool = (row) => {
      if (!current()) return
      setPool((existing) => {
        const byId = new Map((existing || []).map((item) => [item.id, item]))
        byId.set(row.id, row)
        return POOL_GAMES.map((game) => byId.get(game.id)).filter(Boolean)
      })
    }
    // Ge navigationen ett kort, helt nätverksfritt fönster. Ett direkt tryck
    // på Oddset avmonterar Dashboarden före 650 ms och inget Idag-jobb hinner
    // då belasta FastAPI/SQLite. Stannar användaren kvar börjar korten ändå i
    // tid för cirka en sekund till första innehåll (samma nivå som tidigare).
    defer(() => {
      // Visa varje spelform så fort den är klar. Promise.all gjorde att en enda
      // långsam jackpot-/garantifråga höll hela kortet i laddningsläge. Själva
      // omgången visas direkt; pottdata väntar tills användaren hunnit välja vy.
      POOL_GAMES.forEach(async (g) => {
        let result
        try {
          const d = await request(`/api/draws?product=${g.id}`)
          const list = d.open?.length ? d.open : d.draws || []
          // NÄSTA spelstopp = tidigaste framtida stängning bland öppna omgångar
          // (listan kan innehålla passerade/sena poster — lita inte på list[0])
          const upcoming = list
            .filter((x) => x.reg_close_time && new Date(x.reg_close_time) > new Date())
            .sort((a, b) => new Date(a.reg_close_time) - new Date(b.reg_close_time))
          const first = upcoming[0]
          if (!first) result = { ...g, none: true }
          if (first) result = { ...g, draw: first, pay: null, count: upcoming.length }
        } catch { result = { ...g, none: true } }
        if (!current()) return
        mergePool(result)
        if (result.draw && g.id !== 'bomben') {
          defer(() => request(`/api/payouts?product=${result.draw.product}&draw=${result.draw.draw_number}`)
            .then((pay) => mergePool({ ...result, pay })).catch(() => {}))
        }
      })
      guarded(request('/api/dashboard/oddset'), setOddset)
    }, 650)

    // Sekundära Idag-kort startar inte förrän 1200 ms senare. Ett direkt klick
    // på Oddset hinner då avmontera Dashboarden och rensa timern, så dess
    // synkrona backendjobb hamnar aldrig framför Oddsets första svar.
    defer(() => {
      guarded(request('/api/oddset/predictions/summary'), setLedger)
      guarded(request('/api/pool/systems'), setSystems)
      guarded(request('/api/health'), setHealth)
      guarded(request('/api/pool/played?live=false'), (data) => {
        setPlayed(data)
        if (!data) return
        if ((data.coupons || []).some((coupon) => !coupon.settled_at)) {
          // Idag visar faktisk matchstatus och levande rader, inte den dyrare
          // oddsbaserade chansen som hör till Historiks detaljkort.
          guarded(request('/api/pool/played?chance=false'), setPlayed)
        }
      })
      Promise.all(HIST_FAMILIES.map((p) =>
        request(`/api/pool/history?product=${p.id}&limit=1${IS_FAMILY(p.id) ? '&family=1' : ''}`)
          .then((j) => [p.id, j]).catch(() => [p.id, null])
      )).then((pairs) => {
        if (current()) setHist(Object.fromEntries(pairs))
      })
    }, 1200)
  }
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') load()
    }
    load()
    const id = setInterval(tick, 120000)
    document.addEventListener('visibilitychange', tick)
    return () => {
      loadSeq.current += 1
      abortRef.current?.abort()
      clearDeferred()
      clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
  // load/clearDeferred hör till mountens controller och ska inte bytas under
  // dess livstid; varje ny vy får en ny komponent/controller.
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

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
      // Behåll BÅDA fönstren: 24 h utan 6 h döljer om skiftet är färskt eller gammalt.
      if (pp >= 1.5 && (!move || pp > move.pp)) move = { m, sg, pp, h6: sh.h6, h24: sh.h24 }
    }
    if (move) movers.push(move)
  }
  signals.sort((a, b) => (b.v.q ?? 0) - (a.v.q ?? 0))
  movers.sort((a, b) => b.pp - a.pp)
  const ligaNamn = Object.fromEntries((oddset?.leagues || []).map((l) => [l.key, l.name]))

  const research = (oddset?.leagues || []).filter((l) => l.research)
  const researchMatches = (oddset?.matches || []).filter((m) => m.research)
  const nextResearch = researchMatches.map((m) => m.start).filter(Boolean).sort()[0]
  const primaryGroups = (ledger?.groups || []).filter((g) => g.primary && g.active_version)
  const statusIcon = (s) => s === 'green' ? '✓' : s === 'candidate' ? '◐' : '●'
  // Signal-facit kokas ner: en grupp som ligger kvar på amber säger inget nytt
  // dag för dag. Rader ges bara åt grupper som FAKTISKT bytt läge; resten blir
  // en räknare plus den som kommit längst.
  const notableGroups = primaryGroups.filter((g) => g.status !== 'amber')
  const mostClosed = [...primaryGroups].sort((a, b) => (b.n_resolved || 0) - (a.n_resolved || 0))[0]
  const nGreen = primaryGroups.filter((g) => g.status === 'green').length
  // Historikfacit visade arkivantal ("699 omgångar sedan 2013") — ett tal som
  // aldrig ändras. Senast settlade omgången med utdelning gör kortet dagsfärskt.
  // Backend slår ihop Topptipsets tre slugs (family=1), så raden är redan
  // familjens senaste settlade omgång — den bär sin egen produkt för
  // djuplänken och för variantetiketten.
  const histRows = HIST_FAMILIES
    .map((p) => {
      const sum = hist?.[p.id]
      const senaste = sum?.draws?.[0]
      return {
        key: p.id, label: p.label, sum, senaste, total: sum?.total || 0,
        id: senaste?.product || p.id,
      }
    })
    .filter((r) => r.sum?.available)
    .sort((a, b) => new Date(b.senaste?.close || 0) - new Date(a.senaste?.close || 0))
  const poolIssues = health?.pools?.issues || []
  const poolErrors = poolIssues.filter((issue) => issue.level !== 'warning')
  const poolWarnings = poolIssues.filter((issue) => issue.level === 'warning')
  const v22Issues = health?.v22?.issues || []
  // Spelstoppen ligger i spelstoppsordning, inte i produktordning — kortet
  // svarar på "vad stänger härnäst". Grupper utan öppen omgång hamnar sist.
  const stops = [...(pool || [])].sort((a, b) => {
    if (!!a.none !== !!b.none) return a.none ? 1 : -1
    if (a.none) return 0
    return new Date(a.draw.reg_close_time) - new Date(b.draw.reg_close_time)
  })

  return (
    <div className="v3dash">
      {poolErrors.length > 0 && (
        <div className="v3alert" role="alert">
          <b>⚠️ Poolinsamlingen behöver tillsyn</b>
          {poolErrors.slice(0, 4).map((issue, i) => (
            <span key={`${issue.product}-${issue.kind}-${issue.draw_number || i}`}>
              {issue.product}{issue.draw_number ? ` omg ${issue.draw_number}` : ''}: {issue.message}
            </span>
          ))}
          {poolErrors.length > 4 && <span>+{poolErrors.length - 4} ytterligare fel</span>}
        </div>
      )}
      {poolWarnings.length > 0 && (
        <details className="v3notice">
          <summary>Historisk testdata saknas – dagens insamling fungerar</summary>
          <ul>
            {poolWarnings.map((issue, i) => (
              <li key={`${issue.product}-${issue.kind}-${issue.draw_number || i}`}>
                <b>{issue.product}{issue.draw_number ? ` omg ${issue.draw_number}` : ''}</b>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {v22Issues.length > 0 && (
        <div className="v3alert" role="alert">
          <b>⚠️ V2.2-insamlingen behöver tillsyn</b>
          {v22Issues.map((issue, i) => (
            <span key={`${issue.kind}-${i}`}>{issue.message}</span>
          ))}
        </div>
      )}
      {/* Toppraden har egna kolumnbredder: spelstoppen staplas en per rad och
          behöver bara en smal spalt, vilket ger värde- och rörelselistorna
          plats för liga, avspark och pris på samma rad. */}
      <div className="v3toprow">
        <div className="v3card">
          <div className="v3cardhead"><h3>🎟️ Nästa spelstopp</h3>
            <span className="v3hint">i spelstoppsordning</span></div>
          {!pool && <LoadingState label="Hämtar omgångar…" />}
          <div className="v3stops">
            {stops.map((g) => (
              <button key={g.id} className="v3stop" onClick={() => openPool(g.id)}>
                <span className="v3stoptop">
                  <b>{g.label}</b>
                  {!g.none && (
                    <span className={hoursTo(g.draw.reg_close_time) < 2 ? 'v3close soon' : 'v3close'}>
                      {closesIn(g.draw.reg_close_time)}</span>
                  )}
                </span>
                {g.none ? <span className="v3hint">ingen öppen omgång</span> : (
                  <>
                    <span className="v3hint">
                      omg {g.draw.draw_number}
                      {g.count > 1 ? ` · +${g.count - 1} till` : ''}
                    </span>
                    {g.pay?.available && (
                      <span className="v3kpis">
                        {/* Omsättningen NU, med prognosen som spelvärdet räknas
                            mot — de skiljer sig kraftigt tidigt i en omgång. */}
                        <span title={g.pay.projected_turnover > g.pay.turnover
                          ? `Omsatt hittills. Spelvärdet räknas mot prognostiserad slutomsättning ${kr(g.pay.projected_turnover)} (${projectionBasisText(g.pay.projection_basis)}).`
                          : 'Omsatt hittills — spelvärdet räknas mot denna.'}>
                          oms <b>{kr(g.pay.turnover)}</b>
                          {g.pay.projected_turnover > g.pay.turnover
                            ? ` → ${kr(g.pay.projected_turnover)}` : ''}</span>
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

        <div className="v3card">
          <div className="v3cardhead"><h3>💰 Värdespel</h3>
            <button className="v3more" onClick={() => openOddset('varde')}>alla →</button></div>
          {!signals.length && <span className="v3hint">Inga sharp-ankrade edges ≥ 2 % just nu.</span>}
          {signals.length > 0 && <span className="v3hint">sorterat på kvalitet (Kelly-andel),
            inte på rå edge — samma urval som värdekorten i Oddset</span>}
          {signals.slice(0, 5).map(({ m, mk, sg, v }, i) => (
            <div key={i} className="v3row v3feedrow">
              <span className="v3feedtop">
                <b>{selLabel3(m, mk, sg, v.line)}</b>
                <span className="v3edge">+{(v.edge * 100).toFixed(1)}%</span>
              </span>
              <span className="v3feedmatch">{m.home} – {m.away}</span>
              <span className="v3hint">
                {ligaNamn[m.league] || m.league}{m.start ? ` · ${fmtKickoff(m.start)}` : ''}
                {/* Priset mot det pris edgen FAKTISKT räknas mot: Pinnacle
                    devigad (1/fair). Pinnacles råa kvot ligger under sin marginal
                    och är inte den som jämförs — fair-procenten sa samma sak men
                    i en enhet som inte går att ställa bredvid bokens odds. */}
                {' · '}{v.book} {v.odds?.toFixed(2)}
                {v.fair ? ` mot Pinnacle ${(1 / v.fair).toFixed(2)} devigad` : ''}
                {v.q != null ? ` · kval ${(v.q * 100).toFixed(1)} %` : ''}
                {v.derived ? ' · härlett pris' : ''}
              </span>
              {/* "bekräftat kvar" får bara stå när det oförändrade bokpriset
                  återobserverats EFTER Pinnacles senaste prisändring. */}
              {v.held_after_sharp && <span className="v3held" title={`Bokpriset låg kvar oförändrat när det observerades efter Pinnacles senaste prisändring${v.sharp_changed_at ? ` (${fmtKickoff(v.sharp_changed_at)})` : ''} — inte bara ett färskt cachepris.`}>✓ bekräftat kvar</span>}
            </div>
          ))}
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>📈 Rörelser</h3>
            <button className="v3more" onClick={() => openOddset('radar')}>radar →</button></div>
          {!movers.length && <span className="v3hint">Inga devigade skift ≥ 1,5 pp senaste dygnet.</span>}
          {movers.slice(0, 5).map(({ m, sg, pp, h6, h24 }, i) => {
            // Rubriksiffran är det STÖRSTA av fönstren — oddsparet måste gälla
            // just det fönstret, annars beskriver de två olika rörelser.
            const drivande = (h24 != null && pp === h24) ? 24 : 6
            const andra = drivande === 24 ? h6 : h24
            const skift = oddsSkift(m, sg, pp)
            return (
              <div key={i} className="v3row v3feedrow">
                <span className="v3feedtop">
                  <b>{selLabel3(m, '1x2', sg)}</b>
                  <span className="v3steam">🔥 +{pp} pp</span>
                </span>
                <span className="v3feedmatch">{m.home} – {m.away}{m.research ? ' · 🔬' : ''}</span>
                <span className="v3hint">
                  {ligaNamn[m.league] || m.league}{m.start ? ` · ${fmtKickoff(m.start)}` : ''}
                  {skift ? ` · Pinnacle ${skift} på ${drivande} h` : ''}
                  {/* Det andra fönstret avgör om skiftet PÅGÅR eller är gammalt:
                      ett dygnsskift utan rörelse senaste sex timmarna är avstannat. */}
                  {andra != null
                    ? ` · ${drivande === 24 ? '6' : '24'} h ${andra >= 0 ? '+' : ''}${andra} pp`
                    : ''}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      <div className="v3grid">
        {(played?.coupons || []).some((c) => !c.settled_at) && (
          <div className="v3card">
            <div className="v3cardhead"><h3>🎟️ Dina kuponger</h3>
              <button className="v3more" onClick={() => openHistorik()}>facit →</button></div>
            {played.coupons.filter((c) => !c.settled_at).slice(0, 4).map((c) => {
              const live = c.live || {}
              const alive = Object.entries(live.alive_per_level || {})
                .map(([lvl, n]) => [Number(lvl), n])
                .filter(([, n]) => n > 0).sort((a, b) => b[0] - a[0])[0]
              return (
                <div key={`${c.product}-${c.draw_number}-${c.rows_hash}`} className="v3row">
                  <b>{FAMILY_LABEL[FAMILY(c.product)] || c.product} {c.draw_number}</b>
                  <span className="v3hint">
                    {c.n_rows} rader ({kr(c.cost_kr)}) · {live.n_decided ?? '–'}/{live.n_events ?? '–'} avgjorda
                    · fastställt {live.best_secure ?? '–'} rätt
                    {live.current_known > 0 && live.current_best != null
                      ? ` · läget nu ${live.current_best}/${live.current_known}` : ''}
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

        {/* Forskningsligor är DOLD så länge ingen liga är aktiv (2026-08-12:
            RESEARCH_LEAGUE_KEYS är tom). Kortet är inte borttaget — mekanismen
            synlig≠actionable finns kvar och kortet kommer tillbaka av sig självt
            om en liga åter märks research. */}
        {research.length > 0 && (
          <div className="v3card">
            <div className="v3cardhead"><h3>🔬 Forskningsligor</h3>
              <button className="v3more" onClick={() => openOddset(null)}>visa matcher →</button></div>
            <div className="v3row"><span className="v3hint">
              {research.map((l) => l.name).join(' · ')}</span></div>
            <div className="v3row">
              <b>{researchMatches.length} matcher insamlade</b>
              {nextResearch && <span className="v3hint">premiärer från {fmtDay(nextResearch)}</span>}
            </div>
            <span className="v3hint">V2.2 samlar data — odds och rörelser visas,
              inga signaler/Kelly/notiser förrän forwarddomen är klar.</span>
          </div>
        )}

        <div className="v3card">
          <div className="v3cardhead"><h3>🧭 Signal-facit</h3>
            <button className="v3more" onClick={openLabb}>detaljer i Labb →</button></div>
          {!primaryGroups.length && <span className="v3hint">Inga primära signalgrupper ännu.</span>}
          {primaryGroups.length > 0 && (
            <div className="v3row">
              <span className={`v3status ${nGreen ? 'green' : 'amber'}`}>{nGreen ? '✓' : '●'}</span>
              <b>{nGreen} av {primaryGroups.length} grupper gröna</b>
              <span className="v3hint">
                {primaryGroups.reduce((s, g) => s + (g.n_resolved || 0), 0)} stängda flaggor totalt
                {mostClosed ? ` · flest ${mostClosed.league} ${mostClosed.n_resolved}` : ''}
              </span>
            </div>
          )}
          {/* Bara grupper som FAKTISKT bytt läge får en egen rad — fem amber-rader
              som ser likadana ut dag efter dag är brus, inte facit. */}
          {notableGroups.map((g) => (
            <div key={`${g.league}-${g.market}`} className="v3row">
              <span className={`v3status ${g.status}`}>{statusIcon(g.status)}</span>
              <b>{g.league} · {g.market?.toUpperCase()}</b>
              <span className="v3hint">{g.status === 'green' ? 'grön' : 'kandidat'} ·
                {' '}{g.n_resolved} stängda flaggor</span>
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
            // En rad per PRODUKT, inte per produkt × horisont. config_key är
            // alltid championen och stod förut utskriven på var och en av de
            // tio raderna, vilket radbröt dem. Nu står den en gång i foten.
            const perProduct = new Map()
            for (const g of groups.filter((x) => x.primary)) {
              // Topptipsets tre slugs är samma spel och slås ihop till en rad.
              const key = FAMILY(g.product)
              const cur = perProduct.get(key)
                || { product: key, n_frozen: 0, n_evaluable: 0, n_settled: 0,
                     cost_kr: 0, payout_kr: 0, horizons: new Set() }
              cur.n_frozen += g.n_frozen
              cur.n_evaluable += g.n_evaluable
              cur.n_settled += g.n_settled
              // ROI aggregeras över KRONOR, aldrig som medel av gruppernas
              // ROI — en grupp med två omgångar skulle annars väga lika tungt
              // som en med tjugo.
              cur.cost_kr += g.cost_kr || 0
              cur.payout_kr += g.payout_kr || 0
              if (g.horizon_minutes != null) cur.horizons.add(g.horizon_minutes)
              perProduct.set(key, cur)
            }
            // Deterministisk ordning — förut kom raderna i API-ordning och såg
            // slumpmässiga ut. Mest rättat först, produktnamn som tiebreak.
            const rows = [...perProduct.values()].sort((a, b) =>
              (b.n_settled - a.n_settled) || a.product.localeCompare(b.product, 'sv'))
            const horisonter = [...new Set(rows.flatMap((r) => [...r.horizons]))].sort((a, b) => b - a)
            return (
              <>
                {rows.map((r) => {
                  // ROI döljs under ROI_MIN_N. En rättad omgång gav +898 %,
                  // vilket är brus presenterat som facit. Samma regel som Labb.
                  const moget = r.n_evaluable >= ROI_MIN_N && r.cost_kr > 0
                  const roi = moget ? r.payout_kr / r.cost_kr - 1 : null
                  return (
                    <div key={r.product} className="v3row">
                      <b>{FAMILY_LABEL[r.product] || r.product}</b>
                      <span className="v3hint">{r.n_frozen} frysta · {r.n_settled} rättade</span>
                      {roi != null
                        ? <span className={roi >= 0 ? 'v3edge' : 'v3steam'}
                          title={`Insats ${kr(r.cost_kr)} · utdelning ${kr(r.payout_kr)} över ${r.n_evaluable} jämförbara frysningar. Kontrafaktiskt system med egen vinnarutspädning — inte spelade pengar.`}>
                          {roi >= 0 ? '+' : ''}{Math.round(roi * 100)} %</span>
                        : <span className="v3hint">ROI vid {ROI_MIN_N}</span>}
                    </div>
                  )
                })}
                {/* Raderna räknar championfamiljen, `frozen`/`settled` HELA
                    benchmarkregistret (utmanare och pensionerade nycklar).
                    Skilj dem åt — annars summerar inte foten till raderna. */}
                <span className="v3hint">{systems?.champion_key || 'champion'} ·
                  {' '}fryses {horisonter.length ? horisonter.join(' och ') : '180 och 20'} min före stopp ·
                  {' '}{rows.reduce((s, r) => s + r.n_frozen, 0)} frysta i championfamiljen
                  {' '}({frozen} med utmanarna, {settled} rättade)</span>
              </>
            )
          })()}
        </div>

        <div className="v3card">
          <div className="v3cardhead"><h3>🗄 Historikfacit</h3>
            <button className="v3more" onClick={() => openHistorik()}>utforska →</button></div>
          {!histRows.length && <span className="v3hint">Settlementlagret fylls på — kör backfillen eller vänta in nästa varv.</span>}
          {/* Senast SETTLADE omgången med sin toppvinst — det är den som ändras.
              Arkivantalet ("699 omgångar sedan 2013") står kvar i foten. */}
          {histRows.slice(0, 4).map((r) => (
            <div key={r.key} className="v3row v3histrow" role="button" tabIndex={0}
              onClick={() => openHistorik(r.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault(); openHistorik(r.id)
                }
              }}>
              <b>{r.label}{r.senaste ? ` ${r.senaste.draw_number}` : ''}</b>
              {r.senaste ? (
                <span className="v3hint">
                  {fmtDay(r.senaste.close)} ·
                  {' '}oms {kr(r.senaste.turnover)}
                  {r.senaste.top_winners != null && r.senaste.tiers?.[0]
                    ? ` · ${r.senaste.top_winners} vinnare på ${r.senaste.tiers[0].correct} rätt`
                    : ''}
                  {r.senaste.top_amount ? ` · ${kr(r.senaste.top_amount)}` : ''}
                </span>
              ) : <span className="v3hint">{r.total} omgångar i arkivet</span>}
            </div>
          ))}
          <span className="v3hint">
            {histRows.reduce((s, r) => s + (r.total || 0), 0)} settlade omgångar i arkivet —
            slutstreck, omsättning och full utdelning per omgång, facit och aldrig prematch-input.
            Topptipset Dagens, Stryk och Extra räknas som ett spel.</span>
        </div>
      </div>
    </div>
  )
}

/* =============================== Poolspel ================================= */

function ComplementaryChooser({ primary, meta, onUsePrimary, onUseAlternative }) {
  const alternative = meta.system
  const anchors = (items) => items.map((anchor) => (
    <div className="complementary-anchor" key={`${anchor.event_number}:${anchor.sign}`}>
      <b>Match {anchor.event_number}: {anchor.sign}</b>
      <span>{anchor.description}</span>
    </div>
  ))
  const overlapPct = Math.round(meta.row_overlap_pct * 100)
  return (
    <div className="complementary-summary">
      <div className="complementary-title">
        <div>
          <strong>Välj scenario A eller B</strong>
          <span>Två separata kuponger som bygger på olika matcher</span>
        </div>
        <b>{kr(meta.cost_each)} vardera · {kr(meta.total_cost)} för båda</b>
      </div>
      <div className="complementary-options">
        <article className="complementary-option option-a">
          <header><em>A</em><div><strong>Kupong A</strong>
            <span>{primary.num_rows} rader · {kr(primary.cost)}</span></div></header>
          <small>Bygger främst på</small>
          {anchors(meta.primary_spikes)}
          <button className="primary" onClick={onUsePrimary}>Använd kupong A</button>
        </article>
        <article className="complementary-option option-b">
          <header><em>B</em><div><strong>Kupong B</strong>
            <span>{alternative.num_rows} rader · {kr(alternative.cost)}</span></div></header>
          <small>Bygger främst på</small>
          {anchors(meta.alternative_spikes)}
          <button className="primary" onClick={onUseAlternative}>Använd kupong B</button>
        </article>
      </div>
      <div className="complementary-result">
        <b>{overlapPct === 0 ? 'Inga identiska rader' : `${overlapPct} % identiska rader`}</b>
        <span>Varje kupong garderar minst hälften av den andras ankartecken.</span>
      </div>
      {meta.below_preferred_quality && (
        <div className="complementary-tradeoff">
          <b>Större riskspridning kostar modellstyrka den här omgången</b>
          <span>Riktmärket är {Math.round(meta.preferred_quality_floor * 100)} %. A når{' '}
            {Math.round(meta.primary_quality_ratio * 100)} % och B{' '}
            {Math.round(meta.alternative_quality_ratio * 100)} %, men båda håller det hårda
            minimigolvet {Math.round(meta.quality_floor * 100)} %. Procenten är ett internt
            jämförelsemått, inte vinstchans.</span>
        </div>
      )}
      <details className="complementary-tech">
        <summary>Visa teknisk jämförelse</summary>
        <p>{meta.row_overlap} av {primary.num_rows} rader är exakt lika. Modellstyrka mot
          singelförslaget: A {Math.round(meta.primary_quality_ratio * 100)} % och B{' '}
          {Math.round(meta.alternative_quality_ratio * 100)} %. Detta är ett internt
          rankningsmått, inte vinstsannolikhet.</p>
      </details>
    </div>
  )
}

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
  const [rowModel, setRowModel] = useState(() => {
    if (!ROW_MODELS.some((model) => model.id === saved.rowModel)) return 'standard'
    if (saved.rowModel === 'row_shape_v1' && (saved.budget || 256) !== 384) {
      return 'standard'
    }
    return saved.rowModel
  })
  const [complementaryMode, setComplementaryMode] = useState(
    saved.sysType === 'ev' && saved.rowModel !== 'row_shape_v1'
    && saved.complementaryMode === true)
  const [picks, setPicks] = useState(saved.picks || {})
  const [pickRows, setPickRows] = useState(saved.pickRows || null)
  const [couponVariant, setCouponVariant] = useState(saved.couponVariant || null)
  const [couponModel, setCouponModel] = useState(saved.couponModel || null)
  const [couponValueWeight, setCouponValueWeight] = useState(
    saved.couponValueWeight ?? null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [bombenNonce, setBombenNonce] = useState(0)
  // Varje omladdning får ett löpnummer. Ett sent svar från föregående
  // omgång får aldrig skriva över analys, rörelse eller pott för den som nu
  // är vald — särskilt jackpotten går direkt in i både ROI och radbyggaren.
  const loadSequence = useRef(0)

  const loadAnalysis = async (p = product, dn = draw, silent = false) => {
    if (!dn) return
    const sequence = beginRequest(loadSequence)
    if (!silent) { setLoading(true); setErr(null); setSelected(null) }
    try {
      const a = await get(`/api/analysis?product=${p}&draw=${dn}`)
      if (!requestIsCurrent(loadSequence, sequence)) return
      setAnalysis(a)
      const [moveResult, payoutResult] = await Promise.allSettled([
        get(`/api/movement?product=${p}&draw=${dn}`),
        get(`/api/payouts?product=${p}&draw=${dn}`),
      ])
      if (!requestIsCurrent(loadSequence, sequence)) return
      setMovement(moveResult.status === 'fulfilled' ? moveResult.value : null)
      const pay = payoutResult.status === 'fulfilled' ? payoutResult.value : null
      // Svarskontraktet bär både produkt och omgång. Ett korrekt men gammalt
      // svar är fortfarande fel data för den synliga kupongen.
      setPayouts(payoutMatchesSelection(pay, p, dn) ? pay : null)
    } catch (e) {
      if (requestIsCurrent(loadSequence, sequence) && !silent) setErr(String(e))
    } finally {
      if (requestIsCurrent(loadSequence, sequence) && !silent) setLoading(false)
    }
  }

  const pickDraws = async (g, restore = false) => {
    // Ogiltigförklara alla svar som hör till den tidigare spelgruppen redan
    // vid klicket, inte först när den nya omgångens analys hunnit svara.
    const selectionSequence = beginRequest(loadSequence)
    setLoading(true); setErr(null); setSys(null); setAnalysis(null)
    setMovement(null); setPayouts(null)
    if (!restore) {
      setPicks({}); setPickRows(null); setCouponVariant(null); setCouponModel(null)
      setCouponValueWeight(null)
    }
    try {
      const d = await get(`/api/draws?product=${g}`)
      if (!requestIsCurrent(loadSequence, selectionSequence)) return
      const raw = d.open?.length ? d.open : d.draws || []
      const list = uniqueDraws(raw).sort((a, b) => {
        const at = a.reg_close_time ? new Date(a.reg_close_time).getTime() : Infinity
        const bt = b.reg_close_time ? new Date(b.reg_close_time).getTime() : Infinity
        return at - bt
      })
      setDraws(list)
      const restored = restore && list.find((x) => x.product === saved.product && x.draw_number === saved.draw)
      const chosen = restored || list[0]
      if (!chosen) { setLoading(false); setErr('Inga öppna omgångar just nu.'); return }
      if (restore && !restored) {
        setPicks({}); setPickRows(null); setCouponVariant(null); setCouponModel(null)
        setCouponValueWeight(null)
      }
      setProduct(chosen.product); setDraw(chosen.draw_number)
      if (g !== 'bomben') await loadAnalysis(chosen.product, chosen.draw_number)
      else setLoading(false)
    } catch (e) {
      if (requestIsCurrent(loadSequence, selectionSequence)) {
        setErr(String(e)); setLoading(false)
      }
    }
  }
  useEffect(() => { pickDraws(game, true) }, [])  // eslint-disable-line

  const switchGame = (g) => { setGame(g); pickDraws(g) }
  const changeDraw = (slug, dn) => {
    beginRequest(loadSequence)
    setProduct(slug); setDraw(dn); setSys(null); setAnalysis(null)
    setMovement(null); setPayouts(null); setPicks({}); setPickRows(null)
    setCouponVariant(null); setCouponModel(null); setCouponValueWeight(null)
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
        rowModel, complementaryMode, couponVariant, couponModel, couponValueWeight,
        pickRows: pickRows && pickRows.length <= 2048 ? pickRows : null,
      }))
    } catch { /* ok */ }
  }, [game, product, draw, picks, pickRows, strategy, budget, sysType, valueWeight,
    rowModel, complementaryMode, couponVariant, couponModel, couponValueWeight])

  const toggleSign = (ev, sign) => {
    setPickRows(null)
    setCouponVariant(null)
    setCouponModel(null)
    setCouponValueWeight(null)
    setPicks((prev) => {
      const cur = prev[ev] || []
      const next = cur.includes(sign) ? cur.filter((s) => s !== sign) : [...cur, sign]
      const copy = { ...prev }
      if (next.length) copy[ev] = next; else delete copy[ev]
      return copy
    })
  }
  const clearCoupon = () => {
    setPicks({}); setPickRows(null); setCouponVariant(null); setCouponModel(null)
    setCouponValueWeight(null)
  }
  const selectSystem = (chosenSystem, variantLabel) => {
    if (!analysis || !chosenSystem?.picks) return
    const p = {}
    chosenSystem.picks.forEach((pk) => { p[pk.event_number] = pk.signs })
    setPickRows(chosenSystem.rows && chosenSystem.rows.length
      ? chosenSystem.rows.map((r) => [...r]) : null)
    setPicks(p)
    setCouponVariant(variantLabel)
    setCouponModel(chosenSystem.row_model || 'standard')
    setCouponValueWeight(chosenSystem.effective_value_weight ?? effectiveValueWeight / 100)
    // scrollIntoView får även flytta sidan horisontellt. När den breda
    // kupongtabellen nyss mountats ser det på mobil ut som att sidan zoomar.
    // Vänta tills layouten satt sig och flytta bara Y-led.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const coupon = document.getElementById('kupong')
      if (!coupon) return
      const top = coupon.getBoundingClientRect().top + window.scrollY - 8
      window.scrollTo({ top, left: 0, behavior: 'smooth' })
    }))
  }

  const nMatches = analysis?.matches?.length || 0
  const systemTypes = nMatches === 13 ? [...SYSTEM_BASE, ...SYSTEM_SVS] : SYSTEM_BASE
  const rowModelAvailable = sysType === 'ev' && ['topptipset', 'stryktipset', 'europatipset']
    .includes(FAMILY(product))
  const availableRowModels = ROW_MODELS.filter((model) => (
    model.id !== 'row_shape_v1' || FAMILY(product) === 'topptipset'))
  const rowModelSupported = availableRowModels.some((model) => model.id === rowModel)
  const activeRowModel = rowModelAvailable && rowModelSupported
    && (rowModel !== 'row_shape_v1' || budget === 384) ? rowModel : 'standard'
  const effectiveValueWeight = activeRowModel === 'hit' ? 0
    : activeRowModel === 'row_shape_v1' ? 50 : valueWeight
  const activeRowModelInfo = ROW_MODELS.find((model) => model.id === activeRowModel)
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
  // Försvar på rendernivå också: även en framtida anropsväg som glömmer
  // sekvensvakten får inte mata fel omgångs pengar till UI eller byggare.
  const currentPayouts = payoutMatchesSelection(payouts, product, draw)
    ? payouts : null

  const loadSystem = async () => {
    const selectionSequence = loadSequence.current
    setErr(null)
    try {
      let q = (systemTypes.find((t) => t.id === sysType) || SYSTEM_BASE[0]).q
      if (q.endsWith('guarantee=')) q += Math.max(1, nMatches - 1)
      const vw = effectiveValueWeight / 100
      const jp = currentPayouts?.jackpot != null
        ? `&jackpot=${encodeURIComponent(currentPayouts.jackpot)}` : ''
      const pair = complementaryMode && sysType === 'ev'
        && activeRowModel !== 'row_shape_v1' ? '&complementary=true' : ''
      const built = await getDetail(
        `/api/system?product=${product}&draw=${draw}&strategy=${encodeURIComponent(strategy)}&budget=${budget}&value_weight=${vw}&row_model=${activeRowModel}&${q}${jp}${pair}`,
        'System')
      if (requestIsCurrent(loadSequence, selectionSequence)) setSys(built)
    } catch (e) {
      if (requestIsCurrent(loadSequence, selectionSequence)) setErr(String(e))
    }
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
                stänger {fmtClose(d.reg_close_time)}
                {d.state !== 'Open' ? ` (${d.state})` : ''} · omg {d.draw_number}
              </option>
            ))}
          </select>
        )}
        {analysis && game !== 'bomben' && (
          <span className="v3poolkpi">
            oms <b>{analysis.turnover ? kr(analysis.turnover) : '–'}</b>
            {currentPayouts?.available && <> · spelvärde <b className={((currentPayouts.spelvarde_proj ?? currentPayouts.spelvarde) || 0) >= 1 ? 'pos' : ''}>
              {Math.round(((currentPayouts.spelvarde_proj ?? currentPayouts.spelvarde) || 0) * 100)}%</b></>}
            {currentPayouts?.jackpot > 0 && <> · 💰 {kr(currentPayouts.jackpot)}</>}
            {currentPayouts?.available && <PlayRec payouts={currentPayouts} product={product} />}
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
          <BombenView key={`${draw}:${bombenNonce}`} draw={draw} nonce={bombenNonce} />
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
                      onChange={() => {
                        setStrategy(s)
                        if (activeRowModel === 'standard') setValueWeight(STRATEGY_EV[s])
                        setSys(null)
                      }} />{s}
                  </label>
                ))}
                <label className="budget">
                  Max budget <b>{budget} kr</b>
                  <input type="range" min="0" max={BUDGET_STOPS.length - 1} step="1" value={budgetIdx}
                    onChange={(e) => {
                      const nextBudget = BUDGET_STOPS[Number(e.target.value)]
                      setBudget(nextBudget)
                      if (rowModel === 'row_shape_v1' && nextBudget !== 384) {
                        setRowModel('standard')
                      }
                      setSys(null)
                    }} />
                </label>
                <select value={sysType} onChange={(e) => {
                  const next = e.target.value
                  setSysType(next)
                  if (next !== 'ev') setComplementaryMode(false)
                  setSys(null)
                }}>
                  {systemTypes.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                </select>
                <label className={`complementary-toggle ${complementaryMode ? 'active' : ''}`}
                  title="Bygger två lika stora kuponger tillsammans. De får skilda ankare, högst 10 % identiska rader och tonar ned varandras ankartecken. Varje kupong kostar hela den valda insatsen.">
                  <input type="checkbox" checked={complementaryMode}
                    disabled={sysType !== 'ev' || activeRowModel === 'row_shape_v1'}
                    onChange={(e) => { setComplementaryMode(e.target.checked); setSys(null) }} />
                  Två kompletterande kuponger
                </label>
                <button className="primary" onClick={loadSystem}>
                  {complementaryMode && sysType === 'ev' ? 'Föreslå två kuponger' : 'Föreslå rad'}
                </button>
              </div>
              {rowModelAvailable && (
                <fieldset className="rowprofiles">
                  <legend>Radprofil</legend>
                  <div className="rowprofile-options">
                    {availableRowModels.map((model) => {
                      const disabled = model.id === 'row_shape_v1' && budget !== 384
                      return (
                      <label key={model.id}
                        className={activeRowModel === model.id ? 'active' : ''}>
                        <input type="radio" name="row-model" value={model.id}
                          checked={activeRowModel === model.id} disabled={disabled}
                          onChange={() => {
                            setRowModel(model.id)
                            if (model.id === 'hit') setValueWeight(0)
                            if (model.id === 'row_shape_v1' || model.id === 'standard') {
                              setValueWeight(50)
                            }
                            if (model.id === 'row_shape_v1') setComplementaryMode(false)
                            setSys(null)
                          }} />
                        <span>{model.label}{disabled ? ' · kräver 384 kr' : ''}</span>
                      </label>
                      )
                    })}
                  </div>
                  <p>{activeRowModelInfo?.note}</p>
                </fieldset>
              )}
              <div className="evscale">
                <span>Träffbart</span>
                <input type="range" min="0" max="100" step="5"
                  value={effectiveValueWeight} disabled={activeRowModel !== 'standard'}
                  onChange={(e) => { setValueWeight(Number(e.target.value)); setSys(null) }} />
                <span>Max EV</span>
                <span className="evval">{effectiveValueWeight}%</span>
              </div>
              {sys?.complementary?.available && sys.complementary.system && (
                <>
                  <ComplementaryChooser primary={sys} meta={sys.complementary}
                    onUsePrimary={() => selectSystem(sys, 'Kupong A')}
                    onUseAlternative={() => selectSystem(sys.complementary.system, 'Kupong B')} />
                  <details className="complementary-details">
                    <summary><b>Fördjupning kupong A</b><span>simulering och teckenfördelning</span></summary>
                    <SystemView key={`${product}:${draw}:a`} sys={sys}
                      matches={analysis?.matches} payouts={currentPayouts}
                      onRecalc={loadSystem} label="Kupong A"
                      actionLabel="⬇ Lägg A i kupongen"
                      onUse={() => selectSystem(sys, 'Kupong A')} />
                  </details>
                  <details className="complementary-details">
                    <summary><b>Fördjupning kupong B</b><span>simulering och teckenfördelning</span></summary>
                    <SystemView key={`${product}:${draw}:b`} sys={sys.complementary.system}
                      matches={analysis?.matches} payouts={currentPayouts}
                      label="Kupong B" actionLabel="⬇ Lägg B i kupongen"
                      showHonesty={false}
                      onUse={() => selectSystem(sys.complementary.system, 'Kupong B')} />
                  </details>
                </>
              )}
              {sys?.complementary && !sys.complementary.available && (
                <>
                  <SystemView key={`${product}:${draw}:a`} sys={sys}
                    matches={analysis?.matches} payouts={currentPayouts}
                    onRecalc={loadSystem} label="Singelförslag"
                    onUse={() => selectSystem(sys, 'Förslag')} />
                  <div className="complementary-warning">
                    <b>Två tillräckligt olika kuponger kunde inte skapas.</b>
                    <span>{sys.complementary.reason}</span>
                  </div>
                </>
              )}
              {sys && !sys.complementary && (
                <SystemView key={`${product}:${draw}:single`} sys={sys}
                  matches={analysis?.matches} payouts={currentPayouts}
                  onRecalc={loadSystem}
                  onUse={() => selectSystem(sys, 'Förslag')} />
              )}
            </section>

            <section id="kupong">
              <h2>Din kupong{couponVariant ? ` · ${couponVariant}` : ''}
                {couponModel && couponModel !== 'standard'
                  ? ` · ${ROW_MODEL_LABEL[couponModel] || couponModel}` : ''}
                {' '}— granska &amp; lämna in</h2>
              {/* Byggarens inställningar följer med till bokföringen. Utan dem
                  gick det inte att i efterhand se VILKET slags förslag en
                  spelad kupong byggde på — alla rader före 2026-08-05 har
                  därför okänd förslagstyp, och de bakfylls aldrig. */}
              <CouponPanel key={`${product}:${draw}`} matches={analysis.matches}
                picks={picks} pickRows={pickRows}
                payouts={currentPayouts} product={product} draw={draw} onClear={clearCoupon}
                buildConfig={{ strategy, budget,
                  value_weight: couponValueWeight ?? valueWeight / 100,
                  source: couponVariant === 'Kupong A' ? 'byggare-komplement-a'
                    : couponVariant === 'Kupong B' ? 'byggare-komplement-b'
                      : couponVariant === 'Förslag' && couponModel === 'row_shape_v1'
                        ? 'byggare-radform-v1'
                        : couponVariant === 'Förslag' && couponModel === 'hit'
                          ? 'byggare-traffsakrare'
                          : couponVariant === 'Förslag' ? 'byggare' : 'manuell',
                  label: [couponVariant, couponModel && couponModel !== 'standard'
                    ? ROW_MODEL_LABEL[couponModel] : null].filter(Boolean).join(' · ') }} />
            </section>
          </div>

          <details className="v3extras">
            <summary>Sharp-odds, steam &amp; signal-facit</summary>
            <div className="v3cols">
              <section>
                <h2>Sharp-odds &amp; steam</h2>
                <SharpPanel key={`${product}:${draw}`} product={product} draw={draw}
                  onLoaded={() => loadAnalysis()} />
                <SteamPanel key={`${product}:${draw}`} product={product} draw={draw}
                  matches={analysis?.matches} />
              </section>
              <section>
                <h2>Signal-facit (CLV)</h2>
                <ClvPanel key={game} group={game} />
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

const STRATEGY_LABEL = {
  säker: 'Säker', medel: 'Medel', tuff: 'Tuff',
  byggarslump: 'Slump · samma urval', favoritrad: 'Favoritrader',
  folkrad: 'Folkrader',
  // `maxev` är samma byggare som medel med balansknappen i botten
  // (värdevikt 1,0 ⇒ k = 0, ren EV utan träffchansdämpning). Etiketten
  // säger vad knappen GÖR, eftersom "maxev" annars läses som en egen metod.
  maxev: 'Ren EV · utan dämpning',
}

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
  const [rowPage, setRowPage] = useState(0)
  const [rowNumber, setRowNumber] = useState('')
  useEffect(() => {
    let current = true
    get(`/api/pool/systems/detail?product=${product}&draw=${draw}`
      + `&horizon=${horizon}&config=${encodeURIComponent(config)}`)
      .then((value) => { if (current) setD(value) })
      .catch((e) => { if (current) setErr(String(e)) })
    return () => { current = false }
  }, [product, draw, horizon, config])
  const move = (e, sign) => {
    const a = e.streck_at_freeze?.[sign], b = e.streck_at_close?.[sign]
    if (a == null || b == null || a === b) return null
    const diff = b - a
    return <span className={diff > 0 ? 'v3neg' : 'v3pos'}> ({diff > 0 ? '+' : ''}{diff})</span>
  }
  const pageSize = 100
  const rows = d?.rows || []
  const searchedRow = rowNumber === '' ? null
    : rows.find((row) => row.index === Number(rowNumber))
  const shownRows = rowNumber === ''
    ? rows.slice(rowPage * pageSize, (rowPage + 1) * pageSize)
    : searchedRow ? [searchedRow] : []
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const distribution = Object.entries(d?.correct_dist || {})
    .map(([correct, count]) => [Number(correct), Number(count)])
    .sort((a, b) => b[0] - a[0])
  const signWeights = (event) => ['1', 'X', '2'].map((sign) => {
    const share = event.sign_shares?.[sign]
    return `${sign} ${share == null ? '–' : `${Math.round(share * 100)} %`}`
  }).join(' · ')
  const oddsLine = (event, key) => ['1', 'X', '2'].map((sign) => {
    const odds = event[key]?.[sign]
    return `${sign} ${odds == null ? '–' : Number(odds).toFixed(2)}`
  }).join(' · ')
  const marketTime = (iso) => {
    if (!iso) return null
    const parsed = new Date(iso)
    return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString('sv-SE', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  }
  return (
    <div className="v3sysdetail" id="hist-system-detail">
      <div className="v3sysdetailhead">
        <b>{PRODUCT_LABEL[product] || product} · omgång {draw} · {d
          ? `${d.research ? '🧪 PH5-test · ' : ''}${d.research
            ? PH5_METHOD_LABEL[d.method] || d.method
            : STRATEGY_LABEL[d.strategy] || d.strategy || 'testsystem'}`
          : 'testsystem'}</b>
        <button className="v3more" onClick={onClose}>stäng ✕</button>
      </div>
      {err && <ErrorState message={err} />}
      {!d && !err && <LoadingState label="Hämtar systemet…" />}
      {d && !d.available && <EmptyState title="Systemet finns inte i ledgern" />}
      {d?.available && (
        <>
          <div className="v3sysdetailmeta">
            <span>{d.n_rows.toLocaleString('sv-SE')} rader · {kr(d.cost_kr)}</span>
            <span>fryst {horizonLabel(d)} före stopp{d.timely ? '' : ' (sen)'}</span>
            <span>bäst <b>{d.correct_max ?? '–'}</b> rätt</span>
            {d.n_missed > 0 && (
              <span className="v3neg" title="Matcher där inget av systemets tecken
                gick in. Varje sådan match sänker takresultatet med ett rätt.">
                missade {d.n_missed} {d.n_missed === 1 ? 'match' : 'matcher'}</span>
            )}
            <span className={roiCls(d.roi)}>{d.correct_max == null
              ? 'väntar facit'
              : d.payout_complete === false ? 'utdelning okänd'
                : `${kr(d.payout_kr)} · ${pctSigned(d.roi)}`}</span>
          </div>
          {d.x_summary && (
            <div className="v3xsummary">
              <b>X-kontroll</b>
              <span>Kryss utgör {d.x_summary.row_share == null ? '–'
                : `${Math.round(d.x_summary.row_share * 100)} %`} av alla tecken
                i systemets {d.n_rows.toLocaleString('sv-SE')} rader.</span>
              <span>{d.x_summary.omitted} matcher saknar X helt
                {d.x_summary.thin ? ` · ${d.x_summary.thin} har under 10 % X` : ''}.</span>
              {d.facit_complete && <span className={d.x_summary.x_outcomes_omitted
                ? 'v3neg' : 'v3hint'}>{d.x_summary.x_outcomes} matcher slutade X
                {' '}· {d.x_summary.x_outcomes_omitted} av dem saknades helt.</span>}
            </div>
          )}
          <div className="v3histtablewrap">
            <table className="v3histtable v3sysfacit">
              <thead><tr>
                <th>#</th><th>Match</th><th>Facit</th><th>Teckenvikt</th>
                <th title="Pinnacles/sharp odds, senast observerade före frysningen.">Sharpodds vid frysning</th>
                <th title="Svenska Spels odds och folkets streck när systemet frystes.">SvS odds · streck</th>
                <th title="Folkets procent när systemet frystes, och förändringen
                  fram till spelstopp.">Streck vid frysning → stopp</th>
              </tr></thead>
              <tbody>
                {d.events.map((e) => (
                  <tr key={e.event_number}
                    className={e.hit === false ? 'v3sysmiss' : ''}>
                    <td>{e.event_number}</td>
                    <td>{e.home && e.away ? `${e.home} – ${e.away}`
                      : e.description || `Match ${e.event_number}`}
                      {e.market_observed_at && <span className="v3markettime">
                        prisbild mätt {marketTime(e.market_observed_at)}</span>}
                    </td>
                    <td className="v3outcome">
                      {e.cancelled ? '⚠️' : e.outcome || '–'}</td>
                    <td className={e.x_omitted ? 'v3xmissing' : ''}>
                      {signWeights(e)}{e.hit === false
                      ? <span className="v3neg" title="Systemet spelade inte det
                        tecken som gick in — inget av raderna kunde bli rätt här."> ✗</span>
                      : e.hit ? ' ✓' : ''}
                      {e.x_omitted && <span className="v3xflag"> X saknas</span>}
                    </td>
                    <td className="v3oddsline">{oddsLine(e, 'sharp_odds_at_freeze')}</td>
                    <td className="v3oddsline">
                      {['1', 'X', '2'].map((s) => (
                        <span key={s}>{s} {e.odds_at_freeze?.[s] == null ? '–'
                          : Number(e.odds_at_freeze[s]).toFixed(2)} ·{' '}
                          {e.streck_at_freeze?.[s] ?? '–'} % </span>
                      ))}
                    </td>
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
          <span className="v3hint">Teckenvikt visar hur stor del av de 5 000
            raderna som använder 1, X respektive 2 — betydligt mer informativt
            än att ett tecken råkar finnas på minst en rad. Ett ✗ betyder att
            facittecknet saknades helt. Oddsen och strecken är sista sparade
            observationen före frysningen; de läses aldrig in i efterhand.</span>
          {rows.length > 0 && (
            <section className="v3systemrows" aria-label="Testsystemets exakta rader">
              <div className="v3systemrowshead">
                <div>
                  <h4>Exakta rader mot facit</h4>
                  <span className="v3hint">Det här testet består av {rows.length.toLocaleString('sv-SE')}
                    {' '}separata rader, inte en enda rad. {d.facit_complete
                      ? 'De är sorterade med bäst resultat först.'
                      : 'Facit saknas ännu, så den frysta originalordningen visas.'}
                    {' '}# är platsen i den sparade testfilen.</span>
                </div>
                <label className="v3rowfind">
                  <span>Hitta radnummer</span>
                  <input type="number" min="1" max={rows.length}
                    value={rowNumber} placeholder={`1–${rows.length}`}
                    onChange={(event) => setRowNumber(event.target.value)} />
                </label>
              </div>
              {d.facit_complete
                ? <div className="v3systemfacitline">
                    <b>Facit</b>
                    {(d.facit || '').split('').map((sign, index) => (
                      <span key={index}>{sign}</span>
                    ))}
                  </div>
                : <div className="v3note"><b>Facit väntar.</b> Kupongen är ändå
                    redan fryst och kan granskas exakt som den såg ut före
                    spelstopp.</div>}
              <div className="v3systemdist">
                {distribution.map(([correct, count]) => (
                  <span key={correct}>{count.toLocaleString('sv-SE')} {count === 1 ? 'rad' : 'rader'}
                    {' '}med <b>{correct} rätt</b></span>
                ))}
              </div>
              {d.audit_matches_stored === false && (
                <div className="v3note v3neg"><b>Kontrollvarning:</b> de omräknade
                  raderna stämmer inte med den sparade summeringen.</div>
              )}
              <div className="v3systemrowlist">
                {shownRows.map((row) => (
                  <div className="v3systemrow" key={row.index}>
                    <span className="v3systemrowindex">#{row.index}</span>
                    <div className="v3systemsigns" aria-label={`Rad ${row.index}: ${row.signs}`}
                      style={{ gridTemplateColumns: `repeat(${d.events.length}, minmax(19px, 1fr))` }}>
                      {row.signs.split('').map((sign, index) => (
                        <span key={index}
                          className={!d.facit_complete ? ''
                            : d.facit?.[index] === sign ? 'hit' : 'miss'}>{sign}</span>
                      ))}
                    </div>
                    <b>{row.correct == null ? 'väntar' : `${row.correct}/${d.events.length}`}</b>
                    {row.payout_kr == null ? null : row.payout_kr > 0
                      ? <span className="v3pos">+{kr(row.payout_kr)}</span>
                      : <span className="v3hint">0 kr</span>}
                  </div>
                ))}
                {rowNumber !== '' && !searchedRow && (
                  <EmptyState title={`Rad #${rowNumber} finns inte`}
                    detail={`Ange ett nummer mellan 1 och ${rows.length}.`} />
                )}
              </div>
              {rowNumber === '' && pageCount > 1 && (
                <div className="v3rowpager">
                  <button disabled={rowPage === 0}
                    onClick={() => setRowPage((page) => Math.max(0, page - 1))}>← Föregående</button>
                  <span>Rader {rowPage * pageSize + 1}–{Math.min((rowPage + 1) * pageSize, rows.length)}
                    {' '}av {rows.length.toLocaleString('sv-SE')}</span>
                  <button disabled={rowPage >= pageCount - 1}
                    onClick={() => setRowPage((page) => Math.min(pageCount - 1, page + 1))}>Nästa →</button>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}

const PH5_METHOD_LABEL = {
  varderader: 'Värderader',
  byggarslump: 'Byggarslump',
  favoritrad: 'Favoritrad',
  maxev: 'Max-EV',
  folkrad: 'Folkrad (avslutad)',
}

/* PH5 har en egen uppgift och ska därför inte ligga gömt bland Historiks
   hundratals benchmarkgrupper. En rad här är EN exakt fryst 5 000-raders-
   kupong. Själva raderna hämtas först när användaren öppnar testet. */
function Ph5V3() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [openSystem, setOpenSystem] = useState(null)
  const [filters, setFilters] = useState({ product: 'alla', horizon: 'alla', method: 'alla' })
  useEffect(() => {
    let current = true
    get('/api/pool/ph5')
      .then((value) => { if (current) setData(value) })
      .catch((reason) => { if (current) setError(String(reason)) })
    return () => { current = false }
  }, [])
  useEffect(() => {
    if (!openSystem) return undefined
    const frame = window.requestAnimationFrame(() => {
      document.getElementById('hist-system-detail')?.scrollIntoView({
        behavior: 'smooth', block: 'start',
      })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [openSystem])
  if (error) return <ErrorState message={error} />
  if (!data) return <LoadingState label="Hämtar 5 000-kronorstestet…" />

  const tests = (data.tests || []).filter((test) => (
    (filters.product === 'alla' || test.product === filters.product)
    && (filters.horizon === 'alla' || test.horizon === filters.horizon)
    && (filters.method === 'alla' || test.method === filters.method)
  ))
  const summary = data.summary || {}
  const setFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }))
  const methods = [...new Set((data.tests || []).map((test) => test.method))]
  const retiredCount = (data.tests || []).filter((test) => test.retired).length

  return (
    <div className="v3ph5">
      <section className="v3hero v3ph5hero">
        <div>
          <span className="v3eyebrow">FRAMÅTRIKTAT BLINDTEST · INGA RIKTIGA INSATSER</span>
          <h1>5 000-kronorstestet</h1>
          <p>Här går varje automatisk testkupong att öppna exakt som den frystes
            före spelstopp — samtliga 5 000 rader, odds, streck, teckenvikt och
            slutligt facit på samma ställe.</p>
        </div>
      </section>

      <div className="v3ph5kpis">
        <div><span>Omgångar</span><b>{summary.draws || 0}</b></div>
        <div><span>Aktiva testkuponger</span><b>{summary.freezes || 0}</b></div>
        <div><span>Facitklara aktiva</span><b>{summary.evaluated || 0}</b></div>
        <div><span>Aktiva metoder</span><b>{summary.methods || 0}</b></div>
      </div>

      <div className="v3card v3ph5explain">
        <div className="v3cardhead"><h3>Så ska testet läsas</h3></div>
        <p>Fyra olika metoder får samma budget och fryses både tre timmar och
          tjugo minuter före stopp. Det gör jämförelsen rättvis. Resultatet är
          kontrafaktiskt: systemet lämnades aldrig in, så kronor och ROI visar
          vad testet uppskattas ha gett — inte pengar som vunnits eller förlorats.</p>
        <div className="v3ph5methods">
          <span><b>Värderader</b> appens balanserade modell</span>
          <span><b>Max-EV</b> prioriterar värde hårdast</span>
          <span><b>Favoritrad</b> marknadens sannolikaste tecken</span>
          <span><b>Byggarslump</b> slumpkontroll ur samma kandidater</span>
        </div>
      </div>

      <div className="v3card v3ph5xnote">
        <div className="v3cardhead"><h3>Är X systematiskt underviktat?</h3></div>
        <p>Det är en rimlig misstanke, särskilt när ett binärt 1–2-hörn väljs.
          Vi ändrar inte den pågående PH5-v3-kohorten i efterhand. I stället
          mäter sidan nu X-andelen i varje kupong och markerar varje match där
          X saknas helt eller får mindre än 10 procent av raderna.</p>
        <p><b>Appens Värderader hittills:</b> X har saknats i{' '}
          {summary.model_x_omitted_events || 0} frysta matchbeslut. Av{' '}
          {summary.model_x_outcomes || 0} observerade X-facit saknades X helt i{' '}
          <span className={summary.model_x_outcomes_omitted ? 'v3neg' : 'v3pos'}>
            {summary.model_x_outcomes_omitted || 0}</span>. Samma match kan
          räknas vid både tre timmar och tjugo minuter; detta är diagnostik,
          ännu inget statistiskt modellbeslut. Kontrollerna visas separat i
          tabellen och blandas inte in i den här siffran.</p>
      </div>

      <div className="v3card">
        <div className="v3cardhead"><h3>Alla frysta 5 000-kuponger</h3>
          <span className="v3hint">{tests.length} av {(data.tests || []).length}
            {retiredCount ? ` · ${retiredCount} avslutade` : ''}</span></div>
        <div className="v3groupfilters" aria-label="Filtrera 5 000-tester">
          <label><span>Spel</span><select value={filters.product}
            onChange={(event) => setFilter('product', event.target.value)}>
            <option value="alla">Alla spel</option>
            {(data.products || []).map((product) => <option key={product} value={product}>
              {PRODUCT_LABEL[product] || product}</option>)}
          </select></label>
          <label><span>Fryst</span><select value={filters.horizon}
            onChange={(event) => setFilter('horizon', event.target.value)}>
            <option value="alla">Båda tiderna</option>
            <option value="h3">3 timmar före</option>
            <option value="m20">20 minuter före</option>
          </select></label>
          <label><span>Metod</span><select value={filters.method}
            onChange={(event) => setFilter('method', event.target.value)}>
            <option value="alla">Alla metoder</option>
            {methods.map((method) => <option key={method} value={method}>
              {PH5_METHOD_LABEL[method] || method}</option>)}
          </select></label>
        </div>

        {openSystem && <SystemDetail
          key={`${openSystem.product}:${openSystem.draw_number}:${openSystem.horizon}:${openSystem.config_key}`}
          product={openSystem.product} draw={openSystem.draw_number}
          horizon={openSystem.horizon} config={openSystem.config_key}
          onClose={() => setOpenSystem(null)} />}

        {!tests.length
          ? <EmptyState title="Inga tester matchar filtren" />
          : <div className="v3histtablewrap"><table className="v3histtable v3ph5table">
              <thead><tr><th>Datum</th><th>Spel</th><th>Omgång</th><th>Fryst</th>
                <th>Metod</th><th>Facit</th><th>X-vikt</th><th>Kupong</th></tr></thead>
              <tbody>{tests.map((test) => (
                <tr key={`${test.product}:${test.draw_number}:${test.horizon}:${test.config_key}`}
                  className={test.retired ? 'v3retired' : ''}>
                  <td>{test.close ? fmtDay(test.close) : fmtDay(test.frozen_at)}</td>
                  <td>{PRODUCT_LABEL[test.product] || test.product}</td>
                  <td>#{test.draw_number}</td>
                  <td>{horizonLabel(test)}{test.timely ? '' : ' · sen'}</td>
                  <td>{PH5_METHOD_LABEL[test.method] || test.method}</td>
                  <td>{test.correct_max == null ? 'Väntar facit'
                    : test.payout_complete === false
                      ? `${test.correct_max} rätt · utdelning okänd`
                      : <><b>{test.correct_max} rätt</b> · {kr(test.payout_kr)} ·{' '}
                          <span className={roiCls(test.roi)}>{pctSigned(test.roi)}</span></>}</td>
                  <td className={test.x_outcomes_omitted ? 'v3neg' : ''}>
                    {test.x_share == null ? '–' : `${Math.round(test.x_share * 100)} %`}
                    {test.x_omitted_events ? ` · saknas i ${test.x_omitted_events}` : ''}</td>
                  <td><button className="v3more" onClick={() => setOpenSystem(test)}>
                    Visa exakt kupong</button></td>
                </tr>
              ))}</tbody>
            </table></div>}
      </div>

    </div>
  )
}

/* En grupp är en simulerad konfiguration över flera omgångar, inte en spelad
   kupong. Håll därför kostnad/utdelning explicit kontrafaktiska i både rubrik
   och tooltip; annars läser den ackumulerade ROI-nämnaren som verkliga pengar. */
function SystemGroupsTable({ id, groups, limit = null, onOpenLatest = null }) {
  return (
    <SortableTable id={id} className="v3histtable"
      wrapperClassName="v3histtablewrap"
      defaultSort={{ key: 'latest_frozen', dir: 'desc' }}
      rows={groups} limit={limit}
      columns={[
        { key: 'product', label: 'Spel', defaultDir: 'asc',
          value: (g) => PRODUCT_LABEL[g.product] || g.product },
        { key: 'budget', label: 'Kostnad/test',
          title: 'Systemets kostnad i en enskild testomgång. Radpriset är 1 kr, så beloppet är också antalet rader.' },
        { key: 'strategy', label: 'Strategi', defaultDir: 'asc',
          value: (g) => STRATEGY_LABEL[g.strategy] || g.strategy || '' },
        { key: 'value_weight', label: 'Värdevikt' },
        { key: 'horizon_minutes', label: 'Fryst',
          title: 'Minuter före spelstopp' },
        { key: 'latest_frozen', label: 'Senast testad', defaultDir: 'desc',
          title: 'Datum för senaste omgång där konfigurationen sparades automatiskt',
          // Sortera kalenderdag, inte klockslaget för h3/m20. Då hålls
          // samma dags produkter ihop i backendens produktordning.
          value: (g) => g.latest_frozen?.slice(0, 10) || null },
        { key: 'n_frozen', label: 'Sparade tester',
          title: 'Antal automatiskt frysta förslag för gruppen.' },
        { key: 'n_evaluable', label: 'ROI-underlag',
          title: 'Frysta i tid, med känt resultat OCH känd utdelning — de enda ROI räknas på.' },
        { key: 'cost_kr', label: 'Sammanlagt',
          title: 'Antal tester med facit × kostnad per test. Inga pengar har spelats.' },
        { key: 'payout_kr', label: 'Simulerad utdelning',
          title: 'Kontrafaktiskt uppskattad utdelning. Detta är inte mottagna pengar.' },
        { key: 'roi', label: 'Simulerad ROI' },
        { key: 'best_correct', label: 'Bäst' },
        { key: 'open_latest', label: 'Rader', value: () => '' },
      ]}
      renderRow={(g) => {
        const perTest = g.cost_per_draw_kr ?? g.budget
        return (
          <tr key={`${g.product}-${g.config_key}-${g.horizon}`}
            className={g.retired ? 'v3retired' : ''}>
            <td>{g.research
              ? <span title="Research-only: påverkar inte ordinarie system eller promotion">🧪 </span>
              : null}{PRODUCT_LABEL[g.product] || g.product}</td>
            <td>{g.primary ? '★ ' : ''}{perTest != null ? kr(perTest) : '–'}</td>
            <td>{STRATEGY_LABEL[g.strategy] || g.strategy || '–'}</td>
            <td>{g.value_weight != null ? `${Math.round(g.value_weight * 100)} %` : '–'}</td>
            <td>{horizonLabel(g)}</td>
            <td>{g.latest_frozen ? fmtDay(g.latest_frozen) : '–'}</td>
            <td>{g.n_frozen}{g.n_timely < g.n_frozen
              ? <span className="v3hint"> ({g.n_frozen - g.n_timely} sena)</span> : ''}
              {g.n_cancelled
                ? <span className="v3hint"> ({g.n_cancelled} inställda)</span> : ''}</td>
            <td>{g.n_evaluable
              ? `${g.n_evaluable} ${g.n_evaluable === 1 ? 'test' : 'tester'}` : '–'}
              {g.n_payout_incomplete
                ? <span className="v3hint"> ({g.n_payout_incomplete} okänd utd.)</span> : ''}</td>
            <td className="v3costformula">{g.n_evaluable
              ? <>{g.n_evaluable} × {kr(perTest)} = <b>{kr(g.cost_kr)}</b></>
              : '–'}</td>
            <td>{g.n_evaluable ? kr(g.payout_kr) : '–'}</td>
            <td className={roiCls(g.roi)}>{pctSigned(g.roi)}</td>
            <td>{g.best_correct ?? '–'}</td>
            <td>{g.latest_draw_number != null && onOpenLatest
              ? <button className="v3more" onClick={() => onOpenLatest(g)}>
                  Visa senaste testet</button>
              : '–'}</td>
          </tr>
        )
      }}
      renderCard={(g) => {
        const perTest = g.cost_per_draw_kr ?? g.budget
        return (
          <article key={`${g.product}-${g.config_key}-${g.horizon}`}
            className={`v3groupcard${g.retired ? ' v3retired' : ''}`}>
            <div className="v3groupcardhead">
              <b>{g.research
                ? <span title="Research-only: påverkar inte ordinarie system eller promotion">🧪 </span>
                : null}{PRODUCT_LABEL[g.product] || g.product}</b>
              <strong className={roiCls(g.roi)}>{pctSigned(g.roi)}</strong>
            </div>
            <div className="v3groupcardmeta">
              <span>{g.primary ? '★ ' : ''}{kr(perTest)}/test</span>
              <span>{STRATEGY_LABEL[g.strategy] || g.strategy || '–'}</span>
              <span>värde {g.value_weight != null
                ? `${Math.round(g.value_weight * 100)} %` : '–'}</span>
              <span>fryst {horizonLabel(g)}</span>
            </div>
            <div className="v3groupcardformula">
              {g.n_evaluable
                ? <>{g.n_evaluable} {g.n_evaluable === 1 ? 'test' : 'tester'} × {kr(perTest)} = <b>{kr(g.cost_kr)}</b></>
                : 'Inga tester med komplett facit ännu'}
            </div>
            <div className="v3groupcardfoot">
              <span>{g.n_frozen} {g.n_frozen === 1 ? 'sparat test' : 'sparade tester'}</span>
              {g.n_cancelled ? <span>{g.n_cancelled} inställda</span> : null}
              <span>sim. utdelning {g.n_evaluable ? kr(g.payout_kr) : '–'}</span>
              <span>senast {g.latest_frozen ? fmtDay(g.latest_frozen) : '–'}</span>
              <span>bäst {g.best_correct ?? '–'} rätt</span>
            </div>
            {g.latest_draw_number != null && onOpenLatest && (
              <button className="v3more v3groupopen" onClick={() => onOpenLatest(g)}>
                Visa senaste testets rader och facit</button>
            )}
          </article>
        )
      }} />
  )
}

function HistorikV3({ initialProduct, focus }) {
  const [product, setProduct] = useState(initialProduct || 'alla')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [detail, setDetail] = useState({})
  const [systems, setSystems] = useState(null)
  const [strength, setStrength] = useState(null)
  const [halsa, setHalsa] = useState(null)
  const [overview, setOverview] = useState(null)
  const [openSystem, setOpenSystem] = useState(null)
  const [showAllDraws, setShowAllDraws] = useState(false)
  const [showAllFreezes, setShowAllFreezes] = useState(false)
  // Rubriken lovar alla konfigurationer. Visa därför hela urvalet från start;
  // användaren kan aktivt komprimera det till topplistan.
  const [showAllGroups, setShowAllGroups] = useState(true)
  // Pensionerade grupper är jämförelsehistorik, men får inte blandas visuellt
  // med den aktiva testmatrisen eller blåsa upp dess gruppantal.
  const [showRetired, setShowRetired] = useState(false)
  const [groupFilter, setGroupFilter] = useState({
    product: 'alla', budget: 'alla', strategy: 'alla', horizon: 'alla',
  })

  // ETT filter styr hela sidan. `alla` visar tvärsnittet; en produkt filtrerar
  // kuponger, systemfacit OCH omsättning samtidigt.
  const single = product !== 'alla'
  const chooseProduct = (next) => {
    setProduct(next); setData(null); setErr(null); setExpanded(null)
    setOpenSystem(null); setStrength(null)
    setGroupFilter((current) => ({ ...current, product: 'alla' }))
  }

  useEffect(() => {
    if (!single) return undefined
    let current = true
    get(`/api/pool/history?product=${product}&limit=400${IS_FAMILY(product) ? '&family=1' : ''}`)
      .then((value) => { if (current) setData(value) })
      .catch((e) => { if (current) setErr(String(e)) })
    return () => { current = false }
  }, [product, single])
  useEffect(() => {
    get('/api/pool/systems').then(setSystems).catch(() => setSystems(null))
    get('/api/pool/turnover-prognos').then(setHalsa).catch(() => setHalsa(null))
  }, [])
  useEffect(() => {
    let current = true
    const query = single
      ? `?product=${product}${IS_FAMILY(product) ? '&family=1' : ''}` : ''
    get(`/api/pool/strength-shadow${query}`)
      .then((value) => { if (current) setStrength(value) })
      .catch(() => { if (current) setStrength(null) })
    return () => { current = false }
  }, [product, single])
  useEffect(() => {
    Promise.all(HIST_FAMILIES.map((p) =>
      get(`/api/pool/history?product=${p.id}&limit=1${IS_FAMILY(p.id) ? '&family=1' : ''}`)
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

  // Raden lämnar sin EGEN produkt: i familjeläget kommer omgångarna från tre
  // slugs, och `product` är då familjenyckeln — den hittar inte Extra 1856.
  const toggle = (n, rowProduct) => {
    const key = `${rowProduct || product}:${n}`
    const next = expanded === key ? null : key
    setExpanded(next)
    if (next != null && !detail[key]) {
      get(`/api/pool/history?product=${rowProduct || product}&draw=${n}`)
        .then((j) => setDetail((d) => ({ ...d, [key]: j })))
        .catch(() => { /* raden visar ändå nivåerna */ })
    }
  }

  const showSystemDetail = (row) => {
    setOpenSystem(row)
    // Detaljen ligger efter grupptabellen. Flytta användaren dit även när
    // testet öppnas från en grupp högt upp på sidan.
    setTimeout(() => document.getElementById('hist-system-detail')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }
  const showLatestGroupTest = (group) => showSystemDetail({
    product: group.latest_product || group.product,
    draw_number: group.latest_draw_number,
    horizon: group.horizon,
    config_key: group.config_key,
  })

  const draws = data?.draws || []
  const shownDraws = showAllDraws ? draws : draws.slice(0, 20)
  const sparkVals = [...draws].reverse().map((d) => d.turnover)
  // Filtret jämför på FAMILJ: väljs Topptipset ska alla tre slugs med, både i
  // systemfacit och i omsättningen. Andra spel har sig själva som familj.
  const inScope = (row) => !single || FAMILY(row.product) === FAMILY(product)

  /* Topptipsets tre slugs kör SAMMA benchmarkfamilj — `benchmarks_for(product)`
     ger identiska konfigurationer för alla tre — så två rader som skiljer sig
     bara i produkt är samma konfiguration mätt på fler omgångar. De slås ihop.

     Pengar SUMMERAS och ROI räknas om ur summorna, aldrig som medel av
     gruppernas ROI: en grupp med två omgångar skulle annars väga lika tungt
     som en med tjugo. Championrapporten slås INTE ihop — där är varje rad ett
     förregistrerat test, se noten i kortet. */
  const mergeFamily = (groups) => {
    const out = new Map()
    const antal = new Map()
    for (const g of groups) {
      const key = `${FAMILY(g.product)}|${g.config_key}|${g.horizon}`
      antal.set(key, (antal.get(key) || 0) + 1)
      const cur = out.get(key)
      if (!cur) { out.set(key, { ...g, product: FAMILY(g.product) }); continue }
      for (const f of ['n_frozen', 'n_settled', 'n_timely', 'n_evaluable',
        'n_unresolvable', 'n_cancelled', 'n_payout_incomplete', 'cost_kr', 'payout_kr']) {
        cur[f] = (cur[f] || 0) + (g[f] || 0)
      }
      if ((g.latest_frozen || '') > (cur.latest_frozen || '')) {
        cur.latest_frozen = g.latest_frozen
        cur.latest_product = g.latest_product
        cur.latest_draw_number = g.latest_draw_number
      }
      if ((g.best_correct ?? -1) > (cur.best_correct ?? -1)) cur.best_correct = g.best_correct
      cur.retired = cur.retired && g.retired
    }
    for (const [key, g] of out) {
      // Bara omräknad ROI där vi faktiskt slog ihop — annars står backendens
      // egen siffra kvar orörd.
      if (antal.get(key) > 1) g.roi = g.cost_kr > 0 ? g.payout_kr / g.cost_kr - 1 : null
    }
    return [...out.values()]
  }
  const allGroups = mergeFamily((systems?.groups || []).filter(inScope))
  const activeGroupBase = allGroups.filter((g) => !g.retired)
  const retiredGroupBase = allGroups.filter((g) => g.retired)
  const groupMatches = (g) => (
    // Alternativen kommer ur HIST_FAMILIES, så jämförelsen sker på familj.
    (groupFilter.product === 'alla' || FAMILY(g.product) === groupFilter.product)
    && (groupFilter.budget === 'alla' || String(g.budget) === groupFilter.budget)
    && (groupFilter.strategy === 'alla' || g.strategy === groupFilter.strategy)
    && (groupFilter.horizon === 'alla'
      || String(g.horizon_minutes) === groupFilter.horizon)
  )
  const activeGroups = activeGroupBase.filter(groupMatches)
  const retiredGroups = retiredGroupBase.filter(groupMatches)
  const groupProducts = HIST_FAMILIES.filter((p) =>
    activeGroupBase.some((g) => FAMILY(g.product) === p.id))
  const groupBudgets = [...new Set(activeGroupBase.map((g) => g.budget))]
    .filter((v) => v != null).sort((a, b) => a - b)
  const groupStrategies = [...new Set(activeGroupBase.map((g) => g.strategy))]
    .filter(Boolean)
  const groupHorizons = [...new Set(activeGroupBase.map((g) => g.horizon_minutes))]
    .filter((v) => v != null).sort((a, b) => b - a)
  const groupFilterActive = Object.values(groupFilter).some((v) => v !== 'alla')
  const setGroupFilterValue = (key, value) => setGroupFilter(
    (current) => ({ ...current, [key]: value }))
  const champRows = (systems?.champion_report?.rows || []).filter(inScope)
  const recent = (systems?.recent || [])
    .filter(inScope).filter((r) => showRetired || !r.retired)

  return (
    <div className="v3hist">
      <div className="v3histbar">
        <nav className="v3subnav" aria-label="Spel">
          <button className={product === 'alla' ? 'on' : ''}
            onClick={() => chooseProduct('alla')}>Alla spel</button>
          {HIST_FAMILIES.map((p) => (
            <button key={p.id} className={product === p.id ? 'on' : ''}
              onClick={() => chooseProduct(p.id)}>{p.label}</button>
          ))}
        </nav>
        <span className="v3hint">Filtret styr hela sidan — kuponger, systemfacit
          och omsättning.</span>
      </div>

      {/* ---------------------------- kuponger ---------------------------- */}
      <div className="v3card">
        <div className="v3cardhead"><h3>🎟️ Dina spelade kuponger</h3>
          <span className="v3hint">bara kuponger du markerat som spelade</span>
        </div>
        <PlayedPanel product={single ? product : null} />
      </div>

      {/* --------------------------- systemfacit -------------------------- */}
      <div className="v3card v3systembox" id="hist-system">
        <div className="v3cardhead"><h3>📋 Autopool · sparade förslag och facit</h3>
          {systems?.champion_key && (
            <span className="v3hint">champion: {systems.champion_key}</span>)}
        </div>
        <span className="v3hint">
          Det här är automatiskt sparade förslag, inte inlämnade spel. Före
          varje spelstopp fryser varvet vad radbyggaren föreslår — vid
          180 min och vid 20 min — och rättar sedan raderna mot riktigt utfall.
          <b> Championen är appens egen standardinställning</b>; övriga är
          utmanare. Ingen inställning byts förrän en utmanare slår championen på
          data som samlats EFTER att den registrerades, med minst{' '}
          {systems?.champion_report?.gate_min_draws ?? 40} omgångar och
          FDR-korrigering över hela utmanarfamiljen. Utdelningen är en
          kontrafaktisk uppskattning: den publicerade nivån späds med våra egna
          vinnande rader.
          {' '}Topptipset Dagens, Stryk och Extra räknas som ETT spel: de kör
          samma benchmarkfamilj på samma spelform, så deras omgångar hör till
          samma jämförelse. Pareringen sker på produkt OCH omgång, så de tre
          nummerserierna kan inte blandas ihop.
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

        {!allGroups.length && (
          <EmptyState title="Inga frysta testsystem ännu"
            detail="Första frysningen sker automatiskt när nästa omgång går in i sitt 180-minutersfönster." />
        )}
        {allGroups.length > 0 && (
          <>
            <div className="v3note">
              <b>Automatiska testsystem — inga pengar har spelats.</b>{' '}
              Varje rad följer en systeminställning över flera omgångar.
              Sammanlagt visar uträkningen antal tester med facit × kostnad per
              test. Resultaten får inte summeras mellan raderna.
            </div>
            {activeGroupBase.some((g) => g.research) && (
              <div className="v3note">
                <b>🧪 PH5-forward är ett riktigt men simulerat framtidstest.</b>{' '}
                Raderna frystes före spelstopp och rättas automatiskt, men inga
                pengar spelades. Researchrader kan inte byta champion eller
                ändra dina vanliga systemförslag.
              </div>
            )}

            <div className="v3groupfilters" aria-label="Filtrera testkonfigurationer">
              <label><span>Spel</span>
                <select value={groupFilter.product}
                  onChange={(e) => setGroupFilterValue('product', e.target.value)}>
                  <option value="alla">Alla spel</option>
                  {groupProducts.map((p) => <option key={p.id} value={p.id}>
                    {p.label}</option>)}
                </select>
              </label>
              <label><span>Kostnad/test</span>
                <select value={groupFilter.budget}
                  onChange={(e) => setGroupFilterValue('budget', e.target.value)}>
                  <option value="alla">Alla kostnader</option>
                  {groupBudgets.map((budget) => <option key={budget} value={String(budget)}>
                    {kr(budget)}</option>)}
                </select>
              </label>
              <label><span>Strategi</span>
                <select value={groupFilter.strategy}
                  onChange={(e) => setGroupFilterValue('strategy', e.target.value)}>
                  <option value="alla">Alla strategier</option>
                  {groupStrategies.map((strategy) => <option key={strategy} value={strategy}>
                    {STRATEGY_LABEL[strategy] || strategy}</option>)}
                </select>
              </label>
              <label><span>Fryst</span>
                <select value={groupFilter.horizon}
                  onChange={(e) => setGroupFilterValue('horizon', e.target.value)}>
                  <option value="alla">Alla tider</option>
                  {groupHorizons.map((minutes) => <option key={minutes} value={String(minutes)}>
                    {minutes} min före stopp</option>)}
                </select>
              </label>
              {groupFilterActive && <button className="v3filterreset"
                onClick={() => setGroupFilter({
                  product: 'alla', budget: 'alla', strategy: 'alla', horizon: 'alla',
                })}>Rensa filter</button>}
            </div>

            <h4 className="v3subhead">Aktiva testkonfigurationer{' '}
              <span className="v3hint">({activeGroups.length === activeGroupBase.length
                ? `${activeGroups.length} grupper`
                : `${activeGroups.length} av ${activeGroupBase.length} grupper`})</span></h4>
            <span className="v3hint">Senast testad är den senaste omgång där
              konfigurationen sparades. Klicka kolumnen för äldst eller nyast.</span>
            {activeGroups.length > 0
              ? <SystemGroupsTable id="hist-systemgroups-v5" groups={activeGroups}
                  limit={showAllGroups ? null : 20}
                  onOpenLatest={showLatestGroupTest} />
              : <EmptyState title="Inga testkonfigurationer matchar filtren"
                  detail="Ändra eller rensa filtren för att visa fler grupper." />}
            {activeGroups.length > 20 && (
              <button className="v3more"
                onClick={() => setShowAllGroups(!showAllGroups)}>
                {showAllGroups ? 'visa topp 20 ▲'
                  : `visa alla ${activeGroups.length} aktiva konfigurationer ▼`}</button>
            )}
          </>
        )}

        {retiredGroupBase.length > 0 && (
          <label className="v3toggle">
            <input type="checkbox" checked={showRetired}
              onChange={(e) => setShowRetired(e.target.checked)} />
            Visa pensionerade testkonfigurationer ({retiredGroups.length === retiredGroupBase.length
              ? `${retiredGroups.length} grupper`
              : `${retiredGroups.length} av ${retiredGroupBase.length} grupper`})
          </label>
        )}
        {showRetired && retiredGroupBase.length > 0 && (
          <>
            <h4 className="v3subhead">Pensionerade testkonfigurationer{' '}
              <span className="v3hint">({retiredGroups.length === retiredGroupBase.length
                ? `${retiredGroups.length} grupper`
                : `${retiredGroups.length} av ${retiredGroupBase.length} grupper`})</span></h4>
            <span className="v3hint">Äldre matris, mätt före 2026-08-05 och
              jämförbar bara med sig själv.</span>
            {retiredGroups.length > 0
              ? <SystemGroupsTable id="hist-systemgroups-retired-v2"
                  groups={retiredGroups} onOpenLatest={showLatestGroupTest} />
              : <EmptyState title="Inga pensionerade grupper matchar filtren"
                  detail="Rensa filtren för att se hela den äldre matrisen." />}
          </>
        )}

        {recent.length > 0 && (
          <details className="v3recent">
            <summary className="v3hint">Enskilda frysningar ({recent.length}) —
              klicka en rad för att se systemet mot facit</summary>
            <div className="v3histtablewrap">
              <table className="v3histtable">
                <thead><tr><th>Spel</th><th>Omgång</th><th>Spelstopp</th>
                  <th>Fryst</th><th>Sim. kostnad</th><th>Rader</th><th>Facit</th></tr></thead>
                <tbody>
                  {recent.slice(0, showAllFreezes ? recent.length : 20).map((r, i) => (
                    <tr key={i} className="v3histrowline" role="button" tabIndex={0}
                      onClick={() => showSystemDetail(r)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault(); showSystemDetail(r)
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
          <SystemDetail key={`${openSystem.product}:${openSystem.draw_number}:${openSystem.horizon}:${openSystem.config_key}`}
            product={openSystem.product} draw={openSystem.draw_number}
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
                {HIST_FAMILIES.map((p) => {
                  const o = overview[p.id]
                  return (
                    <tr key={p.id} className="v3histrowline" role="button" tabIndex={0}
                      onClick={() => chooseProduct(p.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault(); chooseProduct(p.id)
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
              {data.cancelled_count > 0 && (
                <span className="v3hint">{data.cancelled_count} inställda omgångar
                  finns kvar i arkivet men är exkluderade ur statistik och facit.</span>
              )}
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
                      const rowKey = `${d.product || product}:${d.draw_number}`
                      return [
                        <tr key={`${d.product || product}-${d.draw_number}`} className="v3histrowline"
                          role="button" tabIndex={0}
                          onClick={() => toggle(d.draw_number, d.product)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault(); toggle(d.draw_number, d.product)
                            }
                          }}>
                          <td>{d.draw_number}</td>
                          <td>{fmtDay(d.close)}</td>
                          <td>{d.turnover ? kr(d.turnover) : '–'}</td>
                          <td>{top ? `${top.name}: ${top.winners ?? '–'} st` : '–'}
                            {d.top_winners === 0 && <span className="v3roll" title="Ingen vinnare på toppnivån — potten rullar">🎰</span>}
                            {d.n_cancelled > 0 && <span className="v3cancel" title={`${d.n_cancelled} struken/strukna matcher`}>⚠️</span>}</td>
                          <td>{top?.amount ? kr(top.amount) : '–'}</td>
                          <td className="v3expand">{expanded === rowKey ? '▲' : '▼'}</td>
                        </tr>,
                        expanded === rowKey && (
                          <tr key={`${d.product || product}-${d.draw_number}-x`} className="v3histdetail"><td colSpan="6">
                            <div className="v3tiers">
                              {(d.tiers || []).map((t) => (
                                <span key={t.name} className="v3tier">
                                  {t.name}: <b>{t.winners ?? '–'}</b> à <b>{t.amount ? kr(t.amount) : '–'}</b>
                                </span>
                              ))}
                            </div>
                            {!detail[rowKey] && <LoadingState label="Hämtar matchfacit…" />}
                            {detail[rowKey]?.available && (
                              <table className="v3facit">
                                <tbody>
                                  {detail[rowKey].draw.events.map((e) => (
                                    <tr key={e.event_number} className={e.cancelled ? 'cancelled' : ''}>
                                      <td>{e.event_number}</td>
                                      <td>{e.home && e.away ? `${e.home} – ${e.away}` : e.description}</td>
                                      <td className="v3outcome">{e.cancelled ? '⚠️ struken' : e.outcome || '–'}</td>
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
                        : <span className="v3hint">samlar</span>}</td>
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
  danish_superliga: 'Danska Superliga',
  belgian_pro_league: 'Belgiska Pro League',
  primeira_liga: 'Primeira Liga',
  bolivian_primera: 'Bolivianska Primera División',
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
  { icon: '🎟️', title: 'PH5 256/512 rader', date: '2026-07-26', status: 'fals',
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
  const [radarErr, setRadarErr] = useState(null)
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
  const [radarViewFilter, setRadarViewFilter] = useState('played')
  const [radarLevelFilter, setRadarLevelFilter] = useState('alla')
  const [radarTypeFilter, setRadarTypeFilter] = useState('alla')
  const [radarOddsFilter, setRadarOddsFilter] = useState('alla')

  useEffect(() => {
    // engångsläsning — mätserierna rör sig på varv-/veckoskala, ingen poll
    get('/api/oddset/clv').then(setClv).catch((e) => { setClv(null); setErr(String(e)) })
    get('/api/oddset/predictions').then(setLedger).catch(() => setLedger(null))
    get('/api/oddset/radar-facit').then(setRadar).catch((e) => {
      setRadar(null); setRadarErr(String(e))
    })
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
    no_canonical_match: 'ingen säker koppling till Svenska Spels livemarknad',
    no_svenskaspel_id: 'matchen saknade id hos Svenska Spel',
    not_offered: 'Ö/U erbjöds inte just då',
    suspended: 'Ö/U var suspenderat vid signalen',
    no_eligible_quote: 'ingen källa hade ett färskt öppet pris på vald lina',
    all_sources_failed: 'samtliga oddskällor fick tekniskt fel',
  }[row.odds_status] || (row.odds_status?.startsWith('source_error')
    ? 'oddsfel vid signalen' : 'liveodds saknas'))
  const radarSource = (source) => ({
    svenskaspel: 'SvS', ninja: 'Ninja', pinnacle: 'Pinnacle',
  }[source] || source || 'okänd källa')
  const radarQuoteStatus = (quote) => {
    if (quote.status === 'captured') {
      return `${radarSource(quote.source)} · Ö ${quote.line} @ ${Number(
        quote.over_odds).toFixed(2)}${quote.selected ? ' · ✓ bäst' : ''}`
    }
    if (quote.status === 'line_mismatch') {
      return `${radarSource(quote.source)} · annan lina (${quote.line})`
    }
    if (quote.status === 'stale') {
      return `${radarSource(quote.source)} · för gammal cache${quote.age_s != null
        ? ` (${Math.round(quote.age_s)} s)` : ''}`
    }
    const reason = ({
      no_match: 'ingen säker matchkoppling', ambiguous_match: 'tvetydig match',
      suspended: 'suspenderad', not_offered: 'Ö/U saknades',
    }[quote.status] || (quote.status?.startsWith('source_error')
      ? 'källfel' : quote.status || 'saknas'))
    return `${radarSource(quote.source)} · ${reason}`
  }
  const radarOverResult = (v) => ({
    win: 'vinst', half_win: 'halvvinst', push: 'återbetald',
    half_loss: 'halvförlust', loss: 'förlust',
  }[v] || v)
  const radarOutcome = (row) => {
    if (!row.settled_at) return { icon: '⏳', label: 'Inväntar facit', cls: 'pending' }
    if (row.over_result === 'win' || row.over_result === 'half_win') {
      return { icon: '✓', label: radarOverResult(row.over_result), cls: 'won' }
    }
    if (row.over_result === 'loss' || row.over_result === 'half_loss') {
      return { icon: '✕', label: radarOverResult(row.over_result), cls: 'lost' }
    }
    if (row.over_result === 'push') {
      return { icon: '↔', label: radarOverResult(row.over_result), cls: 'push' }
    }
    return { icon: '–', label: 'saknar spelbart facit', cls: 'pending' }
  }

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
  const radarRows = radar?.signal_ledger?.rows || []
  const radarTestBets = radarRows.filter((row) => row.test_bet)
  const radarNotPlayed = radarRows.filter((row) => !row.test_bet)
  const radarVisibleRows = radarRows.filter((row) => {
    if (radarViewFilter === 'played' && !row.test_bet) return false
    if (radarViewFilter === 'not_played' && row.test_bet) return false
    if (radarLevelFilter !== 'alla' && row.signal_level !== radarLevelFilter) return false
    if (radarTypeFilter !== 'alla' && row.signal_type !== radarTypeFilter) return false
    if (radarOddsFilter === 'captured' && row.odds_status !== 'captured') return false
    if (radarOddsFilter === 'missing' && row.odds_status === 'captured') return false
    return true
  })
  const radarFiltersActive = radarViewFilter !== 'played'
    || radarLevelFilter !== 'alla' || radarTypeFilter !== 'alla'
    || radarOddsFilter !== 'alla'
  const radarGroupOrder = { 'xg-watch': 0, 'xg-strong': 1, 'proxy-watch': 2 }
  const radarGroups = [...(radar?.signal_ledger?.groups || [])].sort((a, b) =>
    (radarGroupOrder[`${a.signal_type}-${a.signal_level}`] ?? 99)
    - (radarGroupOrder[`${b.signal_type}-${b.signal_level}`] ?? 99))
  const radarTotalSignals = radarGroups.reduce(
    (sum, group) => sum + (group.n_signals || 0), 0)
  const radarRoi = (g) => g.n_priced_settled >= ROI_MIN_N
    ? evPct(g.roi_over) : '–'
  const radarRoiNote = (g) => g.n_priced_settled >= ROI_MIN_N
    ? `${g.n_priced_settled} spel · preliminärt`
    : `${g.n_priced_settled} spel · för få för ROI`
  const radarMissingBreakdown = (g) => {
    const counts = g.odds_status_counts || {}
    const sourceErrors = Object.entries(counts).reduce(
      (sum, [status, count]) => sum + (status.startsWith('source_error') ? count : 0), 0)
    const parts = [
      [counts.no_canonical_match, 'utan säker matchkoppling'],
      [counts.no_svenskaspel_id, 'utan SvS-id'],
      [counts.not_offered, 'utan erbjuden Ö/U'],
      [counts.suspended, 'suspenderad marknad'],
      [counts.no_eligible_quote, 'utan färskt öppet pris på vald lina'],
      [counts.all_sources_failed, 'där alla oddskällor fick fel'],
      [sourceErrors, 'källfel'],
      [counts.unknown, 'okänd prisstatus'],
    ].filter(([count]) => count > 0)
      .map(([count, label]) => `${count} ${label}`)
    return parts.length ? parts.join(' · ') : 'ingen förklaring rapporterad'
  }
  const radarSourceCoverage = (g) => Object.entries(g.quote_source_counts || {})
    .map(([source, counts]) => {
      const checked = Object.values(counts).reduce((sum, n) => sum + n, 0)
      const captured = counts.captured || 0
      const stale = counts.stale || 0
      return `${radarSource(source)} ${captured}/${checked}${stale ? ` (${stale} stale)` : ''}`
    }).join(' · ')
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
  const radarLevelCols = [
    { key: 'level', label: 'Vänta till', defaultDir: 'asc',
      value: (g) => radarGroupOrder[`${g.signal_type}-${g.signal_level}`] ?? 99 },
    { key: 'n_matches', label: 'Matcher som nådde nivån' },
    { key: 'n_priced_signals', label: 'Bästa pris låst' },
    { key: 'n_priced_settled', label: 'Facit på prissatta' },
    { key: 'goal_15min_rate', label: 'Mål inom 15 min' },
    { key: 'avg_goals_after', label: 'Snitt mål efter' },
    { key: 'roi_over', label: 'Simulerad Över-ROI' },
  ]
  const radarJournalCols = [
    { key: 'match', label: 'Match', defaultDir: 'asc',
      value: (row) => `${row.home} ${row.away}` },
    { key: 'captured_at', label: 'Signalögonblick', defaultDir: 'desc' },
    { key: 'decision', label: 'Beslut',
      value: (row) => `${row.test_bet ? 2 : row.blind_entry ? 1 : 0}-${row.signal_level}-${row.signal_type}` },
    { key: 'over_odds', label: 'Låst liveodds' },
    { key: 'over_profit', label: 'Facit' },
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
        <div className="v3card v3wide">
          <div className="v3cardhead"><h3>💰 Sharp-facit (CLV och utfall)</h3>
            <LabbPill s={activePrimaryClv.some((g) => g.green_ready) ? 'pass' : 'samlar'} /></div>
          {!clv && !err && <LoadingState label="Hämtar facit…" />}
          {clv && (
            <>
              <span className="v3hint">Aktiv version: <code>{activeSharp || '–'}</code>
                {!activePrimaryClv.length && ' · inga stängda flaggor ännu'}</span>
              <div className="v3evidence-table v3labb-summarytable">
                <table className="logtable">
                  <thead><tr><th>Mätning</th><th>Underlag</th><th>Resultat</th>
                    <th>Osäkerhet / träff</th></tr></thead>
                  <tbody>
                    {activePrimaryClv.map((g) => (
                      <tr key={`${g.league}-${g.version}`}>
                        <td><b>{LABB_LEAGUE[g.league] || g.league}</b>
                          <small>Aktiv version</small></td>
                        <td>{g.n_resolved} av {g.n} stängda</td>
                        <td className={evCls(g.avg_close_ev)}>{evPct(g.avg_close_ev)} Close-EV</td>
                        <td>90 % KI {ciStr(g.ci)}</td>
                      </tr>
                    ))}
                    {clv.sharp && (
                      <tr>
                        <td><b>Alla versioner</b><small>Samlat sedan start</small></td>
                        <td>{clv.sharp.n_resolved} av {clv.sharp.n} stängda</td>
                        <td className={evCls(clv.sharp.avg_close_ev)}>
                          {evPct(clv.sharp.avg_close_ev)} Close-EV</td>
                        <td>90 % KI {ciStr(clv.sharp.ci)}</td>
                      </tr>
                    )}
                    {clv.sharp?.n_outcomes > 0 && (
                      <tr title="Resultatbaserad ROI till first-odds på settlade 1X2-flaggor, alla versioner. Display — grönt beslutas av close-EV-grinden.">
                        <td><b>Faktiska 1X2-utfall</b><small>Visas bara som kontroll</small></td>
                        <td>{clv.sharp.n_outcomes} avgjorda</td>
                        <td className={evCls(clv.sharp.result_roi)}>
                          {evPct(clv.sharp.result_roi)} ROI</td>
                        <td>{rate(clv.sharp.hit_rate)} träff</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
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
              <div className="v3evidence-table">
                <table className="logtable">
                  <thead><tr><th>Marknad</th><th>Status</th><th>Modellfel</th>
                    <th>Pinnacle-fel</th><th>Underlag</th><th>log-score Δ</th></tr></thead>
                  <tbody>{modelCloseCurrent.map((g) => (
                    <tr key={`${g.market}-${g.version}`}
                      title={`Parad log-score mot Pinnacle vid samma horisont. Positivt KI helt över noll krävs.\nVersion ${g.version}`}>
                      <td><b>{LABB_MARKET[g.market] || g.market}</b>
                        <small><code>{g.version}</code></small></td>
                      <td><span className={`model-close-status ${g.status}`}>
                        {modelCloseLabel(g.status)}</span></td>
                      <td>{g.model_mae_pp?.toFixed(2) ?? '–'} pp</td>
                      <td>{g.sharp_mae_pp?.toFixed(2) ?? '–'} pp</td>
                      <td>{g.n_cases} fall · {g.n_matches} matcher ·
                        {' '}{g.span_days} {dayWord(g.span_days)}</td>
                      <td>{g.logscore_gain != null
                        ? <>{g.logscore_gain >= 0 ? '+' : ''}{g.logscore_gain.toFixed(4)}
                          {g.logscore_gain_ci && <small>90 % KI [{g.logscore_gain_ci[0].toFixed(4)}
                            ..{g.logscore_gain_ci[1].toFixed(4)}]</small>}</>
                        : '–'}</td>
                    </tr>
                  ))}</tbody>
                </table>
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
            <div className="v3evidence-table">
              <table className="logtable">
                <thead><tr><th>Aktiv signalgrupp</th><th>Status</th><th>Stängda</th>
                  <th>Matcher</th><th>Dagar</th><th>Nästa kontrollpunkt</th>
                  <th>90 % KI</th></tr></thead>
                <tbody>{activePrimaryGroups.map((g) => (
                  <tr key={`${g.league}-${g.market}-${g.version}`}
                    title="Kandidat kräver mängdkraven och positiv undre 90 %-KI-gräns. Datumet uppskattar bara mängd och tid.">
                    <td><b>{LABB_LEAGUE[g.league] || g.league} ·
                      {' '}{LABB_MARKET[g.market] || g.market}</b>
                      <small><code>{g.version}</code></small></td>
                    <td className={`ledgerstatus ${g.status}`}>{statusLabel(g.status)}</td>
                    <td>{g.n_resolved}/{candidateReq.n_resolved}</td>
                    <td>{g.n_matches}/{candidateReq.n_matches}</td>
                    <td>{g.span_days}/{candidateReq.span_days}</td>
                    <td>{candidateText(g)}</td>
                    <td>{g.ci
                      ? `[${(g.ci[0] * 100).toFixed(1)}..${(g.ci[1] * 100).toFixed(1)}]`
                      : '–'}{!g.ci_stable && g.ci ? ' · instabilt' : ''}</td>
                  </tr>
                ))}</tbody>
              </table>
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

        {/* ⚓ Två ankare togs bort 2026-08-07 när Smarkets kopplades bort som
            andra ankare: den har 56 030 priser på 1X2 och NOLL på AH/Ö/U/
            hörnor, så den kunde bara mäta 24 % av flaggorna och 271 av
            frånvaronoteringarna var brus om ett känt strukturellt hål.
            Spärren i ANCHOR_SOURCES står kvar — se
            docs/closing-drift-v8-forregistrering-2026-08-07.md. */}

        <div className="v3card v3radar-facit">
          <div className="v3cardhead"><h3>⚡ Radar-facit och signaljournal</h3>
            <LabbPill s={radar?.signal_ledger?.blind_gate?.status === 'pass'
              ? 'pass' : radar?.signal_ledger?.blind_gate?.status === 'no_support'
                ? 'fals' : 'samlar'} /></div>
          {!radar && !radarErr && <LoadingState label="Hämtar radar-facit…" />}
          {radarErr && !radar && <ErrorState message={radarErr} />}
          {radar && <>
          {radar?.signal_version && (
            <span className="v3hint">Kohort <code>{radar.signal_version}</code>
              {radar.signal_version_started_at
                ? ` sedan ${dShort(radar.signal_version_started_at)}` : ''} —
              räknarna nedan nollställdes vid versionsbytet (kohortregeln);
              äldre kohorter ligger kvar i journalen.</span>
          )}

          <h4 className="v3tabletitle">Signalregler</h4>
          <div className="v3evidence-table v3radar-tablewrap">
            <table className="logtable v3radar-rulestable" aria-label="Radarns signalregler">
              <thead><tr><th>Nivå</th><th>Tidsfönster</th><th>Krav</th>
                <th>När priset låses</th></tr></thead>
              <tbody>
                <tr><td><b>Följer · xG</b></td>
                  <td>{radar?.signal_ledger?.thresholds?.xg_watch?.minute
                    || 'Minut 15–78, minst 12 minuter kvar'}</td>
                  <td>{radar?.signal_ledger?.thresholds?.xg_watch?.rule
                    || 'Lagets xG−mål ≥ 0,65 eller matchens xG−mål ≥ 1,00'}</td>
                  <td>Första gången Följer-xG nås</td></tr>
                <tr className="strong"><td><b>Stark · xG</b></td>
                  <td>{radar?.signal_ledger?.thresholds?.xg_strong?.minute
                    || 'Samma tidsfönster som Följer'}</td>
                  <td>{radar?.signal_ledger?.thresholds?.xg_strong?.rule
                    || 'Lagets xG−mål ≥ 1,15 eller matchens xG−mål ≥ 1,65'}</td>
                  <td>Första gången Stark-xG nås</td></tr>
                <tr><td><b>Följer · skott</b></td>
                  <td>{radar?.signal_ledger?.thresholds?.proxy_watch?.minute
                    || 'Minut 20–78, minst 12 minuter kvar'}</td>
                  <td>{radar?.signal_ledger?.thresholds?.proxy_watch?.rule
                    || 'Stora chanser−mål ≥ 1,5, eller skott på mål−mål ≥ 5 och minst 8 skott i box'}</td>
                  <td>Första gången Följer-skott nås</td></tr>
              </tbody>
            </table>
          </div>

          <div className="v3radar-explainer">
            <b>En match kan gå från Följer till Stark.</b>
            <span>Huvudblindtestet använder bara matchens allra första aktiva
              signal och kan därför aldrig innehålla två spel på samma match.</span>
            <span>Nivåjämförelsen längre ned gör en annan kontroll: den visar
              vilket resultat man hade fått om man alltid väntat på just den
              nivån. Där kan samma match finnas både i Följer- och Stark-raden.</span>
            <span>SvS, Ninja och Pinnacle frågas i signalögonblicket. Högsta
              öppna Över-odds låses på exakt samma lina. En gammal
              Pinnacle-cache får aldrig vinna. Saknas ett färskt pris blir
              raden ingen insats och priset bakfylls aldrig.</span>
          </div>

          <h4 className="v3tabletitle">Huvudblindtest · högst ett spel per match</h4>
          <div className="v3evidence-table v3radar-tablewrap">
            <table className="logtable v3radar-maintable">
              <thead><tr><th>Beslutsregel</th><th>Matcher med signal</th>
                <th>Pris låst</th><th>Facit klart</th><th>Över-ROI</th>
                <th>90 % KI</th><th>Testkrav</th></tr></thead>
              <tbody><tr>
                <td><b>Matchens första aktiva signal</b>
                  <small>Följer eller Stark, oavsett signaltyp</small></td>
                <td>{gate?.n_matches ?? 0}</td>
                <td><b>{gate?.n_priced_signals ?? 0}</b>
                  <small>öppet odds i beslutet</small></td>
                <td><b>{gateN}</b>
                  <small>av {gate?.n_priced_signals ?? 0} prissatta</small></td>
                <td className={gateN >= ROI_MIN_N ? evCls(gate?.roi_over) : ''}>
                  {gateN >= ROI_MIN_N ? evPct(gate?.roi_over) : '–'}
                  <small>{gateN >= ROI_MIN_N ? `${gateN} spel · preliminärt`
                    : `visas från ${ROI_MIN_N} spel`}</small></td>
                <td>{gateN >= ROI_MIN_N ? ciStr(gate?.roi_ci90) : '–'}</td>
                <td>{gateN}/{gate?.required_priced_settled ?? 200} spel
                  <small>{gate?.n_match_days ?? 0}/{gate?.required_match_days ?? 20} matchdygn
                    {' · '}{gate?.span_days ?? 0}/{gate?.required_span_days ?? 30} dygns spann</small></td>
              </tr></tbody>
            </table>
          </div>
          <span className="v3hint">Resultatet är inte godkänt för blind ryggning före minst
            {' '}{gate?.required_priced_settled ?? 200} prissatta och avgjorda matcher,
            {' '}{gate?.required_match_days ?? 20} distinkta matchdygn,
            {' '}{gate?.required_span_days ?? 30} dygns spann och en positiv undre
            90 %-KI-gräns. Matchantalet är den statistiska styrkan; dygnskraven finns
            bara för att de matcherna inte ska komma från ett enda tillfälle —
            spann ensamt mätte avståndet mellan första och sista observationen,
            inte spridningen.</span>

          {!!Object.keys(gate?.source_roi || {}).length && (
            <>
              <h4 className="v3tabletitle">Per oddskälla · om vi alltid spelat hos en enda</h4>
              <span className="v3hint">Alla källor prissätter exakt den lina signalen
                bokförde, så det enda som skiljer raderna är priset. Läs ROI och
                täckning ihop: en källa som bara listar hälften av matcherna kan ha
                bäst ROI utan att vara ett bättre val, och bortfallet är inte
                slumpmässigt — en bok som stänger marknaden när den är osäker lämnar
                just de matcherna ur sin egen serie.</span>
              <div className="v3evidence-table v3radar-tablewrap">
                <table className="logtable">
                  <thead><tr><th>Källa</th><th>Pris på samma lina</th>
                    <th>Vann prisjämförelsen</th><th>Snittodds</th>
                    <th>Över-ROI</th><th>90 % KI</th></tr></thead>
                  <tbody>{Object.entries(gate.source_roi)
                    .sort(([, a], [, b]) => (b.n_priced || 0) - (a.n_priced || 0))
                    .map(([source, s]) => (
                      <tr key={source}>
                        <td><b>{radarSource(source)}</b>
                          <small>{s.playable ? 'spelbar bok'
                            : 'ankare — inte ett bokresultat'}</small></td>
                        <td><b>{s.n_priced}</b> av {s.n_asked}</td>
                        <td>{s.n_best}</td>
                        <td>{s.avg_over_odds ?? '–'}</td>
                        <td className={s.n_priced >= ROI_MIN_N ? evCls(s.roi_over) : ''}>
                          {s.n_priced >= ROI_MIN_N ? evPct(s.roi_over) : '–'}
                          <small>{s.n_priced >= ROI_MIN_N
                            ? `${s.n_priced} spel · preliminärt`
                            : `visas från ${ROI_MIN_N} spel`}</small></td>
                        <td>{s.n_priced >= ROI_MIN_N ? ciStr(s.roi_ci90) : '–'}</td>
                      </tr>
                    ))}</tbody>
                </table>
              </div>
              <span className="v3hint"><b>Pinnacle är ankare, inte bok.</b> Den har
                lägst marginal och vinner därför nästan varje prisjämförelse. En ROI
                mätt på dess pris är “vad fair value gav mig”, inte vad en bok gav —
                den raden får aldrig läsas som ett bokresultat och grindar ingenting.</span>
            </>
          )}

          {radar && !radar.signal_ledger?.groups?.length && (
            <div className="v3note">
              Inga signaler i den här kohorten ännu. Det är väntat direkt efter
              ett versionsbyte — räknarna nollställs och fylls först när
              matcher spelas. Föregående kohorters rader finns kvar i
              journalen och blandas aldrig in.
            </div>
          )}
          {!!radarGroups.length && (
            <>
              <h4 className="v3tabletitle">Nivåjämförelse · om vi alltid väntat på…</h4>
              <span className="v3hint">Det här är tre separata jämförelseregler,
                inte extra spel i huvudtestet. Summera därför inte raderna. “Bästa
                pris låst” betyder högsta öppna Över-odds på samma lina bland
                de färska priser som faktiskt observerades när nivån nåddes.</span>
              <SortableTable id="labb-radar-levels" columns={radarLevelCols}
                rows={radarGroups} defaultSort={{ key: 'level', dir: 'asc' }}
                className="logtable v3radar-leveltable"
                wrapperClassName="v3evidence-table v3radar-tablewrap"
                renderRow={(g) => (
                    <tr key={`${g.signal_type}-${g.signal_level}`}>
                      <td><b>{radarLevel(g.signal_level)} · {radarType(g.signal_type)}</b>
                        <small>{g.signal_level === 'strong'
                          ? 'ignorera tidigare Följer och vänta' : 'första gången nivån nås'}</small></td>
                      <td><b>{g.n_matches}</b></td>
                      <td><b>{g.n_priced_signals}</b> av {g.n_matches}
                        <small>{g.n_matches - g.n_priced_signals} utan färskt öppet pris</small>
                        {!!radarSourceCoverage(g) &&
                          <small>Källtäckning: {radarSourceCoverage(g)}</small>}
                        {g.n_matches > g.n_priced_signals &&
                          <small>{radarMissingBreakdown(g)}</small>}</td>
                      <td><b>{g.n_priced_settled}</b> av {g.n_priced_signals}</td>
                      <td>{rate(g.goal_15min_rate)}
                        <small>{g.n_goal_15min ?? 0} avgjorda observationer</small></td>
                      <td>{g.avg_goals_after ?? '–'}</td>
                      <td className={g.n_priced_settled >= ROI_MIN_N
                        ? evCls(g.roi_over) : ''}>{radarRoi(g)}
                        <small>{radarRoiNote(g)}</small></td>
                    </tr>
                )} />
              <span className="v3hint"><b>Så räknas nivå-ROI:</b> en låtsasenhet
                placeras på Över till priset som låstes när nivån nåddes. Nettot
                delas med antalet prissatta och avgjorda matcher i just den raden.
                Exempelvis +4,5 % betyder +0,045 enhet per satsad enhet i snitt —
                inte att underlaget är stort nog för en rekommendation.</span>
            </>
          )}

          <details className="v3radar-old">
            <summary>Diagnostiskt rå-providerfacit utan liveodds</summary>
            <span className="v3hint">Detta jämför varje källas egna ögonblick och
              lånar inte klocka eller ställning från en annan källa. Signaljournalen
              ovan är facitet för det som faktiskt visades.</span>
            <div className="v3evidence-table v3radar-tablewrap">
              <table className="logtable">
                <thead><tr><th>Källa till signal</th><th>Ögonblick</th>
                  <th>Matcher</th><th>Mål inom 15 min</th><th>Basnivå</th></tr></thead>
                <tbody>{['xg', 'proxy'].map((k) => {
                  const g = radar?.groups?.[k]
                  const a = g?.outcomes?.outcome_15min
                  return (
                    <tr key={k}>
                      <td><b>{k === 'xg' ? 'xG' : 'Skottbaserad'}</b></td>
                      <td>{g?.n_signal_moments ?? '–'}</td>
                      <td>{g?.n_signal_matches ?? '–'}</td>
                      <td>{a?.n_resolved ? `${a.hits}/${a.n_resolved} = ${rate(a.rate)}` : '–'}</td>
                      <td>{a?.n_resolved ? rate(a.base_rate) : '–'}</td>
                    </tr>
                  )
                })}</tbody>
              </table>
            </div>
          </details>

          {!!radarRows.length && (
            <details className="v3radar-log" open>
              <summary>Matchjournal · {radarTotalSignals} signaler ·
                {' '}{gate?.n_priced_signals ?? radarTestBets.length} blindtestspel</summary>
              <div className="v3radar-filters" aria-label="Filtrera matchjournalen">
                <label>Visning
                  <select value={radarViewFilter}
                    onChange={(e) => {
                      const view = e.target.value
                      setRadarViewFilter(view)
                      if (view === 'played' && radarLevelFilter === 'strong') {
                        setRadarLevelFilter('alla')
                      }
                    }}>
                    <option value="played">Blindtestspel ({radarTestBets.length})</option>
                    <option value="all">Alla signaler ({radarRows.length})</option>
                    <option value="not_played">Ej spelade ({radarNotPlayed.length})</option>
                  </select>
                </label>
                <label>Nivå
                  <select value={radarLevelFilter} onChange={(e) => {
                    const level = e.target.value
                    setRadarLevelFilter(level)
                    if (level === 'strong' && radarViewFilter === 'played') {
                      setRadarViewFilter('all')
                    }
                  }}>
                    <option value="alla">Alla nivåer</option>
                    <option value="watch">Följer</option>
                    <option value="strong">Stark</option>
                  </select>
                </label>
                <label>Signaltyp
                  <select value={radarTypeFilter}
                    onChange={(e) => setRadarTypeFilter(e.target.value)}>
                    <option value="alla">Alla typer</option>
                    <option value="xg">xG</option>
                    <option value="proxy">Skottbaserad</option>
                  </select>
                </label>
                <label>Livepris
                  <select value={radarOddsFilter}
                    onChange={(e) => setRadarOddsFilter(e.target.value)}>
                    <option value="alla">Med och utan pris</option>
                    <option value="captured">Pris låst</option>
                    <option value="missing">Pris saknas</option>
                  </select>
                </label>
                <button type="button" disabled={!radarFiltersActive} onClick={() => {
                  setRadarViewFilter('played'); setRadarLevelFilter('alla')
                  setRadarTypeFilter('alla'); setRadarOddsFilter('alla')
                }}>Återställ</button>
              </div>
              <span className="v3hint">Visar <b>{radarVisibleRows.length}</b> av
                {' '}{radarRows.length} journalrader. Väljer du Stark öppnas
                automatiskt alla signaler, eftersom Stark-raderna är senare
                observationer och inte extra spel i huvudblindtestet.</span>
              {!radarVisibleRows.length && (
                <div className="v3note">Inga journalrader matchar de valda filtren.</div>
              )}
              {!!radarVisibleRows.length && (
                <SortableTable id="labb-radar-journal" columns={radarJournalCols}
                  rows={radarVisibleRows}
                  defaultSort={{ key: 'captured_at', dir: 'desc' }}
                  className="logtable v3radar-logtable"
                  wrapperClassName="v3evidence-table v3radar-tablewrap"
                  renderRow={(row) => {
                    const outcome = radarOutcome(row)
                    return (
                      <tr className={row.test_bet
                        ? `testbet ${outcome.cls}` : 'notplayed'} key={row.id}>
                        <td><b>{row.home} – {row.away}</b></td>
                        <td>{radarTime(row.captured_at)}
                          <small>{row.minute ?? '–'}′ · ställning{' '}
                            {row.home_score ?? '–'}–{row.away_score ?? '–'}</small></td>
                        <td>{row.test_bet
                          ? <><b>{radarLevel(row.signal_level)} · {radarType(row.signal_type)}</b>
                            <small>första signalen · räknas i huvudtestet</small></>
                          : <><b>Ingen insats</b><small>{row.blind_entry
                            ? radarOddsStatus(row)
                            : 'senare signal – första signalen äger huvudtestet'}</small></>}
                          <small>{row.reason}</small></td>
                        <td>{row.odds_status === 'captured'
                          ? <><b>Ö {row.ou_line} @ {Number(row.over_odds).toFixed(2)}</b>
                            <small>U @ {Number(row.under_odds).toFixed(2)}</small>
                            <small>{radarSource(row.odds_source)} · bäst på samma lina</small>
                            <small>låst {radarTime(row.odds_observed_at)}</small></>
                          : <span className="v3hint">{radarOddsStatus(row)}</span>}
                          {!!row.odds_quotes?.length && row.odds_quotes.map((quote) => (
                            <small key={`${row.id}-${quote.source}`}>
                              {radarQuoteStatus(quote)}
                            </small>
                          ))}</td>
                        <td className="v3radar-result">
                          {row.test_bet
                            ? <><b className={outcome.cls}><i>{outcome.icon}</i>{outcome.label}</b>
                              <small>{row.settled_at
                                ? `${row.final_home_score}–${row.final_away_score} · ${row.goals_after_signal} mål efter signalen${row.over_profit == null ? '' : ` · ${row.over_profit >= 0 ? '+' : ''}${row.over_profit.toFixed(2)} u`}`
                                : 'Matchen är ännu inte rättad'}</small></>
                            : <><b>Observation</b><small>{row.settled_at
                              ? `${row.final_home_score}–${row.final_away_score} · ingår inte i ROI`
                              : 'väntar på slutresultat'}</small></>}
                        </td>
                      </tr>
                    )
                  }} />
              )}
            </details>
          )}
          <span className="v3hint">Shadow: detta påverkar inga tips, Kelly, notiser eller
            systemförslag. Metod: <code>docs/live-radar-2026-07-25.md</code>.</span>
          </>}
        </div>

        {/* PH3-systemledgern togs bort härifrån 2026-08-05. Den visade samma
            siffror som Historikens Systemfacit, fast grundare — och PH3 är
            pool, inte odds. Historik äger den nu, med champion-jämförelse och
            klick-in mot facit. */}

        <div className="v3card v3wide">
          <div className="v3cardhead"><h3>🔬 Övriga forskningsspår</h3>
            <span className="v3hint">samlad status</span></div>
          <div className="v3evidence-table v3labb-summarytable">
            <table className="logtable">
              <thead><tr><th>Spår</th><th>Status</th><th>Slutsats / läge</th>
                <th>Dokumentation</th></tr></thead>
              <tbody>{LABB_RESEARCH.map((c) => (
                <tr key={c.title}>
                  <td><b>{c.icon} {c.title}</b>{c.date && <small>{c.date}</small>}</td>
                  <td><LabbPill s={c.status} /></td>
                  <td className="v3wrapcell">{c.text}</td>
                  <td><code>{c.doc}</code></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ================================= Skal =================================== */

export default function AppV3() {
  // En ny/omladdad session ska alltid ge den snabba översikten. Att återställa
  // Historik/Oddset här gjorde mobilens första skärm beroende av deras stora
  // rapporter innan användaren ens valt dem.
  const [view, setView] = useState('idag')
  const [histProduct, setHistProduct] = useState(null)
  const [histFocus, setHistFocus] = useState(null)
  const [oddsetFocus, setOddsetFocus] = useState(null)
  const go = (v) => {
    if (v !== 'oddset') setOddsetFocus(null)
    setView(v)
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
        {view === 'ph5' && <ErrBoundary><Ph5V3 /></ErrBoundary>}
        {view === 'labb' && <ErrBoundary><LabbV3 /></ErrBoundary>}
      </main>
      <footer className="v3foot">Lokal data från Svenska Spel + Pinnacle · personligt verktyg</footer>
    </div>
  )
}
