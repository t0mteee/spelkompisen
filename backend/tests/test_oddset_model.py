import datetime
import unittest

from app import oddset_model


class AsianSettlementTests(unittest.TestCase):
    @staticmethod
    def _simple_total_matrix() -> list[list[float]]:
        matrix = [[0.0] * 5 for _ in range(5)]
        matrix[1][1] = 0.2  # total 2
        matrix[2][1] = 0.3  # total 3
        matrix[2][2] = 0.5  # total 4
        return matrix

    def test_pair_fair_handles_push(self) -> None:
        fair = oddset_model.pair_fair(
            self._simple_total_matrix(), "ou", 3.0, ("O", "U"))
        self.assertEqual(1.4, fair["O"])
        self.assertEqual(3.5, fair["U"])
        self.assertAlmostEqual(0.7143, fair["pO"], places=4)
        self.assertAlmostEqual(0.2857, fair["pU"], places=4)

    def test_pair_fair_handles_quarter_line(self) -> None:
        fair = oddset_model.pair_fair(
            self._simple_total_matrix(), "ou", 2.75, ("O", "U"))
        self.assertEqual(1.31, fair["O"])
        self.assertEqual(4.25, fair["U"])
        self.assertAlmostEqual(0.7647, fair["pO"], places=4)
        self.assertAlmostEqual(0.2353, fair["pU"], places=4)

    def test_anchor_roundtrips_settlement_probability_after_temperature(self) -> None:
        temperature = 0.85
        source = oddset_model.temper(
            oddset_model.dc_matrix(1.55, 1.05), temperature)

        for line in (2.5, 3.0, 2.75, 3.25):
            with self.subTest(line=line):
                target = oddset_model.pair_fair(source, "ou", line, ("O", "U"))["pO"]
                mu_h, mu_a = oddset_model._anchor_total(
                    0.9, 1.45, line, target, temperature=temperature)
                anchored = oddset_model.temper(
                    oddset_model.dc_matrix(mu_h, mu_a), temperature)
                actual = oddset_model.pair_fair(
                    anchored, "ou", line, ("O", "U"))["pO"]
                self.assertAlmostEqual(target, actual, delta=1e-3)

    def test_corner_poisson_pair_handles_push_and_is_complementary(self) -> None:
        pair = oddset_model.corner_pair(10.0, 10.0)

        self.assertIsNotNone(pair)
        self.assertAlmostEqual(1.0, pair["pO"] + pair["pU"], places=4)
        self.assertAlmostEqual(1 / pair["O"], pair["pO"], places=2)
        self.assertAlmostEqual(1 / pair["U"], pair["pU"], places=2)


class ModelTransparencyTests(unittest.TestCase):
    def test_market_comparison_devigs_all_sources_and_reports_pp(self) -> None:
        match = {
            "odds": {
                "pinnacle": {
                    "1x2": {"1": 2.0, "X": 4.0, "2": 4.0, "fresh": True},
                    "ou": {"O": 1.8, "U": 2.0, "line": 3.0, "fresh": True},
                },
                "svenskaspel": {
                    "1x2": {"1": 2.1, "X": 3.8, "2": 3.9, "fresh": True},
                    "ou": {"O": 2.0, "U": 1.8, "line": 2.5, "fresh": True},
                },
            },
            "sharp_alt": {
                "ou": {
                    2500: {
                        "O": 1.9, "U": 1.9, "available": True,
                        "last_seen_at": "2026-07-25T10:00:00Z",
                    },
                },
            },
        }
        model = {
            "p": {"1": 0.55, "X": 0.24, "2": 0.21},
            "ou": {"line": 2.5, "pO": 0.54, "pU": 0.46},
        }
        now = oddset_model.dt.datetime(
            2026, 7, 25, 10, 10, tzinfo=oddset_model.dt.timezone.utc)

        result = oddset_model.market_comparisons(match, model, now=now)

        self.assertAlmostEqual(0.5, result["1x2"]["sharp"]["1"], places=4)
        self.assertEqual(5.0, result["1x2"]["model_vs_sharp_pp"]["1"])
        self.assertEqual("pinnacle_alt", result["ou"]["sharp_source"])
        self.assertAlmostEqual(0.5, result["ou"]["sharp"]["O"], places=4)
        self.assertEqual(4.0, result["ou"]["model_vs_sharp_pp"]["O"])
        self.assertIsNotNone(result["ou"]["svs"])

    def test_pair_never_compares_different_lines_without_alt_price(self) -> None:
        match = {
            "odds": {
                "pinnacle": {
                    "ah": {"H": 1.9, "A": 1.9, "line": -0.5, "fresh": True},
                },
                "svenskaspel": {
                    "ah": {"H": 1.9, "A": 1.9, "line": -0.25, "fresh": True},
                },
            },
        }
        model = {"ah": {"line": -0.25, "pH": 0.52, "pA": 0.48}}

        result = oddset_model.market_comparisons(match, model)

        self.assertIsNone(result["ah"]["sharp"])
        self.assertIn("exakt lina", result["ah"]["sharp_note"])

    def test_corner_comparison_uses_the_frozen_sharp_line(self) -> None:
        match = {
            "odds": {
                "pinnacle": {
                    "cor": {"O": 1.9, "U": 1.9, "line": 9.5, "fresh": True},
                },
                "svenskaspel": {
                    "cor": {"O": 2.0, "U": 1.8, "line": 9.5, "fresh": True},
                },
            },
        }
        model = {
            "cor": {"line": 9.5, "pO": 0.55, "pU": 0.45},
        }

        result = oddset_model.market_comparisons(match, model)["cor"]

        self.assertEqual(5.0, result["model_vs_sharp_pp"]["O"])
        self.assertIsNotNone(result["svs"])


