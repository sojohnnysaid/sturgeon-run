# Sturgeon Run — internal contracts

Single source of truth for cross-service shapes. Services are built against
this doc so ingest, corridor-api, mcp, and web stay consistent. If you change a
shape here, update the producing and consuming services in the same PR.

## Environment / ports

| Service      | In-compose host   | Port | Host-exposed |
|--------------|-------------------|------|--------------|
| postgis      | `postgis`         | 5432 | 5432         |
| corridor-api | `corridor-api`    | 8080 | 8080         |
| tiles/Martin | `tiles`           | 3000 | 3000         |
| mcp          | `mcp`             | 8081 | 8081         |
| web          | `web`             | 5173 | 5173         |

`DATABASE_URL = postgres://$POSTGRES_USER:$POSTGRES_PASSWORD@postgis:5432/$POSTGRES_DB`

## Database (system of record)

Tables (see `db/init/02_schema.sql`): `species`, `occurrences`, `stations`,
`readings`, `corridor_cells`, `data_quality_reports`. Geometry is `EPSG:4326`.

## data/quality-report.json

Written by ingest; also mirrored into `data_quality_reports`. Shape:

```json
{
  "run_id": "20260715T2236Z-ab12cd",
  "generated_at": "2026-07-15T22:36:00Z",
  "snapshot_mode": false,
  "sources": [
    {
      "source": "gbif",
      "snapshot_mode": false,
      "records_fetched": 812,
      "records_kept": 640,
      "records_dropped": 172,
      "drop_reasons": {
        "missing_coordinates": 90,
        "outside_bbox": 51,
        "unparseable_date": 12,
        "excluded_basis_of_record": 14,
        "duplicate": 5
      },
      "notes": "GBIF backbone taxonKey 2408831; bbox NY Harbor->Troy"
    },
    {
      "source": "usgs",
      "snapshot_mode": false,
      "records_fetched": 60,
      "records_kept": 58,
      "records_dropped": 2,
      "drop_reasons": { "missing_coordinates": 2 },
      "notes": "NWIS IV; discovered N sites in bbox"
    }
  ]
}
```

`drop_reasons` keys are stable slugs the web layer panel renders as flags.

## corridor-api — HTTP (all responses `application/json`)

Base: `http://corridor-api:8080` (host: `http://localhost:8080`).

- `GET /healthz` → `{"status":"ok","db":"ok"}` (200) / `503` if DB down.

- `GET /api/species` → JSON array
  ```json
  [{"id":1,"gbif_taxon_key":2408831,"scientific_name":"Acipenser oxyrinchus","common_name":"Atlantic sturgeon"}]
  ```

- `GET /api/occurrences?from=YYYY-MM-DD&to=YYYY-MM-DD&species_id=1&limit=5000`
  → GeoJSON `FeatureCollection`. Each feature: `geometry` Point,
  `properties`: `{id, gbif_id, event_date, year, basis_of_record,
  coordinate_uncertainty, dataset_key}`. `from`/`to`/`species_id`/`limit`
  all optional; invalid date/int → `400 {"error":"..."}`.

- `GET /api/stations` → GeoJSON `FeatureCollection`, Point features.
  `properties`: `{id, site_no, name, agency_cd, site_type_cd}`.

- `GET /api/readings/latest?parameter_cd=00010` → JSON array of latest reading
  per (station,parameter): `[{station_id, site_no, name, parameter_cd,
  parameter_name, value, unit, measured_at}]`. `parameter_cd` optional filter.

- `GET /api/corridor?species_id=1` → GeoJSON `FeatureCollection`, Polygon
  (hex) features. `properties`: `{id, occurrence_count, hex_meters}`.

- `GET /api/corridor/summary?species_id=1` → JSON object
  ```json
  {"species_id":1,"cell_count":42,"occurrence_count":640,"hex_meters":2000,
   "max_cell_count":37,"computed_at":"2026-07-15T22:40:00Z","bbox":[-74.1,40.55,-73.6,42.75]}
  ```

## mcp — Streamable HTTP JSON-RPC

Single endpoint `POST /mcp` (host `http://localhost:8081/mcp`).
Stateless. `Authorization: Bearer $MCP_API_TOKEN` required; if `MCP_API_TOKEN`
unset the endpoint returns `503`. Missing/bad token → `401`.
JSON-RPC 2.0 methods: `initialize`, `tools/list`, `tools/call`, `ping`.

Tools (all read via corridor-api, never the DB directly):
`list_species`, `get_occurrences` (bbox+date range), `get_stations`,
`get_latest_readings`, `get_corridor_summary`, `get_data_quality_report`.

## Ownership (for parallel builds)

Each service owns ONLY its own directory + its Dockerfile. The following are
owned by the integrator (main agent) — service builders must not edit them:
`docker-compose.yml`, `.env.example`, `db/init/`, `k8s/`, `Makefile`,
`docs/CONTRACTS.md`, top-level `README.md`.
