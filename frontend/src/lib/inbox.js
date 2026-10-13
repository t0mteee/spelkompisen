// spel-ai-kompisens inkorg (/api/spelai/inbox) i Spelkompisen: beslut och
// förslag som väntar på Saman. Ren logik utan React så `node --test` når den.
// Svaren registreras BARA här (betrodd kod, docs/spel-ai-kompisen-design.md
// 5.5); agentens app visar listan men länkar hit för svaret.

export const KIND_LABEL = {
  beslut: 'Beslut',
  forslag_forbattring: 'Förbättring',
  forslag_spelrad: 'Spelråd',
}

export const kindLabel = (typ) => KIND_LABEL[typ] || typ

// Driftsättning (2026-10-13): ett beslut med fasta alternativ 0 = Godkänn,
// 1 = Avvisa och begäran i `driftsattning` (commit, steg, resultat).
export const isDeploy = (item) => Boolean(item?.driftsattning)
export const itemLabel = (item) => (isDeploy(item) ? 'Driftsättning' : kindLabel(item?.typ))

const DEPLOY_STATUS = {
  pagar: 'Körs nu',
  gron: 'Klar, grön hälsa',
  gron_utan_push: 'Klar, grön hälsa, men pushen misslyckades',
  aterstalld: 'Röd hälsa: förra bygget återställt',
  rod: 'Röd hälsa, även efter återställning',
  avbruten: 'Avbruten',
}

// "Klar, grön hälsa" / "Avbruten: <orsak>" — null innan den körts.
export function deployResultText(item) {
  const res = item?.driftsattning?.resultat
  if (!res) return null
  const text = DEPLOY_STATUS[res.status] || res.status
  return res.orsak ? `${text}: ${res.orsak}` : text
}

export const isDecision = (item) => item?.typ === 'beslut'

export function splitInbox(poster) {
  const all = poster || []
  return {
    beslut: all.filter((p) => p.status === 'vantar' && isDecision(p)),
    forslag: all.filter((p) => p.status === 'vantar' && !isDecision(p)),
    besvarade: all.filter((p) => p.status !== 'vantar'),
  }
}

export function recommendedIndex(item) {
  const index = (item?.alternativ || []).findIndex((alt) => alt?.rekommenderas)
  return index >= 0 ? index : null
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`

// "3 beslut och 2 förslag väntar" — null när inget väntar.
export function inboxSummary(data) {
  if (!data?.tabeller) return null
  const { beslut, forslag } = splitInbox(data.poster)
  if (!beslut.length && !forslag.length) return null
  const parts = []
  if (beslut.length) parts.push(plural(beslut.length, 'beslut', 'beslut'))
  if (forslag.length) parts.push(plural(forslag.length, 'förslag', 'förslag'))
  return `${parts.join(' och ')} väntar`
}

const TIME = { timeZone: 'Europe/Stockholm', weekday: 'short', day: 'numeric',
  month: 'numeric', hour: '2-digit', minute: '2-digit' }

export function deadlineText(iso) {
  const d = iso ? new Date(iso) : null
  if (!d || Number.isNaN(d.getTime())) return ''
  return `senast ${d.toLocaleString('sv-SE', TIME)}`
}

// Vad svaret blev, i klartext.
export function answerText(item) {
  const svar = item?.svar
  if (item?.status === 'utgangen' && !svar) return 'Sista tiden passerade utan svar'
  if (!svar) return ''
  const when = new Date(svar.tid)
  const tid = Number.isNaN(when.getTime()) ? '' : when.toLocaleString('sv-SE', TIME)
  if (isDeploy(item)) {
    const valt = svar.val === '0' ? 'Godkänd' : svar.val === '1' ? 'Avvisad' : svar.val
    const tidText = Number.isNaN(when.getTime()) ? '' : when.toLocaleString('sv-SE', TIME)
    return [tidText, valt, deployResultText(item)].filter(Boolean).join(' · ')
  }
  const alt = isDecision(item) ? (item.alternativ || [])[Number(svar.val)] : null
  const val = isDecision(item)
    ? (alt ? alt.text : svar.val)
    : ({ kor_nu: 'Kör nu', nej: 'Nej' }[svar.val] || svar.val)
  return [tid, val].filter(Boolean).join(' · ')
}
