"""Landslagens identitet i Oddset (2026-10-03).

Svenska Spel (Kambi) skriver landslagen på svenska ("Tyskland"), Pinnacle på
engelska ("Germany"). Oddsets vanliga koppling är ungefärlig namnlikhet
(`oddset._team_sim`). Den fungerar inte mellan språk, och för landslag är den
farlig: "Irland" ligger inuti "Nordirland" och "Niger" inuti "Nigeria".
Landslag kopplas därför bara på landskod (`oddset._resolve_landslag`), och
båda lagen måste vara kända. Ett okänt namn ger ingen koppling, alltså en egen
rad i stället för en gissning. Insamlingen rapporterar okända namn under
`okanda_landslag` i ligarapporten; lägg då till dem här.

Koden är FIFA:s landskod. Tabellen täcker Europa (UEFA) och de vanligaste
motståndarna i landskamper. Namnen jämförs utan skiftläge och diakriter, och
"&", "och" och "and" räknas som samma ord.

Rör INTE `oddset.TEAM_ALIASES` för landslag: den ingår i V2.2:s fingeravtryck.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

LANDSLAG: dict[str, tuple[str, ...]] = {
    # ── UEFA ──
    "ALB": ("Albanien", "Albania"),
    "AND": ("Andorra",),
    "ARM": ("Armenien", "Armenia"),
    "AUT": ("Österrike", "Austria"),
    "AZE": ("Azerbajdzjan", "Azerbaijan"),
    "BLR": ("Vitryssland", "Belarus"),
    "BEL": ("Belgien", "Belgium"),
    "BIH": ("Bosnien & Hercegovina", "Bosnien-Hercegovina", "Bosnia & Herzegovina",
            "Bosnia-Herzegovina"),
    "BUL": ("Bulgarien", "Bulgaria"),
    "CRO": ("Kroatien", "Croatia"),
    "CYP": ("Cypern", "Cyprus"),
    "CZE": ("Tjeckien", "Czech Republic", "Czechia"),
    "DEN": ("Danmark", "Denmark"),
    "ENG": ("England",),
    "EST": ("Estland", "Estonia"),
    "FRO": ("Färöarna", "Faroe Islands", "Faroe Isl"),
    "FIN": ("Finland",),
    "FRA": ("Frankrike", "France"),
    "GEO": ("Georgien", "Georgia"),
    "GER": ("Tyskland", "Germany"),
    "GIB": ("Gibraltar",),
    "GRE": ("Grekland", "Greece"),
    "HUN": ("Ungern", "Hungary"),
    "ISL": ("Island", "Iceland"),
    "IRL": ("Irland", "Ireland", "Republic of Ireland", "Rep of Ireland"),
    "ISR": ("Israel",),
    "ITA": ("Italien", "Italy"),
    "KAZ": ("Kazakstan", "Kazakhstan"),
    "KVX": ("Kosovo",),
    "LVA": ("Lettland", "Latvia"),
    "LIE": ("Liechtenstein",),
    "LTU": ("Litauen", "Lithuania"),
    "LUX": ("Luxemburg", "Luxembourg"),
    "MLT": ("Malta",),
    "MDA": ("Moldavien", "Moldova"),
    "MNE": ("Montenegro",),
    "NED": ("Nederländerna", "Holland", "Netherlands"),
    "MKD": ("Nordmakedonien", "Makedonien", "North Macedonia", "Macedonia"),
    "NIR": ("Nordirland", "Northern Ireland"),
    "NOR": ("Norge", "Norway"),
    "POL": ("Polen", "Poland"),
    "POR": ("Portugal",),
    "ROU": ("Rumänien", "Romania"),
    "RUS": ("Ryssland", "Russia"),
    "SMR": ("San Marino",),
    "SCO": ("Skottland", "Scotland"),
    "SRB": ("Serbien", "Serbia"),
    "SVK": ("Slovakien", "Slovakia"),
    "SVN": ("Slovenien", "Slovenia"),
    "ESP": ("Spanien", "Spain"),
    "SWE": ("Sverige", "Sweden"),
    "SUI": ("Schweiz", "Switzerland"),
    "TUR": ("Turkiet", "Turkey", "Türkiye"),
    "UKR": ("Ukraina", "Ukraine"),
    "WAL": ("Wales",),
    # ── CONMEBOL ──
    "ARG": ("Argentina",),
    "BOL": ("Bolivia",),
    "BRA": ("Brasilien", "Brazil"),
    "CHI": ("Chile",),
    "COL": ("Colombia",),
    "ECU": ("Ecuador",),
    "PAR": ("Paraguay",),
    "PER": ("Peru",),
    "URU": ("Uruguay",),
    "VEN": ("Venezuela",),
    # ── CONCACAF ──
    "USA": ("USA", "United States", "US"),
    "MEX": ("Mexiko", "Mexico"),
    "CAN": ("Kanada", "Canada"),
    "CRC": ("Costa Rica",),
    "PAN": ("Panama",),
    "JAM": ("Jamaica",),
    "HON": ("Honduras",),
    "SLV": ("El Salvador",),
    "GUA": ("Guatemala",),
    "HAI": ("Haiti",),
    "TRI": ("Trinidad & Tobago",),
    "CUW": ("Curaçao",),
    "NCA": ("Nicaragua",),
    "SUR": ("Surinam", "Suriname"),
    # ── AFC ──
    "JPN": ("Japan",),
    "KOR": ("Sydkorea", "South Korea", "Korea Republic", "Korea"),
    "PRK": ("Nordkorea", "North Korea", "Korea DPR"),
    "CHN": ("Kina", "China", "China PR"),
    "AUS": ("Australien", "Australia"),
    "IRN": ("Iran",),
    "IRQ": ("Irak", "Iraq"),
    "KSA": ("Saudiarabien", "Saudi Arabia"),
    "QAT": ("Qatar",),
    "UAE": ("Förenade Arabemiraten", "United Arab Emirates", "UAE"),
    "JOR": ("Jordanien", "Jordan"),
    "UZB": ("Uzbekistan",),
    "IND": ("Indien", "India"),
    "THA": ("Thailand",),
    "VIE": ("Vietnam",),
    "IDN": ("Indonesien", "Indonesia"),
    "OMA": ("Oman",),
    "BHR": ("Bahrain",),
    "KUW": ("Kuwait",),
    "SYR": ("Syrien", "Syria"),
    "LBN": ("Libanon", "Lebanon"),
    "PLE": ("Palestina", "Palestine"),
    "MAS": ("Malaysia",),
    "SIN": ("Singapore",),
    "PHI": ("Filippinerna", "Philippines"),
    "HKG": ("Hongkong", "Hong Kong"),
    "KGZ": ("Kirgizistan", "Kyrgyzstan"),
    "TJK": ("Tadzjikistan", "Tajikistan"),
    # ── CAF ──
    "MAR": ("Marocko", "Morocco"),
    "ALG": ("Algeriet", "Algeria"),
    "TUN": ("Tunisien", "Tunisia"),
    "EGY": ("Egypten", "Egypt"),
    "NGA": ("Nigeria",),
    "GHA": ("Ghana",),
    "SEN": ("Senegal",),
    "CIV": ("Elfenbenskusten", "Ivory Coast", "Côte d'Ivoire"),
    "CMR": ("Kamerun", "Cameroon"),
    "RSA": ("Sydafrika", "South Africa"),
    "MLI": ("Mali",),
    "BFA": ("Burkina Faso",),
    "CPV": ("Kap Verde", "Cape Verde", "Cabo Verde"),
    "COD": ("DR Kongo", "Kongo DR", "Kongo-Kinshasa", "DR Congo", "Congo DR"),
    "CGO": ("Kongo", "Kongo-Brazzaville", "Congo"),
    "GAB": ("Gabon",),
    "GUI": ("Guinea",),
    "ZAM": ("Zambia",),
    "ANG": ("Angola",),
    "NIG": ("Niger",),
    "UGA": ("Uganda",),
    "KEN": ("Kenya",),
    "TAN": ("Tanzania",),
    "BEN": ("Benin",),
    "TOG": ("Togo",),
    "MTN": ("Mauretanien", "Mauritania"),
    "LBY": ("Libyen", "Libya"),
    "SDN": ("Sudan",),
    "ZIM": ("Zimbabwe",),
    "MOZ": ("Moçambique", "Mozambique"),
    "MAD": ("Madagaskar", "Madagascar"),
    "EQG": ("Ekvatorialguinea", "Equatorial Guinea"),
    "GNB": ("Guinea-Bissau",),
    "GAM": ("Gambia",),
    "COM": ("Komorerna", "Comoros"),
    "NAM": ("Namibia",),
    "DJI": ("Djibouti",),
    "RWA": ("Rwanda",),
    "BDI": ("Burundi",),
    "ETH": ("Etiopien", "Ethiopia"),
    "ERI": ("Eritrea",),
    "SOM": ("Somalia",),
    "SSD": ("Sydsudan", "South Sudan"),
    "CTA": ("Centralafrikanska republiken", "Central African Republic"),
    "CHA": ("Tchad", "Chad"),
    "LBR": ("Liberia",),
    "SLE": ("Sierra Leone",),
    "BOT": ("Botswana",),
    "LES": ("Lesotho",),
    "SWZ": ("Eswatini", "Swaziland"),
    "MWI": ("Malawi",),
    "MRI": ("Mauritius",),
    "SEY": ("Seychellerna", "Seychelles"),
    "STP": ("São Tomé och Príncipe", "Sao Tome & Principe"),
    # ── fler i AFC och CONCACAF ──
    "SRI": ("Sri Lanka",),
    "BAN": ("Bangladesh",),
    "NEP": ("Nepal",),
    "MDV": ("Maldiverna", "Maldives"),
    "MYA": ("Myanmar",),
    "CAM": ("Kambodja", "Cambodia"),
    "LAO": ("Laos",),
    "MNG": ("Mongoliet", "Mongolia"),
    "AFG": ("Afghanistan",),
    "PAK": ("Pakistan",),
    "TKM": ("Turkmenistan",),
    "YEM": ("Jemen", "Yemen"),
    "TPE": ("Taiwan", "Chinese Taipei"),
    "BRU": ("Brunei",),
    "TLS": ("Östtimor", "Timor-Leste", "East Timor"),
    "GUM": ("Guam",),
    "MAC": ("Macao", "Macau"),
    "BHU": ("Bhutan",),
    "CUB": ("Kuba", "Cuba"),
    "DOM": ("Dominikanska republiken", "Dominican Republic"),
    "DMA": ("Dominica",),
    "PUR": ("Puerto Rico",),
    "BRB": ("Barbados",),
    "GRN": ("Grenada",),
    "BER": ("Bermuda",),
    "GUY": ("Guyana",),
    "BLZ": ("Belize",),
    "ATG": ("Antigua & Barbuda",),
    "SKN": ("Saint Kitts & Nevis", "St Kitts & Nevis"),
    "LCA": ("Saint Lucia", "St Lucia"),
    "VIN": ("Saint Vincent & Grenadinerna", "Saint Vincent & the Grenadines",
            "St Vincent & the Grenadines"),
    # ── OFC ──
    "NZL": ("Nya Zeeland", "New Zealand"),
    "FIJ": ("Fiji",),
    "NCL": ("Nya Kaledonien", "New Caledonia"),
    "TAH": ("Tahiti",),
    "SOL": ("Salomonöarna", "Solomon Islands"),
    "PNG": ("Papua Nya Guinea", "Papua New Guinea"),
    "VAN": ("Vanuatu",),
    "SAM": ("Samoa",),
    "ASA": ("Amerikanska Samoa", "American Samoa"),
    "TGA": ("Tonga",),
}


def _nyckel(name: str) -> str:
    """Jämförbar form: gemener, inga diakriter, '&'/'och'/'and' lika, inga
    bindestreck, punkter eller apostrofer."""
    s = unicodedata.normalize("NFD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"[.\-'’]", " ", s).replace("&", " och ")
    s = f" {' '.join(s.split())} ".replace(" and ", " och ")
    return " ".join(s.split())


def _index() -> dict[str, str]:
    index: dict[str, str] = {}
    for code, names in LANDSLAG.items():
        for name in names:
            key = _nyckel(name)
            if index.get(key, code) != code:
                raise ValueError(f"{name!r} pekar på både {index[key]} och {code}")
            index[key] = code
    return index


_INDEX = _index()


def kod(name: str) -> Optional[str]:
    """FIFA-koden för ett landslagsnamn på svenska eller engelska, annars None."""
    return _INDEX.get(_nyckel(name))
