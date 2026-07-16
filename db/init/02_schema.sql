-- Sturgeon Run — system of record schema
-- All geometry stored as EPSG:4326 (WGS84 lon/lat). Derived layers may cache
-- a metric SRID for area/aggregation but the canonical serving CRS is 4326.

-- ---------------------------------------------------------------------------
-- Reference: species we track. Small controlled vocabulary; the platform is
-- built so a research group can add rows here and re-run ingest for new taxa.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS species (
    id              SERIAL PRIMARY KEY,
    gbif_taxon_key  BIGINT UNIQUE,               -- GBIF backbone usageKey
    scientific_name TEXT NOT NULL UNIQUE,
    common_name     TEXT,
    rank            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the flagship taxon. Ingest upserts the resolved GBIF key.
INSERT INTO species (scientific_name, common_name, rank)
VALUES ('Acipenser oxyrinchus', 'Atlantic sturgeon', 'SPECIES')
ON CONFLICT (scientific_name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Occurrences: cleaned GBIF species occurrence records (points).
-- gbif_id is the GBIF occurrence key and gives us idempotent upserts.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS occurrences (
    id                     BIGSERIAL PRIMARY KEY,
    gbif_id                BIGINT UNIQUE,           -- GBIF occurrence key
    species_id             INTEGER NOT NULL REFERENCES species(id),
    event_date             DATE,                    -- null when GBIF omits it
    year                   INTEGER,
    basis_of_record        TEXT,
    coordinate_uncertainty DOUBLE PRECISION,        -- meters, when provided
    dataset_key            TEXT,
    institution_code       TEXT,
    geom                   geometry(Point, 4326) NOT NULL,
    ingested_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Stations: USGS NWIS monitoring sites (points).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stations (
    id           SERIAL PRIMARY KEY,
    site_no      TEXT UNIQUE NOT NULL,             -- USGS site number
    name         TEXT,
    agency_cd    TEXT,
    site_type_cd TEXT,
    geom         geometry(Point, 4326) NOT NULL,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Readings: USGS instantaneous-value observations tied to a station.
-- One row per (station, parameter, datetime). Dedup via the unique key.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS readings (
    id             BIGSERIAL PRIMARY KEY,
    station_id     INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    parameter_cd   TEXT NOT NULL,                  -- USGS 5-digit parameter code
    parameter_name TEXT,
    value          DOUBLE PRECISION,
    unit           TEXT,
    measured_at    TIMESTAMPTZ NOT NULL,
    qualifiers     TEXT,
    ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT readings_uniq UNIQUE (station_id, parameter_cd, measured_at)
);

-- ---------------------------------------------------------------------------
-- Corridor cells: DERIVED layer. A hex-bin density surface computed from
-- occurrences by the corridor-api. This is a statistical artifact of where
-- records exist, NOT a tracked animal path. Recomputed, so it is safe to wipe.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corridor_cells (
    id               BIGSERIAL PRIMARY KEY,
    species_id       INTEGER NOT NULL REFERENCES species(id),
    occurrence_count INTEGER NOT NULL,
    hex_meters       INTEGER NOT NULL,             -- cell size used to derive
    geom             geometry(Polygon, 4326) NOT NULL,
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Data quality report: one row per ingest run per source. Mirrors the JSON
-- written to data/quality-report.json so the API/MCP/web can show provenance.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_quality_reports (
    id                SERIAL PRIMARY KEY,
    run_id            TEXT NOT NULL,               -- shared across sources in a run
    source            TEXT NOT NULL,               -- 'gbif' | 'usgs'
    snapshot_mode     BOOLEAN NOT NULL DEFAULT false,
    records_fetched   INTEGER NOT NULL DEFAULT 0,
    records_kept      INTEGER NOT NULL DEFAULT 0,
    records_dropped   INTEGER NOT NULL DEFAULT 0,
    drop_reasons      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {reason: count}
    notes             TEXT,
    run_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
