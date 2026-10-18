// Byggarens synliga val (beslut koordinatorn-2026-10-18-stada-byggaren-2, val 0):
// Värderader (förval), Reducerat och Matematiskt. Färgreducering, Egen
// reducering och Svenska Spels R-system bär `hidden` i App.jsx; radprofilerna
// Träffsäkrare/Radform v1/Täckningstest v1 och Två kompletterande kuponger
// erbjuds inte längre. Backend bygger dem fortfarande, och historiska kuponger
// behåller sina etiketter. Värdevikten är låst och reglaget gömt.
export const BUILDER_VALUE_WEIGHT = 50

export function visibleSystemTypes(types) {
  return types.filter((type) => !type.hidden)
}

// Ett sparat dolt val (eller ett okänt id) börjar om på första synliga typen.
export function restoredSysType(savedId, types) {
  const visible = visibleSystemTypes(types)
  return visible.some((type) => type.id === savedId) ? savedId : visible[0]?.id
}
