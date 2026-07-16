"""One-shot, idempotent ingest orchestrator."""
from __future__ import annotations

import argparse
import logging
import sys

import requests

from . import db, gbif, report, usgs, validate
from .config import Config

log = logging.getLogger("sturgeon_ingest")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def run_gbif(cfg: Config, conn, use_snapshot: bool) -> dict:
    """Fetch, validate, load GBIF occurrences. Returns a source report dict."""
    snap_path = cfg.snapshot_dir / "gbif_occurrences.json"
    snapshot_mode = use_snapshot
    session = requests.Session()

    # Resolve taxon (needed for taxon_key + species upsert). Live even in
    # snapshot mode is cheap, but honor snapshot: try snapshot metadata via a
    # small live match; if that fails and snapshot exists, fall back.
    taxon_key = None
    rank = None
    if not use_snapshot:
        try:
            match = gbif.match_taxon(cfg.gbif_taxon_name, session=session)
            taxon_key = match["usageKey"]
            rank = match.get("rank")
        except Exception as exc:  # noqa: BLE001
            if snap_path.exists():
                log.warning("GBIF taxon match failed (%s); falling back to snapshot.", exc)
                snapshot_mode = True
            else:
                raise

    # Fetch occurrences.
    if snapshot_mode:
        raw = gbif.load_snapshot(snap_path)
    else:
        try:
            raw = gbif.fetch_occurrences_live(taxon_key, cfg.bbox, session=session)
            if cfg.write_snapshot:
                gbif.save_snapshot(raw, snap_path)
        except Exception as exc:  # noqa: BLE001
            if snap_path.exists():
                log.warning("GBIF live fetch FAILED (%s); FALLING BACK to snapshot.", exc)
                raw = gbif.load_snapshot(snap_path)
                snapshot_mode = True
            else:
                raise

    # If we never resolved a taxon key (pure snapshot mode), read existing one
    # from DB or fall back to a match attempt; species upsert still needs a key.
    if taxon_key is None:
        # Try a live match once more (metadata only) — but do not fail the whole
        # run if offline; use whatever is already stored.
        try:
            match = gbif.match_taxon(cfg.gbif_taxon_name, session=session)
            taxon_key = match["usageKey"]
            rank = match.get("rank")
        except Exception:  # noqa: BLE001
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gbif_taxon_key, rank FROM species WHERE scientific_name = %s",
                    (cfg.gbif_taxon_name,),
                )
                row = cur.fetchone()
            if row and row[0]:
                taxon_key, rank = row[0], row[1]
            else:
                raise RuntimeError(
                    "Cannot resolve GBIF taxon key (offline and none stored)."
                )

    species_id = db.upsert_species_taxon_key(conn, cfg.gbif_taxon_name, taxon_key, rank)

    records_fetched = len(raw)
    normalized = [gbif.normalize(r) for r in raw]

    drop_reasons = {
        "missing_coordinates": 0,
        "outside_bbox": 0,
        "excluded_basis_of_record": 0,
        "duplicate": 0,
    }
    null_date_count = 0

    # Dedup within run by gbif_id.
    deduped, dup_count = validate.dedup_by_key(normalized, "gbif_id")
    drop_reasons["duplicate"] += dup_count

    to_load: list[dict] = []
    for rec in deduped:
        lat = rec.get("decimalLatitude")
        lon = rec.get("decimalLongitude")
        if not validate.coords_valid(lat, lon):
            drop_reasons["missing_coordinates"] += 1
            continue
        latf, lonf = float(lat), float(lon)
        if not validate.in_bbox(latf, lonf, cfg.bbox):
            drop_reasons["outside_bbox"] += 1
            continue
        if validate.basis_excluded(rec.get("basisOfRecord")):
            drop_reasons["excluded_basis_of_record"] += 1
            continue
        event_date = validate.parse_event_date(rec.get("eventDate"))
        if event_date is None and rec.get("eventDate"):
            null_date_count += 1
        elif event_date is None:
            null_date_count += 1
        to_load.append({
            "gbif_id": rec.get("gbif_id"),
            "lat": latf,
            "lon": lonf,
            "event_date": event_date,
            "year": rec.get("year"),
            "basis_of_record": rec.get("basisOfRecord"),
            "coordinate_uncertainty": rec.get("coordinateUncertaintyInMeters"),
            "dataset_key": rec.get("datasetKey"),
            "institution_code": rec.get("institutionCode"),
        })

    written = db.upsert_occurrences(conn, species_id, to_load)
    records_kept = len(to_load)

    notes = f"GBIF backbone taxonKey {taxon_key}; bbox {cfg.bbox}"
    if null_date_count:
        notes += f"; kept {null_date_count} records with null/unparseable date"
    log.info(
        "GBIF summary: fetched=%d kept=%d written=%d drops=%s",
        records_fetched, records_kept, written, drop_reasons,
    )
    return report.build_source_report(
        "gbif", snapshot_mode, records_fetched, records_kept, drop_reasons, notes
    )


