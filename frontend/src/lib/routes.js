// Hash-rutter: EN källa till vilken vy, underflik och detalj som är öppen.
// Utan hash startar appen alltid i Idag (den lätta översikten). En hash är
// ett uttryckligt direktlänkskontrakt: `#/kuponger/12` öppnar din kupong 12,
// `#/tester/ph5/stryktipset/4969/h3/<nyckel>` exakt den testkupongen.
// Ren logik utan React så `node --test` når den.
const HIST_TABS = new Set(['kuponger', 'tester', 'facit'])

export function parseRoute(hash) {
  const raw = String(hash || '').replace(/^#\/?/, '').replace(/\/+$/, '')
  if (!raw) return { view: 'idag' }
  const parts = raw.split('/').map((part) => {
    try { return decodeURIComponent(part) } catch { return part }
  })
  const [head, ...rest] = parts
  if (head === 'kuponger') {
    const id = rest[0] != null && rest[0] !== '' ? Number(rest[0]) : null
    return { view: 'historik', tab: 'kuponger', coupon: Number.isFinite(id) ? id : null }
  }
  if (head === 'tester') {
    const [test, product, draw, horizon, config] = rest
    const open = product && draw && horizon && config
      ? { product, draw_number: Number(draw), horizon, config_key: config } : null
    return { view: 'historik', tab: 'tester', test: test || null, open }
  }
  if (head === 'facit') return { view: 'historik', tab: 'facit', product: rest[0] || null }
  if (head === 'historik') return { view: 'historik', tab: HIST_TABS.has(rest[0]) ? rest[0] : 'kuponger' }
  if (head === 'pool' || head === 'labb') return { view: head }
  if (head === 'oddset') return { view: 'oddset', focus: rest[0] || null }
  return { view: 'idag' }
}

const enc = (value) => encodeURIComponent(String(value))

export function formatRoute(route) {
  if (!route || route.view === 'idag' || !route.view) return ''
  if (route.view === 'historik') {
    const tab = route.tab || 'kuponger'
    if (tab === 'kuponger') return route.coupon != null ? `#/kuponger/${enc(route.coupon)}` : '#/kuponger'
    if (tab === 'tester') {
      if (!route.test) return '#/tester'
      const o = route.open
      if (o?.product && o.draw_number != null && o.horizon && o.config_key) {
        return `#/tester/${enc(route.test)}/${enc(o.product)}/${enc(o.draw_number)}/${enc(o.horizon)}/${enc(o.config_key)}`
      }
      return `#/tester/${enc(route.test)}`
    }
    return route.product ? `#/facit/${enc(route.product)}` : '#/facit'
  }
  if (route.view === 'oddset') return route.focus ? `#/oddset/${enc(route.focus)}` : '#/oddset'
  return `#/${route.view}`
}

export const sameRoute = (a, b) => formatRoute(a) === formatRoute(b)

// Föräldern till en detalj: dit "stäng" och tillbaka-knappen leder när det
// inte finns någon egen historikpost att backa till.
export function parentRoute(route) {
  if (route?.view !== 'historik') return { view: 'idag' }
  if (route.tab === 'kuponger' && route.coupon != null) return { view: 'historik', tab: 'kuponger' }
  if (route.tab === 'tester' && route.open) return { view: 'historik', tab: 'tester', test: route.test }
  if (route.tab === 'tester' && route.test) return { view: 'historik', tab: 'tester' }
  return { view: 'historik', tab: route.tab || 'kuponger' }
}
