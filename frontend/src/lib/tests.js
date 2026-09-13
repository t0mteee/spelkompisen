// Testkatalogen (Historik → Tester): statusfärg och vad som är en NYHET på
// Idag. Ren logik utan React. Statusorden kommer från backend (samma trappa
// som cli.py gater); här bara presentation.
export const STATUS_TONE = {
  samlar: 'muted',
  'avslutsgräns nådd': 'amber',
  'underlag klart': 'amber',
  'ingen utmanare': 'amber',
  kandidat: 'amber',
  promoterbar: 'green',
  'granskad: stöd': 'green',
  'granskad: ej stöd': 'red',
  infört: 'green',
  avslutad: 'grey',
  fel: 'red',
}
export const statusTone = (status) => STATUS_TONE[status] || 'muted'

// Idag visar bara tester där något behöver ses: ett beslut väntar (underlag
// klart/promoterbar) eller nyss fattats. Samlande och avslutade är inga nyheter.
export const NEWS_STATUSES = new Set(['underlag klart', 'promoterbar', 'ingen utmanare',
  'granskad: stöd', 'granskad: ej stöd', 'avslutsgräns nådd', 'fel'])
export function newsworthy(tests, { recentDays = 14, now = new Date() } = {}) {
  return (tests || []).filter((test) => {
    if (test.archived) return false
    if (test.status === 'granskad: ej stöd' || test.status === 'granskad: stöd') {
      const when = test.decision?.date ? new Date(test.decision.date) : null
      return when ? (now.getTime() - when.getTime()) <= recentDays * 86400000 : false
    }
    return NEWS_STATUSES.has(test.status)
  })
}
export const progressText = (test) => (test?.progress
  ? `${test.progress.n}/${test.progress.krav} · ${test.progress.namn}` : '–')
