"""PostGIS access via psycopg v3. Idempotent upserts wrapped in transactions."""
from __future__ import annotations

import logging
from typing import Optional

import psycopg

log = logging.getLogger("sturgeon_ingest.db")


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def upsert_species_taxon_key(
    conn: psycopg.Connection, scientific_name: str, taxon_key: int, rank: Optional[str]
) -> int:
    """Ensure the species row exists and its gbif_taxon_key is set. Returns species id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO species (scientific_name, gbif_taxon_key, rank)
            VALUES (%s, %s, %s)
            ON CONFLICT (scientific_name) DO UPDATE
                SET gbif_taxon_key = EXCLUDED.gbif_taxon_key,
                    rank = COALESCE(EXCLUDED.rank, species.rank)
            RETURNING id
            """,
            (scientific_name, taxon_key, rank),
        )
        species_id = cur.fetchone()[0]
    conn.commit()
    log.info("Upserted species %r id=%d gbif_taxon_key=%s", scientific_name, species_id, taxon_key)
    return species_id


def upsert_occurrences(conn: psycopg.Connection, species_id: int, records: list[dict]) -> int:
    """Upsert normalized occurrence records. Returns number of rows written.

    Each record: gbif_id, lat, lon, event_date (date|None), year, basis_of_record,
    coordinate_uncertainty, dataset_key, institution_code.
    """
    if not records:
        return 0
    written = 0
    with conn.cursor() as cur:
        for r in records:
            cur.execute(
                """
                INSERT INTO occurrences (
                    gbif_id, species_id, event_date, year, basis_of_record,
                    coordinate_uncertainty, dataset_key, institution_code, geom
                )
                VALUES (
                    %(gbif_id)s, %(species_id)s, %(event_date)s, %(year)s, %(basis_of_record)s,
                    %(coordinate_uncertainty)s, %(dataset_key)s, %(institution_code)s,
                    ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)
                )
                ON CONFLICT (gbif_id) DO UPDATE SET
                    species_id = EXCLUDED.species_id,
                    event_date = EXCLUDED.event_date,
                    year = EXCLUDED.year,
                    basis_of_record = EXCLUDED.basis_of_record,
                    coordinate_uncertainty = EXCLUDED.coordinate_uncertainty,
                    dataset_key = EXCLUDED.dataset_key,
                    institution_code = EXCLUDED.institution_code,
                    geom = EXCLUDED.geom
                """,
                {**r, "species_id": species_id},
            )
            written += 1
    conn.commit()
    log.info("Upserted %d occurrences", written)
    return written


def upsert_station(conn: psycopg.Connection, station: dict) -> int:
    """Upsert one station by site_no. Returns station id.

    station: site_no, name, agency_cd, site_type_cd, lat, lon.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stations (site_no, name, agency_cd, site_type_cd, geom)
            VALUES (
                %(site_no)s, %(name)s, %(agency_cd)s, %(site_type_cd)s,
                ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)
            )
            ON CONFLICT (site_no) DO UPDATE SET
                name = EXCLUDED.name,
                agency_cd = EXCLUDED.agency_cd,
                site_type_cd = EXCLUDED.site_type_cd,
                geom = EXCLUDED.geom
            RETURNING id
            """,
            station,
        )
        station_id = cur.fetchone()[0]
    conn.commit()
    return station_id


def upsert_reading(conn: psycopg.Connection, reading: dict) -> None:
    """Upsert one reading by (station_id, parameter_cd, measured_at).

    reading: station_id, parameter_cd, parameter_name, value, unit,
    measured_at, qualifiers.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO readings (
                station_id, parameter_cd, parameter_name, value, unit,
                measured_at, qualifiers
            )
            VALUES (
                %(station_id)s, %(parameter_cd)s, %(parameter_name)s, %(value)s,
                %(unit)s, %(measured_at)s, %(qualifiers)s
            )
            ON CONFLICT (station_id, parameter_cd, measured_at) DO UPDATE SET
                parameter_name = EXCLUDED.parameter_name,
                value = EXCLUDED.value,
                unit = EXCLUDED.unit,
                qualifiers = EXCLUDED.qualifiers
            """,
            reading,
        )
    conn.commit()


def insert_quality_report(conn: psycopg.Connection, run_id: str, source: dict) -> None:
    """Insert one data_quality_reports row for a source within a run."""
    import json as _json
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO data_quality_reports (
                run_id, source, snapshot_mode, records_fetched, records_kept,
                records_dropped, drop_reasons, notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                run_id,
                source["source"],
                source["snapshot_mode"],
                source["records_fetched"],
                source["records_kept"],
                source["records_dropped"],
                _json.dumps(source["drop_reasons"]),
                source.get("notes"),
            ),
        )
    conn.commit()
    log.info("Inserted data_quality_reports row: run=%s source=%s", run_id, source["source"])


def get_species_id(conn: psycopg.Connection, scientific_name: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM species WHERE scientific_name = %s", (scientific_name,))
        row = cur.fetchone()
        return row[0] if row else None
