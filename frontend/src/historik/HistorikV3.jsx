// Historik = 100 % POOL (ytgränsen 2026-08-05). Bruten ur AppV3.jsx 2026-09-02.
import { useEffect, useState } from 'react'
import { get } from '../lib/api.js'
import { PRODUCT_LABEL, HIST_FAMILIES, IS_FAMILY, fmtDay, STRATEGY_LABEL, horizonLabel, pctSigned, roiCls, HISTORIK_RESEARCH } from '../lib/labels.js'
import { MiniSpark, BuildBadge, LabbPill } from '../components/badges.jsx'
import { SystemDetail, SystemGroupsTable } from '../historik/SystemDetail.jsx'
import { LoadingState, EmptyState, ErrorState, FAMILY, kr, PlayedPanel } from '../App.jsx'

export function HistorikV3({ initialProduct, focus }) {
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
          <span className="v3hint">markerade direkt eller importerade i efterhand</span>
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
                  κ-varianter får föreslås.">PH4-fönster</th>
                <th title="Omgångar med observerad jackpot vid spelstopp (senast
                  verifierade snapshot före stängning). Prognosen är jackpotblind
                  tills kravet är nått.">Jackpot vid stopp</th></tr></thead>
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
                      <td>{h.jackpot_close_n ?? 0}/{h.jackpot_close_krav ?? '–'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {Object.entries(halsa)
            .filter(([p, h]) => (!single || p === product) && (h.jackpot_rader || []).length > 0)
            .map(([p, h]) => (
              <div key={`jp-${p}`} className="v3histtablewrap">
                <span className="v3hint">{PRODUCT_LABEL[p] || p}: prognos mot utfall
                  i omgångar med jackpot vid stopp. Underlag för en jackpotdimension
                  i prognosen — ingen modell förrän {h.jackpot_close_krav} omgångar.</span>
                <table className="v3histtable">
                  <thead><tr><th>Stopp</th><th>Jackpot</th><th>Prognos</th>
                    <th>Utfall</th><th>Fel</th></tr></thead>
                  <tbody>
                    {h.jackpot_rader.map((r) => (
                      <tr key={r.close}>
                        <td>{String(r.close).slice(0, 10)}</td>
                        <td>{kr(r.jackpot_close)}</td>
                        <td>{r.prognos == null ? '–' : kr(r.prognos)}</td>
                        <td>{kr(r.net_sale)}</td>
                        <td className={r.fel == null ? 'v3hint' : (r.fel > 0 ? 'v3neg' : 'v3pos')}>
                          {r.fel == null ? '–' : `${r.fel > 0 ? '+' : ''}${(r.fel * 100).toFixed(0)} %`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
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
