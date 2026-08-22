"""US license-plate serial formats used to guess issuing jurisdiction.

Compiled 2026-08-21 from:
- https://en.wikipedia.org/wiki/United_States_license_plate_designs_and_serial_formats
- https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_California
- OpenALPR runtime_data/postprocess/us.patterns (copy at app/data/us.patterns)

Masks: # digit, L letter, A alphanumeric, other characters are literals.
OCR text is compared after stripping spaces and dashes.
"""

from __future__ import annotations

META = {
    "retrieved": "2026-08-21",
    "sources": [
        "https://en.wikipedia.org/wiki/United_States_license_plate_designs_and_serial_formats",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_California",
        "https://github.com/openalpr/openalpr/blob/master/runtime_data/postprocess/us.patterns",
    ],
}

IOQ = ["I", "O", "Q"]
IOQU = ["I", "O", "Q", "U"]
VOWELS = ["A", "E", "I", "O", "U"]
TX_SKIP = ["A", "E", "I", "O", "Q", "U"]

# min_lat, min_lon, max_lat, max_lon
BBOX = {
    "AL": (30.22, -88.47, 35.01, -84.89),
    "AK": (51.22, -179.15, 71.44, -129.98),
    "AZ": (31.33, -114.82, 37.00, -109.04),
    "AR": (33.00, -94.62, 36.50, -89.64),
    "CA": (32.53, -124.48, 42.01, -114.13),
    "CO": (36.99, -109.06, 41.00, -102.04),
    "CT": (40.98, -73.73, 42.05, -71.79),
    "DE": (38.45, -75.79, 39.84, -75.05),
    "DC": (38.79, -77.12, 38.99, -76.91),
    "FL": (24.52, -87.63, 31.00, -80.03),
    "GA": (30.36, -85.61, 35.00, -80.84),
    "HI": (18.91, -178.33, 28.40, -154.81),
    "ID": (41.99, -117.24, 49.00, -111.04),
    "IL": (36.97, -91.51, 42.51, -87.50),
    "IN": (37.77, -88.10, 41.76, -84.78),
    "IA": (40.38, -96.64, 43.50, -90.14),
    "KS": (36.99, -102.05, 40.00, -94.59),
    "KY": (36.50, -89.57, 39.15, -81.96),
    "LA": (28.93, -94.04, 33.02, -88.82),
    "ME": (43.06, -71.08, 47.46, -66.95),
    "MD": (37.91, -79.49, 39.72, -75.05),
    "MA": (41.24, -73.51, 42.89, -69.93),
    "MI": (41.70, -90.42, 48.31, -82.41),
    "MN": (43.50, -97.24, 49.38, -89.49),
    "MS": (30.17, -91.66, 35.00, -88.10),
    "MO": (35.99, -95.77, 40.61, -89.10),
    "MT": (44.36, -116.05, 49.00, -104.04),
    "NE": (39.99, -104.05, 43.00, -95.31),
    "NV": (35.00, -120.01, 42.00, -114.04),
    "NH": (42.70, -72.56, 45.31, -70.70),
    "NJ": (38.93, -75.56, 41.36, -73.89),
    "NM": (31.33, -109.05, 37.00, -103.00),
    "NY": (40.50, -79.76, 45.02, -71.86),
    "NC": (33.84, -84.32, 36.59, -75.46),
    "ND": (45.94, -104.05, 49.00, -96.55),
    "OH": (38.40, -84.82, 42.33, -80.52),
    "OK": (33.62, -103.00, 37.00, -94.43),
    "OR": (41.99, -124.57, 46.29, -116.46),
    "PA": (39.72, -80.52, 42.27, -74.69),
    "RI": (41.15, -71.86, 42.02, -71.12),
    "SC": (32.05, -83.35, 35.22, -78.54),
    "SD": (42.48, -104.06, 45.94, -96.44),
    "TN": (34.98, -90.31, 36.68, -81.65),
    "TX": (25.84, -106.65, 36.50, -93.51),
    "UT": (36.99, -114.05, 42.00, -109.04),
    "VT": (42.73, -73.44, 45.02, -71.46),
    "VA": (36.54, -83.68, 39.47, -75.24),
    "WA": (45.54, -124.85, 49.00, -116.92),
    "WV": (37.20, -82.64, 40.64, -77.72),
    "WI": (42.49, -92.89, 47.31, -86.25),
    "WY": (40.99, -111.06, 45.01, -104.05),
    "AS": (-14.55, -171.09, -14.16, -169.42),
    "GU": (13.23, 144.62, 13.65, 144.96),
    "MP": (14.11, 144.89, 20.55, 146.06),
    "PR": (17.88, -67.95, 18.52, -65.22),
    "VI": (17.67, -65.09, 18.41, -64.56),
}

