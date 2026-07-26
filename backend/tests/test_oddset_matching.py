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

    def test_one_exact_team_cannot_hide_an_unrelated_other_team(self) -> None:
        """Regression: Karlsruhe–Inter ≠ Novara–Internazionale U23."""
        self.assertEqual(
            0.0,
            oddset._match_score(
                "Karlsruher SC", "Inter", "2026-07-26T14:30:00Z",
                "Novara", "Internazionale U23", "2026-07-26T15:30:00Z",
            ),
        )
        self.assertIsNone(oddset._resolve(
            [{
                "id": "karlsruhe",
                "home": "Karlsruher SC",
                "away": "Inter",
                "start": "2026-07-26T14:30:00Z",
            }],
            "Novara", "Internazionale U23", "2026-07-26T15:30:00Z",
        ))

    def test_source_resolver_never_replaces_an_existing_source_id(self) -> None:
        candidates = [{
            "id": "pin:100",
            "home": "Karlsruher SC",
            "away": "Inter",
            "start": "2026-07-26T14:30:00Z",
            "pinnacle_id": "100",
        }]

        self.assertIsNone(oddset._resolve_source(
            candidates, "Karlsruher SC", "Inter",
            "2026-07-26T14:30:00Z", "200", "pinnacle_id"))
        self.assertEqual(
            "pin:100",
            oddset._resolve_source(
                candidates, "Karlsruher", "Internazionale",
                "2026-07-26T14:30:00Z", 100, "pinnacle_id")["id"],
        )

    def test_research_team_pair_can_bridge_placeholder_kickoff(self) -> None:
        candidates = [
            {"id": "inter", "home": "Internazionale", "away": "Monza",
             "start": "2026-08-22T16:30:00Z"},
            {"id": "other", "home": "Udinese", "away": "Como",
             "start": "2026-08-22T16:30:00Z"},
        ]

        match = oddset._resolve_team_pair(
            candidates, "Inter", "Monza")

        self.assertEqual("inter", match["id"])

    def test_research_team_pair_refuses_ambiguous_candidates(self) -> None:
        candidates = [
            {"id": "a", "home": "United", "away": "City",
             "start": "2026-08-22T16:30:00Z"},
            {"id": "b", "home": "United FC", "away": "City FC",
             "start": "2026-08-29T16:30:00Z"},
        ]

        self.assertIsNone(oddset._resolve_team_pair(
            candidates, "United", "City"))


if __name__ == "__main__":
    unittest.main()
