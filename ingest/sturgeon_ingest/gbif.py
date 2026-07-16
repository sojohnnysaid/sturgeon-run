"""GBIF fetch + normalization. Occurrences of the target taxon in the bbox."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("sturgeon_ingest.gbif")

SPECIES_MATCH_URL = "https://api.gbif.org/v1/species/match"
OCCURRENCE_SEARCH_URL = "https://api.gbif.org/v1/occurrence/search"

PAGE_LIMIT = 300
# GBIF caps offset+limit at 100000.
MAX_OFFSET = 100_000
TIMEOUT = 60

OCCURRENCE_FIELDS = (
    "key",
    "decimalLatitude",
    "decimalLongitude",
    "eventDate",
    "year",
    "basisOfRecord",
    "datasetKey",
    "coordinateUncertaintyInMeters",
    "institutionCode",
)


def match_taxon(name: str, session: Optional[requests.Session] = None) -> dict:
    """Resolve a scientific name to a GBIF backbone match. Returns the JSON."""
    sess = session or requests
    resp = sess.get(SPECIES_MATCH_URL, params={"name": name}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("usageKey"):
        raise RuntimeError(f"GBIF species/match returned no usageKey for {name!r}: {data}")
    log.info(
        "GBIF matched %r -> usageKey=%s (%s, %s)",
        name,
        data.get("usageKey"),
        data.get("scientificName"),
        data.get("rank"),
    )
    return data


def fetch_occurrences_live(
    taxon_key: int,
    bbox: tuple[float, float, float, float],
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Page all occurrences for the taxon inside bbox. Returns raw GBIF records."""
    sess = session or requests.Session()
    min_lon, min_lat, max_lon, max_lat = bbox
    records: list[dict] = []
    offset = 0
    while True:
        params = {
            "taxonKey": taxon_key,
            "hasCoordinate": "true",
            "decimalLatitude": f"{min_lat},{max_lat}",
            "decimalLongitude": f"{min_lon},{max_lon}",
            "limit": PAGE_LIMIT,
            "offset": offset,
        }
        resp = sess.get(OCCURRENCE_SEARCH_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("results", [])
        records.extend(batch)
        log.info(
            "GBIF occurrence page offset=%d got=%d total_so_far=%d endOfRecords=%s count=%s",
            offset,
            len(batch),
            len(records),
            payload.get("endOfRecords"),
            payload.get("count"),
        )
        if payload.get("endOfRecords"):
            break
        offset += PAGE_LIMIT
        if offset >= MAX_OFFSET:
            log.warning("GBIF offset cap %d reached; stopping paging.", MAX_OFFSET)
            break
    return records


def occurrences_snapshot_path(snapshot_dir: Path, taxon_key: int) -> Path:
    """Per-taxon occurrence snapshot file, so multi-species runs stay reloadable
    offline without collisions."""
    return snapshot_dir / f"gbif_occurrences_{taxon_key}.json"


def taxa_manifest_path(snapshot_dir: Path) -> Path:
    """Manifest mapping scientific_name -> resolved GBIF backbone metadata.
    Lets snapshot mode resolve taxon keys WITHOUT any live GBIF call."""
    return snapshot_dir / "gbif_taxa.json"


def save_taxa_manifest(manifest: dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Wrote GBIF taxa manifest: %s (%d taxa)", path, len(manifest))


def load_taxa_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise FileNotFoundError(f"GBIF taxa manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    log.info("Loaded GBIF taxa manifest: %s (%d taxa)", path, len(data))
    return data


def save_snapshot(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")
    log.info("Wrote GBIF snapshot: %s (%d records)", path, len(records))


def load_snapshot(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"GBIF snapshot not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    log.info("Loaded GBIF snapshot: %s (%d records)", path, len(data))
    return data


def normalize(rec: dict) -> dict:
    """Project a raw GBIF occurrence to our normalized shape."""
    return {
        "gbif_id": rec.get("key"),
        "decimalLatitude": rec.get("decimalLatitude"),
        "decimalLongitude": rec.get("decimalLongitude"),
        "eventDate": rec.get("eventDate"),
        "year": rec.get("year"),
        "basisOfRecord": rec.get("basisOfRecord"),
        "datasetKey": rec.get("datasetKey"),
        "coordinateUncertaintyInMeters": rec.get("coordinateUncertaintyInMeters"),
        "institutionCode": rec.get("institutionCode"),
    }
