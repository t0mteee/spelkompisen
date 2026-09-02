// Topptipset Dagens/Stryk/Extra är samma spel — åtta matcher, samma vinstplan,
// samma benchmarkfamilj — bara olika omgångsserier under olika namn hos
// Svenska Spel. FAMILY samlar dem i VISNINGEN; produktslug, settlementidentitet
// och config_key är oförändrade. Ren logik utan React så att lib/labels.js och
// node --test når den. Bruten ur App.jsx 2026-09-02.
export const VARIANT = {
  topptipset: 'Dagens', topptipsetstryk: 'Stryk', topptipsetextra: 'Extra',
}
export const FAMILY = (p) => (String(p || '').startsWith('topptipset') ? 'topptipset' : p)