class PowerRankTests(unittest.TestCase):
    """Låser metodregeln: poäng och xPts mäts på SAMMA matcher.

    powerrank-v1 räknade poäng på alla matcher och skalade dem med
    täckningsgraden. Det antog att poängen fördelade sig jämnt över matcher
    med och utan xG — ett antagande utan stöd, som gjorde avvikelsen till en
    approximation. Testerna nedan finns för att den skalningen aldrig ska
    smyga tillbaka.
    """

    @staticmethod
    def _rows(n: int = 40) -> list[dict]:
        """En liten liga där HEMMALAGET alltid vinner 2–0 på xG 2,0–0,2.

        n är satt så varje lag når över MIN_MATCHES även när halva
        uppsättningen tappar xG i testerna nedan.
        """
        teams = ["alfa", "beta", "gamma", "delta"]
        start = datetime.date(2026, 3, 1)
        rows = []
        for i in range(n):
            rows.append({
                "league": "testliga",
                "date": (start + datetime.timedelta(days=i * 3)).isoformat(),
                "home": teams[i % 4], "away": teams[(i + 1) % 4],
                "home_raw": teams[i % 4].title(),
                "away_raw": teams[(i + 1) % 4].title(),
                "hg": 2, "ag": 0, "xg_h": 2.0, "xg_a": 0.2,
            })
        return rows

    def test_points_and_xpts_count_the_same_matches(self) -> None:
        rows = self._rows()
        # Halva matcherna tappar xG — de ska försvinna HELT, inte skalas.
        for row in rows[::2]:
            row["xg_h"] = row["xg_a"] = None
        covered = [r for r in rows if r["xg_h"] is not None]

        rank = oddset_model.powerrank(rows, league="testliga")

        self.assertTrue(rank)
        by_team = {r["team"]: r for r in rank}
        for team, row in by_team.items():
            played = sum(1 for r in covered
                         if team in (r["home"], r["away"]))
            self.assertEqual(played, row["matches"])
            wins = sum(1 for r in covered if r["home"] == team)
            self.assertEqual(3.0 * wins, row["points"])
            self.assertAlmostEqual(row["points"] - row["xpts"],
                                   row["overperformance"], places=1)

    def test_team_without_xg_matches_is_dropped(self) -> None:
        rows = self._rows()
        rows.extend({
            "league": "testliga", "date": f"2026-05-{d:02d}",
            "home": "epsilon", "away": "alfa",
            "home_raw": "Epsilon", "away_raw": "Alfa",
            "hg": 1, "ag": 1, "xg_h": None, "xg_a": None,
        } for d in range(1, 25))

        rank = oddset_model.powerrank(rows, league="testliga")

        # Laget spelade 12 matcher men ingen med xG: det finns inget att
        # jämföra dess poäng mot, så raden ska inte finnas alls.
        self.assertNotIn("epsilon", {r["team"] for r in rank})

    def test_season_filter_scopes_columns_but_not_the_strength_gate(self) -> None:
        rows = self._rows()
        for row in rows[:6]:
            row["date"] = row["date"].replace("2026", "2025")

        full = oddset_model.powerrank(rows, league="testliga")
        current = oddset_model.powerrank(rows, league="testliga", season="2026")

        self.assertTrue(current, "säsongen får inte tömma tabellen")
        # Samma lag kvar (MIN_MATCHES prövas mot hela historiken), men färre
        # räknade matcher.
        self.assertEqual({r["team"] for r in full}, {r["team"] for r in current})
        self.assertLess(sum(r["matches"] for r in current),
                        sum(r["matches"] for r in full))

    def test_season_label_follows_the_league_calendar(self) -> None:
        # Nordiska ligor och MLS spelar inom kalenderåret …
        self.assertEqual("2026", oddset_model.season_of("2026-08-20", "allsvenskan"))
        self.assertEqual("2026", oddset_model.season_of("2026-03-30", "mls"))
        # … Europaligorna över årsskiftet.
        self.assertEqual("2026/27",
                         oddset_model.season_of("2026-08-20", "premier_league"))
        self.assertEqual("2025/26",
                         oddset_model.season_of("2026-02-10", "premier_league"))
        self.assertIsNone(oddset_model.season_of("", "allsvenskan"))

    def test_display_name_prefers_diacritics_then_the_fuller_name(self) -> None:
        self.assertEqual("IFK Norrköping",
                         oddset_model._display_name(
                             "ifk norrkoping", {"Norrkoping", "IFK Norrköping"}))
        self.assertEqual("Degerfors IF",
                         oddset_model._display_name(
                             "degerfors", {"Degerfors", "Degerfors IF"}))
        # Utan råa namn får nyckeln inte nå skärmen i gemener.
        self.assertEqual("Djurgarden",
                         oddset_model._display_name("djurgarden", set()))

    def test_odds_names_supply_diacritics_on_exact_key_only(self) -> None:
        rows = self._rows()
        # Oddssidans namn läggs på när nyckeln stämmer exakt …
        rank = oddset_model.powerrank(
            rows, league="testliga",
            odds_names=["Ålfa IF", "Ingen Sådan Klubb"])

        by_team = {r["team"]: r["name"] for r in rank}
        self.assertEqual("Ålfa IF", by_team["alfa"])
        # … och ett namn utan motsvarande lag skapar aldrig en rad.
        self.assertNotIn("ingen sadan klubb", by_team)

    def test_rows_carry_a_display_name(self) -> None:
        rank = oddset_model.powerrank(self._rows(), league="testliga")

        self.assertTrue(rank)
        for row in rank:
            self.assertEqual(row["team"].title(), row["name"])


if __name__ == "__main__":
    unittest.main()
