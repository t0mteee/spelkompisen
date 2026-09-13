// Standardjämförelsen (PH3): champion mot utmanare, aktiva och pensionerade
// testkonfigurationer, enskilda frysningar och exakt fryst system. Bruten ur
// HistorikV3.jsx 2026-09-13 (Historik → Tester). `product` = 'alla' eller
// en familj; `initialOpen` öppnar ett exakt system direkt (direktlänk).
import { useEffect, useState } from 'react'
import { visibleResearch } from '../lib/couponView.js'
import { get } from '../lib/api.js'
import { PRODUCT_LABEL, HIST_FAMILIES, fmtDay, STRATEGY_LABEL, horizonLabel, pctSigned, roiCls } from '../lib/labels.js'
import { BuildBadge } from '../components/badges.jsx'
import { SystemDetail, SystemGroupsTable } from './SystemDetail.jsx'
import { EmptyState, FAMILY, kr } from '../App.jsx'

export function SystemfacitCard({ product = 'alla', initialOpen = null, onOpenSystem = null, onCloseSystem = null }) {
  const single = product !== 'alla'
  const [systems, setSystems] = useState(null)
  // Öppet system: föräldern (rutten) styr när den skickar `initialOpen`,
  // annars lokalt. Inga effekter behövs — läget härleds vid render.
  const [localOpen, setLocalOpen] = useState(null)
  const openSystem = initialOpen || localOpen
  const setOpenSystem = setLocalOpen
  const [showAllFreezes, setShowAllFreezes] = useState(false)
  const [showAllGroups, setShowAllGroups] = useState(true)
  const [showRetired, setShowRetired] = useState(false)
  const [groupFilter, setGroupFilter] = useState({
    product: 'alla', budget: 'alla', strategy: 'alla', horizon: 'alla',
  })
  useEffect(() => {
    let current = true
    get('/api/pool/systems').then((v) => { if (current) setSystems(v) }).catch(() => { if (current) setSystems(null) })
    return () => { current = false }
  }, [])
  const showSystemDetail = (row) => {
    setOpenSystem(row)
    onOpenSystem?.(row)
  }
  const showLatestGroupTest = (group) => showSystemDetail({
    product: group.latest_product || group.product,
    draw_number: group.latest_draw_number,
    horizon: group.horizon,
    config_key: group.config_key,
  })

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
  const allGroups = mergeFamily((systems?.groups || []).filter(visibleResearch).filter(inScope))
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
    .filter(visibleResearch).filter(inScope).filter((r) => showRetired || !r.retired)
  return (
    <>
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
            onClose={() => { setOpenSystem(null); onCloseSystem?.() }} />
        )}
      </div>
    </>
  )
}
