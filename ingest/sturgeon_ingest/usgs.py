"""USGS NWIS fetch + parsing: Hudson stations (RDB) and instantaneous values (JSON)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("sturgeon_ingest.usgs")

SITE_URL = "https://waterservices.usgs.gov/nwis/site/"
IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
TIMEOUT = 120
IV_PARAMETERS = "00010,00060,00065,00300,00095,00480"
SITE_BATCH = 100


def fetch_sites_live(
    bbox: tuple[float, float, float, float],
    session: Optional[requests.Session] = None,
) -> str:
    """Fetch active IV stream sites inside bbox as raw RDB text."""
    sess = session or requests
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "format": "rdb",
        "bBox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "siteType": "ST",
        "hasDataTypeCd": "iv",
        "siteStatus": "active",
    }
    resp = sess.get(SITE_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    log.info("USGS site RDB fetched (%d bytes)", len(resp.text))
    return resp.text


def fetch_iv_live(
    sites: list[str],
    session: Optional[requests.Session] = None,
) -> dict:
    """Fetch instantaneous values for sites, batching. Returns a merged JSON dict."""
    sess = session or requests.Session()
    merged: Optional[dict] = None
    for i in range(0, len(sites), SITE_BATCH):
        batch = sites[i : i + SITE_BATCH]
        params = {
            "format": "json",
            "sites": ",".join(batch),
            "parameterCd": IV_PARAMETERS,
            "siteStatus": "all",
        }
        resp = sess.get(IV_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        ts = payload.get("value", {}).get("timeSeries", [])
        log.info("USGS IV batch %d-%d: %d sites -> %d timeSeries",
                 i, i + len(batch), len(batch), len(ts))
        if merged is None:
            merged = payload
        else:
            merged["value"]["timeSeries"].extend(ts)
    if merged is None:
        merged = {"value": {"timeSeries": []}}
    return merged


def save_sites_snapshot(rdb_text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rdb_text, encoding="utf-8")
    log.info("Wrote USGS sites snapshot: %s", path)


def save_iv_snapshot(iv_json: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(iv_json), encoding="utf-8")
    log.info("Wrote USGS IV snapshot: %s", path)


def load_sites_snapshot(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"USGS sites snapshot not found: {path}")
    log.info("Loaded USGS sites snapshot: %s", path)
    return path.read_text(encoding="utf-8")


def load_iv_snapshot(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"USGS IV snapshot not found: {path}")
    log.info("Loaded USGS IV snapshot: %s", path)
    return json.loads(path.read_text(encoding="utf-8"))


def parse_sites_rdb(rdb_text: str) -> list[dict]:
    """Parse USGS RDB site output into a list of dicts.

    RDB = tab-separated. Lines starting with '#' are comments. The first
    non-comment line is the column header; the next line is a format spec
    (e.g. '5s\t15s'); remaining lines are data.
    """
    header: Optional[list[str]] = None
    seen_format = False
    rows: list[dict] = []
    for line in rdb_text.splitlines():
        if line.startswith("#"):
            continue
        if not line.strip():
            continue
        fields = line.split("\t")
        if header is None:
            header = fields
            continue
        if not seen_format:
            # This is the format-spec line (e.g. '5s', '15s'); skip once.
            seen_format = True
            continue
        row = dict(zip(header, fields))
        rows.append(row)
    return rows


def normalize_site(row: dict) -> dict:
    """Project an RDB site row to normalized station shape (raw coords as str)."""
    return {
        "site_no": (row.get("site_no") or "").strip(),
        "station_nm": (row.get("station_nm") or "").strip(),
        "dec_lat_va": (row.get("dec_lat_va") or "").strip(),
        "dec_long_va": (row.get("dec_long_va") or "").strip(),
        "agency_cd": (row.get("agency_cd") or "").strip(),
        "site_tp_cd": (row.get("site_tp_cd") or "").strip(),
    }


def parse_iv_latest(iv_json: dict) -> list[dict]:
    """Extract the LATEST value per (site, parameter) from an IV JSON payload.

    Returns list of dicts: site_no, parameter_cd, parameter_name, unit, value,
    measured_at (ISO string), qualifiers.
    """
    out: list[dict] = []
    time_series = iv_json.get("value", {}).get("timeSeries", [])
    for ts in time_series:
        source_info = ts.get("sourceInfo", {})
        site_codes = source_info.get("siteCode", [])
        site_no = site_codes[0].get("value") if site_codes else None
        if not site_no:
            continue
        variable = ts.get("variable", {})
        var_codes = variable.get("variableCode", [])
        parameter_cd = var_codes[0].get("value") if var_codes else None
        parameter_name = variable.get("variableName")
        unit = variable.get("unit", {}).get("unitCode")
        for values_block in ts.get("values", []):
            samples = values_block.get("value", [])
            if not samples:
                continue
            # Latest by dateTime.
            latest = max(samples, key=lambda v: v.get("dateTime", ""))
            raw_val = latest.get("value")
            try:
                value = float(raw_val) if raw_val not in (None, "") else None
            except (TypeError, ValueError):
                value = None
            quals = latest.get("qualifiers")
            qual_str = ",".join(quals) if isinstance(quals, list) else quals
            out.append({
                "site_no": site_no,
                "parameter_cd": parameter_cd,
                "parameter_name": parameter_name,
                "unit": unit,
                "value": value,
                "measured_at": latest.get("dateTime"),
                "qualifiers": qual_str,
            })
    return out
