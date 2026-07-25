import unittest

from app import betsson


HTML = """
<script>
window.bootstrap = {
  "customerContext": {
    "staticContextId": "stc--412615874",
    "userContextId": "stc--412615874"
  },
  "sportsbookBrandId": "6a6d80b9-16ac-4387-a413-244d93a74deb"
};
</script>
"""

USER_CONTEXT = {
    "userContext": {
        "userState": "LoggedOut",
        "contextInformation": {
            "countryCode": "SE",
            "languageCode": "sv",
            "channel": "Web",
            "deviceType": "Desktop",
            "jurisdiction": "Sga",
            "activeWallet": {"currencyCode": "SEK"},
            "segmentId": "segment-1",
            "facadeId": "facade-1",
        },
    },
    "metadata": {"version": "7.37.39.4067-rc2bc041"},
}


class BetssonTests(unittest.TestCase):
    def test_laser_sportsbookens_publika_bootstrap(self):
        parsed = betsson.parse_bootstrap(HTML)
        self.assertEqual(
            "6a6d80b9-16ac-4387-a413-244d93a74deb",
            parsed.sportsbook_brand_id,
        )
        self.assertEqual("stc--412615874", parsed.static_context_id)
        self.assertEqual("stc--412615874", parsed.user_context_id)

    def test_brand_headern_anvander_sportsbook_id(self):
        bootstrap = betsson.parse_bootstrap(HTML)
        headers = betsson.build_sportsbook_headers(
            bootstrap,
            USER_CONTEXT,
            correlation_id="request-1",
        )
        self.assertEqual(bootstrap.sportsbook_brand_id, headers["brandId"])
        self.assertEqual("sv", headers["marketCode"])
        self.assertEqual("stc--412615874", headers["x-sb-static-context-id"])
        self.assertEqual("Sga", headers["x-sb-jurisdiction"])
        self.assertEqual("SEK", headers["x-sb-currency-code"])
        self.assertEqual("request-1", headers["x-sb-correlation-id"])

    def test_saknad_bootstrap_avvisas_tydligt(self):
        with self.assertRaisesRegex(ValueError, "sportsbookBrandId"):
            betsson.parse_bootstrap(
                '{"staticContextId":"stc-1","userContextId":"stc-1"}'
            )

    def test_obligatorisk_serverkontext_far_inte_hardkodas(self):
        bootstrap = betsson.parse_bootstrap(HTML)
        incomplete = {
            "countryCode": "SE",
            "languageCode": "sv",
            "userState": "LoggedOut",
        }
        with self.assertRaisesRegex(ValueError, "jurisdiction"):
            betsson.build_sportsbook_headers(bootstrap, incomplete)


if __name__ == "__main__":
    unittest.main()
