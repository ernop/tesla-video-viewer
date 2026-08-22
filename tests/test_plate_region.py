from __future__ import annotations

from app.plate_region import classify_plate, catalog, dump_series_json
from app.us_plate_data import NAMES, SERIES


STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]


def test_catalog_covers_every_state_and_dc() -> None:
    codes = {item["code"] for item in catalog()}
    assert set(STATES).issubset(codes)
    assert "DC" in codes
    assert codes == set(NAMES)
    assert set(SERIES) == set(NAMES)
    for code in STATES + ["DC"]:
        assert SERIES[code], code


def test_california_has_everyday_series() -> None:
    kinds = {item["kind"] for item in SERIES["CA"]}
    labels = [str(item["label"]) for item in SERIES["CA"]]
    assert len(SERIES["CA"]) >= 10
    assert {"passenger", "commercial", "motorcycle", "trailer"}.issubset(kinds)
    assert any("1980" in label for label in labels)
    assert any("2026" in label for label in labels)


def test_california_passenger_1980_is_distinctive() -> None:
    hit = classify_plate("7ABC123")
    assert hit is not None
    assert hit["code"] == "CA"
    assert hit["confidence"] >= 0.85
    assert "1980" in hit["seriesLabel"]


def test_california_passenger_2026_and_letter_rules() -> None:
    current = classify_plate("123ABC1")
    assert current is not None
    assert current["code"] == "CA"
    assert "2026" in current["seriesLabel"]
    middle_i = classify_plate("7PIE123")
    assert middle_i is not None
    assert middle_i["code"] == "CA"
    leading_i = classify_plate("7IAA123")
    assert leading_i is None or leading_i["code"] != "CA" or leading_i["kind"] != "passenger"


def test_california_commercial_and_motorcycle() -> None:
    commercial = classify_plate("12345A1", lat=37.33, lon=-122.03)
    assert commercial is not None
    assert commercial["code"] == "CA"
    assert commercial["kind"] == "commercial"
    motorcycle = classify_plate("12A1234", lat=37.33, lon=-122.03)
    assert motorcycle is not None
    assert motorcycle["code"] == "CA"
    assert motorcycle["kind"] == "motorcycle"


def test_texas_skips_vowels() -> None:
    texas = classify_plate("BCD1234", lat=30.27, lon=-97.74)
    assert texas is not None
    assert texas["code"] == "TX"
    vowel = classify_plate("ABC1234", lat=30.27, lon=-97.74)
    assert vowel is None or vowel["code"] != "TX"


def test_maryland_current_format() -> None:
    hit = classify_plate("1AB2345", lat=39.29, lon=-76.61)
    assert hit is not None
    assert hit["code"] == "MD"


def test_kansas_and_missouri_are_distinctive() -> None:
    kansas = classify_plate("1234ABC")
    assert kansas is not None
    assert kansas["code"] == "KS"
    missouri = classify_plate("AB1C2D")
    assert missouri is not None
    assert missouri["code"] == "MO"


def test_ambiguous_seven_letter_format_keeps_alternatives() -> None:
    hit = classify_plate("HJK1234")
    assert hit is not None
    assert hit["alternatives"]
    assert hit["confidence"] < 0.7
    codes = {hit["code"], *[item["code"] for item in hit["alternatives"]]}
    assert codes & {"NY", "PA", "OH", "VA", "GA", "NC", "MI", "WA", "WI"}


def test_dump_series_json(tmp_path) -> None:
    path = dump_series_json(tmp_path / "us_plate_series.json")
    text = path.read_text(encoding="utf-8")
    assert "California" in text
    assert "1ABC123" in text or "7ABC123" in text
    assert "https://en.wikipedia.org" in text
