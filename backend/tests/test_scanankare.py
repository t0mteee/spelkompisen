"""Scanankaret får aldrig tappa en öppen omgång.

Topptipset saknar listnings-API och hittas genom nummerscanning: `_scan_draws`
börjar `back` nummer före ankaret och går framåt. Hintet är högsta sedda
omgång och går bara framåt — så när Svenska Spel publicerar långt i förväg
växer avståndet till lägsta ännu ÖPPNA omgång, och de öppna faller ur fönstret.

Det har hänt två gånger:
  2026-07-24  back=4 → 4227/4228 försvann ur omgångsväljaren. Fix: back=8.
  2026-08-14  hint 4275 mot öppen 4264 (elva nummer). Omgång 4264–4266 blev
              osynliga för varvet: inga snapshots och NOLL PH3-frysningar,
              medan appen visade dem som vanligt. h3 för 4264/4265 gick
              förlorad — en point-in-time-frysning kan inte bakfyllas.

Att höja `back` är att gissa om publiceringstakten, och gissningen har slagit
fel båda gångerna. Golvet mäts därför i stället: en omgång vi själva sett som
öppen får aldrig hamna under scanfönstret.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app.storage import Storage


class ScanAnkareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.addCleanup(self.store.close)

    def _draw(self, nummer, state="Open", product="topptipset", close=None):
        # Default: stänger om ett dygn, alltså rimligen fortfarande öppen.
        if close is None:
            close = (dt.datetime.now(dt.timezone.utc)
                     + dt.timedelta(hours=24)).isoformat()
        self.store.conn.execute(
            "INSERT OR REPLACE INTO draws (product, draw_number, state, "
            "reg_close_time) VALUES (?,?,?,?)", (product, nummer, state, close))
        self.store.conn.commit()

    def _gammal(self, nummer, timmar=48, product="topptipset"):
        """Spökrad: står `Open` men spelstoppet passerade för länge sedan."""
        self._draw(nummer, product=product, close=(
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=timmar)).isoformat())

    def _hint(self, nummer, product="topptipset"):
        self.store.meta_set(f"latest_{product}", str(nummer))

    def test_ankaret_dras_ner_till_lagsta_oppna_omgang(self):
        self._hint(4275)
        self._draw(4264)
        self._draw(4275)

        # Den skarpa situationen 2026-08-14: utan detta blev ankaret 4275 och
        # _scan_draws började på 4267 — elva nummer över 4264.
        self.assertEqual(4264, self.store.seed_hint("topptipset"))

    def test_avgjord_omgang_drar_inte_ner_ankaret(self):
        self._hint(4275)
        self._draw(4264, state="Finalized")
        self._draw(4275)

        # Självläkningen: så fort omgången hämtats och visat sig avgjord
        # slutar den hålla fönstret öppet.
        self.assertEqual(4275, self.store.seed_hint("topptipset"))

    def test_utan_kanda_oppna_omgangar_galler_hintet(self):
        self._hint(4275)

        self.assertEqual(4275, self.store.seed_hint("topptipset"))

    def test_en_fastnad_omgang_kan_inte_dra_ankaret_hur_langt_som_helst(self):
        self._hint(4275)
        self._draw(3000)   # fastnad `Open` med spelstopp i FRAMTIDEN

        self.assertEqual(4275 - Storage.SCAN_ANCHOR_MAX_BACK,
                         self.store.seed_hint("topptipset"))

    def test_spokrad_med_passerat_spelstopp_pinnar_inte_ankaret(self):
        # 61 sådana rader fanns i Topptipset 2026-08-14. En omgång vars
        # spelstopp passerade för 48 timmar sedan ÄR inte öppen, oavsett vad
        # raden säger — annars sitter ankaret på sin bound för alltid.
        self._hint(4275)
        self._gammal(4100)
        self._draw(4275)

        self.assertEqual(4275, self.store.seed_hint("topptipset"))

    def test_nyss_stangd_omgang_haller_fonstret_oppet(self):
        # Settlementet släpar; en omgång som stängde nyss ska fortfarande gå
        # att hitta så att tillstånd och facit hinner uppdateras.
        self._hint(4275)
        self._gammal(4264, timmar=2)
        self._draw(4275)

        self.assertEqual(4264, self.store.seed_hint("topptipset"))

    def test_annan_produkts_oppna_omgangar_paverkar_inte(self):
        self._hint(4275)
        self._draw(900, product="topptipsetstryk")

        self.assertEqual(4275, self.store.seed_hint("topptipset"))

    def test_hintet_backar_aldrig_av_ett_kort_scanresultat(self):
        # store_seed MÅSTE jämföra mot det råa hintet. Läser den scanankaret
        # skriver ett kort scanresultat ner hintet permanent, och nästa varv
        # blir ännu blindare — precis felet fixen skulle undvika.
        self._hint(4275)
        self._draw(4264)
        self.assertEqual(4264, self.store.seed_hint("topptipset"))

        self.store.store_seed("topptipset", [{"draw_number": 4270}])

        self.assertEqual(4275, self.store.stored_seed("topptipset"))

    def test_nytt_hogsta_nummer_flyttar_fram_hintet(self):
        self._hint(4275)
        self.store.store_seed("topptipset", [{"draw_number": 4280}])

        self.assertEqual(4280, self.store.stored_seed("topptipset"))

    def test_listningen_lyfter_bort_spokrader_sa_golvet_laker(self):
        # Utan detta läker golvet ALDRIG: `save_snapshot*` skriver bara öppna
        # omgångar, så en omgång som stängde utanför fönstret behåller `Open`
        # och pinnar ankaret för alltid. Uppmätt på Topptipset 4262/4263, som
        # satt kvar som öppna 45 respektive 19 timmar efter spelstopp.
        self._hint(4275)
        self._draw(4262)
        self._draw(4275)
        self.assertEqual(4262, self.store.seed_hint("topptipset"))

        self.store.sync_draw_states("topptipset", [
            {"draw_number": 4262, "state": "Finalized",
             "reg_close_time": "2026-08-12T20:59:00+02:00"},
            {"draw_number": 4275, "state": "Open",
             "reg_close_time": "2026-08-15T00:29:00+02:00"},
        ])

        self.assertEqual(4275, self.store.seed_hint("topptipset"))

    def test_synk_skriver_aldrig_over_en_kand_stangningstid_med_none(self):
        self._draw(4275)
        self.store.sync_draw_states(
            "topptipset", [{"draw_number": 4275, "state": "Finalized"}])
        rad = self.store.conn.execute(
            "SELECT state, reg_close_time FROM draws WHERE product=? AND draw_number=?",
            ("topptipset", 4275)).fetchone()

        self.assertEqual("Finalized", rad[0])
        self.assertIsNotNone(rad[1])


if __name__ == "__main__":
    unittest.main()
