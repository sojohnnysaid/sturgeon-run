# CI snapshot fixture

These are **real, previously-captured** GBIF + USGS API responses for the
Hudson estuary — the same cached-snapshot mechanism the pipeline uses when live
APIs are unreachable (`data/snapshots/`, which stays gitignored). They are
committed here **only** so CI can run ingest deterministically and **off the
live GBIF/USGS APIs**. Nothing here is fabricated or hand-edited.

| File | Source | Contents |
|---|---|---|
| `gbif_taxa.json` | GBIF `species/match` | Flagship taxon → backbone key manifest (offline taxon resolution) |
| `gbif_occurrences_4287132.json` | GBIF `occurrence/search` | 29 real *Acipenser oxyrinchus* occurrences in the bbox |
| `usgs_sites.rdb` | USGS NWIS `site` | Active IV stream sites in the bbox |
| `usgs_iv.json` | USGS NWIS `iv` | Latest instantaneous values for those sites |

CI copies these into `data/snapshots/` and runs `make ingest-snapshot`, which
flags `snapshot_mode: true` in the quality report. To refresh them, run a live
`make ingest` and copy the regenerated `data/snapshots/*` here.
