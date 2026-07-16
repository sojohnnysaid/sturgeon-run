"""Pure validation / parsing functions. No network, no DB. Unit-tested."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

# GBIF basisOfRecord values we drop.
EXCLUDED_BASIS_OF_RECORD = {"FOSSIL_SPECIMEN", "LIVING_SPECIMEN"}


def coords_valid(lat: Optional[float], lon: Optional[float]) -> bool:
    """True if both lat and lon are present and inside sane earth ranges."""
    if lat is None or lon is None:
        return False
    try:
        latf = float(lat)
        lonf = float(lon)
    except (TypeError, ValueError):
        return False
    if not (-90.0 <= latf <= 90.0):
        return False
    if not (-180.0 <= lonf <= 180.0):
        return False
    return True


def in_bbox(
    lat: float,
    lon: float,
    bbox: tuple[float, float, float, float],
) -> bool:
    """bbox = (min_lon, min_lat, max_lon, max_lat). Inclusive membership."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return (min_lon <= lon <= max_lon) and (min_lat <= lat <= max_lat)


def basis_excluded(basis_of_record: Optional[str]) -> bool:
    """True if this GBIF basisOfRecord should be dropped."""
    if basis_of_record is None:
        return False
    return basis_of_record.strip().upper() in EXCLUDED_BASIS_OF_RECORD


def parse_event_date(raw: Optional[str]) -> Optional[date]:
    """Parse a GBIF eventDate to a date (the start).

    Accepts:
      - ISO date: "1999-05-01"
      - ISO datetime: "1999-05-01T12:30:00" (with or without tz/millis)
      - interval: "1999-01-01/1999-12-31" (uses the start)
      - year-month: "1999-05"
      - year only: "1999"
    Returns None if missing or unparseable (record is KEPT with null date).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Interval: take the start side.
    if "/" in s:
        s = s.split("/", 1)[0].strip()
        if not s:
            return None
    # Full ISO datetime.
    candidate = s
    if "T" in candidate or " " in candidate:
        candidate = candidate.replace(" ", "T")
        # Normalise trailing Z for fromisoformat.
        norm = candidate.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(norm).date()
        except ValueError:
            # fall through to date-only handling on the date portion
            candidate = candidate.split("T", 1)[0]
    # Try plain ISO date.
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        pass
    # year-month
    parts = candidate.split("-")
    try:
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 1 and parts[0]:
            return date(int(parts[0]), 1, 1)
    except (ValueError, TypeError):
        return None
    return None


def dedup_by_key(records: list[dict], key_field: str) -> tuple[list[dict], int]:
    """Return (unique_records, duplicate_count) keeping first occurrence.

    Records with a falsy key value are kept (cannot dedup without a key).
    """
    seen: set = set()
    unique: list[dict] = []
    duplicates = 0
    for rec in records:
        k = rec.get(key_field)
        if k in (None, ""):
            unique.append(rec)
            continue
        if k in seen:
            duplicates += 1
            continue
        seen.add(k)
        unique.append(rec)
    return unique, duplicates
