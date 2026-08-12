/* Spelläge för en POOLOMGÅNG — inte för kupongen som ligger bredvid.

   Spelvärdet är `payout_ratio + jackpot / omsättning`, där payout_ratio är en
   KONSTANT per produkt (Stryktipset 0,598 · Europatipset 0,637 · Topptipset
   0,700 — uppmätt, se _payout_ratio i backend). Alla tre ligger under
   tunt-tröskeln 0,80, så utan jackpot kan utfallet inte bli något annat än
   "avstå". Det är aritmetik, inte en bedömning av raderna, och en etikett som
   bara kan anta ett värde bär noll information.

   Därför returnerar modulen även AVSTÅNDET till nästa tröskel: hur mycket
   jackpot som saknas. Eftersom sv = ratio + jackpot/bas höjer en extra krona
   jackpot spelvärdet med 1/bas, vilket ger saknad jackpot = (tröskel − sv) × bas.
   Basen måste vara SAMMA omsättning som spelvärdet räknades på, annars pekar
   avståndet på fel omgång.

   Garantier (t.ex. ensamvinnargaranti) ingår medvetet inte — villkoren är
   overifierade mot SvS regler, se kommentaren i backend/app/main.py. */

export const TUNT = 0.8
export const SPELA = 1.0

// Kompakt belopp för trånga chip (.playrec har white-space: nowrap, så
// "4 958 434 kr" spränger raden på mobil medan "5,0 Mkr" ryms).
export const kompaktKr = (v) => {
  const n = Math.max(0, Math.round(v || 0))
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.', ',') + ' Mkr'
  if (n >= 1e4) return Math.round(n / 1e3).toLocaleString('sv-SE') + ' tkr'
  return n.toLocaleString('sv-SE') + ' kr'
}

export function projectionBasisText(basis) {
  if (!basis) return 'median av tidigare omgångar'
  if (typeof basis === 'string') return basis
  const n = basis.n || 'de'
  if (basis.mode === 'weekday') {
    const days = ['mån', 'tis', 'ons', 'tors', 'fre', 'lör', 'sön']
    return `median av ${n} senaste omgångarna med samma spelstoppsveckodag (${days[basis.weekday] ?? '?'})`
  }
  return `median av senaste ${n} omgångarna oavsett veckodag`
}

export function playRecommendation(payouts) {
  const p = payouts || {}
  // Samma val som spelvärdet: prognosen används bara när den är högre än
  // dagens omsättning, annars är det live-omsättningen som gäller.
  const proj = p.projected_turnover > p.turnover
  const sv = proj ? (p.spelvarde_proj || 0)
    : (p.spelvarde || p.payout_ratio || 0)
  const bas = (proj ? p.projected_turnover : p.turnover) || 0
  const level = sv >= SPELA ? 'go' : sv >= TUNT ? 'thin' : 'skip'
  const nasta = level === 'go' ? null : level === 'thin' ? SPELA : TUNT
  const gap = nasta != null && bas > 0 && sv < nasta ? (nasta - sv) * bas : null
  return { sv, bas, proj, level, gap }
}
