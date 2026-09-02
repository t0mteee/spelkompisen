/* eslint-disable react-refresh/only-export-components -- filen delar
   medvetet komponenter och hjälpare; samma undantag som App.jsx alltid haft. */
// Oddset-vyn med underflikar Matcher/Live/Värdespel/Rörelser/Lagstyrka.
// Bruten ur App.jsx 2026-09-02; monteras i AppV3 via App.jsx export.
import { Fragment, useEffect, useRef, useState } from 'react'
import '../App.css'
import { timeAgo } from '../lib/format.js'
import { InfoDot, useStoredBool, LoadingState, EmptyState, ErrorState } from '../components/ui.jsx'
import { SortableTable } from '../components/SortableTable.jsx'
import { summarizeSourceHealth } from '../sourceHealth.js'

// Oddset-delen (Etapp 1 i docs/plan.md): matchlista i tidsordning med Svenska Spel-odds
// (Kambi) + sharp (Pinnacle) för Allsvenskan, Eliteserien och träningsmatcher.
// Rörelse-konvention (från vm): röd ↓ = oddset NER (ökad vinstchans), grön ↑ = UPP.
export const ODDSET_HIDDEN_KEY = 'svs_oddset_hidden'
export function OddsetLegend() {
  const [open, setOpen] = useStoredBool('svs_ui_oddset_legend')
  return (
    <div className="legendbox">
      <button className="legend-toggle" onClick={() => setOpen(!open)}>
        ℹ️ Vad betyder siffrorna — och vad är värde? {open ? '▲' : '▼'}
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
// ---------- Delad värdenivå-logik (💰-korten + Rek-kolumnen) ----------
// Rek-cellen är ren VISNING av värdemotorns output — samma urval och samma
// nivåtrösklar som 💰-korten. Båda ytorna (och v3-dashboardens värdekort)
// MÅSTE läsa dessa helpers, aldrig egna kopior, så att de inte kan glida isär.
// Urval: bästa selektionen per match = högst kvalitet q = edge/(odds−1),
// bakom spelgrinden edge ≥ 2 % och q ≥ 0,75 % (högoddsar-edges är för sköra).
export function oddsetBestValue(m) {
  let best = null
  for (const [mk, per] of Object.entries(m.value || {})) {
    for (const [sg, v] of Object.entries(per)) {
      if (v.edge < 0.02 || (v.q ?? 0) < 0.0075) continue
      if (!best || (v.q ?? 0) > (best.v.q ?? 0)) best = { mk, sg, v }
    }
  }
  return best
}
/* Böcker man faktiskt kan lägga ett spel hos. Skild från ANKARE (Pinnacle,
   Smarkets), som är prisreferens. Se ANKARE ≠ BOK i CLAUDE.md — men skälet
   att Pinnacle inte står här är MÄTT, inte principiellt: på matcher där ingen
   mjuk bok prissatt tar Pinnacle ~11,5 % marginal på 1X2 mot ~5,6 % i övrigt
   (uppmätt 2026-08-14 på 28 mot 132 matcher), och den uppmätta closing-driften
   är 0,3–0,6 pp. Betinia ligger kvar i BOOK_NAME för historiken men samlas
   inte längre. */
export const PLAYABLE_BOOKS = ['svenskaspel', 'expekt', 'ninjacasino']

// Nivå: OMTVISTAD när andra sharp-ankaret (Smarkets) värderar samma bokodds
// negativt; annars STARK/EDGE/SVAG på kvalitet q — inte på rå edge.
/* ⚓-nivån "OMTVISTAD EDGE" är borttagen 2026-08-12. Den byggde på Smarkets
   som andra sharp-ankare, vilket kopplades bort 2026-08-07: källan hade
   56 030 priser på 1X2 men NOLL på AH/Ö/U/hörnor och kunde bara mäta 24 % av
   flaggorna, så markeringen sa mer om täckningshålet än om edgen.

   Mätningen fortsätter i skugga (`anchor2_*` i oddset_value_log) och spärren i
   ANCHOR_SOURCES står kvar — den är en säkerhetsspärr som hindrar Smarkets
   från att bli spelbar bok, inte en visning. Skulle ankaret återinföras är det
   ett nytt beslut med egen förregistrering, inte en återställd etikett. */
export function oddsetValueTier(v) {
  const q = v.q ?? 0
  if (q >= 0.04) return { cls: 't3', label: 'STARK EDGE', short: 'STARK' }
  if (q >= 0.02) return { cls: 't2', label: 'EDGE', short: 'EDGE' }
  return { cls: 't1', label: 'SVAG EDGE', short: 'SVAG' }
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
export function PowerRankPanel({ leagues }) {
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
        <b>🏋️ Lagstyrka och xPoäng</b>
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
export function OddsetView({ focus = null } = {}) {
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
  // Matcher utan spelbart bokpris döljs som standard — till skillnad från
  // startade-filtret, som är av tills man ber om det. Se PLAYABLE_BOOKS.
  const [hideNoOdds, setHideNoOdds] = useState(() => {
    try { return localStorage.getItem('svs_oddset_hide_no_odds') !== '0' } catch { return true }
  })
  const [bank, setBank] = useState(() => {
    try { return Number(localStorage.getItem('svs_oddset_bank')) || 1000 } catch { return 1000 }
  })
  // Verktygsraden är hopfälld på mobil (⚙). Medvetet INTE persisterad: den är
  // ett tillfälligt uppslag, inte en inställning som ska överleva sessionen.
  const [showTools, setShowTools] = useState(false)
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
  const toggleNoOdds = () => {
    setHideNoOdds(!hideNoOdds)
    try {
      localStorage.setItem('svs_oddset_hide_no_odds', hideNoOdds ? '0' : '1')
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
    return (
      <span className="epill"
        title={`Devigad Pinnacle: ${(v.fair * 100).toFixed(1)}% (fair odds ${(1 / v.fair).toFixed(2)})\nBoken betalar ${v.odds.toFixed(2)} → ${(v.edge * 100).toFixed(1)}% övervärde\nKvalitet (Kelly-andel): ${((v.q ?? 0) * 100).toFixed(1)}% — samma edge är skörare ju högre odds${v.derived ? '\n(P~ = härlett ur handikapp — ta med en nypa salt)' : ''}`}>
        {prefix && `${prefix} `}+{Math.round(v.edge * 100)}%{v.derived ? '°' : ''}
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
            title={`Egen modell (xG-viktad Poisson-styrkefit; DC-korrektion i prediktionen): ${(md.p[sign] * 100).toFixed(1)}%\nμ ${md.mu[0]}–${md.mu[1]} · T=${md.cal_t || 1}${md.anchored ? ' · totalnivå ankrad mot sharp Ö/U' : ' · OANKRAD (ingen sharp-linje ännu)'}${md.prior ? '\n⚠️ Elo-prior: minst ett lag har tunn historik — styrka skattad ur ClubElo' : ''}\nT valdes på samma historiska backtestmaterial; ledgern är oberoende forward-facit.\nAmber-tier: experimentell`}>
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
    // Klasserna styr BARA mobilkortet: `noquote` gömmer bokens "–"-platshållare
    // när priset saknas (sharpens rad står kvar), `noprice` gömmer hela
    // marknaden när varken bok eller sharp har något. Desktoptabellen behåller
    // "–" för kolumnjusteringen — se mobilblocket i App.css.
    const svsPair = Boolean(svs?.[k1] && svs?.[k2])
    const pinPair = Boolean(pin?.[k1] && pin?.[k2])
    return (
      <td className={`oc pair${svsPair || pinPair ? '' : ' noprice'}`}
        data-market={MARKET_LABEL[market]}>
        <div className={quoteClass(`o${svsPair ? '' : ' noquote'}`, svs)}>
          {svsPair ? <>{fmtL(svs.line)} · {svs[k1].toFixed(2)}{arrowAtLine(mvS1, svs.line)} / {svs[k2].toFixed(2)}{arrowAtLine(mvS2, svs.line)}{shiftBadge(mvS1, 'SvS')}{priceStamp(svs)}</> : '–'}
          {edgePill(v1?.book === 'svenskaspel' ? v1 : null)
            || edgePill(v2?.book === 'svenskaspel' ? v2 : null)}
        </div>
        {pinPair && <div className={quoteClass('p', pin)}>P {fmtL(pin.line)} · {pin[k1].toFixed(2)}{arrowAtLine(mvP1, pin.line)} / {pin[k2].toFixed(2)}{arrowAtLine(mvP2, pin.line)}{shiftBadge(mvP1, 'Pinnacle')}{priceStamp(pin)}</div>}
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
        <span className={`rekpill ${tier.cls}`}
          title={[
            `${tier.label} — matchens bästa värdeselektion (samma motor och nivåer som 💰-korten; ren visning, loggar inget).`,
            `Devigad Pinnacle: ${(v.fair * 100).toFixed(1)} % (fair ${(1 / v.fair).toFixed(2)}) — ${BOOK_NAME[v.book] || v.book} betalar ${v.odds.toFixed(2)} = +${(v.edge * 100).toFixed(1)} % övervärde.`,
            `Kvalitet (Kelly-andel): ${((v.q ?? 0) * 100).toFixed(1)} % — nivån sätts på kvalitet, inte rå edge.`,
            v.derived ? '° = sharp-priset är härlett ur handikapp — ta med en nypa salt.' : null,
          ].filter(Boolean).join('\n')}>
          {tier.short} +{(v.edge * 100).toFixed(1)}%{v.derived ? '°' : ''}
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
  // Matchen går att spela bara om en SPELBAR bok har ett pris. Pinnacle och
  // Smarkets räknas inte, och skälet är mätt och inte principiellt: på de
  // matcher där ingen mjuk bok prissatt tar Pinnacle ~11,5 % marginal på 1X2
  // mot ~5,6 % i övrigt (uppmätt 2026-08-14, 28 mot 132 matcher), medan den
  // uppmätta closing-driften är 0,3–0,6 pp. Värdemotorn kan dessutom per
  // konstruktion inte hitta edge mot Pinnacle, eftersom `fair` ÄR Pinnacles
  // devigade pris — edgen blir då minus marginalen.
  const hasBookPrice = (m) => PLAYABLE_BOOKS.some((bk) => {
    const per = m.odds?.[bk]
    if (!per) return false
    return ['1x2', 'ah', 'ou', 'cor'].some((mk) => {
      const o = per[mk]
      return o && ['1', 'X', '2', 'H', 'A', 'O', 'U'].some((k) => o[k])
    })
  })
  const noOddsCount = listed.filter((m) => !hasBookPrice(m)).length
  const matchRows = listed
    .filter((m) => !hideStarted || !m.start || new Date(m.start) >= new Date())
    .filter((m) => !hideNoOdds || hasBookPrice(m))
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
    /* Kolumnen "Andra ankaret" är borttagen 2026-08-12. Smarkets kopplades
       bort som andra ankare 2026-08-07 (56 030 priser på 1X2, NOLL på
       AH/Ö/U/hörnor — den kunde mäta 24 % av flaggorna), så kolumnen stod
       tom för allt nytt och visade bara historik. Mätningen i sig är orörd:
       `anchor2_*` skrivs vidare i oddset_value_log och spärren i
       ANCHOR_SOURCES står kvar — den är en säkerhetsspärr, inte en visning. */
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
        <td><span className={`rekpill ${tier.cls}`}>{tier.short}</span></td>
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
            return r ? <span className="rchip rankchip" title={r.title}>🏋️ {r.text}</span> : null
          })()}
          {m.research && <span className="rchip" title="Forskningsliga — odds och rörelser visas, men inga spelbara signaler.">🔬</span>}
          {m.data_conflict && (
            <span className="conflictchip"
              title={`${m.data_conflict.message}\n${(m.data_conflict.reasons || []).join('\n')}`}>
              ⚠️ datakrock · inga signaler
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
        {/* Verktygen bröts till 3–4 rader på mobil och sköt första matchen
            under vikningen. Färska odds, hämtningstid och "Bara signaler"
            (snabbkollen på telefon) står kvar; resten ligger bakom ⚙. På
            desktop finns plats för allt, så där visas raden som förut. */}
        <div className={`oddset-tools${showTools ? ' open' : ''}`}>
          <button className="lg toolstoggle mobile-only"
            onClick={() => setShowTools(!showTools)} aria-expanded={showTools}
            title="Modell, notiser, datakällor och sidoböcker">
            ⚙ {showTools ? 'Färre' : 'Verktyg'}
          </button>
          <button className={`${showModel ? 'lg model on' : 'lg model'} toolsmore`} onClick={toggleModel}
            title="XG-viktad Poisson-styrkefit per liga med DC-korrektion i prediktionen. Temperatur T valdes på historiska backtestmaterialet; prognosledgern är oberoende forward-facit. Amber-tier tills ledgern godkänt den.">
            🧪 Modell {showModel ? 'på' : 'av'}
          </button>
          <button className={onlySignals ? 'lg on' : 'lg'} onClick={toggleOnly}
            title="Visa bara matcher med någon signal: sharp-värde, steam, linjeflytt eller modellavvikelse. Snabbkollen på mobilen.">
            🎯 Bara signaler
          </button>
          <button className={`${showNotices ? 'lg on' : 'lg'} toolsmore`} onClick={() => setShowNotices(!showNotices)}
            title="Historik över triggade larm (värde ≥3 % / steam ≥5 pp) — även de som INTE pushades för att NTFY_TOPIC saknas.">
            🔔 {notices?.length || 0}
          </button>
          <button className={`${showSources ? 'lg on' : 'lg'} toolsmore`} onClick={() => setShowSources(!showSources)}
            aria-expanded={showSources}>
            Datakällor {sourceHealth.filter((h) => h.ok).length}/{sourceHealth.length}
          </button>
          <button className={`${showBooks ? 'lg on' : 'lg'} toolsmore`} onClick={() => setShowBooks(!showBooks)}
            aria-pressed={showBooks} title="Visa eller dölj spelbara sidoböcker. Ninja/Altenar visas för 1X2, Ö/U och hörnor; Smarkets visas alltid som sharp-ankare.">
            {showBooks ? '− Färre odds' : '+ Fler odds'}
          </button>
          <span className="hint odds-fetched">
            {data.last_run ? `hämtat ${new Date(data.last_run).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' })}` : 'inga odds ännu'}
          </span>
          <button onClick={refresh} disabled={busy}>{busy ? 'Hämtar…' : '↻ Färska odds'}</button>
        </div>
      </div>
      {/* Antalen står PÅ flikarna i stället för bara i räknarraden under.
          Raden upprepade tabbarnas namn och kostade en hel rad på mobil, där
          den dessutom låg först. Informationen är alltid synlig — nu i etiketten
          — och raden står kvar på desktop för live-signalernas "att granska". */}
      <div className="oddset-tabs" role="tablist" aria-label="Oddset-vy">
        {[['matcher', '📋 Matcher', null], ['live', '⚡ Live', liveRadar?.matches?.length ?? 0],
          ['varde', '💰 Värdespel', signals.length], ['rorelser', '📈 Rörelser', movers.length],
          ['styrka', '🏋️ Lagstyrka', null]].map(([t, label, n]) => (
          <button key={t} className={`oddset-tab ${oddsetTab === t ? 'active' : ''}`}
            role="tab" aria-selected={oddsetTab === t}
            onClick={() => pickTab(t)}>
            {label}{n != null ? <span className="tabn"> {n}</span> : ''}
          </button>
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
            <button className={hideNoOdds ? 'lg on' : 'lg'}
              onClick={toggleNoOdds} aria-pressed={hideNoOdds}
              disabled={noOddsCount === 0}
              title={'Matcher som ingen spelbar bok (SvS, Expekt, Ninja/Altenar) har prissatt — mest småskaliga träningsmatcher, plus omgångar där boken ännu inte öppnat.\nDe har Pinnacle-pris, men där tas ungefär dubbel marginal på just dessa matcher (~11,5 % mot ~5,6 %), så priset är sällan spelbart i praktiken.\nDe samlas in och spåras precis som förut — filtret är bara en vy.'}>
              {hideNoOdds ? 'Visa utan odds' : 'Dölj utan odds'}
              {noOddsCount > 0 ? ` (${noOddsCount})` : ''}
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
                detail={hideNoOdds && noOddsCount > 0 && listed.length === noOddsCount
                  ? 'Ingen match i urvalet har ett pris hos en spelbar bok. Visa utan odds för att se dem med enbart Pinnacles pris.'
                  : hideStarted && startedCount > 0
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