def run_usgs(cfg: Config, conn, use_snapshot: bool) -> dict:
    """Fetch, validate, load USGS sites + IV readings. Returns a source report dict."""
    sites_snap = cfg.snapshot_dir / "usgs_sites.rdb"
    iv_snap = cfg.snapshot_dir / "usgs_iv.json"
    snapshot_mode = use_snapshot
    session = requests.Session()

    # --- Sites ---
    site_rows: list[dict]
    if cfg.usgs_sites and not snapshot_mode:
        # Explicit site list: still need station metadata; fetch RDB for these.
        log.info("Using configured USGS_SITES: %s", cfg.usgs_sites)
        try:
            rdb = usgs.fetch_sites_live(cfg.bbox, session=session)
            if cfg.write_snapshot:
                usgs.save_sites_snapshot(rdb, sites_snap)
        except Exception as exc:  # noqa: BLE001
            if sites_snap.exists():
                log.warning("USGS site fetch failed (%s); using snapshot.", exc)
                rdb = usgs.load_sites_snapshot(sites_snap)
                snapshot_mode = True
            else:
                raise
        all_rows = usgs.parse_sites_rdb(rdb)
        wanted = set(cfg.usgs_sites)
        site_rows = [r for r in all_rows if (r.get("site_no") or "").strip() in wanted]
    elif snapshot_mode:
        rdb = usgs.load_sites_snapshot(sites_snap)
        site_rows = usgs.parse_sites_rdb(rdb)
    else:
        try:
            rdb = usgs.fetch_sites_live(cfg.bbox, session=session)
            if cfg.write_snapshot:
                usgs.save_sites_snapshot(rdb, sites_snap)
        except Exception as exc:  # noqa: BLE001
            if sites_snap.exists():
                log.warning("USGS site fetch FAILED (%s); FALLING BACK to snapshot.", exc)
                rdb = usgs.load_sites_snapshot(sites_snap)
                snapshot_mode = True
            else:
                raise
        site_rows = usgs.parse_sites_rdb(rdb)

    records_fetched = len(site_rows)
    drop_reasons = {"missing_coordinates": 0}
    station_id_by_site: dict[str, int] = {}
    kept_sites = 0

    for row in site_rows:
        s = usgs.normalize_site(row)
        if not s["site_no"]:
            continue
        if not validate.coords_valid(s["dec_lat_va"], s["dec_long_va"]):
            drop_reasons["missing_coordinates"] += 1
            continue
        station = {
            "site_no": s["site_no"],
            "name": s["station_nm"],
            "agency_cd": s["agency_cd"],
            "site_type_cd": s["site_tp_cd"],
            "lat": float(s["dec_lat_va"]),
            "lon": float(s["dec_long_va"]),
        }
        sid = db.upsert_station(conn, station)
        station_id_by_site[s["site_no"]] = sid
        kept_sites += 1

    # --- Instantaneous values ---
    site_numbers = list(station_id_by_site.keys())
    iv_json: dict
    if snapshot_mode:
        iv_json = usgs.load_iv_snapshot(iv_snap)
    else:
        try:
            iv_json = usgs.fetch_iv_live(site_numbers, session=session)
            if cfg.write_snapshot:
                usgs.save_iv_snapshot(iv_json, iv_snap)
        except Exception as exc:  # noqa: BLE001
            if iv_snap.exists():
                log.warning("USGS IV fetch FAILED (%s); FALLING BACK to snapshot.", exc)
                iv_json = usgs.load_iv_snapshot(iv_snap)
                snapshot_mode = True
            else:
                raise

    readings = usgs.parse_iv_latest(iv_json)
    readings_written = 0
    for rd in readings:
        sid = station_id_by_site.get(rd["site_no"])
        if sid is None:
            # Reading for a site we did not load (e.g. snapshot mismatch) — skip.
            continue
        if not rd.get("measured_at"):
            continue
        db.upsert_reading(conn, {
            "station_id": sid,
            "parameter_cd": rd["parameter_cd"],
            "parameter_name": rd["parameter_name"],
            "value": rd["value"],
            "unit": rd["unit"],
            "measured_at": rd["measured_at"],
            "qualifiers": rd["qualifiers"],
        })
        readings_written += 1

    notes = (
        f"NWIS IV; discovered {kept_sites} sites in bbox; "
        f"wrote {readings_written} latest readings"
    )
    log.info(
        "USGS summary: sites_fetched=%d sites_kept=%d readings_written=%d drops=%s",
        records_fetched, kept_sites, readings_written, drop_reasons,
    )
    # records_fetched/kept are about the primary spatial entity (stations).
    return report.build_source_report(
        "usgs", snapshot_mode, records_fetched, kept_sites, drop_reasons, notes
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="sturgeon_ingest", description="Sturgeon Run ingest job")
    parser.add_argument("--snapshot", action="store_true",
                        help="Load from data/snapshots instead of live APIs.")
    parser.add_argument("--source", choices=["gbif", "usgs", "all"], default="all")
    args = parser.parse_args(argv)

    cfg = Config.from_env()
    use_snapshot = args.snapshot or cfg.use_snapshot
    log.info(
        "Starting ingest: source=%s snapshot=%s bbox=%s",
        args.source, use_snapshot, cfg.bbox,
    )

    run_id = report.make_run_id()
    sources: list[dict] = []
    any_snapshot = False

    conn = db.connect(cfg.database_url)
    try:
        if args.source in ("gbif", "all"):
            src = run_gbif(cfg, conn, use_snapshot)
            sources.append(src)
            any_snapshot = any_snapshot or src["snapshot_mode"]
            db.insert_quality_report(conn, run_id, src)
        if args.source in ("usgs", "all"):
            src = run_usgs(cfg, conn, use_snapshot)
            sources.append(src)
            any_snapshot = any_snapshot or src["snapshot_mode"]
            db.insert_quality_report(conn, run_id, src)
    finally:
        conn.close()

    full = report.build_report(run_id, any_snapshot, sources)
    report.write_report(full, cfg.quality_report_path)

    log.info("Ingest complete: run_id=%s", run_id)
    for s in sources:
        log.info(
            "  %s: fetched=%d kept=%d dropped=%d snapshot=%s",
            s["source"], s["records_fetched"], s["records_kept"],
            s["records_dropped"], s["snapshot_mode"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