NEIGHBORS = {
    "AL": ["FL", "GA", "MS", "TN"],
    "AK": [],
    "AZ": ["CA", "CO", "NM", "NV", "UT"],
    "AR": ["LA", "MO", "MS", "OK", "TN", "TX"],
    "CA": ["AZ", "NV", "OR"],
    "CO": ["AZ", "KS", "NE", "NM", "OK", "UT", "WY"],
    "CT": ["MA", "NY", "RI"],
    "DE": ["MD", "NJ", "PA"],
    "DC": ["MD", "VA"],
    "FL": ["AL", "GA"],
    "GA": ["AL", "FL", "NC", "SC", "TN"],
    "HI": [],
    "ID": ["MT", "NV", "OR", "UT", "WA", "WY"],
    "IL": ["IA", "IN", "KY", "MO", "WI"],
    "IN": ["IL", "KY", "MI", "OH"],
    "IA": ["IL", "MN", "MO", "NE", "SD", "WI"],
    "KS": ["CO", "MO", "NE", "OK"],
    "KY": ["IL", "IN", "MO", "OH", "TN", "VA", "WV"],
    "LA": ["AR", "MS", "TX"],
    "ME": ["NH"],
    "MD": ["DE", "DC", "PA", "VA", "WV"],
    "MA": ["CT", "NH", "NY", "RI", "VT"],
    "MI": ["IN", "OH", "WI"],
    "MN": ["IA", "ND", "SD", "WI"],
    "MS": ["AL", "AR", "LA", "TN"],
    "MO": ["AR", "IA", "IL", "KS", "KY", "NE", "OK", "TN"],
    "MT": ["ID", "ND", "SD", "WY"],
    "NE": ["CO", "IA", "KS", "MO", "SD", "WY"],
    "NV": ["AZ", "CA", "ID", "OR", "UT"],
    "NH": ["MA", "ME", "VT"],
    "NJ": ["DE", "NY", "PA"],
    "NM": ["AZ", "CO", "OK", "TX", "UT"],
    "NY": ["CT", "MA", "NJ", "PA", "VT"],
    "NC": ["GA", "SC", "TN", "VA"],
    "ND": ["MN", "MT", "SD"],
    "OH": ["IN", "KY", "MI", "PA", "WV"],
    "OK": ["AR", "CO", "KS", "MO", "NM", "TX"],
    "OR": ["CA", "ID", "NV", "WA"],
    "PA": ["DE", "MD", "NJ", "NY", "OH", "WV"],
    "RI": ["CT", "MA"],
    "SC": ["GA", "NC"],
    "SD": ["IA", "MN", "MT", "ND", "NE", "WY"],
    "TN": ["AL", "AR", "GA", "KY", "MO", "MS", "NC", "VA"],
    "TX": ["AR", "LA", "NM", "OK"],
    "UT": ["AZ", "CO", "ID", "NV", "NM", "WY"],
    "VT": ["MA", "NH", "NY"],
    "VA": ["DC", "KY", "MD", "NC", "TN", "WV"],
    "WA": ["ID", "OR"],
    "WV": ["KY", "MD", "OH", "PA", "VA"],
    "WI": ["IL", "IA", "MI", "MN"],
    "WY": ["CO", "ID", "MT", "NE", "SD", "UT"],
    "AS": [],
    "GU": [],
    "MP": [],
    "PR": [],
    "VI": [],
}

NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "AS": "American Samoa",
    "GU": "Guam",
    "MP": "Northern Mariana Islands",
    "PR": "Puerto Rico",
    "VI": "U.S. Virgin Islands",
}


def S(
    sid: str,
    label: str,
    mask: str | None = None,
    *,
    kind: str = "passenger",
    status: str = "current",
    issued: str = "",
    skip: list[str] | None = None,
    ioq_only: list[int] | None = None,
    skip_at: dict[int, list[str]] | None = None,
    weight: float = 1.0,
    example: str = "",
    regex: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": sid,
        "label": label,
        "kind": kind,
        "status": status,
        "issued": issued,
        "mask": mask,
        "weight": weight,
        "example": example,
    }
    if skip:
        item["skip"] = skip
    if ioq_only is not None:
        item["ioqOnly"] = ioq_only
    if skip_at:
        item["skipAt"] = {str(index): letters for index, letters in skip_at.items()}
    if regex:
        item["regex"] = regex
    return item


