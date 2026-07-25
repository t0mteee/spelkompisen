"""Publik bootstrap för Betssons sportsbook-API.

Betssons webbklient skickar två olika slags kontext:

* ``brandId``/``marketCode`` till sportsbook-API:t;
* ``x-sb-*``-fält från sidans publika, utloggade användarkontext.

``brandId`` är sportsbookens UUID i sidans bootstrap — inte det separata
content-brand-id som också förekommer på betsson.com. Modulen hämtar och
normaliserar enbart denna publika kontext. Den försöker inte återanvända
browsercookies eller passera CloudFront/WAF, och är därför ännu inte inkopplad
som bookmakerkälla i Oddset-varvet.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import uuid
from typing import Any, Optional

import httpx


BASE = "https://www.betsson.com"
ODDS_PAGE = f"{BASE}/sv/odds"
USER_CONTEXT_URL = f"{BASE}/sb/fe-api/v1/user-context"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "spelkompisen/1.0 (personligt analysverktyg)",
}


@dataclass(frozen=True)
class Bootstrap:
    sportsbook_brand_id: str
    static_context_id: str
    user_context_id: str


def _embedded_string(html: str, key: str) -> str:
    """Läs ett JSON-strängfält ur sidans inline-bootstrap."""
    pattern = rf'"{re.escape(key)}"\s*:\s*("(?:\\.|[^"\\])*")'
    match = re.search(pattern, html)
    if not match:
        raise ValueError(f"Betsson-bootstrap saknar {key}")
    value = json.loads(match.group(1))
    if not isinstance(value, str) or not value:
        raise ValueError(f"Betsson-bootstrap har ogiltigt {key}")
    return value


def parse_bootstrap(html: str) -> Bootstrap:
    """Extrahera de tre publika ID:n som sportsbookens webbklient använder."""
    return Bootstrap(
        sportsbook_brand_id=_embedded_string(html, "sportsbookBrandId"),
        static_context_id=_embedded_string(html, "staticContextId"),
        user_context_id=_embedded_string(html, "userContextId"),
    )


def _find_key(value: Any, key: str) -> Any:
    """Hitta första namngivna fältet i Betssons nästlade context-payload."""
    if isinstance(value, dict):
        if key in value and value[key] not in (None, ""):
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found not in (None, ""):
                return found
    return None


def _context_value(payload: dict, key: str, default: Optional[str] = None) -> str:
    value = _find_key(payload, key)
    if value in (None, ""):
        if default is not None:
            return default
        raise ValueError(f"Betsson user-context saknar {key}")
    return str(value)


def build_sportsbook_headers(
    bootstrap: Bootstrap,
    user_context: dict,
    correlation_id: Optional[str] = None,
) -> dict[str, str]:
    """Bygg webbklientens publika, utloggade sportsbook-kontext.

    Headernamnet som tidigare blockerade anropen är exakt ``brandId``.
    Övriga fält hämtas ur ``/sb/fe-api/v1/user-context`` och hårdkodas inte.
    """
    request_id = correlation_id or str(uuid.uuid4())
    language = _context_value(user_context, "languageCode", "sv")
    country = _context_value(user_context, "countryCode", "SE")
    channel = _context_value(user_context, "channel", "Web")
    device = _context_value(user_context, "deviceType", "Desktop")
    jurisdiction = _context_value(user_context, "jurisdiction")
    segment = _context_value(user_context, "segmentId")
    facade = _context_value(user_context, "facadeId")
    currency = _context_value(user_context, "currencyCode", "SEK")
    app_version = _context_value(user_context, "version")
    user_state = _context_value(user_context, "userState", "LoggedOut")

    return {
        **HEADERS,
        "brandId": bootstrap.sportsbook_brand_id,
        "marketCode": language,
        "x-sb-brand-id": bootstrap.sportsbook_brand_id,
        "x-sb-static-context-id": bootstrap.static_context_id,
        "x-sb-user-context-id": bootstrap.user_context_id,
        "x-sb-country-code": country,
        "x-sb-language-code": language,
        "x-sb-channel": channel,
        "x-sb-device-type": device,
        "x-sb-jurisdiction": jurisdiction,
        "x-sb-segment-id": segment,
        "x-sb-facade-id": facade,
        "x-sb-currency-code": currency,
        "x-sb-app-version": app_version,
        "x-sb-user-state": user_state,
        "x-sb-type": "b2b",
        "x-sb-correlation-id": request_id,
        "x-correlation-id": request_id,
        "correlationid": request_id,
        "X-OBG-Channel": channel,
        "X-OBG-Device": device,
    }


def fetch_public_context(
    client: Optional[httpx.Client] = None,
) -> tuple[Bootstrap, dict, dict[str, str]]:
    """Hämta cookie-fri bootstrap, user-context och färdiga API-headers."""
    owns_client = client is None
    http = client or httpx.Client(timeout=20.0, headers=HEADERS)
    try:
        page = http.get(ODDS_PAGE)
        page.raise_for_status()
        bootstrap = parse_bootstrap(page.text)

        context = http.get(
            USER_CONTEXT_URL,
            headers={
                **HEADERS,
                "x-sb-static-context-id": bootstrap.static_context_id,
                "x-sb-user-context-id": bootstrap.user_context_id,
            },
        )
        context.raise_for_status()
        payload = context.json()
        return bootstrap, payload, build_sportsbook_headers(bootstrap, payload)
    finally:
        if owns_client:
            http.close()
