import unittest

from scripts import backfill_xg_ligor


def _event(event_id=1, home="Djurgårdens IF", away="Västerås SK",
           hg=6, ag=0, timestamp=1785780000):
    return {
        "id": event_id, "startTimestamp": timestamp,
        "homeTeam": {"name": home}, "awayTeam": {"name": away},
        "homeScore": {"normaltime": hg},
        "awayScore": {"normaltime": ag},
    }


class TargetIdentityTests(unittest.TestCase):
    def setUp(self):
        date, *_ = backfill_xg_ligor._event_identity(_event())
        self.missing = [{
            "league": "allsvenskan", "date": date,
            "home": "djurgarden", "away": "vasteras", "hg": 6, "ag": 0,
        }]

    def test_verified_alias_date_and_score_link_exactly(self):
        target = backfill_xg_ligor._target(
            _event(), self.missing,
            {"djurgardens": "djurgarden", "vasteras": "vasteras"})
        self.assertEqual(self.missing[0], target)

    def test_wrong_score_or_team_falls_closed(self):
        aliases = {"djurgardens": "djurgarden", "vasteras": "vasteras"}
        self.assertIsNone(backfill_xg_ligor._target(
            _event(hg=5), self.missing, aliases))
        self.assertIsNone(backfill_xg_ligor._target(
            _event(away="Västerås U21"), self.missing, aliases))

    def test_ambiguous_target_falls_closed(self):
        aliases = {"djurgardens": "djurgarden", "vasteras": "vasteras"}
        self.assertIsNone(backfill_xg_ligor._target(
            _event(), self.missing * 2, aliases))

    def test_exact_canonical_name_beats_stale_alias(self):
        date, *_ = backfill_xg_ligor._event_identity(_event(
            home="IFK Göteborg", away="Malmö FF", hg=2, ag=1))
        row = {
            "league": "allsvenskan", "date": date,
            "home": "ifk goteborg", "away": "malmo", "hg": 2, "ag": 1,
        }

        target = backfill_xg_ligor._target(
            _event(home="IFK Göteborg", away="Malmö FF", hg=2, ag=1),
            [row], {"ifk goteborg": "goteborg"})

        self.assertEqual(row, target)


if __name__ == "__main__":
    unittest.main()
