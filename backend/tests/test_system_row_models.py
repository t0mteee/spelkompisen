import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from app import main


class SystemRowModelTests(unittest.TestCase):
    @staticmethod
    def _analysis():
        return SimpleNamespace(
            turnover=0.0, row_price=1.0, draw_number=123,
            reg_close_time="2026-08-25T18:00:00Z")

    @staticmethod
    def _call(**overrides):
        args = {
            "product": "topptipset", "draw": 123, "strategy": "medel",
            "budget": 384.0, "reduced": False, "guarantee": 0,
            "sv_rsystem": "", "ev": True, "color": False, "colors": "",
            "bounds": "", "jackpot": 0.0, "value_weight": 0.8,
            "row_model": "standard", "complementary": False,
        }
        args.update(overrides)
        return main.system(**args)

    def test_row_shape_profile_uses_frozen_model_and_weight(self) -> None:
        built = object()
        with (mock.patch("app.main._analyze", return_value=self._analysis()),
              mock.patch("app.main.build_topptips_row_shape_system",
                         return_value=built) as build,
              mock.patch("app.main.system_to_dict", return_value={"rows": 384})):
            response = self._call(row_model="row_shape_v1")

        self.assertEqual("row_shape_v1", response["row_model"])
        self.assertEqual("Radform v1 · test", response["row_model_label"])
        self.assertEqual(0.5, response["effective_value_weight"])
        args, kwargs = build.call_args
        self.assertEqual(4, len(args))
        self.assertEqual(set(range(5)), set(args[1]))
        self.assertEqual(0.5, kwargs["value_weight"])

    def test_hit_profile_forces_zero_weight(self) -> None:
        with (mock.patch("app.main._analyze", return_value=self._analysis()),
              mock.patch("app.main.build_ev_system",
                         return_value=object()) as build,
              mock.patch("app.main.system_to_dict", return_value={})):
            response = self._call(row_model="hit", value_weight=0.9)

        self.assertEqual("hit", response["row_model"])
        self.assertEqual(0.0, response["effective_value_weight"])
        self.assertEqual(0.0, build.call_args.kwargs["value_weight"])

    def test_row_shape_fails_closed_outside_topptips(self) -> None:
        with mock.patch("app.main._analyze", return_value=self._analysis()):
            with self.assertRaises(HTTPException) as error:
                self._call(product="stryktipset", row_model="row_shape_v1")

        self.assertEqual(400, error.exception.status_code)
        self.assertIn("endast Topptipset", error.exception.detail)

    def test_row_shape_fails_closed_outside_validated_budget(self) -> None:
        with mock.patch("app.main._analyze", return_value=self._analysis()):
            with self.assertRaises(HTTPException) as error:
                self._call(row_model="row_shape_v1", budget=256.0)

        self.assertEqual(400, error.exception.status_code)
        self.assertIn("384 kr", error.exception.detail)

    def test_hit_profile_is_available_for_thirteen_match_games(self) -> None:
        with (mock.patch("app.main._analyze", return_value=self._analysis()),
              mock.patch("app.main.build_ev_system",
                         return_value=object()) as build,
              mock.patch("app.main.system_to_dict", return_value={})):
            response = self._call(
                product="europatipset", row_model="hit", budget=256.0)

        self.assertEqual("hit", response["row_model"])
        self.assertEqual(0.0, build.call_args.kwargs["value_weight"])

    def test_row_shape_cannot_be_combined_or_used_outside_ev(self) -> None:
        with mock.patch("app.main._analyze", return_value=self._analysis()):
            with self.assertRaises(HTTPException) as combined:
                self._call(row_model="row_shape_v1", complementary=True)
            with self.assertRaises(HTTPException) as wrong_builder:
                self._call(row_model="hit", ev=False)

        self.assertEqual(400, combined.exception.status_code)
        self.assertEqual(400, wrong_builder.exception.status_code)


if __name__ == "__main__":
    unittest.main()
