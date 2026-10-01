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
  const alt = isDecision(item) ? (item.alternativ || [])[Number(svar.val)] : null
  const val = isDecision(item)
    ? (alt ? alt.text : svar.val)
    : ({ kor_nu: 'Kör nu', nej: 'Nej' }[svar.val] || svar.val)
  return [tid, val].filter(Boolean).join(' · ')
}
