"""Configuration loaded from environment. Never hardcode secrets or hosts."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _parse_bbox(raw: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError(f"HUDSON_BBOX must have 4 comma values, got: {raw!r}")
    min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    return (min_lon, min_lat, max_lon, max_lat)


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Repo layout: this file lives at ingest/sturgeon_ingest/config.py.
# The project data/ dir is ../../data relative to the package dir.
_PACKAGE_DIR = Path(__file__).resolve().parent
_INGEST_DIR = _PACKAGE_DIR.parent
_PROJECT_ROOT = _INGEST_DIR.parent
_DATA_DIR = _PROJECT_ROOT / "data"


def _parse_taxon_names(raw: str) -> list[str]:
    """Split a comma-separated taxon list, trimming blanks and de-duplicating
    while preserving order (so the flagship taxon stays species_id=1)."""
    seen: set[str] = set()
    names: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


@dataclass
class Config:
    database_url: str
    bbox: tuple[float, float, float, float]
    gbif_taxon_names: list[str]
    usgs_sites: list[str] = field(default_factory=list)
    use_snapshot: bool = False
    write_snapshot: bool = True
    data_dir: Path = _DATA_DIR

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def quality_report_path(self) -> Path:
        return self.data_dir / "quality-report.json"

    @classmethod
    def from_env(cls) -> "Config":
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required (set it in the environment).")
        bbox = _parse_bbox(os.environ.get("HUDSON_BBOX", "-74.10,40.55,-73.60,42.75"))
        # GBIF_TAXON_NAMES is a comma list (multi-species); defaults to the
        # single flagship taxon so existing single-species runs are unchanged.
        taxa = _parse_taxon_names(
            os.environ.get("GBIF_TAXON_NAMES", "Acipenser oxyrinchus")
        )
        if not taxa:
            raise RuntimeError("GBIF_TAXON_NAMES resolved to an empty list.")
        raw_sites = os.environ.get("USGS_SITES", "").strip()
        sites = [s.strip() for s in raw_sites.split(",") if s.strip()] if raw_sites else []
        return cls(
            database_url=database_url,
            bbox=bbox,
            gbif_taxon_names=taxa,
            usgs_sites=sites,
            use_snapshot=_bool_env("USE_SNAPSHOT", False),
            write_snapshot=_bool_env("WRITE_SNAPSHOT", True),
        )
