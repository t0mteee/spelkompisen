// Appens skal (enda gränssnittet sedan 2026-07-26, då klassiska vyn revs).
// De tunga komponenterna (analys/bygg/kupong/oddset) importeras från App.jsx,
// som är komponentbiblioteket. Eget här: skalet med vyväxlingen samt
// Idag-översikten, Historik-vyn (PH1-settlementlagret) och Labb.
import './AppV3.css'
import { useEffect, useRef, useState } from 'react'
import { get, getDetail, readState } from './lib/api.js'
import { POOL_GAMES, FAMILY_LABEL, HIST_FAMILIES, IS_FAMILY, ROI_MIN_N, hoursTo, closesIn, fmtDay, fmtKickoff, oddsSkift, selLabel3 } from './lib/labels.js'
import { Ph5V3, MaxTestsV3 } from './historik/ForwardTestV3.jsx'
import { HistorikV3 } from './historik/HistorikV3.jsx'
import { LabbV3 } from './labb/LabbV3.jsx'
import { AnalysisTable, SystemView, CouponPanel, SharpPanel, SteamPanel, ClvPanel, BombenView, OddsetView, Legend, Collection, LoadingState, ErrorState, ErrBoundary, STRATEGIES, STRATEGY_EV, BUDGET_STOPS, SYSTEM_BASE, SYSTEM_SVS, FAMILY, kr, fmtClose, PlayRec, oddsetBestValue } from './App.jsx'
import { beginRequest, payoutMatchesSelection, requestIsCurrent, uniqueDraws } from './poolSelection.js'
import { projectionBasisText } from './playRec.js'

const VIEWS = [
  { id: 'idag', label: 'Idag', icon: '☀️' },
  { id: 'pool', label: 'Poolspel', icon: '🎟️' },
  { id: 'oddset', label: 'Oddset', icon: '⚡' },
  { id: 'historik', label: 'Historik', icon: '🗄' },
  { id: 'ph5', label: '5 000-test', icon: '🧪' },
  { id: 'maxtest', label: 'Max-tester', icon: '🚀' },
  { id: 'labb', label: 'Labb', icon: '🔬' },
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
  // Tystnad i Oddset-varvet, liveradarn eller pooltick (oddset_health).
  const oddsetIssues = health?.oddset?.issues || []
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
      {oddsetIssues.length > 0 && (
        <div className="v3alert" role="alert">
          <b>⚠️ Oddset-/liveinsamlingen är tyst eller felar</b>
          {oddsetIssues.slice(0, 4).map((issue, i) => (
            <span key={`${issue.source}-${issue.kind}-${i}`}>
              {issue.source}: {issue.message}
            </span>
          ))}
          {oddsetIssues.length > 4 && <span>+{oddsetIssues.length - 4} ytterligare</span>}
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
        {view === 'maxtest' && <ErrBoundary><MaxTestsV3 /></ErrBoundary>}
        {view === 'labb' && <ErrBoundary><LabbV3 /></ErrBoundary>}
      </main>
      <footer className="v3foot">Lokal data från Svenska Spel + Pinnacle · personligt verktyg</footer>
    </div>
  )
}
