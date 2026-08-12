"""Två saker som ALDRIG spelas, och som båda såg ut som något annat.

1. INSTÄLLD OMGÅNG. SvS sätter `cancelled: true` på RESULTATET men lämnar
   omgångens egen `drawState` på "Finalized", varje event utan utfall och en
   distribution med noll vinnare och 0,00 kr. Utan draw_state="Cancelled"
   lagras den som en vanlig avgjord omgång vars utfall råkar saknas, och
   systemledgern dömer den "utfall saknas för minst en match". Uppmätt
   2026-08-12: 56 av 8 324 omgångar, alla Topptipset, maj 2024–augusti 2026.

2. UPPSKJUTEN MATCH. statusId 23 låg i den GISSADE serien 20–25 för
   övertidsperioder. Uppmätt 2026-08-12 på Topptipset 4261
   (D. Tolima–Independiente) betyder 23 "Uppskjuten", alltså raka motsatsen:
   matchen spelas inte alls. Med koden i övertidsserien blev `regulation_over`
   sann och kupongen redovisade matchen som avgjord fast det inte fanns något
   resultat att läsa tecknet ur.
"""
import unittest

from app import pool_played, pool_settlement


UPPSKJUTEN = {"statusId": 23, "status": "Uppskjuten"}
OVERTID = {"statusId": 20, "status": "Första övertidsperioden"}
SLUT = {"statusId": 31, "status": "Slut"}
EJ_STARTAD = {"statusId": 0, "status": "Inte startat"}


class UppskjutenMatchTests(unittest.TestCase):
    def test_uppskjuten_ar_inte_forlangning(self):
        self.assertTrue(pool_played.match_postponed(UPPSKJUTEN))
        self.assertFalse(pool_played.in_extra_time(UPPSKJUTEN))

    def test_uppskjuten_match_ar_inte_avgjord(self):
        # Kärnan i felet: utan detta stod matchen som klar utan resultat.
        self.assertFalse(pool_played.regulation_over(UPPSKJUTEN))
        self.assertFalse(pool_played.match_finished(UPPSKJUTEN))

    def test_observerad_overtidskod_galler_fortfarande(self):
        self.assertTrue(pool_played.in_extra_time(OVERTID))
        self.assertTrue(pool_played.regulation_over(OVERTID))
        self.assertFalse(pool_played.match_postponed(OVERTID))

    def test_okand_overtidskod_fangas_av_orden(self):
        # Serien 20–25 är borta; klartexten är skyddsnätet.
        okand = {"statusId": 97, "status": "Andra övertidsperioden"}
        self.assertTrue(pool_played.in_extra_time(okand))

    def test_slut_och_ej_startad_ar_oforandrade(self):
        self.assertTrue(pool_played.match_finished(SLUT))
        self.assertFalse(pool_played.match_postponed(SLUT))
        self.assertFalse(pool_played.regulation_over(EJ_STARTAD))

    def test_uppskjuten_haller_inte_tillbaka_omprovningen(self):
        # matchStart flyttas ofta veckor fram vid uppskjutning; utan undantaget
        # skulle omprövningen vänta på ett datum som aldrig avgör omgången.
        raw = {"drawEvents": [
            {"eventNumber": 1, "match": {**SLUT, "matchStart": "2026-08-11T20:00:00+02:00"}},
            {"eventNumber": 2, "match": {**UPPSKJUTEN, "matchStart": "2026-09-20T20:00:00+02:00"}},
        ]}
        naar = pool_settlement._retry_after(raw)

        self.assertLess(naar, "2026-08-13")


class InstalldOmgangTests(unittest.TestCase):
    def test_resultatets_cancelled_vinner_over_drawstate(self):
        # Payloadformen är den uppmätta: drawState "Finalized", tomma utfall,
        # en nivå med noll vinnare.
        self.assertEqual(pool_settlement.CANCELLED_STATE, "Cancelled")
        self.assertNotEqual(pool_settlement.CANCELLED_STATE, "Finalized")


if __name__ == "__main__":
    unittest.main()
