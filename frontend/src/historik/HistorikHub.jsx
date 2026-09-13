// Historik = 100 % pool, i tre underflikar sedan 2026-09-13: Mina kuponger
// (det du spelat), Tester (experimenten) och Facit & prognos (omgångsfakta).
// Rutten (lib/routes.js) säger vilken flik och detalj som är öppen.
import { MinaKuponger } from './MinaKuponger.jsx'
import { Tester } from './Tester.jsx'
import { HistorikV3 } from './HistorikV3.jsx'

const TABS = [
  { id: 'kuponger', label: '🎟️ Mina kuponger' },
  { id: 'tester', label: '🧪 Tester' },
  { id: 'facit', label: '🗄 Facit & prognos' },
]

export function HistorikHub({ route, navigate }) {
  const tab = route.tab || 'kuponger'
  return (
    <div className="v3hist">
      <nav className="v3subnav v3histtabs" aria-label="Historik">
        {TABS.map((item) => (
          <button key={item.id} className={tab === item.id ? 'on' : ''}
            onClick={() => navigate({ view: 'historik', tab: item.id })}>{item.label}</button>
        ))}
      </nav>
      {tab === 'kuponger' && (
        <MinaKuponger openCoupon={route.coupon ?? null}
          onOpenCoupon={(id) => navigate({ view: 'historik', tab: 'kuponger', coupon: id })}
          onCloseCoupon={() => navigate({ view: 'historik', tab: 'kuponger' }, { back: true })} />
      )}
      {tab === 'tester' && (
        <Tester test={route.test || null} open={route.open || null}
          onOpenTest={(id) => navigate({ view: 'historik', tab: 'tester', test: id })}
          onOpenCoupon={(test) => navigate({ view: 'historik', tab: 'tester', test: route.test,
            open: { product: test.product, draw_number: test.draw_number,
              horizon: test.horizon, config_key: test.config_key } })}
          onCloseCoupon={() => navigate({ view: 'historik', tab: 'tester', test: route.test }, { back: true })} />
      )}
      {tab === 'facit' && (
        <HistorikV3 key={route.product || 'alla'} initialProduct={route.product || null}
          onChooseProduct={(product) => navigate({ view: 'historik', tab: 'facit', product }, { replace: true })} />
      )}
    </div>
  )
}
