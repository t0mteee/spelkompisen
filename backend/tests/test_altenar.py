import unittest
from unittest import mock

from app import altenar


def _payload(*, suspended_main: bool = False) -> dict:
    return {
        "markets": [
            {
                "id": 100,
                "typeId": 166,
                "isBB": False,
                "sv": "8.5",
                "desktopOddIds": [[1, 3, 5], [2, 4, 6]],
            },
            # Samma marknad förekommer som Bet Builder-kopia i riktiga svaret.
            {
                "id": 100,
                "typeId": 166,
                "isBB": True,
                "desktopOddIds": [[1, 3, 5], [2, 4, 6]],
            },
            {"id": 200, "typeId": 18, "desktopOddIds": [[7], [8]]},
        ],
        "odds": [
            {"id": 1, "typeId": 12, "price": 1.4, "sv": "8.5",
             "oddStatus": 0, "isMB": False},
            {"id": 2, "typeId": 13, "price": 2.7143, "sv": "8.5",
             "oddStatus": 0, "isMB": False},
            {"id": 3, "typeId": 12, "price": 1.7, "sv": "9.5",
             "oddStatus": 1 if suspended_main else 0, "isMB": True},
            {"id": 4, "typeId": 13, "price": 2.05, "sv": "9.5",
             "oddStatus": 0, "isMB": True},
            {"id": 5, "typeId": 12, "price": 2.2, "sv": "10.5",
             "oddStatus": 0, "isMB": False},
            {"id": 6, "typeId": 13, "price": 1.6, "sv": "10.5",
             "oddStatus": 0, "isMB": False},
            {"id": 7, "typeId": 12, "price": 1.9, "sv": "2.5", "oddStatus": 0},
            {"id": 8, "typeId": 13, "price": 1.9, "sv": "2.5", "oddStatus": 0},
        ],
    }


class AltenarEventMarketTests(unittest.TestCase):
    def test_corner_parser_uses_odds_line_and_marked_main_pair(self) -> None:
        self.assertEqual(
            {"O": 1.7, "U": 2.05, "line": 9.5},
            altenar._corner_total(_payload()),
        )

    def test_incomplete_suspended_main_falls_back_to_balanced_complete_pair(
            self) -> None:
        self.assertEqual(
            {"O": 2.2, "U": 1.6, "line": 10.5},
            altenar._corner_total(_payload(suspended_main=True)),
        )

    @mock.patch.object(altenar.httpx, "get")
    def test_event_details_endpoint_and_integration_are_used(self, get) -> None:
        response = mock.MagicMock()
        response.json.return_value = _payload()
        get.return_value = response

        result = altenar.event_markets(
            "16807898", integration="ninjacasinose", strict=True)

        self.assertEqual(
            {"cor": {"O": 1.7, "U": 2.05, "line": 9.5}}, result)
        self.assertTrue(get.call_args.args[0].endswith("/GetEventDetails"))
        self.assertEqual("16807898", get.call_args.kwargs["params"]["eventId"])
        self.assertEqual(
            "ninjacasinose", get.call_args.kwargs["params"]["integration"])
        response.raise_for_status.assert_called_once()

    @mock.patch.object(altenar.httpx, "get", side_effect=RuntimeError("blocked"))
    def test_best_effort_returns_empty_but_strict_raises(self, _get) -> None:
        self.assertEqual({}, altenar.event_markets("1"))
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            altenar.event_markets("1", strict=True)


if __name__ == "__main__":
    unittest.main()
