"""Classify OCR plate text as a US jurisdiction from serial format."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from app.us_plate_data import META, jurisdictions as load_jurisdictions

STATUS_WEIGHT = {"current": 1.0, "still_valid": 0.72, "former": 0.4}
HERE_BOOST = 2.4
NEIGHBOR_BOOST = 1.35
IOQ = set("IOQ")


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, dict[str, object]], tuple[dict[str, object], ...]]:
    items = load_jurisdictions()
    by_code = {str(item["code"]): item for item in items}
    flat: list[dict[str, object]] = []
    for item in items:
        for series in item["series"]:
            compiled = dict(series)
            compiled["code"] = item["code"]
            compiled["name"] = item["name"]
            regex = series.get("regex")
            mask = series.get("mask")
            compiled["_re"] = re.compile(str(regex)) if regex else None
            compiled["_mask"] = str(mask) if mask else None
            skip_at = series.get("skipAt") or {}
            compiled["_skip_at"] = {int(key): set(value) for key, value in skip_at.items()}
            compiled["_skip"] = set(series.get("skip") or [])
            compiled["_ioq_only"] = series.get("ioqOnly")
            flat.append(compiled)
    return by_code, tuple(flat)


def catalog() -> list[dict[str, object]]:
    return list(load_jurisdictions())


def dump_series_json(path: Path | None = None) -> Path:
    target = path or Path(__file__).resolve().parent / "data" / "us_plate_series.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": META, "jurisdictions": load_jurisdictions()}
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def _mask_ok(text: str, mask: str) -> bool:
    if len(text) != len(mask):
        return False
    for char, token in zip(text, mask, strict=True):
        if token == "#":
            if not char.isdigit():
                return False
        elif token == "L":
            if not char.isalpha():
                return False
        elif token == "A":
            if not char.isalnum():
                return False
        elif char != token:
            return False
    return True


def _letters_ok(text: str, series: dict[str, object]) -> bool:
    skip: set[str] = series["_skip"]
    skip_at: dict[int, set[str]] = series["_skip_at"]
    ioq_only = series["_ioq_only"]
    for index, char in enumerate(text):
        if not char.isalpha():
            continue
        if char in skip_at.get(index, set()):
            return False
        if ioq_only is not None and char in IOQ and char in skip:
            if index not in ioq_only:
                return False
            continue
        if char in skip:
            return False
    return True


def _match_series(text: str, series: dict[str, object]) -> bool:
    regex = series["_re"]
    mask = series["_mask"]
    if regex is not None:
        if regex.fullmatch(text) is None:
            return False
    elif mask:
        if not _mask_ok(text, mask):
            return False
    else:
        return False
    return _letters_ok(text, series)


def _literal_bonus(mask: str | None) -> float:
    if not mask:
        return 1.0
    literals = sum(1 for token in mask if token not in {"#", "L", "A"})
    return 1.0 + 0.18 * literals


def _status_weight(series: dict[str, object]) -> float:
    return STATUS_WEIGHT.get(str(series.get("status") or "current"), 0.5)


def jurisdictions_for_point(lat: float | None, lon: float | None) -> set[str]:
    if lat is None or lon is None:
        return set()
    here: set[str] = set()
    by_code, _ = _catalog()
    for code, item in by_code.items():
        min_lat, min_lon, max_lat, max_lon = item["bbox"]
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            here.add(code)
    return here


def _location_boost(code: str, here: set[str], neighbors_of: dict[str, set[str]]) -> float:
    if code in here:
        return HERE_BOOST
    nearby: set[str] = set()
    for home in here:
        nearby |= neighbors_of.get(home, set())
    if code in nearby:
        return NEIGHBOR_BOOST
    return 1.0


def _neighbors_map() -> dict[str, set[str]]:
    by_code, _ = _catalog()
    return {code: set(item["neighbors"]) for code, item in by_code.items()}


def classify_plate(
    text: str,
    lat: float | None = None,
    lon: float | None = None,
    *,
    limit: int = 4,
) -> dict[str, object] | None:
    plate = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    if len(plate) < 3:
        return None
    _, flat = _catalog()
    here = jurisdictions_for_point(lat, lon)
    neighbors_of = _neighbors_map()
    scored: list[tuple[float, dict[str, object]]] = []
    for series in flat:
        if not _match_series(plate, series):
            continue
        score = (
            float(series.get("weight") or 1.0)
            * _status_weight(series)
            * _location_boost(str(series["code"]), here, neighbors_of)
            * _literal_bonus(series["_mask"])
        )
        scored.append((score, series))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], str(item[1]["code"]), str(item[1]["id"])))
    best_score, best = scored[0]
    seen_codes: list[str] = []
    ranked: list[dict[str, object]] = []
    for score, series in scored:
        code = str(series["code"])
        if code in seen_codes:
            continue
        seen_codes.append(code)
        ranked.append(
            {
                "code": code,
                "name": series["name"],
                "seriesId": series["id"],
                "seriesLabel": series["label"],
                "kind": series["kind"],
                "confidence": round(score / best_score, 3),
            }
        )
        if len(ranked) >= limit:
            break
    unique_codes = {str(series["code"]) for _, series in scored}
    second = ranked[1]["confidence"] if len(ranked) > 1 else 0.0
    ratio = 1.0 / second if second else 99.0
    rare = len(unique_codes) == 1
    if rare:
        confidence = 0.93 if best.get("status") == "current" else 0.86
    elif ratio >= 3.0 and str(best["code"]) in here:
        confidence = 0.78
    elif ratio >= 2.2:
        confidence = 0.64
    elif ratio >= 1.5:
        confidence = 0.5
    else:
        confidence = 0.36
    top = ranked[0]
    return {
        "code": top["code"],
        "name": top["name"],
        "seriesId": top["seriesId"],
        "seriesLabel": top["seriesLabel"],
        "kind": top["kind"],
        "confidence": round(confidence, 3),
        "alternatives": ranked[1:],
    }


def packed_jurisdiction(info: dict[str, object] | None) -> dict[str, object]:
    if not info:
        return {
            "jurisdiction_code": "",
            "jurisdiction_name": "",
            "jurisdiction_series": "",
            "jurisdiction_kind": "",
            "jurisdiction_confidence": 0.0,
            "jurisdiction_alts": "[]",
        }
    return {
        "jurisdiction_code": str(info.get("code") or ""),
        "jurisdiction_name": str(info.get("name") or ""),
        "jurisdiction_series": str(info.get("seriesLabel") or ""),
        "jurisdiction_kind": str(info.get("kind") or ""),
        "jurisdiction_confidence": float(info.get("confidence") or 0),
        "jurisdiction_alts": json.dumps(info.get("alternatives") or []),
    }


def unpacked_jurisdiction(row: Mapping[str, object]) -> dict[str, object] | None:
    code = str(row.get("jurisdiction_code") or "").strip()
    if not code:
        return None
    raw_alts = row.get("jurisdiction_alts") or "[]"
    try:
        alternatives = json.loads(str(raw_alts))
    except json.JSONDecodeError:
        alternatives = []
    if not isinstance(alternatives, list):
        alternatives = []
    return {
        "code": code,
        "name": row.get("jurisdiction_name") or code,
        "seriesId": None,
        "seriesLabel": row.get("jurisdiction_series") or "",
        "kind": row.get("jurisdiction_kind") or "",
        "confidence": float(row.get("jurisdiction_confidence") or 0),
        "alternatives": alternatives,
    }
