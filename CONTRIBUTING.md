# Contributing to Sturgeon Run

Sturgeon Run is built to be extended by research groups, not just read. The two
most common contributions — adding a **species** and adding a **data layer** —
are sketched below. Please keep the project's core promise: **be honest about
data quality and provenance.** Every layer must carry its counts and its
caveats.

## Ground rules

- Data must be real and attributed. No synthetic or hand-edited "example"
  records in the pipeline. If an upstream API is down, use the snapshot path
  (`data/snapshots/`) and label snapshot mode in the quality report — never
  fabricate.
- Anything derived (like the corridor hex-bin layer) must be documented as
  derived, with its method, in the README's **Data & Limitations** section.
- Cross-service shapes live in `docs/CONTRACTS.md`. Change them there first,
  then update the producing and consuming services in the same PR.

## Dev setup

```bash
cp .env.example .env          # set MCP_API_TOKEN if you want the MCP endpoint
make up                       # postgis, corridor-api, tiles, mcp, web
make ingest                   # pull real GBIF + USGS data
make derive                   # compute the corridor layer
make smoke                    # verify everything answers
make test                     # ingest (pytest) + corridor-api (cargo) tests
```

`make test` is self-provisioning for Python: the validator tests run **inside
the ingest Docker image** (pytest is pinned in `ingest/requirements.txt`), so
you need no host Python packages — only Docker and a Rust toolchain for the
`corridor-api` tests. Run just one side with `make test-python` or
`make test-rust`.

## Adding a new species

The pipeline is taxon-driven, so a new species is mostly configuration + a
re-run.

1. **Register the taxon.** Add a row to `species` (see
   `db/init/02_schema.sql`) — scientific name and common name. On a running DB:
   ```sql
   INSERT INTO species (scientific_name, common_name, rank)
   VALUES ('Morone saxatilis', 'Striped bass', 'SPECIES')
   ON CONFLICT (scientific_name) DO NOTHING;
   ```
2. **Point ingest at it.** Add the scientific name to `GBIF_TAXON_NAMES` in
   `.env` — it's a comma-separated list, e.g.
   `GBIF_TAXON_NAMES="Acipenser oxyrinchus,Morone saxatilis"`. Ingest resolves
   each GBIF backbone key, upserts a `species` row, and keys occurrences by
   `species_id`. (Step 1's manual `INSERT` is optional — ingest upserts the
   species for you; use it only to set a `common_name`.)
3. **Re-run** `make ingest` (idempotent — iterates every taxon) and
   `make derive` (recomputes the corridor for *every* `species_id`).
4. The API, MCP tools, and web layer panel are species-aware
   (`?species_id=`), so the new taxon appears without front-end changes.
   `list_species` / `GET /api/species` will show it.

## Adding a new data layer

Example: sea-surface salinity, or a bathymetry overlay.

1. **Schema.** Add a table in `db/init/` (new numbered file, or a migration)
   with a `geometry(..., 4326)` column and a GIST index.
2. **Ingest.** Add a module under `ingest/sturgeon_ingest/` that fetches +
   validates the source and upserts idempotently, and add its counts to the
   quality report (`report.py`) so provenance shows up everywhere.
3. **Serve.** Add a `GET /api/<layer>` endpoint in `corridor-api` returning a
   GeoJSON FeatureCollection (copy an existing handler; build the JSON in
   Postgres with `ST_AsGeoJSON`). Update `docs/CONTRACTS.md`.
4. **Tiles (optional).** If the layer is dense, expose it to Martin (table
   source or SQL function) so it renders as vector tiles instead of raw
   GeoJSON.
5. **Agents.** Add an MCP tool in `mcp/src/` (zod schema → JSON Schema) that
   reads the new endpoint, so agents get the layer too.
6. **Web.** Add a layer entry to the field-log panel in `web/src/` with its
   live count and quality flags.

## Tests & checks before a PR

- `make test` (Python validators + Rust query-param tests) is green.
- `make smoke` passes against a running stack with data loaded.
- New/changed cross-service shapes are reflected in `docs/CONTRACTS.md`.
- The README's **Data & Limitations** section covers any new source or derived
  artifact, with attribution.

## Attribution

If you add a source, add its citation requirements to the README. GBIF requires
a dataset-level citation (a GBIF download DOI is ideal for reproducible work);
USGS water data is public-domain but should be credited to the U.S. Geological
Survey National Water Information System.
