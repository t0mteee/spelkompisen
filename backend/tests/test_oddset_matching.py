import unittest

from app import oddset
from app.odds_provider import _hours_apart


class EventMatchingTests(unittest.TestCase):
    def test_timezone_offsets_represent_the_same_kickoff(self) -> None:
        local = "2026-07-16T20:00:00+02:00"
        utc = "2026-07-16T18:00:00Z"

        self.assertEqual(0.0, _hours_apart(local, utc))
        self.assertEqual(
            1.0,
            oddset._match_score(
                "Hammarby IF", "Malmö FF", local,
                "Hammarby", "Malmo", utc,
            ),
        )

    def test_same_teams_outside_two_hour_window_are_rejected(self) -> None:
        score = oddset._match_score(
            "Hammarby", "Malmö", "2026-07-16T18:00:00Z",
            "Hammarby IF", "Malmo FF", "2026-07-16T20:00:01Z",
        )

        self.assertEqual(0.0, score)

    def test_resolver_uses_kickoff_to_separate_repeated_fixture(self) -> None:
        candidates = [
            {"id": "wrong", "home": "Hammarby", "away": "Malmö",
             "start": "2026-08-02T18:00:00Z"},
            {"id": "right", "home": "Hammarby IF", "away": "Malmo FF",
             "start": "2026-07-16T18:30:00Z"},
        ]

        match = oddset._resolve(
            candidates, "Hammarby", "Malmö", "2026-07-16T20:00:00+02:00")

        self.assertIsNotNone(match)
        self.assertEqual("right", match["id"])


if __name__ == "__main__":
    unittest.main()
