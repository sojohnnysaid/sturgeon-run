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


def _resolve_taxa(cfg: Config, session, use_snapshot: bool) -> tuple[dict[str, dict], bool]:
    """Resolve every configured taxon name to GBIF backbone metadata.

    Returns (manifest, snapshot_mode). In snapshot mode we read the manifest
    written on a prior live run, so NO live GBIF call is made (deterministic /
    offline). Live mode matches each name and persists the manifest.
    """
    manifest_path = gbif.taxa_manifest_path(cfg.snapshot_dir)

    if use_snapshot:
        return gbif.load_taxa_manifest(manifest_path), True

    manifest: dict[str, dict] = {}
    try:
        for name in cfg.gbif_taxon_names:
            match = gbif.match_taxon(name, session=session)
            manifest[name] = {
                "usageKey": match["usageKey"],
                "rank": match.get("rank"),
                "scientificName": match.get("scientificName"),
            }
        if cfg.write_snapshot:
            gbif.save_taxa_manifest(manifest, manifest_path)
        return manifest, False
    except Exception as exc:  # noqa: BLE001
        if manifest_path.exists():
            log.warning("GBIF taxon match failed (%s); falling back to snapshot manifest.", exc)
            return gbif.load_taxa_manifest(manifest_path), True
        raise


def _load_one_taxon(cfg: Config, conn, session, name: str, meta: dict,
                    snapshot_mode: bool) -> dict:
    """Fetch/load, validate, and upsert occurrences for a single taxon.
    Returns a per-species stats dict."""
    taxon_key = meta["usageKey"]
    rank = meta.get("rank")
    snap_path = gbif.occurrences_snapshot_path(cfg.snapshot_dir, taxon_key)
    this_snapshot = snapshot_mode

    if this_snapshot:
        raw = gbif.load_snapshot(snap_path)
    else:
        try:
            raw = gbif.fetch_occurrences_live(taxon_key, cfg.bbox, session=session)
            if cfg.write_snapshot:
                gbif.save_snapshot(raw, snap_path)
        except Exception as exc:  # noqa: BLE001
            if snap_path.exists():
                log.warning("GBIF live fetch FAILED for %r (%s); FALLING BACK to snapshot.",
                            name, exc)
                raw = gbif.load_snapshot(snap_path)
                this_snapshot = True
            else:
                raise

    species_id = db.upsert_species_taxon_key(conn, name, taxon_key, rank)

    normalized = [gbif.normalize(r) for r in raw]
    drop_reasons = {
        "missing_coordinates": 0,
        "outside_bbox": 0,
        "excluded_basis_of_record": 0,
        "duplicate": 0,
    }
    null_date_count = 0
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
        if event_date is None:
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
    log.info(
        "GBIF %r (species_id=%d, key=%s): fetched=%d kept=%d written=%d drops=%s",
        name, species_id, taxon_key, len(raw), len(to_load), written,
        {k: v for k, v in drop_reasons.items() if v},
    )
    return {
        "name": name,
        "species_id": species_id,
        "taxon_key": taxon_key,
        "records_fetched": len(raw),
        "records_kept": len(to_load),
        "drop_reasons": drop_reasons,
        "null_dates": null_date_count,
        "snapshot_mode": this_snapshot,
    }


def run_gbif(cfg: Config, conn, use_snapshot: bool) -> dict:
    """Fetch, validate, load GBIF occurrences for every configured taxon.
    Returns ONE 'gbif' source report whose notes carry per-species counts."""
    session = requests.Session()
    manifest, snapshot_mode = _resolve_taxa(cfg, session, use_snapshot)

    per_species: list[dict] = []
    for name in cfg.gbif_taxon_names:
        meta = manifest.get(name)
        if meta is None:
            # Snapshot manifest lacks a name that was added to the config: honest
            # failure rather than silently skipping a requested taxon.
            raise RuntimeError(
                f"No GBIF manifest entry for {name!r} in {gbif.taxa_manifest_path(cfg.snapshot_dir)}. "
                "Run a live ingest once (WRITE_SNAPSHOT=1) to record it."
            )
        stats = _load_one_taxon(cfg, conn, session, name, meta, snapshot_mode)
        per_species.append(stats)

    # Aggregate into a single per-source report, summing drop reasons and
    # noting per-species counts (contract keeps one row per source).
    agg_reasons: dict[str, int] = {}
    total_fetched = total_kept = total_null = 0
    any_snapshot = False
    for s in per_species:
        total_fetched += s["records_fetched"]
        total_kept += s["records_kept"]
        total_null += s["null_dates"]
        any_snapshot = any_snapshot or s["snapshot_mode"]
        for k, v in s["drop_reasons"].items():
            agg_reasons[k] = agg_reasons.get(k, 0) + v

    per_species_note = "; ".join(
        f"{s['name']} (key={s['taxon_key']}, species_id={s['species_id']}) "
        f"kept={s['records_kept']}/{s['records_fetched']}"
        for s in per_species
    )
    notes = (
        f"GBIF backbone; {len(per_species)} taxa; bbox {cfg.bbox}; "
        f"per-species: {per_species_note}"
    )
    if total_null:
        notes += f"; kept {total_null} records with null/unparseable date"

    log.info(
        "GBIF summary (all taxa): fetched=%d kept=%d drops=%s",
        total_fetched, total_kept, {k: v for k, v in agg_reasons.items() if v},
    )
    return report.build_source_report(
        "gbif", any_snapshot, total_fetched, total_kept, agg_reasons, notes
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