# Serial series per jurisdiction. Current passenger first, then still-valid older
# passenger, then common non-passenger. California lists the ~10 everyday series.
SERIES: dict[str, list[dict[str, object]]] = {
    "AL": [
        S("al-pass-1", "Passenger, 1-digit county", "#LL####", issued="2022-present", skip=IOQ, example="1AB2345"),
        S("al-pass-2", "Passenger, 2-digit county", "##LL###", issued="2022-present", skip=IOQ, example="12AB345"),
        S("al-pass-alt", "Passenger alternate", "#L##L##", issued="2022-present", skip=IOQ, example="1A23B45", weight=0.9),
        S("al-pass-alt2", "Passenger alternate", "##L##L#", issued="2022-present", skip=IOQ, example="12A34B5", weight=0.9),
        S("al-opt-ab12345", "Optional God Bless America", "LL#####", status="still_valid", issued="2007-2013", example="AB12345", weight=0.4),
        S("al-opt-12345ab", "Optional God Bless America", "#####LL", status="still_valid", issued="2007-2013", example="12345AB", weight=0.4),
    ],
    "AK": [
        S("ak-pass", "Passenger", "LLL###", issued="2010-present", skip=IOQ, example="ABC123"),
    ],
    "AZ": [
        S("az-pass-2021", "Passenger alphabet soup", "AAA#AA", issued="2021-present", skip=IOQU, example="ABC1DE", weight=0.45),
        S("az-pass-2020", "Passenger 2020-2021", "AAA#AAA", status="still_valid", issued="2020-2021", skip=IOQU, example="ABC1DEF", weight=0.5),
        S("az-pass-2008", "Passenger 2008-2020", "LLL####", status="still_valid", issued="2008-2020", skip=IOQU, example="ABC1234"),
        S("az-pass-1996", "Passenger 1996-2008", "###LLL", status="still_valid", issued="1996-2008", skip=IOQU, example="123ABC"),
        S("az-pass-1980", "Passenger 1980-1996", "LLL###", status="still_valid", issued="1980-1996", skip=IOQU, example="ABC123", weight=0.7),
    ],
    "AR": [
        S("ar-pass", "Passenger", "LLL##L", issued="2021-present", skip=["O", "Q"], example="ABC12D"),
        S("ar-pass-2006", "Passenger 2006-2021", "###LLL", status="still_valid", issued="2006-2021", skip=["O", "Q"], example="123ABC"),
    ],
    "CA": [
        S("ca-pass-2026", "Passenger 2026–present", "###LLL#", issued="2026-present", skip=IOQ, ioq_only=[4], example="123ABC1"),
        S("ca-pass-1980", "Passenger 1980–2026", "#LLL###", status="still_valid", issued="1980-2026", skip=IOQ, ioq_only=[2], example="7ABC123", weight=1.05),
        S("ca-pass-1969", "Passenger 1969–1980", "###LLL", status="still_valid", issued="1969-1980", skip=IOQ, example="123ABC", weight=0.7),
        S("ca-pass-1963", "Passenger 1963–1969", "LLL###", status="still_valid", issued="1963-1969", example="ABC123", weight=0.65),
        S("ca-comm-2010", "Commercial 2010–present", "#####L#", kind="commercial", issued="2010-present", skip=IOQ, example="12345A1"),
        S("ca-comm-1976", "Commercial 1976–2010", "#L#####", kind="commercial", status="still_valid", issued="1976-2010", skip=IOQ, example="1A12345", weight=0.9),
        S("ca-mc-1982", "Motorcycle 1982–present", "##L####", kind="motorcycle", issued="1982-present", skip=IOQ, example="12A1234"),
        S("ca-mc-1970", "Motorcycle 1970–1987", "#L####", kind="motorcycle", status="still_valid", issued="1970-1987", skip=IOQ, example="1A1234", weight=0.7),
        S("ca-pti", "Permanent trailer", "4LL####", kind="trailer", issued="2001-present", skip=IOQ, example="4AB1234"),
        S("ca-trailer", "Trailer", "1LL####", kind="trailer", issued="1983-present", skip=IOQ, example="1AB1234"),
        S("ca-apportioned", "Apportioned", "LL#####", kind="commercial", issued="1982-present", regex="^[A-Z]P[0-9]{5}$", example="AP12345", weight=0.8),
        S("ca-temp", "Temporary paper", "LL##L##", kind="temporary", issued="2019-present", skip=IOQ, example="AB12C34", weight=0.7),
        S("ca-tractor", "Tractor trailer", "9L#####", kind="commercial", issued="1987-present", skip=IOQ, example="9A12345", weight=0.85),
        S("ca-disabled", "Disabled person", None, kind="disabled", issued="1995-present", regex="^([0-9]{5}DP|DP[0-9]{5}|DP[A-Z][0-9]{4}|[0-9]{4}[A-Z]DP|DP[0-9]{3}[A-Z]{2}|[A-Z]{2}[0-9]{3}DP)$", example="AB123DP", weight=0.8),
        S("ca-legacy", "Legacy gold-on-black", "L###L#", kind="specialty", issued="2015-present", example="B123A4", weight=0.45),
    ],
    "CO": [
        S("co-pass", "Passenger", "LLLL##", issued="2018-present", example="ABCD12"),
        S("co-pass-2015", "Passenger 2015-2018", "LLL###", status="still_valid", issued="2015-2018", example="ABC123"),
        S("co-pass-2000", "Passenger 2000-2015", "###LLL", status="still_valid", issued="2000-2015", example="123ABC"),
        S("co-pass-old", "Passenger county-coded", "LL####", status="still_valid", issued="1977-2000", example="AB1234", weight=0.55),
    ],
    "CT": [
        S("ct-pass", "Passenger", "LL#####", issued="2015-present", skip=IOQ, example="AB12345"),
        S("ct-pass-2013", "Passenger 2013-2015", "#LLLL#", status="still_valid", issued="2013-2015", skip=IOQ, example="1ABCD2", weight=0.7),
        S("ct-pass-2000", "Passenger 2000-2013", "###LLL", status="still_valid", issued="2000-2013", example="123ABC"),
    ],
    "DE": [
        S("de-pass-6", "Passenger", "######", issued="1969-present", example="123456", weight=0.85),
        S("de-pass-5", "Passenger 5-digit", "#####", issued="1969-present", example="12345", weight=0.7),
        S("de-pass-4", "Passenger 4-digit", "####", issued="1969-present", example="1234", weight=0.55),
        S("de-pass-3", "Passenger 3-digit", "###", issued="1969-present", example="123", weight=0.35),
    ],
    "DC": [
        S("dc-pass", "Passenger", "LL####", issued="2017-present", skip=IOQ, example="AB1234"),
        S("dc-pass-old", "Passenger numeric", "######", status="still_valid", issued="1991-1997", example="123456", weight=0.5),
    ],
    "FL": [
        S("fl-pass", "Passenger Sunshine State", "LLLL##", issued="2003-present", skip=["O"], example="ABCD12"),
        S("fl-pass-county", "Passenger county name", "##LLLL", issued="2003-present", skip=["O"], example="12ABCD", weight=0.95),
        S("fl-igwt", "In God We Trust", "LL##LL", issued="2008-present", skip=["O"], example="AB12CD", weight=0.8),
        S("fl-old-a123bc", "Former passenger", "L###LL", status="still_valid", skip=["O"], example="A123BC", weight=0.45),
        S("fl-old-123abc", "Former passenger", "###LLL", status="still_valid", skip=["O"], example="123ABC", weight=0.45),
        S("fl-old-abc123", "Former passenger", "LLL###", status="still_valid", skip=["O"], example="ABC123", weight=0.45),
        S("fl-old-1234ab", "Former passenger", "####LL", status="still_valid", skip=["O"], example="1234AB", weight=0.45),
        S("fl-old-a12bcd", "Former passenger", "L##LLL", status="still_valid", skip=["O"], example="A12BCD", weight=0.4),
        S("fl-old-ab123c", "Former passenger", "LL###L", status="still_valid", skip=["O"], example="AB123C", weight=0.4),
        S("fl-old-a1234b", "Former passenger", "L####L", status="still_valid", skip=["O"], example="A1234B", weight=0.4),
    ],
    "GA": [
        S("ga-pass", "Passenger", "LLL####", issued="2012-present", skip=["O"], example="ABC1234"),
        S("ga-alt-2026", "250th anniversary", "LLL#LL", issued="2026-present", skip=["O"], example="ABC1DE", weight=0.6),
        S("ga-alt-2026b", "250th anniversary", "LL#LLL", issued="2026-present", skip=["O"], example="AB1CDE", weight=0.6),
        S("ga-old-123abc", "Passenger 1997-2003", "###LLL", status="still_valid", issued="1997-2003", example="123ABC", weight=0.55),
    ],
    "HI": [
        S("hi-pass", "Passenger, county-coded", "LLL###", issued="1991-present", skip=IOQ, example="ABC123"),
    ],
    "ID": [
        S("id-pass", "Passenger county + U", None, issued="2020-present", regex="^[0-9]{0,2}[A-Z]{1,3}[0-9]{1,4}[UPV]$", example="1A1234U", weight=0.7),
        S("id-pass-old", "Passenger county numeric", None, status="still_valid", issued="1991-2020", regex="^[0-9]?[A-Z][0-9]{3,6}$", example="1A12345", weight=0.4),
    ],
    "IL": [
        S("il-pass", "Passenger", "LL#####", issued="2017-present", skip=["I", "O"], example="AB12345"),
        S("il-pass-2017", "Passenger 2017", "LL#####", status="still_valid", issued="2017", skip=["I", "O"], example="AB12345", weight=0.5),
        S("il-pass-2006", "Passenger 2006-2016", "L######", status="still_valid", issued="2006-2016", skip=["I", "O"], example="A123456", weight=0.6),
        S("il-pass-2001", "Passenger 2001-2006", "#######", status="still_valid", issued="2001-2006", example="1234567", weight=0.55),
    ],
    "IN": [
        S("in-pass-7", "Passenger random 7", "###L###", issued="2017-present", example="123A456", weight=0.7),
        S("in-pass-6", "Passenger random 6", "###LLL", issued="2017-present", example="123ABC", weight=0.55),
        S("in-pass-5", "Passenger random 5", "###LL", issued="2017-present", example="123AB", weight=0.35),
        S("in-igwt", "In God We Trust", "LLL###", issued="2012-present", example="ABC123", weight=0.7),
    ],
    "IA": [
        S("ia-pass", "Passenger", "LLL###", issued="2018-present", example="ABC123"),
        S("ia-pass-1997", "Passenger 1997-2018", "###LLL", status="still_valid", issued="1997-2018", example="123ABC"),
    ],
    "KS": [
        S("ks-pass", "Passenger", "####LLL", issued="2024-present", skip=IOQ, example="1234ABC"),
        S("ks-pass-2018", "Passenger 2018-2023", "###LLL", status="still_valid", issued="2018-2023", skip=IOQ, example="123ABC"),
    ],
    "KY": [
        S("ky-pass", "Passenger", "L#L###", issued="2020-present", skip=IOQU, example="A1B234", weight=0.9),
        S("ky-pass-abc", "Passenger", "LLL###", issued="2020-present", skip=IOQU, example="ABC123"),
        S("ky-old", "Passenger 2005-2020", "###LLL", status="still_valid", issued="2005-2020", skip=IOQU, example="123ABC"),
    ],
    "LA": [
        S("la-pass", "Passenger", "###LLL", issued="2016-present", example="123ABC"),
        S("la-old", "Passenger 1993-2015", "LLL###", status="still_valid", issued="1993-2015", example="ABC123", weight=0.7),
    ],
    "ME": [
        S("me-pass", "Passenger", "###LLL", issued="2025-present", skip=["I", "O"], example="123ABC"),
        S("me-old", "Passenger older", "####LL", status="still_valid", skip=["I", "O"], example="1234AB", weight=0.55),
    ],
    "MD": [
        S("md-pass", "Passenger", "#LL####", issued="2016-present", skip=["I", "O", "Q", "U", "E", "F"], example="1AB2345"),
        S("md-pass-2010", "Passenger 2010-2016", "#L#####", status="still_valid", issued="2010-2016", skip=IOQU, example="1A12345", weight=0.55),
        S("md-pass-2005", "Passenger 2005-2010", "#LLL##", status="still_valid", issued="2004-2010", example="1ABC23", weight=0.45),
        S("md-pass-1986", "Passenger 1986-2004", "LLL###", status="still_valid", issued="1986-2004", example="ABC123", weight=0.65),
    ],
    "MA": [
        S("ma-pass", "Passenger Jan-Sep", "#LLL##", issued="1988-present", skip=IOQU, example="1ABC23"),
        S("ma-pass-oct", "Passenger October", "###L##", issued="1988-present", skip=IOQU, example="123A40", weight=0.7),
        S("ma-old-123abc", "Passenger older", "###LLL", status="still_valid", skip=IOQU, example="123ABC", weight=0.5),
        S("ma-old-1234ab", "Passenger older", "####LL", status="still_valid", skip=IOQU, example="1234AB", weight=0.45),
        S("ma-old-12ab34", "Passenger older", "##LL##", status="still_valid", skip=IOQU, example="12AB34", weight=0.45),
        S("ma-old-numeric", "Passenger numeric", "######", status="still_valid", issued="1977-1993", example="123456", weight=0.4),
    ],
    "MI": [
        S("mi-pass", "Passenger", "LLL####", issued="2013-present", skip=["I", "O"], example="ABC1234"),
        S("mi-opt-12abc3", "Water Wonderland", "##LLL#", kind="specialty", issued="2024-present", skip=["I", "O"], example="12ABC3", weight=0.55),
        S("mi-opt-1abc23", "Water-Winter Wonderland", "#LLL##", kind="specialty", issued="2021-present", skip=["I", "O"], example="1ABC23", weight=0.5),
        S("mi-opt-abc123", "Mackinac Bridge", "LLL###", kind="specialty", issued="2014-present", skip=["I", "O"], example="ABC123", weight=0.5),
    ],
    "MN": [
        S("mn-pass-num", "Passenger", "###LLL", issued="2009-present", skip=IOQ, example="123ABC"),
        S("mn-pass-let", "Passenger swapped", "LLL###", issued="2009-present", skip=IOQ, example="ABC123"),
    ],
    "MS": [
        S("ms-pass", "Passenger", "LLL###", issued="2024-present", skip=["O"], example="ABC123"),
    ],
    "MO": [
        S("mo-pass", "Passenger month-coded", "LL#L#L", issued="2018-present", skip=IOQ, example="AB1C2D"),
        S("mo-old", "Passenger older", "###LLL", status="still_valid", skip=IOQ, example="123ABC", weight=0.5),
    ],
    "MT": [
        S("mt-pass-1", "Passenger 1-digit county", None, issued="2025-present", regex="^[0-9][A-Z]{2}[0-9]{4}$", skip=["I", "O", "Q", "R", "V"], example="1AB1234"),
        S("mt-pass-2", "Passenger 2-digit county", None, issued="2025-present", regex="^[0-9]{2}[A-Z]{2}[0-9]{3}$", skip=["I", "O", "Q", "R", "V"], example="12AB123"),
        S("mt-opt", "Optional replica", "LLL###", kind="specialty", issued="2010-present", example="ABC123", weight=0.5),
        S("mt-old", "Passenger older", None, status="still_valid", regex="^[0-9]{1,2}[0-9]{4}[A-Z]$", example="112345A", weight=0.4),
    ],
    "NE": [
        S("ne-metro", "Passenger Douglas/Lancaster/Sarpy", "LLL###", issued="2023-present", skip=["I", "M", "O", "Q", "W", "X"], example="ABC123"),
        S("ne-county", "Passenger county-coded", None, issued="2023-present", regex="^[0-9]{1,2}[A-Z]{1,2}[0-9]{2,4}$", skip=["I", "M", "O", "Q", "W", "X"], example="1A1234", weight=0.65),
    ],
    "NV": [
        S("nv-pass-a", "Passenger", "####L#", issued="2016-present", skip=IOQ, example="4321A5", weight=0.85),
        S("nv-pass-b", "Passenger", "###L##", issued="2016-present", skip=IOQ, example="345A12", weight=0.8),
        S("nv-pass-c", "Passenger", "##L###", issued="2016-present", skip=IOQ, example="12A345", weight=0.8),
        S("nv-old", "Passenger 2001-2017", "###LLL", status="still_valid", issued="2001-2017", skip=IOQ, example="123ABC"),
        S("nv-old-abc", "Passenger older", "LLL###", status="still_valid", skip=IOQ, example="ABC123", weight=0.5),
    ],
    "NH": [
        S("nh-pass", "Passenger", "#######", issued="2000-present", example="1234567"),
        S("nh-old", "Passenger 1999", "######", status="still_valid", issued="1999", example="123456", weight=0.45),
        S("nh-old-abc", "Passenger older", "LLL###", status="still_valid", example="ABC123", weight=0.4),
    ],
    "NJ": [
        S("nj-pass", "Passenger", "L##LLL", issued="2010-present", skip=IOQ, example="D12ABC"),
        S("nj-pass-1999", "Passenger 1999-2010", "LLL##L", status="still_valid", issued="1999-2010", skip=IOQ, example="ABC12D"),
        S("nj-pass-1993", "Passenger 1993-1999", "LL###L", status="still_valid", issued="1993-1999", skip=IOQ, example="AB123C"),
        S("nj-pass-1992", "Passenger 1992-1993", "LLL####", status="still_valid", issued="1992-1993", skip=IOQ, example="ABC1234", weight=0.55),
        S("nj-old-abc123", "Passenger older", "LLL###", status="still_valid", skip=IOQ, example="ABC123", weight=0.5),
        S("nj-old-123abc", "Passenger older", "###LLL", status="still_valid", skip=IOQ, example="123ABC", weight=0.5),
    ],
    "NM": [
        S("nm-pass", "Passenger yellow", "###LLL", issued="1989-present", skip=IOQU + ["V"], example="123ABC"),
        S("nm-alt", "Passenger turquoise", "LLL###", issued="2010-present", skip=IOQU + ["V"], example="ABC123"),
        S("nm-chile", "Chile Capital", "LLLL##", issued="2017-present", skip=IOQU + ["V"], example="ABCD12", weight=0.7),
    ],
    "NY": [
        S("ny-pass", "Passenger", "LLL####", issued="2020-present", skip=IOQ, example="ABC1234"),
        S("ny-old-6", "Passenger 6-character", "LLL###", status="still_valid", skip=IOQ, example="ABC123", weight=0.5),
    ],
    "NC": [
        S("nc-pass", "Passenger", "LLL####", issued="1985-present", skip=["G", "I", "O", "Q", "U"], example="ABC1234"),
        S("nc-old", "Passenger 1982-1985", "LLL###", status="still_valid", issued="1982-1985", skip=["G", "I", "O", "Q", "U"], example="ABC123", weight=0.5),
    ],
    "ND": [
        S("nd-pass", "Passenger", "###LLL", issued="2016-present", example="123ABC"),
    ],
    "OH": [
        S("oh-pass", "Passenger", "LLL####", issued="2004-present", skip=["I", "O"], ioq_only=[1], example="ABC1234"),
        S("oh-old-ab12cd", "Bicentennial", "LL##LL", status="still_valid", issued="2001-2003", example="AB12CD", weight=0.4),
    ],
    "OK": [
        S("ok-pass", "Passenger", "LLL###", issued="2024-present", example="ABC123"),
        S("ok-old", "Passenger 2017-2024", "LLL###", status="still_valid", issued="2017-2024", example="ABC123", weight=0.6),
    ],
    "OR": [
        S("or-pass", "Passenger", "###LLL", issued="2004-present", skip=["I", "O"], example="123ABC"),
        S("or-old", "Passenger 1990-2004", "LLL###", status="still_valid", issued="1990-2004", skip=["I", "O"], example="ABC123"),
    ],
    "PA": [
        S("pa-pass", "Passenger", "LLL####", issued="2025-present", skip=IOQU, skip_at={1: ["A", "E"]}, example="NBC1234"),
        S("pa-old", "Passenger 1999-2004", "LLL####", status="still_valid", issued="1999-2025", skip=IOQU, skip_at={1: ["A", "E"]}, example="ABC1234", weight=0.8),
    ],
    "RI": [
        S("ri-pass", "Passenger", "#LL###", issued="2023-present", skip=["O"], example="1AB234"),
        S("ri-old-6", "Passenger numeric", "######", status="still_valid", example="123456", weight=0.35),
        S("ri-old-ll", "Passenger older", "LL###", status="still_valid", skip=["O"], example="AB123", weight=0.35),
    ],
    "SC": [
        S("sc-pass", "Passenger", "###LLL", issued="2026-present", example="123ABC"),
        S("sc-old", "Passenger 2016-2026", "LLL###", status="still_valid", issued="2016-2026", example="ABC123"),
        S("sc-igwt", "In God We Trust", "####LL", kind="specialty", issued="2016-present", example="1234AB", weight=0.55),
    ],
    "SD": [
        S("sd-pass-1", "Passenger 1-digit county", None, issued="2023-present", regex="^[0-9][A-Z][0-9]{4}$", skip=IOQ, example="1A1234", weight=0.7),
        S("sd-pass-1b", "Passenger 1-digit county letters", None, issued="2023-present", regex="^[0-9][A-Z]{2}[0-9]{3}$", skip=IOQ, example="1AB123", weight=0.7),
        S("sd-pass-2", "Passenger 2-digit county", None, issued="2023-present", regex="^[0-9]{2}[A-Z][0-9]{3}$", skip=IOQ, example="12A123", weight=0.7),
    ],
    "TN": [
        S("tn-pass", "Passenger", "LLL####", issued="2023-present", skip=VOWELS, example="BCD1234"),
        S("tn-igwt", "In God We Trust", "###LLLL", issued="2023-present", skip=VOWELS, example="123BCDE", weight=0.75),
        S("tn-old", "Passenger older", "###LLL", status="still_valid", skip=VOWELS, example="123BCD", weight=0.5),
    ],
    "TX": [
        S("tx-pass", "Passenger", "LLL####", issued="2012-present", skip=TX_SKIP, example="BCD1234"),
        S("tx-old-2009", "Passenger 2009-2012", "LL#L###", status="still_valid", issued="2009-2012", skip=TX_SKIP, example="BC1D234"),
        S("tx-old-abc", "Passenger older", "LLL###", status="still_valid", skip=TX_SKIP, example="BCD123", weight=0.5),
        S("tx-old-123abc", "Passenger older", "###LLL", status="still_valid", skip=TX_SKIP, example="123BCD", weight=0.45),
    ],
    "UT": [
        S("ut-pass", "Passenger Life Elevated", "L###LL", issued="2007-present", skip=IOQ, example="A123BC"),
        S("ut-igwt", "In God We Trust", "#LLL#", kind="specialty", issued="2023-present", skip=IOQ, example="1ABC2", weight=0.55),
        S("ut-igwt-old", "In God We Trust older", "#L#LL", kind="specialty", status="still_valid", issued="2018-2023", skip=IOQ, example="1A2BC", weight=0.45),
        S("ut-old-123abc", "Passenger 1985-2008", "###LLL", status="still_valid", issued="1985-2008", skip=IOQ, example="123ABC", weight=0.55),
        S("ut-old-abc123", "Passenger 1972-1985", "LLL###", status="still_valid", issued="1972-1985", skip=IOQ, example="ABC123", weight=0.5),
    ],
    "VT": [
        S("vt-pass", "Passenger", "LLL###", issued="1990-present", skip=IOQU + ["J"], example="ABC123"),
    ],
    "VA": [
        S("va-pass", "Passenger", "LLL####", issued="1994-present", skip=IOQ, example="ABC1234"),
        S("va-old", "Passenger 1979-1993", "LLL###", status="still_valid", issued="1979-1993", skip=IOQ, example="ABC123", weight=0.55),
    ],
    "WA": [
        S("wa-pass", "Passenger", "LLL####", issued="2010-present", skip_at={2: IOQ}, example="ABC1234"),
        S("wa-old", "Passenger 1987-2010", "###LLL", status="still_valid", issued="1987-2010", skip=IOQ, example="123ABC"),
    ],
    "WV": [
        S("wv-pass-a", "Passenger month-coded", None, issued="2023-present", regex="^[1-9OND][0-9][A-Z][0-9]{4}$", example="11A2345", weight=0.8),
        S("wv-pass-b", "Passenger month-coded letters", None, issued="2023-present", regex="^[1-9OND][A-Z]{2}[0-9]{4}$", example="1AB1234", weight=0.8),
        S("wv-old", "Passenger 2002-2023", None, status="still_valid", issued="2002-2023", regex="^[1-9OND][A-Z]{2}[0-9]{3}$", example="1AB123", weight=0.5),
    ],
    "WI": [
        S("wi-pass", "Passenger", "LLL####", issued="2017-present", skip=IOQ, example="ABC1234"),
        S("wi-old", "Passenger 2000-2017", "###LLL", status="still_valid", issued="2000-2017", skip=IOQ, example="123ABC"),
        S("wi-older", "Passenger older", "LLL###", status="still_valid", skip=IOQ, example="ABC123", weight=0.45),
    ],
    "WY": [
        S("wy-pass", "Passenger county-coded", None, issued="2024-present", regex="^[0-9]{1,2}[A-Z][0-9]{3,4}[A-Z]?$", example="1A123A", weight=0.65),
    ],
    "AS": [
        S("as-pass", "Passenger", "####", issued="2011-present", example="1234", weight=0.4),
    ],
    "GU": [
        S("gu-pass", "Passenger village-coded", "LL####", issued="2009-present", example="AB1234"),
        S("gu-old", "Passenger older", "LLL####", status="still_valid", example="ABC1234", weight=0.45),
    ],
    "MP": [
        S("mp-pass", "Passenger", "LLL###", issued="1989-present", example="ABC123"),
    ],
    "PR": [
        S("pr-pass", "Passenger", "LLL###", issued="2023-present", example="ABC123"),
    ],
    "VI": [
        S("vi-pass", "Passenger island-coded", "LLL###", issued="2023-present", example="ABC123"),
    ],
}


def jurisdictions() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for code, name in NAMES.items():
        items.append(
            {
                "code": code,
                "name": name,
                "neighbors": list(NEIGHBORS.get(code, [])),
                "bbox": list(BBOX[code]),
                "series": SERIES[code],
            }
        )
    return items
