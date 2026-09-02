// Labb = 100 % ODDS: bevisytan för alla mät-/shadowspår. Bruten ur AppV3.jsx 2026-09-02.
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { ROI_MIN_N, LABB_PRIMARY, LABB_LEAGUE, LABB_MARKET, LABB_BOOK, LABB_RESEARCH } from '../lib/labels.js'
import { LabbPill } from '../components/badges.jsx'
import { LoadingState, ErrorState, SortableTable } from '../App.jsx'

export function LabbV3() {
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
