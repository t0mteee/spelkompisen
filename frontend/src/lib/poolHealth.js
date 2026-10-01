// Poolhälsans issues (/api/health → pools.issues) för Idag. Ren logik utan
// React. Tre slag: fel (insamlingen behöver tillsyn NU), varningar som gäller
// nu (för lite färsk Pinnacle nära spelstopp, stoppat shadowspår) och
// historiska bortfall (`scope: 'history'`: frysningar som missades för redan
// stängda omgångar). Före 2026-09-24 var ALLA varningar historiska och visades
// under "dagens insamling fungerar" — en aktuell varning får aldrig visas där.
//
// `product: 'server'` är DRIFTEN, inte poolunderlaget: databasbackupen och
// driftvaktens fynd (backend/app/vakt.py, docs/vakt.md). De hålls utanför
// poolgrupperna och visas under "Drift att se över". Vaktens info-noteringar
// ligger aldrig bland issues (allt som inte är 'warning' räknas som fel) utan
// i /api/health → vakt.notes.
const KIND_LABEL = {
  sharp_link_coverage: 'för lite färsk Pinnacle',
  strength_shadow_stopped: 'styrkeshadowen står still',
  strength_shadow_unreadable: 'styrkeshadowen kunde inte läsas',
  backup_missing: 'databasbackup saknas',
  backup_unreadable: 'backupstatus oläslig',
  backup_stale: 'databasbackupen är gammal',
  backup_not_pushed: 'backupen har inte nått GitHub',
  // Driftvakten
  kalla_nere: 'datakälla svarar inte',
  natverk_nere: 'serverns nät/DNS fallerar',
  kalltest_stale: 'källprovet har inte körts',
  jobb_ej_laddat: 'jobb är inte laddat',
  jobb_nere: 'tjänst ligger nere',
  jobb_exit: 'jobb avslutades med fel',
  jobb_okant: 'okänt jobb',
  insamling_star_still: 'insamlingen står still',
  backend_5xx: 'serverfel i API:t',
  backend_traceback: 'undantag i backend',
  backend_kor_gammal_kod: 'backend kör gammal kod',
  appen_ej_byggd: 'appen är inte ombyggd',
  main_ej_utcheckad: 'driftkopian ligger efter GitHub',
  opushade_commits: 'opushade commits i driftkopian',
  ocommittat_i_driftkopian: 'ocommittade ändringar i driftkopian',
  tester_roda: 'testsviten är röd',
  disk_lag: 'lite diskutrymme',
  vakt_check_failed: 'en vaktkontroll kraschade',
  vakt_stale: 'driftvakten har inte körts',
  vakt_missing: 'driftvakten saknas',
  vakt_unreadable: 'driftvaktens status oläslig',
  test_status_andrad: 'test bytte status',
  avlasningspunkt_nadd: 'avläsningspunkt nådd',
}

export const SERVER_PRODUCT = 'server'

export const kindLabel = (kind) => KIND_LABEL[kind] || kind

export function splitPoolIssues(issues) {
  const all = (issues || []).filter((issue) => issue.product !== SERVER_PRODUCT)
  const warnings = all.filter((issue) => issue.level === 'warning')
  return {
    errors: all.filter((issue) => issue.level !== 'warning'),
    current: warnings.filter((issue) => issue.scope !== 'history'),
    history: warnings.filter((issue) => issue.scope === 'history'),
  }
}

export const poolIssueLabel = (issue) =>
  `${issue.product}${issue.draw_number ? ` omg ${issue.draw_number}` : ''}`

export function poolNoticeSummary(current) {
  const kinds = [...new Set((current || []).map((issue) => kindLabel(issue.kind)))]
  return kinds.length ? `Poolunderlag att se över: ${kinds.join(' · ')}` : null
}

// Driften: samma fel/varning-delning som poolen, men egen rubrik.
export function splitServerIssues(issues) {
  const mine = (issues || []).filter((issue) => issue.product === SERVER_PRODUCT)
  return {
    errors: mine.filter((issue) => issue.level !== 'warning'),
    warnings: mine.filter((issue) => issue.level === 'warning'),
  }
}

// "sedan 25/9 12:43" i svensk tid; tom sträng utan giltig tid.
export function sinceText(iso) {
  const d = iso ? new Date(iso) : null
  if (!d || Number.isNaN(d.getTime())) return ''
  const text = d.toLocaleString('sv-SE', {
    timeZone: 'Europe/Stockholm', day: 'numeric', month: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
  return `sedan ${text}`
}

// En rad per driftfynd: meddelandet plus när det först sågs. Ett fynd som
// vakten bara behåller (backendskov i 24 h, kraschad kontroll) märks.
export function serverIssueText(issue) {
  const since = sinceText(issue.since)
  const parts = [issue.message, since, issue.held ? 'senaste kända läge' : '']
  return parts.filter(Boolean).join(' · ')
}

export function serverNoticeSummary(warnings) {
  const kinds = [...new Set((warnings || []).map((issue) => kindLabel(issue.kind)))]
  return kinds.length ? `Drift att se över: ${kinds.join(' · ')}` : null
}

export function vaktNotesSummary(vakt) {
  const notes = vakt?.notes || []
  if (!notes.length) return null
  const kinds = [...new Set(notes.map((note) => kindLabel(note.kind)))]
  return `Vakten noterade senaste 7 dygnen: ${kinds.join(' · ')}`
}
