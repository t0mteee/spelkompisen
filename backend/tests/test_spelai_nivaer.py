"""Nivåer och validering av poolförslag (beslut 9 och 12)."""
import unittest

from app.spelai import nivaer
from app.spelai.nivaer import Ogiltigt, validera


def _rows(n: int, length: int = 13) -> list[str]:
    out = []
    for k in range(n):
        digits, value = [], k
        for _ in range(length):
            digits.append("1X2"[value % 3])
            value //= 3
        out.append("".join(digits))
    return out


class NivaTests(unittest.TestCase):
    def test_nivaer_per_produkt(self):
        self.assertEqual((256, 512, 5000, 20000, 39366), nivaer.nivaer_for("stryktipset"))
        self.assertEqual((256, 512, 5000, 20000, 39366), nivaer.nivaer_for("europatipset"))
        for product in ("topptipset", "topptipsetstryk", "topptipsetextra"):
            self.assertEqual((256,), nivaer.nivaer_for(product))
        self.assertEqual((), nivaer.nivaer_for("bomben"))

    def test_giltiga_rader(self):
        out = validera("stryktipset", 256, {"format": "rows", "rows": _rows(256),
                                            "motivering_kort": "x" * 900})
        self.assertEqual(256, out["n_rows"])
        self.assertEqual(256.0, out["cost_kr"])
        self.assertEqual(500, len(out["motivering"]))

    def test_fler_rader_an_nivan_avvisas(self):
        with self.assertRaisesRegex(Ogiltigt, "över nivån"):
            validera("stryktipset", 256, {"format": "rows", "rows": _rows(257)})

    def test_dubblett_fel_langd_och_tecken_avvisas(self):
        rows = _rows(3)
        with self.assertRaisesRegex(Ogiltigt, "dubblett"):
            validera("stryktipset", 256, {"format": "rows", "rows": rows + rows[:1]})
        with self.assertRaisesRegex(Ogiltigt, "12 tecken"):
            validera("stryktipset", 256, {"format": "rows", "rows": [rows[0][:12]]})
        with self.assertRaisesRegex(Ogiltigt, "ogiltigt tecken"):
            validera("stryktipset", 256, {"format": "rows", "rows": ["1" * 12 + "x"]})
        with self.assertRaisesRegex(Ogiltigt, "icke-tom"):
            validera("stryktipset", 256, {"format": "rows", "rows": []})

    def test_topptipset_bara_256_och_atta_matcher(self):
        out = validera("topptipsetextra", 256, {"format": "rows", "rows": _rows(10, 8)})
        self.assertEqual(10, out["n_rows"])
        with self.assertRaisesRegex(Ogiltigt, "finns inte"):
            validera("topptipset", 512, {"format": "rows", "rows": _rows(10, 8)})
        with self.assertRaisesRegex(Ogiltigt, "8 matcher"):
            validera("topptipset", 256, {"format": "rows", "rows": _rows(1, 13)})

    def test_msystem_exakt_form(self):
        tecken = ["1", "X", "2", "1X"] + ["1X2"] * 9
        out = validera("europatipset", 39366, {"format": "msystem", "tecken": tecken})
        self.assertEqual(39366, out["n_rows"])
        self.assertEqual(39366, len(nivaer.expandera(out["tecken"])))
        self.assertEqual(len(set(nivaer.expandera(out["tecken"]))), 39366)
        # ordningen inom en match normaliseras
        out2 = validera("europatipset", 39366,
                        {"format": "msystem", "tecken": ["1", "X", "2", "X1"] + ["21X"] * 9})
        self.assertEqual(out["rows_hash"], out2["rows_hash"])

    def test_msystem_fel_form_avvisas(self):
        fyra_spikar = ["1", "1", "1", "1"] + ["1X2"] * 9
        with self.assertRaisesRegex(Ogiltigt, "3 spikar, 1 halvgardering"):
            validera("stryktipset", 39366, {"format": "msystem", "tecken": fyra_spikar})
        with self.assertRaisesRegex(Ogiltigt, "13 matcher"):
            validera("stryktipset", 39366, {"format": "msystem", "tecken": ["1X2"] * 12})
        with self.assertRaisesRegex(Ogiltigt, "dubblerat"):
            validera("stryktipset", 39366,
                     {"format": "msystem", "tecken": ["11", "X", "2", "1X"] + ["1X2"] * 9})

    def test_format_maste_matcha_nivan(self):
        with self.assertRaisesRegex(Ogiltigt, "kräver format 'msystem'"):
            validera("stryktipset", 39366, {"format": "rows", "rows": _rows(5)})
        with self.assertRaisesRegex(Ogiltigt, "kräver format 'rows'"):
            validera("stryktipset", 20000,
                     {"format": "msystem", "tecken": ["1", "X", "2", "1X"] + ["1X2"] * 9})

    def test_hash_ar_ordningsoberoende(self):
        rows = _rows(20)
        a = validera("stryktipset", 256, {"format": "rows", "rows": rows})
        b = validera("stryktipset", 256, {"format": "rows", "rows": list(reversed(rows))})
        self.assertEqual(a["rows_hash"], b["rows_hash"])


if __name__ == "__main__":
    unittest.main()
